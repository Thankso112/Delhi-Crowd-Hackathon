"""Make a SMALL, upload-friendly sample that keeps whole vehicles (so trips stay intact) and only the matching GTFS routes.
Usage:  python scripts/make_sample.py [tickets_path] [gtfs_folder] [n_vehicles]
Output: data/sample_bundle.zip  (tickets_sample.csv + gtfs_sample/*.txt)"""
import sys, zipfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pandas as pd
import config
from crowd.text import norm_route

tpath = Path(sys.argv[1]) if len(sys.argv) > 1 else config.TICKETS_CSV
gdir = Path(sys.argv[2]) if len(sys.argv) > 2 else config.GTFS_DIR
nveh = int(sys.argv[3]) if len(sys.argv) > 3 else 150
t = pd.read_csv(tpath, dtype=str)
vcol, rcol = config.COL["vehicle"], config.COL["route"]
keep = pd.Series(t[vcol].dropna().unique()).sample(min(nveh, t[vcol].nunique()), random_state=0)
s = t[t[vcol].isin(keep)]
print(f"tickets: {len(s):,} rows from {len(keep)} vehicles, {s[rcol].nunique()} routes")
rset = set(s[rcol].map(norm_route))
routes = pd.read_csv(gdir / "routes.txt", dtype=str); routes = routes[routes.route_short_name.map(norm_route).isin(rset)]
trips = pd.read_csv(gdir / "trips.txt", dtype=str); trips = trips[trips.route_id.isin(routes.route_id)]
parts = [c[c.trip_id.isin(trips.trip_id)] for c in pd.read_csv(gdir / "stop_times.txt", dtype=str, chunksize=500000)]
st = pd.concat(parts)
stops = pd.read_csv(gdir / "stops.txt", dtype=str); stops = stops[stops.stop_id.isin(st.stop_id)]
out = config.ROOT / "data" / "sample_bundle.zip"
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
    z.writestr("tickets_sample.csv", s.to_csv(index=False))
    for name, df in [("routes", routes), ("trips", trips), ("stop_times", st), ("stops", stops)]:
        z.writestr(f"gtfs_sample/{name}.txt", df.to_csv(index=False))
    for extra in ("calendar.txt", "calendar_dates.txt", "frequencies.txt"):
        if (gdir / extra).exists(): z.write(gdir / extra, f"gtfs_sample/{extra}")
print(f"wrote {out} ({out.stat().st_size / 1e6:.1f} MB). Upload this file.")
