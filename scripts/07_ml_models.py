"""
Machine-learning layer with a STRICT TIME-BASED split, and an ML fallback for cells with few tickets.

THE TIMELINE (nothing from the future ever leaks backwards)
    1-14 Oct  weeks 1-2   -> FEATURES: what the tickets of the first two weeks say about every route stretch and hour
    15-21 Oct week 3      -> TRAINING TARGET: the crowd actually seen in week 3
    22-31 Oct             -> TEST TARGET: days the model never saw (the "unseen week 4")

WHAT THE MODEL PREDICTS   load_ratio = estimated people on board / bus capacity   (regression)
                          and the tier seats_available / standing_room / crowded  (classification)

WHY ML HERE   Most (route, stretch, hour) cells have very few tickets. A model that learns from the cells that DO have
              plenty can estimate the sparse ones. We use it ONLY if it beats the plain baselines on sparse test cells.

Run:  python scripts/07_ml_models.py        (about 5-8 minutes; needs notebooks 01-03 to have run)
"""
import sys, json, time, warnings
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd, joblib
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt, seaborn as sns
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LinearRegression, Ridge, Lasso, ElasticNet
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.neighbors import KNeighborsClassifier
from sklearn.svm import SVC
from sklearn.model_selection import GroupShuffleSplit
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score, accuracy_score, f1_score, confusion_matrix
import config
from src import db, crowd, ml_features as mf
from src.common import tier_of, capacity_of, TIER_ORDER
from src.concepts import CONCEPTS

T0 = time.time()
def log(msg): print(f"[{time.time() - T0:6.0f}s] {msg}", flush=True)
SCALE, CAP = config.SCALE["base"], config.LOAD_CAP_RATIO
MIN_TRUTH = 10                    # a test cell must have at least this many tickets to count as reliable ground truth
SPARSE = config.CONF_MED          # "sparse" = fewer than this many tickets in the cell

# ----------------------------------------------------------------------------- helper pieces
class Winsorizer(BaseEstimator, TransformerMixin):
    """Clip every column to the 1st-99th percentile LEARNED FROM THE TRAINING DATA ONLY (so extreme values cannot dominate)."""
    def fit(self, X, y=None):
        X = np.asarray(X, float); self.lo_, self.hi_ = np.nanpercentile(X, 1, axis=0), np.nanpercentile(X, 99, axis=0); return self
    def transform(self, X):
        return np.clip(np.asarray(X, float), self.lo_, self.hi_)

def pipe(model):
    """winsorise -> scale -> model.  Because it is one Pipeline, the cut-offs and the scaling are fitted on TRAIN rows only."""
    return Pipeline([("winsor", Winsorizer()), ("scale", StandardScaler()), ("model", model)])

def to_ratio(idx, cap):
    """ticketed riders per bus -> load ratio (people on board / capacity), calibrated and capped like the crowd table."""
    return np.minimum(np.asarray(idx) * SCALE, CAP * cap) / cap

def window(loc, d0, d1):
    return loc[(loc.day >= d0) & (loc.day <= d1)]

def build_window(loc_w, patterns, supply, attrs, hourly_table):
    nd = loc_w.groupby("daytype").date.nunique().to_dict()
    return crowd.build_crowd_tables(crowd.explode_demand(loc_w, patterns), supply, nd, patterns, attrs, hourly_table=hourly_table)

# ----------------------------------------------------------------------------- 1. load
log("loading tickets and timetable tables ...")
engine = db.get_engine()
loc = db.query("SELECT route_n, b, a, pax, ts, date, daytype, is_ac FROM tickets_located", engine)
loc["ts"] = pd.to_datetime(loc["ts"]); loc["day"] = pd.to_datetime(loc.date).dt.day
patterns, supply, attrs = db.read_table("route_patterns", engine), db.read_table("route_supply", engine), db.read_table("route_attrs", engine)

# ----------------------------------------------------------------------------- 2. the three time windows
log("building the crowd table from weeks 1-2 (features) ...")
A = build_window(window(loc, 1, 14), patterns, supply, attrs, hourly_table=True)["crowd_table"]
A = A[["route_n", "daytype", "hour", "pos", "n_sched", "ticket_count", "est_idx"]].rename(columns={"ticket_count": "own_A_tix", "est_idx": "own_A_idx"})
A["route_A_idx"] = A.groupby(["route_n", "daytype"]).own_A_idx.transform("mean")                     # route average, weeks 1-2
A["routehour_A_idx"] = A.groupby(["route_n", "daytype", "hour"]).own_A_idx.transform("mean")        # route x hour average, weeks 1-2
log("building the target cells for week 3 (train) and 22-31 Oct (test) ...")
B = build_window(window(loc, 15, 21), patterns, supply, attrs, False)["hourly_cells"]
C = build_window(window(loc, 22, 31), patterns, supply, attrs, False)["hourly_cells"]
del loc

def make_rows(cells):
    """Static features (time, place, bus frequency ...) + what weeks 1-2 said + the TRUE load ratio of the target window."""
    d = mf.build_ml_dataset(cells, patterns, attrs, min_tickets=MIN_TRUTH)
    d["daytype"] = np.where(d.is_weekend == 1, "weekend", "weekday")
    d = d.merge(A, on=["route_n", "daytype", "hour", "pos"], how="inner")
    d["capacity"] = capacity_of(d.is_ac)
    d["y_ratio"] = to_ratio(d.idx, d.capacity)
    d["y_tier"] = tier_of(d.y_ratio * d.capacity, d.is_ac)
    for c in ("own_A_idx", "route_A_idx", "routehour_A_idx"):
        d[c + "_ratio"] = to_ratio(d[c], d.capacity)                  # the weeks 1-2 knowledge, expressed as load ratio (also our baselines)
    return d

tr, te = make_rows(B), make_rows(C)
FEATS = [f for f in mf.FEATURES if f != "buses_per_hour"] + ["buses_per_hour", "own_A_idx_ratio", "own_A_tix", "route_A_idx_ratio", "routehour_A_idx_ratio"]
log(f"train rows (week 3): {len(tr):,} | test rows (unseen 22-31 Oct): {len(te):,} | sparse test cells: {(te.own_A_tix < SPARSE).sum():,}")
Xtr, Xte, ytr = tr[FEATS], te[FEATS], tr.y_ratio.clip(*np.percentile(tr.y_ratio, [1, 99]))      # winsorise the training target too
sparse = (te.own_A_tix < SPARSE).to_numpy()

# ----------------------------------------------------------------------------- 3. regression on load_ratio
regs = {"OLS (linear regression)": LinearRegression(), "Ridge": Ridge(alpha=10), "Lasso": Lasso(alpha=0.002, max_iter=20000),
        "Elastic Net": ElasticNet(alpha=0.002, l1_ratio=0.5, max_iter=20000),
        "Gradient Boosting": HistGradientBoostingRegressor(random_state=config.RANDOM_STATE)}
reg_rows, fitted, preds = [], {}, {}
def score(name, p, extra=None):
    row = dict(name=name, mae=mean_absolute_error(te.y_ratio, p), rmse=mean_squared_error(te.y_ratio, p) ** 0.5, r2=r2_score(te.y_ratio, p),
               mae_sparse=mean_absolute_error(te.y_ratio[sparse], p[sparse]) if sparse.any() else None)
    return {k: (round(float(v), 4) if isinstance(v, (float, np.floating)) else v) for k, v in row.items()}
log("regression models ...")
for name, m in regs.items():
    fitted[name] = pipe(m).fit(Xtr, ytr); preds[name] = np.clip(fitted[name].predict(Xte), 0, CAP); reg_rows.append(score(name, preds[name]))
baselines = [score("BASELINE route x hour average (weeks 1-2)", te.routehour_A_idx_ratio.to_numpy()), score("BASELINE weeks 1-2 shrinkage estimate", te.own_A_idx_ratio.to_numpy())]
best = min(reg_rows, key=lambda r: r["mae_sparse"] if r["mae_sparse"] is not None else 9)["name"]
base_best_sparse = min(b["mae_sparse"] for b in baselines)
enabled = bool(next(r for r in reg_rows if r["name"] == best)["mae_sparse"] < base_best_sparse)
log(f"best model on sparse test cells: {best} | beats the best baseline: {enabled}")

# ----------------------------------------------------------------------------- 4. classification into tiers
log("classification models (KNN with k chosen on a validation split, SVM with a row cap) ...")
ytr_t = tr.y_tier
inner_tr, inner_va = next(GroupShuffleSplit(1, test_size=0.2, random_state=config.RANDOM_STATE).split(Xtr, groups=tr.route_n))
knn_cap = np.random.RandomState(config.RANDOM_STATE).choice(inner_tr, min(len(inner_tr), 40000), replace=False)
k_scores = {k: f1_score(ytr_t.iloc[inner_va], pipe(KNeighborsClassifier(k)).fit(Xtr.iloc[knn_cap], ytr_t.iloc[knn_cap]).predict(Xtr.iloc[inner_va]), average="macro") for k in (3, 5, 9, 15, 25, 45)}
best_k = max(k_scores, key=k_scores.get)
svm_rows = np.random.RandomState(config.RANDOM_STATE).choice(len(Xtr), min(len(Xtr), 12000), replace=False)        # row cap: SVMs are slow on big data
clfs = {f"KNN (k={best_k}, chosen on validation)": (pipe(KNeighborsClassifier(best_k)), knn_cap),
        "SVM (RBF, class_weight=balanced, 12k-row cap)": (pipe(SVC(C=2, class_weight="balanced")), svm_rows)}
clf_rows, cpred = [], {}
for name, (m, rows) in clfs.items():
    m.fit(Xtr.iloc[rows], ytr_t.iloc[rows]); cpred[name] = m.predict(Xte)
    clf_rows.append(dict(name=name, accuracy=round(accuracy_score(te.y_tier, cpred[name]), 4), macro_f1=round(f1_score(te.y_tier, cpred[name], average="macro"), 4)))
for nm, col in (("BASELINE tier from weeks 1-2 shrinkage estimate", "own_A_idx_ratio"), ("BASELINE tier from route x hour average", "routehour_A_idx_ratio")):
    p = tier_of(te[col] * te.capacity, te.is_ac)
    clf_rows.append(dict(name=nm, accuracy=round(accuracy_score(te.y_tier, p), 4), macro_f1=round(f1_score(te.y_tier, p, average="macro"), 4)))
best_clf = max([r for r in clf_rows if not r["name"].startswith("BASELINE")], key=lambda r: r["macro_f1"])["name"]
cm = confusion_matrix(te.y_tier, cpred[best_clf], labels=TIER_ORDER)

# ----------------------------------------------------------------------------- 5. explanations: importance, Lasso zeros, correlations
w = pd.Series(np.abs(fitted["Ridge"].named_steps["model"].coef_), index=FEATS); w = (w / w.sum()).sort_values(ascending=False)
lasso_zero = [f for f, c in zip(FEATS, fitted["Lasso"].named_steps["model"].coef_) if c == 0]
cor = Xtr.corr().abs().where(np.triu(np.ones((len(FEATS),) * 2), 1).astype(bool)).stack().sort_values(ascending=False).head(6)
pairs = [dict(feature_a=a, feature_b=b, pearson_r=round(float(Xtr[a].corr(Xtr[b])), 3)) for (a, b) in cor.index]

# ----------------------------------------------------------------------------- 6. figures
log("saving figures ...")
fig, ax = plt.subplots(figsize=(5, 4)); sns.heatmap(pd.DataFrame(cm, index=TIER_ORDER, columns=TIER_ORDER), annot=True, fmt="d", cmap="Blues", cbar=False, ax=ax)
ax.set_title(f"{best_clf}\nunseen days 22-31 Oct"); ax.set_ylabel("true tier"); ax.set_xlabel("predicted tier"); plt.tight_layout(); plt.savefig(config.FIG / "ml_confusion_matrix.png", dpi=130); plt.close()
allr = pd.DataFrame(reg_rows + baselines)
fig, ax = plt.subplots(1, 2, figsize=(12, 4.2))
sns.barplot(data=allr, y="name", x="mae", color="#2a9d8f", ax=ax[0]); ax[0].set_title("Error on ALL reliable unseen cells (MAE of load ratio, lower = better)"); ax[0].set_ylabel("")
sns.barplot(data=allr, y="name", x="mae_sparse", color="#e76f51", ax=ax[1]); ax[1].set_title("Error on SPARSE cells (<10 tickets in weeks 1-2)"); ax[1].set_ylabel(""); ax[1].set_yticklabels([])
plt.tight_layout(); plt.savefig(config.FIG / "ml_model_comparison.png", dpi=130); plt.close()

# ----------------------------------------------------------------------------- 7. save the model, then build the SERVED crowd table
(config.OUT / "models").mkdir(exist_ok=True)
joblib.dump(dict(model=fitted[best], name=best, features=FEATS, target="load_ratio", enabled=enabled, trained_on="week 3 (15-21 Oct) with features from weeks 1-2"), config.OUT / "models" / "crowd_fallback.joblib")

served_path = config.OUT / "crowd_table_served.parquet"
log("applying the fallback to sparse cells of the full-month crowd table ...")
ct = pd.read_parquet(config.OUT / "crowd_table.parquet", columns=["route_n", "daytype", "hour", "pos", "n_sched", "ticket_count", "est_idx", "est_load", "est_load_raw", "capacity", "load_ratio", "crowd_level", "confidence", "fallback", "is_ac"])
ct["prediction_source"] = np.where(ct.ticket_count >= SPARSE, "observed_tickets", "route_average")
if enabled:
    sp = ct.index[ct.ticket_count < SPARSE]
    full = ct.loc[sp, ["route_n", "daytype", "hour", "pos", "n_sched", "ticket_count", "est_idx"]].rename(columns={"ticket_count": "own_A_tix", "est_idx": "own_A_idx"})
    full["route_A_idx"] = ct.groupby(["route_n", "daytype"]).est_idx.transform("mean").loc[sp]
    full["routehour_A_idx"] = ct.groupby(["route_n", "daytype", "hour"]).est_idx.transform("mean").loc[sp]
    cells = full.assign(n_tix=1, pax_sum=0.0, idx=full.own_A_idx)[["route_n", "daytype", "hour", "pos", "n_sched", "pax_sum", "n_tix", "idx", "own_A_tix", "own_A_idx", "route_A_idx", "routehour_A_idx"]]
    d = mf.build_ml_dataset(cells, patterns, attrs, min_tickets=0)
    d["daytype"] = np.where(d.is_weekend == 1, "weekend", "weekday")
    d = d.merge(cells[["route_n", "daytype", "hour", "pos", "own_A_tix", "own_A_idx", "route_A_idx", "routehour_A_idx"]], on=["route_n", "daytype", "hour", "pos"], how="left")
    cap_ = capacity_of(d.is_ac)
    for c in ("own_A_idx", "route_A_idx", "routehour_A_idx"): d[c + "_ratio"] = to_ratio(d[c], cap_)
    p = np.clip(fitted[best].predict(d[FEATS]), 0, CAP)
    key = ct.loc[sp, ["route_n", "daytype", "hour", "pos"]].reset_index().merge(d[["route_n", "daytype", "hour", "pos"]].assign(pred=p), on=["route_n", "daytype", "hour", "pos"], how="left").set_index("index")
    ok = key.pred.notna(); idx_ok = key.index[ok]
    ct.loc[idx_ok, "load_ratio"] = key.pred[ok].to_numpy(); ct.loc[idx_ok, "est_load"] = (key.pred[ok] * ct.loc[idx_ok, "capacity"]).to_numpy()
    ct.loc[idx_ok, "crowd_level"] = tier_of(ct.loc[idx_ok, "est_load"], ct.loc[idx_ok, "is_ac"]); ct.loc[idx_ok, "prediction_source"] = "ml_fallback"
ct.drop(columns=["est_idx", "is_ac"]).to_parquet(served_path, index=False)
src = ct.prediction_source.value_counts()

# ----------------------------------------------------------------------------- 8. metrics file (everything here comes from this run)
out = dict(
    split_method="Strict temporal split: features from 1-14 Oct (weeks 1-2), training target 15-21 Oct (week 3), test on unseen 22-31 Oct. Test cells need 10+ tickets.",
    preprocessing_summary="Winsorise features and training target at the 1st/99th percentile of TRAIN data, then StandardScaler, both fitted on train rows only inside one Pipeline. Row cap for SVM (12,000) and KNN search (40,000).",
    train_rows=int(len(tr)), test_rows=int(len(te)), test_sparse_rows=int(sparse.sum()),
    active_fallback_model=best if enabled else "none (ML did not beat the baselines on sparse cells)", ml_fallback_enabled=enabled,
    fallback_stats=dict(total_segments=int(len(ct)), observed_segments=int(src.get("observed_tickets", 0)), ml_fallback_segments=int(src.get("ml_fallback", 0)),
                        ml_fallback_pct=round(float(src.get("ml_fallback", 0)) / len(ct) * 100, 2), route_average_segments=int(src.get("route_average", 0))),
    regression_models=reg_rows, baselines=baselines, classification_models=clf_rows, best_classifier=best_clf, knn_k_scores={str(k): round(v, 4) for k, v in k_scores.items()},
    confusion_matrix=dict(labels=TIER_ORDER, matrix=cm.tolist()),
    feature_importance=[dict(feature=f, weight=round(float(v), 4)) for f, v in w.items()], lasso_zeroed_features=lasso_zero, top_correlated_pairs=pairs,
    caveats=["The 'sparse cell' test only includes cells that later had 10+ tickets (we need a reliable answer to score against). Such cells were BUSIER than they looked in weeks 1-2, which favours any model that can infer 'this place and hour is busy' from location and time. The advantage over the baselines on sparse cells is therefore real but overstated; cells that stay sparse cannot be scored at all.",
             "The fallback is applied with features built from the whole month (not only weeks 1-2), a slightly different window from training.",
             "The target is itself an estimate built from a SAMPLE of riders (mobile e-tickets) scaled by an assumed factor; ML learns to predict that estimate, not a head-count."],
    concepts=CONCEPTS, scale_factor=round(SCALE, 2))
(config.OUT / "ml_metrics.json").write_text(json.dumps(out, indent=2))
log(f"done. fallback enabled={enabled}; served table written to {served_path.name}")
print(pd.DataFrame(reg_rows + baselines)[["name", "mae", "rmse", "r2", "mae_sparse"]].to_string(index=False)); print(pd.DataFrame(clf_rows).to_string(index=False))
