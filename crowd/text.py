import re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # so `import config` works from notebooks too
import config  # noqa

_ABBR = {"stn": "station", "nr": "near", "opp": "opposite", "mkt": "market", "rd": "road", "sec": "sector",
         "ext": "extension", "pt": "point", "dep": "depot", "ngr": "nagar", "vihar": "vihar", "cc": "chowk",
         "i s b t": "isbt", "isbt": "isbt", "clny": "colony", "col": "colony", "mor": "mor", "bs": "", "bus stop": "",
         "bus stand": "", "metro stn": "metro station", "hosp": "hospital", "univ": "university", "ph": "phase", "xing": "crossing", "x ing": "crossing", "xng": "crossing"}

def norm_name(s) -> str:
    """Normalise a stop name: lowercase, strip punctuation, expand common abbreviations."""
    if s is None or (isinstance(s, float) and s != s):
        return ""
    s = str(s).lower().strip()
    s = s.replace("&", " and ").replace("i.s.b.t.", "isbt").replace("i.s.b.t", "isbt")
    s = re.sub(r"[\(\)\[\]\.,/\\\-_'\"]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"\b([a-z])\s(?=[a-z]\b)", r"\1", s)      # "s j hospital" -> "sj hospital"
    for k in sorted(_ABBR, key=len, reverse=True):
        s = re.sub(rf"\b{re.escape(k)}\b", _ABBR[k], s)
    return re.sub(r"\s+", " ", s).strip()

def norm_route(s) -> str:
    return re.sub(r"\s+", "", str(s)).upper().lstrip("0") if s is not None else ""

def band_of(hour: int) -> str:
    for b, (lo, hi) in config.BANDS.items():
        if lo <= hour < hi:
            return b
    return "night"

def level_of(load_adj, is_ac, pass_factor=None, cap_scale=1.0):
    """Map an (already pass-adjusted) on-board load to seats / standing / crowded. Works on scalars or numpy arrays."""
    import numpy as np
    ac = np.asarray(is_ac).astype(bool)
    seats = np.where(ac, config.CAPACITY["ac"]["seats"], config.CAPACITY["nonac"]["seats"]) * cap_scale
    crush = np.where(ac, config.CAPACITY["ac"]["crush"], config.CAPACITY["nonac"]["crush"]) * cap_scale
    x = np.asarray(load_adj, dtype=float)
    return np.where(x <= seats, "seats", np.where(x <= config.STANDING_FRACTION_OF_CRUSH * crush, "standing", "crowded"))

def confidence_of(n_tickets):
    """high / medium / low from the number of tickets that cover a stretch-cell."""
    import numpy as np
    n = np.asarray(n_tickets)
    return np.where(n >= config.CONF_TICKETS_HIGH, "high", np.where(n >= config.CONF_TICKETS_MED, "medium", "low"))

LEVEL_LABEL = {"seats": "Seats available", "standing": "Standing room", "crowded": "Crowded"}
