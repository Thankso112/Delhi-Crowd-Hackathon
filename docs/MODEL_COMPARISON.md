# V2 vs V4 modelling approaches - same data, same split, same metrics

This repository contains two earlier builds of the crowd model. Their own saved scores were not comparable (different targets,
test windows, filters and class balance), so `scripts/compare_v2_vs_v4.py` rebuilds ONE dataset from the raw October tickets and scores
the model families of both builds on identical rows. Raw output: `outputs/model_comparison/compare_report.md` and `compare_results.csv`.

**Setup.** Cell = route x weekday/weekend x hour. Target = tickets per day in the test window (log1p scale).
Train: features from 1-14 Oct predict 15-21 Oct. Test: features from 8-21 Oct predict 22-31 Oct (never seen in training).
Also tested on routes held out from training. Same features for every model.

**Results (cells with at least 10 test tickets).**

| Test | Best V2-style model | Best V4-style model | Shrinkage baseline (no ML) |
|---|---|---|---|
| R2, unseen days | 0.662 (Gradient Boosting) | 0.626 (Gradient Boosting) | **0.790** |
| R2, unseen routes | 0.605 | 0.584 | **0.743** |
| Tier macro-F1, unseen days | 0.588 | 0.608 (SVM) | 0.613 |
| Tier macro-F1, unseen routes | 0.579 | 0.599 (SVM) | 0.605 |

**Reading.**
- The two model families are close: V2-style models lead slightly on regression, V4-style (SVM) slightly on classification. The gaps are small and no confidence intervals were computed.
- At route-hour level the simple shrinkage estimate (own history blended with the route-hour average) beat every ML model. ML therefore is not the primary estimate.
- This is why the production estimate is the shrinkage model, with ML used only as a fallback for stretches with very little ticket history
  (see `docs/TECHNICAL_NOTE.md`, section 6, for the stretch-level test and its caveats).
- Limits of this comparison: route-hour level only (no stop-to-stop stretches, no GTFS features), and it tests the modelling recipes, not the saved model files.