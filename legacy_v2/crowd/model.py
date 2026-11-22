"""Turn flow cells into the crowd table: shrink thin cells, calibrate ticket counts to riders, map to seats / standing / crowded."""
import json
import numpy as np, pandas as pd
from crowd.text import config, level_of, confidence_of

def shrink(cells: pd.DataFrame, value="tix_load", n="n_tickets", k=None):
    """Cells with few tickets are pulled toward their route's average (then the city-wide average): est = (n*x + k*prior)/(n + k)."""
    k = config.SHRINK_K if k is None else k
    route_mean = cells.groupby(["route_n", "dir", "daytype", "band"])[value].transform("mean")
    glob = cells.groupby(["daytype", "band"])[value].transform("mean")
    prior = route_mean.fillna(glob)
    return (cells[n] * cells[value] + k * prior) / (cells[n] + k)

def calibrate_coverage(cells: pd.DataFrame) -> dict:
    """COVERAGE_FACTOR = riders per ticketed passenger. Anchor: the CALIBRATION_PERCENTILE-th percentile of well-observed weekday-peak
    stretch loads equals the standing limit (STANDING_FRACTION x crush, averaged over AC and non-AC). An ASSUMPTION; rankings do not depend on it."""
    crush = config.STANDING_FRACTION_OF_CRUSH * (config.CAPACITY["ac"]["crush"] + config.CAPACITY["nonac"]["crush"]) / 2
    if config.COVERAGE_FACTOR:
        return dict(coverage_factor=float(config.COVERAGE_FACTOR), method="set in config.py")
    ref = cells[(cells.daytype == "weekday") & cells.band.isin(["am_peak", "pm_peak"]) & (cells.n_tickets >= config.CONF_TICKETS_MED)]
    q = float(ref.est_load.quantile(config.CALIBRATION_PERCENTILE))
    return dict(coverage_factor=round(crush / q, 3), method=f"{config.CALIBRATION_PERCENTILE:.0%} percentile of weekday-peak stretch load ({q:.2f} ticketed pax per trip) set to the standing limit of {crush:.0f} passengers",
                anchor_percentile_load=round(q, 3), n_reference_cells=int(len(ref)))

def build_crowd_tables(flow: pd.DataFrame, route_attrs: pd.DataFrame):
    """Returns (crowd_segments, crowd_route_level, calibration dict)."""
    c = flow.merge(route_attrs[["route_n", "is_ac"]], on="route_n", how="left")
    c["est_load"] = shrink(c)
    cal = calibrate_coverage(c)
    raw = c.est_load * cal["coverage_factor"]                                    # estimated passengers on board
    crush = np.where(c.is_ac.fillna(0).astype(bool), config.CAPACITY["ac"]["crush"], config.CAPACITY["nonac"]["crush"])
    c["level"] = level_of(raw, c.is_ac.fillna(0))                                # level uses the uncapped value
    c["load_adj"] = np.minimum(raw, config.LOAD_CAP_FACTOR * crush)               # shown value is capped (GTFS may under-schedule a band)
    conf = pd.Series(confidence_of(c.n_tickets), index=c.index)
    thin = c.trips_per_day < config.MIN_SCHEDULED_TRIPS
    c["confidence"] = conf.where(~thin, conf.map({"high": "medium", "medium": "low", "low": "low"}))
    c["sched_thin"] = thin
    c["source"] = np.where(c.n_tickets >= config.CONF_TICKETS_MED, "segment_data", "shrunk_to_route_level")
    rl = c.groupby(["route_n", "dir", "daytype", "band"]).agg(est_load=("est_load", "mean"), n_tickets=("n_tickets", "median"), is_ac=("is_ac", "first")).reset_index()
    rraw = rl.est_load * cal["coverage_factor"]
    rl["level"] = level_of(rraw, rl.is_ac.fillna(0)); rl["load_adj"] = np.minimum(rraw, config.LOAD_CAP_FACTOR * np.where(rl.is_ac.fillna(0).astype(bool), config.CAPACITY["ac"]["crush"], config.CAPACITY["nonac"]["crush"]))
    rl["confidence"] = confidence_of(rl.n_tickets)
    return c, rl, cal

def readable_table(cells: pd.DataFrame, pat: pd.DataFrame, route_attrs: pd.DataFrame) -> pd.DataFrame:
    """The city-wide crowd table with stop names (outputs/crowd_table.csv)."""
    names = pat.set_index(["route_n", "dir", "idx"]).stop_name.to_dict()
    t = cells.merge(route_attrs[["route_n", "route"]], on="route_n").copy()
    t["from_stop"] = [names.get((r, d, i)) for r, d, i in zip(t.route_n, t.dir, t.pos)]
    t["to_stop"] = [names.get((r, d, i + 1)) for r, d, i in zip(t.route_n, t.dir, t.pos)]
    cols = ["route", "dir", "daytype", "band", "pos", "from_stop", "to_stop", "n_tickets", "trips_per_day", "tix_load", "est_load", "load_adj", "level", "confidence", "source"]
    return t[cols].round(2)
