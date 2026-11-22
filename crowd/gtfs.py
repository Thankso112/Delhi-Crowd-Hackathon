"""Step 2: read static GTFS and build, for every route and direction, the ordered list of stops (a 'pattern')."""
import numpy as np, pandas as pd
from crowd.text import config, norm_name, norm_route

def _to_seconds(series: pd.Series) -> pd.Series:
    """GTFS times look like '17:45:00' (hours can exceed 24). Convert to seconds after midnight."""
    p = series.str.split(":", expand=True).apply(pd.to_numeric, errors="coerce")
    return p[0] * 3600 + p[1] * 60 + p[2]

def build_patterns(gtfs_dir=None):
    """Returns (patterns, hourly_trips, stops).
    patterns: one row per stop of the MOST COMMON stop sequence of each route+direction (idx = position along the route).
    hourly_trips: how many trips start in each hour (used for waiting time)."""
    G = gtfs_dir or config.GTFS_DIR
    stops = pd.read_csv(G / "stops.txt", dtype={"stop_id": str}).rename(columns={"stop_lat": "lat", "stop_lon": "lon"})[["stop_id", "stop_name", "lat", "lon"]]
    routes = pd.read_csv(G / "routes.txt", dtype={"route_id": str, "route_short_name": str})[["route_id", "route_short_name"]]
    tcols = pd.read_csv(G / "trips.txt", nrows=0).columns
    trips = pd.read_csv(G / "trips.txt", dtype=str)
    trips["dir"] = pd.to_numeric(trips["direction_id"], errors="coerce").fillna(0).astype(int) if "direction_id" in tcols else 0
    trips = trips[["route_id", "trip_id", "dir"]]
    st = pd.read_csv(G / "stop_times.txt", dtype=str, usecols=["trip_id", "stop_id", "stop_sequence", "arrival_time", "departure_time"])
    st["seq"] = st.stop_sequence.astype(int)
    st["sec"] = _to_seconds(st.arrival_time.fillna(st.departure_time))
    st = st.sort_values(["trip_id", "seq"])

    sig = st.groupby("trip_id").agg(sig=("stop_id", "|".join), t0=("sec", "min")).reset_index()     # a trip's stop sequence as one string
    tr = trips.merge(sig, on="trip_id")
    pat = tr.groupby(["route_id", "dir", "sig"]).agg(n_trips=("trip_id", "size"), rep_trip=("trip_id", "first")).reset_index()
    best = pat.sort_values(["n_trips", "sig"], ascending=[False, True]).drop_duplicates(["route_id", "dir"])   # most common pattern wins

    rep = st[st.trip_id.isin(best.rep_trip)].merge(best[["route_id", "dir", "rep_trip", "n_trips"]], left_on="trip_id", right_on="rep_trip")
    rep = rep.sort_values(["route_id", "dir", "seq"])
    rep["idx"] = rep.groupby(["route_id", "dir"]).cumcount()
    rep["cum_sec"] = rep.sec - rep.groupby(["route_id", "dir"]).sec.transform("min")
    pats = rep.merge(stops, on="stop_id").merge(routes, on="route_id").rename(columns={"route_short_name": "route"})
    pats = pats.sort_values(["route_id", "dir", "idx"])[["route", "route_id", "dir", "n_trips", "idx", "stop_id", "stop_name", "lat", "lon", "cum_sec"]].reset_index(drop=True)
    pats["route_n"] = pats.route.map(norm_route)
    pats["name_n"] = pats.stop_name.map(norm_name)

    tr["hour"] = (tr.t0 // 3600 % 24).astype(int)
    hourly = tr.merge(routes, on="route_id").groupby(["route_short_name", "dir", "hour"]).size().rename("n_trips").reset_index().rename(columns={"route_short_name": "route"})
    hourly["route_n"] = hourly.route.map(norm_route)
    return pats, hourly, stops
