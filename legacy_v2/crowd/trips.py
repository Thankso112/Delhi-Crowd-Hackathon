"""Step 4: for every ticket find (direction, boarding index, alighting index) on its route, then group tickets into trips.
Tickets have NO trip id, so a trip is rebuilt as: consecutive tickets of one vehicle on one route and direction."""
import numpy as np, pandas as pd
from crowd.text import config, norm_route, band_of

def resolve_tickets(tix: pd.DataFrame, pat: pd.DataFrame, sm: pd.DataFrame):
    idx = pat.groupby(["route_n", "dir", "name_n"]).idx.apply(list).to_dict()    # positions of a stop name along a route+direction
    dirs = pat.groupby("route_n").dir.unique().map(list).to_dict()
    nstops = pat.groupby(["route_n", "dir"]).idx.max().add(1).to_dict()

    def resolve(route_n, s_n, e_n):
        """Pick the direction where the passenger boards BEFORE alighting (smallest positive gap if a stop repeats)."""
        best = None
        for d in dirs.get(route_n, []):
            S, E = idx.get((route_n, d, s_n), []), (idx.get((route_n, d, e_n), []) if e_n else [])
            for b in S:
                for a in E:
                    if a > b and (best is None or a - b < best[2] - best[1]):
                        best = (d, b, a, "ok")
        if best:
            return best
        # End stop missing/unmatched/odd: boarding is still usable if the start stop is on exactly one direction of the route
        with_start = [d for d in dirs.get(route_n, []) if idx.get((route_n, d, s_n))]
        if len(with_start) == 1:                         # real data: UP/DOWN are separate routes, so this is the common case
            return (with_start[0], idx[(route_n, with_start[0], s_n)][0], None, "single_dir_no_end")
        if with_start:
            return (None, None, None, "ambiguous_dir")   # direction decided later from neighbouring tickets of the same vehicle
        return (None, None, None, "start_unmatched")

    tix = tix.copy()
    tix["rid"] = np.arange(len(tix))
    tix["route_n"] = tix.route_raw.astype(str).map(norm_route)
    mp = sm.dropna(subset=["gtfs_name_n"]).set_index(["route_raw", "name"]).gtfs_name_n.to_dict()
    rr = tix.route_raw.astype(str)
    tix["s_n"] = [mp.get((r, n)) for r, n in zip(rr, tix.start_name)]
    tix["e_n"] = [mp.get((r, n)) for r, n in zip(rr, tix.end_name)]

    combos = tix[["route_n", "s_n", "e_n"]].fillna("").drop_duplicates()          # far fewer than tickets -> fast
    out = [resolve(r, s, e) for r, s, e in combos.itertuples(index=False)]
    combos[["dir", "b", "a", "status"]] = pd.DataFrame(out, index=combos.index)
    tix["_s"], tix["_e"] = tix.s_n.fillna(""), tix.e_n.fillna("")
    tix = tix.merge(combos.rename(columns={"s_n": "_s", "e_n": "_e"}), on=["route_n", "_s", "_e"], how="left")
    n_all = len(tix)
    tix = tix[tix.status != "start_unmatched"].sort_values(["vehicle", "route_n", "ts", "rid"]).reset_index(drop=True)

    # Tickets with unknown direction inherit it from the nearest resolved ticket of the same vehicle+route (within the gap limit)
    amb = tix.status == "ambiguous_dir"
    known_veh = tix.vehicle.notna()                      # ~49% of real tickets have no vehicle: they cannot borrow a direction
    okdir, okts = tix.dir.where(~amb), tix.ts.where(~amb)
    g = [tix.vehicle.astype(object).fillna("?"), tix.route_n]
    prev_d, prev_t = okdir.groupby(g).ffill(), okts.groupby(g).ffill()
    next_d, next_t = okdir.groupby(g).bfill(), okts.groupby(g).bfill()
    lim = pd.Timedelta(minutes=config.TRIP_GAP_MIN)
    use_prev = amb & known_veh & prev_d.notna() & ((tix.ts - prev_t) <= lim)
    use_next = amb & known_veh & ~use_prev & next_d.notna() & ((next_t - tix.ts) <= lim)
    tix.loc[use_prev, "dir"] = prev_d[use_prev]
    tix.loc[use_next, "dir"] = next_d[use_next]
    dropped_dir = int((amb & ~use_prev & ~use_next).sum())
    tix = tix[tix.dir.notna()].copy()
    fix = tix.status == "ambiguous_dir"
    tix.loc[fix, "b"] = [(idx.get((r, int(d), s)) or [np.nan])[0] for r, d, s in zip(tix.route_n[fix], tix.dir[fix], tix.s_n[fix])]
    tix = tix[tix.b.notna()].copy()

    # Missing alighting stop -> assume boarding + the typical ride length (in stops) on that route and direction
    med_len = (tix[tix.status == "ok"].a - tix[tix.status == "ok"].b).groupby([tix[tix.status == "ok"].route_n, tix[tix.status == "ok"].dir]).median().to_dict()
    need = tix.a.isna()
    ride = np.array([med_len.get((r, d), 3) for r, d in zip(tix.route_n[need], tix.dir[need])])
    last = np.array([nstops.get((r, d), 2) - 1 for r, d in zip(tix.route_n[need], tix.dir[need])])
    tix.loc[need, "a"] = np.minimum(tix.b[need] + np.maximum(1, np.round(ride)), last)
    tix["imputed_end"] = need
    tix = tix[tix.a > tix.b].copy()
    tix[["b", "a", "dir"]] = tix[["b", "a", "dir"]].astype(int)
    stats = dict(tickets_in=n_all, tickets_kept=len(tix), dropped_direction_unknown=dropped_dir, imputed_end_share=float(tix.imputed_end.mean()))
    return tix, stats

def infer_trips(tix: pd.DataFrame):
    """Split each vehicle's time-ordered tickets into trips; returns (tickets with trip_no, one-row-per-trip table)."""
    tix = tix[tix.vehicle.notna()].sort_values(["vehicle", "ts", "rid"]).reset_index(drop=True)   # only tickets with a vehicle can form trips
    gap_min = tix.groupby("vehicle", sort=False, observed=True).ts.diff().dt.total_seconds().div(60)
    new_trip = ((tix.vehicle != tix.vehicle.shift()) | (gap_min > config.TRIP_GAP_MIN) | (tix.route_n != tix.route_n.shift())
                | (tix.dir != tix.dir.shift()) | ((tix.b.shift() - tix.b) > config.TRIP_BACKSTEP))
    tix["trip_no"] = new_trip.cumsum()
    tr = tix.groupby("trip_no").agg(vehicle=("vehicle", "first"), route_n=("route_n", "first"), route=("route_raw", "first"), dir=("dir", "first"),
                                    start_ts=("ts", "min"), end_ts=("ts", "max"), n_tickets=("rid", "size"), pax=("pax", "sum"),
                                    first_b=("b", "min"), last_a=("a", "max"), is_ac=("is_ac", "max")).reset_index()
    tr["vehicle"], tr["route"] = tr.vehicle.astype(str), tr.route.astype(str)
    tr["date"] = tr.start_ts.dt.date.astype(str)
    tr["daytype"] = np.where(tr.start_ts.dt.dayofweek < 5, "weekday", "weekend")
    tr["band"] = tr.start_ts.dt.hour.map(band_of)
    tr["week"] = (tr.start_ts.dt.day - 1) // 7 + 1
    return tix, tr
