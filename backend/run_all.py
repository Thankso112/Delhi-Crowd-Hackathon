"""
One command to rebuild EVERYTHING from the raw files.      python run_all.py

  python run_all.py            full run: notebooks 01-07 + temporal ML (about 25-35 minutes)
  python run_all.py --quick    core only: notebooks 01-04 + temporal ML (the crowd table + validation; about 12-15 minutes)
  python run_all.py --from 3   start at notebook 3 (if 1-2 already ran)
  python run_all.py --check    only check that the input files are in place

Needs:  data/raw/tickets.csv   and   data/raw/gtfs/{stops,routes,trips,stop_times}.txt   (see README.md)
Works on Windows / macOS / Linux. Results go to outputs/ and to the local database (SQLite file unless USE_MYSQL=1).
"""
import argparse, subprocess, sys, time
from pathlib import Path
import config

NOTEBOOKS = ["01_load_and_explore", "02_gtfs_and_stop_matching", "03_crowd_index", "04_validation",
             "05_ml_regression", "06_ml_classification", "07_clustering_pca"]


def check_inputs():
    need = [config.TICKETS_CSV] + [config.GTFS_DIR / f"{n}.txt" for n in ("stops", "routes", "trips", "stop_times")]
    missing = [str(p) for p in need if not p.exists()]
    print(f"database: {'MySQL ' + config.DB_NAME if config.USE_MYSQL else 'SQLite file ' + str(config.SQLITE_FILE)}")
    if missing:
        sys.exit("Missing input files:\n  " + "\n  ".join(missing) + "\nSee README.md, section 'Get the data'.")
    print("Input files found.")


def run_notebook(name):
    """Execute a notebook top to bottom and save its outputs inside it (what 'Run All' does in Jupyter)."""
    t = time.time(); print(f"\n=== {name} ...", flush=True)
    cmd = [sys.executable, "-m", "jupyter", "nbconvert", "--to", "notebook", "--execute", "--inplace",
           "--ExecutePreprocessor.timeout=7200", str(Path("notebooks") / f"{name}.ipynb")]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout[-1500:], r.stderr[-2500:]); sys.exit(f"FAILED in {name}. Open the notebook in Jupyter to see the error cell.")
    print(f"    done in {time.time() - t:.0f}s")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--quick", action="store_true"); ap.add_argument("--check", action="store_true")
    ap.add_argument("--from", dest="start", type=int, default=1); ap.add_argument("--skip-ml", action="store_true")
    a = ap.parse_args(); check_inputs()
    if a.check: sys.exit(0)
    t0 = time.time()
    core, extra = NOTEBOOKS[:4], NOTEBOOKS[4:]
    for i, n in enumerate(core, 1):
        if i >= a.start: run_notebook(n)
    if not a.skip_ml:
        print("\n=== scripts/07_ml_models.py (temporal split + fallback) ...", flush=True)
        r = subprocess.run([sys.executable, "scripts/07_ml_models.py"])
        if r.returncode != 0: sys.exit("FAILED in scripts/07_ml_models.py")
    if not a.quick:
        for n in extra: run_notebook(n)
    print(f"\nAll done in {(time.time() - t0) / 60:.1f} min.  Start the API:  uvicorn planner.app:app --port 8000")
