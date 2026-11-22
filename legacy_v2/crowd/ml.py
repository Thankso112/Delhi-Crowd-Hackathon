"""ML suite behind /api/ml/insights and the ML fallback for thinly observed stretches.

Same time-based hold-out as crowd/validate.py: train on (week 1 -> week 2), test on (week 2 -> week 3). Never a random split.
4 regressors predict ticketed load per trip; 2 classifiers predict the crowd level (seats / standing / crowded)."""
import json
import numpy as np, pandas as pd
from sklearn.base import clone
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.inspection import permutation_importance
from sklearn.linear_model import Lasso, LinearRegression, LogisticRegression
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from crowd.text import config, level_of
from crowd.validate import HGB_FEATURES

LEVELS = ["seats", "standing", "crowded"]
API_LEVEL = {"seats": "seats_available", "standing": "standing_room", "crowded": "crowded"}

def _X(df):                       # models other than gradient boosting need a complete matrix: missing history -> 0
    return df[HGB_FEATURES].fillna(0).to_numpy(float)

def _scores(y, p):
    return dict(mae=round(float(mean_absolute_error(y, p)), 4), rmse=round(float(np.sqrt(mean_squared_error(y, p))), 4), r2=round(float(r2_score(y, p)), 4))

def build_suite(train, test, coverage, out_dir):
    cf = coverage["coverage_factor"]
    tr = train[train.nT >= config.MIN_TICKETS_TRUTH]; te = test[test.nT >= config.MIN_TICKETS_TRUTH]
    rf_idx = tr.sample(min(80_000, len(tr)), random_state=0).index
    regs = {
        "Linear Regression": make_pipeline(StandardScaler(), LinearRegression()),
        "Lasso (L1)": make_pipeline(StandardScaler(), Lasso(alpha=0.002, max_iter=5000)),
        "Random Forest": RandomForestRegressor(n_estimators=120, max_depth=14, min_samples_leaf=5, n_jobs=-1, random_state=0),
        "Gradient Boosting": HistGradientBoostingRegressor(max_iter=200, learning_rate=0.08, max_depth=6, random_state=0),
    }
    fitted, reg_rows, preds = {}, [], {}
    for name, m in regs.items():
        if name == "Gradient Boosting":
            m.fit(tr[HGB_FEATURES], tr.y, sample_weight=tr.nT); p = np.clip(m.predict(te[HGB_FEATURES]), 0, None)
        elif name == "Random Forest":
            m.fit(_X(tr.loc[rf_idx]), tr.loc[rf_idx].y); p = np.clip(m.predict(_X(te)), 0, None)
        else:
            m.fit(_X(tr), tr.y); p = np.clip(m.predict(_X(te)), 0, None)
        fitted[name], preds[name] = m, p; reg_rows.append(dict(name=name, **_scores(te.y, p)))
    # ---- classifiers: crowd level of the week-3 cell ----
    ytr = pd.Series(level_of(tr.y * cf, tr.is_ac), index=tr.index); yte = pd.Series(level_of(te.y * cf, te.is_ac), index=te.index)
    clfs = {"Logistic Regression": make_pipeline(StandardScaler(), LogisticRegression(max_iter=400)),
            "Gradient Boosting Classifier": HistGradientBoostingClassifier(max_iter=150, learning_rate=0.08, max_depth=6, random_state=0)}
    clf_rows, cms = [], {}
    for name, m in clfs.items():
        if name.startswith("Gradient"): m.fit(tr[HGB_FEATURES], ytr); p = m.predict(te[HGB_FEATURES])
        else: m.fit(_X(tr), ytr); p = m.predict(_X(te))
        clf_rows.append(dict(name=name, accuracy=round(float(accuracy_score(yte, p)), 4), macro_f1=round(float(f1_score(yte, p, average="macro", labels=LEVELS)), 4)))
        cms[name] = confusion_matrix(yte, p, labels=LEVELS).tolist()
    best_clf = max(clf_rows, key=lambda r: r["macro_f1"])["name"]
    # ---- interpretation ----
    sub = te.sample(min(5000, len(te)), random_state=1)
    pi = permutation_importance(fitted["Gradient Boosting"], sub[HGB_FEATURES], sub.y, n_repeats=3, random_state=0, scoring="neg_mean_absolute_error")
    w = np.clip(pi.importances_mean, 0, None); w = w / w.sum() if w.sum() > 0 else w
    importance = sorted([dict(feature=f, weight=round(float(x), 4)) for f, x in zip(HGB_FEATURES, w)], key=lambda d: -d["weight"])
    lasso_coef = fitted["Lasso (L1)"][-1].coef_; zeroed = [f for f, c in zip(HGB_FEATURES, lasso_coef) if abs(c) < 1e-9]
    corr = tr[HGB_FEATURES].fillna(0).corr(); pairs = []
    for i, a in enumerate(HGB_FEATURES):
        for b in HGB_FEATURES[i + 1:]:
            pairs.append(dict(feature_a=a, feature_b=b, pearson_r=round(float(corr.loc[a, b]), 4)))
    pairs = sorted(pairs, key=lambda d: -abs(d["pearson_r"]))[:6]
    # ---- which model should fill THIN cells? ----
    # Trained and judged on ALL cells, never filtered on the outcome: keeping only cells that ended up with >= 10 tickets would keep only
    # busy cells, teach the model busy-cell loads and make it over-predict for genuinely thin cells (selection bias).
    tra = train.sample(min(100_000, len(train)), random_state=0)
    fb = {"Random Forest": RandomForestRegressor(n_estimators=120, max_depth=14, min_samples_leaf=20, n_jobs=-1, random_state=0),
          "Gradient Boosting": HistGradientBoostingRegressor(max_iter=200, learning_rate=0.08, max_depth=6, min_samples_leaf=40, random_state=0)}
    fb["Random Forest"].fit(_X(tra), tra.y); fb["Gradient Boosting"].fit(tra[HGB_FEATURES], tra.y)
    thin_all = test[test.nF < config.CONF_TICKETS_MED]
    if len(thin_all) < 50: thin_all = test
    fp = {"Random Forest": np.clip(fb["Random Forest"].predict(_X(thin_all)), 0, None), "Gradient Boosting": np.clip(fb["Gradient Boosting"].predict(thin_all[HGB_FEATURES]), 0, None)}
    shrink_mae = float(mean_absolute_error(thin_all.y, thin_all.pred_model))
    cand = {k: float(mean_absolute_error(thin_all.y, v)) for k, v in fp.items()}
    best_ml = min(cand, key=cand.get); ml_wins = cand[best_ml] < shrink_mae
    bias = dict(mean_actual=round(float(thin_all.y.mean()), 4), mean_pred_shrinkage=round(float(thin_all.pred_model.mean()), 4), **{f"mean_pred_{k.lower().replace(' ', '_')}": round(float(v.mean()), 4) for k, v in fp.items()})
    insights = dict(
        split_method="Temporal hold-out: features from days 8-14 predict days 15-21; trained models first learn days 1-7 -> 8-14. No random split (it would leak the future).",
        preprocessing_summary=("Ticket stop names matched to GTFS stops (alias + fuzzy); load per stretch = ticketed passengers per scheduled trip (flow); cells need >= %d tickets in the test week to count as truth; "
                               "features: own earlier load (mF, nF), route average (rF), city average (gF), band, day type, position along the route, route length, scheduled trips, AC flag; "
                               "Lasso / Logistic Regression use standardised features, missing history filled with 0." % config.MIN_TICKETS_TRUTH),
        train_rows=int(len(tr)), test_rows=int(len(te)), active_fallback_model=best_ml if ml_wins else "Shrinkage to route average",
        fallback_stats=dict(total_segments=0, observed_segments=0, ml_fallback_segments=0, ml_fallback_pct=0.0),
        regression_models=reg_rows, classification_models=clf_rows,
        confusion_matrix=dict(labels=[API_LEVEL[l] for l in LEVELS], matrix=cms[best_clf], model=best_clf),
        feature_importance=importance, lasso_zeroed_features=zeroed, top_correlated_pairs=pairs,
        thin_cell_comparison=dict(n_thin_test_cells=int(len(thin_all)), mae_shrinkage=round(shrink_mae, 4), mae_by_model={k: round(v, 4) for k, v in cand.items()}, ml_beats_shrinkage=bool(ml_wins), bias_check=bias,
                                  note="Judged on all test cells with little history, not only cells that later turned out well observed (that filter would bias toward busy cells)."),
        concepts=[
            dict(term="Temporal hold-out", summary="Train on the past, test on a later week, as in real use.", example="Weeks 1-2 teach the model; week 3 is only used to score it."),
            dict(term="MAE / RMSE / R²", summary="MAE is the average miss; RMSE punishes big misses; R² is the share of variation explained (0 = no better than the average).", example="MAE 0.26 means we are off by about a quarter of a ticketed passenger per trip."),
            dict(term="Lasso (L1) regularisation", summary="Linear regression with a penalty that pushes useless feature weights to exactly zero.", example="Features listed under lasso_zeroed_features carry no extra signal for Lasso."),
            dict(term="Random forest vs gradient boosting", summary="Both are many decision trees; forests average independent trees, boosting adds trees that fix earlier errors.", example="Trees capture 'busy only at 6 pm on this stretch', which a straight line cannot."),
            dict(term="Macro-F1 and the confusion matrix", summary="Macro-F1 averages F1 over the three levels so the rare 'crowded' class counts equally; the matrix shows which levels get confused.", example="A 'standing' stretch predicted as 'seats' is a cell off the diagonal."),
            dict(term="Fallback for thin data", summary="Stretches with few tickets borrow strength from a model or from the route average, and are flagged with lower confidence.", example="prediction_source says observed_tickets, ml_fallback or route_average."),
        ])
    insights["_model"] = fb[best_ml]; insights["_ml_wins"] = bool(ml_wins)
    return insights

def apply_fallback(cells, model, ml_wins, cf):
    """Fill thin stretch-cells with the ML model (if it beats shrinkage on thin test cells), and label every cell's prediction source."""
    c = cells.copy()
    thin = (c.n_tickets < config.CONF_TICKETS_MED).to_numpy()
    c["load_raw"] = c.est_load * cf
    if ml_wins and thin.any():
        f = c[["route_n", "dir", "daytype", "band", "pos", "tix_load", "n_tickets", "trips_per_day", "n_stops", "is_ac"]].rename(columns={"tix_load": "mF", "n_tickets": "nF"})
        f["rF"] = f.groupby(["route_n", "dir", "daytype", "band"]).mF.transform("mean")
        f["gF"] = f.groupby(["daytype", "band"]).mF.transform("mean")
        f["band_c"] = f.band.map({b: i for i, b in enumerate(config.BANDS)}); f["day_c"] = (f.daytype == "weekend").astype(int)
        f["pos_frac"] = f.pos / (f.n_stops - 1).clip(lower=1); f["is_ac"] = f.is_ac.fillna(0)
        X = f.loc[thin, HGB_FEATURES]
        pred = np.clip(model.predict(X if isinstance(model, HistGradientBoostingRegressor) else X.fillna(0).to_numpy(float)), 0, None)   # same preparation as in training
        c.loc[thin, "est_load"] = pred; c.loc[thin, "load_raw"] = pred * cf
    crush = np.where(c.is_ac.fillna(0).astype(bool), config.CAPACITY["ac"]["crush"], config.CAPACITY["nonac"]["crush"])
    c["level"] = level_of(c.load_raw, c.is_ac.fillna(0)); c["load_adj"] = np.minimum(c.load_raw, config.LOAD_CAP_FACTOR * crush)
    c["prediction_source"] = np.where(thin, "ml_fallback" if ml_wins else "route_average", "observed_tickets")
    c["source"] = c.prediction_source
    return c

def fallback_stats(c):
    n = len(c); k = int((c.prediction_source == "ml_fallback").sum()); r = int((c.prediction_source == "route_average").sum())
    return dict(total_segments=n, observed_segments=int((c.prediction_source == "observed_tickets").sum()), ml_fallback_segments=k, route_average_segments=r, ml_fallback_pct=round(100 * k / n, 2))
