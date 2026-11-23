"""Applies the V4 API fixes (hourly_network, evidence-based hotspot ranking, contract aliases, partial-data flag).

Run from the repo root (the folder that contains src/ and planner/):
    python apply_v4_patch.py

All-or-nothing: every anchor text must be found exactly once, otherwise NOTHING is changed.
Backups are written next to each edited file as <name>.bak. Works with LF or CRLF line endings."""
import sys
from pathlib import Path

root = Path.cwd()
SERVING = root / "src" / "serving.py"
PLANNER = root / "src" / "planner.py"

EDITS = {
    SERVING: [
        # 1. route crowd: segment aliases (null load stays null, never 0)
        (r'''data_source="calibrated_estimate" if ok else "no_schedule_at_this_hour"))''',
         r'''data_source="calibrated_estimate" if ok else "no_schedule_at_this_hour",
                             from_name=s["name"][p], to_name=s["name"][p + 1], crowding=TIER_ORDER[a["tier"][p]] if ok else "unknown",
                             load_pct=min(100, round(float(a["load_ratio"][p]) * 100)) if ok else None,
                             estimated_passengers=round(float(a["est_load"][p])) if ok else None,
                             coordinates=[[float(s["lat"][p]), float(s["lon"][p])], [float(s["lat"][p + 1]), float(s["lon"][p + 1])]]))'''),
        # 2. route crowd: top-level aliases
        (r'''return dict(route_id=str(r.route_id), route_short_name=r.route, direction_id=int(r.direction_id), is_ac=is_ac, day_type=daytype, hour=int(hour),''',
         r'''return dict(route_id=str(r.route_id), route_short_name=r.route, direction_id=int(r.direction_id), is_ac=is_ac, day_type=daytype, hour=int(hour),
                    direction=("Down" if str(r.route).upper().endswith("DOWN") else "Up" if str(r.route).upper().endswith("UP") else None),
                    busiest_stretch=(peak["from_stop_name"] + " \u2013 " + peak["to_stop_name"]) if peak else None,
                    avg_load_pct=min(100, round(sum(x["load_ratio"] for x in valid) / len(valid) * 100)) if valid else None,
                    crowding=peak["crowd_level"] if peak else "unknown", confidence=peak["confidence"] if peak else "low",
                    ticket_count=int(sum(x["ticket_count"] for x in segs)), prediction_source=peak["prediction_source"] if peak else "route_average",'''),
        # 3. hotspots: among rows tied at the cap, rank by evidence (ticket count) before the raw scaled load
        (r'''top = (ct[m].sort_values(["load_ratio", "est_load_raw"], ascending=False)''',
         r'''top = (ct[m].sort_values(["load_ratio", "ticket_count", "est_load_raw"], ascending=False)'''),
        # 4. hotspots: contract aliases per row
        (r'''confidence=str(confidence_of(c.ticket_count)), prediction_source=c.prediction_source))''',
         r'''confidence=str(confidence_of(c.ticket_count)), prediction_source=c.prediction_source,
                             route_long_name=s["name"][0] + " to " + s["name"][-1], corridor=s["name"][0] + " \u2013 " + s["name"][-1],
                             busiest_stretch=s["name"][c.pos] + " \u2013 " + s["name"][c.pos + 1],
                             direction=("Down" if str(r.route).upper().endswith("DOWN") else "Up" if str(r.route).upper().endswith("UP") else None),
                             load_pct=min(100, round(float(c.load_ratio) * 100)), estimated_passengers=int(round(float(c.est_load))), crowding=c.crowd_level,
                             headway_minutes=round(60 / c.n_sched, 1) if c.n_sched > 0 else None))'''),
        # 5. hotspots: add hourly_network to the response
        (r'''return dict(day_type=daytype, hour=hour if hour is not None else "all", min_confidence=min_confidence, count=len(rows), hotspots=rows)''',
         r'''return dict(day_type=daytype, hour=hour if hour is not None else "all", min_confidence=min_confidence, count=len(rows), hotspots=rows,
                    hourly_network=self.hourly_network(daytype))'''),
        # 6. new method: hourly network profile (19 points, 05-23)
        (r'''def network_profile(self, daytype="weekday"):''',
         r'''def hourly_network(self, daytype="weekday"):
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

    def network_profile(self, daytype="weekday"):'''),
    ],
    PLANNER: [
        # 7. plan option: partial-data flag; if most of the ride has no estimate, do not summarise from the short known part
        (r'''_penalty=penalty, _rank_time=end - depart_min + config.TRANSFER_PENALTY_MIN * (len(out) - 1))''',
         r'''_penalty=penalty, _rank_time=end - depart_min + config.TRANSFER_PENALTY_MIN * (len(out) - 1))
        unk = [l for l in out if l["max_load_ratio"] is None]
        ride_all = sum(l["ride_min"] for l in out) or 1.0
        share = sum(l["ride_min"] for l in unk) / ride_all
        opt.update(partial_data=bool(unk), unknown_leg_count=len(unk), unknown_ride_share=round(share, 2))
        if share >= 0.5:
            opt["max_crowd_level"] = "unknown"; opt["max_load_ratio"] = None; opt["avg_load_ratio"] = None; avg = []'''),
        # 8. no departure-shift advice when the base level is unknown
        (r'''base_t = TIER_ORDER.index(base["max_crowd_level"]) if base["max_crowd_level"] in TIER_ORDER else 0''',
         r'''if base["max_crowd_level"] == "unknown":
            return []
        base_t = TIER_ORDER.index(base["max_crowd_level"]) if base["max_crowd_level"] in TIER_ORDER else 0'''),
    ],
}


def load(p):
    raw = p.read_bytes().decode("utf-8")
    return raw.replace("\r\n", "\n"), ("\r\n" in raw)


def main():
    work, errors = {}, []
    for path, edits in EDITS.items():
        if not path.exists():
            errors.append(f"missing file: {path}  (run this from the repo root)")
            continue
        text, crlf = load(path)
        if "hourly_network" in text or "partial_data" in text:
            errors.append(f"{path.name}: already patched, nothing to do")
            continue
        for i, (old, new) in enumerate(edits, 1):
            n = text.count(old)
            if n != 1:
                errors.append(f"{path.name}: anchor {i} found {n} times (expected 1): {old[:70]}...")
            else:
                text = text.replace(old, new)
        work[path] = (text, crlf)
    if errors:
        print("NOTHING WAS CHANGED. Problems:")
        for e in errors:
            print(" -", e)
        sys.exit(1)
    for path, (text, crlf) in work.items():
        original = path.read_bytes()
        Path(str(path) + ".bak").write_bytes(original)
        path.write_bytes((text.replace("\n", "\r\n") if crlf else text).encode("utf-8"))
        print("patched", path.relative_to(root), "(backup: " + path.name + ".bak)")
    print("Done. Now run: python verify_v4_patch.py")


main()
