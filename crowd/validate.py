"""Validation on the flow-based crowd estimate. Time-based hold-out with three consecutive 7-day windows:
   W1 = days 1-7, W2 = days 8-14, W3 = days 15-21.
   Every model predicts W3 from W2 features. Trained models (LinearRegression, gradient boosting) learn W1 -> W2 first. Never a random split (that would leak)."""
import json
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt, seaborn as sns
from scipy.stats import spearmanr
from scipy.sparse import hstack, csr_matrix
from sklearn.linear_model import LinearRegression
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.preprocessing import OneHotEncoder
from sklearn.metrics import r2_score, mean_absolute_error, mean_squared_error
from crowd.text import config, level_of
from crowd.flow import compute_flow_cells, BAND_CODE
from crowd.model import shrink

KEY = ["route_n", "dir", "daytype", "band", "pos"]
sns.set_theme(style="whitegrid", context="notebook")

def window_dates(tix, lo, hi):
    ds = sorted(tix.date.unique())
    return [d for d in ds if lo <= int(d[-2:]) <= hi]

def pair_frame(F, T, attrs):
    """Features from window F, target from window T, one row per target cell."""
    f = F[KEY + ["tix_load", "n_tickets"]].rename(columns={"tix_load": "mF", "n_tickets": "nF"})
    f["rF"] = f.groupby(["route_n", "dir", "daytype", "band"]).mF.transform("mean")
    gF = F.groupby(["daytype", "band"]).tix_load.mean().rename("gF").reset_index()
    t = T[KEY + ["tix_load", "n_tickets", "trips_per_day", "n_stops"]].rename(columns={"tix_load": "y", "n_tickets": "nT"})
    d = t.merge(f, on=KEY, how="left").merge(gF, on=["daytype", "band"], how="left")
    rF = F.groupby(["route_n", "dir", "daytype", "band"]).tix_load.mean().rename("rF2").reset_index()
    d = d.merge(rF, on=["route_n", "dir", "daytype", "band"], how="left")
    d["rF"] = d.rF2; d = d.drop(columns="rF2")
    d["nF"] = d.nF.fillna(0)
    prior = d.rF.fillna(d.gF)
    d["pred_model"] = (d.nF * d.mF.fillna(0) + config.SHRINK_K * prior) / (d.nF + config.SHRINK_K)
    d["pred_route"] = d.rF.fillna(d.gF); d["pred_global"] = d.gF
    d["is_ac"] = d.route_n.map(attrs.set_index("route_n").is_ac).fillna(0)
    d["band_c"] = d.band.map(BAND_CODE); d["day_c"] = (d.daytype == "weekend").astype(int); d["pos_frac"] = d.pos / (d.n_stops - 1).clip(lower=1)
    return d.dropna(subset=["pred_model"])

HGB_FEATURES = ["mF", "nF", "rF", "gF", "band_c", "day_c", "pos", "pos_frac", "n_stops", "trips_per_day", "is_ac"]

def fit_models(train):
    """Train on one (features -> next window) pair, return fitted objects."""
    tr = train[train.nT >= config.MIN_TICKETS_TRUTH]
    enc = OneHotEncoder(handle_unknown="ignore")
    rd = tr.route_n + "_" + tr.dir.astype(str)
    X = hstack([enc.fit_transform(pd.DataFrame({"rd": rd, "band": tr.band, "daytype": tr.daytype})), csr_matrix(tr[["pos", "pos_frac"]].to_numpy(float))]).tocsr()
    lr = LinearRegression().fit(X, tr.y, sample_weight=tr.nT)
    gb = HistGradientBoostingRegressor(max_iter=200, learning_rate=0.08, max_depth=6, random_state=0).fit(tr[HGB_FEATURES], tr.y, sample_weight=tr.nT)
    return enc, lr, gb

def predict_lr(enc, lr, d):
    X = hstack([enc.transform(pd.DataFrame({"rd": d.route_n + "_" + d.dir.astype(str), "band": d.band, "daytype": d.daytype})), csr_matrix(d[["pos", "pos_frac"]].to_numpy(float))]).tocsr()
    return np.clip(lr.predict(X), 0, None)

def scores(y, p, w=None):
    return dict(MAE=round(float(mean_absolute_error(y, p)), 4), RMSE=round(float(np.sqrt(mean_squared_error(y, p))), 4), R2=round(float(r2_score(y, p)), 4),
                Spearman=round(float(spearmanr(y, p).statistic), 4))

def run_validation(tix, hourly, pat, route_attrs, cells, coverage, exclude_dates, out_dir):
    FIG = out_dir / "figures"; FIG.mkdir(parents=True, exist_ok=True)
    attrs = route_attrs; M = {"coverage_factor": coverage["coverage_factor"]}
    W = {i: compute_flow_cells(tix, hourly, pat, dates=window_dates(tix, lo, hi), exclude_dates=exclude_dates) for i, (lo, hi) in enumerate([(1, 7), (8, 14), (15, 21)], 1)}
    train = pair_frame(W[1], W[2], attrs); test = pair_frame(W[2], W[3], attrs)
    enc, lr, gb = fit_models(train)
    test = test.assign(pred_lr=predict_lr(enc, lr, test), pred_gb=np.clip(gb.predict(test[HGB_FEATURES]), 0, None))
    rel = test[test.nT >= config.MIN_TICKETS_TRUTH]                      # only judge cells with enough tickets to be reliable truth
    M["n_test_cells"] = int(len(rel))
    res = {name: scores(rel.y, rel[col]) for name, col in [("shrinkage model", "pred_model"), ("route-level average", "pred_route"), ("city-wide average", "pred_global"), ("linear regression", "pred_lr"), ("gradient boosting", "pred_gb")]}
    tab = pd.DataFrame(res).T; tab.to_csv(out_dir / "holdout_scores.csv"); M["holdout"] = res
    # stability of the raw pattern between consecutive windows + level agreement
    both = pair_frame(W[2], W[3], attrs); both = both[(both.nT >= config.MIN_TICKETS_TRUTH) & (both.nF >= config.MIN_TICKETS_TRUTH)]
    M["stability_spearman_W2_vs_W3"] = round(float(spearmanr(both.mF, both.y).statistic), 4)
    cf = coverage["coverage_factor"]
    for name, col in [("shrinkage", "pred_model"), ("gradient_boosting", "pred_gb")]:
        M[f"level_accuracy_{name}"] = round(float((level_of(rel[col] * cf, rel.is_ac) == level_of(rel.y * cf, rel.is_ac)).mean()), 4)
    M["skill_shrinkage_vs_route_baseline"] = round(1 - res["shrinkage model"]["MAE"] / res["route-level average"]["MAE"], 4)
    # figures
    fig, ax = plt.subplots(figsize=(7, 3.4)); tab.MAE.sort_values().plot.barh(ax=ax, color="#12263F"); ax.set(xlabel="hold-out MAE (ticketed passengers per trip)", title="Predicting week 3 from week 2"); fig.tight_layout(); fig.savefig(FIG / "holdout_mae.png", dpi=130); plt.close(fig)
    fig, ax = plt.subplots(figsize=(4.6, 4.6)); s = rel.sample(min(5000, len(rel)), random_state=0); sns.scatterplot(data=s, x="pred_gb", y="y", s=8, alpha=.4, ax=ax); lim = max(s.pred_gb.max(), s.y.max()); ax.plot([0, lim], [0, lim], "k--", lw=1)
    ax.set(xlabel="predicted (gradient boosting)", ylabel="actual, week 3", title=f"R² = {res['gradient boosting']['R2']:.2f}"); fig.tight_layout(); fig.savefig(FIG / "pred_vs_actual.png", dpi=130); plt.close(fig)
    t = tix.assign(daytype=np.where(tix.dow < 6, "weekday", "weekend")); h = t.groupby(["daytype", "hour"]).pax.sum().div(t.groupby("daytype").date.nunique(), level="daytype").rename("pax").reset_index()
    fig, ax = plt.subplots(figsize=(7, 3.4)); sns.lineplot(data=h, x="hour", y="pax", hue="daytype", marker="o", ax=ax); ax.set(ylabel="avg ticketed passengers / day", title="Boardings by hour"); fig.tight_layout(); fig.savefig(FIG / "hourly_pattern.png", dpi=130); plt.close(fig)
    M["peak_hours_weekday"] = [int(x) for x in h[h.daytype == "weekday"].set_index("hour").pax.sort_values(ascending=False).index[:3]]
    # sensitivity: how many cells are labelled crowded if the coverage factor is wrong
    rows = []
    for mult in (0.5, 0.75, 1.0, 1.5, 2.0):
        lv = level_of(cells.est_load * cf * mult, cells.is_ac.fillna(0))
        rows.append(dict(coverage_multiplier=mult, seats=(lv == "seats").mean(), standing=(lv == "standing").mean(), crowded=(lv == "crowded").mean()))
    sens = pd.DataFrame(rows).round(3); sens.to_csv(out_dir / "sensitivity.csv", index=False)
    M["sensitivity_crowded_share_range"] = [float(sens.crowded.min()), float(sens.crowded.max())]
    M["base_level_shares"] = {k: float(sens[sens.coverage_multiplier == 1.0][k].iloc[0]) for k in ("seats", "standing", "crowded")}
    M["share_low_confidence_cells"] = round(float((cells.confidence == "low").mean()), 4); M["n_crowd_cells"] = int(len(cells)); M["mode"] = config.MODE
    M["ARENA_SCORE"] = round(float(0.4 * max(0, M["skill_shrinkage_vs_route_baseline"]) + 0.3 * M["stability_spearman_W2_vs_W3"] + 0.3 * M["level_accuracy_shrinkage"]), 4)
    json.dump(M, open(out_dir / "metrics.json", "w"), indent=2, default=float)
    (out_dir / "validation.md").write_text("# Validation summary (auto-generated)\n\n```json\n" + json.dumps(M, indent=2, default=float) + "\n```\n\n" + tab.to_markdown() + "\n\n![](figures/holdout_mae.png)\n![](figures/pred_vs_actual.png)\n![](figures/hourly_pattern.png)\n\n## Sensitivity to the coverage factor\n" + sens.to_markdown(index=False))
    from crowd import ml
    ins = ml.build_suite(train, test, coverage, out_dir)
    M["ml_active_fallback_model"] = ins["active_fallback_model"]
    return M, tab, sens, ins
