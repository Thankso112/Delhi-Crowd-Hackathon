"""Small helper functions used by several notebooks (name cleaning, crowd levels, distances)."""
import re
import numpy as np
import config

# Short forms found in ticket stop names -> full words (so "Rohini Sec 7" matches "Rohini Sector 7")
_ABBR = {"stn": "station", "nr": "near", "opp": "opposite", "mkt": "market", "rd": "road", "sec": "sector",
         "ext": "extension", "pt": "point", "dep": "depot", "ngr": "nagar", "cc": "chowk",
         "i s b t": "isbt", "clny": "colony", "col": "colony", "bs": "", "bus stop": "", "bus stand": "",
         "metro stn": "metro station", "hosp": "hospital", "univ": "university", "ph": "phase"}


def norm_name(s) -> str:
    """Clean a stop name: lowercase, remove punctuation, expand abbreviations."""
    if s is None or (isinstance(s, float) and s != s):
        return ""
    s = str(s).lower().strip()
    s = s.replace("&", " and ").replace("i.s.b.t.", "isbt").replace("i.s.b.t", "isbt")
    s = re.sub(r"[\(\)\[\]\.,/\\\-_'\"]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    for k in sorted(_ABBR, key=len, reverse=True):
        s = re.sub(rf"\b{re.escape(k)}\b", _ABBR[k], s)
    return re.sub(r"\s+", " ", s).strip()


def norm_route(s) -> str:
    """'0534 ' -> '534', '534a' -> '534A'."""
    return re.sub(r"\s+", "", str(s)).upper().lstrip("0") if s is not None else ""


def band_of(hour: int) -> str:
    """Hour of day -> time band name (am_peak, midday, ...)."""
    for b, (lo, hi) in config.BANDS.items():
        if lo <= hour < hi:
            return b
    return "night"


def to_percentile(values, reference):
    """Where does each value sit among the reference values? 0-100 (e.g. 87 = busier than 87% of stretches)."""
    ref = np.sort(np.asarray(reference, dtype=float))
    return np.searchsorted(ref, np.asarray(values, dtype=float), side="right") / len(ref) * 100


def level_of_pct(pct):
    """Crowd percentile -> relative level: 'low' (Quiet) / 'medium' (Moderate) / 'high' (Busy)."""
    p = np.asarray(pct, dtype=float)
    return np.where(p < config.LEVEL_CUTS[0], "low", np.where(p < config.LEVEL_CUTS[1], "medium", "high"))


def confidence_of(n_tickets):
    """Number of tickets behind an estimate -> 'high' / 'medium' / 'low'."""
    n = np.asarray(n_tickets)
    return np.where(n >= config.CONF_HIGH, "high", np.where(n >= config.CONF_MED, "medium", "low"))


def capacity_of(is_ac):
    """Maximum passengers on board (crush load) for AC / non-AC buses. Works on arrays."""
    return np.where(np.asarray(is_ac).astype(bool), config.CAPACITY["ac"]["crush"], config.CAPACITY["nonac"]["crush"])


def tier_of(est_load, is_ac):
    """Estimated people on board -> 'seats_available' / 'standing_room' / 'crowded'."""
    ac = np.asarray(is_ac).astype(bool)
    seats = np.where(ac, config.CAPACITY["ac"]["seats"], config.CAPACITY["nonac"]["seats"])
    crush = capacity_of(ac)
    x = np.asarray(est_load, dtype=float)
    return np.where(x <= seats, "seats_available", np.where(x <= config.STANDING_FRACTION_OF_CRUSH * crush, "standing_room", "crowded"))


def haversine_km(lat1, lon1, lat2, lon2):
    """Straight-line distance between two lat/lon points in km (works on arrays)."""
    la1, lo1, la2, lo2 = map(np.radians, (lat1, lon1, lat2, lon2))
    h = np.sin((la2 - la1) / 2) ** 2 + np.cos(la1) * np.cos(la2) * np.sin((lo2 - lo1) / 2) ** 2
    return 6371.0 * 2 * np.arcsin(np.sqrt(h))


LEVEL_LABEL = {"low": "Quiet", "medium": "Moderate", "high": "Busy"}
LEVEL_ORDER = ["low", "medium", "high"]

TIER_LABEL = {"seats_available": "Seats available", "standing_room": "Standing room", "crowded": "Crowded"}
TIER_ORDER = ["seats_available", "standing_room", "crowded"]
TIER_KEY = {"seats_available": "low", "standing_room": "medium", "crowded": "high"}     # used inside the planner
