"""
sheets_sync.py — CAV Spreadsheet sync for Bolt 2.0
Handles /induct, /promote, /purge roster sync against the master workbook.

Sheet structure (all regiment tabs: GaC, 5e, 7e, 26e, CaC):
  - Data rows start at 1-indexed row 24 (FIRST_RANKER_ROW), i.e. 0-indexed row 23.
  - Col layout (0-indexed):
      5  = Rank/Position
      6  = Timezone
      7  = Drafted date (MM/DD/YYYY)
      8  = Days Since
      9  = Discord ID
      10 = Name (Roblox username)
      11 = K (kills)
      12 = KPE
      13 = Activity %
      14+= Rally attendance columns

Stats tab member map (far-right columns, 0-indexed):
      40 = Discord ID
      41 = Regiment (full name, e.g. "7e Curiassiers")
      42 = Roblox username

Blacklisted tab cols (0-indexed):
      0 = roblox_username
      1 = roblox_id
      2 = discord_id
      3 = display_name
      4 = timestamp
"""

import os
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

import gspread
from google.oauth2.service_account import Credentials

log = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────

SPREADSHEET_ID = os.getenv("CAV_SPREADSHEET_ID", "1pPs_Kmcfzz2yu5JUrqCGdrEpVdmXMOLMwHfGGdmGxwY")
SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "credentials.json")

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]

# Maps regiment full name → sheet tab name
REGIMENT_TO_TAB = {
    "Grenadiers-à-Cheval":              "GaC",
    "5e Chevaux Legers Lanciers":        "5e",
    "7e Curiassiers":                    "7e",
    "26e Chasseurs a Cheval de Ligne":   "26e",
    "Chasseurs-à-Cheval":                "CaC",
}

# Inverse map: tab name → full regiment name
TAB_TO_REGIMENT = {v: k for k, v in REGIMENT_TO_TAB.items()}

# Maps brigade name (Roblox rank) → list of regiment tab names a draftee may go to.
# Used by sync_promote_draft to move a member between regiment tabs.
BRIGADE_TO_TABS: dict[str, list[str]] = {
    "BRIGADE KELLERMANN": ["26e"],
    "BRIGADE LASALLE":    ["5e"],
    "BRIGADE BESSIÈRES":  ["GaC", "CaC"],
}

# Rank display name → internal short label used in the sheet
# (sheets use these verbatim; keep in sync with your Roblox group ranks)
RANK_LABELS = {
    # Officer ranks
    "Maréchal de la Cavalerie":         "Maréchal de la Cavalerie",
    "Lieutenant":                        "Lieutenant",
    "Sous-Lieutenant":                   "Sous-Lieutenant",
    "Lieutenant en Premier":             "Lieutenant en Premier",
    # NCO ranks
    "Adjudant-Sous":                     "Adjudant-Sous",
    "Maréchal des Logis-Chef":           "Maréchal des Logis-Chef",
    "Maréchal des Logis":                "Maréchal des Logis",
    "Brigadier":                         "Brigadier",
    "Maréchal des Logis (MAA)":          "Adjudant-Sous (MAA)",
    # Enlisted ranks
    "Cavalier":                          "Cavalier",
    "Caporal":                           "Caporal",
    "Caporal Fourrier":                  "Caporal Fourrier",
    # Trumpeters (special)
    "Trompettiste":                      "Trompettiste",
}

# Column indices (0-based) within a regiment tab
COL_RANK       = 5
COL_TIMEZONE   = 6
COL_DRAFTED    = 7
COL_DAYS_SINCE = 8
COL_DISCORD_ID = 9
COL_USERNAME   = 10
COL_KILLS      = 11
COL_KPE        = 12
COL_ACTIVITY   = 13

FIRST_RANKER_ROW_1IDX = 24   # 1-indexed row where member data begins

# Stats tab map columns (0-based)
STATS_COL_DISCORD_ID = 40
STATS_COL_REGIMENT   = 41
STATS_COL_USERNAME   = 42

# ── Client singleton ───────────────────────────────────────────────────────────

_gc: Optional[gspread.Client] = None
_spreadsheet: Optional[gspread.Spreadsheet] = None


def _get_client() -> gspread.Client:
    global _gc
    if _gc is None:
        creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
        _gc = gspread.authorize(creds)
    return _gc


def _get_spreadsheet() -> gspread.Spreadsheet:
    global _spreadsheet
    if _spreadsheet is None:
        _spreadsheet = _get_client().open_by_key(SPREADSHEET_ID)
    return _spreadsheet


def _worksheet(tab_name: str) -> gspread.Worksheet:
    return _get_spreadsheet().worksheet(tab_name)


# ── Internal helpers ───────────────────────────────────────────────────────────

def _find_member_row_in_tab(ws: gspread.Worksheet, discord_id: str) -> Optional[int]:
    """
    Return the 1-indexed row number of the member in this regiment tab,
    or None if not found. Searches the Discord ID column (COL_DISCORD_ID).
    """
    discord_id_str = str(discord_id)
    # Fetch the entire Discord ID column (col index 8 → gspread col 9 in 1-indexed)
    col_values = ws.col_values(COL_DISCORD_ID + 1)  # gspread is 1-indexed
    for row_1idx, cell_val in enumerate(col_values, start=1):
        if str(cell_val).strip() == discord_id_str and row_1idx >= FIRST_RANKER_ROW_1IDX:
            return row_1idx
    return None


def _find_member_in_stats(discord_id: str) -> Optional[tuple[int, str, str]]:
    """
    Search the Stats tab for a Discord ID.
    Returns (row_1idx, regiment_name, roblox_username) or None.
    """
    ws = _worksheet("Stats")
    col_values = ws.col_values(STATS_COL_DISCORD_ID + 1)  # 1-indexed gspread col
    discord_id_str = str(discord_id)
    for row_1idx, cell_val in enumerate(col_values, start=1):
        if str(cell_val).strip() == discord_id_str:
            row_data = ws.row_values(row_1idx)
            regiment = row_data[STATS_COL_REGIMENT] if len(row_data) > STATS_COL_REGIMENT else ""
            username = row_data[STATS_COL_USERNAME]  if len(row_data) > STATS_COL_USERNAME  else ""
            return (row_1idx, regiment, username)
    return None


def _today_str() -> str:
    """Return today's date as MM/DD/YYYY (zero-padded) — matches _days_since's strptime format."""
    return datetime.now(timezone.utc).strftime("%m/%d/%Y")   # e.g. "06/07/2026"


def _days_since(drafted_str: str) -> str:
    """Calculate days since a date string in MM/DD/YYYY format (zero-padded)."""
    try:
        drafted = datetime.strptime(drafted_str, "%m/%d/%Y").date()
        delta = (datetime.now(timezone.utc).date() - drafted).days
        return f"{delta} days"
    except Exception:
        return "0 days"


# ── Public API — all sync (called from async via run_in_executor) ──────────────

def sync_induct(
    discord_id: str,
    roblox_username: str,
    regiment_full_name: str,
    rank_label: str,
    timezone_str: str = "",
) -> None:
    """
    Add a new member to the correct regiment tab and Stats map.
    Called after /induct successfully completes Roblox group join.

    Args:
        discord_id:          Discord user ID (as string)
        roblox_username:     Roblox display name / username
        regiment_full_name:  e.g. "7e Curiassiers"
        rank_label:          Rank string as it should appear in the sheet
        timezone_str:        Optional timezone string (e.g. "EST")
    """
    tab_name = REGIMENT_TO_TAB.get(regiment_full_name)
    if not tab_name:
        raise ValueError(f"Unknown regiment: {regiment_full_name!r}")

    today = _today_str()
    days = _days_since(today)

    # ── 1. Append row to regiment tab ─────────────────────────────────────────
    ws = _worksheet(tab_name)

    # Build a sparse row: we need to place values at the right columns.
    # Simplest approach: read a full existing data row to get the width,
    # then build a list of the same width with our values slotted in.
    all_values = ws.get_all_values()
    # Find the last occupied data row to append after it
    last_data_row_1idx = FIRST_RANKER_ROW_1IDX - 1
    for i, row in enumerate(all_values):
        row_1idx = i + 1
        if row_1idx < FIRST_RANKER_ROW_1IDX:
            continue
        # A row is "occupied" if the Discord ID cell is non-empty
        if len(row) > COL_DISCORD_ID and str(row[COL_DISCORD_ID]).strip():
            last_data_row_1idx = row_1idx

    new_row_1idx = last_data_row_1idx + 1

    # Determine total column width from existing rows (use header row width)
    header_row = all_values[FIRST_RANKER_ROW_1IDX - 2] if len(all_values) >= FIRST_RANKER_ROW_1IDX else []
    row_width = max(COL_ACTIVITY + 1, len(header_row))

    new_row = [""] * row_width
    new_row[COL_RANK]       = rank_label
    new_row[COL_TIMEZONE]   = timezone_str
    new_row[COL_DRAFTED]    = today
    new_row[COL_DAYS_SINCE] = days
    new_row[COL_DISCORD_ID] = discord_id
    new_row[COL_USERNAME]   = roblox_username
    new_row[COL_KILLS]      = "0"
    new_row[COL_KPE]        = "0.0"
    new_row[COL_ACTIVITY]   = "0%"

    ws.insert_row(new_row, new_row_1idx, value_input_option="USER_ENTERED")

    log.info(f"[sheets_sync] Inducted {roblox_username} ({discord_id}) into {tab_name} at row {new_row_1idx}")

    # ── 2. Append to Stats tab member map ────────────────────────────────────
    stats_ws = _worksheet("Stats")
    stats_all = stats_ws.get_all_values()

    # Find the last occupied row in the stats map (STATS_COL_DISCORD_ID column)
    last_stats_row = 0
    for i, row in enumerate(stats_all):
        if len(row) > STATS_COL_DISCORD_ID and str(row[STATS_COL_DISCORD_ID]).strip():
            last_stats_row = i + 1  # 1-indexed

    new_stats_row_1idx = last_stats_row + 1
    # We write directly to the three stats map cells (the rest of the row stays blank)
    stats_ws.update(
        f"AO{new_stats_row_1idx}:AQ{new_stats_row_1idx}",   # AO=col41, AP=col42, AQ=col43 (1-indexed)
        [[discord_id, regiment_full_name, roblox_username]],
        value_input_option="USER_ENTERED",
    )

    log.info(f"[sheets_sync] Added {roblox_username} to Stats map at row {new_stats_row_1idx}")


def sync_promote(
    discord_id: str,
    new_rank_label: str,
    roblox_username=None,
) -> bool:
    """
    Update the Rank/Position cell for a member in their current regiment tab.
    Looks them up by Discord ID in the Stats map first to find the right tab.

    Returns True on success, False if member not found.
    """
    stats_result = _find_member_in_stats(discord_id)
    if not stats_result:
        log.warning(f"[sheets_sync] promote: discord_id {discord_id} not found in Stats map")
        return False

    _, regiment_full_name, sheet_username = stats_result
    tab_name = REGIMENT_TO_TAB.get(regiment_full_name)
    if not tab_name:
        log.warning(f"[sheets_sync] promote: unknown regiment {regiment_full_name!r} for {discord_id}")
        return False

    ws = _worksheet(tab_name)
    member_row = _find_member_row_in_tab(ws, discord_id)
    if member_row is None:
        log.warning(f"[sheets_sync] promote: {discord_id} not found in tab {tab_name}")
        return False

    rank_col_letter = _col_letter(COL_RANK + 1)
    cell_ref = f"{rank_col_letter}{member_row}"
    ws.update(cell_ref, [[new_rank_label]], value_input_option="USER_ENTERED")

    log.info(
        f"[sheets_sync] Promoted discord_id={discord_id} ({sheet_username}) "
        f"in {tab_name} row {member_row} to {new_rank_label!r}"
    )
    return True


def sync_promote_draft(
    discord_id: str,
    roblox_username: str,
    target_brigade: str,
    target_tab: str,
) -> bool:
    """
    Handle a draft/brigade transfer in the spreadsheet:
      1. Delete the member's old row in their current regiment tab.
      2. Update their Stats map entry with the new regiment.
      3. Insert a fresh Draftee row in the target regiment tab,
         preserving the member's original drafted date if available.

    Returns True on success.
    """
    old_drafted_date = _today_str()

    stats_result = _find_member_in_stats(discord_id)
    if stats_result:
        stats_row_1idx, old_regiment_full_name, sheet_username = stats_result
        old_tab = REGIMENT_TO_TAB.get(old_regiment_full_name)

        if old_tab:
            old_ws = _worksheet(old_tab)
            old_member_row = _find_member_row_in_tab(old_ws, discord_id)
            if old_member_row is not None:
                old_row_data = old_ws.row_values(old_member_row)
                if len(old_row_data) > COL_DRAFTED and old_row_data[COL_DRAFTED].strip():
                    old_drafted_date = old_row_data[COL_DRAFTED].strip()
                old_ws.delete_rows(old_member_row)
                log.info(f"[sheets_sync] draft_transfer: deleted {discord_id} from {old_tab} row {old_member_row}")
            else:
                log.warning(f"[sheets_sync] draft_transfer: {discord_id} not found in old tab {old_tab}")
        else:
            log.warning(f"[sheets_sync] draft_transfer: unknown old regiment {old_regiment_full_name!r}")

        new_regiment_full_name = TAB_TO_REGIMENT.get(target_tab, target_brigade)
        stats_ws = _worksheet("Stats")
        stats_ws.update(
            f"AO{stats_row_1idx}:AQ{stats_row_1idx}",
            [[discord_id, new_regiment_full_name, roblox_username]],
            value_input_option="USER_ENTERED",
        )
        log.info(f"[sheets_sync] draft_transfer: Stats map row {stats_row_1idx} updated to regiment={new_regiment_full_name!r}")
    else:
        log.warning(f"[sheets_sync] draft_transfer: {discord_id} not in Stats map; creating new Stats entry")
        new_regiment_full_name = TAB_TO_REGIMENT.get(target_tab, target_brigade)
        stats_ws = _worksheet("Stats")
        stats_all = stats_ws.get_all_values()
        last_stats_row = 0
        for i, row in enumerate(stats_all):
            if len(row) > STATS_COL_DISCORD_ID and str(row[STATS_COL_DISCORD_ID]).strip():
                last_stats_row = i + 1
        new_stats_row = last_stats_row + 1
        stats_ws.update(
            f"AO{new_stats_row}:AQ{new_stats_row}",
            [[discord_id, new_regiment_full_name, roblox_username]],
            value_input_option="USER_ENTERED",
        )

    # Insert new Draftee row in target regiment tab
    target_ws = _worksheet(target_tab)
    all_values = target_ws.get_all_values()

    last_data_row_1idx = FIRST_RANKER_ROW_1IDX - 1
    for i, row in enumerate(all_values):
        row_1idx = i + 1
        if row_1idx < FIRST_RANKER_ROW_1IDX:
            continue
        if len(row) > COL_DISCORD_ID and str(row[COL_DISCORD_ID]).strip():
            last_data_row_1idx = row_1idx

    new_row_1idx = last_data_row_1idx + 1
    header_row = all_values[FIRST_RANKER_ROW_1IDX - 2] if len(all_values) >= FIRST_RANKER_ROW_1IDX else []
    row_width = max(COL_ACTIVITY + 1, len(header_row))

    days = _days_since(old_drafted_date)
    new_row = [""] * row_width
    new_row[COL_RANK]       = "Cavalier"
    new_row[COL_TIMEZONE]   = ""
    new_row[COL_DRAFTED]    = old_drafted_date
    new_row[COL_DAYS_SINCE] = days
    new_row[COL_DISCORD_ID] = discord_id
    new_row[COL_USERNAME]   = roblox_username
    new_row[COL_KILLS]      = "0"
    new_row[COL_KPE]        = "0.0"
    new_row[COL_ACTIVITY]   = "0%"

    target_ws.insert_row(new_row, new_row_1idx, value_input_option="USER_ENTERED")
    log.info(
        f"[sheets_sync] draft_transfer: inserted {roblox_username} ({discord_id}) "
        f"into {target_tab} at row {new_row_1idx} with rank=Draftee"
    )
    return True



def sync_purge(
    discord_id: str,
    roblox_username: str,
    roblox_id: str,
    display_name: str,
    blacklist: bool,
) -> bool:
    """
    Remove a member from their regiment tab and Stats map.
    If blacklist=True, also appends to the Blacklisted tab.

    Returns True if the member was found and removed, False otherwise.
    """
    # ── 1. Find in Stats map ──────────────────────────────────────────────────
    stats_result = _find_member_in_stats(discord_id)
    if not stats_result:
        log.warning(f"[sheets_sync] purge: discord_id {discord_id} not found in Stats map")
        return False

    stats_row_1idx, regiment_full_name, sheet_username = stats_result
    tab_name = REGIMENT_TO_TAB.get(regiment_full_name)

    # ── 2. Remove from regiment tab ───────────────────────────────────────────
    if tab_name:
        ws = _worksheet(tab_name)
        member_row = _find_member_row_in_tab(ws, discord_id)
        if member_row is not None:
            ws.delete_rows(member_row)
            log.info(f"[sheets_sync] Deleted {sheet_username} from {tab_name} row {member_row}")
        else:
            log.warning(f"[sheets_sync] purge: {discord_id} not found in tab {tab_name}")
    else:
        log.warning(f"[sheets_sync] purge: unknown regiment tab for {regiment_full_name!r}")

    # ── 3. Remove from Stats map ──────────────────────────────────────────────
    stats_ws = _worksheet("Stats")
    # Clear the three cells (don't delete the whole row — other cols may have formulas)
    stats_ws.update(
        f"AO{stats_row_1idx}:AQ{stats_row_1idx}",
        [["", "", ""]],
        value_input_option="USER_ENTERED",
    )
    log.info(f"[sheets_sync] Cleared Stats map entry at row {stats_row_1idx}")

    # ── 4. Append to Blacklisted tab (if applicable) ──────────────────────────
    if blacklist:
        bl_ws = _worksheet("Blacklisted")
        timestamp = datetime.now(timezone.utc).isoformat()
        bl_ws.append_row(
            [roblox_username, roblox_id, discord_id, display_name, timestamp],
            value_input_option="USER_ENTERED",
            insert_data_option="INSERT_ROWS",
            table_range="A1",
        )
        log.info(f"[sheets_sync] Appended {roblox_username} to Blacklisted tab")

    return True


# ── Async wrappers (call these from discord.py commands) ───────────────────────

async def async_sync_induct(
    discord_id: str,
    roblox_username: str,
    regiment_full_name: str,
    rank_label: str,
    timezone_str: str = "",
) -> None:
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None,
        sync_induct,
        discord_id, roblox_username, regiment_full_name, rank_label, timezone_str,
    )


async def async_sync_promote(
    discord_id: str,
    new_rank_label: str,
    roblox_username: Optional[str] = None,
) -> bool:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        sync_promote,
        discord_id, new_rank_label, roblox_username,
    )


async def async_sync_purge(
    discord_id: str,
    roblox_username: str,
    roblox_id: str,
    display_name: str,
    blacklist: bool,
) -> bool:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        sync_purge,
        discord_id, roblox_username, roblox_id, display_name, blacklist,
    )


async def async_sync_promote_draft(
    discord_id: str,
    roblox_username: str,
    target_brigade: str,
    target_tab: str,
) -> bool:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        sync_promote_draft,
        discord_id, roblox_username, target_brigade, target_tab,
    )


# ── Utility ────────────────────────────────────────────────────────────────────

def _col_letter(col_1idx: int) -> str:
    """Convert 1-indexed column number to A1-style letter(s). e.g. 1→A, 27→AA"""
    result = ""
    while col_1idx > 0:
        col_1idx, remainder = divmod(col_1idx - 1, 26)
        result = chr(65 + remainder) + result
    return result