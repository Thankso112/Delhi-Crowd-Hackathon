"""
config.py  -  ALL settings and assumptions live in this one file.

Every number that is an *assumption* (not measured from data) is here, so you can
explain it to an instructor and change it in one place.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")          # reads the MySQL password from the .env file (never uploaded to GitHub)

# ---- 1. DATA LOCATIONS
# data/raw/tickets.csv + data/raw/gtfs/*.txt  (see README.md, "Get the data"). Results go to outputs/.
MODE = "real"                      # (kept so the API can report which data it serves)
RAW = ROOT / "data/raw"
TICKETS_CSV = RAW / "tickets.csv"
GTFS_DIR = RAW / "gtfs"
OUT = ROOT / "outputs"
FIG = OUT / "figures"
for _p in (OUT, FIG):
    _p.mkdir(parents=True, exist_ok=True)

# ---- 2. DATABASE (MySQL). Put your password in .env (copy .env.example to .env) -------------
# Database name (used only with MySQL).
USE_MYSQL = os.getenv("USE_MYSQL", "0") == "1"      # default: a local SQLite file (zero setup). Set USE_MYSQL=1 in .env to use MySQL instead
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
DB_NAME = f"bus_crowd_{MODE}"
SQLITE_FILE = RAW / "bus_crowd.sqlite"

# ---- 3. TICKET COLUMN NAMES in the CSV (change the right-hand side if your header differs)
COL = dict(pax="passenger_count", amount="amount", vehicle="vehicle_number",
           ttype="ticket_type_id", start="start_stop_name", end="end_stop_name",
           route="route", ts="created_at", ac="is_ac")

# ---- 3b. HOLIDAYS: a Mon-Fri with fewer than this share of a normal weekday's tickets is treated like a weekend day
HOLIDAY_RATIO = 0.6

# ---- 4. STOP-NAME MATCHING (fuzzy score 0-100)
FUZZY_ROUTE_THRESHOLD = 86    # similar-looking name inside the route's own stops
PARTIAL_THRESHOLD = 98        # ticket name fully contained in a stop name (e.g. "Mahipal Pur" in "Mahipal Pur Village")
FUZZY_GLOBAL_THRESHOLD = 93   # stricter, used only when falling back to every stop in Delhi

# ---- 5. TRIP EXPERIMENT (only used to show WHY we do not build the model on reconstructed trips)
TRIP_GAP_MIN = 60        # gap (minutes) between two tickets of one vehicle that starts a new "trip"
TRIP_BACKSTEP = 5        # boarding stop going back by more than this many stops also starts a new trip

# ---- 6. CROWD INDEX ASSUMPTIONS
# The ticket file is a SAMPLE of riders (about 27,000 tickets/day for a whole city), so we cannot count
# passengers on a bus. We measure "ticketed riders per scheduled bus" and report it RELATIVE to the network.
SHRINK_K = 10.0                 # a stretch with few tickets is pulled towards its route/hour average (weight in tickets)
CONF_HIGH, CONF_MED = 30, 10    # tickets behind an estimate => high / medium confidence
MIN_SCHEDULED_TRIPS = 2         # fewer scheduled trips per day in a time band => the schedule evidence is thin => confidence drops one step
LEVEL_CUTS = (50, 85)           # percentile cut-offs: below 50 = Quiet, 50-85 = Moderate, above 85 = Busy

# ---- 6b. CALIBRATION: from "ticketed riders per bus" to an estimated number of people on board
# Organizers confirmed this file holds only MOBILE e-tickets (about 3-4% of all bus riders) and omits pass holders.
# These are ASSUMPTIONS (not measured). Change them here; notebook 04 shows how much the tiers move (sensitivity).
EKT_CAPTURE_RATE = {"low": 0.05, "base": 0.035, "high": 0.03}    # share of riders who appear in this file  (high capture -> smaller scale)
PASS_MULTIPLIER = {"low": 1.0, "base": 1.5, "high": 2.0}         # extra riders who never buy a ticket (passes, free travel)
SCALE = {k: PASS_MULTIPLIER[k] / EKT_CAPTURE_RATE[k] for k in ("low", "base", "high")}   # people on board per ticketed rider
CAPACITY = {"ac": dict(seats=33, crush=60), "nonac": dict(seats=36, crush=70)}            # seated / maximum on board
LOAD_CAP_RATIO = 1.5                # a bus cannot carry more than ~1.5x its crush load; higher raw values mean the GTFS schedule lists
                                     # fewer buses than really run on that route, so we cap the shown load (the raw value is kept)
STANDING_FRACTION_OF_CRUSH = 0.75    # above the seats but up to 75% of crush => "standing_room"; above that => "crowded"

# ---- 7. TIME BANDS (hour of day, from <= hour < to)
BANDS = {"night": (0, 5), "early": (5, 7), "am_peak": (7, 10), "midday": (10, 16),
         "pm_peak": (16, 20), "evening": (20, 24)}

# ---- 8. JOURNEY PLANNER
WALK_RADIUS_M = 500
TRANSFER_RADIUS_M = 250
WALK_SPEED_MS = 1.25
WALK_DETOUR = 1.3              # real walking distance = straight line * 1.3
MAX_WAIT_MIN = 20
TRANSFER_PENALTY_MIN = 5
CROWD_PENALTY_MIN = {"low": 0, "medium": 5, "high": 15}   # "comfortable" mode adds these minutes

# ---- 9. MACHINE LEARNING
RANDOM_STATE = 42
CITY_CENTRE = (28.6315, 77.2167)   # Connaught Place, for the "distance to centre" feature
ML_MIN_TICKETS = 5                 # ignore cells built from fewer tickets than this
ML_SAMPLE_ROWS = 20000             # rows used to train the models (SVM and KNN get very slow on millions of rows)
