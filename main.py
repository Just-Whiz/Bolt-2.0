# ============================================================
#  Bolt 2.0 — Corps de Cavalerie Impériale Discord Bot
#  Updated: 2026-05-30
#  Version: 2.0.0
# ============================================================

import asyncio
import json
import logging
import os
import re
from datetime import datetime, timezone

import aiohttp
import discord
import gspread
from discord import app_commands
from discord.ext import commands, tasks
import httpx
from dotenv import load_dotenv
from sheets_sync import (
    async_sync_induct,
    async_sync_promote,
    async_sync_promote_draft,
    async_sync_purge,
)

load_dotenv()

# ============================================================
#  ENVIRONMENT - ACCESSES ALL .env FILE VARIABLES
# ============================================================

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
BLOXLINK_API_KEY = os.getenv("BLOXLINK_API_KEY")
GUILD_ID = os.getenv("GUILD_ID")
ROBLOX_OPEN_CLOUD = os.getenv("ROBLOX_OPEN_CLOUD_KEY")
FRENCH_MAIN_GROUP_ID = os.getenv("FRENCH_GROUP_ID", "5610765")
CAV_GROUP_ID = os.getenv("CAV_GROUP_ID", "195387641")

GOOGLE_SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "credentials.json")

FRENCH_SPREADSHEET_ID = os.getenv("FRENCH_SPREADSHEET_ID")
CAV_SPREADSHEET_ID = os.getenv("CAV_SPREADSHEET_ID, 1m4IWGs9mwK4arKFKCfwpY1K6kmth7YouLRQFz_5u15Q")

def _oc_headers() -> dict:
    return {"x-api-key": ROBLOX_OPEN_CLOUD, "Content-Type": "application/json"}

HTTP_TIMEOUT = aiohttp.ClientTimeout(connect=10, sock_read=15)
ROBLOX_SEMAPHORE = asyncio.Semaphore(3)

# Persistent httpx client — reused across all Roblox API calls so that the
# TLS connection to the Cloudflare Worker is kept alive instead of being
# torn down and re-established on every request (the main source of slowness).
_http: httpx.AsyncClient | None = None

def get_http() -> httpx.AsyncClient:
    global _http
    if _http is None or _http.is_closed:
        _http = httpx.AsyncClient(timeout=15, http2=False)
    return _http

# ============================================================
#  LOGGING
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

# ============================================================
#  GOOGLE SHEETS CLIENT
# ============================================================

def _build_sheets_client() -> gspread.Client | None:
    if not os.path.exists(GOOGLE_SERVICE_ACCOUNT_FILE):
        print(f"[SHEETS] Service-account file not found: {GOOGLE_SERVICE_ACCOUNT_FILE}")
        return None
    try:
        # Scopes updated to allow writing
        client = gspread.service_account(
            filename=GOOGLE_SERVICE_ACCOUNT_FILE,
            scopes=[
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive",
            ]
        )
        print("[SHEETS] Google Sheets client initialised.")
        return client
    except Exception as e:
        print(f"[SHEETS] Failed to initialise: {e}")
        return None

sheets_client: gspread.Client | None = _build_sheets_client()

def _get_worksheets(tab_name: str) -> list[gspread.Worksheet]:
    """Helper to pull tabs from both spreadsheets if they exist."""
    wss = []
    if not sheets_client: return wss
    for sid in [FRENCH_SPREADSHEET_ID, CAV_SPREADSHEET_ID]:
        try:
            sheet = sheets_client.open_by_key(sid)
            wss.append(sheet.worksheet(tab_name))
        except gspread.exceptions.WorksheetNotFound:
            pass 
        except Exception as e:
            log.error(f"[SHEETS] Error accessing {tab_name} in {sid}: {e}")
    return wss

# ============================================================
#  ROBLOX GROUP ID MAPS  (for /background-check display)
# ============================================================

FRENCH_GROUP_IDS: dict[str, str] = {
    "5610765":    "Empire Français",
    "6057395":    "Garde Impériale",
    "6057318":    "Premier Corps",
    "6057327":    "Deuxième Corps",
    "6057333":    "Troisième Corps",
    "7840844":    "Quatrième Corps",
    "9976984":    "Cinquième Corps",
    "13206132":   "Neuvième Corps",
    "13284835":   "État-Major Impériale",
    "195387641":  "Corps de Cavalerie Impériale",
    "6764583":    "Esercito Napoletano",
    "7135170":    "Regno di Napoli",
    "9746123":    "Prima Divisione",
    "10514799":   "Seconda Divisione",
    "32627531":   "Terza Divisione",
    "1112910179": "Quatra Divisione",
    "9067214":    "Marina Napoletana",
    "10349483":   "Guardia Reale",
    "33741408":   "Corpo d'Armata",
    "477750899":  "Reggimento d'Artiglieria di Marina",
    "4614276":    "Woysko Xięstwa Warszawskiego",
    "394072781":  "Sztab Generalny Woyska Polskiego",
    "796097059":  "Brygada Gwardii Narodowej",
    "596867575":  "Xięstwo Litewskie",
    "9921948":    "Pierwsza Dywizya",
    "33709393":   "Drugi Dywizja",
    "9921939":    "Korpus Kawalerii",
}

COALITION_GROUP_IDS: dict[str, str] = {
    "16702357":  "Kaisertum Österreich",
    "17034669":  "Grenadier Korps",
    "16965984":  "Königliche Ungarn",
    "33606731":  "Hof von Österreich",
    "14706502":  "Erste Korps",
    "17248191":  "Zweite Korps",
    "33437234":  "Drittes Korps",
    "33727999":  "Viertes Korps",
    "35915613":  "Fünftes Korps",
    "856818677": "Fünftes Korps Recruitment",
    "33129015":  "Kavallerie Korps",
    "33679754":  "Ingenieur Korps",
    "35755856":  "Küchenbrigade",
    "7528791":   "Imperatorskaya Armiya",
    "10621031":  "Imperskoy Gvardii Korpus",
    "34279561":  "Grenaderskiy Korpus",
    "34279574":  "Severnaya Armiya",
    "32842545":  "Yuzhnaya Armiya",
    "8254296":   "Zapadnaya Armiya",
    "950745879": "Krymskaya Armiya",
    "35917740":  "Vostochnaya Armiya",
    "4000196":    "British Army",
    "9686866":    "First Division",
    "9686840":    "Fifth Brigade",
    "12691944":   "Second Division",
    "35746582":   "Board of Ordnance (INVICTORS)",
    "32033796":   "Braunschweig-Oels-Linien-Bataillon",
    "35746578":   "Board of Ordnance (PRINCIPES)",
    "34209218":   "Schweizer Adelsgeschlecht",
    "7907149":    "Household Brigade",
    "1049512588": "Foot Guards Grenadiers",
    "35965347":  "Preußische Armee",
    "35986490":  "Königliches Gardekorps",
    "35986478":  "Erstes Armeekorps",
    "11639829":  "Ejército de España",
    "223078637": "Ejército Real de Nueva España",
    "32374377":  "Ejército de Aragón",
    "34056502":  "Ejército de Galicia",
    "5531725":   "Andouran Empire",
    "432773563": "Fuirst Keisariks Armcorps",
    "17375317":  "Anders Keisariks Armcorps",
    "35333449":  "Keisariks Armcorps Grenader",
    "16125179":  "Andouran Imperial Guard",
    "8559975":   "Kait",
    "8410719":   "Order of the Gold Griffin",
    "35504152":  "Kurohana",
    "6331920":   "Order of the White Tiger",
    "34011906":  "Exército de Portugal",
    "11392538":  "Real Armada Portuguesa",
    "34460157":  "Brigada Real da Marinha",
    "35181462":  "Corpo Real de Cavalaria",
    "35613090":  "Guarda Real da Polícia de Lisboa",
    "35001756":  "Corte Real Portuguesa",
}

NEUTRAL_GROUP_IDS: dict[str, str] = {
    "5826061":   "United States Army",
    "10822431":  "US Marine Corps",
    "175161616": "General Society of the War of 1812",
    "61813207":  "U.S. Artillery Corps",
    "35683824":  "U.S. Ranger Regiment",
    "35281366":  "United States Cavalry Detachment",
    "17394192":  "Brown's First Brigade",
    "33704866":  "Ripley's 2nd Brigade",
    "32950259":  "Devlet-i Aliyye-i Osmâniyye",
    "36056277":  "Kapıkulu Ocağı",
    "17018827":  "Nizâm-ı Cedîd Ordu",
}

# ============================================================
#  BRIGADE & REGIMENT CONFIGURATION
# ============================================================

BRIGADES: list[str] = [
    "BRIGADE KELLERMANN",
    "BRIGADE LASALLE",
    "BRIGADE BESSIÈRES",
]

# Maps brigade → ordered list of regiment tab keys shown in the dropdown.
# To add a new regiment: append its tab key here and add entries below.
BRIGADE_TO_REGIMENT_TABS: dict[str, list[str]] = {
    "BRIGADE KELLERMANN": ["26e"],                  # add more tab keys here as needed
    "BRIGADE LASALLE":    ["5e", "7e", "10e"],      # 10e has no sheet tab yet
    "BRIGADE BESSIÈRES":  ["GaC", "CaC"],           # CaC has no sheet tab yet
}

# Human-readable dropdown label for each regiment tab key.
# To add a new regiment: add its tab key → display label here.
REGIMENT_TO_TAB_LABEL: dict[str, str] = {
    "26e": "26e Chasseurs à Cheval de Ligne",
    "5e":  "5e Chevaux Légers Lanciers",
    "7e":  "7e Cuirassiers",
    "10e": "10e Régiment de Hussards",
    "GaC": "Grenadiers-à-Cheval de la Garde",
    "CaC": "Chasseurs-à-Cheval de la Garde",
}

# Maps regiment tab key → Discord role name assigned on draft.
# To add a new regiment: add its tab key → Discord role name here.
TAB_TO_DISCORD_ROLE: dict[str, str] = {
    "26e": "26ème Régiment de Chasseurs à Cheval",
    "5e":  "5ème Chevau-Légers Lanciers",
    "7e":  "7ème Cuirassiers",
    "10e": "10ème Régiment de Hussards",
    "GaC": "Grenadiers à Cheval de la Garde Impériale",
    "CaC": "Chasseurs à Cheval de la Garde",
}

ALL_BRIGADE_ROLES:  set[str] = set(BRIGADES)
ALL_REGIMENT_ROLES: set[str] = set(TAB_TO_DISCORD_ROLE.values())

# Legacy alias kept so sheet_sync imports still resolve.
BRIGADE_REGIMENTS: dict[str, list[str]] = {
    brigade: [TAB_TO_DISCORD_ROLE[tab] for tab in tabs if tab in TAB_TO_DISCORD_ROLE]
    for brigade, tabs in BRIGADE_TO_REGIMENT_TABS.items()
}

# ============================================================
#  RANK CONFIGURATION
# ============================================================

DISCORD_RANKS: list[str] = [
    "Conscrit",                       # 0
    "Veteran",                        # 1
    "Cavalier",                       # 2
    "Brigadier",                      # 3
    "Brigadier-Fourrier",             # 4
    "Maréchal des Logis",             # 5
    "Maréchal des Logis-Chef",        # 6  ← SENIOR_THRESHOLD
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
SENIOR_THRESHOLD = DISCORD_RANKS.index("Maréchal des Logis-Chef")

SENIOR_PROMOTER_ROLES: set[str] = {
    "Administration Team",
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
    "Géneral de Brigade",
    "Général de Division",
    "Maréchal",
    "Maréchal en Major Général",
    "Napoléon",
    "Super Admin",
}

# ============================================================
#  ROBLOX GROUP RANK PROGRESSION (for /promote draft)
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
#  SHEET SYNC CONFIGURATION & ROLE MAPPINGS
#
#  Three separate mappings, one per spreadsheet tab:
#    MEDAL_AWARD_MAP      — MedalsRoster tab
#    VENERATION_ROLE_MAP  — Venerations tab  (sheet Rank int → Discord role)
#    NOBILITY_ROLE_MAP    — Nobility tab     (sheet grade → Discord role + nick prefix)
# ============================================================

# ── MedalsRoster mapping ─────────────────────────────────────
# Keys are built by the loader as: f"{category} {tier}" — exactly what the sheet
# stores across col 7 (category) and col 8 (tier).  The right-hand value is the
# Discord role name to assign.
#
# Category names are taken verbatim from the sheet (including typos like
# "Battaile", "Initiaf", "Sociaux") so the keys match without normalisation.
MEDAL_AWARD_MAP: dict[str, str] = {
    # ── Légion d'Honneur ─────────────────────────────────────
    "Légion d'Honneur Légionnaire":    "Légionnaire de la Légion d'Honneur",
    "Légion d'Honneur Chevalier":      "Chevalier de la Légion d'Honneur",
    "Légion d'Honneur Officier":       "Officier de la Légion d'Honneur",
    "Légion d'Honneur Commandeur":     "Commandeur de la Légion d'Honneur",
    "Légion d'Honneur Grand Officier": "Grand Officier de la Légion d'Honneur",
    "Légion d'Honneur Grand Aigle":    "Grand Aigle de la Légion d'Honneur",

    # ── Ordre de la Fidèle ────────────────────────────────────
    "Ordre de la Fidèle Légionnaire": "Légionnaire de l'Ordre de la Fidèle",
    "Ordre de la Fidèle Officier":    "Officier de l'Ordre de la Fidèle",
    "Ordre de la Fidèle Commandeur":  "Commandeur de l'Ordre de la Fidèle",

    # ── Ordre de l'Aigle Impériale ───────────────────────────
    "Ordre de l'Aigle Impériale Légionnaire": "Légionnaire de l'Ordre de l'Aigle Impériale",
    "Ordre de l'Aigle Impériale Officier":    "Officier de l'Ordre de l'Aigle Impériale",
    "Ordre de l'Aigle Impériale Commandeur":  "Commandeur de l'Ordre de l'Aigle Impériale",
    "Ordre de l'Aigle Impériale Grand Aigle": "Grand Aigle de l'Ordre de l'Aigle Impériale",

    # ── Ordre de la Couronne de Fer ──────────────────────────
    "Ordre de la Couronne de Fer Légionnaire": "Légionnaire de l'Ordre de la Couronne de Fer",
    "Ordre de la Couronne de Fer Officier":    "Officier de l'Ordre de la Couronne de Fer",

    # ── Ordre du Mérite de l'Athenmatique ────────────────────
    "Ordre du Mérite de l'Athenmatique Légionnaire": "Légionnaire de l'Ordre du Mérite de l'Athenmatique",
    "Ordre du Mérite de l'Athenmatique Officier":    "Officier de l'Ordre du Mérite de l'Athenmatique",
    "Ordre du Mérite de l'Athenmatique Commandeur":  "Commandeur de l'Ordre du Mérite de l'Athenmatique",
    "Ordre du Mérite de l'Athenmatique de Bronze":   "de Bronze de l'Ordre du Mérite de l'Athenmatique",

    # ── Ordre des Deux Siciles ───────────────────────────────
    "Ordre des Deux Siciles Légionnaire": "Légionnaire de l'Ordre des Deux Siciles",
    "Ordre des Deux Siciles Commandeur":  "Commandeur de l'Ordre des Deux Siciles",
    "Ordre des Deux Siciles Grand Aigle": "Grand Aigle de l'Ordre des Deux Siciles",

    # ── Ordre van de Unie ────────────────────────────────────
    "Ordre van de Unie Légionnaire": "Légionnaire de l'Ordre van de Unie",
    "Ordre van de Unie Commandeur":  "Commandeur de l'Ordre van de Unie",
    "Ordre van de Unie Grand Aigle": "Grand Aigle de l'Ordre van de Unie",

    # ── Premier Mérite ───────────────────────────────────────
    "Premier Mérite Légionnaire": "Légionnaire du Premier Mérite",
    "Premier Mérite Officier":    "Officier du Premier Mérite",
    "Premier Mérite Commandeur":  "Commandeur du Premier Mérite",
    "Premier Mérite de Bronze":   "de Bronze du Premier Mérite",

    # ── Deuxième Mérite ──────────────────────────────────────
    "Deuxième Mérite Légionnaire": "Légionnaire du Deuxième Mérite",
    "Deuxième Mérite Officier":    "Officier du Deuxième Mérite",
    "Deuxième Mérite Commandeur":  "Commandeur du Deuxième Mérite",

    # ── Cinquième Ordre du Mérite ────────────────────────────
    "Cinquième Ordre du Mérite Légionnaire": "Légionnaire du Cinquième Ordre du Mérite",
    "Cinquième Ordre du Mérite Officier":    "Officier du Cinquième Ordre du Mérite",
    "Cinquième Ordre du Mérite Commandeur":  "Commandeur du Cinquième Ordre du Mérite",
    "Cinquième Ordre du Mérite de Bronze":   "de Bronze du Cinquième Ordre du Mérite",

    # ── Neuvième Mérite ──────────────────────────────────────
    "Neuvième Mérite Légionnaire": "Légionnaire du Neuvième Mérite",
    "Neuvième Mérite Officier":    "Officier du Neuvième Mérite",
    "Neuvième Mérite Commandeur":  "Commandeur du Neuvième Mérite",

    # ── Médaille du Croix de Battaile (sheet spelling) ───────
    "Médaille du Croix de Battaile de Bronze": "Médaille de la Croix de Bataille de Bronze",
    "Médaille du Croix de Battaile d'Argent":  "Médaille de la Croix de Battaille d'Argent",
    "Médaille du Croix de Battaile d'Or":      "Médaille de la Croix de Bataille d'Or",

    # ── Médaille du Mérite Militaire ─────────────────────────
    "Médaille du Mérite Militaire de Bronze": "Médaille du Mérite Militaire de Bronze",
    "Médaille du Mérite Militaire d'Argent":  "Médaille du Mérite Militaire d'Argent",
    "Médaille du Mérite Militaire d'Or":      "Médaille du Mérite Militaire d'Or",

    # ── Médaille du Mérite Commandant ────────────────────────
    "Médaille du Mérite Commandant de Bronze": "Médaille du Mérite Commandant de Bronze",
    "Médaille du Mérite Commandant d'Argent":  "Médaille du Mérite Commandant d'Argent",
    "Médaille du Mérite Commandant d'Or":      "Médaille du Mérite Commandant d'Or",

    # ── Médaille du Mérite Initiaf (sheet spelling) ──────────
    "Médaille du Mérite Initiaf de Bronze": "Médaille du Mérite Initiatif de Bronze",
    "Médaille du Mérite Initiaf d'Argent":  "Médaille du Mérite Initiatif d'Argent",
    "Médaille du Mérite Initiaf d'Or":      "Médaille du Mérite Initiatif d'Or",

    # ── Médaille du Mérite Artistique ────────────────────────
    "Médaille du Mérite Artistique de Bronze": "Médaille du Mérite Artistique de Bronze",
    "Médaille du Mérite Artistique d'Argent":  "Médaille du Mérite Artistique d'Argent",
    "Médaille du Mérite Artistique d'Or":      "Médaille du Mérite Artistique d'Or",

    # ── Médaille du Mérite Porte-Aigle ───────────────────────
    "Médaille du Mérite Porte-Aigle de Bronze": "Médaille du Mérite Porte-Aigle de Bronze",
    "Médaille du Mérite Porte-Aigle d'Argent":  "Médaille du Mérite Porte-Aigle d'Argent",
    "Médaille du Mérite Porte-Aigle d'Or":      "Médaille du Mérite Porte-Aigle d'Or",

    # ── Médaille du Mérite en Recrutement ────────────────────
    "Médaille du Mérite en Recrutement de Bronze": "Médaille du Mérite en Recrutement de Bronze",
    "Médaille du Mérite en Recrutement d'Argent":  "Médaille du Mérite en Recrutement d'Argent",
    "Médaille du Mérite en Recrutement d'Or":      "Médaille du Mérite en Recrutement d'Or",

    # ── Médaille du Mérite Sociaux (sheet spelling) ──────────
    "Médaille du Mérite Sociaux d'Argent":  "Médaille du Mérite Social d'Argent",

    # ── Médaille du Mérite Alliance ──────────────────────────
    "Médaille du Mérite Alliance de Bronze": "Médaille du Mérite Alliance de Bronze",
    "Médaille du Mérite Alliance d'Argent":  "Médaille du Mérite Alliance d'Argent",

    # ── Médaille du Mérite Developpement ─────────────────────
    "Médaille du Mérite Developpement de Bronze": "Médaille du Mérite Developpement de Bronze",
    "Médaille du Mérite Developpement d'Argent":  "Médaille du Mérite Developpement d'Argent",

    # ── Médaille Campagne d'Autriche (sheet spelling) ────────
    "Médaille Campagne d'Autriche de Bronze": "Médaille de la Campagne d'Autriche de Bronze",
    "Médaille Campagne d'Autriche d'Argent":  "Médaille de la Campagne d'Autriche d'Argent",
    "Médaille Campagne d'Autriche d'Or":      "Médaille de la Campagne d'Autriche d'Or",

    # ── Médaille de la Campagne d'Allemagne ──────────────────
    "Médaille de la Campagne d'Allemagne de Bronze": "Médaille de la Campagne d'Allemagne de Bronze",
    "Médaille de la Campagne d'Allemagne d'Argent":  "Médaille de la Campagne d'Allemagne d'Argent",
    "Médaille de la Campagne d'Allemagne d'Or":      "Médaille de la Campagne d'Allemagne d'Or",

    # ── Médaille Campagne d'Italie ───────────────────────────
    "Médaille Campagne d'Italie de Bronze": "Médaille de la Campagne d'Italie de Bronze",
    "Médaille Campagne d'Italie d'Argent":  "Médaille de la Campagne d'Italie d'Argent",
    "Médaille Campagne d'Italie d'Or":      "Médaille de la Campagne d'Italie d'Or",

    # ── Médaille de l'Indéfectible ───────────────────────────
    "Médaille de l'Indéfectible Légionnaire": "Médaille de l’Indéfectible",

    # ── Médaille Campagne d'Egypte ───────────────────────────
    "Médaille Campagne d'Egypte Légionnaire": "Médaille Campagne d'Egypte",

    # ── Pendantif Benevole ───────────────────────────────────
    "Pendantif Benevole de Bronze":        "Pendantif Benevole de Bronze",
    "Pendantif Benevole d'Argent":         "Pendantif Benevole d'Argent",
    "Pendantif Benevole d'Or":             "Pendantif Benevole d'Or",
    "Pendantif Benevole (Italy) de Bronze":"Pendantif Benevole (Italy) de Bronze",

    # ── Pendantif d'Elite ────────────────────────────────────
    "Pendantif d'Elite de Bronze": "Pendantif d'Elite de Bronze",

    # ── Croix de la Troisième Valliance ─────────────────────
    "Croix de la Troisième Valliance Légionnaire": "Légionnaire de la Croix de la Troisième Valliance",
    "Croix de la Troisième Valliance Officier":    "Officier de la Croix de la Troisième Valliance",
    "Croix de la Troisième Valliance Commandeur":  "Commandeur de la Croix de la Troisième Valliance",

    # ── Pendantif Mont-Saint-Jean ────────────────────────────
    "Pendantif Mont-Saint-Jean de Bronze": "Pendantif Mont-Saint-Jean de Bronze",
}

# ── Venerations mapping ──────────────────────────────────────
# Keys are string forms of the integer Rank stored in the sheet's "Rank" column.
VENERATION_ROLE_MAP: dict[str, str] = {
    "1":  "First Veneration (3 Months)",
    "2":  "Second Veneration (6 Months)",
    "3":  "Third Veneration (9 Months)",
    "4":  "Fourth Veneration (12 Months)",
    "5":  "Fifth Veneration (15 Months)",
    "6":  "Sixth Veneration (18 Months)",
    "7":  "Seventh Veneration (21 Months)",
    "8":  "Eighth Veneration (24 Months)",
    "9":  "Ninth Veneration (27 Months)",
    "10": "Tenth Veneration (30 Months)",
    "11": "Eleventh Veneration (33 Months)",
    "12": "Twelfth Veneration (36 Months)",
}
VENERATION_ACTIVE_STATUSES: set[str] = {"approved", "active"}

# ── Nobility mapping ─────────────────────────────────────────
# Ordered lowest → highest tier so tier-precedence works (higher tier wins).
# Keys match the grade value in the sheet's second data column.
# Values: (Discord role name, nick_format)
#   nick_format uses {username} as a placeholder for the Roblox username.
#   Chevalier:  "Sir {username}, Chevalier"
#   Baron:      "Baron {username}"
#   Comte:      "Comte {username}"
#   Duc:        "Duc {username}"
NOBILITY_ROLE_MAP: dict[str, tuple[str, str]] = {
    "Chevalier": ("Chevalier d'Empire", "Sir {username}, Chevalier"),
    "Baron":     ("Baron d'Empire",     "Baron {username}"),
    "Comte":     ("Comte d'Empire",     "Comte {username}"),
    "Duc":       ("Duc d'Empire",       "Duc {username}"),
}

def format_nobility_nick(grade: str, username: str) -> str:
    """Return the full nobility nickname for a given grade and Roblox username."""
    _, fmt = NOBILITY_ROLE_MAP.get(grade, ("", "{username}"))
    return fmt.format(username=username)[:32]

def strip_nobility_nick(nick: str) -> str:
    """Strip any nobility title formatting from a nickname, returning the bare username."""
    # Chevalier format: "Sir X, Chevalier" → "X"
    import re as _re
    m = _re.match(r"^Sir (.+), Chevalier$", nick)
    if m:
        return m.group(1)
    # Prefixed formats: "Baron X", "Comte X", "Duc X"
    for _grade, (_role, fmt) in NOBILITY_ROLE_MAP.items():
        prefix = fmt.split("{username}")[0]
        if prefix and nick.startswith(prefix):
            return nick[len(prefix):]
    return nick

# Kept for backward-compat — maps Discord role name → grade key
NOBILITY_PREFIXES: dict[str, str] = {
    role: grade for grade, (role, _fmt) in NOBILITY_ROLE_MAP.items()
}

# All Discord roles that originate from sheet data (used by PURGE_ROLES)
ALL_SHEET_ROLES: set[str] = (
    set(MEDAL_AWARD_MAP.values())
    | set(VENERATION_ROLE_MAP.values())
    | {role for _grade, (role, _fmt) in NOBILITY_ROLE_MAP.items()}
)

# ============================================================
#  INDUCT / PURGE ROLE LISTS
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
    # Strip all rank roles so re-induction always resets to a clean Cavalier state.
    *DISCORD_RANKS,
    *BRIGADES,
]

CAV_INDUCT_ROBLOX_RANK = "BRIGADE KELLERMANN"

PURGE_ROLES: set[str] = (
    ALL_RANK_ROLES | ALL_BRIGADE_ROLES | ALL_REGIMENT_ROLES | ALL_SHEET_ROLES
    | {"Corps de Cavalerie Impériale", "Verified", "Garde Nationale de Cavalerie",
       "Citoyen", "Soldat", "Caporal", "Caporal Fourrier"}
)

PURGED_ROLE = "Purged"

# ============================================================
#  COMMAND PERMISSIONS
# ============================================================

_STAFF_ROLES: set[str] = {
    "Head of Recruitment"
    "Administration Team",
    "Head of Administration",
    "Cavalerie Petit État-major"
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
    "Géneral de Brigade",
    "Général de Division",
    "Maréchal",
    "Maréchal en Major Général",
    "Napoléon",
    "Super Admin",
}

COMMAND_PERMISSIONS: dict[str, set[str]] = {
    "background-check": {"@everyone"},
    "induct": {"Recruitment Team"} | _STAFF_ROLES,
    "purge": SENIOR_PROMOTER_ROLES,
    "promote": _STAFF_ROLES,
    "medal-sync": {"@everyone"},
    "export-rosters": _STAFF_ROLES,
}

# ============================================================
#  CACHE
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
    verified_cache[str(discord_id)] = {
        "roblox_id": str(roblox_id),
        "roblox_username": username,
        "discord_username": discord_username,
        "cached_at": datetime.now(timezone.utc).isoformat(),
    }
    await _save_cache()
    log.info(f"[CACHE] Cached {discord_id} → {username}")

# ============================================================
#  ROBLOX REST HELPERS
# ============================================================

async def roblox_get_user_info(roblox_id: str) -> dict:
    async with ROBLOX_SEMAPHORE:
        try:
            r = await get_http().get(f"https://roblox-proxy.christiansuy25.workers.dev/users/v1/users/{roblox_id}")
            if r.status_code != 200:
                print(f"[ROBLOX] roblox_get_user_info {roblox_id} HTTP {r.status_code}: {r.text[:100]}")
                return {}
            data = r.json()
        except Exception as e:
            print(f"[ROBLOX] roblox_get_user_info {roblox_id} {type(e).__name__}: {e!r}")
            return {}
    account_age, created_str = "Unknown", data.get("created", "")
    if created_str:
        try:
            dt = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
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
    return (await roblox_get_user_info(roblox_id)).get("name") or None

async def roblox_get_previous_usernames(roblox_id: str) -> str:
    async with ROBLOX_SEMAPHORE:
        try:
            r = await get_http().get(f"https://roblox-proxy.christiansuy25.workers.dev/users/v1/users/{roblox_id}/username-history?limit=10")
            if r.status_code != 200:
                return "None"
            names = [e["name"] for e in r.json().get("data", [])]
            return ", ".join(names) if names else "None"
        except Exception:
            return "None"

async def roblox_get_avatar_url(roblox_id: str) -> str | None:
    async with ROBLOX_SEMAPHORE:
        try:
            r = await get_http().get(
                f"https://roblox-proxy.christiansuy25.workers.dev/thumbnails/v1/users/avatar-headshot"
                f"?userIds={roblox_id}&size=150x150&format=Png&isCircular=false"
            )
            if r.status_code != 200:
                return None
            entries = r.json().get("data", [])
            return entries[0].get("imageUrl") if entries else None
        except Exception:
            return None

async def roblox_get_group_memberships(roblox_id: str) -> list[dict]:
    async with ROBLOX_SEMAPHORE:
        try:
            r = await get_http().get(f"https://roblox-proxy.christiansuy25.workers.dev/groups/v2/users/{roblox_id}/groups/roles")
            if r.status_code != 200:
                return []
            return [
                {"name": e["group"]["name"], "id": str(e["group"]["id"]), "rank": e["role"]["name"]}
                for e in r.json().get("data", [])
            ]
        except Exception as e:
            print(f"[ROBLOX] roblox_get_group_memberships error: {e!r}")
            return []

async def roblox_get_group_rank(roblox_id: str, group_id: str) -> str | None:
    for g in await roblox_get_group_memberships(roblox_id):
        if g["id"] == str(group_id):
            return g["rank"]
    return None

async def roblox_accept_join_request(roblox_id: str, group_id: str) -> bool:
    if not ROBLOX_OPEN_CLOUD:
        return False
    async with ROBLOX_SEMAPHORE:
        try:
            s = get_http()
            r = await s.get(
                f"https://roblox-proxy.christiansuy25.workers.dev/apis/cloud/v2/groups/{group_id}/join-requests",
                headers=_oc_headers(), params={"maxPageSize": 100},
            )
            if r.status_code != 200:
                return False
            data = r.json()
            request_path = next(
                (req.get("path") for req in data.get("groupJoinRequests", [])
                 if str(roblox_id) in req.get("user", "")), None,
            )
            if not request_path:
                return False
            r = await s.post(
                f"https://roblox-proxy.christiansuy25.workers.dev/apis/cloud/v2/{request_path}:accept",
                headers=_oc_headers(), json={},
            )
            return r.status_code in (200, 204)
        except Exception as e:
            print(f"[ROBLOX] accept_join_request error: {e!r}")
            return False

async def roblox_set_rank(roblox_id: str, group_id: str, rank_name: str) -> bool:
    if not ROBLOX_OPEN_CLOUD:
        return False
    async with ROBLOX_SEMAPHORE:
        try:
            s = get_http()
            all_roles, page_token = [], None
            while True:
                params = {"maxPageSize": 20}
                if page_token:
                    params["pageToken"] = page_token
                r = await s.get(
                    f"https://roblox-proxy.christiansuy25.workers.dev/apis/cloud/v2/groups/{group_id}/roles",
                    headers=_oc_headers(), params=params,
                )
                if r.status_code != 200:
                    return False
                rd = r.json()
                all_roles.extend(rd.get("groupRoles", []))
                page_token = rd.get("nextPageToken") or ""
                if not page_token:
                    break

            role_path = next(
                (role.get("path") for role in all_roles
                 if (role.get("displayName") or role.get("name") or "").strip().lower()
                 == rank_name.strip().lower()), None,
            )
            if not role_path:
                return False

            r = await s.get(
                f"https://roblox-proxy.christiansuy25.workers.dev/apis/cloud/v2/groups/{group_id}/memberships",
                headers=_oc_headers(),
                params={"filter": f"user == 'users/{roblox_id}'"},
            )
            if r.status_code != 200:
                return False
            memberships = r.json().get("groupMemberships", [])
            if not memberships:
                return False

            r = await s.patch(
                f"https://roblox-proxy.christiansuy25.workers.dev/apis/cloud/v2/{memberships[0]['path']}",
                headers=_oc_headers(), json={"role": role_path},
            )
            success = r.status_code in (200, 204)
            if success:
                log.info(f"[ROBLOX] Ranked {roblox_id} → '{rank_name}' in {group_id}")
            return success
        except Exception as e:
            print(f"[ROBLOX] roblox_set_rank error: {e!r}")
            return False

async def roblox_ban_user(roblox_id: str, group_id: str, reason: str = "Removed from Corps de Cavalerie Impériale") -> bool:
    """
    Kick a user from the Roblox group by deleting their membership via Open Cloud v2.
    No /bans endpoint exists in Roblox Open Cloud for groups — the only ToS-safe
    removal method is DELETE on the membership resource.
    Used by /purge and the auto-blacklist flow.
    """
    if not ROBLOX_OPEN_CLOUD:
        print(f"[PURGE/BAN] Aborted — ROBLOX_OPEN_CLOUD key not set.")
        return False
    async with ROBLOX_SEMAPHORE:
        try:
            base = "https://roblox-proxy.christiansuy25.workers.dev"
            # Step 1: look up the membership path for this user
            membership_url = (
                f"{base}/apis/cloud/v2/groups/{group_id}/memberships"
                f"?filter=user+%3D%3D+%27users%2F{roblox_id}%27"
            )
            print(f"[PURGE/BAN] GET membership for user {roblox_id} in group {group_id}")
            timeout = aiohttp.ClientTimeout(connect=10, sock_read=15)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(membership_url, headers=_oc_headers()) as r:
                    resp_text = await r.text()
                    print(f"[PURGE/BAN] Membership lookup → HTTP {r.status} | body: {resp_text[:200]}")
                    if r.status != 200:
                        log.error(f"[ROBLOX] Membership lookup failed for {roblox_id}: {r.status} - {resp_text}")
                        return False
                    data = await r.json(content_type=None)
                memberships = data.get("groupMemberships", [])
                if not memberships:
                    print(f"[PURGE/BAN] User {roblox_id} has no membership in group {group_id} — nothing to remove.")
                    return False
                membership_path = memberships[0].get("path", "")
                if not membership_path:
                    print(f"[PURGE/BAN] Empty membership path for {roblox_id} — cannot delete.")
                    return False

                # Step 2: DELETE the membership (kicks the user from the group)
                delete_url = f"{base}/apis/{membership_path}"
                print(f"[PURGE/BAN] DELETE {delete_url}")
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.delete(delete_url, headers=_oc_headers()) as r:
                        resp_text = await r.text()
                        print(f"[PURGE/BAN] Delete response → HTTP {r.status} | body: {resp_text}")
                        success = r.status in (200, 204)
                        if success:
                            log.info(f"[ROBLOX] Kicked user {roblox_id} from group {group_id} ({reason})")
                            print(f"[PURGE/BAN] ✅ User {roblox_id} removed from group {group_id}")
                        else:
                            log.error(f"[ROBLOX] Kick failed for {roblox_id}: {r.status} - {resp_text}")
                        return success
        except Exception as e:
            print(f"[PURGE/BAN] Exception: {e!r}")
            log.error(f"[ROBLOX] roblox_ban_user exception: {e!r}")
            return False


async def roblox_unban_user(roblox_id: str, group_id: str) -> bool:
    """
    Attempt to unban / re-admit a user to the Roblox group.
    NOTE: Roblox Open Cloud has no 'unban from group' endpoint.
    The /unban command exists for record-keeping; actual re-admission requires
    the user to send a new join request and an officer to accept it via /induct.
    This function is a no-op stub and always returns False to signal that.
    """
    print(f"[UNBAN] No Open Cloud endpoint exists to unban from a group. "
          f"User {roblox_id} must re-apply to group {group_id} manually.")
    log.warning(f"[ROBLOX] roblox_unban_user called for {roblox_id} — no OC endpoint available; manual re-induct required.")
    return False



# ============================================================
#  BLOXLINK
# ============================================================

async def resolve_roblox_user(discord_id: str) -> dict | None:
    cached = get_cached_user(discord_id)
    if cached:
        return cached
    if not BLOXLINK_API_KEY:
        return None
    try:
        async with aiohttp.ClientSession(timeout=HTTP_TIMEOUT) as s:
            async with s.get(
                f"https://api.blox.link/v4/public/guilds/{GUILD_ID}/discord-to-roblox/{discord_id}",
                headers={"Authorization": BLOXLINK_API_KEY},
            ) as r:
                if r.status != 200:
                    return None
                body      = await r.json()
                roblox_id = str(body.get("robloxID") or body.get("roblox_id", ""))
                # Bloxlink returns robloxID=0 (or syncError:0 message:"") for unverified users
                if not roblox_id or roblox_id == "0":
                    return None
    except Exception as e:
        print(f"[BLOXLINK] Exception: {e}")
        return None
    username = await roblox_get_username(roblox_id)
    if not username:
        return {"roblox_id": roblox_id, "roblox_username": f"Unknown ({roblox_id})"}
    guild = bot.get_guild(int(GUILD_ID))
    discord_mbr = guild.get_member(int(discord_id)) if guild else None
    await cache_user(discord_id, roblox_id, username, str(discord_mbr) if discord_mbr else "")
    return {"roblox_id": roblox_id, "roblox_username": username}

# ============================================================
#  STARTUP SYNC
# ============================================================

async def sync_verified_users() -> None:
    print("[SYNC] Starting verified-user sync…")
    guild = bot.get_guild(int(GUILD_ID))
    if not guild:
        return
    verified_role = discord.utils.get(guild.roles, name="Verified")
    if not verified_role:
        return
    to_sync = [m for m in verified_role.members if not get_cached_user(str(m.id))]
    print(f"[SYNC] {len(verified_cache)} cached | {len(to_sync)} to resolve")
    synced = failed = 0
    for member in to_sync:
        try:
            roblox = await resolve_roblox_user(str(member.id))
            if roblox and not roblox["roblox_username"].startswith("Unknown"):
                synced += 1
            else:
                failed += 1
            await asyncio.sleep(2)
        except Exception as e:
            failed += 1
            print(f"[SYNC] Error for {member.id}: {e}")
    print(f"[SYNC] Done — synced: {synced} | failed: {failed}")

# ============================================================
#  SHEET DATA LOADERS  (all synchronous — run in executor)
# ============================================================

def _col(headers: list, name: str) -> int:
    """Return the index of a column by name, or raise ValueError."""
    return headers.index(name)

def _safe_int(value) -> int | None:
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return None

def sheet_load_medals() -> dict[str, set[str]]:
    """Read MedalsRoster tab.

    Keyed by Roblox ID extracted from the 'Profile Link' column (col G, index 6).
    Format: https://www.roblox.com/users/<ID>/profile

    The sheet uses repeating column triplets for each medal category:
        [Category Label]  [" " (tier/value)]  [Stage]
    e.g.:
        H: "Légion d'Honneur"   I: " "   J: "Stage"
        K: "Ordre de la Fidèle" L: " "   M: "Stage"
        ... and so on.

    We scan for all such triplets and process each one.
    """
    result: dict[str, set[str]] = {}
    for ws in _get_worksheets("MedalsRoster"):
        try:
            rows = ws.get_all_values()
            if not rows:
                continue
            headers = rows[0]

            # Find the Profile Link column (col G = index 6)
            col_p = next(
                (i for i, h in enumerate(headers) if h.strip().lower() == "profile link"),
                None,
            )
            if col_p is None:
                log.warning("[SHEETS] MedalsRoster: no 'Profile Link' column found.")
                continue

            # Find all medal block triplets.
            # A block starts wherever we see a non-blank, non-metadata header
            # that is followed by a blank-ish header and then a "Stage" header.
            SKIP_HEADERS = {
                "username", "corps as recommended", "regiment as recommended",
                "profile link", "recommended by", "recommended reason", "recommended date",
            }
            blocks: list[tuple[int, int, int]] = []  # (col_category, col_value, col_stage)
            i = 0
            while i < len(headers) - 2:
                h = headers[i].strip()
                h_next = headers[i + 1].strip()
                h_stage = headers[i + 2].strip().rstrip(".").lower()
                if (
                    h != ""
                    and h.lower() not in SKIP_HEADERS
                    and h_next in ("", " ")
                    and h_stage == "stage"
                ):
                    blocks.append((i, i + 1, i + 2))
                    i += 3  # skip the whole triplet
                else:
                    i += 1

            if not blocks:
                log.warning(f"[SHEETS] MedalsRoster: no medal blocks found. Headers: {headers}")
                continue

            log.debug(f"[SHEETS] MedalsRoster: found {len(blocks)} medal block(s) at cols "
                      f"{[(b[0], b[1], b[2]) for b in blocks]}")

            for row in rows[1:]:
                if len(row) <= col_p:
                    continue
                profile_link = row[col_p].strip()
                m = re.search(r"/users/(\d+)/", profile_link)
                if not m:
                    continue
                roblox_id = m.group(1)

                for col_cat, col_val, col_stg in blocks:
                    # Check bounds
                    if len(row) <= col_stg:
                        continue

                    stage = row[col_stg].strip().rstrip(".").lower()
                    if stage != "approved":
                        continue

                    # Build the lookup key exactly as the map expects: "{category} {tier}"
                    category = row[col_cat].strip() if len(row) > col_cat else ""
                    award_val = row[col_val].strip()
                    if not award_val or not category:
                        continue

                    sheet_key = f"{category} {award_val}"
                    mapped = MEDAL_AWARD_MAP.get(sheet_key)

                    if not mapped:
                        log.debug(
                            f"[SHEETS][MEDALS] Unmapped sheet key '{sheet_key}' "
                            f"for Roblox ID '{roblox_id}' — add to MEDAL_AWARD_MAP if needed"
                        )
                        continue

                    result.setdefault(roblox_id, set()).add(mapped)

        except Exception as e:
            log.error(f"[SHEETS][MEDALS] sheet_load_medals error: {e}")
    return result

def sheet_load_venerations() -> dict[str, set[str]]:
    """Read Venerations tab → {roblox_id: {discord_role_name, …}}

    Columns (0-indexed):
      A=0 (notes)  B=1 (notes)  C=2 (notes)
      D=3 Username  E=4 Last Corps  F=5 Last Regiment
      G=6 Profile Link  H=7 Type  I=8 Rank  J=9 Status  K=10 Manually Closed
    Keyed by Roblox ID extracted from the Profile Link column.
    """
    result: dict[str, set[str]] = {}
    for ws in _get_worksheets("Venerations"):
        try:
            rows = ws.get_all_values()
            headers = rows[0] if rows else []
            # Locate columns by name, falling back to known indices if needed
            col_p = next((i for i, h in enumerate(headers) if h.strip().lower() == "profile link"), 6)
            col_r = next((i for i, h in enumerate(headers) if h.strip() == "Rank"), 8)
            col_s = next((i for i, h in enumerate(headers) if h.strip() == "Status"), 9)
            col_mc = next((i for i, h in enumerate(headers) if h.strip() == "Manually Closed"), -1)
            for row in rows[1:]:
                if len(row) <= max(col_p, col_r, col_s):
                    continue
                profile_link = row[col_p].strip()
                m = re.search(r"/users/(\d+)/", profile_link)
                if not m:
                    continue
                roblox_id = m.group(1)
                status = row[col_s].strip().lower()
                if col_mc >= 0 and len(row) > col_mc:
                    mc = str(row[col_mc]).strip().lower()
                    if mc in ("true", "1", "yes"):
                        continue
                if status not in VENERATION_ACTIVE_STATUSES:
                    continue
                rank = _safe_int(row[col_r])
                if rank is None:
                    continue
                role = VENERATION_ROLE_MAP.get(str(rank))
                if role:
                    result.setdefault(roblox_id, set()).add(role)
                else:
                    log.debug(f"[SHEETS][VENERATIONS] Unmapped rank '{rank}' for Roblox ID '{roblox_id}'")
        except Exception as e:
            log.error(f"[SHEETS][VENERATIONS] sheet_load_venerations error: {e}")
    return result

def sheet_load_nobility() -> tuple[dict[str, set[str]], dict[str, str]]:
    """Read Nobility tab → ({roblox_id: {discord_role, …}}, {roblox_id: grade})

    The second dict maps each Roblox ID to their highest-tier nobility grade key
    (e.g. "Chevalier", "Baron", "Comte", "Duc") so callers can use
    format_nobility_nick(grade, username) to build the correct nickname.

    Keyed by Roblox ID extracted from the Profile Link column (col G, index 6).
    """
    role_result: dict[str, set[str]] = {}
    grade_result: dict[str, str] = {}   # roblox_id -> highest grade key
    tiers = list(NOBILITY_ROLE_MAP.keys())  # ordered lowest to highest
    for ws in _get_worksheets("Nobility"):
        try:
            rows = ws.get_all_values()
            headers = rows[0] if rows else []
            col_p = next((i for i, h in enumerate(headers) if h.strip().lower() == "profile link"), 6)
            col_g = _col(headers, " ")        # sheet grade/class column has a space header
            col_s = _col(headers, "Stage")
            for row in rows[1:]:
                if len(row) <= max(col_p, col_g, col_s):
                    continue
                profile_link = row[col_p].strip()
                m = re.search(r"/users/(\d+)/", profile_link)
                if not m:
                    continue
                roblox_id = m.group(1)
                grade = row[col_g].strip()
                stage = row[col_s].strip().lower()
                if not roblox_id or stage != "approved":
                    continue
                entry = NOBILITY_ROLE_MAP.get(grade)
                if not entry:
                    log.debug(f"[SHEETS][NOBILITY] Unmapped grade '{grade}' for Roblox ID '{roblox_id}'")
                    continue
                discord_role, _fmt = entry
                role_result.setdefault(roblox_id, set()).add(discord_role)
                # Keep the highest-tier grade for this user
                existing_grade = grade_result.get(roblox_id)
                if existing_grade is None or tiers.index(grade) > tiers.index(existing_grade):
                    grade_result[roblox_id] = grade
        except Exception as e:
            log.error(f"[SHEETS][NOBILITY] sheet_load_nobility error: {e}")
    return role_result, grade_result

def sheet_load_all() -> tuple[
    dict[str, set[str]], # medals    {username_lower → {discord_role, …}}
    dict[str, set[str]], # venerations
    dict[str, set[str]], # nobility roles
    dict[str, str], # nobility grade keys (e.g. "Duc")
]:
    """Load all three active tabs from the French medals spreadsheet."""
    medals = sheet_load_medals()
    venerations = sheet_load_venerations()
    nobility_r, nobility_p = sheet_load_nobility()
    return medals, venerations, nobility_r, nobility_p

# ============================================================
#  SHEET WRITE HELPERS (Sync execution required)
# ============================================================

def append_to_blacklisted_sheet(username: str, roblox_id: str, discord_id: str, display_name: str):
    if not sheets_client: return
    try:
        ws = sheets_client.open_by_key(CAV_SPREADSHEET_ID).worksheet("Blacklisted")
        ws.append_row([
            username, 
            roblox_id, 
            discord_id, 
            display_name, 
            datetime.now(timezone.utc).isoformat()
        ])
    except Exception as e:
        log.error(f"[SHEETS] Error writing to Blacklisted tab: {e}")

# (duplicate sheet_load_all removed — canonical definition is in SHEET DATA LOADERS above)

# ============================================================
#  DISCORD HELPERS
# ============================================================

def get_highest_rank(member: discord.Member) -> str | None:
    best_idx, best_name = -1, None
    for role in member.roles:
        idx = DISCORD_RANK_INDEX.get(role.name)
        if idx is not None and idx > best_idx:
            best_idx, best_name = idx, role.name
    return best_name

def get_rank_index(member: discord.Member) -> int:
    return DISCORD_RANK_INDEX.get(get_highest_rank(member), -1)

def is_senior_promoter(member: discord.Member) -> bool:
    return any(r.name in SENIOR_PROMOTER_ROLES for r in member.roles)

def has_command_permission(interaction: discord.Interaction, command: str) -> bool:
    member  = interaction.guild.get_member(interaction.user.id)
    allowed = COMMAND_PERMISSIONS.get(command, set())
    return bool(member and any(r.name in allowed for r in member.roles))

def categorise_groups(groups: list[dict]) -> tuple[list[str], list[str], list[str]]:
    french, coalition, neutral = [], [], []
    for g in groups:
        gid, rank = g["id"], g["rank"]
        if gid in FRENCH_GROUP_IDS: french.append(f"{FRENCH_GROUP_IDS[gid]} — {rank}")
        elif gid in COALITION_GROUP_IDS: coalition.append(f"{COALITION_GROUP_IDS[gid]} — {rank}")
        elif gid in NEUTRAL_GROUP_IDS: neutral.append(f"{NEUTRAL_GROUP_IDS[gid]} — {rank}")
    return french, coalition, neutral

def truncate_field(lines: list[str], limit: int = 1020) -> str:
    if not lines:
        return "None"
    text = "\n".join(lines)
    return text[:limit] + "\n…" if len(text) > limit else text

MENTION_RE = re.compile(r"<@!?(\d+)>")

def parse_mentions(text: str) -> list[int]:
    return [int(m) for m in MENTION_RE.findall(text)]

# ============================================================
#  BOT + TASKS + EVENTS
# ============================================================

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

@tasks.loop(hours=6)
async def periodic_sync():
    await sync_verified_users()

@bot.event
async def on_ready():
    print(f"[BOT] Online as {bot.user} ({bot.user.id})")
    print(f"[CACHE] {len(verified_cache)} users loaded from disk.")
    try:
        guild  = discord.Object(id=int(GUILD_ID))
        bot.tree.copy_global_to(guild=guild)
        synced = await bot.tree.sync(guild=guild)
        print(f"[BOT] Synced {len(synced)} command(s).")
    except Exception as e:
        print(f"[BOT] Sync error: {e}")
    if not periodic_sync.is_running():
        periodic_sync.start()

    # ── Scan "the-yard" for members who were already there at startup ────────
    real_guild = bot.get_guild(int(GUILD_ID))
    if real_guild:
        yard_channel = discord.utils.get(real_guild.text_channels, name="the-yard")
        if yard_channel:
            bl_role = discord.utils.get(real_guild.roles, name=PURGED_ROLE)
            members_to_process = [
                m for m in real_guild.members
                if not m.bot
                and bl_role not in (m.roles if bl_role else [])
                and yard_channel.permissions_for(m).read_messages
            ]
            if members_to_process:
                print(
                    f"[AUTO-BLACKLIST] Scanning the-yard on startup — "
                    f"{len(members_to_process)} unblacklisted member(s) with access."
                )
                for member in members_to_process:
                    await _blacklist_member(member, real_guild, notify_channel=None)
                    await asyncio.sleep(1)   # gentle rate-limit between members
                print("[AUTO-BLACKLIST] Startup scan complete.")

@bot.event
async def on_member_update(before: discord.Member, after: discord.Member):
    verified_role = discord.utils.get(after.guild.roles, name="Verified")
    if not verified_role:
        return
    if verified_role in before.roles or verified_role not in after.roles:
        return
    print(f"[VERIFY] {after} just got Verified — caching…")
    await resolve_roblox_user(str(after.id))

@bot.event
async def on_message(message: discord.Message):
    await bot.process_commands(message)
    
    if message.author.bot:
        return

    # Auto-blacklist logic for "the-yard" channel
    if message.channel.name == "the-yard" and message.mentions:
        for member in message.mentions:
            await _blacklist_member(member, message.guild, message.channel)


async def _blacklist_member(
    member: discord.Member,
    guild: discord.Guild,
    notify_channel: discord.abc.Messageable | None = None,
) -> None:
    """Apply the full blacklist treatment to a single member.

    Called both from the on_message handler (new mentions) and from the
    on_ready scan (members already present in the-yard when the bot starts).
    """
    try:
        # 1. Assign Discord Blacklist Role
        bl_role = discord.utils.get(guild.roles, name=PURGED_ROLE)
        if bl_role and bl_role not in member.roles:
            await member.add_roles(bl_role, reason="Auto-blacklisted via the-yard")

        # 2. Get Roblox ID and Kick from Cav Group
        roblox = await resolve_roblox_user(str(member.id))
        roblox_id, username = "Unknown", "Unknown"
        if roblox:
            roblox_id = roblox.get("roblox_id", "Unknown")
            username = roblox.get("roblox_username", "Unknown")
            if roblox_id != "Unknown":
                await roblox_ban_user(roblox_id, CAV_GROUP_ID, reason="Auto-blacklisted via the-yard")

        # 3. Write data to the Spreadsheet
        if sheets_client:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                append_to_blacklisted_sheet,
                username,
                roblox_id,
                str(member.id),
                member.display_name,
            )

        msg = (
            f"✅ Auto-blacklisted **{member.display_name}** (Roblox: {username}). "
            f"Kicked from group and logged to the Cav spreadsheet."
        )
        log.info(f"[AUTO-BLACKLIST] {member} blacklisted (Roblox: {username})")
        if notify_channel:
            await notify_channel.send(msg)

    except Exception as e:
        log.error(f"[AUTO-BLACKLIST] Error processing {member}: {e}")
        if notify_channel:
            await notify_channel.send(f"❌ Error auto-blacklisting {member.display_name}: {e}")


# ============================================================
#  /export-rosters
# ============================================================

@bot.tree.command(name="export-rosters", description="Outputs the server rosters in a readable format.")
async def export_rosters(interaction: discord.Interaction):
    if not has_command_permission(interaction, "export-rosters"):
        await interaction.response.send_message("❌ You don't have permission.", ephemeral=True)
        return
        
    await interaction.response.defer()
    
    lines = ["**Corps de Cavalerie Impériale — Roster Export**\n"]
    guild = interaction.guild
    
    for brigade in BRIGADES:
        role = discord.utils.get(guild.roles, name=brigade)
        if role:
            # Sort members alphabetically by display name
            members = sorted([m.display_name for m in role.members], key=str.casefold)
            lines.append(f"🛡️ **{brigade}** ({len(members)} members)")
            if members:
                lines.append(", ".join(members))
            else:
                lines.append("*No members found.*")
            lines.append("") 
            
    response_text = "\n".join(lines)
    
    if not response_text.strip():
        await interaction.followup.send("No roster data could be found.")
        return

    # Safely chunk message output
    for i in range(0, len(response_text), 1900):
        await interaction.followup.send(response_text[i:i+1900])


# ============================================================
#  /background-check
# ============================================================

@bot.tree.command(name="background-check", description="Run a background check on one or more verified users.")
@app_commands.describe(users="Mention one or more users to check")
async def background_check(interaction: discord.Interaction, users: str):
    if not has_command_permission(interaction, "background-check"):
        await interaction.response.send_message("❌ You don't have permission.", ephemeral=True)
        return

    mentions = parse_mentions(users)
    print(f"[BG-CHECK] Invoked by {interaction.user} for {len(mentions)} target(s): {mentions}")
    if not mentions:
        await interaction.response.send_message(
            "❌ No valid members mentioned. Please @mention one or more users.",
            ephemeral=True,
        )
        return
    await interaction.response.defer()

    for discord_id in mentions:
        try:
            print(f"[BG-CHECK] Resolving Discord member {discord_id}…")
            member = interaction.guild.get_member(discord_id)
            print(f"[BG-CHECK] Resolving Roblox account for {discord_id}…")
            roblox = await resolve_roblox_user(str(discord_id))
            if not roblox:
                print(f"[BG-CHECK] No Bloxlink verification found for {discord_id}")
                await interaction.followup.send(f"❌ <@{discord_id}> is not verified with Bloxlink.")
                continue

            roblox_id = roblox["roblox_id"]
            print(f"[BG-CHECK] Roblox ID: {roblox_id} — fetching user info, groups, avatar…")
            user_info, prev_names, all_groups, avatar_url = await asyncio.gather(
                roblox_get_user_info(roblox_id),
                roblox_get_previous_usernames(roblox_id),
                roblox_get_group_memberships(roblox_id),
                roblox_get_avatar_url(roblox_id),
                return_exceptions=True,
            )
            if isinstance(user_info,  Exception): user_info  = {}
            if isinstance(prev_names, Exception): prev_names = "None"
            if isinstance(all_groups, Exception): all_groups = []
            if isinstance(avatar_url, Exception): avatar_url = None

            username = user_info.get("name") or roblox["roblox_username"]
            groups = all_groups if isinstance(all_groups, list) else []
            print(f"[BG-CHECK] Got {len(groups)} group memberships for {username}")

            french_rank = cav_rank = "Not a member"
            for g in groups:
                if g["id"] == str(FRENCH_MAIN_GROUP_ID): french_rank = g["rank"]
                if g["id"] == str(CAV_GROUP_ID):         cav_rank    = g["rank"]

            print(f"[BG-CHECK] Empire Français rank: {french_rank} | Cav rank: {cav_rank}")
            french, coalition, neutral = categorise_groups(groups)

            loop = asyncio.get_event_loop()
            _, nobility_p = await loop.run_in_executor(None, sheet_load_nobility)
            nobility_text = "None"
            nob_grade = nobility_p.get(roblox_id)  # highest grade key, e.g. "Duc"
            if nob_grade and member:
                title_role_name, _fmt = NOBILITY_ROLE_MAP[nob_grade]
                nobility_text = f"Title: **{nob_grade}** ({title_role_name})"
                disc_role = discord.utils.get(interaction.guild.roles, name=title_role_name)
                if disc_role and disc_role not in member.roles:
                    try:
                        await member.add_roles(disc_role, reason="Nobility found in sheet")
                        nobility_text += " ✅ role assigned"
                    except discord.Forbidden:
                        nobility_text += " ⚠️ (could not assign role)"

                # Roblox username for nickname formatting
                roblox_username_for_nick = roblox.get("roblox_username", "") if roblox else username
                new_nick = format_nobility_nick(nob_grade, roblox_username_for_nick)
                current_nick = member.nick or member.display_name
                if current_nick != new_nick:
                    try:
                        await member.edit(nick=new_nick, reason="Nobility title applied")
                        nobility_text += f" ✅ nick → {new_nick}"
                    except discord.Forbidden:
                        nobility_text += " ⚠️ (could not update nick)"
                else:
                    nobility_text += " ✅ nick already correct"

            embed = discord.Embed(title="Background Check Results", color=discord.Color.dark_blue())
            if avatar_url:
                embed.set_thumbnail(url=avatar_url)
            embed.add_field(name="Account", value=f"<@{discord_id}>, {username}", inline=False)
            embed.add_field(name="Account Age", value=user_info.get("account_age", "Unknown"), inline=True)
            embed.add_field(name="Prev. Usernames", value=prev_names, inline=True)
            embed.add_field(name="Nobility", value=nobility_text, inline=False)
            embed.add_field(
                name="French Rankings",
                value=f"Empire Français — {french_rank}\nCorps de Cavalerie — {cav_rank}",
                inline=False,
            )
            embed.add_field(name=f"🇫🇷 French Empire & Clients ({len(french)})", value=truncate_field(french), inline=False)
            embed.add_field(name=f"⚔️ Coalition Powers ({len(coalition)})", value=truncate_field(coalition), inline=False)
            embed.add_field(name=f"🌐 Neutral Powers ({len(neutral)})", value=truncate_field(neutral), inline=False)
            embed.set_footer(text=f"Roblox ID: {roblox_id} • roblox.com/users/{roblox_id}/profile")
            await interaction.followup.send(embed=embed)
            print(f"[BG-CHECK] ✅ Done for {username} ({roblox_id})")
            log.info(f"[BG-CHECK] {username} ({roblox_id}) checked by {interaction.user}")

        except Exception as e:
            print(f"[BG-CHECK] ❌ Exception for {discord_id}: {type(e).__name__}: {e}")
            await interaction.followup.send(f"❌ Error checking <@{discord_id}>: {type(e).__name__}: {e}")
            log.error(f"[BG-CHECK] Error for {discord_id}: {e}")

# ============================================================
#  /induct
# ============================================================

@bot.tree.command(name="induct", description="Induct one or more recruits into the regiment.")
@app_commands.describe(users="Mention one or more users to induct")
async def induct(interaction: discord.Interaction, users: str):
    if not has_command_permission(interaction, "induct"):
        await interaction.response.send_message("❌ You don't have permission.", ephemeral=True)
        return
    await interaction.response.defer()

    mentions = parse_mentions(users)
    print(f"[INDUCT] Invoked by {interaction.user} for {len(mentions)} target(s): {mentions}")

    for discord_id in mentions:
        try:
            print(f"[INDUCT] Fetching member {discord_id}…")
            member = interaction.guild.get_member(discord_id)
            if not member:
                member = await asyncio.wait_for(interaction.guild.fetch_member(discord_id), timeout=10)

            print(f"[INDUCT] Resolving Roblox for {discord_id}…")
            roblox = await resolve_roblox_user(str(discord_id))
            if not roblox:
                print(f"[INDUCT] No Bloxlink verification for {discord_id}")
                err_embed = discord.Embed(
                    title="Induction Failed",
                    description=f"<@{discord_id}> is not verified with Bloxlink. Aborted.",
                    color=discord.Color.red(),
                )
                await interaction.followup.send(embed=err_embed)
                continue

            roblox_id  = roblox["roblox_id"]
            username   = roblox["roblox_username"]
            print(f"[INDUCT] Resolved: {username} (Roblox ID: {roblox_id})")
            avatar_url = await roblox_get_avatar_url(roblox_id)

            embed = discord.Embed(
                title="Induction Results",
                color=discord.Color.dark_blue(),
            )
            embed.set_author(name=f"{member.display_name} ({username})", icon_url=member.display_avatar.url)
            if avatar_url:
                embed.set_thumbnail(url=avatar_url)
            embed.add_field(name="Discord", value=f"<@{discord_id}>", inline=True)
            embed.add_field(name="Roblox", value=username, inline=True)
            status_lines: list[str] = []

            print(f"[INDUCT] Checking Cav group rank for {username}…")
            cav_rank = await roblox_get_group_rank(roblox_id, CAV_GROUP_ID)
            print(f"[INDUCT] Cav rank: {cav_rank!r}")
            if not cav_rank or cav_rank.lower() == "guest":
                print(f"[INDUCT] Accepting join request for {username}…")
                accepted = await asyncio.wait_for(
                    roblox_accept_join_request(roblox_id, CAV_GROUP_ID), timeout=15
                )
                print(f"[INDUCT] Join request accepted: {accepted}")
                if accepted:
                    status_lines.append("✅ Accepted into Corps de Cavalerie Impériale.")
                else:
                    status_lines.append("❌ No pending join request. Ask them to send one first. Aborted.")
                    embed.add_field(name="Status", value="\n".join(status_lines), inline=False)
                    embed.color = discord.Color.red()
                    embed.set_footer(text=f"Roblox ID: {roblox_id}")
                    await interaction.followup.send(embed=embed)
                    continue
            else:
                status_lines.append(f"⚠️ Already in Cav group as **{cav_rank}**.")

            if cav_rank and cav_rank.lower() == CAV_INDUCT_ROBLOX_RANK.lower():
                status_lines.append(f"⚠️ Already ranked **{CAV_INDUCT_ROBLOX_RANK}** in Roblox.")
            else:
                print(f"[INDUCT] Setting Roblox rank to {CAV_INDUCT_ROBLOX_RANK} for {username}…")
                try:
                    ranked = await asyncio.wait_for(
                        roblox_set_rank(roblox_id, CAV_GROUP_ID, CAV_INDUCT_ROBLOX_RANK), timeout=30,
                    )
                    print(f"[INDUCT] Roblox rank set: {ranked}")
                    status_lines.append(
                        f"✅ Ranked to **{CAV_INDUCT_ROBLOX_RANK}**." if ranked
                        else "❌ Failed to set Roblox rank — set manually."
                    )
                except asyncio.TimeoutError:
                    print(f"[INDUCT] ⚠️ Roblox rank request timed out for {username}")
                    status_lines.append("⚠️ Roblox rank request timed out — set manually.")

            guild = interaction.guild
            stripped = []
            for name in INDUCT_REMOVE:
                role = discord.utils.get(guild.roles, name=name)
                if role and role in member.roles:
                    await member.remove_roles(role)
                    stripped.append(name)
            status_lines.append(f"✅ Stripped: {', '.join(stripped)}" if stripped else "⚠️ No roles to strip.")

            added, missing = [], []
            for name in INDUCT_ADD:
                role = discord.utils.get(guild.roles, name=name)
                if role:
                    if role not in member.roles:
                        await member.add_roles(role)
                    added.append(name)
                else:
                    missing.append(name)
            if added:   status_lines.append(f"✅ Added: {', '.join(added)}")
            if missing: status_lines.append(f"❌ Not found in server: {', '.join(missing)}")

            new_nick = f"[26e] {username}"
            try:
                await member.edit(nick=new_nick)
                status_lines.append(f"✅ Nickname → **{new_nick}**")
            except discord.Forbidden:
                status_lines.append("⚠️ Cannot change nickname (bot role too low or server owner).")
            except discord.HTTPException as e:
                status_lines.append(f"⚠️ Nickname failed: {e.text}")

            embed.add_field(name="Actions", value="\n".join(status_lines), inline=False)
            embed.set_footer(text=f"Inducted by {interaction.user} • Roblox ID: {roblox_id}")
            print(f"[INDUCT] ✅ Done for {username} ({roblox_id})")
            log.info(f"[INDUCT] {username} inducted by {interaction.user}")

            # ── Sync to CAV roster spreadsheet ──────────────────────────────
            try:
                sheet_status_msg = await async_sync_induct(
                    discord_id=str(discord_id),
                    roblox_username=username,
                    regiment_full_name="26e Chasseurs a Cheval de Ligne",
                    rank_label="Cavalier",
                )
                print(f"[INDUCT] ✅ Sheet sync complete for {username}: {sheet_status_msg}")
            
            except Exception as _se:
                print(f"[INDUCT] ⚠️ Sheet sync failed for {username}: {_se}")
                log.error(f"[INDUCT] Sheet sync failed for {username}: {_se}")
                # Non-fatal — Roblox rank and Discord roles already applied.

        except asyncio.TimeoutError:
            print(f"[INDUCT] ❌ Timeout for {discord_id}")
            embed = discord.Embed(
                title="Induction Failed",
                description=f"❌ A request timed out for <@{discord_id}>.",
                color=discord.Color.red(),
            )
        except Exception as e:
            print(f"[INDUCT] ❌ Exception for {discord_id}: {type(e).__name__}: {e}")
            embed = discord.Embed(
                title="Induction Error",
                description=f"❌ Unexpected error for <@{discord_id}>: `{type(e).__name__}: {e}`",
                color=discord.Color.red(),
            )
            log.error(f"[INDUCT] Error for {discord_id}: {e}")

        status_lines.append(f"📊 {sheet_status_msg}")
        await interaction.followup.send(embed=embed)

# ============================================================
#  /purge
# ============================================================

@bot.tree.command(name="purge", description="Strip all roles, attempt to kick from Roblox group, and log purged member(s).")
@app_commands.describe(users="Mention one or more users to purge and blacklist")
async def purge(interaction: discord.Interaction, users: str):
    if not has_command_permission(interaction, "purge"):
        await interaction.response.send_message("❌ You don't have permission.", ephemeral=True)
        return

    mentions = parse_mentions(users)
    print(f"[PURGE] Invoked by {interaction.user} for {len(mentions)} target(s): {mentions}")
    if not mentions:
        await interaction.response.send_message("❌ No valid members mentioned.", ephemeral=True)
        return

    await interaction.response.send_message("⏳ Processing…", ephemeral=True)

    do_blacklist = True  # /purge always blacklists

    for discord_id in mentions:
        try:
            print(f"[PURGE] Processing target {discord_id}…")
            member = interaction.guild.get_member(discord_id)
            if not member:
                try:
                    member = await asyncio.wait_for(interaction.guild.fetch_member(discord_id), timeout=10)
                except Exception:
                    print(f"[PURGE] ❌ Could not find Discord member {discord_id}")
                    err_embed = discord.Embed(
                        title="Purge Failed",
                        description=f"❌ Could not find Discord member <@{discord_id}>.",
                        color=discord.Color.red(),
                    )
                    await interaction.followup.send(embed=err_embed)
                    continue

            print(f"[PURGE] Resolving Roblox for {discord_id}…")
            roblox = await resolve_roblox_user(str(discord_id))
            roblox_id = roblox["roblox_id"]  if roblox else None
            username  = roblox["roblox_username"] if roblox else None
            print(f"[PURGE] Roblox resolved: username={username!r}, roblox_id={roblox_id!r}")
            avatar_url = await roblox_get_avatar_url(roblox_id) if roblox_id else None

            embed = discord.Embed(
                title="Remove & Blacklist",
                color=discord.Color.dark_red(),
            )
            embed.set_author(
                name=f"{member.display_name}{' (' + username + ')' if username else ''}",
                icon_url=member.display_avatar.url,
            )
            if avatar_url:
                embed.set_thumbnail(url=avatar_url)
            embed.add_field(name="Discord", value=f"<@{discord_id}>", inline=True)
            if username:
                embed.add_field(name="Roblox", value=username, inline=True)

            status_lines: list[str] = []

            # ── Roblox Action (Kick vs Ban) ──────────────────────────────────
            if not roblox:
                print(f"[PURGE] No Bloxlink verification for {discord_id} — skipping Roblox action")
                status_lines.append("⚠️ Not verified with Bloxlink — skipping Roblox action.")
            else:
                print(f"[PURGE] Checking Cav group rank for Roblox ID {roblox_id}…")
                cav_rank = await roblox_get_group_rank(roblox_id, CAV_GROUP_ID)
                print(f"[PURGE] Cav rank: {cav_rank!r}")
                if not cav_rank:
                    print(f"[PURGE] User {roblox_id} not in Cav group — skipping Roblox action")
                    status_lines.append("⚠️ Not in Cav Roblox group — skipping Roblox action.")
                else:
                    ban_reason = "Purged & role stripped"
                    print(f"[PURGE] Banning {roblox_id} from group {CAV_GROUP_ID} (reason: {ban_reason})…")
                    processed = await asyncio.wait_for(
                        roblox_ban_user(roblox_id, CAV_GROUP_ID, reason=ban_reason),
                        timeout=30,
                    )
                    print(f"[PURGE] Ban result: {processed}")
                    status_lines.append(
                        "✅ Kicked from Corps de Cavalerie Impériale (Roblox)." if processed
                        else "❌ Failed to kick from Roblox group — handle manually."
                    )

            # ── Discord role strip ───────────────────────────────────────────
            print(f"[PURGE] Stripping Discord roles for {member}…")
            stripped = []
            for name in PURGE_ROLES:
                role = discord.utils.get(interaction.guild.roles, name=name)
                if role and role in member.roles:
                    await member.remove_roles(role)
                    stripped.append(name)
            print(f"[PURGE] Stripped {len(stripped)} role(s): {stripped}")
            status_lines.append(
                f"✅ Stripped {len(stripped)} role(s)." if stripped
                else "⚠️ No matching roles found to strip."
            )

            # ── Blacklist ────────────────────────────────────────────────────
            bl_role = discord.utils.get(interaction.guild.roles, name=PURGED_ROLE)
            if bl_role:
                if bl_role not in member.roles:
                    try:
                        await member.add_roles(bl_role, reason="Purged")
                        print(f"[PURGE] Added {PURGED_ROLE} to {member}")
                        status_lines.append(f"✅ Added **{PURGED_ROLE}**.")
                    except discord.Forbidden:
                        print(f"[PURGE] ⚠️ Forbidden adding {PURGED_ROLE} to {member}")
                        status_lines.append(f"⚠️ Could not add **{PURGED_ROLE}** — check bot role hierarchy.")
                else:
                    print(f"[PURGE] {member} already has {PURGED_ROLE}")
                    status_lines.append(f"⚠️ **{PURGED_ROLE}** already applied.")
            else:
                print(f"[PURGE] ⚠️ {PURGED_ROLE} role not found in server")
                status_lines.append(f"⚠️ **{PURGED_ROLE}** role not found in server.")

            # ── Roster sheet sync + Blacklisted log ──────────────────────────
            try:
                found = await async_sync_purge(
                    discord_id=str(discord_id),
                    roblox_username=username or "Unknown",
                    roblox_id=str(roblox_id) if roblox_id else "Unknown",
                    display_name=member.display_name,
                    purged=True,
                )
                if found:
                    status_lines.append("✅ Removed from roster sheet and logged to Purged tab.")
                    print(f"[PURGE] ✅ Sheet sync complete for {username or discord_id}")
                else:
                    status_lines.append("⚠️ Not found in roster sheet — remove manually if needed.")
                    print(f"[PURGE] ⚠️ {username or discord_id} not found in roster sheet")
            except Exception as _se:
                status_lines.append("⚠️ Roster sheet sync failed — update manually.")
                print(f"[PURGE] ⚠️ Sheet sync failed for {username or discord_id}: {_se}")
                log.error(f"[PURGE] Sheet sync failed for {username or discord_id}: {_se}")

            # ── Nickname reset ───────────────────────────────────────────────
            try:
                await member.edit(nick=None)
                print(f"[PURGE] Nickname reset for {member}")
                status_lines.append("✅ Nickname reset.")
            except discord.Forbidden:
                print(f"[PURGE] ⚠️ Cannot reset nickname for {member} (Forbidden)")
                status_lines.append("⚠️ Cannot reset nickname (bot role too low or server owner).")
            except discord.HTTPException as e:
                status_lines.append(f"⚠️ Nickname reset failed: {e.text}")

            embed.add_field(name="Actions", value="\n".join(status_lines), inline=False)
            embed.set_footer(
                text=f"Purged by {interaction.user}"
                     + (f" • Roblox ID: {roblox_id}" if roblox_id else "")
            )
            print(f"[PURGE] ✅ Done for {username or discord_id}")
            log.info(f"[PURGE] {member} purged & blacklisted by {interaction.user}")

        except asyncio.TimeoutError:
            print(f"[PURGE] ❌ Timeout for {discord_id}")
            embed = discord.Embed(
                title="Purge Failed",
                description=f"❌ A request timed out for <@{discord_id}>.",
                color=discord.Color.red(),
            )
        except Exception as e:
            print(f"[PURGE] ❌ Exception for {discord_id}: {type(e).__name__}: {e}")
            embed = discord.Embed(
                title="Purge Error",
                description=f"❌ Unexpected error for <@{discord_id}>: `{type(e).__name__}: {e}`",
                color=discord.Color.red(),
            )
            log.error(f"[PURGE] Error for {discord_id}: {e}")

        await interaction.followup.send(embed=embed)

# ============================================================
#  /medal-sync
#
#  Looks up each mentioned user in the French medals spreadsheet
#  (MedalsRoster, Venerations, Nobility tabs) by their Roblox username,
#  then grants every approved Discord role they are entitled to.
#
#  Terminal output  → print()  (visible in the console)
#  Persistent log   → log.*()  (written to bolt.log)
# ============================================================

@bot.tree.command(
    name="medal-sync",
    description="Sync medals, venerations, and nobility roles from the French spreadsheet.",
)
@app_commands.describe(users="Mention one or more members to sync (e.g. @Alice @Bob)")
@app_commands.default_permissions(manage_roles=True)
async def medal_sync(interaction: discord.Interaction, users: str):
    if not has_command_permission(interaction, "medal-sync"):
        await interaction.response.send_message("❌ You don't have permission.", ephemeral=True)
        return

    await interaction.response.defer()

    mentions = parse_mentions(users)
    if not mentions:
        await interaction.followup.send("❌ No valid members mentioned.")
        return

    # ── Load all three tabs from the spreadsheet (blocking I/O → executor) ──
    print(f"[MEDAL-SYNC] Initiated by {interaction.user} for {len(mentions)} member(s) — loading spreadsheet…")
    log.info(f"[MEDAL-SYNC] Run started by {interaction.user} | targets: {mentions}")

    loop = asyncio.get_event_loop()
    try:
        medals_data, veneration_data, nobility_roles, nobility_grades = await loop.run_in_executor(
            None, sheet_load_all
        )
    except Exception as exc:
        msg = f"❌ Failed to load spreadsheet data: {exc}"
        print(f"[MEDAL-SYNC] {msg}")
        log.error(f"[MEDAL-SYNC] Spreadsheet load failed: {exc}")
        await interaction.followup.send(msg)
        return

    print(
        f"[MEDAL-SYNC] Spreadsheet loaded — "
        f"{len(medals_data)} medal recipients | "
        f"{len(veneration_data)} veneration recipients | "
        f"{len(nobility_roles)} nobility recipients"
    )
    log.info(
        f"[MEDAL-SYNC] Sheet load complete — medals:{len(medals_data)} "
        f"venerations:{len(veneration_data)} nobility:{len(nobility_roles)}"
    )

    for discord_id in mentions:
        member = interaction.guild.get_member(discord_id)
        if not member:
            try:
                member = await asyncio.wait_for(
                    interaction.guild.fetch_member(discord_id), timeout=10
                )
            except Exception:
                err_embed = discord.Embed(
                    title="Medal Sync Failed",
                    description=f"❌ <@{discord_id}> — could not find in server.",
                    color=discord.Color.red(),
                )
                print(f"[MEDAL-SYNC] Member {discord_id} not found in guild.")
                log.warning(f"[MEDAL-SYNC] Member {discord_id} not found in guild.")
                await interaction.followup.send(embed=err_embed)
                continue

        # Resolve Roblox username via Bloxlink / cache
        roblox = await resolve_roblox_user(str(discord_id))
        if not roblox:
            err_embed = discord.Embed(
                title="Medal Sync Failed",
                description=f"❌ <@{discord_id}> is not verified with Bloxlink.",
                color=discord.Color.red(),
            )
            err_embed.set_author(name=member.display_name, icon_url=member.display_avatar.url)
            print(f"[MEDAL-SYNC] {member} has no Bloxlink verification.")
            log.warning(f"[MEDAL-SYNC] {member} has no Bloxlink verification.")
            await interaction.followup.send(embed=err_embed)
            continue

        roblox_username: str = roblox["roblox_username"]
        roblox_id_key:   str = roblox["roblox_id"]
        avatar_url = await roblox_get_avatar_url(roblox_id_key)

        print(
            f"[MEDAL-SYNC] Processing {member} (Roblox: {roblox_username}, ID: {roblox_id_key}) — "
            f"searching MedalsRoster, Venerations, Nobility…"
        )
        log.info(f"[MEDAL-SYNC] Processing {member} → Roblox '{roblox_username}' (id='{roblox_id_key}')")

        embed = discord.Embed(
            title="Medal Sync Results",
            color=discord.Color.dark_blue(),
        )
        embed.set_author(name=f"{member.display_name} ({roblox_username})", icon_url=member.display_avatar.url)
        if avatar_url:
            embed.set_thumbnail(url=avatar_url)
        embed.add_field(name="Discord", value=f"<@{discord_id}>", inline=True)
        embed.add_field(name="Roblox", value=roblox_username, inline=True)

        # ── Helper: assign a single Discord role ────────────────────────────
        async def assign_role(role_name: str, source_tag: str) -> str:
            disc_role = discord.utils.get(interaction.guild.roles, name=role_name)
            if not disc_role:
                msg = f"⚠️ **{role_name}** — not found in server."
                print(f"[MEDAL-SYNC]   MISSING ROLE: '{role_name}' ({source_tag}) for {roblox_username}")
                log.warning(f"[MEDAL-SYNC] Role '{role_name}' ({source_tag}) not in guild for '{roblox_username}'")
                return msg
            if disc_role in member.roles:
                msg = f"✅ **{role_name}** — already assigned."
                log.debug(f"[MEDAL-SYNC] '{roblox_username}' already has '{role_name}' ({source_tag})")
                return msg
            try:
                await member.add_roles(disc_role, reason=f"Medal sync ({source_tag})")
                msg = f"✅ **{role_name}** — granted."
                print(f"[MEDAL-SYNC]   GRANTED: '{role_name}' ({source_tag}) → {roblox_username}")
                log.info(f"[MEDAL-SYNC] Granted '{role_name}' ({source_tag}) to '{roblox_username}'")
                return msg
            except discord.Forbidden:
                msg = f"❌ **{role_name}** — missing permissions."
                print(f"[MEDAL-SYNC]   FORBIDDEN: '{role_name}' ({source_tag}) for {roblox_username}")
                log.error(f"[MEDAL-SYNC] Forbidden assigning '{role_name}' ({source_tag}) to '{roblox_username}'")
                return msg

        # ── Medals (MedalsRoster tab) ────────────────────────────────────────
        medal_roles = medals_data.get(roblox_id_key, set())
        if medal_roles:
            print(f"[MEDAL-SYNC]   MEDALS FOUND ({len(medal_roles)}): {medal_roles}")
            log.info(f"[MEDAL-SYNC] '{roblox_username}' medals from sheet: {medal_roles}")
            medal_lines = [await assign_role(rn, "Medals") for rn in sorted(medal_roles)]
            embed.add_field(
                name=f"🎖️ Medals ({len(medal_roles)} approved)",
                value=truncate_field(medal_lines),
                inline=False,
            )
        else:
            embed.add_field(name="🎖️ Medals", value="None found in MedalsRoster.", inline=False)
            print(f"[MEDAL-SYNC]   No medals found for '{roblox_username}' (ID: {roblox_id_key})")
            log.info(f"[MEDAL-SYNC] No medals found for '{roblox_username}' (ID: {roblox_id_key})")

        # ── Venerations (Venerations tab) ────────────────────────────────────
        veneration_role_set = veneration_data.get(roblox_id_key, set())
        if veneration_role_set:
            print(f"[MEDAL-SYNC]   VENERATIONS FOUND ({len(veneration_role_set)}): {veneration_role_set}")
            log.info(f"[MEDAL-SYNC] '{roblox_username}' venerations from sheet: {veneration_role_set}")
            ven_lines = [await assign_role(rn, "Venerations") for rn in sorted(veneration_role_set)]
            embed.add_field(
                name=f"🕯️ Venerations ({len(veneration_role_set)} approved)",
                value=truncate_field(ven_lines),
                inline=False,
            )
        else:
            embed.add_field(name="🕯️ Venerations", value="None found in Venerations tab.", inline=False)
            print(f"[MEDAL-SYNC]   No venerations found for '{roblox_username}' (ID: {roblox_id_key})")
            log.info(f"[MEDAL-SYNC] No venerations found for '{roblox_username}' (ID: {roblox_id_key})")

        # ── Nobility (Nobility tab) ──────────────────────────────────────────
        nob_roles = nobility_roles.get(roblox_id_key, set())
        nob_grade = nobility_grades.get(roblox_id_key)  # highest grade key, e.g. "Duc"
        if nob_roles:
            print(f"[MEDAL-SYNC]   NOBILITY FOUND ({len(nob_roles)}): {nob_roles} | grade='{nob_grade}'")
            log.info(f"[MEDAL-SYNC] '{roblox_username}' nobility from sheet: {nob_roles} grade='{nob_grade}'")
            nob_lines = [await assign_role(rn, "Nobility") for rn in sorted(nob_roles)]

            if nob_grade:
                new_nick = format_nobility_nick(nob_grade, roblox_username)
                current_nick = member.nick or member.display_name
                if current_nick != new_nick:
                    try:
                        await member.edit(nick=new_nick, reason="Medal sync: nobility title applied")
                        nob_lines.append(f"✅ Nickname updated → **{new_nick}**")
                        print(f"[MEDAL-SYNC]   NICK UPDATED: '{current_nick}' → '{new_nick}' for {roblox_username}")
                        log.info(f"[MEDAL-SYNC] Nick '{current_nick}' → '{new_nick}' for '{roblox_username}'")
                    except discord.Forbidden:
                        nob_lines.append("⚠️ Could not update nickname (bot role too low or server owner).")
                        log.warning(f"[MEDAL-SYNC] Cannot update nick for '{roblox_username}' (Forbidden)")
                else:
                    nob_lines.append(f"✅ Nickname already correct: **{new_nick}**")

            embed.add_field(
                name=f"👑 Nobility ({len(nob_roles)} approved)",
                value=truncate_field(nob_lines),
                inline=False,
            )
        else:
            embed.add_field(name="👑 Nobility", value="None found in Nobility tab.", inline=False)
            print(f"[MEDAL-SYNC]   No nobility found for '{roblox_username}'")
            log.info(f"[MEDAL-SYNC] No nobility found for '{roblox_username}'")

        embed.set_footer(text=f"Synced by {interaction.user} • Roblox ID: {roblox_id_key}")
        log.info(f"[MEDAL-SYNC] Finished processing '{roblox_username}' ({member})")
        print(f"[MEDAL-SYNC] Done: {roblox_username}")
        await interaction.followup.send(embed=embed)

    print(f"[MEDAL-SYNC] All done — results sent to Discord.")
    log.info(f"[MEDAL-SYNC] Run complete by {interaction.user}")

class PromoteTypeSelect(discord.ui.Select):
    def __init__(self):
        super().__init__(
            placeholder="Choose promotion type…", min_values=1, max_values=1,
            options=[
                discord.SelectOption(label="Rank Promotion", value="rank",
                                     description="Move target(s) up to a chosen Discord rank"),
                discord.SelectOption(label="Draft to Brigade", value="draft",
                                     description="Reset rank to Cavalier and move to a brigade"),
            ],
        )
    async def callback(self, interaction: discord.Interaction):
        self.view.promo_type = self.values[0]
        await interaction.response.defer()
        self.view.stop()

class TargetRankSelect(discord.ui.Select):
    def __init__(self, min_idx: int, max_idx: int):
        options = [
            discord.SelectOption(label=name, value=name)
            for i, name in enumerate(DISCORD_RANKS)
            if min_idx <= i <= max_idx
        ]
        super().__init__(placeholder="Select target rank…", min_values=1, max_values=1, options=options)
    async def callback(self, interaction: discord.Interaction):
        self.view.target_rank = self.values[0]
        await interaction.response.defer()
        self.view.stop()

class BrigadeSelect(discord.ui.Select):
    def __init__(self):
        super().__init__(
            placeholder="Select target brigade…", min_values=1, max_values=1,
            options=[discord.SelectOption(label=b, value=b) for b in BRIGADES],
        )
    async def callback(self, interaction: discord.Interaction):
        self.view.target_brigade = self.values[0]
        await interaction.response.defer()
        self.view.stop()

class RegimentSelect(discord.ui.Select):
    """Regiment selector shown when a brigade has multiple regiment tabs."""
    def __init__(self, tab_choices: list[str]):
        # Map tab name -> human-readable label using TAB_TO_REGIMENT
        options = [
            discord.SelectOption(
                label=REGIMENT_TO_TAB_LABEL.get(tab, tab),
                value=tab,
            )
            for tab in tab_choices
        ]
        super().__init__(placeholder="Select regiment…", min_values=1, max_values=1, options=options)
    async def callback(self, interaction: discord.Interaction):
        self.view.target_tab = self.values[0]
        await interaction.response.defer()
        self.view.stop()

class SingleSelectView(discord.ui.View):
    def __init__(self, select: discord.ui.Select, timeout: int = 60):
        super().__init__(timeout=timeout)
        self.promo_type: str | None = None
        self.target_rank: str | None = None
        self.target_brigade: str | None = None
        self.target_tab: str | None = None
        self.add_item(select)

# ============================================================
#  /promote - for moving between brigades and the like
# ============================================================

@bot.tree.command(name="promote", description="Promote member(s) by rank, or draft them to a brigade.")
@app_commands.describe(members="Mention one or more members to promote")
@app_commands.default_permissions(manage_roles=True)
async def promote(interaction: discord.Interaction, members: str):
    if not has_command_permission(interaction, "promote"):
        await interaction.response.send_message("❌ You don't have permission.", ephemeral=True)
        return

    targets = [interaction.guild.get_member(mid) for mid in parse_mentions(members)]
    targets = [t for t in targets if t is not None]
    if not targets:
        await interaction.response.send_message("❌ No valid members mentioned.", ephemeral=True)
        return

    print(f"[PROMOTE] Invoked by {interaction.user} | targets: {[str(t) for t in targets]}")

    exec_member  = interaction.guild.get_member(interaction.user.id)
    exec_idx     = get_rank_index(exec_member)
    senior       = is_senior_promoter(exec_member)
    min_exec_idx = DISCORD_RANK_INDEX.get("Adjudant Sous-Officier", 0)
    print(f"[PROMOTE] Executor rank index: {exec_idx}, senior: {senior}")

    if exec_idx < min_exec_idx and not senior:
        await interaction.response.send_message(
            "❌ You must hold at least **Adjudant Sous-Officier** to promote.", ephemeral=True
        )
        return

    type_view = SingleSelectView(PromoteTypeSelect())
    await interaction.response.send_message(
        "**Step 1:** What type of promotion is this?", view=type_view, ephemeral=True
    )
    await type_view.wait()
    if type_view.promo_type is None:
        await interaction.edit_original_response(content="⏱️ Timed out.", view=None)
        return

    if type_view.promo_type == "draft":
        print(f"[PROMOTE] Draft path selected")
        brigade_view = SingleSelectView(BrigadeSelect())
        await interaction.edit_original_response(
            content="**Step 2:** Select the brigade to draft target(s) into:", view=brigade_view
        )
        await brigade_view.wait()
        if brigade_view.target_brigade is None:
            await interaction.edit_original_response(content="⏱️ Timed out.", view=None)
            return

        target_brigade = brigade_view.target_brigade

        # Step 3: always ask which regiment within the brigade
        available_tabs = BRIGADE_TO_REGIMENT_TABS.get(target_brigade, [])
        reg_view = SingleSelectView(RegimentSelect(available_tabs))
        await interaction.edit_original_response(
            content="**Step 3:** Select the regiment to draft target(s) into:", view=reg_view
        )
        await reg_view.wait()
        if reg_view.target_tab is None:
            await interaction.edit_original_response(content="⏱️ Timed out.", view=None)
            return
        target_tab = reg_view.target_tab

        # The single Discord role to assign for the chosen regiment
        regiment_names = [TAB_TO_DISCORD_ROLE[target_tab]] if target_tab in TAB_TO_DISCORD_ROLE else []

        await interaction.edit_original_response(content="⏳ Processing draft…", view=None)

        async def draft_one(member: discord.Member) -> discord.Embed:
            print(f"[PROMOTE/DRAFT] Processing {member} → {target_brigade}")
            roblox = await resolve_roblox_user(str(member.id))
            roblox_id = roblox["roblox_id"]  if roblox else None
            username = roblox["roblox_username"] if roblox else None
            avatar_url = await roblox_get_avatar_url(roblox_id) if roblox_id else None
            print(f"[PROMOTE/DRAFT] Roblox resolved: {username!r} ({roblox_id!r})")

            if not roblox:
                print(f"[PROMOTE/DRAFT] ❌ No Roblox account for {member}")
                embed = discord.Embed(
                    title="Draft Failed",
                    description="❌ Could not resolve Roblox account.",
                    color=discord.Color.red(),
                )
                embed.set_author(name=member.display_name, icon_url=member.display_avatar.url)
                return embed

            errors: list[str] = []
            status_lines: list[str] = []
            guild = interaction.guild

            print(f"[PROMOTE/DRAFT] Setting Roblox rank → {target_brigade} for {username}")
            if not await roblox_set_rank(roblox_id, CAV_GROUP_ID, target_brigade):
                print(f"[PROMOTE/DRAFT] ❌ Failed to set Roblox rank for {username}")
                errors.append("failed to set Roblox brigade rank")
                status_lines.append("❌ Failed to set Roblox brigade rank — set manually.")
            else:
                print(f"[PROMOTE/DRAFT] ✅ Roblox rank set to {target_brigade} for {username}")
                status_lines.append(f"✅ Ranked to **{target_brigade}** in Roblox.")

            old_ranks     = [r for r in member.roles if r.name in ALL_RANK_ROLES]
            cavalier_role = discord.utils.get(guild.roles, name=DRAFT_RESET_RANK)
            try:
                if old_ranks:     await member.remove_roles(*old_ranks, reason="Draft: rank reset")
                if cavalier_role:
                    await member.add_roles(cavalier_role, reason=f"Draft → {target_brigade}")
                    status_lines.append(f"✅ Rank reset to **{DRAFT_RESET_RANK}**.")
                else:
                    errors.append(f"'{DRAFT_RESET_RANK}' role not found")
                    status_lines.append(f"❌ Role **{DRAFT_RESET_RANK}** not found in server.")
            except discord.Forbidden:
                errors.append("missing permissions for rank roles")
                status_lines.append("❌ Missing permissions to modify rank roles.")

            old_brigades     = [r for r in member.roles if r.name in ALL_BRIGADE_ROLES]
            new_brigade_role = discord.utils.get(guild.roles, name=target_brigade)
            try:
                if old_brigades:     await member.remove_roles(*old_brigades, reason="Draft: brigade swap")
                if new_brigade_role:
                    await member.add_roles(new_brigade_role, reason=f"Draft → {target_brigade}")
                    status_lines.append(f"✅ Brigade set to **{target_brigade}**.")
                else:
                    errors.append(f"'{target_brigade}' Discord role not found")
                    status_lines.append(f"❌ Role **{target_brigade}** not found in server.")
            except discord.Forbidden:
                errors.append("missing permissions for brigade roles")
                status_lines.append("❌ Missing permissions to modify brigade roles.")

            new_regiment_roles = [discord.utils.get(guild.roles, name=rn) for rn in regiment_names]
            new_regiment_roles = [r for r in new_regiment_roles if r is not None]
            new_regiment_role_names = {r.name for r in new_regiment_roles}
            # Strip all regiment roles except the one we're about to assign
            old_regiments = [r for r in member.roles
                             if r.name in ALL_REGIMENT_ROLES and r.name not in new_regiment_role_names]
            try:
                if old_regiments:      await member.remove_roles(*old_regiments, reason="Draft: regiment swap")
                if new_regiment_roles:
                    await member.add_roles(*new_regiment_roles, reason=f"Draft → {target_brigade}")
                    status_lines.append(f"✅ Regiments: {', '.join(regiment_names)}.")
            except discord.Forbidden:
                errors.append("missing permissions for regiment roles")
                status_lines.append("❌ Missing permissions to modify regiment roles.")

            # ── Update nickname regiment tag ─────────────────────────────────
            # Replace the old [tab] prefix in the nickname with the new one.
            # Preserve any nobility title formatting if present.
            if username:
                current_nick = member.nick or member.display_name
                # Strip any existing [tag] prefix, e.g. "[26e] ", "[7e] ", "[GaC] "
                import re as _re
                base_nick = _re.sub(r"^\[[^\]]+\]\s*", "", current_nick)
                new_nick = f"[{target_tab}] {base_nick}"[:32]
                try:
                    await member.edit(nick=new_nick, reason=f"Draft: regiment tag → [{target_tab}]")
                    status_lines.append(f"✅ Nickname → **{new_nick}**")
                    print(f"[PROMOTE/DRAFT] Nick updated: '{current_nick}' → '{new_nick}' for {username}")
                except discord.Forbidden:
                    status_lines.append("⚠️ Cannot update nickname (bot role too low or server owner).")
                except discord.HTTPException as _he:
                    status_lines.append(f"⚠️ Nickname update failed: {_he.text}")

            # ── Sync draft to CAV roster spreadsheet ────────────────────────
            # Moves the member's old regiment row to the target regiment tab
            # and updates the Stats map, preserving their original drafted date.
            if target_tab:
                try:
                    sheet_status_msg = await async_sync_promote_draft(
                        discord_id=str(member.id),
                        roblox_username=username or str(member.id),
                        target_brigade=target_brigade,
                        target_tab=target_tab,
                    )
                    print(f"[PROMOTE/DRAFT] ✅ Sheet sync complete for {username or member} → {target_tab}: {sheet_status_msg}")
                    status_lines.append(f"✅ Roster moved to **{target_tab}** tab: {sheet_status_msg}.")
                except Exception as _se:
                    print(f"[PROMOTE/DRAFT] ⚠️ Sheet sync failed for {username or member}: {_se}")
                    log.error(f"[PROMOTE/DRAFT] Sheet sync failed for {username or member}: {_se}")
                    status_lines.append("⚠️ Roster sheet sync failed — update manually.")
            else:
                print(f"[PROMOTE/DRAFT] ⚠️ No target_tab resolved for {target_brigade} — skipping sheet sync")
                status_lines.append("⚠️ No regiment tab resolved — update roster manually.")

            color = discord.Color.orange() if errors else discord.Color.dark_blue()
            embed = discord.Embed(title="Draft Results", color=color)
            embed.set_author(
                name=f"{member.display_name} ({username})",
                icon_url=member.display_avatar.url,
            )
            if avatar_url:
                embed.set_thumbnail(url=avatar_url)
            embed.add_field(name="Discord", value=f"<@{member.id}>", inline=True)
            embed.add_field(name="Roblox",  value=username, inline=True)
            embed.add_field(name="Actions", value="\n".join(status_lines), inline=False)
            tab_label = REGIMENT_TO_TAB_LABEL.get(target_tab or "", target_tab or target_brigade)
            embed.set_footer(text=f"Drafted by {interaction.user} • {tab_label} • Roblox ID: {roblox_id}")
            if not errors:
                log.info(f"[PROMOTE/DRAFT] {username} drafted → {target_brigade}/{target_tab} by {interaction.user}")
                print(f"[PROMOTE/DRAFT] ✅ {username} drafted → {target_brigade}/{target_tab}")
            else:
                print(f"[PROMOTE/DRAFT] ⚠️ {username} drafted with errors: {errors}")
            return embed

        async with asyncio.timeout(120):
            embeds = await asyncio.gather(*[draft_one(m) for m in targets])
        print(f"[PROMOTE/DRAFT] All drafts complete for {[str(t) for t in targets]}")
        await interaction.edit_original_response(content="✅ Draft complete.", view=None)
        for emb in embeds:
            await interaction.followup.send(embed=emb, ephemeral=False)
        return

    max_idx = len(DISCORD_RANKS) - 1 if senior else min(exec_idx - 1, SENIOR_THRESHOLD - 1)
    min_idx = 1
    if max_idx < min_idx:
        await interaction.edit_original_response(content="❌ Your rank is too low to promote anyone.", view=None)
        return

    rank_view = SingleSelectView(TargetRankSelect(min_idx, max_idx))
    await interaction.edit_original_response(
        content="**Step 2:** Select the rank to promote target(s) to:", view=rank_view
    )
    await rank_view.wait()
    if rank_view.target_rank is None:
        await interaction.edit_original_response(content="⏱️ Timed out.", view=None)
        return

    target_rank     = rank_view.target_rank
    target_rank_idx = DISCORD_RANK_INDEX[target_rank]
    print(f"[PROMOTE/RANK] Target rank selected: {target_rank} (idx {target_rank_idx})")
    await interaction.edit_original_response(content="⏳ Processing promotions…", view=None)

    async def promote_one(member: discord.Member) -> discord.Embed:
        print(f"[PROMOTE/RANK] Processing {member}…")
        roblox     = await resolve_roblox_user(str(member.id))
        roblox_id  = roblox["roblox_id"]  if roblox else None
        username   = roblox["roblox_username"] if roblox else None
        avatar_url = await roblox_get_avatar_url(roblox_id) if roblox_id else None

        current_rank = get_highest_rank(member)
        current_idx  = DISCORD_RANK_INDEX.get(current_rank, -1)
        print(f"[PROMOTE/RANK] {member} current rank: {current_rank!r} (idx {current_idx})")

        def _make_embed(color: discord.Color, description: str) -> discord.Embed:
            emb = discord.Embed(title="Promotion Results", color=color)
            emb.set_author(
                name=f"{member.display_name}{' (' + username + ')' if username else ''}",
                icon_url=member.display_avatar.url,
            )
            if avatar_url:
                emb.set_thumbnail(url=avatar_url)
            emb.add_field(name="Discord", value=f"<@{member.id}>", inline=True)
            if username:
                emb.add_field(name="Roblox", value=username, inline=True)
            emb.add_field(name="Actions", value=description, inline=False)
            emb.set_footer(text=f"Promoted by {interaction.user}"
                           + (f" • Roblox ID: {roblox_id}" if roblox_id else ""))
            return emb

        # Block only if the executor doesn't outrank the target (and isn't senior).
        # Intentionally allow assigning the same rank or a lower one — this handles
        # re-induction resets and any deliberate rank corrections by staff.
        if current_idx >= exec_idx and not senior:
            return _make_embed(
                discord.Color.red(),
                "❌ Cannot modify the rank of someone equal to or above you.",
            )
        if current_idx == target_rank_idx:
            return _make_embed(
                discord.Color.orange(),
                f"⚠️ **{current_rank}** is already the target rank. No change made.",
            )
        new_role = discord.utils.get(interaction.guild.roles, name=target_rank)
        if not new_role:
            return _make_embed(
                discord.Color.red(),
                f"❌ Discord role **{target_rank}** not found in server.",
            )
        old_ranks = [r for r in member.roles if r.name in ALL_RANK_ROLES]
        try:
            if old_ranks: await member.remove_roles(*old_ranks, reason="Promotion: strip old rank")
            await member.add_roles(new_role, reason=f"Promoted to {target_rank}")
        except discord.Forbidden:
            print(f"[PROMOTE/RANK] ❌ Forbidden modifying roles for {member}")
            return _make_embed(discord.Color.red(), "❌ Missing permissions to modify roles.")
        prev = current_rank or "no rank"
        print(f"[PROMOTE/RANK] ✅ {member}: {prev} → {target_rank}")
        log.info(f"[PROMOTE/RANK] {member} {prev} → {target_rank} by {interaction.user}")

        # ── Sync rank to CAV roster spreadsheet ─────────────────────────
        try:
            await async_sync_promote(
                discord_id=str(member.id),
                new_rank_label=target_rank,
                roblox_username=username,
            )
            print(f"[PROMOTE/RANK] ✅ Sheet sync complete for {username or member}")
        except Exception as _se:
            print(f"[PROMOTE/RANK] ⚠️ Sheet sync failed for {username or member}: {_se}")
            log.error(f"[PROMOTE/RANK] Sheet sync failed for {username or member}: {_se}")

        return _make_embed(
            discord.Color.dark_blue(),
            f"✅ Promoted from **{prev}** → **{target_rank}**.",
        )

    async with asyncio.timeout(120):
        embeds = await asyncio.gather(*[promote_one(m) for m in targets])
    print(f"[PROMOTE/RANK] All promotions complete for {[str(t) for t in targets]}")
    await interaction.edit_original_response(content="✅ Promotion complete.", view=None)
    for emb in embeds:
        await interaction.followup.send(embed=emb)

# ============================================================
#  RUN
# ============================================================

bot.run(DISCORD_TOKEN, log_handler=_log_handler, log_level=logging.DEBUG)