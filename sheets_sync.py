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
BRIGADE_TO_TABS: dict[str, list[str]] = {
    "BRIGADE KELLERMANN": ["26e"],
    "BRIGADE LASALLE":    ["5e", "7e"],
    "BRIGADE BESSIÈRES":  ["GaC"],
}

# Rank display name → internal short label used in the sheet
RANK_LABELS = {
    "Maréchal de la Cavalerie":         "Maréchal de la Cavalerie",
    "Lieutenant":                        "Lieutenant",
    "Sous-Lieutenant":                   "Sous-Lieutenant",
    "Lieutenant en Premier":             "Lieutenant en Premier",
    "Adjudant-Sous":                     "Adjudant-Sous",
    "Maréchal des Logis-Chef":           "Maréchal des Logis-Chef",
    "Maréchal des Logis":                "Maréchal des Logis",
    "Brigadier":                         "Brigadier",
    "Maréchal des Logis (MAA)":          "Adjudant-Sous (MAA)",
    "Cavalier":                          "Cavalier",
    "Caporal":                           "Caporal",
    "Caporal Fourrier":                  "Caporal Fourrier",
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

# The induction target regiment — /induct always lands here regardless of history.
INDUCT_REGIMENT_FULL = "26e Chasseurs a Cheval de Ligne"
INDUCT_TAB           = REGIMENT_TO_TAB[INDUCT_REGIMENT_FULL]  # "26e"
INDUCT_RANK_LABEL    = "Cavalier"

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
    col_values = ws.col_values(COL_DISCORD_ID + 1)  # gspread is 1-indexed
    for row_1idx, cell_val in enumerate(col_values, start=1):
        if str(cell_val).strip() == discord_id_str and row_1idx >= FIRST_RANKER_ROW_1IDX:
            return row_1idx
    return None


def _find_member_in_stats(discord_id: str) -> Optional[tuple[int, str, str]]:
    """
    Search the Stats tab for a Discord ID.
    Returns (row_1idx, regiment_name, roblox_username) or None.

    Returns the LAST match so that re-inducted members (who may have a stale
    old entry earlier in the map) always resolve to their most recent entry.
    """
    ws = _worksheet("Stats")
    col_values = ws.col_values(STATS_COL_DISCORD_ID + 1)
    discord_id_str = str(discord_id)
    last_match: Optional[tuple[int, str, str]] = None
    for row_1idx, cell_val in enumerate(col_values, start=1):
        if str(cell_val).strip() == discord_id_str:
            row_data = ws.row_values(row_1idx)
            regiment = row_data[STATS_COL_REGIMENT] if len(row_data) > STATS_COL_REGIMENT else ""
            username = row_data[STATS_COL_USERNAME]  if len(row_data) > STATS_COL_USERNAME  else ""
            last_match = (row_1idx, regiment, username)
    return last_match


def _today_str() -> str:
    """Return today's date as MM/DD/YYYY — matches _days_since's strptime format."""
    return datetime.now(timezone.utc).strftime("%m/%d/%Y")


def _days_since(drafted_str: str) -> str:
    """Calculate days since a date string in MM/DD/YYYY format."""
    try:
        drafted = datetime.strptime(drafted_str, "%m/%d/%Y").date()
        delta = (datetime.now(timezone.utc).date() - drafted).days
        return f"{delta} days"
    except Exception:
        return "0 days"


def _col_letter(col_1idx: int) -> str:
    """Convert 1-indexed column number to A1-style letter(s). e.g. 1→A, 27→AA"""
    result = ""
    while col_1idx > 0:
        col_1idx, remainder = divmod(col_1idx - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _find_last_data_row(ws: gspread.Worksheet) -> int:
    """
    Return the 1-indexed row of the last member row in a regiment tab,
    or FIRST_RANKER_ROW_1IDX - 1 if the tab has no data rows yet.
    """
    all_values = ws.get_all_values()
    last = FIRST_RANKER_ROW_1IDX - 1
    for i, row in enumerate(all_values):
        row_1idx = i + 1
        if row_1idx >= FIRST_RANKER_ROW_1IDX and len(row) > COL_DISCORD_ID and str(row[COL_DISCORD_ID]).strip():
            last = row_1idx
    return last


def _insert_row_with_formulas(
    ws: gspread.Worksheet,
    new_row_1idx: int,
    rank_label: str,
    timezone_str: str,
    drafted_date: str,
    discord_id: str,
    roblox_username: str,
) -> None:
    """
    Insert a new member row at new_row_1idx, copying all cell formulas from the
    row directly above it (new_row_1idx - 1) so that formula-driven columns
    (Days Since, KPE, Activity %, rally attendance, etc.) auto-calculate
    correctly for the new row rather than receiving hard-coded static values.

    Strategy
    --------
    1. Read the raw (formula) content of the template row via the Sheets v4
       `spreadsheets.values.get` call with `valueRenderOption=FORMULA`.
    2. Use gspread's `insert_rows` to push a blank row at the target position,
       which shifts every row below it down by one (preserving existing data).
    3. Write the merged row data back: copied formulas for "computed" columns,
       actual values for the identity columns (rank, timezone, date, Discord ID,
       Roblox username).  We always write with `value_input_option=USER_ENTERED`
       so that formula strings starting with `=` are interpreted as formulas.

    The "identity" columns we always overwrite with real values are:
        COL_RANK, COL_TIMEZONE, COL_DRAFTED, COL_DISCORD_ID, COL_USERNAME
    Every other column gets its formula from the template row, with the
    template row's own row number replaced by new_row_1idx so relative
    references stay correct.
    """
    spreadsheet = _get_spreadsheet()
    sheet_id = ws.id

    template_row_1idx = new_row_1idx - 1

    # ── Step 1: read template row formulas via raw Sheets API ─────────────────
    # gspread's .row_values() returns displayed values; we need raw formulas.
    # Access the underlying google-auth credentials from the gspread client.
    import googleapiclient.discovery  # type: ignore

    creds = _get_client().auth_credentials  # google.oauth2.service_account.Credentials
    service = googleapiclient.discovery.build("sheets", "v4", credentials=creds, cache_discovery=False)

    tab_title = ws.title
    range_notation = f"'{tab_title}'!{template_row_1idx}:{template_row_1idx}"

    result = (
        service.spreadsheets()
        .values()
        .get(
            spreadsheetId=SPREADSHEET_ID,
            range=range_notation,
            valueRenderOption="FORMULA",
        )
        .execute()
    )
    template_values = result.get("values", [[]])[0] if result.get("values") else []

    # ── Step 2: insert a blank row at new_row_1idx (shifts everything below) ──
    ws.insert_rows([[]], row=new_row_1idx)

    # ── Step 3: build the merged row ──────────────────────────────────────────
    # Extend template to cover at least up to COL_ACTIVITY so we always have
    # enough cells; gaps are filled with "".
    row_width = max(len(template_values), COL_ACTIVITY + 1)
    new_row_data = list(template_values) + [""] * (row_width - len(template_values))

    # For formula cells that reference a specific row number, replace the
    # template row number with the new row number so relative refs stay correct.
    template_row_str = str(template_row_1idx)
    new_row_str      = str(new_row_1idx)
    updated_row = []
    for cell in new_row_data:
        if isinstance(cell, str) and cell.startswith("=") and template_row_str in cell:
            cell = cell.replace(template_row_str, new_row_str)
        updated_row.append(cell)

    # Overwrite the identity columns with the real inductee values.
    # We always reset these regardless of what the template contained.
    updated_row[COL_RANK]       = rank_label
    updated_row[COL_TIMEZONE]   = timezone_str
    updated_row[COL_DRAFTED]    = drafted_date
    updated_row[COL_DAYS_SINCE] = f"=DATEDIF(H{new_row_1idx},TODAY(),\"D\")&\" days\""
    updated_row[COL_DISCORD_ID] = discord_id
    updated_row[COL_USERNAME]   = roblox_username

    # ── Step 4: write the merged row back ─────────────────────────────────────
    start_col = _col_letter(1)
    end_col   = _col_letter(row_width)
    cell_range = f"'{tab_title}'!{start_col}{new_row_1idx}:{end_col}{new_row_1idx}"

    (
        service.spreadsheets()
        .values()
        .update(
            spreadsheetId=SPREADSHEET_ID,
            range=cell_range,
            valueInputOption="USER_ENTERED",
            body={"values": [updated_row]},
        )
        .execute()
    )

    log.info(
        f"[sheets_sync] insert_row_with_formulas: wrote row {new_row_1idx} "
        f"in {tab_title!r} (template from row {template_row_1idx})"
    )


# ── Public API — all sync (called from async via run_in_executor) ──────────────

def sync_induct(
    discord_id: str,
    roblox_username: str,
    regiment_full_name: str,  # kept for API compatibility, always forced to 26e
    rank_label: str,           # kept for API compatibility, always forced to Cavalier
    timezone_str: str = "",
) -> str:
    """
    Induct (or re-induct) a member.

    * Always targets the 26e tab and always sets rank to Cavalier — regardless
      of what regiment_full_name / rank_label are passed in and regardless of
      where the member currently sits on the spreadsheet.
    * If the member already exists anywhere on the sheet their row is deleted
      and a fresh row is appended to the 26e tab (rank reset to Cavalier).
    * New rows copy cell formulas from the row above so that formula-driven
      columns (Days Since, KPE, Activity %, rally columns, etc.) work correctly.
    """
    discord_id_str = str(discord_id)

    # Always 26e / Cavalier — ignore whatever the caller passed
    target_tab_name    = INDUCT_TAB          # "26e"
    effective_rank     = INDUCT_RANK_LABEL   # "Cavalier"
    effective_regiment = INDUCT_REGIMENT_FULL

    today = _today_str()

    # 1. Scan ALL regiment tabs for any existing record of this user
    existing_locations: list[tuple[str, gspread.Worksheet, list[int]]] = []
    for t_name in REGIMENT_TO_TAB.values():
        try:
            ws = _worksheet(t_name)
            col_vals = ws.col_values(COL_DISCORD_ID + 1)
            rows = [
                i + 1 for i, cell in enumerate(col_vals)
                if str(cell).strip() == discord_id_str and i + 1 >= FIRST_RANKER_ROW_1IDX
            ]
            if rows:
                existing_locations.append((t_name, ws, rows))
        except Exception as e:
            log.error(f"[sheets_sync] Error reading tab {t_name} for duplicates: {e}")

    stats_ws = _worksheet("Stats")
    stats_col_values = stats_ws.col_values(STATS_COL_DISCORD_ID + 1)
    stats_rows = [
        idx + 1 for idx, cell in enumerate(stats_col_values)
        if str(cell).strip() == discord_id_str
    ]

    rows_deleted = 0

    # ── Delete ALL existing rows across all tabs (re-induction always starts fresh) ──
    if existing_locations:
        for t_name, ws, rows in existing_locations:
            for r in reversed(rows):
                ws.delete_rows(r)
                rows_deleted += 1
        log.info(
            f"[sheets_sync] Re-induction: cleared {rows_deleted} existing row(s) "
            f"for {roblox_username} across all tabs"
        )

    # ── Append a brand-new row to the 26e tab ─────────────────────────────────
    target_ws    = _worksheet(target_tab_name)
    last_row     = _find_last_data_row(target_ws)
    new_row_1idx = last_row + 1

    if last_row >= FIRST_RANKER_ROW_1IDX:
        # There is at least one existing data row — copy formulas from it.
        _insert_row_with_formulas(
            ws            = target_ws,
            new_row_1idx  = new_row_1idx,
            rank_label    = effective_rank,
            timezone_str  = timezone_str,
            drafted_date  = today,
            discord_id    = discord_id_str,
            roblox_username = roblox_username,
        )
    else:
        # Tab is empty — no template row exists yet; fall back to static values.
        row_width = COL_ACTIVITY + 1
        new_row = [""] * row_width
        new_row[COL_RANK]       = effective_rank
        new_row[COL_TIMEZONE]   = timezone_str
        new_row[COL_DRAFTED]    = today
        new_row[COL_DAYS_SINCE] = f"=DATEDIF(H{new_row_1idx},TODAY(),\"D\")&\" days\""
        new_row[COL_DISCORD_ID] = discord_id_str
        new_row[COL_USERNAME]   = roblox_username
        target_ws.insert_rows([new_row], row=new_row_1idx, value_input_option="USER_ENTERED")

    # ── Update Stats map ───────────────────────────────────────────────────────
    if stats_rows:
        stats_keep = stats_rows[-1]
        # Blank out any duplicates
        for r in reversed(stats_rows[:-1]):
            stats_ws.update(f"AO{r}:AQ{r}", [["", "", ""]], value_input_option="USER_ENTERED")
        stats_ws.update(
            f"AO{stats_keep}:AQ{stats_keep}",
            [[discord_id_str, effective_regiment, roblox_username]],
            value_input_option="USER_ENTERED",
        )
    else:
        # No Stats entry yet — find the next free row and create one
        stats_all = stats_ws.get_all_values()
        last_stats_row = max(
            (i + 1 for i, row in enumerate(stats_all)
             if len(row) > STATS_COL_DISCORD_ID and str(row[STATS_COL_DISCORD_ID]).strip()),
            default=0,
        )
        stats_ws.update(
            f"AO{last_stats_row + 1}:AQ{last_stats_row + 1}",
            [[discord_id_str, effective_regiment, roblox_username]],
            value_input_option="USER_ENTERED",
        )

    log.info(
        f"[sheets_sync] Inducted {roblox_username} → {target_tab_name} row {new_row_1idx} "
        f"rank={effective_rank!r}  (cleared {rows_deleted} old row(s))"
    )

    if rows_deleted:
        return f"Re-inducted → **{target_tab_name}** at Cavalier (cleared {rows_deleted} old row(s))."
    return f"Added new roster row to **{target_tab_name}**."


def sync_promote(
    discord_id: str,
    new_rank_label: str,
    roblox_username=None,
) -> bool:
    """
    Update the Rank/Position cell for a member in their current regiment tab.
    Looks them up by Discord ID in the Stats map first to find the right tab.
    Falls back to a full scan if the Stats map is stale.

    Returns True on success, False if member not found anywhere.
    """
    stats_result = _find_member_in_stats(discord_id)

    # ── Try Stats-map-indicated tab first ─────────────────────────────────────
    if stats_result:
        _, regiment_full_name, sheet_username = stats_result
        tab_name = REGIMENT_TO_TAB.get(regiment_full_name)
        if tab_name:
            ws = _worksheet(tab_name)
            member_row = _find_member_row_in_tab(ws, discord_id)
            if member_row is not None:
                rank_col_letter = _col_letter(COL_RANK + 1)
                ws.update(f"{rank_col_letter}{member_row}", [[new_rank_label]], value_input_option="USER_ENTERED")
                log.info(
                    f"[sheets_sync] Promoted discord_id={discord_id} ({sheet_username}) "
                    f"in {tab_name} row {member_row} to {new_rank_label!r}"
                )
                return True
            else:
                log.warning(
                    f"[sheets_sync] promote: {discord_id} not found in Stats-indicated tab "
                    f"{tab_name!r} — falling back to full tab scan"
                )
        else:
            log.warning(f"[sheets_sync] promote: unknown regiment {regiment_full_name!r} for {discord_id} — scanning all tabs")
    else:
        log.warning(f"[sheets_sync] promote: discord_id {discord_id} not found in Stats map — scanning all tabs")

    # ── Fallback: scan every known regiment tab ────────────────────────────────
    for tab_name in REGIMENT_TO_TAB.values():
        try:
            ws = _worksheet(tab_name)
        except Exception:
            continue
        member_row = _find_member_row_in_tab(ws, discord_id)
        if member_row is not None:
            rank_col_letter = _col_letter(COL_RANK + 1)
            ws.update(f"{rank_col_letter}{member_row}", [[new_rank_label]], value_input_option="USER_ENTERED")
            log.info(
                f"[sheets_sync] Promoted discord_id={discord_id} in {tab_name} row {member_row} "
                f"to {new_rank_label!r} (found via fallback scan)"
            )
            _repair_stats_entry(discord_id, tab_name, roblox_username)
            return True

    log.warning(f"[sheets_sync] promote: {discord_id} not found in any regiment tab")
    return False


def _repair_stats_entry(discord_id: str, correct_tab: str, roblox_username: Optional[str]) -> None:
    """
    Update (or create) the Stats map entry so it points to `correct_tab`.
    Clears any duplicate entries.
    """
    correct_regiment = TAB_TO_REGIMENT.get(correct_tab, correct_tab)
    stats_ws = _worksheet("Stats")
    col_values = stats_ws.col_values(STATS_COL_DISCORD_ID + 1)
    discord_id_str = str(discord_id)

    existing_rows = [
        idx + 1 for idx, cell in enumerate(col_values)
        if str(cell).strip() == discord_id_str
    ]

    if existing_rows:
        for i, row_1idx in enumerate(existing_rows):
            if i == 0:
                row_data = stats_ws.row_values(row_1idx)
                username = roblox_username or (row_data[STATS_COL_USERNAME] if len(row_data) > STATS_COL_USERNAME else "")
                stats_ws.update(
                    f"AO{row_1idx}:AQ{row_1idx}",
                    [[discord_id_str, correct_regiment, username]],
                    value_input_option="USER_ENTERED",
                )
                log.info(f"[sheets_sync] Repaired Stats map row {row_1idx}: regiment → {correct_regiment!r}")
            else:
                stats_ws.update(f"AO{row_1idx}:AQ{row_1idx}", [["", "", ""]], value_input_option="USER_ENTERED")
                log.warning(f"[sheets_sync] Cleared duplicate Stats map entry at row {row_1idx} for {discord_id}")
    else:
        stats_all = stats_ws.get_all_values()
        last_stats_row = max(
            (i + 1 for i, row in enumerate(stats_all)
             if len(row) > STATS_COL_DISCORD_ID and str(row[STATS_COL_DISCORD_ID]).strip()),
            default=0,
        )
        new_row = last_stats_row + 1
        stats_ws.update(
            f"AO{new_row}:AQ{new_row}",
            [[discord_id_str, correct_regiment, roblox_username or ""]],
            value_input_option="USER_ENTERED",
        )
        log.info(f"[sheets_sync] Created Stats map entry at row {new_row} for {discord_id} → {correct_regiment!r}")


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
      3. Insert a fresh Cavalier row in the target regiment tab,
         copying formulas from the row above so computed columns work correctly.
         The member's original drafted date is preserved.

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
        last_stats_row = max(
            (i + 1 for i, row in enumerate(stats_all)
             if len(row) > STATS_COL_DISCORD_ID and str(row[STATS_COL_DISCORD_ID]).strip()),
            default=0,
        )
        stats_ws.update(
            f"AO{last_stats_row + 1}:AQ{last_stats_row + 1}",
            [[discord_id, new_regiment_full_name, roblox_username]],
            value_input_option="USER_ENTERED",
        )

    # ── Insert new Cavalier row in target regiment tab ─────────────────────────
    target_ws    = _worksheet(target_tab)
    last_row     = _find_last_data_row(target_ws)
    new_row_1idx = last_row + 1

    if last_row >= FIRST_RANKER_ROW_1IDX:
        _insert_row_with_formulas(
            ws              = target_ws,
            new_row_1idx    = new_row_1idx,
            rank_label      = "Cavalier",
            timezone_str    = "",
            drafted_date    = old_drafted_date,
            discord_id      = discord_id,
            roblox_username = roblox_username,
        )
    else:
        row_width = COL_ACTIVITY + 1
        new_row = [""] * row_width
        new_row[COL_RANK]       = "Cavalier"
        new_row[COL_TIMEZONE]   = ""
        new_row[COL_DRAFTED]    = old_drafted_date
        new_row[COL_DAYS_SINCE] = f"=DATEDIF(H{new_row_1idx},TODAY(),\"D\")&\" days\""
        new_row[COL_DISCORD_ID] = discord_id
        new_row[COL_USERNAME]   = roblox_username
        target_ws.insert_rows([new_row], row=new_row_1idx, value_input_option="USER_ENTERED")

    log.info(
        f"[sheets_sync] draft_transfer: inserted {roblox_username} ({discord_id}) "
        f"into {target_tab} at row {new_row_1idx} with rank=Cavalier"
    )
    return True


def sync_purge(
    discord_id: str,
    roblox_username: str,
    roblox_id: str,
    display_name: str,
    purged: bool,
) -> bool:
    """
    Remove a member from their regiment tab and Stats map.
    If purged=True, also appends to the Purged tab.

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
    stats_ws.update(
        f"AO{stats_row_1idx}:AQ{stats_row_1idx}",
        [["", "", ""]],
        value_input_option="USER_ENTERED",
    )
    log.info(f"[sheets_sync] Cleared Stats map entry at row {stats_row_1idx}")

    # ── 4. Append to Purged tab to log purged users ──────────────────────────
    if purged:
        bl_ws = _worksheet("Purged")
        timestamp = datetime.now(timezone.utc).isoformat()
        bl_ws.append_row(
            [roblox_username, roblox_id, discord_id, display_name, timestamp],
            value_input_option="USER_ENTERED",
            insert_data_option="INSERT_ROWS",
            table_range="A1",
        )
        log.info(f"[sheets_sync] Appended {roblox_username} to the Purged tab")

    return True


# ── Async wrappers (call these from discord.py commands) ───────────────────────

async def async_sync_induct(
    discord_id: str,
    roblox_username: str,
    regiment_full_name: str,
    rank_label: str,
    timezone_str: str = "",
) -> str:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
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