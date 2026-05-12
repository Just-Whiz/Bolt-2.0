# Bot name: Bolt 2.0
# Author: orbandit (@just_whiz on Discord)
# Date: 2026-05-10
# Version: 0.7.0

import discord
from discord import app_commands
from discord.ext import commands
import logging
import os
import re
import json
import aiohttp
import asyncio
from dotenv import load_dotenv
from datetime import timezone, datetime

load_dotenv()

token = os.getenv("DISCORD_TOKEN")
BLOXLINK_API_KEY = os.getenv("BLOXLINK_API_KEY")
GUILD_ID = os.getenv("GUILD_ID")
ROBLOX_OPEN_CLOUD = os.getenv("ROBLOX_OPEN_CLOUD_KEY")
ROBLOX_OC_HEADERS = lambda: {
    "x-api-key": ROBLOX_OPEN_CLOUD,
    "Content-Type": "application/json"
}

# The two groups we specifically surface at the top of every check
FRENCH_MAIN_GROUP_ID = os.getenv("FRENCH_GROUP_ID")
CAV_GROUP_ID = os.getenv("CAV_GROUP_ID")

VERIFIED_USERS_PATH = "verified_users.json"
AIOHTTP_TIMEOUT = aiohttp.ClientTimeout(total=10)
RECRUITMENT_ROLE_NAME = "Recruitment Team"


# ─────────────────────────────────────────────
#  GROUP ID → DISPLAY NAME MAPS
#  Only groups in these maps are shown.
#  Anything else is silently ignored.
# ─────────────────────────────────────────────

FRENCH_GROUP_IDS = {
    # ── France ──────────────────────────────
    "5610765": "Empire Français",
    "6057395": "Garde Impériale",
    "6057318": "Premier Corps",
    "6057327": "Deuxième Corps",
    "6057333": "Troisième Corps",
    "7840844": "Quatrième Corps",
    "9976984": "Cinquième Corps",
    "13206132":"Neuvième Corps",
    "13284835": "État-Major Impériale",
    "195387641": "Corps de Cavalerie Impériale",
    # ── Naples ──────────────────────────────
    "6764583": "Esercito Napoletano",
    "7135170": "Regno di Napoli",
    "9746123": "Prima Divisione",
    "10514799": "Seconda Divisione",
    "32627531": "Terza Divisione",
    "1112910179":"Quatra Divisione",
    "9067214": "Marina Napoletana",
    "10349483": "Guardia Reale",
    "33741408": "Corpo d'Armata",
    "477750899": "Reggimento d'Artiglieria di Marina",
    # ── Warsaw / Poland ─────────────────────
    "4614276": "Woysko Xięstwa Warszawskiego",
    "394072781": "Sztab Generalny Woyska Polskiego",
    "796097059": "Brygada Gwardii Narodowej",
    "596867575": "Xięstwo Litewskie",
    "9921948": "Pierwsza Dywizya",
    "33709393": "Drugi Dywizja",
    "9921939": "Korpus Kawalerii",
}

COALITION_GROUP_IDS = {
    # ── Austria ─────────────────────────────
    "16702357": "Kaisertum Österreich",
    "17034669": "Grenadier Korps",
    "16965984": "Königliche Ungarn",
    "33606731": "Hof von Österreich",
    "14706502": "Erste Korps",
    "17248191": "Zweite Korps",
    "33437234": "Drittes Korps",
    "33727999": "Viertes Korps",
    "35915613": "Fünftes Korps",
    "856818677":"Fünftes Korps Recruitment",
    "33129015": "Kavallerie Korps",
    "33679754": "Ingenieur Korps",
    "35755856": "Küchenbrigade",
    # ── Russia ──────────────────────────────
    "7528791": "Imperatorskaya Armiya",
    "10621031": "Imperskoy Gvardii Korpus",
    "34279561": "Grenaderskiy Korpus",
    "34279574": "Severnaya Armiya",
    "32842545": "Yuzhnaya Armiya",
    "8254296": "Zapadnaya Armiya",
    "950745879": "Krymskaya Armiya",
    "35917740": "Vostochnaya Armiya",
    # ── Britain ─────────────────────────────
    "4000196": "British Army",
    "9686866": "First Division",
    "9686840": "Fifth Brigade",
    "12691944": "Second Division",
    "35746582": "Board of Ordnance (INVICTORS)",
    "32033796": "Braunschweig-Oels-Linien-Bataillon",
    "35746578": "Board of Ordnance (PRINCIPES)",
    "34209218": "Schweizer Adelsgeschlecht",
    "7907149": "Household Brigade",
    "1049512588":"Foot Guards Grenadiers",
    # ── Prussia ─────────────────────────────
    "35965347": "Preußische Armee",
    "35986490": "Königliches Gardekorps",
    "35986478": "Erstes Armeekorps",
    # ── Spain ───────────────────────────────
    "11639829": "Ejército de España",
    "223078637": "Ejército Real de Nueva España",
    "32374377": "Ejército de Aragón",
    "34056502": "Ejército de Galicia",
    # ── Andour ──────────────────────────────
    "5531725": "Andouran Empire",
    "432773563": "Fuirst Keisariks Armcorps",
    "17375317": "Anders Keisariks Armcorps",
    "35333449": "Keisariks Armcorps Grenader",
    "16125179": "Andouran Imperial Guard",
    "8559975": "Kait",
    "8410719": "Order of the Gold Griffin",
    "35504152": "Kurohana",
    "6331920": "Order of the White Tiger",
    # ── Portugal ────────────────────────────
    "34011906": "Exército de Portugal",
    "11392538": "Real Armada Portuguesa",
    "34460157": "Brigada Real da Marinha",
    "35181462": "Corpo Real de Cavalaria",
    "35613090": "Guarda Real da Polícia de Lisboa",
    "35001756":  "Corte Real Portuguesa",
}

NEUTRAL_GROUP_IDS = {
    # ── United States ────────────────────────
    "5826061": "United States Army",
    "10822431": "US Marine Corps",
    "175161616": "General Society of the War of 1812",
    "61813207": "U.S. Artillery Corps",
    "35683824": "U.S. Ranger Regiment",
    "35281366": "United States Cavalry Detachment",
    "17394192": "Brown's First Brigade",
    "33704866": "Ripley's 2nd Brigade",
    # ── Ottomans ────────────────────────────
    "32950259": "Devlet-i Aliyye-i Osmâniyye",
    "36056277": "Kapıkulu Ocağı",
    "17018827": "Nizâm-ı Cedîd Ordu",
}

# Combined set for fast membership lookup
ALL_KNOWN_IDS = set(FRENCH_GROUP_IDS) | set(COALITION_GROUP_IDS) | set(NEUTRAL_GROUP_IDS)

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
#  JSON CACHE
# ─────────────────────────────────────────────

def load_verified_users() -> dict:
    if os.path.exists(VERIFIED_USERS_PATH):
        with open(VERIFIED_USERS_PATH, 'r') as f:
            return json.load(f)
    return {}

def get_cached_roblox(discord_id: str) -> dict | None:
    return load_verified_users().get(str(discord_id))

def cache_roblox_user(discord_id: str, roblox_id: str, roblox_username: str):
    users = load_verified_users()
    users[str(discord_id)] = {
        'roblox_id': roblox_id,
        'roblox_username': roblox_username,
        'cached_at': datetime.now(timezone.utc).isoformat()
    }
    with open(VERIFIED_USERS_PATH, 'w') as f:
        json.dump(users, f, indent=2)
    bolt_log.info(f"[CACHE] Cached {discord_id} → {roblox_username} ({roblox_id})")

# ─────────────────────────────────────────────
#  BLOXLINK
# ─────────────────────────────────────────────

async def get_roblox_user(discord_id: str) -> dict | None:
    cached = get_cached_roblox(discord_id)
    if cached:
        bolt_log.info(f"[BLOXLINK] Cache hit for {discord_id}")
        return cached

    if not BLOXLINK_API_KEY:
        bolt_log.error("[BLOXLINK] No API key configured.")
        return None

    url = f"https://api.blox.link/v4/public/guilds/{GUILD_ID}/discord-to-roblox/{discord_id}"
    headers = {'Authorization': BLOXLINK_API_KEY}
    print(f"[BLOXLINK] Calling: {url}")

    try:
        async with aiohttp.ClientSession(timeout=AIOHTTP_TIMEOUT) as session:
            async with session.get(url, headers=headers) as resp:
                print(f"[BLOXLINK] Status: {resp.status}")
                body = await resp.json()
                print(f"[BLOXLINK] Body: {body}")
                if resp.status != 200:
                    return None
                roblox_id = str(body.get('robloxID') or body.get('roblox_id', ''))
                if not roblox_id:
                    return None
    except Exception as e:
        print(f"[BLOXLINK] Exception: {e}")
        return None

    username = await get_roblox_username(roblox_id)
    if username:
        cache_roblox_user(discord_id, roblox_id, username)
        return {'roblox_id': roblox_id, 'roblox_username': username}
    return None

# ─────────────────────────────────────────────
#  ROBLOX API HELPERS
# ─────────────────────────────────────────────

async def get_roblox_username(roblox_id: str) -> str | None:
    try:
        async with aiohttp.ClientSession(timeout=AIOHTTP_TIMEOUT) as session:
            async with session.get(
                f"https://users.roblox.com/v1/users/{roblox_id}"
            ) as resp:
                if resp.status != 200:
                    return None
                return (await resp.json()).get('name')
    except Exception:
        return None

async def get_roblox_account_age(roblox_id: str) -> str:
    try:
        async with aiohttp.ClientSession(timeout=AIOHTTP_TIMEOUT) as session:
            async with session.get(
                f"https://users.roblox.com/v1/users/{roblox_id}"
            ) as resp:
                if resp.status != 200:
                    return 'Unknown'
                data = await resp.json()
                created = data.get('created', '')
                if not created:
                    return 'Unknown'
                created_dt = datetime.fromisoformat(created.replace('Z', '+00:00'))
                delta = datetime.now(timezone.utc) - created_dt
                years = delta.days // 365
                months = (delta.days % 365) // 30
                days = delta.days % 30
                return f"{years} years, {months} months, {days} days"
    except Exception:
        return 'Unknown'

async def get_roblox_previous_usernames(roblox_id: str) -> str:
    try:
        async with aiohttp.ClientSession(timeout=AIOHTTP_TIMEOUT) as session:
            async with session.get(
                f"https://users.roblox.com/v1/users/{roblox_id}/username-history?limit=10"
            ) as resp:
                if resp.status != 200:
                    return 'None'
                data = await resp.json()
                names = [e['name'] for e in data.get('data', [])]
                return ', '.join(names) if names else 'None'
    except Exception:
        return 'None'

# This specific async function returns the all the groups & the ranks that the user is in (for validating that a potential recruit has left all valid groups)
async def get_all_group_ranks(roblox_id: str) -> list[dict]:
    """Returns all Roblox groups the user is in."""
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
                        'name': e['group']['name'],
                        'id': str(e['group']['id']),
                        'rank': e['role']['name']
                    }
                    for e in data.get('data', [])
                ]
    except Exception:
        return []
    
# This function is different than the one above; it insteads checks to see if a user is in a SPECIFIC group rather than checking all groups (for auto-accepting users into the Roblox Group)
async def get_group_rank(roblox_id: str, group_id: str) -> str | None:
    """Returns rank name of a user in a specific group, or None if not a member."""
    try:
        async with aiohttp.ClientSession(timeout=AIOHTTP_TIMEOUT) as session:
            async with session.get(
                f"https://groups.roblox.com/v2/users/{roblox_id}/groups/roles"
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                for entry in data.get('data', []):
                    if str(entry['group']['id']) == str(group_id):
                        return entry['role']['name']
        return None
    except Exception:
        return None
    
async def get_roblox_avatar_url(roblox_id: str) -> str | None:
    """Returns a headshot thumbnail URL for a Roblox user."""
    try:
        async with aiohttp.ClientSession(timeout=AIOHTTP_TIMEOUT) as session:
            async with session.get(
                f"https://thumbnails.roblox.com/v1/users/avatar-headshot"
                f"?userIds={roblox_id}&size=150x150&format=Png&isCircular=false"
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                entries = data.get('data', [])
                if entries:
                    return entries[0].get('imageUrl')
    except Exception:
        return None

# ─────────────────────────────────────────────
#  CATEGORISATION
# ─────────────────────────────────────────────

def categorise_groups(all_groups: list[dict]) -> tuple[list, list, list]:
    """
    Returns (french_lines, coalition_lines, neutral_lines).
    Groups not in any known map are silently dropped.
    """
    french = []
    coalition = []
    neutral = []

    for g in all_groups:
        gid = g['id']
        rank = g['rank']

        if gid in FRENCH_GROUP_IDS:
            french.append(f"**{FRENCH_GROUP_IDS[gid]}** — {rank}")
        elif gid in COALITION_GROUP_IDS:
            coalition.append(f"**{COALITION_GROUP_IDS[gid]}** — {rank}")
        elif gid in NEUTRAL_GROUP_IDS:
            neutral.append(f"**{NEUTRAL_GROUP_IDS[gid]}** — {rank}")
        # anything else: silently ignored

    return french, coalition, neutral

def format_field(lines: list[str]) -> str:
    if not lines:
        return 'None'
    text = '\n'.join(lines)
    return text[:1020] + '\n...' if len(text) > 1020 else text

# ─────────────────────────────────────────────
#  Accept join request w/ Roblox Open Cloud API
# ─────────────────────────────────────────────

async def accept_join_request(roblox_id: str, group_id: str) -> bool:
    """Lists pending join requests and accepts the one matching roblox_id."""
    if not ROBLOX_OPEN_CLOUD:
        print("[ROBLOX] No Open Cloud key configured.")
        return False
    try:
        async with aiohttp.ClientSession(timeout=AIOHTTP_TIMEOUT) as session:
            async with session.get(
                f"https://apis.roblox.com/cloud/v2/groups/{group_id}/join-requests",
                headers=ROBLOX_OC_HEADERS(),
                params={'maxPageSize': 100}
            ) as resp:
                if resp.status != 200:
                    print(f"[ROBLOX] List join requests failed: {resp.status}")
                    return False
                data = await resp.json()
    except Exception as e:
        print(f"[ROBLOX] Exception listing join requests: {e}")
        return False

    request_path = None
    for request in data.get('groupJoinRequests', []):
        if str(roblox_id) in request.get('user', ''):
            request_path = request.get('path')
            break

    if not request_path:
        print(f"[ROBLOX] No pending join request for {roblox_id}")
        return False

    try:
        async with aiohttp.ClientSession(timeout=AIOHTTP_TIMEOUT) as session:
            async with session.post(
                f"https://apis.roblox.com/cloud/v2/{request_path}:accept",
                headers=ROBLOX_OC_HEADERS(),
                json={}
            ) as resp:
                print(f"[ROBLOX] Accept status: {resp.status}")
                return resp.status in (200, 204)
    except Exception as e:
        print(f"[ROBLOX] Exception accepting join request: {e}")
        return False

# ─────────────────────────────────────────────
#  Set Rank in Roblox Group w/ Open Cloud API
# ─────────────────────────────────────────────

async def set_group_rank(roblox_id: str, group_id: str, rank_name: str) -> bool:
    """
    Sets a Roblox user's role in a group using Open Cloud.
    Reusable for inductions, promotions, demotions, etc.
    """

    print(f"[ROBLOX] Ranking {roblox_id} -> {rank_name} in {group_id}")
    if not ROBLOX_OPEN_CLOUD:
        print("[ROBLOX] No Open Cloud key configured.")
        return False
    try:
        async with aiohttp.ClientSession(timeout=AIOHTTP_TIMEOUT) as session:
            # STEP 1: GET ALL GROUP ROLES
            async with session.get(
                f"https://apis.roblox.com/cloud/v2/groups/{group_id}/roles",
                headers=ROBLOX_OC_HEADERS()
            ) as resp:

                body = await resp.text()
                print(f"[ROBLOX] Roles response ({resp.status}): {body}")

                if resp.status != 200:
                    return False
                roles_data = json.loads(body)

            # STEP 2: FIND TARGET ROLE
            role_path = None
            for role in roles_data.get("groupRoles", []):
                display_name = role.get("displayName", "").strip().lower()
                if display_name == rank_name.strip().lower():
                    role_path = role.get("path")
                    break
            if not role_path:
                print(f"[ROBLOX] Role '{rank_name}' not found.")
                return False
            print(f"[ROBLOX] Found role path: {role_path}")
            # STEP 3: GET MEMBERSHIP
            async with session.get(
                f"https://apis.roblox.com/cloud/v2/groups/{group_id}/memberships",
                headers=ROBLOX_OC_HEADERS(),
                params={
                    "filter": f"user == 'users/{roblox_id}'"
                }
            ) as resp:

                body = await resp.text()
                print(f"[ROBLOX] Membership response ({resp.status}): {body}")
                if resp.status != 200:
                    return False
                membership_data = json.loads(body)
            memberships = membership_data.get("groupMemberships", [])
            if not memberships:
                print(f"[ROBLOX] No membership found.")
                return False
            membership_path = memberships[0]["path"]
            print(f"[ROBLOX] Membership path: {membership_path}")
            # STEP 4: PATCH MEMBERSHIP ROLE
            payload = {
                "role": {
                    "path": role_path
                }
            }
            async with session.patch(
                f"https://apis.roblox.com/cloud/v2/{membership_path}",
                headers=ROBLOX_OC_HEADERS(),
                json=payload
            ) as resp:
                response_text = await resp.text()
                print(
                    f"[ROBLOX] Rank PATCH response "
                    f"({resp.status}): {response_text}"
                )
                success = resp.status in (200, 204)

                if success:
                    bolt_log.info(
                        f"[ROBLOX] Ranked {roblox_id} "
                        f"to '{rank_name}' in group {group_id}"
                    )
                return success

    except Exception as e:
        print(f"[ROBLOX] Exception in set_group_rank: {e}")
        return False

# ─────────────────────────────────────────────
#  ROLE/PERMISSION CHECK
# ─────────────────────────────────────────────

def has_recruitment_role(interaction: discord.Interaction) -> bool:
    member = interaction.guild.get_member(interaction.user.id)
    if not member:
        return False
    return any(r.name == RECRUITMENT_ROLE_NAME for r in member.roles)

# ─────────────────────────────────────────────
#  BOT SETUP
# ─────────────────────────────────────────────

intents                 = discord.Intents.default()
intents.message_content = True
intents.members         = True

bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    print(f'[BOT] Logged in as {bot.user.name} - {bot.user.id}')
    bolt_log.info(f"[BOT] Logged in as {bot.user.name} - {bot.user.id}")
    try:
        guild = discord.Object(id=int(GUILD_ID))

        # ONE-TIME CLEANUP — remove after running once
        #bot.tree.clear_commands(guild=None)       # clears global commands
        #await bot.tree.sync()                     # pushes the empty list globally
        # END CLEANUP

        bot.tree.copy_global_to(guild=guild)
        synced = await bot.tree.sync(guild=guild)
        print(f"[BOT] Synced {len(synced)} slash command(s) to guild.")
        bolt_log.info(f"[BOT] Synced {len(synced)} slash command(s) to guild.")
    except Exception as e:
        print(f"[BOT] Sync error: {e}")
        bolt_log.error(f"[BOT] Sync error: {e}")

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
                    f"❌ <@{discord_id}> is not verified with Bloxlink or could not be found."
                )
                continue

            roblox_id       = roblox['roblox_id']
            roblox_username = roblox['roblox_username']

            # Fire all Roblox lookups concurrently
            account_age, prev_names, all_groups, avatar_url = await asyncio.gather(
                get_roblox_account_age(roblox_id),
                get_roblox_previous_usernames(roblox_id),
                get_all_group_ranks(roblox_id),
                get_roblox_avatar_url(roblox_id),
                return_exceptions=True
            )
            if isinstance(account_age, Exception): account_age = 'Unknown'
            if isinstance(prev_names, Exception): prev_names = 'None'
            if isinstance(all_groups, Exception): all_groups = []
            if isinstance(avatar_url, Exception): avatar_url = None

            groups = all_groups if isinstance(all_groups, list) else []

            # ── Specific group status ──────────────────
            french_rank = 'Not a member'
            cav_rank = 'Not a member'
            for g in groups:
                if g['id'] == FRENCH_MAIN_GROUP_ID:
                    french_rank = g['rank']
                if g['id'] == CAV_GROUP_ID:
                    cav_rank = g['rank']

            # ── Categorise all groups ──────────────────
            french, coalition, neutral = categorise_groups(groups)

            # ── Build embed ────────────────────────────
            discord_display = f"<@{discord_id}>" if member else f"Unknown ({discord_id})"
            discord_nick = (member.nick or member.name) if member else roblox_username

            embed = discord.Embed(
                title="Background Check Results",
                color=discord.Color.dark_blue()
            )

            #Identity
            if avatar_url:
                embed.set_thumbnail(url=avatar_url)
            embed.add_field(name="Discord", value=discord_display, inline=True)
            embed.add_field(name="Nickname", value=discord_nick, inline=True)
            embed.add_field(name="Roblox Username", value=roblox_username, inline=True)

            # Account info
            embed.add_field(name="Account Age", value=account_age,  inline=True)
            embed.add_field(name="Previous Usernames", value=prev_names, inline=True)

            # Key group ranks (always shown)
            embed.add_field(name="\u200b", value="\u200b", inline=False)  # spacer
            embed.add_field(name="Empire Français Rank", value=french_rank, inline=True)
            embed.add_field(name="Corps de Cavalerie Rank", value=cav_rank,    inline=True)

            # Nation memberships
            embed.add_field(name="\u200b", value="\u200b", inline=False)  # spacer
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

            embed.set_footer(text=f"Roblox ID: {roblox_id}")

            await interaction.followup.send(embed=embed)
            bolt_log.info(
                f"[BG CHECK] {roblox_username} ({roblox_id}) "
                f"checked by {interaction.user} - "
                f"F:{len(french)} C:{len(coalition)} N:{len(neutral)}"
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

INDUCT_ROLES    = ['BRIGADE KELLERMANN', '26ème Régiment de Chasseurs à Cheval', 'Corps de Cavalerie Impériale', 'Cavalier']
REMOVE_ON_INDUCT = ['Garde Nationale de Cavalerie', 'Guest' 'Citoyen', 'Soldat', 'Caporal', 'Caporal Fourrier']
CAV_INDUCT_RANK = 'BRIGADE KELLERMANN'   # exact Roblox rank name in the Cav group

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
            # ── Resolve Discord member ─────────────────
            member = interaction.guild.get_member(int(discord_id))
            if not member:
                member = await asyncio.wait_for(
                    interaction.guild.fetch_member(int(discord_id)), timeout=10
                )
            lines.append(f"<@{discord_id}> — {member.display_name}")

            # ── Bloxlink lookup ────────────────────────
            roblox = await asyncio.wait_for(get_roblox_user(discord_id), timeout=10)
            if not roblox:
                lines.append("❌ Not verified with Bloxlink. Aborted.")
                await interaction.followup.send('\n'.join(lines))
                continue

            roblox_id = roblox['roblox_id']
            roblox_username = roblox['roblox_username']

            # ── Cav group: accept if pending, then rank ─
            cav_rank = await asyncio.wait_for(
                get_group_rank(roblox_id, CAV_GROUP_ID), timeout=10
            )

            if not cav_rank or cav_rank.lower() == 'guest':
                # Not in group yet — try to accept a pending join request
                accepted = await asyncio.wait_for(
                    accept_join_request(roblox_id, CAV_GROUP_ID), timeout=15
                )
                if accepted:
                    lines.append("✅ Accepted into Corps de Cavalerie Impériale.")
                else:
                    lines.append(
                        "❌ Not in Cav group and no pending join request found. "
                        "Ask them to send a join request first. Aborted."
                    )
                    await interaction.followup.send('\n'.join(lines))
                    continue
            else:
                lines.append(f"⚠️ Already in Cav group as {cav_rank}.")

            # ── Set Cav rank → BRIGADE KELLERMAN ───────
            if cav_rank and cav_rank.lower() == CAV_INDUCT_RANK.lower():
                lines.append(f"⚠️ Already ranked {CAV_INDUCT_RANK} in Roblox. Skipping.")
            else:
                try:
                    ranked = await asyncio.wait_for(
                        set_group_rank(roblox_id, CAV_GROUP_ID, CAV_INDUCT_RANK),
                        timeout=15
                    )
                    lines.append(
                        f"✅ Ranked to {CAV_INDUCT_RANK} in Corps de Cavalerie."
                        if ranked else
                        "❌ Failed to set Roblox rank. Set manually."
                    )
                except asyncio.TimeoutError:
                    lines.append("⚠️ Roblox rank request timed out.")

            guild = interaction.guild

            # ── Strip old roles ────────────────────────
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

            # ── Add regiment roles ─────────────────────
            added = []
            for rn in INDUCT_ROLES:
                r = discord.utils.get(guild.roles, name=rn)
                if r:
                    if r not in member.roles:
                        await member.add_roles(r)
                    added.append(rn)
                else:
                    lines.append(f"❌ Role not found in Discord: '{rn}'")
            if added:
                lines.append(f"✅ Added: {', '.join(added)}")

            # ── Update nickname ────────────────────────
            new_nick = f"[26e] {roblox_username}"
            try:
                await member.edit(nick=new_nick)
                lines.append(f"✅ Nickname set to {new_nick}.")
            except discord.Forbidden:
                lines.append("⚠️ Could not update nickname (missing permissions).")

            bolt_log.info(f"[INDUCT] {roblox_username} inducted by {interaction.user}")

        except asyncio.TimeoutError:
            lines.append("❌ A request timed out.")
            bolt_log.error(f"[INDUCT] Timeout for {discord_id}")
        except Exception as e:
            lines.append(f"❌ Unexpected error: {type(e).__name__}: {e}")
            bolt_log.error(f"[INDUCT] Error for {discord_id}: {e}")
            print(f"[INDUCT] Error: {e}")

        await interaction.followup.send('\n'.join(lines))

# ─────────────────────────────────────────────
#  RUN
# ─────────────────────────────────────────────

bot.run(token, log_handler=handler, log_level=logging.DEBUG)