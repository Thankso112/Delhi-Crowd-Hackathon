"""Describe your REAL data so it can be pasted into a chat. Safe: prints structure + small samples only.
Usage (Anaconda Prompt, project folder):
    python scripts/inspect_data.py                      # uses data/raw/tickets.csv (or .zip) and data/raw/gtfs/
    python scripts/inspect_data.py path\\to\\tickets.zip path\\to\\gtfs_folder
Writes outputs/data_inspection.txt  -> paste that file's contents."""
import sys, io, re
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pandas as pd
import config
from crowd.text import norm_name, norm_route

out = io.StringIO()
def p(*a):
    print(*a); print(*a, file=out)
pd.set_option("display.width", 200); pd.set_option("display.max_columns", 40); pd.set_option("display.max_colwidth", 40)

def find_tickets(arg):
    if arg: return Path(arg)
    for c in [config.TICKETS_CSV, *sorted(config.RAW.glob("*.zip")), *sorted(config.RAW.glob("*.csv"))]:
        if Path(c).exists(): return Path(c)
    sys.exit("Tickets file not found. Pass its path as the first argument.")

tpath = find_tickets(sys.argv[1] if len(sys.argv) > 1 else None)
gdir = Path(sys.argv[2]) if len(sys.argv) > 2 else config.GTFS_DIR
p("=" * 70, "\nTICKETS:", tpath, f"({tpath.stat().st_size / 1e6:.1f} MB)")
t = pd.read_csv(tpath, dtype=str, nrows=300000)           # first 300k rows are enough to learn the format
try:
    n = sum(len(c) for c in pd.read_csv(tpath, usecols=[0], chunksize=500000, dtype=str))
    p("total rows:", f"{n:,}")
except Exception as e:
    p("row count failed:", e)
p("\ncolumns:", list(t.columns)); p("\nfirst 8 rows:\n", t.head(8).to_string())
p("\nnull counts (sample):\n", t.isna().sum().to_string())
p("\nunique values (sample):\n", t.nunique().to_string())
for col in t.columns:
    if re.search(r"route|type|ac|count", col, re.I):
        p(f"\ntop values of {col}:\n", t[col].value_counts(dropna=False).head(15).to_string())
tscol = next((c for c in t.columns if re.search(r"creat|time|date|ts", c, re.I)), None)
if tscol:
    p(f"\ntimestamp column '{tscol}' examples:", t[tscol].dropna().sample(5, random_state=1).tolist())
    parsed = pd.to_datetime(t[tscol].str.slice(0, 19), errors="coerce")
    p("parse success (first 19 chars):", f"{parsed.notna().mean():.1%}", "| range:", parsed.min(), "to", parsed.max(), "| has offset suffix:", bool(t[tscol].str.contains(r"[+-]\d\d:?\d\d$|Z$", regex=True).any()))
for col in t.columns:
    if re.search(r"stop|name", col, re.I):
        p(f"\nsample values of {col}:", t[col].dropna().sample(8, random_state=2).tolist())
for col in t.columns:
    if re.search(r"amount|count|pax|fare", col, re.I):
        p(f"\nnumeric summary of {col}:\n", pd.to_numeric(t[col], errors="coerce").describe().to_string())

p("\n" + "=" * 70, "\nGTFS folder:", gdir)
if not gdir.exists():
    p("GTFS folder not found.")
else:
    p("files:", sorted(f.name for f in gdir.glob("*")))
    for f in ["stops.txt", "routes.txt", "trips.txt", "stop_times.txt", "calendar.txt", "calendar_dates.txt", "frequencies.txt", "shapes.txt"]:
        fp = gdir / f
        if not fp.exists():
            p(f"\n{f}: MISSING"); continue
        d = pd.read_csv(fp, dtype=str, nrows=5)
        p(f"\n{f} ({fp.stat().st_size / 1e6:.1f} MB) columns: {list(d.columns)}\n{d.head(3).to_string()}")
    try:
        routes = pd.read_csv(gdir / "routes.txt", dtype=str); stops = pd.read_csv(gdir / "stops.txt", dtype=str)
        rn = set(routes.route_short_name.map(norm_route)); tn = t.iloc[:, [list(t.columns).index(c) for c in t.columns if re.fullmatch(r"route", c, re.I)][0]].map(norm_route)
        p(f"\nROUTE MATCH: {tn.isin(rn).mean():.1%} of ticket rows have a route found in routes.txt (route_short_name)")
        p("ticket routes NOT in GTFS (top 15):", tn[~tn.isin(rn)].value_counts().head(15).to_dict())
        sn = set(stops.stop_name.map(norm_name))
        for col in [c for c in t.columns if re.search(r"start.*stop|end.*stop", c, re.I)]:
            p(f"STOP NAME exact match for {col}: {t[col].map(norm_name).isin(sn).mean():.1%} (before fuzzy matching)")
        p("direction_id present in trips.txt:", "direction_id" in pd.read_csv(gdir / "trips.txt", nrows=1).columns)
    except Exception as e:
        p("match preview failed:", repr(e))
(config.OUT / "data_inspection.txt").write_text(out.getvalue()); print("\nSaved to", config.OUT / "data_inspection.txt")
