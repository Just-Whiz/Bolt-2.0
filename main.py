# ============================================================
#  Bolt 2.0 — Corps de Cavalerie Impériale Discord Bot
#  Updated: 2026-05-30
#  Version: 1.2.0
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

load_dotenv()

# ============================================================
#  ENVIRONMENT - ACCESSES ALL .env FILE VARIABLES
# ============================================================

DISCORD_TOKEN        = os.getenv("DISCORD_TOKEN")
BLOXLINK_API_KEY     = os.getenv("BLOXLINK_API_KEY")
GUILD_ID             = os.getenv("GUILD_ID")
ROBLOX_OPEN_CLOUD    = os.getenv("ROBLOX_OPEN_CLOUD_KEY")
FRENCH_MAIN_GROUP_ID = os.getenv("FRENCH_GROUP_ID", "5610765")
CAV_GROUP_ID         = os.getenv("CAV_GROUP_ID", "195387641")

GOOGLE_SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "credentials.json")

FRENCH_SPREADSHEET_ID = os.getenv("FRENCH_SPREADSHEET_ID")
CAV_SPREADSHEET_ID    = os.getenv("CAV_SPREADSHEET_ID")

def _oc_headers() -> dict:
    return {"x-api-key": ROBLOX_OPEN_CLOUD, "Content-Type": "application/json"}

HTTP_TIMEOUT     = aiohttp.ClientTimeout(connect=10, sock_read=15)
ROBLOX_SEMAPHORE = asyncio.Semaphore(3)

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

BRIGADE_REGIMENTS: dict[str, list[str]] = {
    "BRIGADE KELLERMANN": ["26ème Régiment de Chasseurs à Cheval"],
    "BRIGADE LASALLE":    ["5ème Chevau-Légers Lanciers", "10ème Régiment de Hussards"],
    "BRIGADE BESSIÈRES":  ["Grenadiers à Cheval de la Garde Impériale"],
}

ALL_BRIGADE_ROLES:  set[str] = set(BRIGADES)
ALL_REGIMENT_ROLES: set[str] = {r for regs in BRIGADE_REGIMENTS.values() for r in regs}

# ============================================================
#  RANK CONFIGURATION
# ============================================================

DISCORD_RANKS: list[str] = [
    "Conscrit",                       # 0
    "Veteran",                        # 1
    "Cavalier",                       # 2
    "Brigadier",                      # 3
    "Brigadier-Fourrier",             # 4
    "Marechal des Logis",             # 5
    "Marechal des Logis-Chef",        # 6  ← SENIOR_THRESHOLD
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
ALL_RANK_ROLES:     set[str]       = set(DISCORD_RANKS)
DRAFT_RESET_RANK                   = "Cavalier"
SENIOR_THRESHOLD                   = DISCORD_RANKS.index("Marechal des Logis-Chef")

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
# Ordered lowest → highest tier so prefix precedence works (higher tier wins).
# Keys match the grade value in the sheet's second data column.
# Values: (Discord role name, nickname prefix)
NOBILITY_ROLE_MAP: dict[str, tuple[str, str]] = {
    "Chevalier": ("Chevalier d'Empire", "Chv."),
    "Baron":     ("Baron d'Empire",     "Bon."),
    "Comte":     ("Comte d'Empire",     "Cte."),
    "Duc":       ("Duc d'Empire",       "Duc"),
}

# Kept for backward-compat with /background-check (role → prefix lookup)
NOBILITY_PREFIXES: dict[str, str] = {
    role: prefix for _grade, (role, prefix) in NOBILITY_ROLE_MAP.items()
}

# All Discord roles that originate from sheet data (used by PURGE_ROLES)
ALL_SHEET_ROLES: set[str] = (
    set(MEDAL_AWARD_MAP.values())
    | set(VENERATION_ROLE_MAP.values())
    | {role for _grade, (role, _prefix) in NOBILITY_ROLE_MAP.items()}
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
]

CAV_INDUCT_ROBLOX_RANK = "BRIGADE KELLERMANN"

PURGE_ROLES: set[str] = (
    ALL_RANK_ROLES | ALL_BRIGADE_ROLES | ALL_REGIMENT_ROLES | ALL_SHEET_ROLES
    | {"Corps de Cavalerie Impériale", "Verified", "Garde Nationale de Cavalerie",
       "Citoyen", "Soldat", "Caporal", "Caporal Fourrier"}
)

ADMISSIONS_BLACKLIST_ROLE = "Admissions Blacklisted"

# ============================================================
#  COMMAND PERMISSIONS
# ============================================================

_STAFF_ROLES: set[str] = {
    "Administration Team",
    "Head of Administration",
    "Head of Recruitment",
    "26ème État-major",
    "7ème État-major",
    "5ème État-major",
    "GaC État-major",
    "Adjudant Sous-Officier",
    "Cavalerie État-major",
    "Adjoint d'État Major",
    "Super Admin",
    "Admin",
}

COMMAND_PERMISSIONS: dict[str, set[str]] = {
    "background-check": {"Recruitment Team"} | _STAFF_ROLES,
    "induct":           {"Recruitment Team"} | _STAFF_ROLES,
    "purge":            _STAFF_ROLES,
    "promote":          _STAFF_ROLES,
    "medal-sync":       _STAFF_ROLES,
    "export-rosters":   _STAFF_ROLES,
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
        "roblox_id":        str(roblox_id),
        "roblox_username":  username,
        "discord_username": discord_username,
        "cached_at":        datetime.now(timezone.utc).isoformat(),
    }
    await _save_cache()
    log.info(f"[CACHE] Cached {discord_id} → {username}")

# ============================================================
#  ROBLOX REST HELPERS
# ============================================================

async def roblox_get_user_info(roblox_id: str) -> dict:
    async with ROBLOX_SEMAPHORE:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.get(f"https://roblox-proxy.christiansuy25.workers.dev/users/v1/users/{roblox_id}")
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
            dt    = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
            delta = datetime.now(timezone.utc) - dt
            y, m, d = delta.days // 365, (delta.days % 365) // 30, delta.days % 30
            account_age = f"{y} years, {m} months, {d} days"
        except Exception:
            pass
    return {
        "name":         data.get("name", ""),
        "display_name": data.get("displayName", ""),
        "account_age":  account_age,
        "created":      created_str,
    }

async def roblox_get_username(roblox_id: str) -> str | None:
    return (await roblox_get_user_info(roblox_id)).get("name") or None

async def roblox_get_previous_usernames(roblox_id: str) -> str:
    async with ROBLOX_SEMAPHORE:
        try:
            async with httpx.AsyncClient(timeout=15) as s:
                r = await s.get(f"https://roblox-proxy.christiansuy25.workers.dev/users/v1/users/{roblox_id}/username-history?limit=10")
                if r.status_code != 200:
                    return "None"
                names = [e["name"] for e in r.json().get("data", [])]
                return ", ".join(names) if names else "None"
        except Exception:
            return "None"

async def roblox_get_avatar_url(roblox_id: str) -> str | None:
    async with ROBLOX_SEMAPHORE:
        try:
            async with httpx.AsyncClient(timeout=15) as s:
                r = await s.get(
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
            async with httpx.AsyncClient(timeout=15) as s:
                r = await s.get(f"https://roblox-proxy.christiansuy25.workers.dev/groups/v2/users/{roblox_id}/groups/roles")
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
            async with httpx.AsyncClient(timeout=15) as s:
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
            async with httpx.AsyncClient(timeout=15) as s:
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

async def roblox_kick_from_group(roblox_id: str, group_id: str) -> bool:
    if not ROBLOX_OPEN_CLOUD:
        return False
    async with ROBLOX_SEMAPHORE:
        try:
            async with httpx.AsyncClient(timeout=15) as s:
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
                path = memberships[0]["path"]
                r = await s.delete(
                    f"https://roblox-proxy.christiansuy25.workers.dev/apis/cloud/v2/{path}",
                    headers=_oc_headers(),
                )
                success = r.status_code in (200, 204)
                if success:
                    log.info(f"[ROBLOX] Kicked {roblox_id} from {group_id}")
                return success
        except Exception as e:
            print(f"[ROBLOX] kick_from_group error: {e!r}")
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
                if not roblox_id:
                    return None
    except Exception as e:
        print(f"[BLOXLINK] Exception: {e}")
        return None
    username = await roblox_get_username(roblox_id)
    if not username:
        return {"roblox_id": roblox_id, "roblox_username": f"Unknown ({roblox_id})"}
    guild         = bot.get_guild(int(GUILD_ID))
    discord_mbr   = guild.get_member(int(discord_id)) if guild else None
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
                    category  = row[col_cat].strip() if len(row) > col_cat else ""
                    award_val = row[col_val].strip()
                    if not award_val or not category:
                        continue

                    sheet_key = f"{category} {award_val}"
                    mapped    = MEDAL_AWARD_MAP.get(sheet_key)

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
            rows    = ws.get_all_values()
            headers = rows[0] if rows else []
            # Locate columns by name, falling back to known indices if needed
            col_p  = next((i for i, h in enumerate(headers) if h.strip().lower() == "profile link"), 6)
            col_r  = next((i for i, h in enumerate(headers) if h.strip() == "Rank"), 8)
            col_s  = next((i for i, h in enumerate(headers) if h.strip() == "Status"), 9)
            col_mc = next((i for i, h in enumerate(headers) if h.strip() == "Manually Closed"), -1)
            for row in rows[1:]:
                if len(row) <= max(col_p, col_r, col_s):
                    continue
                profile_link = row[col_p].strip()
                m = re.search(r"/users/(\d+)/", profile_link)
                if not m:
                    continue
                roblox_id = m.group(1)
                status    = row[col_s].strip().lower()
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
    """Read Nobility tab → ({roblox_id: {discord_role, …}}, {roblox_id: nick_prefix})

    Keyed by Roblox ID extracted from the Profile Link column (col G, index 6).
    """
    role_result:   dict[str, set[str]] = {}
    prefix_result: dict[str, str]      = {}
    for ws in _get_worksheets("Nobility"):
        try:
            rows    = ws.get_all_values()
            headers = rows[0] if rows else []
            col_p   = next((i for i, h in enumerate(headers) if h.strip().lower() == "profile link"), 6)
            col_g   = _col(headers, " ")        # sheet's grade/class column has a space header
            col_s   = _col(headers, "Stage")
            for row in rows[1:]:
                if len(row) <= max(col_p, col_g, col_s):
                    continue
                profile_link = row[col_p].strip()
                m = re.search(r"/users/(\d+)/", profile_link)
                if not m:
                    continue
                roblox_id = m.group(1)
                grade     = row[col_g].strip()
                stage     = row[col_s].strip().lower()
                if not roblox_id or stage != "approved":
                    continue
                entry = NOBILITY_ROLE_MAP.get(grade)
                if not entry:
                    log.debug(f"[SHEETS][NOBILITY] Unmapped grade '{grade}' for Roblox ID '{roblox_id}'")
                    continue
                discord_role, nick_prefix = entry
                role_result.setdefault(roblox_id, set()).add(discord_role)
                # Keep highest-tier prefix for this user
                tiers    = list(NOBILITY_ROLE_MAP.keys())
                existing = prefix_result.get(roblox_id)
                if existing is None or tiers.index(grade) > tiers.index(
                    next(k for k, (r, p) in NOBILITY_ROLE_MAP.items() if p == existing), grade
                ):
                    prefix_result[roblox_id] = nick_prefix
        except Exception as e:
            log.error(f"[SHEETS][NOBILITY] sheet_load_nobility error: {e}")
    return role_result, prefix_result

def sheet_load_all() -> tuple[
    dict[str, set[str]],   # medals    {username_lower → {discord_role, …}}
    dict[str, set[str]],   # venerations
    dict[str, set[str]],   # nobility roles
    dict[str, str],        # nobility nick prefixes
]:
    """Load all three active tabs from the French medals spreadsheet."""
    medals               = sheet_load_medals()
    venerations          = sheet_load_venerations()
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
        if gid in FRENCH_GROUP_IDS:       french.append(f"{FRENCH_GROUP_IDS[gid]} — {rank}")
        elif gid in COALITION_GROUP_IDS:  coalition.append(f"{COALITION_GROUP_IDS[gid]} — {rank}")
        elif gid in NEUTRAL_GROUP_IDS:    neutral.append(f"{NEUTRAL_GROUP_IDS[gid]} — {rank}")
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
            bl_role = discord.utils.get(real_guild.roles, name=ADMISSIONS_BLACKLIST_ROLE)
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
        bl_role = discord.utils.get(guild.roles, name=ADMISSIONS_BLACKLIST_ROLE)
        if bl_role and bl_role not in member.roles:
            await member.add_roles(bl_role, reason="Auto-blacklisted via the-yard")

        # 2. Get Roblox ID and Kick from Cav Group
        roblox = await resolve_roblox_user(str(member.id))
        roblox_id, username = "Unknown", "Unknown"
        if roblox:
            roblox_id = roblox.get("roblox_id", "Unknown")
            username  = roblox.get("roblox_username", "Unknown")
            if roblox_id != "Unknown":
                await roblox_kick_from_group(roblox_id, CAV_GROUP_ID)

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

    await interaction.response.defer()

    for discord_id in parse_mentions(users):
        try:
            member = interaction.guild.get_member(discord_id)
            roblox = await resolve_roblox_user(str(discord_id))
            if not roblox:
                await interaction.followup.send(f"❌ <@{discord_id}> is not verified with Bloxlink.")
                continue

            roblox_id = roblox["roblox_id"]
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
            groups   = all_groups if isinstance(all_groups, list) else []

            french_rank = cav_rank = "Not a member"
            for g in groups:
                if g["id"] == str(FRENCH_MAIN_GROUP_ID): french_rank = g["rank"]
                if g["id"] == str(CAV_GROUP_ID):         cav_rank    = g["rank"]

            french, coalition, neutral = categorise_groups(groups)

            loop = asyncio.get_event_loop()
            _, nobility_p = await loop.run_in_executor(None, sheet_load_nobility)
            nobility_text = "None"
            nick_prefix   = nobility_p.get(roblox_id)
            if nick_prefix and member:
                nobility_text = f"Title prefix: **{nick_prefix}**"
                title_role = next(
                    (r for t, (r, p) in NOBILITY_ROLE_MAP.items() if p == nick_prefix), None
                )
                if title_role:
                    disc_role = discord.utils.get(interaction.guild.roles, name=title_role)
                    if disc_role and disc_role not in member.roles:
                        try:
                            await member.add_roles(disc_role, reason="Nobility found in sheet")
                            nobility_text += " ✅ role assigned"
                        except discord.Forbidden:
                            nobility_text += " ⚠️ (could not assign role)"

                current_nick = member.nick or member.display_name
                if not current_nick.startswith(nick_prefix):
                    base = current_nick
                    for _, pfx in NOBILITY_ROLE_MAP.values():
                        if base.startswith(pfx + " "):
                            base = base[len(pfx) + 1:]
                            break
                    new_nick = f"{nick_prefix} {base}"[:32]
                    try:
                        await member.edit(nick=new_nick, reason="Nobility title applied")
                        nobility_text += f" ✅ nick → {new_nick}"
                    except discord.Forbidden:
                        nobility_text += " ⚠️ (could not update nick)"

            embed = discord.Embed(title="Background Check Results", color=discord.Color.dark_blue())
            if avatar_url:
                embed.set_thumbnail(url=avatar_url)
            embed.add_field(name="Account",         value=f"<@{discord_id}>, {username}", inline=False)
            embed.add_field(name="Account Age",     value=user_info.get("account_age", "Unknown"), inline=True)
            embed.add_field(name="Prev. Usernames", value=prev_names,  inline=True)
            embed.add_field(name="Nobility",        value=nobility_text, inline=False)
            embed.add_field(
                name="French Rankings",
                value=f"Empire Français — {french_rank}\nCorps de Cavalerie — {cav_rank}",
                inline=False,
            )
            embed.add_field(name=f"🇫🇷 French Empire & Clients ({len(french)})",  value=truncate_field(french),    inline=False)
            embed.add_field(name=f"⚔️ Coalition Powers ({len(coalition)})",        value=truncate_field(coalition), inline=False)
            embed.add_field(name=f"🌐 Neutral Powers ({len(neutral)})",            value=truncate_field(neutral),   inline=False)
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
        await interaction.response.send_message("❌ You don't have permission.", ephemeral=True)
        return
    await interaction.response.defer()

    for discord_id in parse_mentions(users):
        lines = ["**Induct Results**"]
        try:
            member = interaction.guild.get_member(discord_id)
            if not member:
                member = await asyncio.wait_for(interaction.guild.fetch_member(discord_id), timeout=10)
            lines.append(f"<@{discord_id}> — {member.display_name}")

            roblox = await resolve_roblox_user(str(discord_id))
            if not roblox:
                lines.append("❌ Not verified with Bloxlink. Aborted.")
                await interaction.followup.send("\n".join(lines))
                continue

            roblox_id = roblox["roblox_id"]
            username  = roblox["roblox_username"]

            cav_rank = await roblox_get_group_rank(roblox_id, CAV_GROUP_ID)
            if not cav_rank or cav_rank.lower() == "guest":
                accepted = await asyncio.wait_for(
                    roblox_accept_join_request(roblox_id, CAV_GROUP_ID), timeout=15
                )
                if accepted:
                    lines.append("✅ Accepted into Corps de Cavalerie Impériale.")
                else:
                    lines.append("❌ No pending join request. Ask them to send one first. Aborted.")
                    await interaction.followup.send("\n".join(lines))
                    continue
            else:
                lines.append(f"⚠️ Already in Cav group as {cav_rank}.")

            if cav_rank and cav_rank.lower() == CAV_INDUCT_ROBLOX_RANK.lower():
                lines.append(f"⚠️ Already ranked {CAV_INDUCT_ROBLOX_RANK}.")
            else:
                try:
                    ranked = await asyncio.wait_for(
                        roblox_set_rank(roblox_id, CAV_GROUP_ID, CAV_INDUCT_ROBLOX_RANK), timeout=30,
                    )
                    lines.append(f"✅ Ranked to {CAV_INDUCT_ROBLOX_RANK}." if ranked
                                 else "❌ Failed to set Roblox rank — set manually.")
                except asyncio.TimeoutError:
                    lines.append("⚠️ Roblox rank request timed out — set manually.")

            guild    = interaction.guild
            stripped = []
            for name in INDUCT_REMOVE:
                role = discord.utils.get(guild.roles, name=name)
                if role and role in member.roles:
                    await member.remove_roles(role)
                    stripped.append(name)
            lines.append(f"✅ Stripped: {', '.join(stripped)}" if stripped else "⚠️ No roles to strip.")

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
        except Exception as e:
            lines.append(f"❌ Unexpected error: {type(e).__name__}: {e}")
            log.error(f"[INDUCT] Error for {discord_id}: {e}")

        await interaction.followup.send("\n".join(lines))

# ============================================================
#  /purge
# ============================================================

@bot.tree.command(name="purge", description="Strip all roles, kick from Roblox group, and reset nickname.")
@app_commands.describe(users="Mention one or more users to purge")
async def purge(interaction: discord.Interaction, users: str):
    if not has_command_permission(interaction, "purge"):
        await interaction.response.send_message("❌ You don't have permission.", ephemeral=True)
        return
    await interaction.response.defer()

    mentions = parse_mentions(users)
    if not mentions:
        await interaction.followup.send("❌ No valid members mentioned.")
        return

    all_results = []

    for discord_id in mentions:
        lines = [f"**Purge Results for <@{discord_id}>:**"]
        try:
            member = interaction.guild.get_member(discord_id)
            if not member:
                try:
                    member = await asyncio.wait_for(interaction.guild.fetch_member(discord_id), timeout=10)
                except Exception:
                    lines.append(f"❌ Could not find Discord member.")
                    all_results.append("\n".join(lines))
                    continue

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
                    lines.append("✅ Kicked from Corps de Cavalerie Impériale (Roblox)." if kicked
                                 else "❌ Failed to kick from Roblox group — remove manually.")

            stripped = []
            for name in PURGE_ROLES:
                role = discord.utils.get(interaction.guild.roles, name=name)
                if role and role in member.roles:
                    await member.remove_roles(role)
                    stripped.append(name)
            lines.append(f"✅ Stripped: {', '.join(stripped)}" if stripped
                         else "⚠️ No matching roles found to strip.")

            bl_role = discord.utils.get(interaction.guild.roles, name=ADMISSIONS_BLACKLIST_ROLE)
            if bl_role:
                if bl_role not in member.roles:
                    try:
                        await member.add_roles(bl_role, reason="Purged from regiment")
                        lines.append(f"✅ Added **{ADMISSIONS_BLACKLIST_ROLE}**.")
                    except discord.Forbidden:
                        lines.append(f"⚠️ Could not add **{ADMISSIONS_BLACKLIST_ROLE}** — check bot role hierarchy.")
            else:
                lines.append(f"⚠️ **{ADMISSIONS_BLACKLIST_ROLE}** role not found in server.")

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
        except Exception as e:
            lines.append(f"❌ Unexpected error: {type(e).__name__}: {e}")
            log.error(f"[PURGE] Error for {discord_id}: {e}")

        all_results.append("\n".join(lines))

    response_text = "\n\n".join(all_results)
    if not response_text:
        await interaction.followup.send("⚠️ No actions were taken.")
        return
        
    for i in range(0, len(response_text), 1900):
        await interaction.followup.send(response_text[i:i+1900])

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
        medals_data, veneration_data, nobility_roles, nobility_prefixes = await loop.run_in_executor(
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

    all_results: list[str] = []

    for discord_id in mentions:
        member = interaction.guild.get_member(discord_id)
        if not member:
            try:
                member = await asyncio.wait_for(
                    interaction.guild.fetch_member(discord_id), timeout=10
                )
            except Exception:
                msg = f"❌ <@{discord_id}> — could not find in server."
                print(f"[MEDAL-SYNC] {msg}")
                log.warning(f"[MEDAL-SYNC] Member {discord_id} not found in guild.")
                all_results.append(msg)
                continue

        # Resolve Roblox username via Bloxlink / cache
        roblox = await resolve_roblox_user(str(discord_id))
        if not roblox:
            msg = f"❌ <@{discord_id}> — not verified with Bloxlink, cannot look up spreadsheet."
            print(f"[MEDAL-SYNC] {msg}")
            log.warning(f"[MEDAL-SYNC] {member} has no Bloxlink verification.")
            all_results.append(msg)
            continue

        roblox_username: str = roblox["roblox_username"]
        roblox_id_key:   str = roblox["roblox_id"]

        print(
            f"[MEDAL-SYNC] Processing {member} (Roblox: {roblox_username}, ID: {roblox_id_key}) — "
            f"searching MedalsRoster, Venerations, Nobility…"
        )
        log.info(f"[MEDAL-SYNC] Processing {member} → Roblox '{roblox_username}' (id='{roblox_id_key}')")

        lines: list[str] = [
            f"**Medal Sync — {member.mention}** (Roblox: **{roblox_username}**)"
        ]

        # ── Helper: assign a single Discord role ────────────────────────────
        async def assign_role(role_name: str, source_tag: str) -> str:
            """
            Try to add `role_name` to `member`.
            Returns a one-line status string for the embed.
            """
            disc_role = discord.utils.get(interaction.guild.roles, name=role_name)
            if not disc_role:
                msg = f"  ⚠️ [{source_tag}] Role **{role_name}** not found in server — create it first."
                print(f"[MEDAL-SYNC]   MISSING ROLE: '{role_name}' ({source_tag}) for {roblox_username}")
                log.warning(f"[MEDAL-SYNC] Role '{role_name}' ({source_tag}) not in guild for '{roblox_username}'")
                return msg
            if disc_role in member.roles:
                msg = f"  ✅ [{source_tag}] **{role_name}** — already assigned."
                print(f"[MEDAL-SYNC]   ALREADY HAS: '{role_name}' ({source_tag})")
                log.debug(f"[MEDAL-SYNC] '{roblox_username}' already has '{role_name}' ({source_tag})")
                return msg
            try:
                await member.add_roles(disc_role, reason=f"Medal sync ({source_tag})")
                msg = f"  ✅ [{source_tag}] **{role_name}** — granted."
                print(f"[MEDAL-SYNC]   GRANTED: '{role_name}' ({source_tag}) → {roblox_username}")
                log.info(f"[MEDAL-SYNC] Granted '{role_name}' ({source_tag}) to '{roblox_username}'")
                return msg
            except discord.Forbidden:
                msg = f"  ❌ [{source_tag}] **{role_name}** — missing permissions to assign."
                print(f"[MEDAL-SYNC]   FORBIDDEN: '{role_name}' ({source_tag}) for {roblox_username}")
                log.error(f"[MEDAL-SYNC] Forbidden assigning '{role_name}' ({source_tag}) to '{roblox_username}'")
                return msg

        # ── Medals (MedalsRoster tab) ────────────────────────────────────────
        medal_roles = medals_data.get(roblox_id_key, set())
        if medal_roles:
            print(f"[MEDAL-SYNC]   MEDALS FOUND ({len(medal_roles)}): {medal_roles}")
            log.info(f"[MEDAL-SYNC] '{roblox_username}' medals from sheet: {medal_roles}")
            lines.append(f"\n🎖️ **Medals** ({len(medal_roles)} approved):")
            for role_name in sorted(medal_roles):
                lines.append(await assign_role(role_name, "Medals"))
        else:
            lines.append("\n🎖️ **Medals** — none found in MedalsRoster.")
            print(f"[MEDAL-SYNC]   No medals found for '{roblox_username}' (ID: {roblox_id_key})")
            log.info(f"[MEDAL-SYNC] No medals found for '{roblox_username}' (ID: {roblox_id_key})")

        # ── Venerations (Venerations tab) ────────────────────────────────────
        veneration_roles = veneration_data.get(roblox_id_key, set())
        if veneration_roles:
            print(f"[MEDAL-SYNC]   VENERATIONS FOUND ({len(veneration_roles)}): {veneration_roles}")
            log.info(f"[MEDAL-SYNC] '{roblox_username}' venerations from sheet: {veneration_roles}")
            lines.append(f"\n🕯️ **Venerations** ({len(veneration_roles)} approved):")
            for role_name in sorted(veneration_roles):
                lines.append(await assign_role(role_name, "Venerations"))
        else:
            lines.append("\n🕯️ **Venerations** — none found in Venerations tab.")
            print(f"[MEDAL-SYNC]   No venerations found for '{roblox_username}' (ID: {roblox_id_key})")
            log.info(f"[MEDAL-SYNC] No venerations found for '{roblox_username}' (ID: {roblox_id_key})")

        # ── Nobility (Nobility tab) ──────────────────────────────────────────
        nob_roles  = nobility_roles.get(roblox_id_key, set())
        nob_prefix = nobility_prefixes.get(roblox_id_key)
        if nob_roles:
            print(f"[MEDAL-SYNC]   NOBILITY FOUND ({len(nob_roles)}): {nob_roles} | prefix='{nob_prefix}'")
            log.info(f"[MEDAL-SYNC] '{roblox_username}' nobility from sheet: {nob_roles} prefix='{nob_prefix}'")
            lines.append(f"\n👑 **Nobility** ({len(nob_roles)} approved):")
            for role_name in sorted(nob_roles):
                lines.append(await assign_role(role_name, "Nobility"))

            # Apply nobility nickname prefix
            if nob_prefix:
                current_nick = member.nick or member.display_name
                if not current_nick.startswith(nob_prefix):
                    # Strip any existing nobility prefix before prepending the new one
                    base = current_nick
                    for _g, (_r, pfx) in NOBILITY_ROLE_MAP.items():
                        if base.startswith(pfx + " "):
                            base = base[len(pfx) + 1:]
                            break
                    new_nick = f"{nob_prefix} {base}"[:32]
                    try:
                        await member.edit(nick=new_nick, reason="Medal sync: nobility prefix applied")
                        nick_msg = f"  ✅ [Nobility] Nickname updated → **{new_nick}**"
                        print(f"[MEDAL-SYNC]   NICK UPDATED: '{current_nick}' → '{new_nick}' for {roblox_username}")
                        log.info(f"[MEDAL-SYNC] Nick '{current_nick}' → '{new_nick}' for '{roblox_username}'")
                    except discord.Forbidden:
                        nick_msg = f"  ⚠️ [Nobility] Could not update nickname (bot role too low or server owner)."
                        print(f"[MEDAL-SYNC]   NICK FORBIDDEN for {roblox_username}")
                        log.warning(f"[MEDAL-SYNC] Cannot update nick for '{roblox_username}' (Forbidden)")
                    lines.append(nick_msg)
                else:
                    lines.append(f"  ✅ [Nobility] Nickname prefix **{nob_prefix}** already applied.")
        else:
            lines.append("\n👑 **Nobility** — none found in Nobility tab.")
            print(f"[MEDAL-SYNC]   No nobility found for '{roblox_username}'")
            log.info(f"[MEDAL-SYNC] No nobility found for '{roblox_username}'")

        log.info(f"[MEDAL-SYNC] Finished processing '{roblox_username}' ({member})")
        print(f"[MEDAL-SYNC] Done: {roblox_username}")
        all_results.append("\n".join(lines))

    # ── Send results in chunks to avoid Discord's 2000-char limit ───────────
    full_output = "\n\n".join(all_results) if all_results else "⚠️ No members were processed."
    print(f"[MEDAL-SYNC] All done — sending results to Discord.")
    log.info(f"[MEDAL-SYNC] Run complete by {interaction.user}")
    for i in range(0, len(full_output), 1900):
        await interaction.followup.send(full_output[i:i + 1900])
# ============================================================

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

class SingleSelectView(discord.ui.View):
    def __init__(self, select: discord.ui.Select, timeout: int = 60):
        super().__init__(timeout=timeout)
        self.promo_type:     str | None = None
        self.target_rank:    str | None = None
        self.target_brigade: str | None = None
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

    exec_member  = interaction.guild.get_member(interaction.user.id)
    exec_idx     = get_rank_index(exec_member)
    senior       = is_senior_promoter(exec_member)
    min_exec_idx = DISCORD_RANK_INDEX.get("Adjudant Sous-Officier", 0)

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
        brigade_view = SingleSelectView(BrigadeSelect())
        await interaction.edit_original_response(
            content="**Step 2:** Select the brigade to draft target(s) into:", view=brigade_view
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
            username  = roblox["roblox_username"]
            errors: list[str] = []
            guild = interaction.guild

            if not await roblox_set_rank(roblox_id, CAV_GROUP_ID, target_brigade):
                errors.append("failed to set Roblox brigade rank")

            old_ranks     = [r for r in member.roles if r.name in ALL_RANK_ROLES]
            cavalier_role = discord.utils.get(guild.roles, name=DRAFT_RESET_RANK)
            try:
                if old_ranks:     await member.remove_roles(*old_ranks, reason="Draft: rank reset")
                if cavalier_role: await member.add_roles(cavalier_role, reason=f"Draft → {target_brigade}")
                else:             errors.append(f"'{DRAFT_RESET_RANK}' role not found")
            except discord.Forbidden:
                errors.append("missing permissions for rank roles")

            old_brigades     = [r for r in member.roles if r.name in ALL_BRIGADE_ROLES]
            new_brigade_role = discord.utils.get(guild.roles, name=target_brigade)
            try:
                if old_brigades:     await member.remove_roles(*old_brigades, reason="Draft: brigade swap")
                if new_brigade_role: await member.add_roles(new_brigade_role, reason=f"Draft → {target_brigade}")
                else:                errors.append(f"'{target_brigade}' Discord role not found")
            except discord.Forbidden:
                errors.append("missing permissions for brigade roles")

            old_regiments      = [r for r in member.roles if r.name in ALL_REGIMENT_ROLES]
            new_regiment_roles = [discord.utils.get(guild.roles, name=rn) for rn in regiment_names]
            new_regiment_roles = [r for r in new_regiment_roles if r is not None]
            try:
                if old_regiments:      await member.remove_roles(*old_regiments, reason="Draft: regiment swap")
                if new_regiment_roles: await member.add_roles(*new_regiment_roles, reason=f"Draft → {target_brigade}")
            except discord.Forbidden:
                errors.append("missing permissions for regiment roles")

            if errors:
                return f"⚠️ **{username}** — drafted with issues: {'; '.join(errors)}."
            log.info(f"[PROMOTE/DRAFT] {username} drafted → {target_brigade} by {interaction.user}")
            return (f"✅ **{username}** — drafted to **{target_brigade}** "
                    f"({', '.join(regiment_names)}), rank reset to **{DRAFT_RESET_RANK}**.")

        async with asyncio.timeout(120):
            results = await asyncio.gather(*[draft_one(m) for m in targets])
        await interaction.edit_original_response(content="\n".join(results), view=None)
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
    await interaction.edit_original_response(content="⏳ Processing promotions…", view=None)

    async def promote_one(member: discord.Member) -> str:
        current_rank = get_highest_rank(member)
        current_idx  = DISCORD_RANK_INDEX.get(current_rank, -1)
        if current_idx >= target_rank_idx:
            return (f"⚠️ **{member.display_name}** — already holds **{current_rank}**, "
                    f"equal to or above **{target_rank}**. Skipped.")
        if current_idx >= exec_idx and not senior:
            return f"❌ **{member.display_name}** — cannot promote someone of equal or higher rank."
        new_role = discord.utils.get(interaction.guild.roles, name=target_rank)
        if not new_role:
            return f"❌ **{member.display_name}** — Discord role **{target_rank}** not found in server."
        old_ranks = [r for r in member.roles if r.name in ALL_RANK_ROLES]
        try:
            if old_ranks: await member.remove_roles(*old_ranks, reason="Promotion: strip old rank")
            await member.add_roles(new_role, reason=f"Promoted to {target_rank}")
        except discord.Forbidden:
            return f"❌ **{member.display_name}** — missing permissions to modify roles."
        prev = current_rank or "no rank"
        log.info(f"[PROMOTE/RANK] {member} {prev} → {target_rank} by {interaction.user}")
        return f"✅ **{member.display_name}** — promoted from **{prev}** → **{target_rank}**."

    async with asyncio.timeout(120):
        results = await asyncio.gather(*[promote_one(m) for m in targets])
    await interaction.edit_original_response(content="\n".join(results), view=None)

# ============================================================
#  RUN
# ============================================================

bot.run(DISCORD_TOKEN, log_handler=_log_handler, log_level=logging.DEBUG)
