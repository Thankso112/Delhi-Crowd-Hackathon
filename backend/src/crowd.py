"""
The crowd model.

IDEA (in one line):   crowd index  =  ticketed riders on a stretch  /  buses scheduled on that stretch.

Because the ticket file is only a SAMPLE of all riders, the index is not a head-count. It is a fair way to
compare "which stretch/time is busier" - so we report it RELATIVE to the rest of the network.

1. explode_demand():      spread every ticket over the stretches it travelled (stop b -> stop a), shifting
                          the time forward using the timetable's travel times.
2. build_crowd_tables():  divide by scheduled buses, handle thin data (shrinkage), convert to percentiles/levels.
"""
import numpy as np
import pandas as pd
import config
from src.common import to_percentile, level_of_pct, confidence_of, capacity_of, tier_of
import config

DAYTYPES = ("weekday", "weekend")


def explode_demand(tix, patterns, chunk=400_000):
    """DEMAND: how many ticketed passengers were on board each stretch, by route / daytype / hour.
    A ticket boarding at stop b and leaving at stop a is "on board" on stretches b, b+1, ..., a-1.
    Returns DataFrame[route_n, daytype, hour, pos, pax_sum, n_tix]."""
    pat = patterns.sort_values(["route_n", "idx"]).reset_index(drop=True)
    first = pat.groupby("route_n").cumcount() == 0
    offset = pd.Series(np.flatnonzero(first.to_numpy()), index=pat.route_n[first].to_numpy())   # row where each route starts
    cum = pat.cum_sec.to_numpy(dtype=np.int64)
    rnames = offset.index.to_numpy()
    rcode = pd.Series(np.arange(len(rnames)), index=rnames)
    K = int(pat.idx.max()) + 1

    t = tix[tix.route_n.isin(rcode.index)]
    rc = t.route_n.map(rcode).to_numpy(np.int64)
    off = t.route_n.map(offset).to_numpy(np.int64)
    b, a, pax = t.b.to_numpy(np.int64), t.a.to_numpy(np.int64), t.pax.to_numpy(np.int64)
    sec = (t.ts.dt.hour * 3600 + t.ts.dt.minute * 60 + t.ts.dt.second).to_numpy(np.int64)
    dt = (t.daytype == "weekend").to_numpy(np.int64)

    parts = []
    for s in range(0, len(t), chunk):
        sl = slice(s, s + chunk)
        L = a[sl] - b[sl]
        i = np.repeat(np.arange(len(L)), L)
        start = np.cumsum(L) - L
        p = b[sl][i] + (np.arange(L.sum()) - np.repeat(start, L))              # every stretch number travelled
        secs = sec[sl][i] + cum[off[sl][i] + p] - cum[off[sl][i] + b[sl][i]]    # time the bus reaches that stretch
        hour = (secs // 3600) % 24
        key = ((rc[sl][i] * 2 + dt[sl][i]) * 24 + hour) * K + p
        parts.append(pd.DataFrame({"key": key, "pax": pax[sl][i]}).groupby("key").pax.agg(pax_sum="sum", n_tix="size"))
    d = pd.concat(parts).groupby(level=0).sum().reset_index()
    out = pd.DataFrame({"route_n": rnames[d.key // (K * 48)], "daytype": np.where((d.key // (K * 24)) % 2 == 0, "weekday", "weekend"),
                        "hour": (d.key // K) % 24, "pos": d.key % K, "pax_sum": d.pax_sum, "n_tix": d.n_tix})
    return out


def _calibrate(df, idx_col, is_ac):
    """ticketed riders per bus -> estimated people on board, capacity, load ratio and the organizers' tier."""
    raw = df[idx_col] * config.SCALE["base"]
    df["capacity"] = capacity_of(is_ac)
    df["est_load_raw"] = raw
    df["est_load"] = np.minimum(raw, config.LOAD_CAP_RATIO * df.capacity)     # cap: see LOAD_CAP_RATIO in config.py
    df["load_ratio"] = df.est_load / df.capacity
    df["crowd_level"] = tier_of(df.est_load, is_ac)
    return df


def _hourly(grid, rh, rb, gl, k, attrs, patterns):
    """Hourly crowd table for ONE day type (done one at a time to keep memory low).
    Fallback chain for thin cells:  stretch-hour  ->  route-hour  ->  route-band  ->  city."""
    ct = (grid.merge(rh[["route_n", "daytype", "hour", "n_tickets", "rh_idx"]].rename(columns={"n_tickets": "rh_tix"}), on=["route_n", "daytype", "hour"], how="left")
               .merge(rb[["route_n", "daytype", "band", "route_idx"]], on=["route_n", "daytype", "band"], how="left")
               .merge(gl[["daytype", "band", "g_idx"]], on=["daytype", "band"], how="left"))
    prior = pd.Series(np.where(ct.rh_tix >= config.CONF_MED, ct.rh_idx, ct.route_idx), index=ct.index).fillna(ct.g_idx)
    ct["est_idx"] = (ct.n_tix * ct.idx + k * prior) / (ct.n_tix + k)                 # thin cells lean on their fallback
    ct["fallback"] = np.where(ct.n_tix >= config.CONF_MED, "stretch_hour",
                      np.where(ct.rh_tix >= config.CONF_MED, "route_hour", np.where(ct.route_idx.notna(), "route_band", "city")))
    ct["confidence"] = confidence_of(ct.n_tix)
    ct["is_ac"] = ct.route_n.map(attrs).fillna(0).astype(int)
    ct = _calibrate(ct, "est_idx", ct.is_ac).rename(columns={"n_tix": "ticket_count"})
    sid = patterns[["route_n", "idx", "stop_id"]]
    ct = (ct.merge(sid.rename(columns={"idx": "pos", "stop_id": "from_stop_id"}), on=["route_n", "pos"], how="left")
            .merge(sid.assign(pos=sid.idx - 1).drop(columns="idx").rename(columns={"stop_id": "to_stop_id"}), on=["route_n", "pos"], how="left"))
    return ct[["route_n", "daytype", "hour", "pos", "from_stop_id", "to_stop_id", "n_sched", "ticket_count", "est_idx", "est_load", "est_load_raw",
               "capacity", "load_ratio", "crowd_level", "confidence", "fallback", "is_ac"]]


def build_crowd_tables(demand, supply, n_days, patterns, route_attrs, hourly_table=True):
    """Returns dict of DataFrames:
       crowd_table  - hourly, the main lookup: (route, stretch, hour, daytype) -> est_load, capacity, load_ratio, crowd_level, confidence
                      (None if hourly_table=False, used to speed up validation runs)
       segments     - the same by time band (used by the journey planner)
       route_level, global_level, hourly_cells (raw cells with tickets, used for machine learning)."""
    attrs = route_attrs.set_index("route_n").is_ac
    # --- full grid of (route, daytype, hour, stretch) with at least one scheduled bus; demand = 0 if no tickets
    grid = pd.concat([supply.assign(daytype=d) for d in DAYTYPES], ignore_index=True)
    grid = grid.merge(demand, on=["route_n", "daytype", "hour", "pos"], how="left")
    grid[["pax_sum", "n_tix"]] = grid[["pax_sum", "n_tix"]].fillna(0)
    grid = grid.astype({"hour": "int16", "pos": "int16", "n_sched": "int32"})
    grid["idx"] = grid.pax_sum / (grid.daytype.map(n_days) * grid.n_sched)      # ticketed riders per scheduled bus
    lost_share = 1 - grid.pax_sum.sum() / demand.pax_sum.sum()                   # demand where no bus is scheduled (reported, ignored)
    hourly = grid[grid.n_tix > 0].reset_index(drop=True)

    band_of_hour = {h: b for b, (lo, hi) in config.BANDS.items() for h in range(lo, hi)}
    grid["band"] = grid.hour.map(band_of_hour)
    k = config.SHRINK_K
    agg = dict(pax_sum=("pax_sum", "sum"), n_tickets=("n_tix", "sum"), n_sched=("n_sched", "sum"))
    rb = grid.groupby(["route_n", "daytype", "band"], as_index=False).agg(**agg)
    rb["route_idx"] = rb.pax_sum / (rb.daytype.map(n_days) * rb.n_sched)
    rh = grid.groupby(["route_n", "daytype", "hour"], as_index=False).agg(**agg)
    rh["rh_idx"] = rh.pax_sum / (rh.daytype.map(n_days) * rh.n_sched)
    gl = grid.groupby(["daytype", "band"], as_index=False).agg(pax_sum=("pax_sum", "sum"), n_sched=("n_sched", "sum"))
    gl["g_idx"] = gl.pax_sum / (gl.daytype.map(n_days) * gl.n_sched)

    # --- 1) HOURLY crowd table (one day type at a time)
    ct = None
    if hourly_table:
        ct = pd.concat([_hourly(grid[grid.daytype == d], rh[rh.daytype == d], rb[rb.daytype == d], gl[gl.daytype == d], k, attrs, patterns) for d in DAYTYPES], ignore_index=True)
        ct["crowd_pct"] = to_percentile(ct.est_idx, ct.est_idx)                  # rank among ALL stretch-hours (weekday + weekend together)

    # --- 2) time-band table (planner)
    seg = grid.groupby(["route_n", "daytype", "band", "pos"], as_index=False).agg(**agg)
    del grid
    seg["raw_idx"] = seg.pax_sum / (seg.daytype.map(n_days) * seg.n_sched)
    seg = seg.merge(rb[["route_n", "daytype", "band", "route_idx"]], on=["route_n", "daytype", "band"], how="left").merge(gl[["daytype", "band", "g_idx"]], on=["daytype", "band"], how="left")
    prior = seg.route_idx.fillna(seg.g_idx)
    seg["est_idx"] = (seg.n_tickets * seg.raw_idx + k * prior) / (seg.n_tickets + k)
    seg["crowd_pct"] = to_percentile(seg.est_idx, seg.est_idx)
    seg["level"] = level_of_pct(seg.crowd_pct)                    # RELATIVE level: low / medium / high  (Quiet / Moderate / Busy)
    seg["confidence"] = confidence_of(seg.n_tickets)
    thin = seg.n_sched < config.MIN_SCHEDULED_TRIPS               # very few buses scheduled in this band: the denominator is shaky
    seg["sched_thin"] = thin
    seg["confidence"] = np.where(thin & (seg.confidence == "high"), "medium", np.where(thin & (seg.confidence == "medium"), "low", seg.confidence))
    seg["source"] = np.where(seg.n_tickets >= config.CONF_MED, "segment_data", "shrunk_to_route_level")
    seg["dir"] = 0
    seg["is_ac"] = seg.route_n.map(attrs).fillna(0).astype(int)
    seg = _calibrate(seg, "est_idx", seg.is_ac)                   # CALIBRATED tier: seats_available / standing_room / crowded
    names = patterns[["route_n", "idx", "stop_name"]]
    seg = (seg.merge(names.rename(columns={"idx": "pos", "stop_name": "from_stop"}), on=["route_n", "pos"], how="left")
              .merge(names.assign(pos=names.idx - 1).drop(columns="idx").rename(columns={"stop_name": "to_stop"}), on=["route_n", "pos"], how="left"))
    seg = seg.drop(columns=["route_idx", "g_idx"])

    # --- 3) route-level table
    rl = rb.merge(gl[["daytype", "band", "g_idx"]], on=["daytype", "band"])
    rl["crowd_pct"] = to_percentile(rl.route_idx, seg.est_idx)       # same yardstick as the stretches
    rl["level"] = level_of_pct(rl.crowd_pct)
    rl["confidence"] = confidence_of(rl.n_tickets)
    rl["dir"] = 0
    rl["is_ac"] = rl.route_n.map(attrs).fillna(0).astype(int)
    rl = _calibrate(rl, "route_idx", rl.is_ac).drop(columns="g_idx")
    return dict(crowd_table=ct, hourly_cells=hourly, segments=seg, route_level=rl, global_level=gl, lost_share=float(lost_share))


def make_route_attrs(tix):
    """One row per route: a typical raw name, AC or not (most common value), number of tickets."""
    g = tix.groupby("route_n")
    return pd.DataFrame({"route": g.route_raw.agg(lambda s: s.astype(str).mode().iat[0]),
                         "is_ac": g.is_ac.agg(lambda s: int(round(s.mean()))), "n_tickets": g.size()}).reset_index()
