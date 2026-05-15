# Bot name: Bolt 2.0
# Author: orbandit (@just_whiz on Discord)
# Date: 2026-05-14
# Version: 0.8.0

import discord
from discord import app_commands
from discord.ext import commands, tasks
import logging
import os
import re
import json
import aiohttp
import asyncio
from dotenv import load_dotenv
from datetime import timezone, datetime

load_dotenv()

# ─────────────────────────────────────────────
#  ENVIRONMENT
# ─────────────────────────────────────────────

token = os.getenv("DISCORD_TOKEN")
BLOXLINK_API_KEY = os.getenv("BLOXLINK_API_KEY")
GUILD_ID = os.getenv("GUILD_ID")
ROBLOX_OPEN_CLOUD = os.getenv("ROBLOX_OPEN_CLOUD_KEY")
FRENCH_MAIN_GROUP_ID = os.getenv("FRENCH_GROUP_ID", "5610765")
CAV_GROUP_ID = os.getenv("CAV_GROUP_ID", "195387641")

ROBLOX_OC_HEADERS = lambda: {
    "x-api-key":    ROBLOX_OPEN_CLOUD,
    "Content-Type": "application/json"
}

VERIFIED_USERS_PATH = "verified_users.json"
RECRUITMENT_ROLE_NAME = "Recruitment Team"
VERIFIED_ROLE_NAME = "Verified"

# One shared timeout for all HTTP calls
AIOHTTP_TIMEOUT = aiohttp.ClientTimeout(total=12)

# Rate-limit: max concurrent Roblox API calls at once
ROBLOX_SEMAPHORE = asyncio.Semaphore(3)

# ─────────────────────────────────────────────
#  GROUP ID MAPS  (only these are ever displayed)
# Only gruoups in these maps are shown
# ─────────────────────────────────────────────

FRENCH_GROUP_IDS = {
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

COALITION_GROUP_IDS = {
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
    "8254296":  "Zapadnaya Armiya",
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

NEUTRAL_GROUP_IDS = {
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

# ─────────────────────────────────────────────
#  LOGGING
# ─────────────────────────────────────────────

LOG_FILE = "bolt.log"
file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8", mode="a")
file_handler.setFormatter(logging.Formatter(
    fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S"
))
bolt_log = logging.getLogger("bolt")
bolt_log.setLevel(logging.DEBUG)
bolt_log.addHandler(file_handler)
bolt_log.propagate = False

for lib in ("discord", "discord.http", "discord.gateway"):
    lib_logger = logging.getLogger(lib)
    lib_logger.setLevel(logging.DEBUG)
    lib_logger.addHandler(file_handler)
    lib_logger.propagate = False

handler = file_handler

# ─────────────────────────────────────────────
#  PATTERNS
# ─────────────────────────────────────────────

MENTION_PATTERN = re.compile(r'<@!?(\d+)>')

# ─────────────────────────────────────────────
#  JSON CACHE  (in-memory + disk)
# ─────────────────────────────────────────────

CACHE_LOCK = asyncio.Lock()

def _load_cache() -> dict:
    try:
        if os.path.exists(VERIFIED_USERS_PATH):
            with open(VERIFIED_USERS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        bolt_log.error(f"[CACHE] Load failed: {e}")
    return {}

verified_cache: dict = _load_cache()

async def _save_cache():
    async with CACHE_LOCK:
        try:
            with open(VERIFIED_USERS_PATH, "w", encoding="utf-8") as f:
                json.dump(verified_cache, f, indent=None, ensure_ascii=False)
        except Exception as e:
            bolt_log.error(f"[CACHE] Save failed: {e}")

def get_cached_roblox(discord_id: str) -> dict | None:
    return verified_cache.get(str(discord_id))

async def cache_roblox_user(discord_id: str, roblox_id: str, username: str):
    """Write one entry to the in-memory cache and flush to disk."""
    verified_cache[str(discord_id)] = {
        "roblox_id": str(roblox_id),
        "roblox_username": username,
        "cached_at": datetime.now(timezone.utc).isoformat()
    }
    await _save_cache()
    print(f"[CACHE] Cached {discord_id} → {username}")
    bolt_log.info(f"[CACHE] Cached {discord_id} → {username}")

# ─────────────────────────────────────────────
#  ROBLOX USER INFO  (one call, all data)
# ─────────────────────────────────────────────

async def fetch_roblox_user_info(roblox_id: str) -> dict:
    """
    Single call to users.roblox.com that returns username, display name,
    account age string, and raw created timestamp.
    Returns a dict with keys: name, display_name, account_age, created.
    Falls back gracefully on any error.
    """
    async with ROBLOX_SEMAPHORE:
        try:
            async with aiohttp.ClientSession(timeout=AIOHTTP_TIMEOUT) as session:
                async with session.get(
                    f"https://users.roblox.com/v1/users/{roblox_id}"
                ) as resp:
                    if resp.status != 200:
                        return {}
                    data = await resp.json()
        except Exception as e:
            print(f"[ROBLOX] fetch_roblox_user_info exception: {e}")
            return {}

    created_str = data.get("created", "")
    account_age = "Unknown"
    if created_str:
        try:
            created_dt = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
            delta = datetime.now(timezone.utc) - created_dt
            years = delta.days // 365
            months = (delta.days % 365) // 30
            days = delta.days % 30
            account_age = f"{years} years, {months} months, {days} days"
        except Exception:
            pass

    return {
        "name": data.get("name", ""),
        "display_name": data.get("displayName", ""),
        "account_age": account_age,
        "created": created_str,
    }

async def fetch_roblox_username(roblox_id: str) -> str | None:
    """Lightweight wrapper used by Bloxlink lookup — returns just the name."""
    info = await fetch_roblox_user_info(roblox_id)
    return info.get("name") or None

async def fetch_roblox_previous_usernames(roblox_id: str) -> str:
    async with ROBLOX_SEMAPHORE:
        try:
            async with aiohttp.ClientSession(timeout=AIOHTTP_TIMEOUT) as session:
                async with session.get(
                    f"https://users.roblox.com/v1/users/{roblox_id}"
                    f"/username-history?limit=10"
                ) as resp:
                    if resp.status != 200:
                        return "None"
                    data = await resp.json()
                    names = [e["name"] for e in data.get("data", [])]
                    return ", ".join(names) if names else "None"
        except Exception:
            return "None"

async def fetch_roblox_avatar_url(roblox_id: str) -> str | None:
    async with ROBLOX_SEMAPHORE:
        try:
            async with aiohttp.ClientSession(timeout=AIOHTTP_TIMEOUT) as session:
                async with session.get(
                    "https://thumbnails.roblox.com/v1/users/avatar-headshot"
                    f"?userIds={roblox_id}&size=150x150&format=Png&isCircular=false"
                ) as resp:
                    if resp.status != 200:
                        return None
                    data = await resp.json()
                    entries = data.get("data", [])
                    return entries[0].get("imageUrl") if entries else None
        except Exception:
            return None

# ─────────────────────────────────────────────
#  ROBLOX GROUP HELPERS  (one endpoint, two uses)
# ─────────────────────────────────────────────

async def fetch_group_roles(roblox_id: str) -> list[dict]:
    """
    Returns all groups + ranks for a user.
    Each entry: {name, id, rank}
    Used by both get_all_group_ranks and get_group_rank.
    """
    async with ROBLOX_SEMAPHORE:
        try:
            async with aiohttp.ClientSession(timeout=AIOHTTP_TIMEOUT) as session:
                async with session.get(
                    f"https://groups.roblox.com/v2/users/{roblox_id}/groups/roles"
                ) as resp:
                    if resp.status != 200:
                        return []
                    data = await resp.json()
                    return [
                        {
                            "name": e["group"]["name"],
                            "id": str(e["group"]["id"]),
                            "rank": e["role"]["name"]
                        }
                        for e in data.get("data", [])
                    ]
        except Exception as e:
            print(f"[ROBLOX] fetch_group_roles exception: {e}")
            return []

async def get_all_group_ranks(roblox_id: str) -> list[dict]:
    return await fetch_group_roles(roblox_id)

async def get_group_rank(roblox_id: str, group_id: str) -> str | None:
    """Returns rank name in a specific group, or None."""
    groups = await fetch_group_roles(roblox_id)
    for g in groups:
        if g["id"] == str(group_id):
            return g["rank"]
    return None

# ─────────────────────────────────────────────
#  ROBLOX OPEN CLOUD — ACCEPT + RANK
# ─────────────────────────────────────────────

async def accept_join_request(roblox_id: str, group_id: str) -> bool:
    if not ROBLOX_OPEN_CLOUD:
        print("[ROBLOX] No Open Cloud key.")
        return False
    async with ROBLOX_SEMAPHORE:
        try:
            async with aiohttp.ClientSession(timeout=AIOHTTP_TIMEOUT) as session:
                async with session.get(
                    f"https://apis.roblox.com/cloud/v2/groups/{group_id}/join-requests",
                    headers=ROBLOX_OC_HEADERS(),
                    params={"maxPageSize": 100}
                ) as resp:
                    if resp.status != 200:
                        print(f"[ROBLOX] List join-requests failed: {resp.status}")
                        return False
                    data = await resp.json()

                request_path = None
                for req in data.get("groupJoinRequests", []):
                    if str(roblox_id) in req.get("user", ""):
                        request_path = req.get("path")
                        break

                if not request_path:
                    print(f"[ROBLOX] No pending join request for {roblox_id}")
                    return False

                async with session.post(
                    f"https://apis.roblox.com/cloud/v2/{request_path}:accept",
                    headers=ROBLOX_OC_HEADERS(),
                    json={}
                ) as resp:
                    print(f"[ROBLOX] Accept status: {resp.status}")
                    return resp.status in (200, 204)

        except Exception as e:
            print(f"[ROBLOX] accept_join_request exception: {e}")
            return False

async def set_group_rank(roblox_id: str, group_id: str, rank_name: str) -> bool:
    """
    Sets a Roblox user's rank in a group via Open Cloud.
    Handles paginated role list automatically.
    """
    print(f"[ROBLOX] Ranking {roblox_id} → {rank_name} in {group_id}")
    if not ROBLOX_OPEN_CLOUD:
        print("[ROBLOX] No Open Cloud key.")
        return False

    async with ROBLOX_SEMAPHORE:
        try:
            async with aiohttp.ClientSession(timeout=AIOHTTP_TIMEOUT) as session:

                # STEP 1: collect all roles (paginated)
                all_roles = []
                next_page_token = None
                while True:
                    params = {"maxPageSize": 20}
                    if next_page_token:
                        params["pageToken"] = next_page_token

                    async with session.get(
                        f"https://apis.roblox.com/cloud/v2/groups/{group_id}/roles",
                        headers=ROBLOX_OC_HEADERS(),
                        params=params
                    ) as resp:
                        if resp.status != 200:
                            print(f"[ROBLOX] Get roles failed: {resp.status}")
                            return False
                        roles_data = await resp.json()

                    all_roles.extend(roles_data.get("groupRoles", []))
                    next_page_token = roles_data.get("nextPageToken", "")
                    if not next_page_token:
                        break

                # STEP 2: find target role path
                role_path = None
                for role in all_roles:
                    name = (role.get("displayName") or role.get("name") or "").strip()
                    if name.lower() == rank_name.strip().lower():
                        role_path = role.get("path")
                        break

                if not role_path:
                    print(f"[ROBLOX] Role '{rank_name}' not found in group {group_id}")
                    return False

                print(f"[ROBLOX] Found role path: {role_path}")

                # STEP 3: get membership path
                async with session.get(
                    f"https://apis.roblox.com/cloud/v2/groups/{group_id}/memberships",
                    headers=ROBLOX_OC_HEADERS(),
                    params={"filter": f"user == 'users/{roblox_id}'"}
                ) as resp:
                    if resp.status != 200:
                        print(f"[ROBLOX] Get membership failed: {resp.status}")
                        return False
                    membership_data = await resp.json()

                memberships = membership_data.get("groupMemberships", [])
                if not memberships:
                    print(f"[ROBLOX] No membership found for {roblox_id}")
                    return False

                membership_path = memberships[0]["path"]
                print(f"[ROBLOX] Membership path: {membership_path}")

                # STEP 4: PATCH
                async with session.patch(
                    f"https://apis.roblox.com/cloud/v2/{membership_path}",
                    headers=ROBLOX_OC_HEADERS(),
                    json={"role": role_path}
                ) as resp:
                    text = await resp.text()
                    success = resp.status in (200, 204)
                    print(f"[ROBLOX] Rank PATCH {resp.status}: {text[:120]}")
                    if success:
                        bolt_log.info(
                            f"[ROBLOX] Ranked {roblox_id} → '{rank_name}' in {group_id}"
                        )
                    return success

        except Exception as e:
            print(f"[ROBLOX] set_group_rank exception: {e}")
            return False

# ─────────────────────────────────────────────
#  BLOXLINK
# ─────────────────────────────────────────────

async def get_roblox_user(discord_id: str) -> dict | None:
    """
    Returns {roblox_id, roblox_username} for a Discord user.
    Checks in-memory cache first, then calls Bloxlink.
    Does NOT cache if username lookup fails.
    """
    cached = get_cached_roblox(discord_id)
    if cached:
        print(f"[BLOXLINK] Cache hit for {discord_id}")
        return cached

    if not BLOXLINK_API_KEY:
        print("[BLOXLINK] No API key configured.")
        return None

    url = (
        f"https://api.blox.link/v4/public/guilds/"
        f"{GUILD_ID}/discord-to-roblox/{discord_id}"
    )
    headers = {"Authorization": BLOXLINK_API_KEY}

    try:
        async with aiohttp.ClientSession(timeout=AIOHTTP_TIMEOUT) as session:
            async with session.get(url, headers=headers) as resp:
                print(f"[BLOXLINK] {discord_id} → status {resp.status}")
                if resp.status != 200:
                    return None
                body = await resp.json()
                roblox_id = str(body.get("robloxID") or body.get("roblox_id", ""))
                if not roblox_id:
                    return None
    except Exception as e:
        print(f"[BLOXLINK] Exception: {e}")
        return None

    username = await fetch_roblox_username(roblox_id)
    if not username:
        # users.roblox.com unreachable — return data without caching
        print(f"[BLOXLINK] Could not resolve username for {roblox_id} — not caching")
        return {"roblox_id": roblox_id, "roblox_username": f"Unknown ({roblox_id})"}

    await cache_roblox_user(discord_id, roblox_id, username)
    return {"roblox_id": roblox_id, "roblox_username": username}

# ─────────────────────────────────────────────
#  STARTUP SYNC  (only un-cached members, throttled)
# ─────────────────────────────────────────────

async def sync_verified_users():
    """
    On startup, resolves only members who are NOT already cached.
    Waits 2 seconds between Bloxlink calls to avoid rate-limiting.
    """
    print("[SYNC] Starting verified user sync...")
    guild = bot.get_guild(int(GUILD_ID))
    if not guild:
        print("[SYNC] Guild not found.")
        return

    verified_role = discord.utils.get(guild.roles, name=VERIFIED_ROLE_NAME)
    if not verified_role:
        print("[SYNC] Verified role not found.")
        return

    to_sync = [m for m in verified_role.members if not get_cached_roblox(str(m.id))]
    print(f"[SYNC] {len(to_sync)} uncached members to resolve.")

    synced = failed = 0
    for member in to_sync:
        try:
            roblox = await get_roblox_user(str(member.id))
            if roblox and not roblox["roblox_username"].startswith("Unknown"):
                synced += 1
                print(f"[SYNC] {member} → {roblox['roblox_username']}")
            else:
                failed += 1
                print(f"[SYNC] Failed for {member}")
            await asyncio.sleep(2)   # 2s gap — stays well under Bloxlink rate limit
        except Exception as e:
            failed += 1
            print(f"[SYNC] Error for {member}: {e}")

    print(f"[SYNC] Done. Synced={synced} Failed={failed}")
    bolt_log.info(f"[SYNC] Done. Synced={synced} Failed={failed}")

# ─────────────────────────────────────────────
#  GROUP CATEGORISATION + DISPLAY HELPERS
# ─────────────────────────────────────────────

def categorise_groups(groups: list[dict]) -> tuple[list, list, list]:
    french = []
    coalition = []
    neutral = []
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

def format_field(lines: list[str]) -> str:
    if not lines:
        return "None"
    text = "\n".join(lines)
    return text[:1020] + "\n..." if len(text) > 1020 else text

def has_recruitment_role(interaction: discord.Interaction) -> bool:
    member = interaction.guild.get_member(interaction.user.id)
    return bool(member and any(r.name == RECRUITMENT_ROLE_NAME for r in member.roles))

# ─────────────────────────────────────────────
#  BOT SETUP
# ─────────────────────────────────────────────

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

@tasks.loop(hours=6)
async def periodic_sync():
    await sync_verified_users()

@bot.event
async def on_ready():
    print(f"[BOT] Logged in as {bot.user.name} - {bot.user.id}")
    bolt_log.info(f"[BOT] Logged in as {bot.user.name} - {bot.user.id}")
    print(f"[CACHE] {len(verified_cache)} users loaded from disk.")

    # Sync slash commands to guild instantly
    try:
        guild = discord.Object(id=int(GUILD_ID))
        bot.tree.copy_global_to(guild=guild)
        synced = await bot.tree.sync(guild=guild)
        print(f"[BOT] Synced {len(synced)} command(s) to guild.")
        bolt_log.info(f"[BOT] Synced {len(synced)} command(s).")
    except Exception as e:
        print(f"[BOT] Sync error: {e}")

    # Start background sync (fires immediately, then every 6h)
    if not periodic_sync.is_running():
        periodic_sync.start()

@bot.event
async def on_member_update(before: discord.Member, after: discord.Member):
    """Auto-cache when a member gets the Verified role."""
    verified_role = discord.utils.get(after.guild.roles, name=VERIFIED_ROLE_NAME)
    if not verified_role:
        return
    if verified_role in before.roles or verified_role not in after.roles:
        return

    print(f"[VERIFY] {after} just got Verified — caching...")
    roblox = await get_roblox_user(str(after.id))
    if roblox and not roblox["roblox_username"].startswith("Unknown"):
        print(f"[VERIFY] Cached {after} → {roblox['roblox_username']}")
        bolt_log.info(f"[VERIFY] Auto-cached {after} → {roblox['roblox_username']}")

# ─────────────────────────────────────────────
#  /background-check
# ─────────────────────────────────────────────

@bot.tree.command(
    name="background-check",
    description="Run a background check on one or more verified users."
)
@app_commands.describe(users="Mention one or more users to check")
async def background_check(interaction: discord.Interaction, users: str):
    if not has_recruitment_role(interaction):
        await interaction.response.send_message(
            f"❌ You need the **{RECRUITMENT_ROLE_NAME}** role to use this command.",
            ephemeral=True
        )
        return

    await interaction.response.defer()

    mentioned_ids = MENTION_PATTERN.findall(users)
    if not mentioned_ids:
        await interaction.followup.send("Please mention at least one user.")
        return

    for discord_id in mentioned_ids:
        try:
            member = interaction.guild.get_member(int(discord_id))
            roblox = await get_roblox_user(discord_id)

            if not roblox:
                await interaction.followup.send(
                    f"❌ <@{discord_id}> is not verified with Bloxlink."
                )
                continue

            roblox_id = roblox["roblox_id"]
            roblox_username = roblox["roblox_username"]

            # Fire all lookups concurrently — one users.roblox.com call covers
            # username + age, the rest are separate endpoints
            user_info, prev_names, all_groups, avatar_url = await asyncio.gather(
                fetch_roblox_user_info(roblox_id),
                fetch_roblox_previous_usernames(roblox_id),
                get_all_group_ranks(roblox_id),
                fetch_roblox_avatar_url(roblox_id),
                return_exceptions=True
            )
            if isinstance(user_info, Exception): user_info   = {}
            if isinstance(prev_names, Exception): prev_names  = "None"
            if isinstance(all_groups, Exception): all_groups  = []
            if isinstance(avatar_url, Exception): avatar_url  = None

            account_age = user_info.get("account_age", "Unknown")
            roblox_username = user_info.get("name") or roblox_username
            groups = all_groups if isinstance(all_groups, list) else []

            # Specific rank lookups
            french_rank = cav_rank = "Not a member"
            for g in groups:
                if g["id"] == str(FRENCH_MAIN_GROUP_ID):
                    french_rank = g["rank"]
                if g["id"] == str(CAV_GROUP_ID):
                    cav_rank = g["rank"]

            french, coalition, neutral = categorise_groups(groups)

            discord_display = f"<@{discord_id}>" if member else f"Unknown ({discord_id})"
            discord_nick = (member.nick or member.name) if member else roblox_username

            embed = discord.Embed(
                title="Background Check Results",
                color=discord.Color.dark_blue()
            )
            if avatar_url:
                embed.set_thumbnail(url=avatar_url)

            embed.add_field(
                name="Account",
                value=f"{discord_display}, {roblox_username}",
                inline=False
            )
            embed.add_field(name="Account Age",      value=account_age,  inline=True)
            embed.add_field(name="Prev. Usernames",  value=prev_names,   inline=True)
            embed.add_field(
                name="French Rankings",
                value=(
                    f"Empire Français — {french_rank}\n"
                    f"Corps de Cavalerie — {cav_rank}"
                ),
                inline=False
            )
            embed.add_field(
                name=f"🇫🇷 French Empire & Clients ({len(french)})",
                value=format_field(french),
                inline=False
            )
            embed.add_field(
                name=f"⚔️ Coalition Powers ({len(coalition)})",
                value=format_field(coalition),
                inline=False
            )
            embed.add_field(
                name=f"🌐 Neutral Powers ({len(neutral)})",
                value=format_field(neutral),
                inline=False
            )
            embed.set_footer(
                text=f"Roblox ID: {roblox_id} • roblox.com/users/{roblox_id}/profile"
            )

            await interaction.followup.send(embed=embed)
            bolt_log.info(
                f"[BG CHECK] {roblox_username} ({roblox_id}) "
                f"checked by {interaction.user}"
            )

        except Exception as e:
            await interaction.followup.send(
                f"❌ Error checking <@{discord_id}>: {type(e).__name__}: {e}"
            )
            bolt_log.error(f"[BG CHECK] Error for {discord_id}: {e}")
            print(f"[BG CHECK] Error: {e}")

# ─────────────────────────────────────────────
#  /induct
# ─────────────────────────────────────────────

INDUCT_ROLES     = ["BRIGADE KELLERMANN", "26ème Régiment de Chasseurs à Cheval", "Corps de Cavalerie Impériale", "Cavalier"]
REMOVE_ON_INDUCT = ["Garde Nationale de Cavalerie", "Guest", "Citoyen", "Soldat", "Caporal", "Caporal Fourrier"]
CAV_INDUCT_RANK  = "BRIGADE KELLERMANN"

@bot.tree.command(name="induct", description="Induct one or more recruits into the regiment.")
@app_commands.describe(users="Mention one or more users to induct")
async def induct(interaction: discord.Interaction, users: str):
    if not has_recruitment_role(interaction):
        await interaction.response.send_message(
            f"❌ You need the **{RECRUITMENT_ROLE_NAME}** role to use this command.",
            ephemeral=True
        )
        return

    await interaction.response.defer()

    mentioned_ids = MENTION_PATTERN.findall(users)
    if not mentioned_ids:
        await interaction.followup.send("Please mention at least one user.")
        return

    for discord_id in mentioned_ids:
        lines = ["**Induct Results**"]
        try:
            # Resolve member
            member = interaction.guild.get_member(int(discord_id))
            if not member:
                member = await asyncio.wait_for(
                    interaction.guild.fetch_member(int(discord_id)), timeout=10
                )
            lines.append(f"<@{discord_id}> — {member.display_name}")

            # Bloxlink lookup
            roblox = await get_roblox_user(discord_id)
            if not roblox:
                lines.append("❌ Not verified with Bloxlink. Aborted.")
                await interaction.followup.send("\n".join(lines))
                continue

            roblox_id = roblox["roblox_id"]
            roblox_username = roblox["roblox_username"]

            # Check / accept into Cav group
            cav_rank = await get_group_rank(roblox_id, CAV_GROUP_ID)
            if not cav_rank or cav_rank.lower() == "guest":
                accepted = await asyncio.wait_for(
                    accept_join_request(roblox_id, CAV_GROUP_ID), timeout=15
                )
                if accepted:
                    lines.append("✅ Accepted into Corps de Cavalerie Impériale.")
                    cav_rank = None   # reset so rank is set below
                else:
                    lines.append(
                        "❌ Not in Cav group and no pending join request. "
                        "Ask them to send a join request first. Aborted."
                    )
                    await interaction.followup.send("\n".join(lines))
                    continue
            else:
                lines.append(f"⚠️ Already in Cav group as {cav_rank}.")

            # Set Cav rank
            if cav_rank and cav_rank.lower() == CAV_INDUCT_RANK.lower():
                lines.append(f"⚠️ Already ranked {CAV_INDUCT_RANK}. Skipping.")
            else:
                try:
                    ranked = await asyncio.wait_for(
                        set_group_rank(roblox_id, CAV_GROUP_ID, CAV_INDUCT_RANK),
                        timeout=30
                    )
                    lines.append(
                        f"✅ Ranked to {CAV_INDUCT_RANK}."
                        if ranked else
                        "❌ Failed to set Roblox rank — set manually."
                    )
                except asyncio.TimeoutError:
                    lines.append("⚠️ Roblox rank request timed out — set manually.")

            guild = interaction.guild

            # Strip old roles
            stripped = []
            for rn in REMOVE_ON_INDUCT:
                r = discord.utils.get(guild.roles, name=rn)
                if r and r in member.roles:
                    await member.remove_roles(r)
                    stripped.append(rn)
            lines.append(
                f"✅ Stripped: {', '.join(stripped)}"
                if stripped else "⚠️ No roles to strip."
            )

            # Add regiment roles
            added = []
            missing = []
            for rn in INDUCT_ROLES:
                r = discord.utils.get(guild.roles, name=rn)
                if r:
                    if r not in member.roles:
                        await member.add_roles(r)
                    added.append(rn)
                else:
                    missing.append(rn)
            if added:
                lines.append(f"✅ Added: {', '.join(added)}")
            if missing:
                lines.append(f"❌ Not found in Discord: {', '.join(missing)}")

            # Nickname
            new_nick = f"[26e] {roblox_username}"
            try:
                await member.edit(nick=new_nick)
                lines.append(f"✅ Nickname → {new_nick}")
            except discord.Forbidden:
                lines.append("⚠️ Cannot change nickname (bot role too low or owner).")
            except discord.HTTPException as e:
                lines.append(f"⚠️ Nickname failed: {e.text}")

            bolt_log.info(f"[INDUCT] {roblox_username} inducted by {interaction.user}")

        except asyncio.TimeoutError:
            lines.append("❌ A request timed out.")
            bolt_log.error(f"[INDUCT] Timeout for {discord_id}")
        except Exception as e:
            lines.append(f"❌ Unexpected error: {type(e).__name__}: {e}")
            bolt_log.error(f"[INDUCT] Error for {discord_id}: {e}")
            print(f"[INDUCT] Error: {e}")

        await interaction.followup.send("\n".join(lines))

# ─────────────────────────────────────────────
#  RUN
# ─────────────────────────────────────────────

bot.run(token, log_handler=handler, log_level=logging.DEBUG)