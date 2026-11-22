"""Central configuration. All assumptions live here so they are documented in one place."""
import os
from pathlib import Path

ROOT = Path(__file__).parent
# DATA_MODE=real (default) reads data/raw ; DATA_MODE=synthetic reads data/synthetic
MODE = os.environ.get("DATA_MODE", "real")
RAW = ROOT / ("data/synthetic" if MODE == "synthetic" else "data/raw")
PROC = ROOT / ("data/synthetic/processed" if MODE == "synthetic" else "data/processed")
OUT = ROOT / ("outputs/synthetic" if MODE == "synthetic" else "outputs")
DOCS = ROOT / "docs"
for p in (PROC, OUT):
    p.mkdir(parents=True, exist_ok=True)

TICKETS_CSV = RAW / "tickets.csv"      # unzip October-Delhi.csv.zip and rename/symlink to this
GTFS_DIR = RAW / "gtfs"                # stops.txt routes.txt trips.txt stop_times.txt

# ---- Ticket column names (as published). Change here if the real header differs. ----
COL = dict(pax="passenger_count", amount="amount", vehicle="vehicle_number",
           ttype="ticket_type_id", start="start_stop_name", end="end_stop_name",
           route="route", ts="created_at", ac="is_ac")

# ---- Ticket resolution ----
TRIP_GAP_MIN = 60          # (optional trip diagnostics) gap between tickets of one vehicle that starts a new trip
TRIP_BACKSTEP = 5          # (optional trip diagnostics) boarding index falling by more than this many stops => new trip
# ~49% of real tickets have vehicle_number = NULL, so the crowd model does NOT depend on vehicles (see crowd/flow.py).

# ---- Stop-name matching ----
FUZZY_ROUTE_THRESHOLD = 86  # score (0-100) accepted when matching inside the route's own stops
FUZZY_GLOBAL_THRESHOLD = 93 # stricter score when falling back to all GTFS stops

# ---- Crowding model ----
# The ticket file is a THIN SAMPLE of real ridership (about 1 passenger per scheduled trip per day) and has no zero-fare tickets,
# so ticket counts must be scaled up to riders. COVERAGE_FACTOR = riders per ticketed passenger. None => calibrate automatically:
# the CALIBRATION_PERCENTILE-th percentile of well-observed weekday-peak stretch loads is set equal to the STANDING limit, i.e. the busiest
# ~10% of weekday-peak route-stretches are labelled 'crowded'.
# Ranking between buses/stretches does NOT depend on this factor; only the seats/standing/crowded labels do (see sensitivity.csv).
COVERAGE_FACTOR = None
CALIBRATION_PERCENTILE = 0.90
CAPACITY = {"ac": dict(seats=33, crush=60), "nonac": dict(seats=36, crush=70)}   # assumed, not in the data
STANDING_FRACTION_OF_CRUSH = 0.75   # load above seats and <= this*crush => "standing room"
SHRINK_K = 10.0                     # empirical-Bayes strength, in tickets
CONF_TICKETS_HIGH, CONF_TICKETS_MED = 100, 20   # tickets covering a stretch-cell => high / medium confidence
LOAD_CAP_FACTOR = 1.3               # displayed load never exceeds this x crush capacity (a bus cannot carry 400 people)
MIN_SCHEDULED_TRIPS = 2             # fewer scheduled trips per day in a band => schedule evidence is thin => confidence is lowered one step
MIN_TICKETS_TRUTH = 10              # hold-out cells need at least this many tickets to count as reliable ground truth

# ---- Time bands (hour of day, [start, end)) ----
BANDS = {"night": (0, 5), "early": (5, 7), "am_peak": (7, 10), "midday": (10, 16),
         "pm_peak": (16, 20), "evening": (20, 24)}

# ---- Planner ----
WALK_RADIUS_M = 500
TRANSFER_RADIUS_M = 250
WALK_SPEED_MS = 1.25
WALK_DETOUR = 1.3
MAX_WAIT_MIN = 20
TRANSFER_PENALTY_MIN = 5
CROWD_PENALTY_MIN = {"seats": 0, "standing": 5, "crowded": 15}  # used by "comfortable" mode
