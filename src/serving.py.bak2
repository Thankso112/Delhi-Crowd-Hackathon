"""
Serving layer: loads the finished crowd model once and answers lookups FAST (no pandas work inside a request).

What is loaded
  * route patterns (ordered stops of each route-direction), bus frequency, AC flags   <- notebooks 02, 03
  * the HOURLY crowd table (route, stretch, hour, day type) with calibrated load       <- notebook 03 (+ ML fallback)
Everything is also turned into flat numpy arrays, so "what is the crowd on stretches i..j of route R at hour H?"
is one array lookup.
"""
import json, math, re
from pathlib import Path
import numpy as np
import pandas as pd
from rapidfuzz import process, fuzz
import config
from src import db
from src.common import norm_name, TIER_ORDER, confidence_of

CONF_CODES = ["low", "medium", "high"]
SRC_CODES = ["observed_tickets", "ml_fallback", "route_average"]
TIER_RANK = {t: i for i, t in enumerate(TIER_ORDER)}


def _artifact(name):
    """Prefer a Parquet file in outputs/artifacts (zero-setup), else read the table from the database."""
    p = config.OUT / "artifacts" / f"{name}.parquet"
    if p.exists():
        return pd.read_parquet(p)
    try:
        return db.read_table(name, db.get_engine())
    except Exception as e:
        raise RuntimeError(f"Crowd model files not found ({name}). Run `python run_all.py` first (see README.md). Original error: {e}") from e


class CrowdStore:
    def __init__(self):
        self.pat = _artifact("route_patterns")
        self.hourly = _artifact("route_hourly")
        self.attrs = _artifact("route_attrs").set_index("route_n")
        self._load_route_meta()
        self._load_crowd()
        self._build_stop_index()
        self.metrics = self._read_json("metrics.json")
        self.ml = self._read_json("ml_metrics.json")

    # ------------------------------------------------------------------ loading
    @staticmethod
    def _read_json(name):
        p = config.OUT / name
        return json.loads(p.read_text()) if p.exists() else None

    def _load_route_meta(self):
        """route_id, short name, agency and the official route description (from GTFS routes.txt)."""
        r = self.pat.drop_duplicates("route_n")[["route_n", "route", "route_id"]].reset_index(drop=True)
        f = config.GTFS_DIR / "routes.txt"
        meta = config.OUT / "artifacts" / "route_meta.parquet"                  # shipped with the outputs, so no raw GTFS is needed
        if meta.exists() or f.exists():
            g = pd.read_parquet(meta) if meta.exists() else pd.read_csv(f, dtype=str, keep_default_na=False)
            r = r.merge(g[["route_id", "agency_id", "route_desc"]], on="route_id", how="left")
        else:
            r["agency_id"], r["route_desc"] = "", ""
        r["direction_id"] = np.where(r.route.str.upper().str.endswith("DOWN"), 1, 0)
        r["base"] = r.route.str.upper().str.replace(r"(UP|DOWN)$", "", regex=True)
        self.routes = r.set_index("route_n")
        self._ends = {rn: "" for rn in self.routes.index}
        self.by_key = {}
        for rn, row in self.routes.iterrows():
            for k in {str(row.route_id), row.route.upper(), rn}:
                self.by_key.setdefault(k, []).append(rn)
            self.by_key.setdefault(row.base, []).append(rn)
        r["search"] = [norm_name(f"{a} {b} {c}") for a, b, c in zip(r.route, r.route_desc.fillna(""), r.agency_id.fillna(""))]
        self.routes = r.set_index("route_n")
        # ordered stop lists per route
        self.stops_of = {}
        for rn, g in self.pat.sort_values(["route_n", "idx"]).groupby("route_n"):
            self.stops_of[rn] = dict(stop_id=g.stop_id.tolist(), name=g.stop_name.tolist(), lat=g.lat.to_numpy(float),
                                     lon=g.lon.to_numpy(float), cum=g.cum_sec.to_numpy(float))
            self._ends[rn] = norm_name(g.stop_name.iloc[0] + " " + g.stop_name.iloc[-1])

    def _load_crowd(self):
        cols = ["route_n", "daytype", "hour", "pos", "n_sched", "ticket_count", "est_load", "est_load_raw", "capacity", "load_ratio",
                "crowd_level", "confidence", "fallback", "prediction_source"]
        served = config.OUT / "crowd_table_served.parquet"
        plain = config.OUT / "crowd_table.parquet"
        path = served if served.exists() else plain
        if path.exists():
            have = pd.read_parquet(path).columns
            ct = pd.read_parquet(path, columns=[c for c in cols if c in have])
        else:
            ct = db.read_table("crowd_table", db.get_engine())[[c for c in cols if c != "prediction_source"]]
        if "prediction_source" not in ct:
            ct["prediction_source"] = np.where(ct.ticket_count >= config.CONF_MED, "observed_tickets", "route_average")
        self.ct = ct
        self.ct_path = path.name if path.exists() else "database"
        # --- flat arrays: one slot per (route, daytype, hour, stretch)
        names = sorted(self.stops_of)
        self.rcode = {r: i for i, r in enumerate(names)}
        nst = np.array([len(self.stops_of[r]["stop_id"]) - 1 for r in names])
        sizes = np.repeat(nst, 48)
        self.off = np.concatenate([[0], np.cumsum(sizes)[:-1]]).astype(np.int64)
        total = int(sizes.sum())
        rc = ct.route_n.map(self.rcode).to_numpy(np.int64)
        gid = (rc * 2 + (ct.daytype == "weekend").to_numpy(np.int64)) * 24 + ct.hour.to_numpy(np.int64)
        flat = self.off[gid] + ct.pos.to_numpy(np.int64)
        self.A = {k: np.full(total, np.nan, np.float32) for k in ("load_ratio", "est_load", "n_sched")}
        self.A["load_ratio"][flat] = ct.load_ratio.to_numpy(np.float32)
        self.A["est_load"][flat] = ct.est_load.to_numpy(np.float32)
        self.A["n_sched"][flat] = ct.n_sched.to_numpy(np.float32)
        self.A["tix"] = np.zeros(total, np.int32); self.A["tix"][flat] = ct.ticket_count.to_numpy(np.int32)
        self.A["tier"] = np.full(total, -1, np.int8); self.A["tier"][flat] = ct.crowd_level.map(TIER_RANK).to_numpy(np.int8)
        self.A["src"] = np.full(total, 2, np.int8); self.A["src"][flat] = ct.prediction_source.map({s: i for i, s in enumerate(SRC_CODES)}).to_numpy(np.int8)
        self.trips_hr = self.hourly.groupby(["route_n", "hour"]).n_trips.sum().to_dict()

    def _build_stop_index(self):
        p = self.pat
        st = p.drop_duplicates("stop_id")[["stop_id", "stop_name", "lat", "lon"]].reset_index(drop=True)
        st["norm"] = st.stop_name.map(norm_name)
        rt = p.groupby("stop_id").route.agg(lambda s: sorted(set(s)))
        st["routes"] = st.stop_id.map(rt)
        st["n_routes"] = st.routes.map(len)
        self.stops = st
        self._norm = st.norm.tolist()
        self.stop_by_id = st.set_index("stop_id")

    # ------------------------------------------------------------------ crowd lookup (vectorised)
    def seg_arrays(self, route_n, daytype, hours, pos):
        """Crowd values for stretches `pos` (array) of a route, each at its own hour (array)."""
        gid = (self.rcode[route_n] * 2 + (daytype == "weekend")) * 24 + np.asarray(hours, np.int64)
        idx = self.off[gid] + np.asarray(pos, np.int64)
        return {k: v[idx] for k, v in self.A.items()}

    # ------------------------------------------------------------------ stops
    def search_stops(self, q, limit=15):
        """Autocomplete. Empty query -> empty list (never an error)."""
        limit = max(1, min(int(limit or 15), 100))
        qn = norm_name(q or "")
        if not qn:
            return dict(query=q or "", count=0, stops=[])
        score = np.zeros(len(self._norm))
        for i, n in enumerate(self._norm):
            if n == qn: score[i] = 100
            elif n.startswith(qn): score[i] = 92
            elif qn in n: score[i] = 84
        if (score > 0).sum() < limit:                       # not enough direct hits -> add fuzzy matches (typos, word order)
            for _, sc, i in process.extract(qn, self._norm, scorer=fuzz.token_set_ratio, limit=limit * 3):
                if sc >= 78 and score[i] == 0:
                    score[i] = min(80, sc)
        order = sorted(np.flatnonzero(score > 0), key=lambda i: (-score[i], -self.stops.n_routes[i]))[:limit]
        out = []
        for i in order:
            s = self.stops.iloc[i]
            out.append(dict(stop_id=s.stop_id, stop_name=s.stop_name, name=s.stop_name, lat=float(s.lat), lng=float(s.lon), lon=float(s.lon),
                            match_score=int(score[i]), routes_count=int(s.n_routes), sample_routes=s.routes[:6]))
        return dict(query=q, count=len(out), stops=out)

    def resolve_place(self, text):
        """Name, stop_id or 'lat,lon' -> the stop to plan from/to. Returns dict or None."""
        t = (text or "").strip()
        if not t:
            return None
        if t in self.stop_by_id.index:
            s = self.stop_by_id.loc[t]; return self._place(t, s, "stop_id", 100)
        m = re.match(r"^\s*(-?\d+\.?\d*)\s*,\s*(-?\d+\.?\d*)\s*$", t)
        if m:
            lat, lon = float(m.group(1)), float(m.group(2))
            d = np.hypot((self.stops.lat - lat) * 110540, (self.stops.lon - lon) * 111320 * math.cos(math.radians(lat)))
            i = int(np.argmin(d)); s = self.stops.iloc[i]
            return self._place(s.stop_id, s, "coordinates", max(0, 100 - int(d[i] / 20)))
        r = self.search_stops(t, 1)["stops"]
        if not r:
            return None
        s = r[0]
        method = "exact" if s["match_score"] >= 100 else "prefix" if s["match_score"] >= 92 else "substring" if s["match_score"] >= 84 else "fuzzy"
        return dict(stop_id=s["stop_id"], stop_name=s["stop_name"], lat=s["lat"], lng=s["lng"], match_method=method, match_score=s["match_score"])

    @staticmethod
    def _place(sid, s, method, score):
        return dict(stop_id=sid, stop_name=s["stop_name"], lat=float(s["lat"]), lng=float(s["lon"]), match_method=method, match_score=int(score))

    # ------------------------------------------------------------------ routes
    def list_routes(self, q="", limit=100, offset=0):
        qn = norm_name(q or ""); rows = []
        for rn, r in self.routes.iterrows():
            if qn and qn not in r.search and qn not in self._ends[rn]:
                continue
            s = self.stops_of[rn]
            origin, dest = s["name"][0], s["name"][-1]
            rows.append(dict(route_id=str(r.route_id), route_short_name=r.route, direction_id=int(r.direction_id), origin_stop=origin, destination_stop=dest,
                             num_stops=len(s["name"]), is_ac=bool(self.attrs.is_ac.get(rn, 0)), has_crowd_data=bool(self.attrs.n_tickets.get(rn, 0) > 0),
                             agency=r.agency_id, description=r.route_desc))
        limit, offset = max(1, min(int(limit), 500)), max(0, int(offset))
        page = rows[offset:offset + limit]
        return dict(total=len(rows), count=len(page), offset=offset, routes=page)

    def find_route(self, key, direction_id=None):
        c = self.by_key.get(str(key).strip().upper()) or self.by_key.get(str(key).strip())
        if not c:
            return None
        if direction_id is not None:
            m = [r for r in c if int(self.routes.direction_id[r]) == int(direction_id)]
            c = m or c
        return c[0]

    def route_crowd(self, rn, daytype="weekday", hour=18):
        s, r = self.stops_of[rn], self.routes.loc[rn]
        n = len(s["stop_id"]) - 1
        a = self.seg_arrays(rn, daytype, np.full(n, hour), np.arange(n))
        is_ac = bool(self.attrs.is_ac.get(rn, 0)); cap = config.CAPACITY["ac" if is_ac else "nonac"]
        segs = []
        for p in range(n):
            ok = not np.isnan(a["load_ratio"][p])
            segs.append(dict(sequence=p, from_stop_id=s["stop_id"][p], to_stop_id=s["stop_id"][p + 1], from_stop_name=s["name"][p], to_stop_name=s["name"][p + 1],
                             from_lat=float(s["lat"][p]), from_lng=float(s["lon"][p]), to_lat=float(s["lat"][p + 1]), to_lng=float(s["lon"][p + 1]),
                             estimated_load=round(float(a["est_load"][p]), 1) if ok else None, seated_capacity=cap["seats"], capacity=cap["crush"],
                             load_ratio=round(float(a["load_ratio"][p]), 3) if ok else None, crowd_level=TIER_ORDER[a["tier"][p]] if ok else "unknown",
                             scheduled_buses_hr=int(a["n_sched"][p]) if ok else 0, ticket_count=int(a["tix"][p]),
                             confidence=str(confidence_of(a["tix"][p])), prediction_source=SRC_CODES[a["src"][p]] if ok else "route_average",
                             data_source="calibrated_estimate" if ok else "no_schedule_at_this_hour",
                             from_name=s["name"][p], to_name=s["name"][p + 1], crowding=TIER_ORDER[a["tier"][p]] if ok else "unknown",
                             load_pct=min(100, round(float(a["load_ratio"][p]) * 100)) if ok else None,
                             estimated_passengers=round(float(a["est_load"][p])) if ok else None,
                             coordinates=[[float(s["lat"][p]), float(s["lon"][p])], [float(s["lat"][p + 1]), float(s["lon"][p + 1])]]))
        valid = [x for x in segs if x["load_ratio"] is not None]
        peak = max(valid, key=lambda x: x["load_ratio"]) if valid else None
        return dict(route_id=str(r.route_id), route_short_name=r.route, direction_id=int(r.direction_id), is_ac=is_ac, day_type=daytype, hour=int(hour),
                    direction=("Down" if str(r.route).upper().endswith("DOWN") else "Up" if str(r.route).upper().endswith("UP") else None),
                    busiest_stretch=(peak["from_stop_name"] + " \u2013 " + peak["to_stop_name"]) if peak else None,
                    avg_load_pct=min(100, round(sum(x["load_ratio"] for x in valid) / len(valid) * 100)) if valid else None,
                    crowding=peak["crowd_level"] if peak else "unknown", confidence=peak["confidence"] if peak else "low",
                    ticket_count=int(sum(x["ticket_count"] for x in segs)), prediction_source=peak["prediction_source"] if peak else "route_average",
                    description=r.route_desc, agency=r.agency_id,
                    summary=dict(max_crowd_level=peak["crowd_level"] if peak else "unknown", max_load_ratio=peak["load_ratio"] if peak else None,
                                 peak_estimated_load=peak["estimated_load"] if peak else None, seated_capacity=cap["seats"], capacity=cap["crush"],
                                 total_tickets_in_hour=int(sum(x["ticket_count"] for x in segs)), scheduled_buses_hr=int(self.trips_hr.get((rn, hour), 0))),
                    stops=[dict(sequence=i, stop_id=s["stop_id"][i], stop_name=s["name"][i], lat=float(s["lat"][i]), lng=float(s["lon"][i])) for i in range(n + 1)],
                    polyline=[[float(s["lat"][i]), float(s["lon"][i])] for i in range(n + 1)], segments=segs)

    # ------------------------------------------------------------------ operator view
    def hotspots(self, daytype="weekday", hour=9, limit=20, min_confidence="low"):
        ct = self.ct
        m = (ct.daytype == daytype)
        if hour is not None:
            m &= ct.hour == int(hour)
        m &= ct.ticket_count >= {"low": 0, "medium": config.CONF_MED, "high": config.CONF_HIGH}.get(min_confidence, 0)
        top = (ct[m].sort_values(["load_ratio", "ticket_count", "est_load_raw"], ascending=False)
                 .drop_duplicates("route_n").head(max(1, min(int(limit), 200))))          # one row per route-direction: its busiest stretch
        rows = []
        for k, c in enumerate(top.itertuples(), 1):
            s, r = self.stops_of[c.route_n], self.routes.loc[c.route_n]
            target = c.capacity * config.STANDING_FRACTION_OF_CRUSH
            extra = int(max(1, math.ceil((c.est_load / target - 1) * c.n_sched))) if c.est_load > target else 0
            cap = config.CAPACITY["ac" if self.attrs.is_ac.get(c.route_n, 0) else "nonac"]
            rows.append(dict(rank=k, route_id=str(r.route_id), route_short_name=r.route, direction_id=int(r.direction_id), hour=int(c.hour),
                             is_ac=bool(self.attrs.is_ac.get(c.route_n, 0)), from_stop_id=s["stop_id"][c.pos], from_stop_name=s["name"][c.pos],
                             to_stop_id=s["stop_id"][c.pos + 1], to_stop_name=s["name"][c.pos + 1], from_lat=float(s["lat"][c.pos]), from_lng=float(s["lon"][c.pos]),
                             to_lat=float(s["lat"][c.pos + 1]), to_lng=float(s["lon"][c.pos + 1]), estimated_load=round(float(c.est_load), 1),
                             seated_capacity=cap["seats"], capacity=int(c.capacity), load_ratio=round(float(c.load_ratio), 3), crowd_level=c.crowd_level,
                             scheduled_buses_hr=int(c.n_sched), suggested_extra_buses_hr=extra, ticket_count=int(c.ticket_count),
                             confidence=str(confidence_of(c.ticket_count)), prediction_source=c.prediction_source,
                             route_long_name=s["name"][0] + " to " + s["name"][-1], corridor=s["name"][0] + " \u2013 " + s["name"][-1],
                             busiest_stretch=s["name"][c.pos] + " \u2013 " + s["name"][c.pos + 1],
                             direction=("Down" if str(r.route).upper().endswith("DOWN") else "Up" if str(r.route).upper().endswith("UP") else None),
                             load_pct=min(100, round(float(c.load_ratio) * 100)), estimated_passengers=int(round(float(c.est_load))), crowding=c.crowd_level,
                             headway_minutes=round(60 / c.n_sched, 1) if c.n_sched > 0 else None))
        return dict(day_type=daytype, hour=hour if hour is not None else "all", min_confidence=min_confidence, count=len(rows), hotspots=rows,
                    hourly_network=self.hourly_network(daytype))

    def hourly_network(self, daytype="weekday"):
        """19 hourly points (05-23) for the operator chart: average load ratio over ALL cells of that hour, weighted by scheduled buses,
        and the number of stretch-hours labelled crowded. Hours with no data get cells=0 (not a real zero load)."""
        cache = self.__dict__.setdefault("_net_cache", {})
        if daytype not in cache:
            ct = self.ct
            c = ct.loc[(ct.daytype == daytype) & ct.load_ratio.notna(), ["hour", "load_ratio", "n_sched", "crowd_level"]]
            c = c.assign(rw=c.load_ratio * c.n_sched, over=(c.crowd_level == "crowded"))
            g = c.groupby("hour").agg(rw=("rw", "sum"), w=("n_sched", "sum"), over=("over", "sum"), cells=("load_ratio", "size"))
            out = []
            for h in range(5, 24):
                if h in g.index and g.at[h, "w"] > 0:
                    avg = float(g.at[h, "rw"] / g.at[h, "w"])
                    out.append(dict(hour=h, avg_load_ratio=round(avg, 3), avg_load_pct=min(100, round(avg * 100)), overloaded_count=int(g.at[h, "over"]),
                                    cells=int(g.at[h, "cells"]),
                                    crowding="seats" if avg <= 0.55 else ("standing" if avg <= config.STANDING_FRACTION_OF_CRUSH else "crowded")))
                else:
                    out.append(dict(hour=h, avg_load_ratio=None, avg_load_pct=0, overloaded_count=0, cells=0, crowding="seats"))
            cache[daytype] = out
        return cache[daytype]

    def network_profile(self, daytype="weekday"):
        """Average load ratio per hour (for the operator bar chart); only cells with medium/high confidence."""
        c = self.ct[(self.ct.daytype == daytype) & (self.ct.ticket_count >= config.CONF_MED)]
        g = c.groupby("hour").agg(avg_load_ratio=("load_ratio", "mean"), crowded_share=("crowd_level", lambda s: float((s == "crowded").mean())), cells=("load_ratio", "size"))
        return dict(day_type=daytype, hours=[dict(hour=int(h), avg_load_ratio=round(float(r.avg_load_ratio), 3), crowded_share=round(r.crowded_share, 3), cells=int(r.cells)) for h, r in g.iterrows()])

    # ------------------------------------------------------------------ meta
    def health(self):
        cal = dict(eticket_capture_rate=config.EKT_CAPTURE_RATE["base"], pass_holder_multiplier=config.PASS_MULTIPLIER["base"],
                   effective_scale_factor=round(config.SCALE["base"], 2), capacity_ac=config.CAPACITY["ac"], capacity_nonac=config.CAPACITY["nonac"])
        return dict(status="ok", mode=config.MODE, ready=True,
                    counts=dict(routes=int(self.routes.base.nunique()), route_directions=int(len(self.routes)), stops=int(len(self.stops)), crowd_cells=int(len(self.ct))),
                    map_center=dict(lat=config.CITY_CENTRE[0], lng=config.CITY_CENTRE[1]),
                    ml_fallback_model=(self.ml or {}).get("active_fallback_model", "none (ML module not run)"), crowd_table_file=self.ct_path, calibration=cal)

    def validation_summary(self):
        if getattr(self, "_vs", None) is None:
            self._vs = self._validation_summary()
        return self._vs

    def _validation_summary(self):
        m, ml = self.metrics or {}, self.ml or {}
        prof = self._read_json("01_data_profile.json") or {}
        match = self._read_json("02_match_report.json") or {}
        c3 = self._read_json("03_metrics.json") or {}
        ours = next((x for x in m.get("temporal_holdout", []) if x["predictor"].startswith("Our")), None)
        return dict(
            mode=config.MODE,
            dataset=dict(total_tickets=prof.get("tickets"), null_vehicle_share=prof.get("share_without_vehicle"), stop_match_rate_on_route_pct=match.get("matched_on_route_pct"),
                         tickets_usable_share=c3.get("share_usable"), holiday_dates_treated_as_weekend=prof.get("holiday_like_days"), n_crowd_cells=int(len(self.ct))),
            temporal_holdout_w1_w3_to_w4=dict(train_days="2026-10-01 to 2026-10-21", test_days="2026-10-22 to 2026-10-31",
                                              tier_agreement_pct=ours["tier_agreement_pct"] if ours else None, mae_people=ours["MAE_people"] if ours else None,
                                              spearman=ours["spearman"] if ours else None, baselines=[x for x in m.get("temporal_holdout", []) if not x["predictor"].startswith("Our")],
                                              note="evaluated on cells with 10+ tickets in the unseen period"),
            reliability=dict(split_half_odd_even_spearman=m.get("split_half_odd_even_all_cells_spearman_shrunk"), split_half_first_vs_second_half_spearman=m.get("split_half_first_vs_second_half_spearman_shrunk")),
            sensitivity=m.get("sensitivity"), organizer_curve_check=m.get("organizer_curve_check"),
            tier_distribution={k: round(float(v), 3) for k, v in self.ct.crowd_level.value_counts(normalize=True).items()},
            confidence_distribution={k: round(float(v), 3) for k, v in pd.Series(confidence_of(self.ct.ticket_count)).value_counts(normalize=True).items()},
            fallback_stats=ml.get("fallback_stats"), generated_from="real run outputs (outputs/*.json)" if m else "validation not run yet")

    def ml_insights(self):
        if self.ml:
            return self.ml
        return dict(split_method="not available: run scripts/07_ml_models.py", preprocessing_summary="", train_rows=0, test_rows=0, active_fallback_model="none",
                    fallback_stats=dict(total_segments=int(len(self.ct)), observed_segments=int((self.ct.prediction_source == "observed_tickets").sum()), ml_fallback_segments=0, ml_fallback_pct=0.0),
                    regression_models=[], classification_models=[], confusion_matrix=dict(labels=[], matrix=[]), feature_importance=[], concepts=[])
