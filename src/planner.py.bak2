"""
Journey planner: direct buses and ONE transfer, built on the GTFS route patterns, with a crowd estimate on every leg.

How an option is built
  1. find stops within walking distance of origin and destination (KD-tree)
  2. find direct routes (origin stop -> later stop near destination) and one-transfer pairs (walk <= 250 m between routes)
  3. walk through the trip on the clock: walk -> wait for the bus -> ride -> (walk -> wait -> ride) -> walk
  4. for every stretch the bus rides, look up the crowd at the hour the bus passes it (CrowdStore, calibrated load)
  5. rank by the traveller's preference: fastest / balanced / comfortable
"""
import math
import numpy as np
from scipy.spatial import cKDTree
import config
from src.common import TIER_ORDER, confidence_of
from src.serving import SRC_CODES, CrowdStore

PENALTY = [config.CROWD_PENALTY_MIN["low"], config.CROWD_PENALTY_MIN["medium"], config.CROWD_PENALTY_MIN["high"]]   # minutes added per tier
CONF_RANK = {"low": 0, "medium": 1, "high": 2}


def hhmm(minutes):
    m = int(round(minutes)) % 1440
    return f"{m // 60:02d}:{m % 60:02d}"


class Planner:
    def __init__(self, store: CrowdStore):
        self.s = store
        self.pat = store.stops_of                               # route_n -> dict(stop_id, name, lat, lon, cum)
        st = store.stops
        self.sid = st.stop_id.tolist(); self.sname = st.stop_name.tolist()
        self.kx = 111320 * math.cos(math.radians(st.lat.mean())); self.ky = 110540
        self.xy = np.c_[st.lon.to_numpy() * self.kx, st.lat.to_numpy() * self.ky]
        self.tree = cKDTree(self.xy)
        self.sid2i = {s: i for i, s in enumerate(self.sid)}
        self.at_stop = {}                                       # stop_id -> [(route_n, index along the route)]
        for rn, p in self.pat.items():
            for i, s in enumerate(p["stop_id"]):
                self.at_stop.setdefault(s, []).append((rn, i))
        self._ball = {}

    # ---------------------------------------------------------------- small helpers
    def _near(self, lat, lon, radius):
        d, i = self.tree.query([lon * self.kx, lat * self.ky], k=min(12, len(self.sid)))
        return [(int(j), float(x)) for x, j in zip(np.atleast_1d(d), np.atleast_1d(i)) if x <= radius]

    def _near_stop(self, xi):                                   # stops within transfer-walking distance (cached)
        if xi not in self._ball:
            self._ball[xi] = self.tree.query_ball_point(self.xy[xi], config.TRANSFER_RADIUS_M)
        return self._ball[xi]

    @staticmethod
    def _walk_min(m): return m * config.WALK_DETOUR / config.WALK_SPEED_MS / 60

    def _wait_min(self, rn, hour):
        t = self.s.trips_hr
        n = t.get((rn, hour % 24), 0) or t.get((rn, (hour + 1) % 24), 0)
        return min(config.MAX_WAIT_MIN, 30.0 / n) if n else config.MAX_WAIT_MIN       # on average half the gap between buses

    def _ride_min(self, rn, i, j):
        c = self.pat[rn]["cum"]
        return max(1.0, (c[j] - c[i]) / 60)

    # ---------------------------------------------------------------- 1) find candidate journeys
    def candidates(self, o, d, hour):
        O, D = self._near(*o, config.WALK_RADIUS_M), self._near(*d, config.WALK_RADIUS_M)
        if not O or not D:
            return []
        Omap = {self.sid[j]: x for j, x in O}; Dmap = {self.sid[j]: x for j, x in D}
        cand = {}
        for sid, wd in Omap.items():                                                    # --- direct
            for rn, i in self.at_stop.get(sid, []):
                ids = self.pat[rn]["stop_id"]
                for j in range(i + 1, len(ids)):
                    if ids[j] in Dmap:
                        tot = self._walk_min(wd) + self._wait_min(rn, hour) + self._ride_min(rn, i, j) + self._walk_min(Dmap[ids[j]])
                        if (rn,) not in cand or tot < cand[(rn,)][0]:
                            cand[(rn,)] = (tot, [(rn, i, j)], wd, Dmap[ids[j]], 0.0)
                        break
        dest_at = {}
        for sid, dd in Dmap.items():
            for rn, j in self.at_stop.get(sid, []):
                dest_at.setdefault(rn, []).append((j, dd))
        for sid, wd in Omap.items():                                                    # --- one transfer
            for r1, i in self.at_stop.get(sid, []):
                p1 = self.pat[r1]["stop_id"]
                for x in range(i + 1, len(p1)):
                    xi = self.sid2i[p1[x]]
                    for yi in self._near_stop(xi):
                        for r2, y in self.at_stop.get(self.sid[yi], []):
                            if r2 == r1 or r2 not in dest_at:
                                continue
                            for j, dd in dest_at[r2]:
                                if j > y:
                                    tw = float(np.hypot(*(self.xy[xi] - self.xy[yi])))
                                    tot = (self._walk_min(wd) + self._wait_min(r1, hour) + self._ride_min(r1, i, x) + self._walk_min(tw)
                                           + self._wait_min(r2, hour) + self._ride_min(r2, y, j) + self._walk_min(dd) + config.TRANSFER_PENALTY_MIN)
                                    if (r1, r2) not in cand or tot < cand[(r1, r2)][0]:
                                        cand[(r1, r2)] = (tot, [(r1, i, x), (r2, y, j)], wd, dd, tw)
                                    break
        return sorted(cand.values(), key=lambda c: c[0])

    # ---------------------------------------------------------------- 2) put a candidate on the clock and attach the crowd
    def _leg_crowd(self, rn, i, j, daytype, board_min):
        cum = self.pat[rn]["cum"]; pos = np.arange(i, j)
        hours = ((board_min * 60 + cum[pos] - cum[i]) // 3600).astype(int) % 24             # hour at which the bus passes each stretch
        a = self.s.seg_arrays(rn, daytype, hours, pos)
        ok = ~np.isnan(a["load_ratio"])
        if not ok.any():
            return dict(max_crowd_level="unknown", max_load_ratio=None, avg_load_ratio=None, ticket_count=int(a["tix"].sum()), confidence="low", prediction_source="route_average", tier_idx=-1)
        lr = a["load_ratio"][ok]
        src = np.bincount(a["src"][ok], minlength=3)
        return dict(max_crowd_level=TIER_ORDER[int(a["tier"][ok].max())], max_load_ratio=round(float(lr.max()), 3), avg_load_ratio=round(float(lr.mean()), 3),
                    ticket_count=int(a["tix"].sum()), confidence=str(confidence_of(np.median(a["tix"]))), prediction_source=SRC_CODES[int(src.argmax())],
                    tier_idx=int(a["tier"][ok].max()))

    def evaluate(self, cand, depart_min, daytype):
        total, legs, wd, dd, tw = cand
        t = depart_min + self._walk_min(wd); out = []
        for n, (rn, i, j) in enumerate(legs):
            wait = self._wait_min(rn, int(t // 60)); board = t + wait; ride = self._ride_min(rn, i, j)
            c = self._leg_crowd(rn, i, j, daytype, board)
            p, meta = self.pat[rn], self.s.routes.loc[rn]
            out.append(dict(route_id=str(meta.route_id), route_short_name=meta.route, from_stop=dict(stop_id=p["stop_id"][i], stop_name=p["name"][i], lat=float(p["lat"][i]), lng=float(p["lon"][i])),
                            to_stop=dict(stop_id=p["stop_id"][j], stop_name=p["name"][j], lat=float(p["lat"][j]), lng=float(p["lon"][j])),
                            departure_time=hhmm(board), arrival_time=hhmm(board + ride), ride_min=round(ride, 1), wait_min=round(wait, 1), num_stops=j - i,
                            is_ac=bool(self.s.attrs.is_ac.get(rn, 0)), agency=meta.agency_id, **{k: v for k, v in c.items() if k != "tier_idx"},
                            path=[[float(p["lat"][k]), float(p["lon"][k])] for k in range(i, j + 1)], stop_sequence=p["name"][i:j + 1], _tier=c["tier_idx"]))
            t = board + ride + (self._walk_min(tw) if n == 0 and len(legs) > 1 else 0)
        end = t + self._walk_min(dd)
        tiers = [l["_tier"] for l in out]; ratios = [l["max_load_ratio"] for l in out if l["max_load_ratio"] is not None]
        avg = [l["avg_load_ratio"] for l in out if l["avg_load_ratio"] is not None]
        worst = max(tiers) if tiers else -1
        penalty = sum(PENALTY[max(0, l["_tier"])] * (0.5 if l["confidence"] == "low" else 1.0) for l in out)
        src_rank = {"route_average": 0, "ml_fallback": 1, "observed_tickets": 2}
        opt = dict(total_duration_min=round(end - depart_min), in_vehicle_min=round(sum(l["ride_min"] for l in out)), wait_min=round(sum(l["wait_min"] for l in out)),
                   walk_min=round(self._walk_min(wd) + self._walk_min(tw) + self._walk_min(dd)), transfers=len(out) - 1,
                   max_crowd_level=TIER_ORDER[worst] if worst >= 0 else "unknown", avg_crowd_level="unknown",
                   max_load_ratio=max(ratios) if ratios else None, avg_load_ratio=round(float(np.mean(avg)), 3) if avg else None,
                   confidence=min((l["confidence"] for l in out), key=CONF_RANK.get), prediction_source=min((l["prediction_source"] for l in out), key=src_rank.get),
                   ticket_count=int(sum(l["ticket_count"] for l in out)), legs=out, walk_to_first_m=round(wd), walk_from_last_m=round(dd), transfer_walk_m=round(tw),
                   _penalty=penalty, _rank_time=end - depart_min + config.TRANSFER_PENALTY_MIN * (len(out) - 1))
        unk = [l for l in out if l["max_load_ratio"] is None]
        ride_all = sum(l["ride_min"] for l in out) or 1.0
        share = sum(l["ride_min"] for l in unk) / ride_all
        opt.update(partial_data=bool(unk), unknown_leg_count=len(unk), unknown_ride_share=round(share, 2))
        if share >= 0.5:
            opt["max_crowd_level"] = "unknown"; opt["max_load_ratio"] = None; opt["avg_load_ratio"] = None; avg = []
        if avg:                                                                   # tier of the AVERAGE load (typical experience on the trip)
            cap = np.mean([1.0]); a = float(np.mean(avg))
            opt["avg_crowd_level"] = TIER_ORDER[0] if a <= 0.55 else TIER_ORDER[1] if a <= config.STANDING_FRACTION_OF_CRUSH else TIER_ORDER[2]
        return opt

    # ---------------------------------------------------------------- 3) the public entry point
    def plan(self, o, d, depart="18:00", daytype="weekday", preference="balanced", k=5):
        h, m = (int(x) for x in depart.split(":")[:2]); depart_min = h * 60 + m
        cands = self.candidates(o, d, h)
        if not cands:
            return dict(options=[], departure_shifts=[], note="No bus stops within walking distance of the origin or destination.")
        seen, opts = set(), []
        for c in cands[:40]:                                                      # evaluate the quickest candidates, one per route combination
            sig = tuple(rn for rn, _, _ in c[1])
            if sig in seen: continue
            seen.add(sig); opts.append((c, self.evaluate(c, depart_min, daytype)))
            if len(opts) >= 12: break
        score = {"fastest": lambda e: e["_rank_time"], "comfortable": lambda e: e["_rank_time"] + e["_penalty"],
                 "balanced": lambda e: e["_rank_time"] + 0.5 * e["_penalty"]}[preference if preference in ("fastest", "comfortable", "balanced") else "balanced"]
        opts.sort(key=lambda ce: score(ce[1]))
        opts = opts[:k]
        fastest = min(opts, key=lambda ce: ce[1]["_rank_time"])[1]
        comfy = min(opts, key=lambda ce: ce[1]["_rank_time"] + ce[1]["_penalty"])[1]
        final = []
        for n, (c, e) in enumerate(opts, 1):
            tag = {"fastest": "fastest", "comfortable": "most_comfortable", "balanced": "balanced"}[preference if preference in ("fastest", "comfortable", "balanced") else "balanced"] if n == 1 \
                else "fastest" if e is fastest else "most_comfortable" if e is comfy else "alternative"
            e.update(option_id=f"opt-{n}", rank=n, tag=tag); final.append(e)
        shifts = self._shifts(opts[0][0], opts[0][1], depart_min, daytype)
        for e in final:                                                           # remove internal fields
            e.pop("_penalty", None); e.pop("_rank_time", None)
            for l in e["legs"]: l.pop("_tier", None)
        return dict(options=final, departure_shifts=shifts, note=None)

    def _shifts(self, cand, base, depart_min, daytype):
        out = []
        if base["max_crowd_level"] == "unknown":
            return []
        base_t = TIER_ORDER.index(base["max_crowd_level"]) if base["max_crowd_level"] in TIER_ORDER else 0
        for sh in (15, 30):
            e = self.evaluate(cand, depart_min + sh, daytype)
            t = TIER_ORDER.index(e["max_crowd_level"]) if e["max_crowd_level"] in TIER_ORDER else 0
            b, n = base["max_load_ratio"] or 0.0, e["max_load_ratio"] or 0.0
            better = t < base_t or (t == base_t and b - n >= 0.05)
            summ = (f"Leaving {sh} min later ({hhmm(depart_min + sh)}) moves the worst stretch from '{base['max_crowd_level']}' to '{e['max_crowd_level']}'." if better
                    else f"Leaving {sh} min later does not noticeably reduce crowding.")
            out.append(dict(shift_minutes=sh, departure_time=hhmm(depart_min + sh), improves_crowding=bool(better), previous_crowd_level=base["max_crowd_level"],
                            new_crowd_level=e["max_crowd_level"], load_ratio_delta=round(n - b, 3), summary=summ))
        return out
