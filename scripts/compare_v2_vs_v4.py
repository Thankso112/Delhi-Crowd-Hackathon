#!/usr/bin/env python3
"""
compare_v2_vs_v4.py  -  fair head-to-head of the V2 and V4 ML "recipes" on the SAME real data.

WHY: the saved scores of V2 and V4 use different targets, test windows, filters and class balance, so they cannot be compared.
This script rebuilds ONE common dataset from the raw ticket file and scores every model on identical rows with identical metrics.

WHAT IT DOES
  * Cell = route x daytype (weekday/weekend) x hour.   Target = tickets per day in the TEST window (log1p scale).
  * Strictly temporal:  train  = features from days 1-14  -> target days 15-21
                        test   = features from days 8-21  -> target days 22-end        (nothing from the test window is ever seen)
  * Same feature set for every model (own history, route / route-hour / city averages, hour, peaks, AC).
  * "V2 recipe": LinearRegression, Lasso, RandomForest, GradientBoosting, Logistic, GB-classifier  (raw features, no winsorising)
  * "V4 recipe": OLS, Ridge, Lasso, ElasticNet, GradientBoosting, KNN, SVM (winsorise 1/99 + StandardScaler fitted on train only)
  * Baselines: global mean, own-history persistence, shrinkage estimate.
  * Two test views: ALL cells (no filtering on the outcome) and cells with >= MIN_TEST tickets (what both repos used).
  * Optional UNSEEN-ROUTE test (--unseen): hold out 20% of routes from training.

LIMITS (be honest in your report): works at route-hour level, not stop-to-stop stretch level, and needs no GTFS; it compares the
modelling approaches, not the exact saved .joblib files. Pass/fail of the real pipelines still needs `run_all.py` / `run_pipeline.py`.

USAGE
    pip install pandas numpy scikit-learn scipy
    python compare_v2_vs_v4.py --tickets data/raw/tickets.csv
    python compare_v2_vs_v4.py --tickets data/raw/tickets.csv --unseen            # also the unseen-route test
    python compare_v2_vs_v4.py --tickets data/raw/tickets.csv --nrows 500000      # quick smoke test
Outputs: compare_results.csv, compare_report.md (in --out, default current folder).
"""
import argparse, time, warnings
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import ElasticNet, Lasso, LinearRegression, LogisticRegression, Ridge
from sklearn.metrics import accuracy_score, f1_score, mean_absolute_error, mean_squared_error, r2_score
from sklearn.neighbors import KNeighborsClassifier, KNeighborsRegressor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC, SVR

warnings.filterwarnings("ignore")
SEED = 42
COL = dict(pax="passenger_count", route="route", ts="created_at", ac="is_ac")      # same names both repos use (config.COL)
FEATURES = ["own_mean", "own_log", "own_n", "route_dt_mean", "route_hour_mean", "city_hour_dt_mean",
            "hour", "hour_sin", "hour_cos", "is_weekend", "is_am_peak", "is_pm_peak", "is_ac"]
LEVELS = ["Quiet", "Moderate", "Busy"]
CUTS = (50, 85)          # percentile cut-offs for the three tiers (same as V4 config.LEVEL_CUTS)
SHRINK_K = 10.0          # same as V4 config.SHRINK_K


# ----------------------------------------------------------------------------------------------- data
def norm_route(s):
    return s.astype(str).str.replace(r"\s+", "", regex=True).str.upper().str.lstrip("0")


def load(path, nrows=None):
    head = pd.read_csv(path, nrows=0).columns
    miss = [v for v in COL.values() if v not in head]
    assert not miss, f"Columns missing from CSV: {miss}. Found: {list(head)}. Edit COL at the top of this file."
    df = pd.read_csv(path, usecols=list(COL.values()), na_values=["NULL", "null", "None", ""], nrows=nrows,
                     dtype={COL["route"]: str, COL["ac"]: str, COL["ts"]: str})
    out = pd.DataFrame({
        "pax": pd.to_numeric(df[COL["pax"]], errors="coerce"),
        "route": df[COL["route"]],
        "ts": pd.to_datetime(df[COL["ts"]].astype(str).str.slice(0, 19), errors="coerce"),
        "is_ac": df[COL["ac"]].astype(str).str.lower().isin(["1", "true", "t", "yes", "y", "ac", "1.0"]).astype(int)})
    out = out[out.ts.notna() & out.route.notna() & (out.pax > 0)].copy()
    out["route"] = norm_route(out.route)
    out["date"] = out.ts.dt.normalize()
    out["day"] = out.ts.dt.day
    out["hour"] = out.ts.dt.hour
    dow = out.ts.dt.dayofweek
    daily = out.groupby("date").size()
    weekday_med = daily[daily.index.dayofweek < 5].median()
    off = set(daily[(daily.index.dayofweek < 5) & (daily / weekday_med < 0.6)].index)      # holiday-like weekdays (V4 logic)
    out["weekend"] = ((dow >= 5) | out.date.isin(off)).astype(int)
    return out.drop(columns=["ts"]), sorted(off)


def window_table(df, d0, d1):
    """tickets per day (passengers) for every (route, weekend, hour) seen in days d0..d1 + number of tickets."""
    w = df[(df.day >= d0) & (df.day <= d1)]
    ndays = w.groupby("weekend").date.nunique()
    g = w.groupby(["route", "weekend", "hour"]).pax.agg(["sum", "size"]).reset_index()
    g["per_day"] = g["sum"] / g.weekend.map(ndays).replace(0, np.nan)
    g = g.rename(columns={"size": "n_tix"})
    return g[["route", "weekend", "hour", "per_day", "n_tix"]], ndays


def build(df, h0, h1, t0, t1):
    """Rows = full grid (every route seen in the history window x weekend x hour). Features from days h0..h1, target from t0..t1."""
    hist, _ = window_table(df, h0, h1)
    targ, _ = window_table(df, t0, t1)
    routes = hist.route.unique()
    grid = pd.MultiIndex.from_product([routes, [0, 1], range(24)], names=["route", "weekend", "hour"]).to_frame(index=False)
    X = grid.merge(hist.rename(columns={"per_day": "own_mean", "n_tix": "own_n"}), on=["route", "weekend", "hour"], how="left")
    X[["own_mean", "own_n"]] = X[["own_mean", "own_n"]].fillna(0)
    X["route_dt_mean"] = X.groupby(["route", "weekend"]).own_mean.transform("mean")
    X["route_hour_mean"] = X.groupby(["route", "hour"]).own_mean.transform("mean")
    X["city_hour_dt_mean"] = X.groupby(["weekend", "hour"]).own_mean.transform("mean")
    ac = df.groupby("route").is_ac.max()
    X["is_ac"] = X.route.map(ac).fillna(0).astype(int)
    X["own_log"] = np.log1p(X.own_mean)
    X["hour_sin"], X["hour_cos"] = np.sin(2 * np.pi * X.hour / 24), np.cos(2 * np.pi * X.hour / 24)
    X["is_weekend"] = X.weekend
    X["is_am_peak"], X["is_pm_peak"] = X.hour.between(7, 9).astype(int), X.hour.between(16, 19).astype(int)
    X = X.merge(targ.rename(columns={"per_day": "y_raw", "n_tix": "test_tix"}), on=["route", "weekend", "hour"], how="left")
    X[["y_raw", "test_tix"]] = X[["y_raw", "test_tix"]].fillna(0)
    X["y"] = np.log1p(X.y_raw)
    return X


# ----------------------------------------------------------------------------------------------- models
class Winsor(BaseEstimator, TransformerMixin):
    """Clip every column at the 1st/99th percentile of the TRAIN data (V4 preprocessing)."""
    def fit(self, X, y=None):
        self.lo_, self.hi_ = np.percentile(X, 1, axis=0), np.percentile(X, 99, axis=0)
        return self
    def transform(self, X):
        return np.clip(X, self.lo_, self.hi_)


def v2_regressors():
    sc = lambda m: make_pipeline(StandardScaler(), m)
    return {"V2 | Linear Regression": sc(LinearRegression()), "V2 | Lasso": sc(Lasso(alpha=0.001, max_iter=5000)),
            "V2 | Random Forest": RandomForestRegressor(200, min_samples_leaf=5, n_jobs=-1, random_state=SEED),
            "V2 | Gradient Boosting": HistGradientBoostingRegressor(learning_rate=0.1, max_leaf_nodes=15, min_samples_leaf=20, random_state=SEED)}


def v4_regressors():
    pp = lambda m: make_pipeline(Winsor(), StandardScaler(), m)
    return {"V4 | OLS": pp(LinearRegression()), "V4 | Ridge": pp(Ridge(alpha=1.0)),
            "V4 | Lasso": pp(Lasso(alpha=0.001, max_iter=5000)), "V4 | Elastic Net": pp(ElasticNet(alpha=0.001, l1_ratio=0.5, max_iter=5000)),
            "V4 | Gradient Boosting": pp(HistGradientBoostingRegressor(learning_rate=0.1, max_leaf_nodes=15, min_samples_leaf=20, random_state=SEED)),
            "V4 | KNN (k=15)": pp(KNeighborsRegressor(15, n_jobs=-1)), "V4 | SVR (RBF, 12k cap)": pp(SVR(C=1.0))}


def v2_classifiers():
    return {"V2 | Logistic Regression": make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000)),
            "V2 | GB classifier": HistGradientBoostingClassifier(learning_rate=0.1, max_leaf_nodes=15, min_samples_leaf=20, random_state=SEED)}


def v4_classifiers():
    pp = lambda m: make_pipeline(Winsor(), StandardScaler(), m)
    return {"V4 | KNN (k=15)": pp(KNeighborsClassifier(15, n_jobs=-1)),
            "V4 | SVM (RBF, balanced, 12k cap)": pp(SVC(C=1.0, class_weight="balanced"))}


CAPPED = ("SVR", "SVM")


# ----------------------------------------------------------------------------------------------- metrics
def tier(y_log, cuts):
    return np.digitize(y_log, cuts)          # 0 Quiet, 1 Moderate, 2 Busy


def score_reg(y, p, y_raw, cuts):
    p = np.clip(p, 0, None)
    t_true, t_pred = tier(y, cuts), tier(p, cuts)
    rho = spearmanr(y, p).correlation if np.std(p) > 0 else np.nan
    return dict(R2=r2_score(y, p), MAE_log=mean_absolute_error(y, p), RMSE_log=mean_squared_error(y, p) ** 0.5,
                MAE_tickets_per_day=mean_absolute_error(y_raw, np.expm1(p)), Spearman=rho,
                tier_acc=accuracy_score(t_true, t_pred), tier_macroF1=f1_score(t_true, t_pred, average="macro"))


def run(df, args, unseen=False):
    A = build(df, 1, 14, 15, 21)                                  # train rows
    T = build(df, 8, 21, 22, 31)                                  # test rows (target window never seen)
    if unseen:
        rs = np.random.RandomState(SEED)
        routes = np.array(sorted(A.route.unique()))
        held = set(rs.choice(routes, int(0.2 * len(routes)), replace=False))
        A, T = A[~A.route.isin(held)], T[T.route.isin(held)]
    Xtr, ytr = A[FEATURES].to_numpy(float), A.y.to_numpy()
    Xte, yte = T[FEATURES].to_numpy(float), T.y.to_numpy()
    pos = ytr[A.y_raw.to_numpy() > 0]
    cuts = np.percentile(pos, CUTS)                               # tier cut-offs from TRAIN target only
    ytr_w = np.clip(ytr, *np.percentile(ytr, [1, 99]))             # V4: winsorise the training target too
    views = {"ALL cells (no outcome filter)": np.ones(len(T), bool),
             f"cells with >= {args.min_test} test tickets": (T.test_tix.to_numpy() >= args.min_test)}
    print(f"\n{'UNSEEN-ROUTE' if unseen else 'TEMPORAL'} test: train cells {len(A):,}  test cells {len(T):,}  "
          f"(>= {args.min_test} tickets: {views[list(views)[1]].sum():,})  tier cuts (log1p tickets/day) {np.round(cuts, 3)}")

    preds, secs = {}, {}
    def go(name, model, y_fit, label_fit=False):
        t0 = time.time()
        Xf, yf = Xtr, y_fit
        if any(c in name for c in CAPPED) and len(Xf) > 12000:
            idx = np.random.RandomState(SEED).choice(len(Xf), 12000, replace=False); Xf, yf = Xf[idx], yf[idx]
        model.fit(Xf, yf)
        preds[name] = model.predict(Xte); secs[name] = time.time() - t0
        print(f"   fitted {name:<38s} {secs[name]:6.1f}s")

    print("fitting models ...")
    for n, m in v2_regressors().items(): go(n, m, ytr)
    for n, m in v4_regressors().items(): go(n, m, ytr_w)
    ttr = tier(ytr, cuts)
    cls = {}
    for n, m in {**v2_classifiers(), **v4_classifiers()}.items():
        t0 = time.time(); Xf, yf = Xtr, ttr
        if any(c in n for c in CAPPED) and len(Xf) > 12000:
            idx = np.random.RandomState(SEED).choice(len(Xf), 12000, replace=False); Xf, yf = Xf[idx], yf[idx]
        m.fit(Xf, yf); cls[n] = m.predict(Xte); print(f"   fitted {n:<38s} {time.time() - t0:6.1f}s")

    # baselines (no training)
    own, rh = T.own_mean.to_numpy(), T.route_hour_mean.to_numpy()
    shr = (T.own_n.to_numpy() * own + SHRINK_K * rh) / (T.own_n.to_numpy() + SHRINK_K)
    base = {"BASE | global mean": np.full(len(T), ytr.mean()), "BASE | own-history persistence": np.log1p(own),
            "BASE | shrinkage (own + route-hour)": np.log1p(shr)}

    rows = []
    for view, mask in views.items():
        y, yr = yte[mask], T.y_raw.to_numpy()[mask]
        for n, p in {**preds, **base}.items():
            rows.append(dict(view=view, model=n, **score_reg(y, p[mask], yr, cuts)))
        for n, p in cls.items():
            rows.append(dict(view=view, model=n + "  [classifier]", tier_acc=accuracy_score(tier(y, cuts), p[mask]),
                             tier_macroF1=f1_score(tier(y, cuts), p[mask], average="macro")))
    res = pd.DataFrame(rows)
    res.insert(0, "test", "unseen routes" if unseen else "temporal")
    return res


def report(res, args):
    lines = ["# V2 vs V4 - same data, same split, same metrics\n",
             f"Tickets: `{args.tickets}`. Train: features days 1-14 -> target 15-21. Test: features days 8-21 -> target 22-31. "
             "Cell = route x weekday/weekend x hour. R2 / MAE on log1p(tickets per day).\n"]
    for (test, view), g in res.groupby(["test", "view"], sort=False):
        g = g.copy()
        g["recipe"] = g.model.str.split(" | ").str[0]
        lines.append(f"\n## {test} - {view}\n")
        cols = ["model", "R2", "MAE_log", "RMSE_log", "MAE_tickets_per_day", "Spearman", "tier_acc", "tier_macroF1"]
        lines.append("```\n" + g.sort_values("R2", ascending=False, na_position="last")[cols].round(4).to_string(index=False) + "\n```")
        reg = g[g.R2.notna() & g.recipe.isin(["V2", "V4"])]
        cl = g[g.R2.isna() & g.recipe.isin(["V2", "V4"])]
        if len(reg):
            b = reg.groupby("recipe").R2.max()
            lines.append(f"\nBest R2  -> V2: {b.get('V2', float('nan')):.4f}   V4: {b.get('V4', float('nan')):.4f}")
        if len(cl):
            b = cl.groupby("recipe").tier_macroF1.max()
            lines.append(f"Best classifier macro-F1 -> V2: {b.get('V2', float('nan')):.4f}   V4: {b.get('V4', float('nan')):.4f}")
        sh = g[g.model.str.contains("shrinkage")].R2.max()
        lines.append(f"Shrinkage baseline R2 = {sh:.4f}  (a model must beat this to add value)")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickets", required=True, help="path to the raw ticket CSV (October-Delhi.csv)")
    ap.add_argument("--nrows", type=int, default=None, help="read only the first N rows (smoke test)")
    ap.add_argument("--min-test", type=int, default=10, help="min test-window tickets for the 'truth' view (both repos used 10)")
    ap.add_argument("--unseen", action="store_true", help="also run the unseen-route test")
    ap.add_argument("--out", default=".")
    args = ap.parse_args()
    t0 = time.time()
    df, off = load(args.tickets, args.nrows)
    print(f"loaded {len(df):,} tickets, {df.date.nunique()} days ({df.date.min().date()} .. {df.date.max().date()}), "
          f"{df.route.nunique():,} routes; holiday-like weekdays treated as weekend: {[d.date().isoformat() for d in off] or 'none'}")
    assert df.day.max() >= 25, "need data through the end of the month for the 22-31 test window"
    results = [run(df, args)]
    if args.unseen:
        results.append(run(df, args, unseen=True))
    res = pd.concat(results, ignore_index=True)
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    res.to_csv(out / "compare_results.csv", index=False)
    md = report(res, args)
    (out / "compare_report.md").write_text(md)
    print("\n" + md)
    print(f"\nsaved {out / 'compare_results.csv'} and {out / 'compare_report.md'}   (total {time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
