import os
import json
import asyncio
import uuid
import re
from datetime import datetime, timezone
from contextlib import suppress
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from . import database
from .playfab import PlayFab, PlayFabError

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT.parent / ".env")

TITLE_ID = os.getenv("PLAYFAB_TITLE_ID", "").strip()
SECRET_KEY = os.getenv("PLAYFAB_SECRET_KEY", "").strip()
CATALOG_VERSION = os.getenv("PLAYFAB_CATALOG_VERSION", "Catalog").strip()
HOST = os.getenv("HOST", "127.0.0.1")
if HOST not in ("127.0.0.1", "localhost", "::1"):
    raise RuntimeError("Security stop: BOINGUS Admin must bind to localhost only.")

pf = PlayFab(TITLE_ID, SECRET_KEY)
app = FastAPI(title="BOINGUS Local Admin")
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
clients: set[WebSocket] = set()
sync_task = None

# Player search index is cached locally in memory to avoid querying PlayFab on
# every keystroke. Set PLAYFAB_ALL_PLAYERS_SEGMENT_ID in .env to override
# automatic detection of the "All Players" segment.
player_index = []
player_index_loaded_at = 0.0
player_index_lock = asyncio.Lock()
PLAYER_INDEX_TTL = 300

@app.on_event("startup")
async def startup():
    global sync_task
    database.initialize()
    sync_task = asyncio.create_task(report_sync_loop())

@app.on_event("shutdown")
async def shutdown():
    global sync_task
    if sync_task:
        sync_task.cancel()
        with suppress(asyncio.CancelledError):
            await sync_task

async def report_sync_loop():
    # Pulls CloudScript's BOINGUS_Report_* Title Internal Data records into SQLite.
    while True:
        if TITLE_ID and SECRET_KEY:
            try:
                result = await pf.get_title_internal_data()
                data = result.get("Data", {}) or {}
                changed = False
                for key, record in data.items():
                    if not key.startswith("BOINGUS_Report_"):
                        continue
                    raw = record.get("Value") if isinstance(record, dict) else record
                    if not raw:
                        continue
                    try:
                        report = json.loads(raw)
                        if report.get("reportID") and report.get("targetPlayFabID"):
                            database.save_report(report)
                            changed = True
                    except (TypeError, ValueError):
                        continue
                if changed:
                    await broadcast({"type": "reports_changed"})
            except Exception as exc:
                print(f"[PlayFab report sync] {exc}")
        await asyncio.sleep(30)

@app.get("/")
async def index():
    return FileResponse(ROOT / "static" / "index.html")

@app.get("/api/status")
async def status():
    configured = bool(TITLE_ID and SECRET_KEY)
    return {"local": True, "playfab_configured": configured, "title_id_set": bool(TITLE_ID),
            "catalog_version": CATALOG_VERSION, **database.report_stats()}

@app.get("/api/home")
async def home():
    return {**database.report_stats(), "recent_reports": database.recent_reports(8),
            "playfab_configured": bool(TITLE_ID and SECRET_KEY)}

@app.get("/api/reports")
async def reports(limit: int = 100):
    return {"reports": database.recent_reports(max(1, min(limit, 500)))}

@app.post("/api/local/reports")
async def ingest_local_report(payload: dict):
    if not payload.get("reportID") or not payload.get("targetPlayFabID"):
        raise HTTPException(400, "Report is missing its ID or target PlayFab ID.")
    database.save_report(payload)
    await broadcast({"type": "reports_changed"})
    return {"ok": True}

@app.get("/api/player/{playfab_id}")
async def player(playfab_id: str):
    try:
        account = await pf.get_account(playfab_id=playfab_id)
        internal = await pf.get_user_internal_data(playfab_id)
        bans = await pf.get_user_bans(playfab_id)
        inventory_error = None
        try:
            inventory = await pf.get_user_inventory(playfab_id)
        except PlayFabError as exc:
            inventory = {"VirtualCurrency": {}}
            inventory_error = str(exc)
        cloud_notes = []
        for key, record in (internal.get("Data", {}) or {}).items():
            if key.startswith("BOINGUS_Note_"):
                raw = record.get("Value") if isinstance(record, dict) else record
                try:
                    cloud_notes.append(json.loads(raw))
                except (TypeError, ValueError):
                    pass
        report_history = database.player_reports(playfab_id)
        return {"account": account, "internal_data": internal, "bans": bans, "inventory": inventory, "inventory_error": inventory_error,
                "local_notes": database.get_notes(playfab_id),
                "playfab_notes": sorted(cloud_notes, key=lambda x: x.get("createdAt", ""), reverse=True),
                **report_history}
    except PlayFabError as exc:
        raise HTTPException(502, str(exc))


def _profile_values(profile: dict):
    if not isinstance(profile, dict):
        return None
    account = profile.get("PlayerProfile") or profile.get("Profile") or profile
    title_info = account.get("TitleInfo") or {}
    player_id = profile.get("PlayerId") or profile.get("PlayFabId") or account.get("PlayerId") or account.get("PlayFabId")
    if not player_id:
        return None
    return {
        "playFabId": str(player_id),
        "displayName": account.get("TitleDisplayName") or account.get("DisplayName") or title_info.get("DisplayName") or account.get("Username") or "Unknown",
        "username": account.get("Username") or "",
        "created": title_info.get("Created") or account.get("Created") or "",
        "lastLogin": title_info.get("LastLogin") or "",
        "isBanned": bool(title_info.get("isBanned", False))
    }


async def _load_player_index(force=False):
    global player_index, player_index_loaded_at
    now = asyncio.get_running_loop().time()
    if not force and player_index_loaded_at and now - player_index_loaded_at < PLAYER_INDEX_TTL:
        return player_index
    async with player_index_lock:
        now = asyncio.get_running_loop().time()
        if not force and player_index_loaded_at and now - player_index_loaded_at < PLAYER_INDEX_TTL:
            return player_index
        configured_segment = os.getenv("PLAYFAB_ALL_PLAYERS_SEGMENT_ID", "").strip()
        if configured_segment:
            segment_id = configured_segment
        else:
            segments_result = await pf.get_all_segments()
            segments = segments_result.get("Segments", []) or []
            all_players = next((s for s in segments if str(s.get("Name", "")).strip().lower() == "all players"), None)
            if not all_players:
                raise PlayFabError('Could not find a PlayFab segment named "All Players". Create/enable that segment or set PLAYFAB_ALL_PLAYERS_SEGMENT_ID in .env.')
            segment_id = all_players.get("Id")
        if not segment_id:
            raise PlayFabError("The All Players segment did not contain a segment ID.")
        fresh, token = [], None
        for _ in range(20):
            page = await pf.get_players_in_segment(segment_id, token, 10000)
            for profile in page.get("PlayerProfiles", []) or []:
                normalized = _profile_values(profile)
                if normalized:
                    fresh.append(normalized)
            token = page.get("ContinuationToken")
            if not token:
                break
        player_index = fresh
        player_index_loaded_at = asyncio.get_running_loop().time()
        return player_index


@app.get("/api/player-search")
async def player_search(q: str):
    q = q.strip()
    if len(q) < 3:
        raise HTTPException(400, "Type at least 3 characters to search.")
    try:
        if len(q) >= 16 and re.fullmatch(r"[A-Za-z0-9-]+", q):
            result = await pf.get_account(playfab_id=q)
            info = result.get("UserInfo") or result.get("AccountInfo") or {}
            title = info.get("TitleInfo") or {}
            return {"results": [{
                "playFabId": info.get("PlayFabId", q),
                "displayName": title.get("DisplayName") or info.get("Username") or "Unknown",
                "username": info.get("Username") or "",
                "created": title.get("Created") or info.get("Created") or "",
                "lastLogin": title.get("LastLogin") or "",
                "isBanned": bool(title.get("isBanned", False))
            }]}
        index = await _load_player_index()
        needle = q.casefold()
        matches = [p for p in index if needle in p["playFabId"].casefold()
                   or needle in p["displayName"].casefold() or needle in p["username"].casefold()]
        return {"results": matches[:25], "total_cached": len(index)}
    except PlayFabError as exc:
        raise HTTPException(502, str(exc))

class NoteRequest(BaseModel):
    note: str = Field(min_length=1, max_length=2000)
    category: str = Field(default="General", max_length=40)

@app.get("/api/player/{playfab_id}/notes")
async def player_notes(playfab_id: str):
    return {"notes": database.get_notes(playfab_id)}

@app.post("/api/player/{playfab_id}/notes")
async def create_note(playfab_id: str, body: NoteRequest):
    note = database.add_note(playfab_id, body.note.strip(), body.category)
    cloud_sync = "failed"
    cloud_error = None
    try:
        # One internal-data key per note avoids a single ever-growing JSON blob.
        key = "BOINGUS_Note_" + note["noteID"].replace("-", "")
        await pf.update_user_internal_data(playfab_id, {key: json.dumps(note)})
        cloud_sync = "saved"
    except PlayFabError as exc:
        cloud_error = str(exc)
    await broadcast({"type": "player_notes_changed", "playfab_id": playfab_id})
    return {"ok": True, "note": note, "cloud_sync": cloud_sync, "cloud_error": cloud_error}

@app.post("/api/player/{playfab_id}/local-notes")
async def create_local_note(playfab_id: str, body: NoteRequest):
    note = database.add_note(playfab_id, body.note.strip(), body.category)
    await broadcast({"type": "player_notes_changed", "playfab_id": playfab_id})
    return {"ok": True, "note": note}

@app.get("/api/title-data")
async def title_data():
    try:
        result = await pf.get_title_data(["MOTD", "GameVersion"])
        return {"data": result.get("Data", {})}
    except PlayFabError as exc:
        raise HTTPException(502, str(exc))

class TitleDataRequest(BaseModel):
    key: str = Field(min_length=1, max_length=100)
    value: str = Field(max_length=10000)

@app.put("/api/title-data")
async def update_title_data(body: TitleDataRequest):
    if body.key not in ("MOTD", "GameVersion"):
        raise HTTPException(400, "Only MOTD and GameVersion are enabled in this first stage.")
    try:
        await pf.set_title_data(body.key, body.value)
        await broadcast({"type": "title_data_changed", "key": body.key})
        return {"ok": True, "key": body.key}
    except PlayFabError as exc:
        raise HTTPException(502, str(exc))

@app.get("/api/catalog")
async def catalog():
    try:
        result = await pf.get_catalog(CATALOG_VERSION)
        return {"catalog": result.get("Catalog", []), "catalog_version": CATALOG_VERSION}
    except PlayFabError as exc:
        raise HTTPException(502, str(exc))

@app.get("/api/bans/{playfab_id}")
async def player_bans(playfab_id: str):
    try:
        return await pf.get_user_bans(playfab_id)
    except PlayFabError as exc:
        raise HTTPException(502, str(exc))

async def broadcast(message: dict):
    dead = []
    for ws in list(clients):
        try:
            await ws.send_json(message)
        except Exception:
            dead.append(ws)
    for ws in dead:
        clients.discard(ws)

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    clients.add(ws)
    try:
        await ws.send_json({"type": "connected"})
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        clients.discard(ws)
