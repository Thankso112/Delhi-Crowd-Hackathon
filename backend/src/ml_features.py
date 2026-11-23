"""
Turn the hourly crowd table into a machine-learning dataset.

Each ROW  = one stretch (stop i -> stop i+1) of one route, at one hour, on weekdays or weekends.
TARGET    = crowd index (ticketed riders per scheduled bus)      -> REGRESSION
            or Quiet / Moderate / Busy built from that index    -> CLASSIFICATION
FEATURES  = things we know WITHOUT looking at tickets: time, position on the route, distance to the city
            centre, how many buses run (timetable), AC or not ...
"""
import numpy as np
import pandas as pd
import config
from src.common import haversine_km, to_percentile, level_of_pct

FEATURES = ["hour", "is_weekend", "is_am_peak", "is_pm_peak", "is_up", "pos", "n_stops", "pos_frac", "is_ac",
            "buses_per_hour", "dist_from_centre_km", "towards_centre", "lat", "lon", "route_len_km"]


def build_ml_dataset(hourly_cells, patterns, route_attrs, min_tickets=None):
    min_tickets = config.ML_MIN_TICKETS if min_tickets is None else min_tickets
    df = hourly_cells[hourly_cells.n_tix >= min_tickets].copy()

    p = patterns[["route_n", "idx", "lat", "lon"]].sort_values(["route_n", "idx"]).copy()
    c0, c1 = config.CITY_CENTRE
    p["d_centre"] = haversine_km(p.lat, p.lon, c0, c1)
    g = p.groupby("route_n")
    step = haversine_km(p.lat, p.lon, g.lat.shift(), g.lon.shift()).fillna(0)          # km from the previous stop
    p["route_len_km"] = step.groupby(p.route_n).transform("sum")
    p["n_stops"] = g.idx.transform("max") + 1

    frm = p.rename(columns={"idx": "pos", "d_centre": "dist_from_centre_km"})
    to = p[["route_n", "idx", "d_centre"]].assign(pos=lambda x: x.idx - 1).rename(columns={"d_centre": "d_to"})[["route_n", "pos", "d_to"]]
    df = df.merge(frm, on=["route_n", "pos"], how="left").merge(to, on=["route_n", "pos"], how="left")
    df["towards_centre"] = (df.d_to < df.dist_from_centre_km).astype(int)          # does this stretch head INTO the city?
    df["pos_frac"] = df.pos / (df.n_stops - 1)                                       # 0 = first stop, 1 = last stop
    df = df.merge(route_attrs[["route_n", "route", "is_ac"]], on="route_n", how="left")
    df["is_up"] = df.route_n.str.endswith("UP").astype(int)
    df["is_weekend"] = (df.daytype == "weekend").astype(int)
    df["is_am_peak"] = df.hour.between(7, 9).astype(int)
    df["is_pm_peak"] = df.hour.between(16, 19).astype(int)
    df["buses_per_hour"] = df.n_sched

    df = df.dropna(subset=FEATURES + ["idx"]).reset_index(drop=True)
    df["level"] = level_of_pct(to_percentile(df.idx, df.idx))
    return df[["route", "route_n"] + FEATURES + ["n_tix", "idx", "level"]]
