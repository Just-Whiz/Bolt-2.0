# Bot name: Bolt 2.0
# Author: orbandit (@just_whiz on Discord)
# Date: 2026-05-08
# Description: Discord message logger that logs to Google Sheets
# Version: 0.3.0
# Note: using pythoncore 3.14-64. Run requirements.txt using pip to install all listed dependencies in this file.

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
import gspread
from google.oauth2.service_account import Credentials

load_dotenv()

token = os.getenv("DISCORD_TOKEN")
CREDENTIALS_PATH = os.getenv("GOOGLE_CREDENTIALS_PATH", "credentials.json")
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
LOG_SHEET_NAME = os.getenv("LOG_SHEET_NAME", "Garde Nationale Test Example")
BLOXLINK_API_KEY = os.getenv("BLOXLINK_API_KEY")
ROBLOX_OPEN_CLOUD = os.getenv("ROBLOX_OPEN_CLOUD_KEY")

print(f"[CONFIG] Open Cloud key loaded: {bool(ROBLOX_OPEN_CLOUD)} | Value start: {str(ROBLOX_OPEN_CLOUD)[:8] if ROBLOX_OPEN_CLOUD else 'NONE'}")

ROBLOX_GROUP_ID = os.getenv("ROBLOX_GROUP_ID", "772916015")
GUILD_ID = os.getenv("GUILD_ID")

VERIFIED_USERS_PATH = "verified_users.json"
AIOHTTP_TIMEOUT = aiohttp.ClientTimeout(total=10)

# Logging setup
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

for lib in ("discord", "discord.http", "discord.gateway", "gspread", "google"):
    lib_logger = logging.getLogger(lib)
    lib_logger.setLevel(logging.DEBUG)
    lib_logger.addHandler(file_handler)
    lib_logger.propagate = False # Ensures a line won't be logged twice by ancestor handlers

handler = file_handler

# Role setup 
# Roles for Roblox rank progression (lowest to highest)
RANK_PROGRESSION = [
    "Guest",
    "Citoyen",
    "Conscrit",
    "Soldat", 
    "Caporal",
    "Caporal Fourrier"
    "Admin",
    "Owner"
]

# Discord role placeholders - to be swapped for exact role names
DISCORD_RANK_ROLES = {
    "Conscrit": "Conscrit",
    "Soldat": "Soldat",
    "Caporal": "Caporal",
    "Caporal Fourrier": "Caporal Fourrier"
}

# Discord Company Roles
DISCORD_COMPANY_ROLES = {
    '7EME':  '7EME',
    '8EME':  '8EME',
    'FLQG':  'FLQG',
    'FLQC':  'FLQC',
    '4EME':  '4EME',
    '5EME':  '5EME',
    '6EME':  '6EME',
}

GARDE_NATIONALE_ROLE = "Garde Nationale" # Swapping for actual GN role
BASE_ROLES = ["Member", "Verified"]

# Matching companies to timezone for Google Sheet logging
COMPANY_TIMEZONE = {
    '7EME': 'EUNA',
    '8EME': 'EUNA',
    'FLQG': 'EUNA',
    '4EME': 'ASOC',
    '5EME': 'ASOC', 
    '6EME': 'ASOC',
    'FLQC': 'ASOC',
    }


# Google Spreadsheet setup
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]


# Regex Formatter
KNOWN_COMPANIES     = '|'.join(re.escape(c) for c in COMPANY_TIMEZONE.keys())
COMPANY_PATTERN     = re.compile(rf'\*\*\s*({KNOWN_COMPANIES})\s*\*\*')
MENTION_PATTERN     = re.compile(r'<@!?(\d+)>')
GRADUATION_TRIGGER  = 'Garde Nationale Graduates'


# JSON Cache Handler
def load_verified_users() -> dict:
    if os.path.exists(VERIFIED_USERS_PATH):
        with open(VERIFIED_USERS_PATH, 'r') as f:
            return json.load(f)
    return {}

def save_verified_users(data: dict):
    with open(VERIFIED_USERS_PATH, 'w') as f:
        json.dump(data, f, indent=2)
    bolt_log.info(f"[CACHE] Saved verified_users.json ({len(data)} entries)")

def get_cached_roblox(discord_id: str) -> dict | None:
    users = load_verified_users()
    return users.get(str(discord_id))

def cache_roblox_user(discord_id: str, roblox_id: str, roblox_username: str):
    users = load_verified_users()
    users[str(discord_id)] = {
        'roblox_id':       roblox_id,
        'roblox_username': roblox_username,
        'cached_at':       datetime.utcnow().isoformat()
    }
    save_verified_users(users)
    bolt_log.info(f"[CACHE] Cached {discord_id} → {roblox_username} ({roblox_id})")


# BLOXLINK API
async def get_roblox_user(discord_id: str) -> dict | None:
    """
    Returns {'roblox_id': str, 'roblox_username': str} or None.
    Checks local cache first, then falls back to Bloxlink.
    """
    cached = get_cached_roblox(discord_id)
    if cached:
        bolt_log.info(f"[BLOXLINK] Cache hit for Discord ID {discord_id}")
        return cached

    if not BLOXLINK_API_KEY:
        bolt_log.error("[BLOXLINK] No API key configured.")
        return None

    url = f"https://api.blox.link/v4/public/guilds/{GUILD_ID}/discord-to-roblox/{discord_id}"
    headers = {'Authorization': BLOXLINK_API_KEY}

    print(f"[BLOXLINK] CALLING: {url}")

    async with aiohttp.ClientSession(timeout=AIOHTTP_TIMEOUT) as session:
        async with session.get(url, headers=headers) as resp:
            print(f"[BLOXLINK] Response status: {resp.status}")
            body = await resp.json()
            print(f"[BLOXLINK] Response body: {body}")

            if resp.status != 200:
                bolt_log.warning(f"[BLOXLINK] Lookup failed for {discord_id}: HTTP {resp.status}")
                return None

            roblox_id = str(body.get('robloxID') or body.get('roblox_id', ''))
            if not roblox_id:
                bolt_log.warning(f"[BLOXLINK] No Roblox ID in response: {body}")
                return None

    username = await get_roblox_username(roblox_id)
    if username:
        cache_roblox_user(discord_id, roblox_id, username)
        return {'roblox_id': roblox_id, 'roblox_username': username}

    return None


# Roblox Open Cloud API
ROBLOX_OC_HEADERS = lambda: {
    'x-api-key': ROBLOX_OPEN_CLOUD,
    'Content-Type': 'application/json'
}

#verify key is loaded at startup
print(f"[CONFIG] ROBLOX_OC_HEADERS x-api-key present: {bool(ROBLOX_OPEN_CLOUD)}")

async def get_roblox_username(roblox_id: str) -> str | None:
    url = f"https://users.roblox.com/v1/users/{roblox_id}"
    async with aiohttp.ClientSession(timeout=AIOHTTP_TIMEOUT) as session:
        async with session.get(url) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
            return data.get('name')

async def get_roblox_account_age(roblox_id: str) -> str:
    url = f"https://users.roblox.com/v1/users/{roblox_id}"
    async with aiohttp.ClientSession(timeout=AIOHTTP_TIMEOUT) as session:
        async with session.get(url) as resp:
            if resp.status != 200:
                return 'Unknown'
            data = await resp.json()
            created = data.get('created', '')
            if not created:
                return 'Unknown'
            created_dt = datetime.fromisoformat(created.replace('Z', '+00:00'))
            now = datetime.now(timezone.utc)
            delta = now - created_dt
            years  = delta.days // 365
            months = (delta.days % 365) // 30
            days   = delta.days % 30
            return f"{years} years, {months} months, {days} days"

async def get_roblox_previous_usernames(roblox_id: str) -> str:
    url = f"https://users.roblox.com/v1/users/{roblox_id}/username-history?limit=10"
    async with aiohttp.ClientSession(timeout=AIOHTTP_TIMEOUT) as session:
        async with session.get(url) as resp:
            if resp.status != 200:
                return 'Unknown'
            data = await resp.json()
            names = [entry['name'] for entry in data.get('data', [])]
            return ', '.join(names) if names else 'None'

async def get_group_rank(roblox_id: str, group_id: str) -> str | None:
    """Returns the rank name of a user in a group, or None if not a member."""
    url = f"https://groups.roblox.com/v2/users/{roblox_id}/groups/roles"
    async with aiohttp.ClientSession(timeout=AIOHTTP_TIMEOUT) as session:
        async with session.get(url) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
            for entry in data.get('data', []):
                if str(entry['group']['id']) == str(group_id):
                    return entry['role']['name']
    return None

async def set_group_rank(roblox_id: str, group_id: str, rank_name: str) -> bool:
    """Sets a user's rank in a group by rank name using Open Cloud."""
    print(f"[ROBLOX] set_group_rank called: user={roblox_id}, group={group_id}, rank={rank_name}")

    if not ROBLOX_OPEN_CLOUD:
        print("[ROBLOX] ERROR: No Open Cloud key configured")
        bolt_log.error("[ROBLOX] No Open Cloud key configured.")
        return False

    # Step 1: Get all roles to find the role path matching rank_name
    roles_url = f"https://apis.roblox.com/cloud/v2/groups/{group_id}/roles"
    print(f"[ROBLOX] Fetching roles from: {roles_url}")

    try:
        async with aiohttp.ClientSession(timeout=AIOHTTP_TIMEOUT) as session:
            async with session.get(roles_url, headers=ROBLOX_OC_HEADERS()) as resp:
                print(f"[ROBLOX] Get roles status: {resp.status}")
                if resp.status != 200:
                    body = await resp.text()
                    print(f"[ROBLOX] Get roles error: {body}")
                    bolt_log.error(f"[ROBLOX] Failed to fetch roles: HTTP {resp.status} — {body}")
                    return False
                roles_data = await resp.json()
    except Exception as e:
        print(f"[ROBLOX] Exception fetching roles: {e}")
        bolt_log.error(f"[ROBLOX] Exception fetching roles: {e}")
        return False

    role_path = None
    for role in roles_data.get('groupRoles', []):
        display_name = role.get('displayName', '').strip()
        print(f"[ROBLOX] Available role: '{display_name}' | path: {role.get('path')}")
        if display_name.lower() == rank_name.strip().lower():
            role_path = role.get('path')
            print(f"[ROBLOX] Matched role: '{display_name}' → {role_path}")
            break

    if not role_path:
        print(f"[ROBLOX] Role '{rank_name}' not found in group roles list")
        bolt_log.error(f"[ROBLOX] Rank '{rank_name}' not found in group {group_id}")
        return False

    # Step 2: Find the membership path for this user
    memberships_url = f"https://apis.roblox.com/cloud/v2/groups/{group_id}/memberships"
    params = {'filter': f"user == 'users/{roblox_id}'"}
    print(f"[ROBLOX] Fetching membership for user {roblox_id}")

    try:
        async with aiohttp.ClientSession(timeout=AIOHTTP_TIMEOUT) as session:
            async with session.get(memberships_url, headers=ROBLOX_OC_HEADERS(), params=params) as resp:
                print(f"[ROBLOX] Get membership status: {resp.status}")
                body_text = await resp.text()
                print(f"[ROBLOX] Get membership response: {body_text}")
                if resp.status != 200:
                    bolt_log.error(f"[ROBLOX] Failed to fetch membership: HTTP {resp.status}")
                    return False
                membership_data = json.loads(body_text)
    except Exception as e:
        print(f"[ROBLOX] Exception fetching membership: {e}")
        bolt_log.error(f"[ROBLOX] Exception fetching membership: {e}")
        return False

    memberships = membership_data.get('groupMemberships', [])
    if not memberships:
        print(f"[ROBLOX] No membership found for user {roblox_id} in group {group_id}")
        bolt_log.error(f"[ROBLOX] User {roblox_id} is not a member of group {group_id}")
        return False

    membership_path = memberships[0].get('path')
    print(f"[ROBLOX] Found membership path: {membership_path}")

    # Step 3: PATCH the membership with the new role
    patch_url = f"https://apis.roblox.com/cloud/v2/{membership_path}"
    payload = {'role': role_path}
    print(f"[ROBLOX] Patching {patch_url} with role {role_path}")

    try:
        async with aiohttp.ClientSession(timeout=AIOHTTP_TIMEOUT) as session:
            async with session.patch(patch_url, headers=ROBLOX_OC_HEADERS(), json=payload) as resp:
                print(f"[ROBLOX] Set rank status: {resp.status}")
                body = await resp.text()
                print(f"[ROBLOX] Set rank response: {body}")
                success = resp.status in (200, 204)
                if not success:
                    bolt_log.error(f"[ROBLOX] Failed to set rank: HTTP {resp.status} — {body}")
                else:
                    bolt_log.info(f"[ROBLOX] Successfully set {roblox_id} to {rank_name}")
                return success
    except Exception as e:
        print(f"[ROBLOX] Exception setting rank: {e}")
        bolt_log.error(f"[ROBLOX] Exception setting rank: {e}")
        return False


#  GOOGLE SHEETS
def get_timezone(company: str) -> str:
    return COMPANY_TIMEZONE.get(company.strip(), 'UNKNOWN')

class SheetsLogger:
    def __init__(self, credentials_path, spreadsheet_id, sheet_name):
        bolt_log.info("[SHEETS] Authenticating with Google Sheets API...")
        creds = Credentials.from_service_account_file(credentials_path, scopes=SCOPES)
        client = gspread.authorize(creds)
        self.sheet = client.open_by_key(spreadsheet_id).worksheet(sheet_name)
        bolt_log.info(f"[SHEETS] Connected to worksheet: '{sheet_name}'")

    def ensure_headers(self):
        first_row = self.sheet.row_values(1)
        if not first_row:
            self.sheet.append_row([
                'LOG TIMESTAMP', 'Recruit Username', 'Discord ID',
                'Class Date', 'Date Left', 'EUNA/ASOC', 'COMPANY', 'GN Host'
            ], value_input_option='USER_ENTERED')
            bolt_log.info("[SHEETS] Headers written.")
        else:
            bolt_log.info("[SHEETS] Headers present, skipping.")

    def log_recruits(self, rows: list[list]):
        if rows:
            self.sheet.append_rows(rows, value_input_option='USER_ENTERED')
            bolt_log.info(f"[SHEETS] Wrote {len(rows)} row(s).")
        else:
            bolt_log.warning("[SHEETS] log_recruits called with empty list.")

#  GRADUATION MESSAGE PARSER
async def parse_graduation_message(message: discord.Message) -> list[list]:
    content    = message.content
    host       = str(message.author)
    dt         = message.created_at.replace(tzinfo=timezone.utc)
    class_date = f"{dt.month}/{dt.day}/{dt.year}"
    timestamp  = dt.isoformat()
    rows, segments, last_end, current_company = [], [], 0, None

    for match in COMPANY_PATTERN.finditer(content):
        company_name = match.group(1).strip()
        bolt_log.debug(f"[PARSE] Matched company: '{company_name}'")
        segment_text = content[last_end:match.start()]
        if current_company is not None:
            segments.append((current_company, segment_text))
        current_company = company_name
        last_end = match.end()

    if current_company is not None:
        segments.append((current_company, content[last_end:]))

    for company, segment_text in segments:
        timezone_label = get_timezone(company)
        bolt_log.debug(f"[PARSE] Company: '{company}' → Timezone: '{timezone_label}'")
        for user_id in MENTION_PATTERN.findall(segment_text):
            username = ''
            try:
                member = message.guild.get_member(int(user_id))
                if member:
                    username = str(member)
                else:
                    member = await message.guild.fetch_member(int(user_id))
                    username = str(member)
            except Exception as e:
                username = f'Unknown ({user_id})'
                bolt_log.warning(f"[PARSE] Could not resolve {user_id}: {e}")
            rows.append([timestamp, username, user_id, class_date, '', timezone_label, company, host])

    bolt_log.info(f"[PARSE] Parsed {len(rows)} recruit row(s).")
    return rows


#  BOT SETUP
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)
sheets_logger: SheetsLogger | None = None


@bot.event
async def on_ready():
    global sheets_logger
    print(f'[BOT] Logged in as {bot.user.name} - {bot.user.id}')
    bolt_log.info(f"[BOT] Logged in as {bot.user.name} - {bot.user.id}")
    try:
        sheets_logger = SheetsLogger(CREDENTIALS_PATH, SPREADSHEET_ID, LOG_SHEET_NAME)
        sheets_logger.ensure_headers()
        print("[BOT] Google Sheets logger initialized successfully.")
        bolt_log.info("[BOT] Google Sheets logger initialized successfully.")
    except Exception as e:
        print(f"[BOT] Error initializing Google Sheets logger: {type(e).__name__}: {e}")
        bolt_log.error(f"[BOT] Error initializing Sheets: {type(e).__name__}: {e}")

    try:
        synced = await bot.tree.sync()
        print(f"[BOT] Synced {len(synced)} slash command(s).")
        bolt_log.info(f"[BOT] Synced {len(synced)} slash command(s).")
    except Exception as e:
        print(f"[BOT] Failed to sync commands: {e}")
        bolt_log.error(f"[BOT] Failed to sync commands: {e}")


@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    if GRADUATION_TRIGGER not in message.content:
        await bot.process_commands(message)
        return
    print(f"[GRADUATION] Detected from {message.author} in #{message.channel.name}")
    bolt_log.info(f"[BOT] Graduation message detected from {message.author}")
    if sheets_logger:
        try:
            rows = await parse_graduation_message(message)
            sheets_logger.log_recruits(rows)
            print(f"[GRADUATION] Logged {len(rows)} recruit(s).")
        except Exception as e:
            print(f"[GRADUATION] Error: {type(e).__name__}: {e}")
            bolt_log.error(f"[BOT] Graduation processing failed: {type(e).__name__}: {e}")
    await bot.process_commands(message)



#  /background-check
@bot.tree.command(name="background-check", description="Run a background check on one or more users.")
@app_commands.describe(users="Mention one or more users to check")
async def background_check(interaction: discord.Interaction, users: str):
    await interaction.response.defer()
    mentioned_ids = MENTION_PATTERN.findall(users)
    if not mentioned_ids:
        await interaction.followup.send("Please mention at least one user.")
        return

    for discord_id in mentioned_ids:
        member = interaction.guild.get_member(int(discord_id))
        roblox = await get_roblox_user(discord_id)

        if not roblox:
            await interaction.followup.send(
                f"❌ <@{discord_id}> is not verified with Bloxlink or could not be found."
            )
            continue

        roblox_id       = roblox['roblox_id']
        roblox_username = roblox['roblox_username']
        account_age     = await get_roblox_account_age(roblox_id)
        prev_names      = await get_roblox_previous_usernames(roblox_id)
        group_rank      = await get_group_rank(roblox_id, ROBLOX_GROUP_ID) or 'Not in group'

        discord_display = f"<@{discord_id}>" if member else f"Unknown ({discord_id})"
        nick            = member.nick or member.name if member else roblox_username

        embed = discord.Embed(
            title="Background Check Results",
            color=discord.Color.dark_blue()
        )
        embed.add_field(name="Discord",          value=discord_display,  inline=False)
        embed.add_field(name="Roblox Username",  value=roblox_username,  inline=True)
        embed.add_field(name="Account Age",      value=account_age,      inline=True)
        embed.add_field(name="Current Rank",     value=group_rank,       inline=True)
        embed.add_field(name="Previous Usernames", value=prev_names,     inline=False)
        embed.add_field(
            name="Coalition",
            value="*Placeholder — source TBD*",
            inline=False
        )
        embed.add_field(
            name="Clients & France",
            value="*Placeholder — source TBD*",
            inline=False
        )
        embed.set_footer(text=f"Roblox ID: {roblox_id}")

        await interaction.followup.send(embed=embed)
        bolt_log.info(f"[BG CHECK] Ran background check on {roblox_username} ({roblox_id})")


#  /accept
async def accept_join_request(roblox_id: str, group_id: str) -> bool:
    """
    Accepts a pending join request using Open Cloud.
    Must first list join requests to find the request path,
    then POST to accept it.
    """
    if not ROBLOX_OPEN_CLOUD:
        bolt_log.error("[ROBLOX] No Open Cloud key configured.")
        return False

    # Step 1: List all pending join requests to find this user's request path
    list_url = f"https://apis.roblox.com/cloud/v2/groups/{group_id}/join-requests"
    request_path = None

    async with aiohttp.ClientSession(timeout=AIOHTTP_TIMEOUT) as session:
        params = {'maxPageSize': 100}
        async with session.get(list_url, headers=ROBLOX_OC_HEADERS(), params=params) as resp:
            print(f"[ROBLOX] List join requests status: {resp.status}")
            if resp.status != 200:
                body = await resp.text()
                print(f"[ROBLOX] List join requests error: {body}")
                bolt_log.error(f"[ROBLOX] Failed to list join requests: HTTP {resp.status} — {body}")
                return False
            data = await resp.json()
            print(f"[ROBLOX] Join requests response: {data}")

            for request in data.get('groupJoinRequests', []):
                # path looks like "groups/772916015/join-requests/1203721042"
                # user looks like "users/1203721042"
                user_field = request.get('user', '')
                if str(roblox_id) in user_field:
                    request_path = request.get('path')
                    break

    if not request_path:
        print(f"[ROBLOX] No pending join request found for Roblox ID {roblox_id}")
        bolt_log.warning(f"[ROBLOX] No pending join request found for {roblox_id}")
        return False

    # Step 2: Accept the request using its path
    accept_url = f"https://apis.roblox.com/cloud/v2/{request_path}:accept"
    async with aiohttp.ClientSession(timeout=AIOHTTP_TIMEOUT) as session:
        async with session.post(
            accept_url,
            headers=ROBLOX_OC_HEADERS(),
            json={}  # ← Roblox requires an empty JSON body, not no body
        ) as resp:
            print(f"[ROBLOX] Accept join request status: {resp.status}")
            body = await resp.text()
            print(f"[ROBLOX] Accept response: {body}")
            success = resp.status in (200, 204)
            if not success:
                bolt_log.error(f"[ROBLOX] Failed to accept join request: HTTP {resp.status} — {body}")
            return success
        
# 1. AcceptGroupSelect FIRST
class AcceptGroupSelect(discord.ui.Select):
    def __init__(self, discord_ids: list[str], roblox_data: dict):
        self.discord_ids = discord_ids
        self.roblox_data = roblox_data
        options = [
            discord.SelectOption(
                label="Bandits Hideout (Test Group)",
                value=ROBLOX_GROUP_ID,
                description="Accept into the test Roblox group"
            ),
        ]
        super().__init__(placeholder="Select which group to accept into...", options=options)

    async def callback(self, interaction: discord.Interaction):
        group_id = self.values[0]
        await interaction.response.defer()
        results = []

        for discord_id in self.discord_ids:
            roblox = self.roblox_data.get(discord_id)
            if not roblox:
                results.append(f"❌ <@{discord_id}> — not verified with Bloxlink")
                continue

            roblox_id = roblox['roblox_id']
            roblox_username = roblox['roblox_username']

            # Check if already in group
            current_rank = await get_group_rank(roblox_id, group_id)
            if current_rank and current_rank.lower() not in ('guest', ''):
                print(f"[ACCEPT] {roblox_username} already in group as '{current_rank}', checking Discord roles and Roblox rank")

                # Attempt to set Roblox rank to Citoyen if not already there
                roblox_rank_line = ""
                if current_rank.lower() != 'citoyen':
                    ranked = await set_group_rank(roblox_id, group_id, 'Citoyen')
                    roblox_rank_line = "✅ Roblox rank set to Citoyen" if ranked else "⚠️ Failed to set Roblox rank"
                else:
                    roblox_rank_line = "⚠️ Already ranked Citoyen in Roblox"

                # Assign missing Discord roles
                citoyen_role  = discord.utils.get(interaction.guild.roles, name='Citoyen')
                verified_role = discord.utils.get(interaction.guild.roles, name='Verified')
                discord_line  = ""
                try:
                    member = interaction.guild.get_member(int(discord_id))
                    if not member:
                        member = await interaction.guild.fetch_member(int(discord_id))
                    roles_to_add = []
                    if citoyen_role and citoyen_role not in member.roles:
                        roles_to_add.append(citoyen_role)
                    if verified_role and verified_role not in member.roles:
                        roles_to_add.append(verified_role)
                    if roles_to_add:
                        await member.add_roles(*roles_to_add)
                        discord_line = f"✅ Discord roles added: {', '.join(r.name for r in roles_to_add)}"
                    else:
                        discord_line = "⚠️ Discord roles already present"
                except Exception as e:
                    discord_line = f"❌ Discord role error: {e}"

                results.append(f"**{roblox_username}** (was {current_rank})\n  {roblox_rank_line}\n  {discord_line}")
                continue

            # Accept join request
            accepted = await accept_join_request(roblox_id, group_id)
            if not accepted:
                results.append(f"❌ **{roblox_username}** — failed to accept (no pending request?)")
                continue

            # Set Roblox rank to Citoyen
            ranked = await set_group_rank(roblox_id, group_id, 'Citoyen')

            # Assign Discord roles regardless of Roblox ranking result
            citoyen_role  = discord.utils.get(interaction.guild.roles, name='Citoyen')
            verified_role = discord.utils.get(interaction.guild.roles, name='Verified')
            discord_roles_added = []
            try:
                member = interaction.guild.get_member(int(discord_id))
                if not member:
                    member = await interaction.guild.fetch_member(int(discord_id))
                roles_to_add = []
                if citoyen_role and citoyen_role not in member.roles:
                    roles_to_add.append(citoyen_role)
                if verified_role and verified_role not in member.roles:
                    roles_to_add.append(verified_role)
                if roles_to_add:
                    await member.add_roles(*roles_to_add)
                    discord_roles_added = [r.name for r in roles_to_add]
            except Exception as e:
                bolt_log.warning(f"[ACCEPT] Failed to assign Discord roles to {discord_id}: {e}")

            status_line = f"✅ **{roblox_username}** — accepted"
            if ranked:
                status_line += ", ranked to Citoyen in Roblox"
            else:
                status_line += ", ⚠️ Roblox rank failed (set manually)"
            if discord_roles_added:
                status_line += f", Discord roles added: {', '.join(discord_roles_added)}"

            results.append(status_line)
            bolt_log.info(f"[ACCEPT] Accepted {roblox_username} into group {group_id}")

        await interaction.followup.send("**Accept Results**\n" + '\n'.join(results))
        self.view.stop()

class AcceptView(discord.ui.View):
    def __init__(self, discord_ids: list[str], roblox_data: dict):
        super().__init__(timeout=60)
        self.add_item(AcceptGroupSelect(discord_ids, roblox_data))

# 3. /accept command LAST
@bot.tree.command(name="accept", description="Accept one or more users into a Roblox group.")
@app_commands.describe(users="Mention one or more users to accept")
async def accept(interaction: discord.Interaction, users: str):
    print(f"[ACCEPT] Command fired by {interaction.user} with input: {users}")
    await interaction.response.defer()
    mentioned_ids = MENTION_PATTERN.findall(users)
    if not mentioned_ids:
        await interaction.followup.send("Please mention at least one user.")
        return

    roblox_data = {}
    for discord_id in mentioned_ids:
        roblox = await get_roblox_user(discord_id)
        if roblox:
            roblox_data[discord_id] = roblox
        else:
            bolt_log.warning(f"[ACCEPT] Could not resolve Roblox for {discord_id}")

    view = AcceptView(mentioned_ids, roblox_data)
    await interaction.followup.send("Which group would you like to accept these users into?", view=view)


#  /induct
@bot.tree.command(name="induct", description="Induct one or more recruits into the regiment.")
@app_commands.describe(
    users="Mention one or more users to induct",
    company="The company to assign (e.g. 7EME, FLQG)"
)
async def induct(interaction: discord.Interaction, users: str, company: str):
    print("[INDUCT] Command fired")
    await interaction.response.defer()
    company = company.upper().strip()

    if company not in DISCORD_COMPANY_ROLES:
        await interaction.followup.send(
            f"❌ Unknown company `{company}`. Valid options: {', '.join(DISCORD_COMPANY_ROLES.keys())}"
        )
        return

    mentioned_ids = MENTION_PATTERN.findall(users)
    if not mentioned_ids:
        await interaction.followup.send("Please mention at least one user.")
        return

    for discord_id in mentioned_ids:
        lines = []
        try:
            member = interaction.guild.get_member(int(discord_id))
            if not member:
                try:
                    member = await interaction.guild.fetch_member(int(discord_id))
                except Exception:
                    await interaction.followup.send(f"❌ Could not find Discord member <@{discord_id}>.")
                    continue

            roblox = await get_roblox_user(discord_id)

            lines.append(f"**Induct Results**")
            lines.append(f"<@{discord_id}>, {member.display_name}")

            if not roblox:
                lines.append("❌ Not verified with Bloxlink. Induction aborted.")
                await interaction.followup.send('\n'.join(lines))
                continue

            roblox_id       = roblox['roblox_id']
            roblox_username = roblox['roblox_username']

            current_rank = await get_group_rank(roblox_id, ROBLOX_GROUP_ID)
            if not current_rank or current_rank.lower() in ('guest', ''):
                lines.append("❌ Not in the Roblox group or pending. Run /accept first. Induction aborted.")
                await interaction.followup.send('\n'.join(lines))
                continue

            lines.append("✅ Accepted to Garde Impériale")

            # Set Roblox rank
            if current_rank.lower() == 'conscrit':
                lines.append("⚠️ Is already ranked Conscrit. Skipping")
            else:
                try:
                    ranked = await asyncio.wait_for(
                        set_group_rank(roblox_id, ROBLOX_GROUP_ID, 'Conscrit'),
                        timeout=15
                    )
                    lines.append("✅ Ranked to Conscrit." if ranked else "❌ Failed to set Roblox rank.")
                except asyncio.TimeoutError:
                    lines.append("⚠️ Roblox rank request timed out.")

            # Strip previous Discord roles
            guild = interaction.guild
            roles_to_remove = []
            for rank_role_name in DISCORD_RANK_ROLES.values():
                role = discord.utils.get(guild.roles, name=rank_role_name)
                if role and role in member.roles:
                    roles_to_remove.append(role)
            for company_role_name in DISCORD_COMPANY_ROLES.values():
                role = discord.utils.get(guild.roles, name=company_role_name)
                if role and role in member.roles:
                    roles_to_remove.append(role)
            citoyen_discord = discord.utils.get(guild.roles, name='Citoyen')
            if citoyen_discord and citoyen_discord in member.roles:
                roles_to_remove.append(citoyen_discord)
            if roles_to_remove:
                await member.remove_roles(*roles_to_remove)
                lines.append(f"✅ Stripped previous roles: {', '.join(r.name for r in roles_to_remove)}")

            # Add Conscrit role
            conscrit_role = discord.utils.get(guild.roles, name=DISCORD_RANK_ROLES['Conscrit'])
            if conscrit_role:
                await member.add_roles(conscrit_role)
                lines.append("✅ Added Conscrit role.")
            else:
                lines.append("❌ Conscrit Discord role not found.")

            # Add company role
            company_role_name = DISCORD_COMPANY_ROLES.get(company)
            company_role      = discord.utils.get(guild.roles, name=company_role_name)
            if company_role:
                await member.add_roles(company_role)
                lines.append(f"✅ Added company role for {company}.")
            else:
                lines.append(f"❌ Company role '{company_role_name}' not found.")

            # Add base roles
            base_added = []
            for role_name in BASE_ROLES:
                role = discord.utils.get(guild.roles, name=role_name)
                if role and role not in member.roles:
                    await member.add_roles(role)
                    base_added.append(role_name)
            lines.append("✅ Added base roles." if base_added else "⚠️ Base roles already present.")

            # Remove Garde Nationale role
            gn_role = discord.utils.get(guild.roles, name=GARDE_NATIONALE_ROLE)
            if gn_role and gn_role in member.roles:
                await member.remove_roles(gn_role)
                lines.append("✅ Removed Garde Nationale role.")
            else:
                lines.append("⚠️ Garde Nationale role not present.")

            # Update nickname
            new_nick = f"[{company}] {roblox_username}"
            try:
                await member.edit(nick=new_nick)
                lines.append(f"✅ Updated nickname to {new_nick}.")
            except discord.Forbidden:
                lines.append("⚠️ Could not update nickname (missing permissions).")

            bolt_log.info(f"[INDUCT] Inducted {roblox_username} into {company}")

        except Exception as e:
            # Catch-all — guarantees the interaction always gets a response
            lines.append(f"❌ Unexpected error during induction: {type(e).__name__}: {e}")
            bolt_log.error(f"[INDUCT] Unexpected error for {discord_id}: {type(e).__name__}: {e}")
            print(f"[INDUCT] Unexpected error for {discord_id}: {type(e).__name__}: {e}")

        finally:
            # This ALWAYS runs — guarantees Discord clears the "thinking" state
            if lines:
                await interaction.followup.send('\n'.join(lines))


#  /draft
@bot.tree.command(name="draft", description="Draft a user to a new company, resetting their rank.")
@app_commands.describe(
    users="Mention one or more users to draft",
    new_company="The new company to assign"
)
async def draft(interaction: discord.Interaction, users: str, new_company: str):
    print("[DRAFT] Command fired")
    await interaction.response.defer()
    new_company = new_company.upper().strip()

    if new_company not in DISCORD_COMPANY_ROLES:
        await interaction.followup.send(
            f"❌ Unknown company `{new_company}`. Valid: {', '.join(DISCORD_COMPANY_ROLES.keys())}"
        )
        return

    mentioned_ids = MENTION_PATTERN.findall(users)
    if not mentioned_ids:
        await interaction.followup.send("Please mention at least one user.")
        return

    for discord_id in mentioned_ids:
        member = interaction.guild.get_member(int(discord_id))
        if not member:
            try:
                member = await interaction.guild.fetch_member(int(discord_id))
            except Exception:
                await interaction.followup.send(f"❌ Could not find <@{discord_id}>.")
                continue

        roblox = await get_roblox_user(discord_id)
        lines  = [f"**Draft Results**", f"<@{discord_id}>, {member.display_name}"]

        if not roblox:
            lines.append("❌ Not verified with Bloxlink. Draft aborted.")
            await interaction.followup.send('\n'.join(lines))
            continue

        roblox_id = roblox['roblox_id']
        roblox_username = roblox['roblox_username']
        guild = interaction.guild

        # Remove all existing company roles
        removed_companies = []
        for company_role_name in DISCORD_COMPANY_ROLES.values():
            role = discord.utils.get(guild.roles, name=company_role_name)
            if role and role in member.roles:
                await member.remove_roles(role)
                removed_companies.append(company_role_name)

        # Remove all existing rank roles
        for rank_role_name in DISCORD_RANK_ROLES.values():
            role = discord.utils.get(guild.roles, name=rank_role_name)
            if role and role in member.roles:
                await member.remove_roles(role)

        lines.append(f"✅ Removed previous company/rank roles: {', '.join(removed_companies) or 'none'}")

        # Assign new company role
        new_company_role = discord.utils.get(guild.roles, name=DISCORD_COMPANY_ROLES[new_company])
        if new_company_role:
            await member.add_roles(new_company_role)
            lines.append(f"✅ Assigned to {new_company}.")
        else:
            lines.append(f"❌ Company role '{new_company}' not found in Discord.")

        # Assign Conscrit rank role
        conscrit_role = discord.utils.get(guild.roles, name=DISCORD_RANK_ROLES['Conscrit'])
        if conscrit_role:
            await member.add_roles(conscrit_role)
            lines.append("✅ Reset rank to Conscrit.")
        else:
            lines.append("❌ Conscrit role not found in Discord.")

        # Reset Roblox rank to Conscrit
        try:
            ranked = await asyncio.wait_for(
                set_group_rank(roblox_id, ROBLOX_GROUP_ID, 'Conscrit'),
                timeout=15
            )
        except asyncio.TimeoutError:
            ranked = False
            lines.append("⚠️ Roblox rank request timed out.")
        lines.append("✅ Roblox rank reset to Conscrit." if ranked else "❌ Failed to reset Roblox rank.")

        # Update nickname
        new_nick = f"[{new_company}] {roblox_username}"
        try:
            await member.edit(nick=new_nick)
            lines.append(f"✅ Updated nickname to {new_nick}.")
        except discord.Forbidden:
            lines.append("⚠️ Could not update nickname (missing permissions).")

        await interaction.followup.send('\n'.join(lines))
        bolt_log.info(f"[DRAFT] Drafted {roblox_username} to {new_company}")

#  LEGACY COMMANDS
server_role = "gamer"

@bot.event
async def on_member_join(member):
    await member.send(f"Welcome to the server {member.name}!")

@bot.command()
async def hello(ctx):
    await ctx.send(f"Hello {ctx.author.mention}!")

@bot.command()
async def assign(ctx):
    role = discord.utils.get(ctx.guild.roles, name=server_role)
    if role:
        await ctx.author.add_roles(role)
        await ctx.send(f"{ctx.author.mention} has been assigned the {server_role} role.")
    else:
        await ctx.send("Role doesn't exist.")


bot.run(token, log_handler=handler, log_level=logging.DEBUG)