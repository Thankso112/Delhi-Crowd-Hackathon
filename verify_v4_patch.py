"""Checks the patched V4 code WITHOUT starting a web server (your PC blocks the FastAPI dependency).
Run from the repo root:  python verify_v4_patch.py       Takes about 20-60 seconds. Read-only."""
import sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from src.serving import CrowdStore
from src.planner import Planner

t = time.time()
s = CrowdStore()
print("store loaded in", round(time.time() - t, 1), "s")

print("\n== hotspots (weekday, hour 8, limit 25) ==")
h = s.hotspots("weekday", 8, 25, "low")
rows = h["hotspots"]
print("rows:", len(rows), "| distinct route+direction:", len({(r["route_id"], r["direction_id"]) for r in rows}),
      "| distinct load ratios:", len({r["load_ratio"] for r in rows}))
print("ticket counts of the first 8 rows:", [r["ticket_count"] for r in rows[:8]])
need = ["route_long_name", "corridor", "busiest_stretch", "direction", "load_pct", "estimated_passengers", "crowding", "headway_minutes",
        "from_stop_id", "from_stop_name", "to_stop_id", "to_stop_name", "crowd_level", "ticket_count"]
print("missing row fields:", [k for k in need if rows and k not in rows[0]] or "none")
print("first row:", {k: rows[0][k] for k in ("route_short_name", "direction", "busiest_stretch", "load_ratio", "load_pct", "crowd_level", "ticket_count", "headway_minutes")})
hn = h["hourly_network"]
print("hourly_network entries:", len(hn), "(expected 19)")
for p in hn[:3] + hn[-2:]:
    print("  ", p)
low = [p for p in hn if p["cells"] == 0]
print("hours with no data:", [p["hour"] for p in low] or "none")

print("\n== route crowd (route 1, weekday, hour 9) ==")
rn = s.find_route("1")
rc = s.route_crowd(rn, "weekday", 9)
for k in ("direction", "busiest_stretch", "avg_load_pct", "crowding", "confidence", "ticket_count", "prediction_source"):
    print(" ", k, "=", rc.get(k))
segs = rc["segments"]
nulls = [x for x in segs if x["load_ratio"] is None]
print("segments:", len(segs), "| null load:", len(nulls))
if nulls:
    x = nulls[0]
    print("example null segment:", {k: x[k] for k in ("load_ratio", "load_pct", "crowd_level", "crowding", "estimated_passengers", "data_source")})
print("segment alias keys present:", all(k in segs[0] for k in ("from_name", "to_name", "load_pct", "estimated_passengers", "coordinates")))

print("\n== plan (Anand Vihar -> Connaught Place, 18:30) ==")
pl = Planner(s)
o, d = s.resolve_place("Anand Vihar"), s.resolve_place("Connaught Place")
r = pl.plan((o["lat"], o["lng"]), (d["lat"], d["lng"]), "18:30", "weekday", "balanced")
for e in r["options"]:
    print(" rank", e["rank"], "|", e["total_duration_min"], "min | max level:", e["max_crowd_level"], "| partial_data:", e["partial_data"],
          "| unknown ride share:", e["unknown_ride_share"], "| max load ratio:", e["max_load_ratio"])
print("departure shifts:", len(r["departure_shifts"]))
print("\nDone.")
