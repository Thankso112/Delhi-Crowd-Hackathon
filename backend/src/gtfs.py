"""
GTFS = the standard timetable files every transit agency publishes (stops.txt, routes.txt, trips.txt, stop_times.txt).

build_patterns()  -> for each route and direction: the ordered list of stops (the "route pattern")
match_stop_names() -> link the stop NAMES typed on tickets to the real GTFS stops of that route
"""
import pandas as pd
from rapidfuzz import process, fuzz
import config
from src.common import norm_name, norm_route


def build_patterns(gtfs_dir=None):
    """Return (patterns, hourly, trip_starts).
    patterns: one row per route/direction/stop, in order (idx = 0,1,2,...), with lat/lon and seconds since the first stop.
    hourly:   how many scheduled trips start in each hour for each route/direction (the bus frequency).
    trip_starts: one row per scheduled trip (route_n, t0 = start time in seconds) - used to count buses per stretch."""
    g = gtfs_dir or config.GTFS_DIR
    rd = lambda f: pd.read_csv(g / f, dtype=str, keep_default_na=False)
    stops, routes, trips, st = rd("stops.txt"), rd("routes.txt"), rd("trips.txt"), rd("stop_times.txt")

    stops = stops.assign(lat=stops.stop_lat.astype(float), lon=stops.stop_lon.astype(float))[["stop_id", "stop_name", "lat", "lon"]]
    trips["dir"] = pd.to_numeric(trips["direction_id"], errors="coerce").fillna(0).astype(int) if "direction_id" in trips else 0
    trips = trips[["route_id", "trip_id", "dir"]]

    # clock time "HH:MM:SS" -> seconds after midnight (GTFS allows hours above 24)
    t = st.arrival_time.where(st.arrival_time != "", st.departure_time)
    p = t.str.split(":", expand=True).astype(int)
    st = st.assign(seq=st.stop_sequence.astype(int), sec=p[0] * 3600 + p[1] * 60 + p[2])
    st = st.sort_values(["trip_id", "seq"])

    # a trip's "signature" = its stop ids joined together. Trips with the same signature follow the same pattern.
    sig = st.groupby("trip_id").agg(sig=("stop_id", "|".join), t0=("sec", "min")).reset_index()
    tp = trips.merge(sig, on="trip_id")
    pat = (tp.groupby(["route_id", "dir", "sig"])
             .agg(rep_trip=("trip_id", "first"), n_trips=("trip_id", "size")).reset_index()
             .sort_values(["route_id", "dir", "n_trips", "sig"], ascending=[True, True, False, True])
             .drop_duplicates(["route_id", "dir"]))       # keep the MOST COMMON pattern of each route/direction

    patterns = pat.merge(st, left_on="rep_trip", right_on="trip_id").sort_values(["route_id", "dir", "seq"])
    patterns["idx"] = patterns.groupby(["route_id", "dir"]).cumcount()
    patterns["cum_sec"] = patterns.sec - patterns.groupby(["route_id", "dir"]).sec.transform("min")
    patterns = (patterns.merge(stops, on="stop_id").merge(routes[["route_id", "route_short_name"]], on="route_id")
                .rename(columns={"route_short_name": "route"})
                .sort_values(["route_id", "dir", "idx"]).reset_index(drop=True))
    patterns = patterns[["route", "route_id", "dir", "n_trips", "idx", "stop_id", "stop_name", "lat", "lon", "cum_sec"]]
    patterns["route_n"] = patterns.route.map(norm_route)
    patterns["name_n"] = patterns.stop_name.map(norm_name)

    tp = tp.merge(routes[["route_id", "route_short_name"]], on="route_id")
    tp["hour"] = (tp.t0 // 3600) % 24
    hourly = tp.groupby(["route_short_name", "dir", "hour"]).size().rename("n_trips").reset_index().rename(columns={"route_short_name": "route"})
    hourly["route_n"] = hourly.route.map(norm_route)
    trip_starts = tp[["route_short_name", "t0"]].rename(columns={"route_short_name": "route"})
    trip_starts["route_n"] = trip_starts.route.map(norm_route)
    return patterns, hourly, trip_starts[["route_n", "t0"]]


def supply_by_stretch(patterns, trip_starts):
    """SUPPLY: how many scheduled buses pass each stretch (stop i -> i+1) in each hour of the day.
    A trip that starts at t0 reaches stretch i at t0 + cum_sec[i] (the timetable's travel time)."""
    last = patterns.groupby("route_n").idx.transform("max")
    pat = patterns.loc[patterns.idx < last, ["route_n", "idx", "cum_sec"]]
    m = trip_starts.merge(pat, on="route_n")
    m["hour"] = ((m.t0 + m.cum_sec) // 3600) % 24
    return (m.groupby(["route_n", "hour", "idx"]).size().rename("n_sched").reset_index().rename(columns={"idx": "pos"}))


def _partial(name, cands):
    """Ticket names are often shorter than the official stop name ('Mahipal Pur' vs 'Mahipal Pur Village').
    Accept a candidate that CONTAINS all words of the ticket name; among those pick the closest overall."""
    top = process.extract(name, cands, scorer=fuzz.token_set_ratio, limit=6)
    top = [t for t in top if t[1] >= config.PARTIAL_THRESHOLD]
    if not top:
        return None
    best = max(top, key=lambda t: fuzz.token_sort_ratio(name, t[0]))
    return best[0], float(best[1])


def match_stop_names(name_counts, patterns):
    """name_counts: DataFrame[route_raw, name, n] (every stop name typed on tickets and how often).
    For each one, find the GTFS stop of the SAME route it refers to. Tiers, first success wins:
      exact_route            same text as a stop name or ALIAS on that route
      fuzzy_route            very similar text (score >= 86)
      partial_route          ticket name is part of a longer stop name ("Mahipal Pur" -> "Mahipal Pur Village")
      fuzzy_no_spaces        same letters, different spacing ("azad pur" / "azadpur")
      fuzzy_global_offroute  near-identical stop elsewhere in Delhi (strict; cannot be used for the journey)
    ALIASES: GTFS names are often composite ("Laxmi Nagar Metro Station / Laxmi Nagar"), tickets use one simple form,
    so every '/'-separated part of a GTFS name becomes an alias that points back to the full name."""
    tk = name_counts.groupby(["route_raw", "name"], dropna=False, as_index=False).n.sum()
    tk["route_n"] = tk.route_raw.map(norm_route)
    tk["name_n"] = tk.name.map(norm_name)
    alias = {}                                                    # route_n -> {alias text: full normalised stop name}
    for rn, nm in zip(patterns.route_n, patterns.stop_name):
        full = norm_name(nm); d = alias.setdefault(rn, {})
        d.setdefault(full, full)
        for part in str(nm).split("/"):
            pn = norm_name(part)
            if pn: d.setdefault(pn, full)
    nospace = {rn: {k.replace(" ", ""): v for k, v in d.items()} for rn, d in alias.items()}
    glob = patterns.drop_duplicates("name_n").name_n.tolist()
    res = []
    for r in tk.itertuples():
        method, score, hit = "none", 0.0, None
        if not r.name_n:
            method = "blank"
        elif r.route_n not in alias:
            method = "route_not_in_gtfs"
        else:
            al = alias[r.route_n]; keys = list(al)
            if r.name_n in al:
                hit, score, method = al[r.name_n], 100.0, "exact_route"
            else:
                m = process.extractOne(r.name_n, keys, scorer=fuzz.token_sort_ratio)
                if m and m[1] >= config.FUZZY_ROUTE_THRESHOLD:
                    hit, score, method = al[m[0]], m[1], "fuzzy_route"
                elif len(r.name_n) >= 4 and (part := _partial(r.name_n, keys)):
                    hit, score, method = al[part[0]], part[1], "partial_route"
                else:
                    ns = nospace[r.route_n]
                    m = process.extractOne(r.name_n.replace(" ", ""), list(ns), scorer=fuzz.ratio)
                    if m and m[1] >= 92:
                        hit, score, method = ns[m[0]], m[1], "fuzzy_no_spaces"
                    else:
                        m = process.extractOne(r.name_n, glob, scorer=fuzz.token_sort_ratio)
                        if m and m[1] >= config.FUZZY_GLOBAL_THRESHOLD:
                            hit, score, method = m[0], m[1], "fuzzy_global_offroute"
        res.append((r.route_raw, r.route_n, r.name, r.name_n, hit, score, method, r.n))
    return pd.DataFrame(res, columns=["route_raw", "route_n", "name", "name_n", "gtfs_name_n", "score", "method", "n_uses"])
