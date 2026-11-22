"""Step 5 (real-data version): crowd intensity WITHOUT needing vehicle numbers or inferred trips.

About half of the real tickets have no vehicle_number, so we cannot rebuild trips. Instead we use FLOW:
  riders on a stretch (ticketed passengers whose ride covers that stretch, summed over the days in the cell)
  ------------------------------------------------------------------------------------------------------
  number of scheduled trips in that time band (from GTFS) x number of days
= average ticketed passengers on board per scheduled trip, on that stretch. (Assumes every scheduled trip runs.)"""
import numpy as np, pandas as pd
from crowd.text import config

BANDS = list(config.BANDS)
HOUR_TO_BAND = np.array([next(b for b, (lo, hi) in config.BANDS.items() if lo <= h < hi) for h in range(24)])
BAND_CODE = {b: i for i, b in enumerate(BANDS)}

def day_table(tix: pd.DataFrame, exclude_dates=()):
    """Which dates count, and how many of each day type (weekday / weekend)."""
    d = tix[["date", "dow"]].drop_duplicates()
    d = d[~d.date.isin(set(exclude_dates))]
    d["daytype"] = np.where(d.dow < 6, "weekday", "weekend")
    return d, d.groupby("daytype").date.nunique().to_dict()

def scheduled_trips_per_day(hourly: pd.DataFrame) -> pd.DataFrame:
    h = hourly.copy(); h["band"] = HOUR_TO_BAND[h.hour.to_numpy()]
    return h.groupby(["route_n", "dir", "band"]).n_trips.sum().rename("trips_per_day").reset_index()

def compute_flow_cells(tix, hourly, pat, dates=None, exclude_dates=()):
    """One row per route x direction x daytype x band x stretch with ticketed load per scheduled trip."""
    t = tix if dates is None else tix[tix.date.isin(set(dates))]
    dtab, n_days = day_table(t, exclude_dates)
    t = t[t.date.isin(set(dtab.date))]
    daytype = np.where(t.dow.to_numpy() < 6, 0, 1)
    key = daytype * len(BANDS) + pd.Series(HOUR_TO_BAND[t.hour.to_numpy()]).map(BAND_CODE).to_numpy()
    t = t.assign(_key=key)
    n_stops = pat.groupby(["route_n", "dir"]).idx.max().add(1).to_dict()
    trips = scheduled_trips_per_day(hourly).set_index(["route_n", "dir", "band"]).trips_per_day.to_dict()
    pieces = []
    for (rn, d), g in t.groupby(["route_n", "dir"]):
        n = n_stops.get((rn, d))
        if n is None or n < 2: continue
        k = g._key.to_numpy(); b = g.b.to_numpy(); a = g.a.to_numpy(); px = g.pax.to_numpy()
        R = np.zeros((2 * len(BANDS), n + 1)); C = np.zeros_like(R)
        np.add.at(R, (k, b), px); np.add.at(R, (k, a), -px)          # +pax where they board, -pax where they alight
        np.add.at(C, (k, b), 1); np.add.at(C, (k, a), -1)            # same idea, counting tickets instead of passengers
        riders = np.cumsum(R, axis=1)[:, : n - 1]; cnt = np.cumsum(C, axis=1)[:, : n - 1]   # running sums along the route
        used = np.unique(k)
        for kk in used:
            dt, bd = ("weekday", "weekend")[kk // len(BANDS)], BANDS[kk % len(BANDS)]
            tpd = trips.get((rn, d, bd), 0); nd = n_days.get(dt, 0)
            if tpd <= 0 or nd <= 0: continue
            pieces.append(pd.DataFrame({"route_n": rn, "dir": d, "daytype": dt, "band": bd, "pos": np.arange(n - 1),
                                        "riders": riders[kk], "n_tickets": cnt[kk].astype(int), "n_days": nd, "trips_per_day": tpd}))
    c = pd.concat(pieces, ignore_index=True)
    c["tix_load"] = c.riders / (c.n_days * c.trips_per_day)          # ticketed passengers on board per scheduled trip
    c["n_stops"] = pd.MultiIndex.from_frame(c[["route_n", "dir"]]).map(n_stops).astype(int)
    return c
