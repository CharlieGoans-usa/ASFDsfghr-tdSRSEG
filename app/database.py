import json
import sqlite3
from pathlib import Path
from datetime import datetime, timezone

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "boingus_admin.db"

def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    return db

def initialize():
    with connect() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS reports (
            report_id TEXT PRIMARY KEY,
            target_playfab_id TEXT NOT NULL,
            target_username TEXT,
            reporter_playfab_id TEXT,
            reporter_rank TEXT,
            reason TEXT,
            priority TEXT,
            status TEXT DEFAULT 'Pending',
            timestamp TEXT,
            lobby_id TEXT,
            photon_region TEXT,
            raw_json TEXT NOT NULL,
            synced_at TEXT
        );
        CREATE TABLE IF NOT EXISTS player_notes (
            note_id TEXT PRIMARY KEY,
            playfab_id TEXT NOT NULL,
            note TEXT NOT NULL,
            category TEXT DEFAULT 'General',
            created_at TEXT NOT NULL,
            author TEXT DEFAULT 'Local Admin'
        );
        CREATE TABLE IF NOT EXISTS moderation_actions (
            action_id TEXT PRIMARY KEY,
            playfab_id TEXT NOT NULL,
            action_type TEXT NOT NULL,
            reason TEXT,
            duration_hours REAL,
            created_at TEXT NOT NULL,
            actor TEXT DEFAULT 'Local Admin',
            synced_to_playfab INTEGER DEFAULT 0,
            raw_json TEXT
        );
        CREATE TABLE IF NOT EXISTS sync_state (
            key TEXT PRIMARY KEY,
            value TEXT
        );
        """)

def save_report(report: dict):
    now = datetime.now(timezone.utc).isoformat()
    with connect() as db:
        db.execute("""
        INSERT INTO reports (
            report_id,target_playfab_id,target_username,reporter_playfab_id,
            reporter_rank,reason,priority,status,timestamp,lobby_id,photon_region,
            raw_json,synced_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(report_id) DO UPDATE SET
            status=excluded.status, raw_json=excluded.raw_json, synced_at=excluded.synced_at
        """, (
            report.get("reportID"), report.get("targetPlayFabID"), report.get("targetUsername"),
            report.get("reporterPlayFabID"), report.get("reporterRank"), report.get("reason"),
            report.get("priority"), report.get("status", "Pending"), report.get("timestamp"),
            report.get("lobbyID"), report.get("photonRegion"),
            json.dumps(report), now
        ))

def report_stats():
    with connect() as db:
        total = db.execute("SELECT COUNT(*) FROM reports").fetchone()[0]
        pending = db.execute("SELECT COUNT(*) FROM reports WHERE status='Pending'").fetchone()[0]
        return {"reports_total": total, "reports_pending": pending}

def recent_reports(limit=20):
    with connect() as db:
        rows = db.execute("SELECT raw_json FROM reports ORDER BY timestamp DESC LIMIT ?", (limit,)).fetchall()
        return [json.loads(row["raw_json"]) for row in rows]

def add_note(playfab_id: str, note: str, category="General"):
    import uuid
    created = datetime.now(timezone.utc).isoformat()
    note_obj = {"noteID": str(uuid.uuid4()), "playFabID": playfab_id, "note": note,
                "category": category, "createdAt": created, "author": "Local Admin"}
    with connect() as db:
        db.execute("INSERT INTO player_notes VALUES (?,?,?,?,?,?)",
                   (note_obj["noteID"], playfab_id, note, category, created, "Local Admin"))
    return note_obj

def get_notes(playfab_id: str):
    with connect() as db:
        rows = db.execute("SELECT note_id,note,category,created_at,author FROM player_notes WHERE playfab_id=? ORDER BY created_at DESC",
                          (playfab_id,)).fetchall()
        return [dict(row) for row in rows]


def player_reports(playfab_id: str):
    with connect() as db:
        against = db.execute(
            "SELECT raw_json FROM reports WHERE target_playfab_id=? ORDER BY timestamp DESC",
            (playfab_id,)
        ).fetchall()
        submitted = db.execute(
            "SELECT raw_json FROM reports WHERE reporter_playfab_id=? ORDER BY timestamp DESC",
            (playfab_id,)
        ).fetchall()
    return {
        "reports_against": [json.loads(row["raw_json"]) for row in against],
        "reports_submitted": [json.loads(row["raw_json"]) for row in submitted]
    }
