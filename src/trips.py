"""
Tickets do NOT say which trip they belong to.

locate_tickets(): for every ticket find the boarding stop number (b) and alighting stop number (a) on its route
infer_trips():    group the tickets of one vehicle into trips.  (Only used for an EXPERIMENT in notebook 03 that
                  shows why we do not build the crowd model on reconstructed trips: the data is too sparse.)
"""
import numpy as np
import pandas as pd
import config
from src.common import norm_route, band_of


def locate_tickets(tix, stop_map, patterns):
    """Work out WHERE each ticket was used: b = boarding stop number, a = alighting stop number on the route.

    In this dataset the route name already contains the direction (8UP / 8DOWN) and the GTFS has one pattern
    per direction, so a ticket's route tells us the direction - we only need the two stop numbers.
    If the alighting stop is missing / not matched we assume the typical ride length of that route.
    Returns (tickets_with_b_a, report_dict)."""
    idx = patterns.groupby(["route_n", "name_n"]).idx.apply(list).to_dict()
    nstops = patterns.groupby("route_n").idx.max().add(1).to_dict()

    tix = tix.copy()
    tix["rid"] = np.arange(len(tix))                    # a simple ticket id
    tix["route_n"] = tix.route_raw.astype(str).map(norm_route)
    mp = stop_map.dropna(subset=["gtfs_name_n"]).set_index(["route_raw", "name"]).gtfs_name_n.to_dict()
    sn = tix.start_name.astype(object).where(tix.start_name.notna(), None)     # blank names -> None (safe dictionary key)
    en = tix.end_name.astype(object).where(tix.end_name.notna(), None)
    rr = tix.route_raw.astype(str)
    tix["s_n"] = [mp.get((r, n)) for r, n in zip(rr, sn)]
    tix["e_n"] = [mp.get((r, n)) for r, n in zip(rr, en)]

    # far fewer DISTINCT (route, start, end) combinations than tickets -> resolve each combination once
    combo = tix[["route_n", "s_n", "e_n"]].fillna("").drop_duplicates()

    def resolve(route_n, s_n, e_n):
        S, E = idx.get((route_n, s_n), []), idx.get((route_n, e_n), []) if e_n else []
        best = None
        for b in S:                                    # loop routes can visit the same stop twice
            for a in E:
                if a > b and (best is None or a - b < best[1] - best[0]):
                    best = (b, a)
        if best:
            return best[0], best[1], "ok"
        if S:
            return S[0], np.nan, "end_missing"         # boarding known, alighting unknown
        return np.nan, np.nan, "start_unmatched"

    out = [resolve(r, s, e) for r, s, e in combo.itertuples(index=False)]
    combo[["b", "a", "status"]] = pd.DataFrame(out, index=combo.index)
    tix = tix.assign(_s=tix.s_n.fillna(""), _e=tix.e_n.fillna(""))
    tix = tix.merge(combo.rename(columns={"s_n": "_s", "e_n": "_e"}), on=["route_n", "_s", "_e"], how="left")
    n_all = len(tix)
    status_all = tix.status.value_counts().to_dict()
    tix = tix[tix.status != "start_unmatched"].copy()

    # typical ride length (in stops) per route, measured from the tickets where both stops are known
    ok = tix[tix.status == "ok"]
    med_len = (ok.a - ok.b).groupby(ok.route_n).median().to_dict()
    need = tix.a.isna()
    ride = np.array([med_len.get(r, 3) for r in tix.route_n[need]])
    last = np.array([nstops.get(r, 2) - 1 for r in tix.route_n[need]])
    tix.loc[need, "a"] = np.minimum(tix.b[need] + np.maximum(1, np.round(ride)), last)
    tix["imputed_end"] = need
    tix = tix[tix.a > tix.b].copy()                    # boarding at the very last stop carries nobody anywhere
    tix[["b", "a"]] = tix[["b", "a"]].astype(int)
    tix["dir"] = 0                                     # direction is part of the route name
    report = dict(n_tickets_in=n_all, status_all=status_all, n_tickets_kept=len(tix),
                  share_kept=len(tix) / n_all, share_imputed_end=float(tix.imputed_end.mean()))
    return tix.drop(columns=["_s", "_e"]), report


def infer_trips(tix):
    """Group each vehicle's time-ordered tickets into trips. Returns (tickets_with_trip_no, trips)."""
    tix = tix.sort_values(["vehicle", "ts", "rid"]).reset_index(drop=True)
    gap = tix.groupby("vehicle", sort=False).ts.diff().dt.total_seconds().div(60)
    new_trip = ((tix.vehicle != tix.vehicle.shift())                    # a different vehicle
                | (gap > config.TRIP_GAP_MIN)                            # long silence
                | (tix.route_n != tix.route_n.shift())                   # changed route
                | (tix.dir != tix.dir.shift())                           # changed direction
                | ((tix.b.shift() - tix.b) > config.TRIP_BACKSTEP))      # boarding stop jumped backwards
    tix["trip_no"] = new_trip.cumsum()
    tr = tix.groupby("trip_no").agg(vehicle=("vehicle", "first"), route_n=("route_n", "first"), route=("route_raw", "first"),
                                    dir=("dir", "first"), start_ts=("ts", "min"), end_ts=("ts", "max"),
                                    n_tickets=("rid", "size"), pax=("pax", "sum"), first_b=("b", "min"),
                                    last_a=("a", "max"), is_ac=("is_ac", "max")).reset_index()
    tr["date"] = tr.start_ts.dt.strftime("%Y-%m-%d")
    tr["hour"] = tr.start_ts.dt.hour
    tr["dow"] = tr.start_ts.dt.dayofweek
    tr["daytype"] = np.where(tr.dow < 5, "weekday", "weekend")
    tr["band"] = tr.hour.map(band_of)
    tr["week"] = (tr.start_ts.dt.day - 1) // 7 + 1
    return tix, tr
