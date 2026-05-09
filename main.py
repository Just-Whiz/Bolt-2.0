# Bot name: Bolt 2.0
# Author: orbandit (@just_whiz on Discord)
# Date: 2026-05-08
# Description: Discord message logger that logs to Google Sheets
# Version: 0.3.0
# Note: using pythoncore 3.14-64. Run requirements.txt using pip to install all listed dependencies in this file.

import discord
from discord.ext import commands
import logging
import os
import re
from dotenv import load_dotenv
from datetime import timezone
import gspread
from google.oauth2.service_account import Credentials

print("hello world!")

load_dotenv()

token = os.getenv("DISCORD_TOKEN")
CREDENTIALS_PATH = os.getenv("GOOGLE_CREDENTIALS_PATH", "credentials.json")
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
LOG_SHEET_NAME = os.getenv("LOG_SHEET_NAME", "Garde Nationale Test Example")
BLOXLINK_API_KEY = os.getenv("BLOXLINK_API_KEY")
ROBLOX_OPEN_CLOUD = os.getenv("ROBLOX_OPEN_CLOUD_KEY")
ROBLOX_GROUP_ID = os.getenv("ROBLOX_GROUP_ID", "772916015")

VERIFIED_USERS_PATH = "verified_users.json"

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
    "https://www.googleapis.com/auth/spreadsheets"
    "https://www.googleapis.com/auth/drive"
]

