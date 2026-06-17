ANALYSIS_PERIOD = "Jan–May 2025 vs Jan–May 2026"
YEAR_1 = 2025
YEAR_2 = 2026
# The active month set is DERIVED FROM THE DATA — see pipeline.get_active_months(),
# which intersects the months present in YEAR_1 and YEAR_2. No hardcoded month list;
# the report flexes to however many months both years share.

# The in-progress, month-to-date (partial) month — flagged as "<Mon> MTD" across all
# tabs so a partial month can't be misread as a full-month figure. None when every
# active month is a full month.
MTD_MONTH = 6

WORKING_DAYS = {
    (1, 2025): 19.0,
    (2, 2025): 17.6,
    (3, 2025): 18.6,
    (4, 2025): 19.6,
    (5, 2025): 18.0,
    (6, 2025): 10.8,   # June MTD — elapsed working days for 6/1-6/17 (independently 10.8)
    (1, 2026): 18.0,
    (2, 2026): 17.6,
    (3, 2026): 19.6,
    (4, 2026): 19.6,
    (5, 2026): 17.0,
    (6, 2026): 10.8,   # June MTD — elapsed working days for 6/1-6/16 (independently 10.8)
}

# Set to (month_num, year, days_passed) when a month is in progress
PARTIAL_MONTH = None

PROVIDER_THRESHOLD_PCT = 90.0
PROVIDER_FLOOR_PCT = 2.0

# YoY % change is "Not Meaningful" (N/M) when the 2025 baseline Rev/Day is
# negative, zero, or below this near-zero floor ($/day). Avoids absurd
# percentages from tiny/negative denominators.
NM_BASELINE_FLOOR = 50.0

import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__))

SOURCE_FILE  = _os.path.join(_HERE, "data",   "A.2025_2026_Data_Updated.xlsx")
PROVIDER_MAP = _os.path.join(_HERE, "data",   "B.Provider_Map_Prod.xlsx")
OUTPUT_FILE  = _os.path.join(_HERE, "output", "Revenue_Driver_Analysis.html")

# 76 named offices in user-defined priority rank order (default sort)
OFFICE_LIST = [
    {"rank":  1, "name": "Citrus Park",                    "state": "Florida"},
    {"rank":  2, "name": "Saraland Smiles",                "state": "Alabama"},
    {"rank":  3, "name": "Wesley Chapel",                  "state": "Florida"},
    {"rank":  4, "name": "JR Dental",                      "state": "Florida"},
    {"rank":  5, "name": "Pensacola",                      "state": "Florida"},
    {"rank":  6, "name": "Alafaya",                        "state": "Florida"},
    {"rank":  7, "name": "Humphries Family Dental",        "state": "Alabama"},
    {"rank":  8, "name": "Crestview",                      "state": "Florida"},
    {"rank":  9, "name": "East Hamilton",                  "state": "Tennessee"},
    {"rank": 10, "name": "Mary Esther",                    "state": "Florida"},
    {"rank": 11, "name": "Damerau",                        "state": "Florida"},
    {"rank": 12, "name": "Criswell Mainstreet",            "state": "Arkansas"},
    {"rank": 13, "name": "Lumina Dental Brandon",          "state": "Florida"},
    {"rank": 14, "name": "JR Dental - San Jose",           "state": "Florida"},
    {"rank": 15, "name": "P&G Ortho",                      "state": "Kentucky"},
    {"rank": 16, "name": "Phillips Dental - Anniston",     "state": "Alabama"},
    {"rank": 17, "name": "Sheats - Nashville",             "state": "Tennessee"},
    {"rank": 18, "name": "Sheats - Franklin",              "state": "Tennessee"},
    {"rank": 19, "name": "Davis Dental",                   "state": "Kentucky"},
    {"rank": 20, "name": "East Hamilton Panorama",         "state": "Tennessee"},
    {"rank": 21, "name": "New Zephyrhills Dental",         "state": "Florida"},
    {"rank": 22, "name": "Lakeland",                       "state": "Florida"},
    {"rank": 23, "name": "Cool Springs",                   "state": "Tennessee"},
    {"rank": 24, "name": "Volunteer Ortho",                "state": "Tennessee"},
    {"rank": 25, "name": "Farni",                          "state": "Alabama"},
    {"rank": 26, "name": "Fairway Dental",                 "state": "Alabama"},
    {"rank": 27, "name": "Huntsville",                     "state": "Alabama"},
    {"rank": 28, "name": "Sheats - Murfreesboro",          "state": "Tennessee"},
    {"rank": 29, "name": "Brandon Smiles",                 "state": "Florida"},
    {"rank": 30, "name": "Bellevue",                       "state": "Tennessee"},
    {"rank": 31, "name": "Smiles on Florida",              "state": "Florida"},
    {"rank": 32, "name": "Pinnacle EPI",                   "state": "Florida"},
    {"rank": 33, "name": "Ledakis",                        "state": "Florida"},
    {"rank": 34, "name": "Decatur",                        "state": "Alabama"},
    {"rank": 35, "name": "Brentwood",                      "state": "Tennessee"},
    {"rank": 36, "name": "Criswell Northridge",            "state": "Arkansas"},
    {"rank": 37, "name": "Sunshine Smiles Designs",        "state": "Florida"},
    {"rank": 38, "name": "Donelson",                       "state": "Tennessee"},
    {"rank": 39, "name": "Moore Smiles",                   "state": "Kentucky"},
    {"rank": 40, "name": "Murfreesboro",                   "state": "Tennessee"},
    {"rank": 41, "name": "Florence",                       "state": "Alabama"},
    {"rank": 42, "name": "East Nashville",                 "state": "Tennessee"},
    {"rank": 43, "name": "JR Dental Argyle - Oak Leaf",   "state": "Florida"},
    {"rank": 44, "name": "New Port Richey",                "state": "Florida"},
    {"rank": 45, "name": "Madison",                        "state": "Alabama"},
    {"rank": 46, "name": "Parkside",                       "state": "Kentucky"},
    {"rank": 47, "name": "Cedar Grove",                    "state": "Tennessee"},
    {"rank": 48, "name": "Fort Smith",                     "state": "Arkansas"},
    {"rank": 49, "name": "Nashville Family Dentistry",     "state": "Tennessee"},
    {"rank": 50, "name": "Premier Periodontics Lexington", "state": "Kentucky"},
    {"rank": 51, "name": "Westen Dental Group",            "state": "Kentucky"},
    {"rank": 52, "name": "Arnold",                         "state": "Kentucky"},
    {"rank": 53, "name": "Orion Family Dentistry",         "state": "Alabama"},
    {"rank": 54, "name": "Truecare Family and Implant",    "state": "Florida"},
    {"rank": 55, "name": "Seaside Dental",                 "state": "Alabama"},
    {"rank": 56, "name": "Pinnacle Hills",                 "state": "Arkansas"},
    {"rank": 57, "name": "Premier Periodontics Danville",  "state": "Kentucky"},
    {"rank": 58, "name": "Bohle Family Dentistry",         "state": "Kentucky"},
    {"rank": 59, "name": "Franklin/Downs",                 "state": "Tennessee"},
    {"rank": 60, "name": "Phillips Dental - Woodland",     "state": "Alabama"},
    {"rank": 61, "name": "Crestview Kids",                 "state": "Florida"},
    {"rank": 62, "name": "Villages Premier Dental",        "state": "Florida"},
    {"rank": 63, "name": "Gamble",                         "state": "Alabama"},
    {"rank": 64, "name": "Fayetteville",                   "state": "Arkansas"},
    {"rank": 65, "name": "Rogers",                         "state": "Arkansas"},
    {"rank": 66, "name": "Hillsboro Village",              "state": "Tennessee"},
    {"rank": 67, "name": "Williams - Wesley Chapel",       "state": "Florida"},
    {"rank": 68, "name": "New Health Dental",              "state": "Arkansas"},
    {"rank": 69, "name": "Valley Urgent",                  "state": "Arkansas"},
    {"rank": 70, "name": "Metro OMS",                      "state": "Alabama"},
    {"rank": 71, "name": "O'Donnell",                      "state": "Kentucky"},
    {"rank": 72, "name": "JR Dental - Multispecialty",     "state": "Florida"},
    {"rank": 73, "name": "Bradenton Family & Implant",     "state": "Florida"},
    {"rank": 74, "name": "Premier Periodontics Richmond",  "state": "Kentucky"},
    {"rank": 75, "name": "Monument Dental",                "state": "Alabama"},
    {"rank": 76, "name": "Dothan Smiles",                  "state": "Alabama"},
]

NOISE_PATTERNS = [
    'temp', 'insurance', 'missing', 'default', 'breakdown',
    'budget', 'summary', 'unassigned', 'llc', 'pa ', 'p.a.',
    'inc.', 'pllc', 'hygiene temp', 'doctor temp', 'hyg temp',
    'temp dds', 'temp dr', 'temp hyg', 'temporary',
]
