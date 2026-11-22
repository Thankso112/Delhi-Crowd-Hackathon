"""Run the whole pipeline from raw data with one command:   python run_pipeline.py   [--db]
(The notebooks in notebooks/ do the same steps one at a time, with plots and explanations.)"""
import sys, time, json, gc
import pandas as pd
import config
from crowd import ingest, gtfs, matching, trips, flow, model, validate, ml, db

def step(msg): print(f"\n=== {msg} ===", flush=True)

def main(use_db=False):
    P, OUT = config.PROC, config.OUT
    t0 = time.time()
    step("1. Load + profile tickets"); tk = ingest.load_tickets()
    prof = ingest.profile(tk); md = ingest.profile_markdown(prof, config.TICKETS_CSV)
    (config.DOCS if config.MODE == "real" else OUT).joinpath("data_profile.md").write_text(md); print(md[:900]); tk_rows = len(tk)
    excl = prof["daily"][prof["daily"].outlier].date.tolist(); print("outlier weekdays excluded from the model:", excl)
    tk.to_parquet(P / "tickets.parquet")
    step("2. GTFS patterns"); pat, hourly, stops = gtfs.build_patterns()
    pat.to_parquet(P / "patterns.parquet"); hourly.to_parquet(P / "route_hourly.parquet"); stops.to_parquet(P / "stops.parquet")
    print(f"{pat.groupby(['route_id', 'dir']).ngroups} route-directions, {pat.stop_id.nunique()} stops")
    step("3. Match stop names"); sm = matching.match_stop_names(tk, pat)
    sm.to_parquet(P / "stop_map.parquet"); rep = matching.match_report(sm); (OUT / "match_report.md").write_text(rep); print(rep)
    sm[sm.gtfs_name_n.isna() & (sm.method != "blank")].sort_values("n_uses", ascending=False).to_csv(OUT / "unmatched_names.csv", index=False)
    step("4. Resolve tickets to route positions"); tx, stats = trips.resolve_tickets(tk, pat, sm); print(stats)
    keep = ["route_n", "route_raw", "dir", "b", "a", "pax", "ts", "date", "hour", "dow", "is_ac", "vehicle", "imputed_end"]
    tx = tx[keep].copy(); del tk, sm; gc.collect()            # free memory (the sandbox has only 3 GB)
    tx.to_parquet(P / "tickets_resolved.parquet")
    (OUT / "resolution_report.md").write_text(f"# Ticket resolution report\n{json.dumps(stats, indent=2)}\n")
    step("5. Flow-based crowd table")
    attrs = tx.groupby("route_n").agg(route=("route_raw", "first"), is_ac=("is_ac", lambda s: int(s.mean() > 0.5))).reset_index(); attrs["route"] = attrs.route.astype(str)
    cells_raw = flow.compute_flow_cells(tx, hourly, pat, exclude_dates=excl)
    cells, lv, cal = model.build_crowd_tables(cells_raw, attrs); print(cal)
    cells.to_parquet(P / "crowd_segments.parquet"); lv.to_parquet(P / "crowd_route_level.parquet"); attrs.to_parquet(P / "route_attrs.parquet")
    json.dump(cal, open(P / "calibration.json", "w"), indent=2)
    model.readable_table(cells, pat, attrs).to_csv(OUT / "crowd_table.csv.gz", index=False)       # city-wide crowd table, every stretch
    lv.merge(attrs[["route_n", "route"]], on="route_n").drop(columns=["route_n"]).round(2).to_csv(OUT / "crowd_route_level.csv", index=False)   # compact: one row per route, day type, band
    print(cells.level.value_counts(normalize=True).round(3).to_dict(), cells.confidence.value_counts().to_dict())
    step("6. Validation + ML suite (hold-out, 4 regressors, 2 classifiers)"); M, tab, _, ins = validate.run_validation(tx, hourly, pat, attrs, cells, cal, excl, OUT); print(tab); print({k: v for k, v in M.items() if k != "holdout"})
    step("6b. ML fallback for thin stretches + final crowd table")
    cells = ml.apply_fallback(cells, ins["_model"], ins["_ml_wins"], cal["coverage_factor"]); ins["fallback_stats"] = ml.fallback_stats(cells); print(ins["fallback_stats"], "| thin-cell MAE:", ins["thin_cell_comparison"])
    ins.pop("_model"); ins.pop("_ml_wins"); json.dump(ins, open(P / "ml_insights.json", "w"), indent=2); json.dump(ins, open(OUT / "ml_insights.json", "w"), indent=2)
    cells.to_parquet(P / "crowd_segments.parquet"); model.readable_table(cells.assign(source=cells.prediction_source), pat, attrs).to_csv(OUT / "crowd_table.csv.gz", index=False)
    if use_db:
        step("7. Save to SQL database"); eng = db.save_tables({"crowd_segments": cells, "route_attrs": attrs}); print("saved to", eng.url)
    print(f"\nDone in {time.time() - t0:.0f}s. Start the app:  streamlit run app.py")

if __name__ == "__main__":
    main(use_db="--db" in sys.argv)
