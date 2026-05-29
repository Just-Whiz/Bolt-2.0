# ============================================================
#  Bolt 2.0 — Corps de Cavalerie Impériale Discord Bot
#  Author : orbandit (@just_whiz on Discord)
#  Updated: 2026-05-28
#  Version: 0.9.0
# ============================================================

import asyncio
import json
import logging
import os
import re
from datetime import datetime, timezone

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands, tasks
from dotenv import load_dotenv

load_dotenv()

# ============================================================
#  ENVIRONMENT
# ============================================================

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
BLOXLINK_API_KEY = os.getenv("BLOXLINK_API_KEY")
GUILD_ID = os.getenv("GUILD_ID")
ROBLOX_OPEN_CLOUD = os.getenv("ROBLOX_OPEN_CLOUD_KEY")
FRENCH_MAIN_GROUP_ID = os.getenv("FRENCH_GROUP_ID", "5610765")
CAV_GROUP_ID = os.getenv("CAV_GROUP_ID", "195387641")

def _oc_headers() -> dict:
    """Returns fresh Open Cloud auth headers for every request."""
    return {
        "x-api-key":    ROBLOX_OPEN_CLOUD,
        "Content-Type": "application/json",
    }

# Shared HTTP timeout for all aiohttp calls (seconds)
HTTP_TIMEOUT = aiohttp.ClientTimeout(total=12)

# Max concurrent outbound Roblox API calls at once
ROBLOX_SEMAPHORE = asyncio.Semaphore(3)

# ============================================================
#  LOGGING
#  All output goes to bolt.log.  Console prints are kept for
#  quick local debugging but can be removed for production.
# ============================================================

_log_handler = logging.FileHandler("bolt.log", encoding="utf-8", mode="a")
_log_handler.setFormatter(logging.Formatter(
    fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
))

log = logging.getLogger("bolt")
log.setLevel(logging.DEBUG)
log.addHandler(_log_handler)
log.propagate = False

for _lib in ("discord", "discord.http", "discord.gateway"):
    _l = logging.getLogger(_lib)
    _l.setLevel(logging.DEBUG)
    _l.addHandler(_log_handler)
    _l.propagate = False

# ============================================================
#  ROBLOX GROUP ID MAPS
#  Only groups whose ID appears here are shown in /background-check.
#  To add a new faction: drop its ID + display name into the right dict.
# ============================================================

FRENCH_GROUP_IDS: dict[str, str] = {
    "5610765": "Empire Français",
    "6057395": "Garde Impériale",
    "6057318": "Premier Corps",
    "6057327": "Deuxième Corps",
    "6057333": "Troisième Corps",
    "7840844": "Quatrième Corps",
    "9976984": "Cinquième Corps",
    "13206132": "Neuvième Corps",
    "13284835": "État-Major Impériale",
    "195387641": "Corps de Cavalerie Impériale",
    # Naples
    "6764583": "Esercito Napoletano",
    "7135170": "Regno di Napoli",
    "9746123": "Prima Divisione",
    "10514799": "Seconda Divisione",
    "32627531": "Terza Divisione",
    "1112910179": "Quatra Divisione",
    "9067214": "Marina Napoletana",
    "10349483": "Guardia Reale",
    "33741408": "Corpo d'Armata",
    "477750899": "Reggimento d'Artiglieria di Marina",
    # Warsaw / Poland
    "4614276": "Woysko Xięstwa Warszawskiego",
    "394072781": "Sztab Generalny Woyska Polskiego",
    "796097059": "Brygada Gwardii Narodowej",
    "596867575": "Xięstwo Litewskie",
    "9921948": "Pierwsza Dywizya",
    "33709393": "Drugi Dywizja",
    "9921939": "Korpus Kawalerii",
}

COALITION_GROUP_IDS: dict[str, str] = {
    # Austria
    "16702357": "Kaisertum Österreich",
    "17034669": "Grenadier Korps",
    "16965984": "Königliche Ungarn",
    "33606731": "Hof von Österreich",
    "14706502": "Erste Korps",
    "17248191": "Zweite Korps",
    "33437234": "Drittes Korps",
    "33727999": "Viertes Korps",
    "35915613": "Fünftes Korps",
    "856818677": "Fünftes Korps Recruitment",
    "33129015": "Kavallerie Korps",
    "33679754": "Ingenieur Korps",
    "35755856": "Küchenbrigade",
    # Russia
    "7528791": "Imperatorskaya Armiya",
    "10621031": "Imperskoy Gvardii Korpus",
    "34279561": "Grenaderskiy Korpus",
    "34279574": "Severnaya Armiya",
    "32842545": "Yuzhnaya Armiya",
    "8254296": "Zapadnaya Armiya",
    "950745879": "Krymskaya Armiya",
    "35917740": "Vostochnaya Armiya",
    # Britain
    "4000196": "British Army",
    "9686866": "First Division",
    "9686840": "Fifth Brigade",
    "12691944": "Second Division",
    "35746582": "Board of Ordnance (INVICTORS)",
    "32033796": "Braunschweig-Oels-Linien-Bataillon",
    "35746578": "Board of Ordnance (PRINCIPES)",
    "34209218": "Schweizer Adelsgeschlecht",
    "7907149": "Household Brigade",
    "1049512588": "Foot Guards Grenadiers",
    # Prussia
    "35965347": "Preußische Armee",
    "35986490": "Königliches Gardekorps",
    "35986478": "Erstes Armeekorps",
    # Spain
    "11639829": "Ejército de España",
    "223078637": "Ejército Real de Nueva España",
    "32374377": "Ejército de Aragón",
    "34056502": "Ejército de Galicia",
    # Andour
    "5531725": "Andouran Empire",
    "432773563": "Fuirst Keisariks Armcorps",
    "17375317": "Anders Keisariks Armcorps",
    "35333449": "Keisariks Armcorps Grenader",
    "16125179": "Andouran Imperial Guard",
    "8559975": "Kait",
    "8410719": "Order of the Gold Griffin",
    "35504152": "Kurohana",
    "6331920": "Order of the White Tiger",
    # Portugal
    "34011906": "Exército de Portugal",
    "11392538": "Real Armada Portuguesa",
    "34460157": "Brigada Real da Marinha",
    "35181462": "Corpo Real de Cavalaria",
    "35613090": "Guarda Real da Polícia de Lisboa",
    "35001756": "Corte Real Portuguesa",
}

NEUTRAL_GROUP_IDS: dict[str, str] = {
    # USA
    "5826061": "United States Army",
    "10822431": "US Marine Corps",
    "175161616": "General Society of the War of 1812",
    "61813207": "U.S. Artillery Corps",
    "35683824": "U.S. Ranger Regiment",
    "35281366": "United States Cavalry Detachment",
    "17394192": "Brown's First Brigade",
    "33704866": "Ripley's 2nd Brigade",
    # Ottomans
    "32950259": "Devlet-i Aliyye-i Osmâniyye",
    "36056277": "Kapıkulu Ocağı",
    "17018827": "Nizâm-ı Cedîd Ordu",
}

# ============================================================
#  REGIMENT & BRIGADE CONFIGURATION
#
#  BRIGADES - Roblox group rank names for the three brigades, in ascending order. Used by /promote draft.
#  BRIGADE_REGIMENTS - Maps each brigade → its regiment Discord role(s). Add new regiments here when the corps expands.
#  ALL_BRIGADE_ROLES - Set of brigade role names for quick stripping.
#  ALL_REGIMENT_ROLES - Set of regiment role names for quick stripping.
# ============================================================

BRIGADES: list[str] = [
    "BRIGADE KELLERMANN",
    "BRIGADE LASALLE",
    "BRIGADE BESSIÈRES",
]

BRIGADE_REGIMENTS: dict[str, list[str]] = {
    "BRIGADE KELLERMANN": ["26ème Régiment de Chasseurs à Cheval"],
    "BRIGADE LASALLE": ["5ème Chevau-Légers Lanciers", "10ème Régiment de Hussards"],
    "BRIGADE BESSIÈRES": ["Grenadiers à Cheval de la Garde Impériale"],
}

ALL_BRIGADE_ROLES: set[str]  = set(BRIGADES)
ALL_REGIMENT_ROLES: set[str] = {r for regs in BRIGADE_REGIMENTS.values() for r in regs}

# ============================================================
#  RANK CONFIGURATION
#
#  DISCORD_RANKS - Ordered list of Discord rank role names, from lowest -> highest. Index IS the rank level.
#  DISCORD_RANK_INDEX - Fast name -> index lookup (built automatically).
#  ALL_RANK_ROLES - Set of all rank names for quick stripping.
#  DRAFT_RESET_RANK - The rank a member receives when drafted.
#  SENIOR_THRESHOLD - Index of the first rank that requires a senior promoter role to assign (inclusive). Currently: "Marechal des Logis-Chef" (index 6).
#  SENIOR_PROMOTER_ROLES - Discord role names allowed to promote at or above SENIOR_THRESHOLD. Can do more as needed.
# ============================================================

DISCORD_RANKS: list[str] = [
    "Conscrit",                       # 0
    "Veteran",                        # 1
    "Cavalier",                       # 2
    "Brigadier",                      # 3
    "Brigadier-Fourrier",             # 4
    "Marechal des Logis",             # 5
    "Marechal des Logis-Chef",        # 6  <- SENIOR_THRESHOLD
    "Adjudant",                       # 7
    "Adjudant Sous-Officier",         # 8
    "Lieutenant en Second",           # 9
    "Lieutenant en Premier",          # 10
    "Capitaine",                      # 11
    "Chef dÉscadron",                 # 12
    "Major",                          # 13
    "Colonel",                        # 14
    "Adjudant-Commandant",            # 15
    "Adjoint du Corps",               # 16
    "Adjoint du General de Division", # 17
    "Adjoint du General de Brigade",  # 18
    "Adjoint du Marechal",            # 19
    "Adjoint d'État Major",           # 20
    "Commandant de Cavalerie Brigade",# 21
]

DISCORD_RANK_INDEX: dict[str, int] = {name: i for i, name in enumerate(DISCORD_RANKS)}
ALL_RANK_ROLES: set[str] = set(DISCORD_RANKS)

DRAFT_RESET_RANK = "Cavalier"
SENIOR_THRESHOLD = DISCORD_RANKS.index("Marechal des Logis-Chef")

# Roles allowed to promote AT or ABOVE SENIOR_THRESHOLD
SENIOR_PROMOTER_ROLES: set[str] = ({
    "Administration Team"
    "Head of Administration",
    "26ème État-major",
    "7ème État-major",
    "5ème État-major",
    "GaC État-major",
    "Adjudant Sous-Officier",
    "Lieutenant en Second",
    "Lieutenant en Premier",
    "Capitaine",
    "Chef d'Escadron",
    "Major",
    "Colonel",
    "Adjudant-Commandant",
    "Adjoint du Corps",
    "Adjoint du Général de Division",
    "Adjoint du Général de Brigade",
    "Adjoint du Maréchal",
    "Adjoint d'État Major",
    "Commandant de Cavalerie Brigade",
    "Cavalerie État-major",
    "Admin",
    "Adjudant-Commandant",
    "Géneral de Brigade",
    "Général de Division",
    "Maréchal",
    "Maréchal en Major Général",
    "Napoléon",
    "Super Admin"
})

# ============================================================
#  ROBLOX GROUP RANK PROGRESSION
#  Used only for /promote draft (setting the Roblox brigade rank).
#  The numeric rank values come from the group roles API.
# ============================================================

CAV_ROBLOX_RANKS: list[tuple[int, str]] = [
    (243, "BRIGADE KELLERMANN"),
    (244, "BRIGADE LASALLE"),
    (245, "BRIGADE BESSIÈRES"),
    (246, "Sous-Officier"),
    (247, "Adjutant Sous-Officier"),
    (248, "Officier Subalterne"),
    (249, "Officier Supérieur"),
    (250, "Officier à la Suite"),
    (251, "Commandant d'Échelon"),
    (252, "Général"),
    (253, "Maréchal en Major Général"),
    (254, "Napoléon"),
    (255, "Maréchal"),
]

# ============================================================
#  INDUCT/PURGE ROLE LISTS
#  INDUCT_ADD - Discord roles given on /induct.
#  INDUCT_REMOVE - Discord roles stripped on /induct.
#  PURGE_ROLES - Everything stripped on /purge (includes all brigade, regiment, and rank roles automatically).
# ============================================================

INDUCT_ADD: list[str] = [
    "BRIGADE KELLERMANN",
    "26ème Régiment de Chasseurs à Cheval",
    "Corps de Cavalerie Impériale",
    "Cavalier",
]

INDUCT_REMOVE: list[str] = [
    "Garde Nationale de Cavalerie",
    "Guest",
    "Citoyen",
    "Soldat",
    "Caporal",
    "Caporal Fourrier",
]

CAV_INDUCT_ROBLOX_RANK = "BRIGADE KELLERMANN"

# Purge strips all brigade + regiment + rank roles plus these extras.
# You don't need to list brigade/regiment/rank roles here because they're added automatically from the config sets above.
_PURGE_EXTRA: list[str] = [
    "Corps de Cavalerie Impériale",
    "Verified",
    "Garde Nationale de Cavalerie",
    "Citoyen",
    "Soldat",
    "Caporal",
    "Caporal Fourrier",
]
PURGE_ROLES: set[str] = (
    ALL_RANK_ROLES | ALL_BRIGADE_ROLES | ALL_REGIMENT_ROLES | set(_PURGE_EXTRA)
)

# ============================================================
#  COMMAND PERMISSIONS
#  Maps command name → set of Discord role names allowed to run it.
#  Add or remove roles here without touching command code.
# ============================================================

_ETAT_MAJOR_ROLES: set[str] = {
    "Administration Team"
    "Head of Administration",
    "26ème État-major",
    "7ème État-major",
    "5ème État-major",
    "GaC État-major",
    "Adjudant Sous-Officier",
    "Lieutenant en Second",
    "Lieutenant en Premier",
    "Capitaine",
    "Chef d'Escadron",
    "Major",
    "Colonel",
    "Adjudant-Commandant",
    "Adjoint du Corps",
    "Adjoint du Général de Division",
    "Adjoint du Général de Brigade",
    "Adjoint du Maréchal",
    "Adjoint d'État Major",
    "Commandant de Cavalerie Brigade",
    "Cavalerie État-major",
    "Admin",
    "Adjudant-Commandant",
    "Géneral de Brigade",
    "Général de Division",
    "Maréchal",
    "Maréchal en Major Général",
    "Napoléon",
    "Super Admin"
}

COMMAND_PERMISSIONS: dict[str, set[str]] = {
    "background-check": {"Recruitment Team"} | {"Head of Recruitment"} | _ETAT_MAJOR_ROLES,
    "induct": {"Recruitment Team"}| {"Head of Recruitment"} | _ETAT_MAJOR_ROLES,
    "purge": _ETAT_MAJOR_ROLES,
    "promote": _ETAT_MAJOR_ROLES
}

# ============================================================
#  CACHE  (in-memory dict, flushed to JSON on every write)
#
#  Schema per entry:
#    "discord_id": {
#        "roblox_id":       str,
#        "roblox_username": str,
#        "discord_username": str,
#        "cached_at":       ISO-8601 str,
#    }
# ============================================================

CACHE_PATH = "verified_users.json"
CACHE_LOCK = asyncio.Lock()

def _load_cache() -> dict:
    try:
        if os.path.exists(CACHE_PATH):
            with open(CACHE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        log.error(f"[CACHE] Load failed: {e}")
    return {}

verified_cache: dict = _load_cache()

async def _save_cache() -> None:
    async with CACHE_LOCK:
        try:
            with open(CACHE_PATH, "w", encoding="utf-8") as f:
                json.dump(verified_cache, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[CACHE] Save failed: {e}")
            log.error(f"[CACHE] Save failed: {e}")

def get_cached_user(discord_id: str) -> dict | None:
    return verified_cache.get(str(discord_id))

async def cache_user(discord_id: str, roblox_id: str, username: str, discord_username: str = "") -> None:
    """Write one entry into the in-memory cache and flush to disk."""
    verified_cache[str(discord_id)] = {
        "roblox_id":        str(roblox_id),
        "roblox_username":  username,
        "discord_username": discord_username,
        "cached_at":        datetime.now(timezone.utc).isoformat(),
    }
    await _save_cache()
    print(f"[CACHE] Cached {discord_id} → {username} ({discord_username})")
    log.info(f"[CACHE] Cached {discord_id} → {username} ({discord_username})")

# ============================================================
#  ROBLOX REST HELPERS
#  Each function is responsible for exactly one API concern.
#  All HTTP errors are caught and logged; callers get a clean
#  empty value (dict/list/None/False) on failure.
# ============================================================

async def roblox_get_user_info(roblox_id: str) -> dict:
    """
    Fetches username, display name, and a human-readable account age.
    Returns: {name, display_name, account_age, created}
    Returns empty dict on any failure.
    """
    async with ROBLOX_SEMAPHORE:
        try:
            async with aiohttp.ClientSession(timeout=HTTP_TIMEOUT) as s:
                async with s.get(f"https://users.roblox.com/v1/users/{roblox_id}") as r:
                    if r.status != 200:
                        return {}
                    data = await r.json()
        except Exception as e:
            print(f"[ROBLOX] roblox_get_user_info error: {e}")
            return {}

    account_age = "Unknown"
    created_str = data.get("created", "")
    if created_str:
        try:
            dt    = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
            delta = datetime.now(timezone.utc) - dt
            y, m, d = delta.days // 365, (delta.days % 365) // 30, delta.days % 30
            account_age = f"{y} years, {m} months, {d} days"
        except Exception:
            pass

    return {
        "name": data.get("name", ""),
        "display_name": data.get("displayName", ""),
        "account_age": account_age,
        "created": created_str,
    }

async def roblox_get_username(roblox_id: str) -> str | None:
    """Thin wrapper — returns just the username string, or None."""
    info = await roblox_get_user_info(roblox_id)
    return info.get("name") or None

async def roblox_get_previous_usernames(roblox_id: str) -> str:
    """Returns a comma-separated string of previous usernames, or 'None'."""
    async with ROBLOX_SEMAPHORE:
        try:
            async with aiohttp.ClientSession(timeout=HTTP_TIMEOUT) as s:
                async with s.get(
                    f"https://users.roblox.com/v1/users/{roblox_id}/username-history?limit=10"
                ) as r:
                    if r.status != 200:
                        return "None"
                    data = await r.json()
                    names = [e["name"] for e in data.get("data", [])]
                    return ", ".join(names) if names else "None"
        except Exception:
            return "None"

async def roblox_get_avatar_url(roblox_id: str) -> str | None:
    """Returns the headshot thumbnail URL for a Roblox user, or None."""
    async with ROBLOX_SEMAPHORE:
        try:
            async with aiohttp.ClientSession(timeout=HTTP_TIMEOUT) as s:
                async with s.get(
                    "https://thumbnails.roblox.com/v1/users/avatar-headshot"
                    f"?userIds={roblox_id}&size=150x150&format=Png&isCircular=false"
                ) as r:
                    if r.status != 200:
                        return None
                    data = await r.json()
                    entries = data.get("data", [])
                    return entries[0].get("imageUrl") if entries else None
        except Exception:
            return None

async def roblox_get_group_memberships(roblox_id: str) -> list[dict]:
    """
    Returns all Roblox groups a user belongs to.
    Each entry: {name: str, id: str, rank: str}
    """
    async with ROBLOX_SEMAPHORE:
        try:
            async with aiohttp.ClientSession(timeout=HTTP_TIMEOUT) as s:
                async with s.get(
                    f"https://groups.roblox.com/v2/users/{roblox_id}/groups/roles"
                ) as r:
                    if r.status != 200:
                        return []
                    data = await r.json()
                    return [
                        {
                            "name": e["group"]["name"],
                            "id": str(e["group"]["id"]),
                            "rank": e["role"]["name"],
                        }
                        for e in data.get("data", [])
                    ]
        except Exception as e:
            print(f"[ROBLOX] roblox_get_group_memberships error: {e}")
            return []

async def roblox_get_group_rank(roblox_id: str, group_id: str) -> str | None:
    """Returns the rank name for a specific group, or None if not a member."""
    groups = await roblox_get_group_memberships(roblox_id)
    for g in groups:
        if g["id"] == str(group_id):
            return g["rank"]
    return None

async def roblox_accept_join_request(roblox_id: str, group_id: str) -> bool:
    """Accepts a pending Roblox group join request for a user."""
    if not ROBLOX_OPEN_CLOUD:
        print("[ROBLOX] No Open Cloud key configured.")
        return False

    async with ROBLOX_SEMAPHORE:
        try:
            async with aiohttp.ClientSession(timeout=HTTP_TIMEOUT) as s:
                # List pending join requests
                async with s.get(
                    f"https://apis.roblox.com/cloud/v2/groups/{group_id}/join-requests",
                    headers=_oc_headers(),
                    params={"maxPageSize": 100},
                ) as r:
                    if r.status != 200:
                        print(f"[ROBLOX] List join-requests failed: {r.status}")
                        return False
                    data = await r.json()

                # Find the matching request path
                request_path = next(
                    (req.get("path") for req in data.get("groupJoinRequests", [])
                     if str(roblox_id) in req.get("user", "")),
                    None,
                )
                if not request_path:
                    print(f"[ROBLOX] No pending join request for {roblox_id}")
                    return False

                # Accept it
                async with s.post(
                    f"https://apis.roblox.com/cloud/v2/{request_path}:accept",
                    headers=_oc_headers(),
                    json={},
                ) as r:
                    print(f"[ROBLOX] Accept join-request status: {r.status}")
                    return r.status in (200, 204)

        except Exception as e:
            print(f"[ROBLOX] roblox_accept_join_request error: {e}")
            return False

async def roblox_set_rank(roblox_id: str, group_id: str, rank_name: str) -> bool:
    """
    Sets a user's rank in a Roblox group via Open Cloud.
    Three-step process: fetch paginated role list → find role path
    → fetch membership path → PATCH.
    """
    print(f"[ROBLOX] Setting rank: user={roblox_id} rank='{rank_name}' group={group_id}")
    if not ROBLOX_OPEN_CLOUD:
        print("[ROBLOX] No Open Cloud key configured.")
        return False

    async with ROBLOX_SEMAPHORE:
        try:
            async with aiohttp.ClientSession(timeout=HTTP_TIMEOUT) as s:

                # Step 1 — collect all roles (paginated)
                all_roles = []
                page_token  = None
                while True:
                    params = {"maxPageSize": 20}
                    if page_token:
                        params["pageToken"] = page_token
                    async with s.get(
                        f"https://apis.roblox.com/cloud/v2/groups/{group_id}/roles",
                        headers=_oc_headers(),
                        params=params,
                    ) as r:
                        if r.status != 200:
                            print(f"[ROBLOX] Get roles failed: {r.status}")
                            return False
                        roles_data = await r.json()
                    all_roles.extend(roles_data.get("groupRoles", []))
                    page_token = roles_data.get("nextPageToken") or ""
                    if not page_token:
                        break

                # Step 2 — find the target role path
                role_path = next(
                    (
                        role.get("path") for role in all_roles
                        if (role.get("displayName") or role.get("name") or "").strip().lower()
                        == rank_name.strip().lower()
                    ),
                    None,
                )
                if not role_path:
                    print(f"[ROBLOX] Role '{rank_name}' not found in group {group_id}")
                    return False

                print(f"[ROBLOX] Found role path: {role_path}")

                # Step 3 — get membership path
                async with s.get(
                    f"https://apis.roblox.com/cloud/v2/groups/{group_id}/memberships",
                    headers=_oc_headers(),
                    params={"filter": f"user == 'users/{roblox_id}'"},
                ) as r:
                    if r.status != 200:
                        print(f"[ROBLOX] Get membership failed: {r.status}")
                        return False
                    membership_data = await r.json()

                memberships = membership_data.get("groupMemberships", [])
                if not memberships:
                    print(f"[ROBLOX] No membership found for {roblox_id} in {group_id}")
                    return False

                membership_path = memberships[0]["path"]
                print(f"[ROBLOX] Membership path: {membership_path}")

                # Step 4 — PATCH the rank
                async with s.patch(
                    f"https://apis.roblox.com/cloud/v2/{membership_path}",
                    headers=_oc_headers(),
                    json={"role": role_path},
                ) as r:
                    body = await r.text()
                    success = r.status in (200, 204)
                    print(f"[ROBLOX] Rank PATCH {r.status}: {body[:120]}")
                    if success:
                        log.info(f"[ROBLOX] Ranked {roblox_id} → '{rank_name}' in {group_id}")
                    return success

        except Exception as e:
            print(f"[ROBLOX] roblox_set_rank error: {e}")
            return False

async def roblox_kick_from_group(roblox_id: str, group_id: str) -> bool:
    """Removes a user from a Roblox group by deleting their membership."""
    if not ROBLOX_OPEN_CLOUD:
        print("[ROBLOX] No Open Cloud key configured.")
        return False

    async with ROBLOX_SEMAPHORE:
        try:
            async with aiohttp.ClientSession(timeout=HTTP_TIMEOUT) as s:
                # Find membership path
                async with s.get(
                    f"https://apis.roblox.com/cloud/v2/groups/{group_id}/memberships",
                    headers=_oc_headers(),
                    params={"filter": f"user == 'users/{roblox_id}'"},
                ) as r:
                    if r.status != 200:
                        print(f"[ROBLOX] Get membership failed: {r.status}")
                        return False
                    data = await r.json()
                    memberships = data.get("groupMemberships", [])
                    if not memberships:
                        print(f"[ROBLOX] {roblox_id} not found in group {group_id}")
                        return False
                    membership_path = memberships[0]["path"]

                # Delete the membership
                async with s.delete(
                    f"https://apis.roblox.com/cloud/v2/{membership_path}",
                    headers=_oc_headers(),
                ) as r:
                    print(f"[ROBLOX] Kick status: {r.status}")
                    success = r.status in (200, 204)
                    if success:
                        log.info(f"[ROBLOX] Kicked {roblox_id} from group {group_id}")
                    return success

        except Exception as e:
            print(f"[ROBLOX] roblox_kick_from_group error: {e}")
            return False

# ============================================================
#  BLOXLINK
#  Resolves a Discord user to their Roblox account.
#  Results are cached in verified_users.json.
# ============================================================

async def resolve_roblox_user(discord_id: str) -> dict | None:
    """
    Returns a cache-entry dict for a Discord user:
        {roblox_id, roblox_username, discord_username, cached_at}
    Returns None if the user is not verified with Bloxlink,
    or if the Bloxlink API is unavailable.
    """
    # Cache hit
    cached = get_cached_user(discord_id)
    if cached:
        print(f"[BLOXLINK] Cache hit for {discord_id}")
        return cached

    if not BLOXLINK_API_KEY:
        print("[BLOXLINK] No API key configured.")
        return None

    # Bloxlink lookup
    url = f"https://api.blox.link/v4/public/guilds/{GUILD_ID}/discord-to-roblox/{discord_id}"
    headers = {"Authorization": BLOXLINK_API_KEY}

    try:
        async with aiohttp.ClientSession(timeout=HTTP_TIMEOUT) as s:
            async with s.get(url, headers=headers) as r:
                print(f"[BLOXLINK] {discord_id} → HTTP {r.status}")
                if r.status != 200:
                    return None
                body = await r.json()
                roblox_id = str(body.get("robloxID") or body.get("roblox_id", ""))
                if not roblox_id:
                    return None
    except Exception as e:
        print(f"[BLOXLINK] Exception: {e}")
        return None

    # Resolve username (users.roblox.com may be intermittently down)
    username = await roblox_get_username(roblox_id)
    if not username:
        print(f"[BLOXLINK] Username lookup failed for {roblox_id} — returning without caching")
        return {"roblox_id": roblox_id, "roblox_username": f"Unknown ({roblox_id})"}

    # Resolve Discord display name for the cache entry
    guild = bot.get_guild(int(GUILD_ID))
    discord_member = guild.get_member(int(discord_id)) if guild else None
    discord_uname = str(discord_member) if discord_member else ""

    await cache_user(discord_id, roblox_id, username, discord_uname)
    return {"roblox_id": roblox_id, "roblox_username": username}

# ============================================================
#  STARTUP SYNC
#  On startup, resolves any Verified members not yet in cache.
#  Runs again every 6 hours via the periodic_sync task.
#  Throttled to one Bloxlink call every 2 seconds to avoid
#  hitting rate limits.
# ============================================================

async def sync_verified_users() -> None:
    print("[SYNC] Starting verified-user sync…")
    guild = bot.get_guild(int(GUILD_ID))
    if not guild:
        print("[SYNC] Guild not found.")
        return

    verified_role = discord.utils.get(guild.roles, name="Verified")
    if not verified_role:
        print("[SYNC] 'Verified' role not found.")
        return

    to_sync = [m for m in verified_role.members if not get_cached_user(str(m.id))]
    print(f"[SYNC] {len(verified_cache)} already cached | {len(to_sync)} to resolve")

    synced = failed = 0
    for member in to_sync:
        try:
            roblox = await resolve_roblox_user(str(member.id))
            if roblox and not roblox["roblox_username"].startswith("Unknown"):
                synced += 1
                print(f"[SYNC] {member.id} → {roblox['roblox_username']} ({roblox['roblox_id']})")
                log.info(f"[SYNC] {member.id} → {roblox['roblox_username']} ({roblox['roblox_id']})")
            else:
                failed += 1
                print(f"[SYNC] Failed for {member.id} ({member})")
            await asyncio.sleep(2)
        except Exception as e:
            failed += 1
            print(f"[SYNC] Error for {member.id}: {e}")

    print(f"[SYNC] Done — synced: {synced} | failed: {failed}")
    log.info(f"[SYNC] Done — synced: {synced} | failed: {failed}")

# ============================================================
#  DISCORD HELPERS
# ============================================================

def get_highest_rank(member: discord.Member) -> str | None:
    """Returns the name of the highest rank role the member holds, or None."""
    best_idx = -1
    best_name = None
    for role in member.roles:
        idx = DISCORD_RANK_INDEX.get(role.name)
        if idx is not None and idx > best_idx:
            best_idx  = idx
            best_name = role.name
    return best_name

def get_rank_index(member: discord.Member) -> int:
    """Returns the numeric rank index of the member, or -1 if unranked."""
    rank = get_highest_rank(member)
    return DISCORD_RANK_INDEX.get(rank, -1)

def is_senior_promoter(member: discord.Member) -> bool:
    """Returns True if the member holds any senior promoter role."""
    return any(r.name in SENIOR_PROMOTER_ROLES for r in member.roles)

def has_command_permission(interaction: discord.Interaction, command: str) -> bool:
    """Returns True if the executor holds at least one allowed role for the command."""
    member = interaction.guild.get_member(interaction.user.id)
    allowed = COMMAND_PERMISSIONS.get(command, set())
    return bool(member and any(r.name in allowed for r in member.roles))

def categorise_groups(groups: list[dict]) -> tuple[list[str], list[str], list[str]]:
    """Splits a user's group list into French, Coalition, and Neutral buckets."""
    french = coalition = neutral = []
    french, coalition, neutral = [], [], []
    for g in groups:
        gid = g["id"]
        rank = g["rank"]
        if gid in FRENCH_GROUP_IDS:
            french.append(f"{FRENCH_GROUP_IDS[gid]} — {rank}")
        elif gid in COALITION_GROUP_IDS:
            coalition.append(f"{COALITION_GROUP_IDS[gid]} — {rank}")
        elif gid in NEUTRAL_GROUP_IDS:
            neutral.append(f"{NEUTRAL_GROUP_IDS[gid]} — {rank}")
    return french, coalition, neutral

def truncate_field(lines: list[str], limit: int = 1020) -> str:
    """Joins lines for a Discord embed field, truncating if needed."""
    if not lines:
        return "None"
    text = "\n".join(lines)
    return text[:limit] + "\n…" if len(text) > limit else text

MENTION_RE = re.compile(r"<@!?(\d+)>")

def parse_mentions(text: str) -> list[int]:
    """Returns a list of integer Discord IDs from a mention string."""
    return [int(m) for m in MENTION_RE.findall(text)]

# ============================================================
#  BOT + TASKS
# ============================================================

intents = discord.Intents.default()
intents.message_content = True
intents.members         = True

bot = commands.Bot(command_prefix="!", intents=intents)

@tasks.loop(hours=6)
async def periodic_sync():
    await sync_verified_users()

@bot.event
async def on_ready():
    print(f"[BOT] Logged in & online as {bot.user} - {bot.user.id}")
    log.info(f"[BOT] Logged in & online as {bot.user} <@{bot.user.id}>")
    print(f"[CACHE] {len(verified_cache)} users loaded from disk.")
    log.info(f"[CACHE] {len(verified_cache)} users loaded from disk.")

    try:
        guild  = discord.Object(id=int(GUILD_ID))
        bot.tree.copy_global_to(guild=guild)
        synced = await bot.tree.sync(guild=guild)
        print(f"[BOT] Synced {len(synced)} command(s) to guild.")
        log.info(f"[BOT] Synced {len(synced)} command(s).")
    except Exception as e:
        print(f"[BOT] Command sync error: {e}")

    if not periodic_sync.is_running():
        periodic_sync.start()

@bot.event
async def on_member_update(before: discord.Member, after: discord.Member):
    """Auto-cache a member the moment they receive the Verified role."""
    verified_role = discord.utils.get(after.guild.roles, name="Verified")
    if not verified_role:
        return
    if verified_role in before.roles or verified_role not in after.roles:
        return

    print(f"[VERIFY] {after} just got Verified — caching…")
    roblox = await resolve_roblox_user(str(after.id))
    if roblox and not roblox["roblox_username"].startswith("Unknown"):
        print(f"[VERIFY] Cached {after} → {roblox['roblox_username']}")
        log.info(f"[VERIFY] Auto-cached {after} → {roblox['roblox_username']}")

# ============================================================
#  /background-check
# ============================================================

@bot.tree.command(
    name="background-check",
    description="Run a background check on one or more verified users.",
)
@app_commands.describe(users="Mention one or more users to check")
async def background_check(interaction: discord.Interaction, users: str):
    if not has_command_permission(interaction, "background-check"):
        await interaction.response.send_message(
            "❌ You don't have permission to use this command.", ephemeral=True
        )
        return

    await interaction.response.defer()

    ids = parse_mentions(users)
    if not ids:
        await interaction.followup.send("Please mention at least one user.")
        return

    for discord_id in ids:
        try:
            member = interaction.guild.get_member(discord_id)
            roblox = await resolve_roblox_user(str(discord_id))

            if not roblox:
                await interaction.followup.send(f"❌ <@{discord_id}> is not verified with Bloxlink.")
                continue

            roblox_id = roblox["roblox_id"]

            # Fire all lookups concurrently
            user_info, prev_names, all_groups, avatar_url = await asyncio.gather(
                roblox_get_user_info(roblox_id),
                roblox_get_previous_usernames(roblox_id),
                roblox_get_group_memberships(roblox_id),
                roblox_get_avatar_url(roblox_id),
                return_exceptions=True,
            )
            if isinstance(user_info, Exception): user_info  = {}
            if isinstance(prev_names, Exception): prev_names = "None"
            if isinstance(all_groups, Exception): all_groups = []
            if isinstance(avatar_url, Exception): avatar_url = None

            username = user_info.get("name") or roblox["roblox_username"]
            age_str = user_info.get("account_age", "Unknown")
            groups = all_groups if isinstance(all_groups, list) else []

            french_rank = cav_rank = "Not a member"
            for g in groups:
                if g["id"] == str(FRENCH_MAIN_GROUP_ID): french_rank = g["rank"]
                if g["id"] == str(CAV_GROUP_ID): cav_rank = g["rank"]

            french, coalition, neutral = categorise_groups(groups)

            embed = discord.Embed(title="Background Check Results", color=discord.Color.dark_blue())
            if avatar_url:
                embed.set_thumbnail(url=avatar_url)

            embed.add_field(
                name="Account",
                value=f"<@{discord_id}>, {username}",
                inline=False,
            )
            embed.add_field(name="Account Age", value=age_str, inline=True)
            embed.add_field(name="Prev. Usernames", value=prev_names, inline=True)
            embed.add_field(
                name="French Rankings",
                value=f"Empire Français — {french_rank}\nCorps de Cavalerie — {cav_rank}",
                inline=False,
            )
            embed.add_field(name=f"🇫🇷 French Empire & Clients ({len(french)})",
                            value=truncate_field(french), inline=False)
            embed.add_field(name=f"⚔️ Coalition Powers ({len(coalition)})",
                            value=truncate_field(coalition), inline=False)
            embed.add_field(name=f"🌐 Neutral Powers ({len(neutral)})",
                            value=truncate_field(neutral), inline=False)
            embed.set_footer(text=f"Roblox ID: {roblox_id} • roblox.com/users/{roblox_id}/profile")

            await interaction.followup.send(embed=embed)
            log.info(f"[BG-CHECK] {username} ({roblox_id}) checked by {interaction.user}")

        except Exception as e:
            await interaction.followup.send(f"❌ Error checking <@{discord_id}>: {type(e).__name__}: {e}")
            log.error(f"[BG-CHECK] Error for {discord_id}: {e}")

# ============================================================
#  /induct
# ============================================================

@bot.tree.command(name="induct", description="Induct one or more recruits into the regiment.")
@app_commands.describe(users="Mention one or more users to induct")
async def induct(interaction: discord.Interaction, users: str):
    if not has_command_permission(interaction, "induct"):
        await interaction.response.send_message(
            "❌ You don't have permission to use this command.", ephemeral=True
        )
        return

    await interaction.response.defer()

    ids = parse_mentions(users)
    if not ids:
        await interaction.followup.send("Please mention at least one user.")
        return

    for discord_id in ids:
        lines = ["**Induct Results**"]
        try:
            member = interaction.guild.get_member(discord_id)
            if not member:
                member = await asyncio.wait_for(
                    interaction.guild.fetch_member(discord_id), timeout=10
                )
            lines.append(f"<@{discord_id}> — {member.display_name}")

            roblox = await resolve_roblox_user(str(discord_id))
            if not roblox:
                lines.append("❌ Not verified with Bloxlink. Aborted.")
                await interaction.followup.send("\n".join(lines))
                continue

            roblox_id = roblox["roblox_id"]
            username = roblox["roblox_username"]

            # Accept join request if not already in the group
            cav_rank = await roblox_get_group_rank(roblox_id, CAV_GROUP_ID)
            if not cav_rank or cav_rank.lower() == "guest":
                accepted = await asyncio.wait_for(
                    roblox_accept_join_request(roblox_id, CAV_GROUP_ID), timeout=15
                )
                if accepted:
                    lines.append("✅ Accepted into Corps de Cavalerie Impériale.")
                else:
                    lines.append(
                        "❌ Not in Cav group and no pending join request. "
                        "Ask them to send a join request first. Aborted."
                    )
                    await interaction.followup.send("\n".join(lines))
                    continue
            else:
                lines.append(f"⚠️ Already in Cav group as {cav_rank}.")

            # Set Roblox rank
            if cav_rank and cav_rank.lower() == CAV_INDUCT_ROBLOX_RANK.lower():
                lines.append(f"⚠️ Already ranked {CAV_INDUCT_ROBLOX_RANK}. Skipping.")
            else:
                try:
                    ranked = await asyncio.wait_for(
                        roblox_set_rank(roblox_id, CAV_GROUP_ID, CAV_INDUCT_ROBLOX_RANK),
                        timeout=30,
                    )
                    lines.append(
                        f"✅ Ranked to {CAV_INDUCT_ROBLOX_RANK}." if ranked
                        else "❌ Failed to set Roblox rank — set manually."
                    )
                except asyncio.TimeoutError:
                    lines.append("⚠️ Roblox rank request timed out — set manually.")

            guild = interaction.guild

            # Strip old roles
            stripped = []
            for name in INDUCT_REMOVE:
                role = discord.utils.get(guild.roles, name=name)
                if role and role in member.roles:
                    await member.remove_roles(role)
                    stripped.append(name)
            lines.append(
                f"✅ Stripped: {', '.join(stripped)}" if stripped else "⚠️ No roles to strip."
            )

            # Add induction roles
            added = missing = []
            added, missing = [], []
            for name in INDUCT_ADD:
                role = discord.utils.get(guild.roles, name=name)
                if role:
                    if role not in member.roles:
                        await member.add_roles(role)
                    added.append(name)
                else:
                    missing.append(name)
            if added:   lines.append(f"✅ Added: {', '.join(added)}")
            if missing: lines.append(f"❌ Not found in server: {', '.join(missing)}")

            # Nickname
            new_nick = f"[26e] {username}"
            try:
                await member.edit(nick=new_nick)
                lines.append(f"✅ Nickname → {new_nick}")
            except discord.Forbidden:
                lines.append("⚠️ Cannot change nickname (bot role too low or server owner).")
            except discord.HTTPException as e:
                lines.append(f"⚠️ Nickname failed: {e.text}")

            log.info(f"[INDUCT] {username} inducted by {interaction.user}")

        except asyncio.TimeoutError:
            lines.append("❌ A request timed out.")
            log.error(f"[INDUCT] Timeout for {discord_id}")
        except Exception as e:
            lines.append(f"❌ Unexpected error: {type(e).__name__}: {e}")
            log.error(f"[INDUCT] Error for {discord_id}: {e}")

        await interaction.followup.send("\n".join(lines))

# ============================================================
#  /purge
# ============================================================

@bot.tree.command(
    name="purge",
    description="Strip all roles, kick from Roblox group, and reset nickname.",
)
@app_commands.describe(users="Mention one or more users to purge")
async def purge(interaction: discord.Interaction, users: str):
    if not has_command_permission(interaction, "purge"):
        await interaction.response.send_message(
            "❌ You don't have permission to use this command.", ephemeral=True
        )
        return

    await interaction.response.defer()

    ids = parse_mentions(users)
    if not ids:
        await interaction.followup.send("Please mention at least one user.")
        return

    for discord_id in ids:
        lines = ["**Purge Results**"]
        try:
            member = interaction.guild.get_member(discord_id)
            if not member:
                try:
                    member = await asyncio.wait_for(
                        interaction.guild.fetch_member(discord_id), timeout=10
                    )
                except Exception:
                    lines.append(f"❌ Could not find Discord member <@{discord_id}>.")
                    await interaction.followup.send("\n".join(lines))
                    continue

            lines.append(f"<@{discord_id}> — {member.display_name}")

            # Roblox group kick
            roblox = await resolve_roblox_user(str(discord_id))
            if not roblox:
                lines.append("⚠️ Not verified with Bloxlink — skipping Roblox kick.")
            else:
                roblox_id = roblox["roblox_id"]
                cav_rank  = await roblox_get_group_rank(roblox_id, CAV_GROUP_ID)
                if not cav_rank:
                    lines.append("⚠️ Not in Cav Roblox group — skipping kick.")
                else:
                    kicked = await asyncio.wait_for(
                        roblox_kick_from_group(roblox_id, CAV_GROUP_ID), timeout=15
                    )
                    lines.append(
                        "✅ Kicked from Corps de Cavalerie Impériale (Roblox)." if kicked
                        else "❌ Failed to kick from Roblox group — remove manually."
                    )

            # Strip Discord roles
            stripped = []
            for name in PURGE_ROLES:
                role = discord.utils.get(interaction.guild.roles, name=name)
                if role and role in member.roles:
                    await member.remove_roles(role)
                    stripped.append(name)
            lines.append(
                f"✅ Stripped: {', '.join(stripped)}" if stripped
                else "⚠️ No matching roles found to strip."
            )

            # Reset nickname
            try:
                await member.edit(nick=None)
                lines.append("✅ Nickname reset.")
            except discord.Forbidden:
                lines.append("⚠️ Cannot reset nickname (bot role too low or server owner).")
            except discord.HTTPException as e:
                lines.append(f"⚠️ Nickname reset failed: {e.text}")

            log.info(f"[PURGE] {member} purged by {interaction.user}")

        except asyncio.TimeoutError:
            lines.append("❌ A request timed out.")
            log.error(f"[PURGE] Timeout for {discord_id}")
        except Exception as e:
            lines.append(f"❌ Unexpected error: {type(e).__name__}: {e}")
            log.error(f"[PURGE] Error for {discord_id}: {e}")

        await interaction.followup.send("\n".join(lines))

# ============================================================
#  /promote — UI components
# ============================================================

class PromoteTypeSelect(discord.ui.Select):
    def __init__(self):
        super().__init__(
            placeholder="Choose promotion type…",
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(
                    label="Rank Promotion",
                    value="rank",
                    description="Move target(s) up to a chosen Discord rank",
                ),
                discord.SelectOption(
                    label="Draft to Brigade",
                    value="draft",
                    description="Reset rank to Cavalier and move to a brigade",
                ),
            ],
        )

    async def callback(self, interaction: discord.Interaction):
        self.view.promo_type = self.values[0]
        await interaction.response.defer()
        self.view.stop()


class TargetRankSelect(discord.ui.Select):
    def __init__(self, min_idx: int, max_idx: int):
        """Shows only the rank range the executor is permitted to assign."""
        options = [
            discord.SelectOption(label=name, value=name)
            for i, name in enumerate(DISCORD_RANKS)
            if min_idx <= i <= max_idx
        ]
        super().__init__(
            placeholder="Select target rank…",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        self.view.target_rank = self.values[0]
        await interaction.response.defer()
        self.view.stop()


class BrigadeSelect(discord.ui.Select):
    def __init__(self):
        super().__init__(
            placeholder="Select target brigade…",
            min_values=1,
            max_values=1,
            options=[discord.SelectOption(label=b, value=b) for b in BRIGADES],
        )

    async def callback(self, interaction: discord.Interaction):
        self.view.target_brigade = self.values[0]
        await interaction.response.defer()
        self.view.stop()


class SingleSelectView(discord.ui.View):
    """Generic single-step select view.  Caller reads .promo_type /
    .target_rank / .target_brigade after await view.wait()."""
    def __init__(self, select: discord.ui.Select, timeout: int = 60):
        super().__init__(timeout=timeout)
        self.promo_type: str | None = None
        self.target_rank: str | None = None
        self.target_brigade: str | None = None
        self.add_item(select)

# ============================================================
#  /promote
# ============================================================

@bot.tree.command(
    name="promote",
    description="Promote member(s) by rank, or draft them to a brigade.",
)
@app_commands.describe(members="Mention one or more members to promote")
@app_commands.default_permissions(manage_roles=True)
async def promote(interaction: discord.Interaction, members: str):
    if not has_command_permission(interaction, "promote"):
        await interaction.response.send_message(
            "❌ You don't have permission to use this command.", ephemeral=True
        )
        return

    targets = [
        interaction.guild.get_member(mid)
        for mid in parse_mentions(members)
    ]
    targets = [t for t in targets if t is not None]

    if not targets:
        await interaction.response.send_message("❌ No valid members mentioned.", ephemeral=True)
        return

    exec_member = interaction.guild.get_member(interaction.user.id)
    exec_idx = get_rank_index(exec_member)
    senior = is_senior_promoter(exec_member)
    min_exec_idx = DISCORD_RANK_INDEX.get("Adjudant Sous-Officier", 0)

    if exec_idx < min_exec_idx and not senior:
        await interaction.response.send_message(
            "❌ You must hold at least **Adjudant Sous-Officier** to promote.", ephemeral=True
        )
        return

    # ── Step 1: promotion type ────────────────────────────────────────────────
    type_view = SingleSelectView(PromoteTypeSelect())
    await interaction.response.send_message(
        "**Step 1:** What type of promotion is this?", view=type_view, ephemeral=True
    )
    await type_view.wait()

    if type_view.promo_type is None:
        await interaction.edit_original_response(content="⏱️ Timed out.", view=None)
        return

    # ── DRAFT flow ────────────────────────────────────────────────────────────
    if type_view.promo_type == "draft":
        brigade_view = SingleSelectView(BrigadeSelect())
        await interaction.edit_original_response(
            content="**Step 2:** Select the brigade to draft target(s) into:",
            view=brigade_view,
        )
        await brigade_view.wait()

        if brigade_view.target_brigade is None:
            await interaction.edit_original_response(content="⏱️ Timed out.", view=None)
            return

        target_brigade = brigade_view.target_brigade
        regiment_names = BRIGADE_REGIMENTS[target_brigade]

        await interaction.edit_original_response(content="⏳ Processing draft…", view=None)

        async def draft_one(member: discord.Member) -> str:
            roblox = await resolve_roblox_user(str(member.id))
            if not roblox:
                return f"❌ **{member.display_name}** — could not resolve Roblox account."

            roblox_id = roblox["roblox_id"]
            username = roblox["roblox_username"]
            errors: list[str] = []

            # 1. Set Roblox brigade rank
            ok = await roblox_set_rank(roblox_id, CAV_GROUP_ID, target_brigade)
            if not ok:
                errors.append("failed to set Roblox brigade rank")

            guild = interaction.guild

            # 2. Swap Discord rank role → Cavalier
            old_ranks = [r for r in member.roles if r.name in ALL_RANK_ROLES]
            cavalier_role = discord.utils.get(guild.roles, name=DRAFT_RESET_RANK)
            try:
                if old_ranks:
                    await member.remove_roles(*old_ranks, reason="Draft: rank reset")
                if cavalier_role:
                    await member.add_roles(cavalier_role, reason=f"Draft → {target_brigade}")
                else:
                    errors.append(f"'{DRAFT_RESET_RANK}' role not found in server")
            except discord.Forbidden:
                errors.append("missing permissions to modify rank roles")

            # 3. Swap brigade Discord role
            old_brigades = [r for r in member.roles if r.name in ALL_BRIGADE_ROLES]
            new_brigade_role = discord.utils.get(guild.roles, name=target_brigade)
            try:
                if old_brigades:
                    await member.remove_roles(*old_brigades, reason="Draft: brigade swap")
                if new_brigade_role:
                    await member.add_roles(new_brigade_role, reason=f"Draft → {target_brigade}")
                else:
                    errors.append(f"'{target_brigade}' Discord role not found in server")
            except discord.Forbidden:
                errors.append("missing permissions to modify brigade roles")

            # 4. Swap regiment Discord role(s)
            old_regiments = [r for r in member.roles if r.name in ALL_REGIMENT_ROLES]
            new_regiment_roles = [
                discord.utils.get(guild.roles, name=rn) for rn in regiment_names
            ]
            new_regiment_roles = [r for r in new_regiment_roles if r is not None]
            try:
                if old_regiments:
                    await member.remove_roles(*old_regiments, reason="Draft: regiment swap")
                if new_regiment_roles:
                    await member.add_roles(*new_regiment_roles, reason=f"Draft → {target_brigade}")
            except discord.Forbidden:
                errors.append("missing permissions to modify regiment roles")

            if errors:
                return f"⚠️ **{username}** — drafted with issues: {'; '.join(errors)}."

            regiment_str = ", ".join(regiment_names)
            log.info(f"[PROMOTE/DRAFT] {username} drafted → {target_brigade} by {interaction.user}")
            return (
                f"✅ **{username}** — drafted to **{target_brigade}** "
                f"({regiment_str}), rank reset to **{DRAFT_RESET_RANK}**."
            )

        async with asyncio.timeout(120):
            results = await asyncio.gather(*[draft_one(m) for m in targets])

        await interaction.edit_original_response(content="\n".join(results), view=None)
        return

    # ── RANK PROMOTION flow ───────────────────────────────────────────────────

    # Senior promoters can assign any rank; others cap out one below their own
    # and cannot exceed SENIOR_THRESHOLD - 1.
    if senior:
        max_idx = len(DISCORD_RANKS) - 1
    else:
        max_idx = min(exec_idx - 1, SENIOR_THRESHOLD - 1)

    min_idx = 1  # cannot promote to Conscrit (index 0)

    if max_idx < min_idx:
        await interaction.edit_original_response(
            content="❌ Your rank is too low to promote anyone.", view=None
        )
        return

    rank_view = SingleSelectView(TargetRankSelect(min_idx, max_idx))
    await interaction.edit_original_response(
        content="**Step 2:** Select the rank to promote target(s) to:", view=rank_view
    )
    await rank_view.wait()

    if rank_view.target_rank is None:
        await interaction.edit_original_response(content="⏱️ Timed out.", view=None)
        return

    target_rank = rank_view.target_rank
    target_rank_idx = DISCORD_RANK_INDEX[target_rank]

    await interaction.edit_original_response(content="⏳ Processing promotions…", view=None)

    async def promote_one(member: discord.Member) -> str:
        current_rank = get_highest_rank(member)
        current_idx = DISCORD_RANK_INDEX.get(current_rank, -1)

        if current_idx >= target_rank_idx:
            return (
                f"⚠️ **{member.display_name}** — already holds **{current_rank}**, "
                f"equal to or above **{target_rank}**. Skipped."
            )

        if current_idx >= exec_idx and not senior:
            return f"❌ **{member.display_name}** — cannot promote someone of equal or higher rank."

        new_role = discord.utils.get(interaction.guild.roles, name=target_rank)
        if not new_role:
            return f"❌ **{member.display_name}** — Discord role **{target_rank}** not found in server."

        old_ranks = [r for r in member.roles if r.name in ALL_RANK_ROLES]
        try:
            if old_ranks:
                await member.remove_roles(*old_ranks, reason="Promotion: strip old rank")
            await member.add_roles(new_role, reason=f"Promoted to {target_rank}")
        except discord.Forbidden:
            return f"❌ **{member.display_name}** — missing permissions to modify roles."

        prev = current_rank or "no rank"
        log.info(f"[PROMOTE/RANK] {member} promoted {prev} → {target_rank} by {interaction.user}")
        return f"✅ **{member.display_name}** — promoted from **{prev}** → **{target_rank}**."

    async with asyncio.timeout(120):
        results = await asyncio.gather(*[promote_one(m) for m in targets])

    await interaction.edit_original_response(content="\n".join(results), view=None)

# ============================================================
#  RUN
# ============================================================

bot.run(DISCORD_TOKEN, log_handler=_log_handler, log_level=logging.DEBUG)