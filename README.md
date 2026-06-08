# Bolt 2.0 — Corps de Cavalerie Impériale Discord Bot

A Discord bot for the **Corps de Cavalerie Impériale** Roblox military group, built with discord.py. Bolt automates member induction, rank promotion, brigade drafting, background checks, medal syncing, and roster management — bridging your Discord server, Roblox group, and Google Sheets roster in a single workflow.

---

## Features

- **`/induct`** — Accepts a recruit's Roblox join request, sets their Roblox group rank, assigns Discord roles, sets their nickname, and creates a new roster row in the Google Sheet.
- **`/promote`** — Interactive multi-step promotion flow. Supports rank-by-rank promotion or a full brigade draft (which also moves the member's sheet row to the correct regiment tab).
- **`/purge`** — Strips all roles, kicks the member from the Roblox group, resets their nickname, logs them to a "Purged" sheet tab, and adds the Admissions Blacklist role.
- **`/background-check`** — Pulls a member's Roblox profile, account age, previous usernames, avatar, and group memberships (categorised as French, Coalition, or Neutral), and assigns any matching nobility title/nickname.
- **`/medal-sync`** — Reads the MedalsRoster, Venerations, and Nobility tabs from Google Sheets and grants every approved Discord role to the target member.
- **`/export-rosters`** — Outputs a formatted brigade-by-brigade member list.
- **Auto-blacklist** — Automatically blacklists any member mentioned in `#the-yard`, kicking them from the Roblox group and logging them to the spreadsheet.

---

## Tech Stack

- **[discord.py](https://github.com/Rapptz/discord.py)** (slash commands, UI components)
- **[gspread](https://github.com/burnash/gspread)** + Google Sheets API (roster sync)
- **[httpx](https://www.python-httpx.org/)** (persistent async HTTP client for Roblox API calls)
- **[Bloxlink API](https://blox.link/)** (Discord → Roblox account resolution)
- **Roblox Open Cloud v2** (group rank management, join request acceptance, member removal)
- **[python-dotenv](https://github.com/theskumar/python-dotenv)** (environment configuration)

---

## Project Structure

```
.
├── main.py              # Bot entry point — all Discord commands and event handlers
├── sheets_sync.py       # Google Sheets roster sync logic (induct, promote, draft, purge)
├── credentials.json     # Google service account key (not committed)
├── verified_users.json  # Local Bloxlink resolution cache (auto-generated)
├── bolt.log             # Persistent debug log (auto-generated)
└── .env                 # Environment variables (see below)
```

---

## Setup

### Prerequisites

- Python 3.11+
- A Discord bot token with **Message Content** and **Server Members** intents enabled
- A Bloxlink API key
- A Roblox Open Cloud API key with group management permissions
- A Google service account with Sheets + Drive access, and the `credentials.json` file

### Installation

```bash
pip install discord.py gspread httpx aiohttp python-dotenv google-auth google-api-python-client
```

### Environment Variables

Create a `.env` file in the project root:

```env
DISCORD_TOKEN=your_discord_bot_token
BLOXLINK_API_KEY=your_bloxlink_api_key
GUILD_ID=your_discord_guild_id
ROBLOX_OPEN_CLOUD_KEY=your_roblox_open_cloud_key
FRENCH_GROUP_ID=5610765
CAV_GROUP_ID=195387641
GOOGLE_SERVICE_ACCOUNT_FILE=credentials.json
FRENCH_SPREADSHEET_ID=your_french_spreadsheet_id
CAV_SPREADSHEET_ID=your_cav_spreadsheet_id
```

### Running

```bash
python main.py
```

---

## Configuration

### Adding Regiments

All regiment configuration lives in `main.py`. To add a new regiment:

1. Add its tab key to `BRIGADE_TO_REGIMENT_TABS` under the appropriate brigade.
2. Add a human-readable label to `REGIMENT_TO_TAB_LABEL`.
3. Add its Discord role name to `TAB_TO_DISCORD_ROLE`.

### Sheet Structure

`sheets_sync.py` expects each regiment tab to have data rows starting at **row 24** with the following column layout (0-indexed):

| Index | Column |
|-------|--------|
| 5 | Rank/Position |
| 6 | Timezone |
| 7 | Drafted Date (MM/DD/YYYY) |
| 8 | Days Since |
| 9 | Discord ID |
| 10 | Roblox Username |
| 11 | Kills |
| 12 | KPE |
| 13 | Activity % |

The **Stats** tab maps members across regiments using columns AO–AQ (Discord ID, Regiment, Roblox Username).

---

## Logging

All bot activity is written to `bolt.log` with timestamped entries at DEBUG level. Console output (`print`) covers the most important per-operation steps and is suitable for live monitoring.

---

## Notes

- The Roblox Open Cloud API has no group-unban endpoint. `/purge` removes members by deleting their group membership. Re-admission requires the user to send a new join request and be re-inducted manually.
- The verified user cache (`verified_users.json`) is populated on-demand via Bloxlink and refreshed every 6 hours at startup. It persists across restarts.
- New roster rows copy cell formulas from the row above them so that computed columns (KPE, Activity %, rally attendance, etc.) continue to work correctly.