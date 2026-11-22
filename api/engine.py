"""TransitEngine: the data layer behind the CrowdWise-compatible HTTP API (see docs/API.md).
Built on planner.engine.Planner (GTFS graph + crowd table); adds stop search with aliases, timed journey options,
per-stretch segments, departure shifts, route catalogue and operator hotspots, all in the contract's JSON shape."""
import json, math, gc, ctypes
from collections import Counter
from pathlib import Path
import numpy as np, pandas as pd
from rapidfuzz import fuzz, process
import config
from crowd.text import norm_name, level_of
from planner.engine import Planner, band_of, CONF_RANK

LV = {"seats": "seats_available", "standing": "standing_room", "crowded": "crowded", "unknown": "unknown"}
LV_RANK = {"seats_available": 0, "standing_room": 1, "crowded": 2, "unknown": -1}
RANK_CONF = {0: "low", 1: "medium", 2: "high"}
ALIASES = {"kashmiri": "kashmere", "cp": "connaught place", "ndls": "new delhi railway station", "rly": "railway", "stn": "station"}
BAND_HOURS = {b: hi - lo for b, (lo, hi) in config.BANDS.items()}

def hhmm(minutes: float) -> str:
    m = int(round(minutes)) % (24 * 60)
    return f"{m // 60:02d}:{m % 60:02d}"

def pct(ratio) -> int:
    """Load ratio (share of crush capacity) -> integer percent, clamped to 0..100 for display."""
    return int(max(0, min(100, round(float(ratio) * 100))))

class TransitEngine(Planner):
    def __init__(self):
        super().__init__()
        P = config.PROC
        cs = pd.read_parquet(P / "crowd_segments.parquet", columns=["route_n", "dir", "daytype", "band", "pos", "load_raw", "n_tickets", "level",
                                                                  "confidence", "is_ac", "trips_per_day", "prediction_source"])
        cs["prediction_source"] = cs["prediction_source"].astype("category")
        self.cx = {}                                                     # (route_n, dir, daytype, band) -> prediction_source[]
        for k, g in cs.groupby(["route_n", "dir", "daytype", "band"]):
            n = int(g.pos.max()) + 2
            src = np.array([None] * n, dtype=object); src[g.pos.to_numpy()] = g.prediction_source.to_numpy()
            self.cx[k] = src
        cs["load_raw"] = cs["load_raw"].astype("float32")
        for c in ("route_n", "daytype", "band", "level"):
            cs[c] = cs[c].astype("category")
        self.cells = cs
        self.by_rn = {(p["route_n"], p["dir"]): k for k, p in self.patterns.items()}
        self.by_id = {p["route_id"]: k for k, p in self.patterns.items()}
        self.ml = json.loads((P / "ml_insights.json").read_text())
        self.cal = json.loads((P / "calibration.json").read_text())
        self.mlMetrics = self.ml
        self._build_stop_index()
        self._build_route_index()
        self._build_hourly_network()
        gc.collect()
        try: ctypes.CDLL("libc.so.6").malloc_trim(0)                    # hand freed memory back to the OS (Linux only)
        except Exception: pass

    @staticmethod
    def _dir_label(route_name):
        r = str(route_name).upper()
        return "Down" if r.endswith("DOWN") else ("Up" if r.endswith("UP") else None)

    # ------------------------------------------------------------------ stops
    def _build_stop_index(self):
        s = self.stops.copy()
        s["num_routes"] = s.stop_id.map(lambda x: len({k[0] for k, _ in self.at_stop.get(x, [])}))
        s["name_n"] = s.stop_name.map(norm_name)
        s = s.sort_values("num_routes", ascending=False).drop_duplicates("name_n").reset_index(drop=True)   # one entry per name: the busiest stop
        self.sidx = s
        self.sidx_names = s.name_n.tolist()

    def _rec(self, r, method="", score=0.0):
        routes = sorted({k[0] for k, _ in self.at_stop.get(r.stop_id, [])})
        return dict(stop_id=str(r.stop_id), stop_name=r.stop_name, lat=float(r.lat), lng=float(r.lon), num_routes=int(r.num_routes), routes=routes[:30],
                    match_method=method, match_score=round(float(score), 1))

    def _norm_query(self, q):
        return " ".join(ALIASES.get(t, t) for t in norm_name(q).split())

    def _match(self, q, limit):
        qn = self._norm_query(q); out = {}
        if len(qn) >= 2:
            n = self.sidx.name_n
            for i in np.flatnonzero(n.str.startswith(qn).to_numpy()): out[i] = ("prefix", 100.0)
            for i in np.flatnonzero(n.str.contains(qn, regex=False).to_numpy()): out.setdefault(i, ("substring", 92.0))
            if len(out) < limit:
                for _, sc, i in process.extract(qn, self.sidx_names, scorer=fuzz.WRatio, limit=limit * 2, score_cutoff=72): out.setdefault(i, ("fuzzy", float(sc)))
        rows = sorted(out.items(), key=lambda kv: (-kv[1][1], -int(self.sidx.num_routes.iloc[kv[0]])))
        return rows[:limit]

    def searchStops(self, q="", limit=15):
        limit = max(1, min(int(limit), 100))
        if not (q or "").strip():                                           # empty query: the busiest hubs
            res = [self._rec(r, "hub", 100) for r in self.sidx.head(limit).itertuples()]
        else:
            res = [self._rec(self.sidx.iloc[i], m, sc) for i, (m, sc) in self._match(q, limit)]
        return dict(query=q, count=len(res), stops=res)

    def resolve_place(self, text):
        t = text.strip()
        try:                                                                # "lat,lng"
            a, b = [float(x) for x in t.split(",")]
            if 5 < a < 40 and 60 < b < 100:
                d, i = self.tree.query([b * self.kx, a * self.ky]); r = self.stops.iloc[int(i)]
                r = self.sidx[self.sidx.name_n == norm_name(r.stop_name)].iloc[0]
                return self._rec(r, "coordinates", max(0.0, 100 - float(d) / 20))
        except ValueError:
            pass
        m = self._match(t, 5)
        if not m: return None
        i, (meth, sc) = m[0]
        return self._rec(self.sidx.iloc[i], meth, sc)

    # --------------------------------------------------------------- segments
    def _crush(self, route_n):
        return config.CAPACITY["ac" if self.attrs.get(route_n, 0) else "nonac"]["crush"]

    def segments_for(self, key, i, j, daytype, band):
        p = self.patterns[key]; ck = (p["route_n"], p["dir"], daytype, band); crush = self._crush(p["route_n"]); out = []
        arr = self.crowd.get(ck)
        alt = None
        for pos in range(i, j):
            if arr is not None and pos < len(arr[0]) and np.isfinite(arr[0][pos]):
                load, ntr, lvl, conf = arr[0][pos], int(arr[1][pos]), arr[2][pos], arr[3][pos]; src = self.cx[ck][pos] or "observed_tickets"
            else:                                                           # no cell: average over the route's other bands, else unknown
                if alt is None:
                    alt = [v for (rn, d, dt, b), v in self.route_level.items() if rn == p["route_n"] and d == p["dir"] and dt == daytype]
                if alt:
                    load = float(np.mean([v["load_adj"] for v in alt])); ntr = 0; lvl = str(level_of(load, self.attrs.get(p["route_n"], 0))); conf = "low"; src = "route_average"
                else:
                    load, ntr, lvl, conf, src = float("nan"), 0, "unknown", "low", "route_average"
            ratio = None if not np.isfinite(load) else round(float(load) / crush, 3)
            est = None if ratio is None else round(ratio * crush)
            out.append(dict(sequence=pos, from_stop=p["names"][pos], to_stop=p["names"][pos + 1], from_stop_id=p["stop_ids"][pos], to_stop_id=p["stop_ids"][pos + 1],
                            from_name=p["names"][pos], to_name=p["names"][pos + 1],
                            load_ratio=ratio, load_pct=None if ratio is None else pct(ratio), est_passengers=est, estimated_passengers=est,
                            crowd_level=LV.get(lvl, "unknown"), crowding=str(lvl) if lvl in LV else "unknown", confidence=conf,
                            prediction_source=src, ticket_count=ntr,
                            coordinates=[[float(p["lat"][pos]), float(p["lon"][pos])], [float(p["lat"][pos + 1]), float(p["lon"][pos + 1])]]))
        return out

    def _summ(self, segs):
        known = [s for s in segs if s["load_ratio"] is not None]
        ranks = sorted(CONF_RANK[s["confidence"]] for s in segs) or [0]
        return dict(max_crowd_level=max((s["crowd_level"] for s in segs), key=lambda x: LV_RANK[x], default="unknown"),
                    max_load_ratio=round(max((s["load_ratio"] for s in known), default=0.0), 3), avg_load_ratio=round(float(np.mean([s["load_ratio"] for s in known])) if known else 0.0, 3),
                    ticket_count=int(np.median([s["ticket_count"] for s in segs])) if segs else 0, confidence=RANK_CONF[ranks[len(ranks) // 2]],
                    prediction_source=Counter(s["prediction_source"] for s in segs).most_common(1)[0][0] if segs else "route_average")

    def _avg_level(self, ratio, ac):
        cap = config.CAPACITY["ac" if ac else "nonac"]
        return LV[str(level_of(ratio * cap["crush"], int(ac)))]

    # ------------------------------------------------------------------- plan
    def planJourney(self, origin, destination, time="18:00", day_type="weekday", preference="balanced", limit=5):
        day_type = "weekend" if str(day_type).lower() == "weekend" else "weekday"
        pref = {"fast": "fastest", "comfort": "comfortable"}.get(str(preference).lower(), str(preference).lower())
        if pref not in ("fastest", "balanced", "comfortable"): pref = "balanced"
        try:
            hh, mm = [int(x) for x in time.split(":")[:2]]; assert 0 <= hh < 24 and 0 <= mm < 60
        except Exception:
            return dict(error=dict(code="BAD_TIME", message="time must look like HH:MM (24h), e.g. 18:30.", details=dict(time=time)))
        o, d = self.resolve_place(origin), self.resolve_place(destination)
        if o is None or d is None:
            bad = "origin" if o is None else "destination"
            return dict(error=dict(code="STOP_NOT_FOUND", message=f"Could not resolve the {bad}. Try /api/stops?q= to find a stop.", details=dict(origin=origin, destination=destination)))
        band = band_of(hh)
        raw = self.plan((o["lat"], o["lng"]), (d["lat"], d["lng"]), f"{hh:02d}:{mm:02d}", day_type, "fast", k=8)
        opts = []
        for r in raw.get("options", []):
            t = hh * 60 + mm + self._walk_min(r["walk_to_first_m"]); legs = []; allsegs = []
            for li, l in enumerate(r["legs"]):
                t += l["wait_min"]; dep = t; t += l["ride_min"]; arr = t
                if li < len(r["legs"]) - 1: t += self._walk_min(r["transfer_walk_m"])
                segs = self.segments_for(l["key"], l["i"], l["j"], day_type, band); allsegs += segs; sm = self._summ(segs); p = self.patterns[l["key"]]
                legs.append(dict(route_id=p["route_id"], route_short_name=l["route"], direction_id=int(l["dir"]), direction=self._dir_label(l["route"]),
                                 from_stop=dict(stop_id=p["stop_ids"][l["i"]], stop_name=l["from_stop"], lat=float(p["lat"][l["i"]]), lng=float(p["lon"][l["i"]])),
                                 to_stop=dict(stop_id=p["stop_ids"][l["j"]], stop_name=l["to_stop"], lat=float(p["lat"][l["j"]]), lng=float(p["lon"][l["j"]])),
                                 intermediate_stops=[dict(stop_id=p["stop_ids"][q], stop_name=p["names"][q], lat=float(p["lat"][q]), lng=float(p["lon"][q]))
                                                     for q in range(l["i"] + 1, l["j"])],
                                 departure_time=hhmm(dep), arrival_time=hhmm(arr), ride_min=round(l["ride_min"], 1), wait_min=round(l["wait_min"], 1), num_stops=int(l["n_stops"]),
                                 is_ac=bool(l["crowd"]["is_ac"]), polyline=l["path"], segments=segs, **sm))
            ride, wait = sum(x["ride_min"] for x in legs), sum(x["wait_min"] for x in legs)
            so = self._summ(allsegs); ac = legs[0]["is_ac"]
            comfort = r["comfort_score"]; score = {"fastest": r["total_min"], "comfortable": comfort, "balanced": (r["total_min"] + comfort) / 2}[pref]
            opts.append(dict(total_duration_min=int(r["total_min"]), in_vehicle_min=round(ride), wait_min=round(wait), walk_min=max(0, round(r["total_min"] - ride - wait)), transfers=int(r["transfers"]),
                             avg_crowd_level=self._avg_level(so["avg_load_ratio"], ac), legs=legs, _score=score, _ac=ac, **so))
        opts.sort(key=lambda x: x["_score"]); opts = opts[:max(1, int(limit))]
        for x in opts:                                                      # aliases some frontends read
            x["duration_minutes"] = x["total_duration_min"]
            x["overall_crowding"] = x["max_crowd_level"]
            x["peak_load_pct"] = pct(x["max_load_ratio"])
            x["avg_load_pct"] = pct(x["avg_load_ratio"])
        if opts:
            fastest = min(opts, key=lambda x: x["total_duration_min"]); calm = min(opts, key=lambda x: (x["max_load_ratio"], x["total_duration_min"]))
        for n, x in enumerate(opts, 1):
            x["rank"] = n; x["option_id"] = f"opt{n}-" + "+".join(l["route_short_name"] for l in x["legs"])
            x["tag"] = "fastest" if x is fastest else ("most_comfortable" if x is calm else ("direct" if x["transfers"] == 0 else "with_transfer"))
        shifts = self._departure_shifts(opts[0], hh, mm, day_type) if opts else []
        for x in opts: x.pop("_score"); x.pop("_ac")
        note = None
        if not opts: note = "No direct or one-transfer bus journey found between these stops. Try nearby stops."
        elif all(x["confidence"] == "low" for x in opts): note = "Crowd levels are typical for this time band (not live) and rest on few tickets for this journey; treat them as indicative."
        return dict(query=dict(origin=origin, destination=destination, time=f"{hh:02d}:{mm:02d}", hour=hh, day_type=day_type, preference=pref),
                    resolved_origin=o, resolved_destination=d, options=opts, departure_shifts=shifts, note=note)

    def _departure_shifts(self, best, hh, mm, day_type):
        """Same buses at other departure times: only shifts that change the time band can change the crowd level (bands are the model's resolution)."""
        base_band = band_of(hh); base = (LV_RANK[best["max_crowd_level"]], best["max_load_ratio"]); seen, out = set(), []
        legs = [(self._key_of(l), l) for l in best["legs"]]
        for sh in (15, 30, 45, 60, 90, 120, -15, -30, -45, -60, -90, -120):
            t = hh * 60 + mm + sh
            if not 0 <= t < 24 * 60: continue
            nb = band_of(t // 60)
            if nb == base_band or nb in seen: continue
            segs = []
            for key, l in legs:
                i = self.patterns[key]["stop_ids"].index(l["from_stop"]["stop_id"]); j = self.patterns[key]["stop_ids"].index(l["to_stop"]["stop_id"])
                segs += self.segments_for(key, i, j, day_type, nb)
            sm = self._summ(segs); new = (LV_RANK[sm["max_crowd_level"]], sm["max_load_ratio"]); seen.add(nb)
            improves = new[0] < base[0] or (new[0] == base[0] and new[1] < base[1] - 0.05)
            if improves:
                out.append(dict(shift_minutes=sh, departure_time=hhmm(t), improves_crowding=True, previous_crowd_level=best["max_crowd_level"], new_crowd_level=sm["max_crowd_level"],
                                load_ratio_delta=round(new[1] - base[1], 3),
                                summary=f"Leaving {abs(sh)} min {'later' if sh > 0 else 'earlier'} ({hhmm(t)}) moves you out of the {base_band.replace('_', ' ')} band: peak load drops from {base[1]:.2f} to {new[1]:.2f} of crush capacity."))
        return sorted(out, key=lambda x: abs(x["shift_minutes"]))[:4]

    def _key_of(self, leg):
        return self.by_id[leg["route_id"]]

    # ----------------------------------------------------------------- routes
    def _build_route_index(self):
        rows = []
        for (r, d), p in self.patterns.items():
            rows.append(dict(route_id=p["route_id"], route_short_name=r, direction_id=int(d), direction=self._dir_label(r), num_stops=len(p["stop_ids"]), is_ac=bool(self.attrs.get(p["route_n"], 0)),
                             origin_stop=p["names"][0], destination_stop=p["names"][-1], origin_name=p["names"][0], destination_name=p["names"][-1],
                             route_long_name=f"{p['names'][0]} to {p['names'][-1]}", corridor_label=f"{p['names'][0]} – {p['names'][-1]}"))
        self.route_df = pd.DataFrame(rows).sort_values(["route_short_name", "direction_id"]).reset_index(drop=True)
        hr = pd.read_parquet(config.PROC / "route_hourly.parquet")
        tp = hr.groupby(["route", "dir"]).n_trips.sum()
        pk = hr.groupby(["route", "dir"]).n_trips.max()                     # trips in the busiest hour
        keys = list(zip(self.route_df.route_short_name, self.route_df.direction_id))
        self.route_df["trips_per_day"] = [int(tp.get(k, 0)) for k in keys]
        self.route_df["headway_minutes"] = pd.Series([round(60 / pk.get(k), 1) if pk.get(k, 0) > 0 else None for k in keys], dtype=object, index=self.route_df.index)

    def listRoutes(self, q="", limit=100, offset=0):
        df = self.route_df
        if q:
            ql = q.lower(); df = df[df.route_short_name.str.lower().str.contains(ql, regex=False) | df.route_long_name.str.lower().str.contains(ql, regex=False)]
        limit = max(1, min(int(limit), 500)); offset = max(0, int(offset))
        return dict(total=int(len(df)), count=int(len(df.iloc[offset:offset + limit])), limit=limit, offset=offset, routes=df.iloc[offset:offset + limit].to_dict("records"))

    def getRouteCrowd(self, route_id, day_type="weekday", hour=18, direction_id=None):
        day_type = "weekend" if day_type == "weekend" else "weekday"; df = self.route_df
        m = df[df.route_id == str(route_id)]
        if m.empty: m = df[df.route_short_name.str.lower() == str(route_id).lower()]
        if direction_id is not None and not m.empty: m = m[m.direction_id == direction_id] if (m.direction_id == direction_id).any() else m
        if m.empty: return None
        r = m.iloc[0]; key = (r.route_short_name, int(r.direction_id)); p = self.patterns[key]; band = band_of(int(hour) % 24)
        segs = self.segments_for(key, 0, len(p["stop_ids"]) - 1, day_type, band)
        stops = [dict(stop_id=sid, stop_name=nm, lat=float(a), lng=float(b), sequence=i) for i, (sid, nm, a, b) in enumerate(zip(p["stop_ids"], p["names"], p["lat"], p["lon"]))]
        summ = self._summ(segs); known = [s for s in segs if s["load_ratio"] is not None]
        top = max(known, key=lambda s: s["load_ratio"], default=None)
        return dict(route_id=r.route_id, route_short_name=r.route_short_name, direction_id=int(r.direction_id), direction=self._dir_label(r.route_short_name),
                    is_ac=bool(r.is_ac), day_type=day_type, hour=int(hour), band=band, num_stops=len(stops), stops=stops, segments=segs,
                    polyline=[[s["lat"], s["lng"]] for s in stops], summary=summ,
                    busiest_stretch=f"{top['from_stop']} – {top['to_stop']}" if top else None,
                    avg_load_pct=pct(summ["avg_load_ratio"]), crowding=summ["max_crowd_level"], confidence=summ["confidence"],
                    ticket_count=summ["ticket_count"], prediction_source=summ["prediction_source"])

    # --------------------------------------------------------------- operator
    def _build_hourly_network(self):
        """Network-wide average load per (day type, time band), weighted by scheduled trips per day. The model works in bands, so hours in one band share a value."""
        c = self.cells
        crush = np.where(c.is_ac.fillna(0).astype(bool), config.CAPACITY["ac"]["crush"], config.CAPACITY["nonac"]["crush"])
        ratio = np.minimum(c.load_raw.to_numpy(dtype=float) / crush, config.LOAD_CAP_FACTOR)
        w = c.trips_per_day.to_numpy(dtype=float)
        d = pd.DataFrame({"daytype": c.daytype.values, "band": c.band.values, "rw": ratio * w, "w": w, "over": (c.level == "crowded").to_numpy()})
        g = d.groupby(["daytype", "band"], observed=True).agg(rw=("rw", "sum"), w=("w", "sum"), over=("over", "sum"))
        self.net_band = {(str(a), str(b)): (float(v.rw / v.w) if v.w else 0.0, int(v.over)) for (a, b), v in g.iterrows()}
        del d, ratio, w, crush

    def _hourly_network(self, day_type):
        out = []
        for h in range(5, 24):
            avg, over = self.net_band.get((day_type, band_of(h)), (0.0, 0))
            out.append(dict(hour=h, avg_load_pct=pct(avg), overloaded_count=over,
                            crowding="seats" if avg < 0.52 else ("standing" if avg < 0.75 else "crowded")))
        return out

    def getOperatorHotspots(self, day_type="weekday", hour=9, limit=20, min_confidence="low"):
        day_type = "weekend" if str(day_type) == "weekend" else "weekday"; hour = int(hour) % 24; band = band_of(hour)
        c = self.cells[(self.cells.daytype == day_type) & (self.cells.band == band)]
        c = c[c.confidence.map(CONF_RANK) >= CONF_RANK.get(min_confidence, 0)].copy()
        crush = np.where(c.is_ac.fillna(0).astype(bool), config.CAPACITY["ac"]["crush"], config.CAPACITY["nonac"]["crush"])
        c["rank_ratio"] = np.minimum(c.load_raw / crush, config.LOAD_CAP_FACTOR)   # rank on the capped value: uncapped values can be scaling artefacts
        c = c.sort_values(["rank_ratio", "n_tickets"], ascending=False).drop_duplicates(["route_n", "dir"]).head(max(1, min(int(limit), 200)))
        out = []
        for n, r in enumerate(c.itertuples(), 1):
            key = self.by_rn.get((r.route_n, int(r.dir)))
            if key is None: continue
            p = self.patterns[key]; pos = int(r.pos); ratio = float(r.rank_ratio); buses_hr = r.trips_per_day / BAND_HOURS[band]
            extra = int(min(20, max(0, math.ceil(buses_hr * (ratio / config.STANDING_FRACTION_OF_CRUSH - 1)))))
            est = round(ratio * self._crush(r.route_n)); fs, ts = p["names"][pos], p["names"][pos + 1]
            out.append(dict(rank=n, route_id=p["route_id"], route_short_name=p["route"], route_long_name=f"{p['names'][0]} to {p['names'][-1]}",
                            direction_id=int(r.dir), direction=self._dir_label(p["route"]), corridor=f"{p['names'][0]} – {p['names'][-1]}",
                            busiest_stretch=f"{fs} – {ts}", hour=hour, from_stop=fs, to_stop=ts,
                            origin_stop_id=p["stop_ids"][pos], origin_name=fs, destination_stop_id=p["stop_ids"][pos + 1], destination_name=ts, sequence=pos,
                            load_ratio=round(ratio, 3), load_pct=pct(ratio), est_passengers=est, estimated_passengers=est,
                            crowd_level=LV[str(r.level)], crowding=str(r.level), confidence=r.confidence, ticket_count=int(r.n_tickets),
                            prediction_source=r.prediction_source, scheduled_trips_per_hour=round(buses_hr, 2),
                            headway_minutes=round(60 / buses_hr, 1) if buses_hr > 0 else None, suggested_extra_buses_hr=extra))
        return dict(day_type=day_type, hour=hour, band=band, min_confidence=min_confidence, count=len(out), hotspots=out,
                    hourly_network=self._hourly_network(day_type))

    # ------------------------------------------------------------ meta/health
    def getHealth(self):
        cf = self.cal["coverage_factor"]
        return dict(status="ok", mode=config.MODE, ready=True, counts=dict(routes=int(self.route_df.route_short_name.nunique()), route_directions=int(len(self.patterns)), stops=int(len(self.stops)), crowd_cells=int(len(self.cells))),
                    map_center=dict(lat=float(self.stops.lat.mean()), lng=float(self.stops.lon.mean())), ml_fallback_model=self.ml["active_fallback_model"],
                    calibration=dict(eticket_capture_rate=round(1 / cf, 4), pass_holder_multiplier=1.0, effective_scale_factor=cf, method=self.cal.get("method"),
                                     capacity_ac=config.CAPACITY["ac"], capacity_nonac=config.CAPACITY["nonac"]))

    def getValidationSummary(self):
        O = config.OUT; M = json.loads((O / "metrics.json").read_text()); res = {}
        try: res["ticket_resolution"] = json.loads((O / "resolution_report.md").read_text().split("\n", 1)[1])
        except Exception: pass
        try: res["stop_matching_report"] = (O / "match_report.md").read_text()
        except Exception: pass
        sens = pd.read_csv(O / "sensitivity.csv").to_dict("records") if (O / "sensitivity.csv").exists() else []
        return dict(mode=config.MODE, calibration=self.cal, holdout=M.get("holdout"), stability_spearman_w2_vs_w3=M.get("stability_spearman_W2_vs_W3"),
                    level_accuracy=dict(shrinkage=M.get("level_accuracy_shrinkage"), gradient_boosting=M.get("level_accuracy_gradient_boosting")),
                    skill_vs_route_baseline=M.get("skill_shrinkage_vs_route_baseline"), sensitivity_to_coverage_factor=sens, share_low_confidence_cells=M.get("share_low_confidence_cells"),
                    fallback_stats=self.ml["fallback_stats"], **res,
                    limitations=["Typical crowding by time band and day type, not live.", "Ticket file is a thin sample (about 1 ticketed passenger per scheduled trip per day) and has no free-fare tickets, so counts are scaled by a stated calibration factor.",
                                 "No ground-truth crowding exists: metrics show consistency and predictability over time, not absolute accuracy of the seats/standing/crowded labels.",
                                 "Capacities are assumptions (config.py).", "One month of data: no seasons or festivals.", "GTFS has a single all-days calendar, so weekday and weekend schedules are identical."])
