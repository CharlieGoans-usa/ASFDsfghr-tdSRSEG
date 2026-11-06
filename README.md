# BOINGUS Local Admin Panel — Phase 1

This is the local-only foundation for the BOINGUS moderation panel.

## Included
- FastAPI backend bound to `127.0.0.1`
- Browser dashboard shell with the agreed sidebar
- WebSocket connection for live local updates
- SQLite database for local report copies, notes, and moderation audit entries
- PlayFab REST client wrapper using the title secret key on the Python server only
- Initial PlayFab reads for Title Data, player account lookup, bans, and legacy catalog items
- Local configuration via `.env`

## Setup
1. Install Python 3.11 or newer.
2. Extract this folder somewhere convenient.
3. Run `run.bat`.
4. On first run, `.env` is copied from `.env.example`.
5. Edit `.env` and enter your PlayFab Title ID and Developer Secret Key.
6. Restart `run.bat` and open `http://127.0.0.1:8765`.

## Security
- The app binds to `127.0.0.1`, not your LAN.
- The PlayFab secret key is read only by Python and is never sent to browser JavaScript.
- Do not upload `.env`, the SQLite database, or backups publicly.
- This is a development foundation, not yet a finished moderation tool. Destructive actions (ban/unban, catalog replacement/deletion) are deliberately not exposed in this first build.

## Important PlayFab notes
- The project uses PlayFab's legacy catalog endpoints because BOINGUS currently uses legacy Catalogs.
- Legacy Economy is in bug-fix-only mode. This panel will keep using the existing catalog rather than silently migrating your game.
- Reports must be saved by CloudScript when players submit them. The included CloudScript file is a proposed update to your current script; review and deploy it before expecting cloud report history to populate.
- The local SQLite archive stores records received by this panel. It cannot recover historical reports that were never stored in PlayFab or locally.

## Next implementation stage
1. Confirm the Title ID and catalog version (do not paste your secret key into chat).
2. Deploy the CloudScript report persistence update.
3. Verify report synchronization and dual-storage player notes.
4. Add verified ban/unban and catalog create/edit/delete operations with confirmation and audit logging.

## UPDATE #1 PLAYER SEARCH

BOINGUS Admin Panel - Player Search Update

Replace these files in your existing BOINGUS_Admin_Panel folder, preserving the same paths:
- app/main.py
- app/playfab.py
- app/static/app.js
- app/static/index.html
- app/static/style.css

Then stop the currently running server window (Ctrl+C) and run run.bat again.
Open http://127.0.0.1:9271/ if that is the port configured in your run.bat.

How player autocomplete works:
- Type at least 3 characters of a PlayFab ID, display name, or username.
- Matching accounts appear underneath the search field.
- Click a result to load its full profile.
- The player index is cached in memory for 5 minutes.

PlayFab requirement:
The backend finds the "All Players" segment through Admin/GetAllSegments, then reads its player profiles using Admin/GetPlayersInSegment. If your title does not have a segment named exactly "All Players", add this optional setting to .env:
PLAYFAB_ALL_PLAYERS_SEGMENT_ID=YOUR_SEGMENT_ID

The segment ID is not a secret. Do not share your PlayFab Developer Secret Key.

The player profile also shows report records already present in your local report archive, both reports against the player and reports submitted by them. It does not invent historical reports that were never stored.

## UPDATE #2 FULL PLAYER DETAILS

BOINGUS Admin Panel - Full Player Information Update

This update replaces files inside your existing BOINGUS_Admin_Panel folder.
It does NOT replace your .env file or your data/boingus_admin.db database.

Files included:
- app/main.py
- app/playfab.py
- app/static/app.js
- app/static/index.html
- app/static/style.css

Install:
1. Stop the running admin panel window with Ctrl+C.
2. Extract this ZIP.
3. Open the extracted app folder.
4. Copy the app folder into your existing BOINGUS_Admin_Panel folder.
5. Choose Replace files when Windows asks.
6. Run run.bat again and open http://127.0.0.1:9271/.

What changed:
- Selecting a player opens a dedicated full-information view.
- Back button returns to player search.
- Shows account created, first login, last login, account origin, and ban status/history.
- Reads the player's legacy PlayFab virtual currency balance for currency code SS (Springy Springs).
- Shows reports against the player and reports submitted by the player.
- Adds local admin notes stored only in this computer's SQLite database. These notes are not sent to PlayFab.
- Keeps the Owners, Staff, Moderator, and Trial Moderator report filters; these filter by reporter rank.

Notes:
- The SS balance is read using PlayFab Admin/GetUserInventory. It is read-only in this update.
- First login/origin may display Unavailable if PlayFab has not returned those fields for that account.
- The priority-member report pages only show reports that have already synced into the local report archive.
- Keep your existing .env and data folder. Do not delete them.
