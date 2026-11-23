"""
Rebuild outputs/crowd_table_served.parquet WITHOUT the ML fallback.

Why: the ML fallback overwrote 65% of cells (those with <10 tickets) and raised their median load
from ~3.6 to ~78 people, so 57% of all cells came out "crowded". compare_report.md shows the shrinkage
estimate beats every ML model, so sparse cells keep the shrinkage estimate.

Run from the repo root:   python fix_served_table.py
"""
import numpy as np
import pandas as pd
from pathlib import Path

OUT = Path("outputs")
SPARSE = 10                      # same threshold as scripts/07_ml_models.py (tickets behind an estimate)
KEEP = ["route_n", "daytype", "hour", "pos", "n_sched", "ticket_count", "est_load", "est_load_raw",
        "capacity", "load_ratio", "crowd_level", "confidence", "fallback"]

old = pd.read_parquet(OUT / "crowd_table_served.parquet", columns=["crowd_level"])
ct = pd.read_parquet(OUT / "crowd_table.parquet")
served = ct[KEEP].copy()
served["prediction_source"] = np.where(served.ticket_count >= SPARSE, "observed_tickets", "route_average")

# consistency checks
assert (served.load_ratio - served.est_load / served.capacity).abs().max() < 1e-4, "load_ratio != est_load / capacity"
assert len(served) == len(old), "row count changed"

def shares(s):
    return s.value_counts(normalize=True).round(3).to_dict()

print("BEFORE (ML fallback):", shares(old.crowd_level))
print("AFTER  (shrinkage)  :", shares(served.crowd_level))
print("\nCrowded share by hour (weekday / weekend):")
t = (served.assign(c=served.crowd_level == "crowded").groupby(["daytype", "hour"]).c.mean().unstack(0).round(3))
print(t.to_string())
worst = t.max().max()
print("\nmax hourly crowded share:", worst)

served.to_parquet(OUT / "crowd_table_served.parquet", index=False)
print("saved outputs/crowd_table_served.parquet")
