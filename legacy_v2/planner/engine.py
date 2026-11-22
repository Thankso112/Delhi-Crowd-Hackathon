"""Static-GTFS bus journey planner (direct + one transfer) with a crowd level attached to every option."""
import sys, math, gc
import sys, math
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config
import numpy as np, pandas as pd
from scipy.spatial import cKDTree

LEVEL_RANK = {"seats": 0, "standing": 1, "crowded": 2}
CONF_RANK = {"low": 0, "medium": 1, "high": 2}
LABEL = {"seats": "Seats available", "standing": "Standing room", "crowded": "Crowded"}

def band_of(h):
    for b, (lo, hi) in config.BANDS.items():
        if lo <= h < hi: return b
    return "night"

class Planner:
    def __init__(self, proc=None):
        P = Path(proc or config.PROC)
        pat = pd.read_parquet(P / "patterns.parquet")
        self.pat = pat
        self.patterns = {}   # (route, dir) -> dict(stops=[...], cum=[...], route_n)
        for (r, d), g in pat.groupby(["route", "dir"]):
            g = g.sort_values("idx")
            self.patterns[(r, d)] = dict(route=r, dir=int(d), route_n=g.route_n.iloc[0], route_id=str(g.route_id.iloc[0]), stop_ids=g.stop_id.tolist(), names=g.stop_name.tolist(),
                                         lat=g.lat.to_numpy(), lon=g.lon.to_numpy(), cum=g.cum_sec.to_numpy(dtype=float))
        stops = pat.drop_duplicates("stop_id")[["stop_id", "stop_name", "lat", "lon"]].reset_index(drop=True)
        self.stops = stops
        self.lat0 = stops.lat.mean()
        self.kx = 111320 * math.cos(math.radians(self.lat0)); self.ky = 110540
        self.xy = np.c_[stops.lon * self.kx, stops.lat * self.ky]
        self.tree = cKDTree(self.xy)
        self.sid2i = {s: i for i, s in enumerate(stops.stop_id)}
        # stop -> [(pattern key, idx)]
        self.at_stop = {}
        for k, p in self.patterns.items():
            for i, s in enumerate(p["stop_ids"]):
                self.at_stop.setdefault(s, []).append((k, i))
        hr = pd.read_parquet(P / "route_hourly.parquet")
        self.trips_hr = hr.groupby(["route", "dir", "hour"]).n_trips.sum().to_dict()
        # crowd lookup: (route_n, dir, daytype, band) -> arrays by pos
        cs = pd.read_parquet(P / "crowd_segments.parquet", columns=["route_n", "dir", "daytype", "band", "pos", "load_adj", "n_tickets", "level", "confidence"])
        cs["level"] = cs["level"].astype("category"); cs["confidence"] = cs["confidence"].astype("category")
        self.crowd = {}
        for k, g in cs.groupby(["route_n", "dir", "daytype", "band"]):
            n = int(g.pos.max()) + 2
            load, ntr, lvl, conf = np.full(n, np.nan), np.zeros(n, int), np.array([None] * n, dtype=object), np.array([None] * n, dtype=object)
            load[g.pos.to_numpy()] = g.load_adj.to_numpy(); ntr[g.pos.to_numpy()] = g.n_tickets.to_numpy()
            lvl[g.pos.to_numpy()] = g.level.to_numpy(); conf[g.pos.to_numpy()] = g.confidence.to_numpy()
            self.crowd[k] = (load, ntr, lvl, conf)
        del cs; gc.collect()
        self.route_level = pd.read_parquet(P / "crowd_route_level.parquet").set_index(["route_n", "dir", "daytype", "band"])[["load_adj", "level", "confidence", "n_tickets"]].to_dict("index")
        self.attrs = pd.read_parquet(P / "route_attrs.parquet").set_index("route_n").is_ac.to_dict()

    # ---------- helpers ----------
    def _near(self, lat, lon, radius):
        d, i = self.tree.query([lon * self.kx, lat * self.ky], k=min(12, len(self.stops)))
        return [(int(j), float(x)) for x, j in zip(np.atleast_1d(d), np.atleast_1d(i)) if x <= radius]

    def _walk_min(self, m): return m * config.WALK_DETOUR / config.WALK_SPEED_MS / 60

    def _wait_min(self, route, d, hour):
        n = self.trips_hr.get((route, d, hour), 0) or self.trips_hr.get((route, d, (hour + 1) % 24), 0)
        return min(config.MAX_WAIT_MIN, 30.0 / n) if n else config.MAX_WAIT_MIN  # half the headway

    def crowd_leg(self, key, i, j, daytype, band):
        p = self.patterns[key]; ck = (p["route_n"], p["dir"], daytype, band)
        ac = self.attrs.get(p["route_n"], 0)
        if ck in self.crowd:
            load, ntr, lvl, conf = self.crowd[ck]
            sl = slice(i, j); ls = load[sl]
            if np.isfinite(ls).any():
                m = int(np.nanargmax(ls)); lv = [x for x in lvl[sl] if x]
                worst = max(lv, key=LEVEL_RANK.get); cf = [x for x in conf[sl] if x]
                bl = load[i] if np.isfinite(load[i]) else np.nan
                return dict(level=worst, peak_load=round(float(np.nanmax(ls))), board_load=None if np.isnan(bl) else round(float(bl)),
                            confidence=min(cf, key=CONF_RANK.get), source="segment data",
                            n_tickets=int(ntr[sl].min()), is_ac=bool(ac))
        rl = self.route_level.get(ck)
        if rl:
            return dict(level=rl["level"], peak_load=round(rl["load_adj"]), board_load=None, confidence="low", source="route-level average (thin data)", n_tickets=int(rl["n_tickets"]), is_ac=bool(ac))
        return dict(level="unknown", peak_load=None, board_load=None, confidence="low", source="no data", n_tickets=0, is_ac=bool(ac))

    def _leg(self, key, i, j, hour, daytype):
        p = self.patterns[key]; band = band_of(hour)
        ride = max(60.0, p["cum"][j] - p["cum"][i]) / 60
        c = self.crowd_leg(key, i, j, daytype, band)
        cap = config.CAPACITY['ac' if c['is_ac'] else 'nonac']; c['seats'], c['crush'] = cap['seats'], cap['crush']
        return dict(key=key, i=i, j=j, route=p["route"], dir=p["dir"], from_stop=p["names"][i], to_stop=p["names"][j], n_stops=j - i, ride_min=round(ride, 1),
                    wait_min=round(self._wait_min(p["route"], p["dir"], hour), 1), crowd=c,
                    path=[[float(a), float(b)] for a, b in zip(p["lat"][i:j + 1], p["lon"][i:j + 1])])

    # ---------- search ----------
    def plan(self, o, d, depart="18:00", daytype="weekday", mode="fast", k=3):
        hour = int(depart.split(":")[0]); rad = config.WALK_RADIUS_M
        O, D = self._near(*o, rad), self._near(*d, rad)
        if not O or not D: return dict(options=[], note="No bus stops within walking distance of origin or destination.")
        Omap = {self.stops.stop_id[j]: dist for j, dist in O}
        Dmap = {self.stops.stop_id[j]: dist for j, dist in D}
        cand = {}
        # ---- direct ----
        for sid, wd in Omap.items():
            for key, i in self.at_stop.get(sid, []):
                p = self.patterns[key]
                for j in range(i + 1, len(p["stop_ids"])):
                    if p["stop_ids"][j] in Dmap:
                        total = self._walk_min(wd) + self._wait_min(p["route"], p["dir"], hour) + (max(60.0, p["cum"][j] - p["cum"][i]) / 60) + self._walk_min(Dmap[p["stop_ids"][j]])
                        ck = (key,)
                        if ck not in cand or total < cand[ck][0]:
                            cand[ck] = (total, [(key, i, j)], wd, Dmap[p["stop_ids"][j]], 0.0)
                        break
        # ---- one transfer ----
        dest_at = {}
        for sid, dd in Dmap.items():
            for key, j in self.at_stop.get(sid, []):
                dest_at.setdefault(key, []).append((j, dd))
        for sid, wd in Omap.items():
            for k1, i in self.at_stop.get(sid, []):
                p1 = self.patterns[k1]
                for x in range(i + 1, len(p1["stop_ids"])):
                    xi = self.sid2i[p1["stop_ids"][x]]
                    for yi in self.tree.query_ball_point(self.xy[xi], config.TRANSFER_RADIUS_M):
                        ysid = self.stops.stop_id[yi]
                        for k2, y in self.at_stop.get(ysid, []):
                            if k2 == k1 or k2[0] == k1[0] or k2 not in dest_at: continue
                            for (j, dd) in dest_at[k2]:
                                if j > y:
                                    p2 = self.patterns[k2]
                                    twalk = float(np.hypot(*(self.xy[xi] - self.xy[yi])))
                                    total = (self._walk_min(wd) + self._wait_min(p1["route"], p1["dir"], hour) + max(60.0, p1["cum"][x] - p1["cum"][i]) / 60
                                             + self._walk_min(twalk) + self._wait_min(p2["route"], p2["dir"], hour) + max(60.0, p2["cum"][j] - p2["cum"][y]) / 60
                                             + self._walk_min(dd) + config.TRANSFER_PENALTY_MIN)
                                    ck = (k1, k2)
                                    if ck not in cand or total < cand[ck][0]:
                                        cand[ck] = (total, [(k1, i, x), (k2, y, j)], wd, dd, twalk)
                                    break
        options = []
        for ck, (total, legs, wd, dd, tw) in cand.items():
            L = [self._leg(k, i, j, hour, daytype) for k, i, j in legs]
            worst = max((l["crowd"]["level"] for l in L), key=lambda x: LEVEL_RANK.get(x, -1))
            conf = min((l["crowd"]["confidence"] for l in L), key=CONF_RANK.get)
            pen = sum(config.CROWD_PENALTY_MIN.get(l["crowd"]["level"], 0) * (0.5 if l["crowd"]["confidence"] == "low" else 1.0) for l in L)
            options.append(dict(total_min=round(total), walk_to_first_m=round(wd), walk_from_last_m=round(dd), transfer_walk_m=round(tw), transfers=len(L) - 1,
                                legs=L, crowd_level=worst, crowd_label=LABEL.get(worst, "No data"), confidence=conf,
                                comfort_score=total + pen, score=(total + pen) if mode == "comfort" else total))
        options.sort(key=lambda o: o["score"])
        out, seen = [], set()
        for op in options:                                  # diversify: avoid listing the same route set twice
            sig = tuple(l["route"] for l in op["legs"])
            if sig in seen: continue
            seen.add(sig); out.append(op)
            if len(out) == k: break
        return dict(options=out, depart=depart, daytype=daytype, band=band_of(hour), mode=mode,
                    origin_stops=[self.stops.stop_name[j] for j, _ in O[:3]], dest_stops=[self.stops.stop_name[j] for j, _ in D[:3]])

    def operator_view(self, daytype="weekday", band="pm_peak", top=15):
        rows = []
        for (rn, d, dt, b), (load, ntr, lvl, conf) in self.crowd.items():
            if dt != daytype or b != band: continue
            fin = np.isfinite(load)
            if fin.any():
                m = int(np.nanargmax(load)); rows.append((rn, d, float(load[m]), lvl[m], int(ntr[m]), m))
        pn = {v["route_n"]: v["route"] for v in self.patterns.values()}
        df = pd.DataFrame(rows, columns=["route_n", "dir", "peak_load", "level", "n_tickets", "pos"]).sort_values("peak_load", ascending=False).head(top)
        df["route"] = df.route_n.map(pn); df["peak_load"] = df.peak_load.round()
        return df.to_dict("records")
