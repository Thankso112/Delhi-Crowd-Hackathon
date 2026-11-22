# Technical note — crowding estimate for Delhi buses (real October 2026 data)

## 1. Problem and approach
Commuters choose between buses without knowing how full they will be. We estimate typical on-board crowding by route, stretch, time of day and day type from the October 2026 ticket file, and show it as a level plus a confidence flag in a bus journey planner built on static GTFS (buses only, all of Delhi).

## 2. What the real data looks like (this drove the method)
| Fact (from `docs/data_profile.md`, `outputs/*`) | Consequence |
|---|---|
| 2,559,899 tickets, 2,753,606 passengers, 1 Oct to 31 Oct, 2,259 route names | Large enough for route-level statistics, thin per stretch |
| **49% of tickets have `vehicle_number = NULL`** (1,242,167 rows) | Trips cannot be rebuilt from vehicles, so the model does not use trips |
| About 1 ticketed passenger per scheduled trip per day (about 100k tickets per weekday vs about 80k scheduled trips) | The file is a **thin sample** of real ridership; counts must be scaled to riders (calibration, section 4) |
| Only 8 tickets have amount = 0; one `ticket_type_id` | No free-ride tickets appear, so free-fare and pass travellers are probably missing: another reason to scale up |
| Route names carry direction (`8UP`, `8ADOWN`); GTFS has the same names; `direction_id` is empty | Direction comes from the route name; no direction guessing |
| GTFS stop names are often composite (`Laxmi Nagar Metro Station / Laxmi Nagar`); tickets use one simple form | Matching uses each `/` part as an alias |
| 2 Oct and 20 Oct (weekdays) have less than half the usual volume | Flagged as outliers and left out of the model |
| GTFS: single all-days calendar, no `frequencies.txt`, 2,574 routes, 6,825 stops | Weekday and weekend have the same schedule; trips per hour come from `stop_times` |

## 3. Linking tickets to the network (`crowd/text.py`, `matching.py`, `trips.py`)
Names are normalised (lowercase, punctuation, abbreviations such as Stn, Sec, X-ing, initials like S.J.). Matching, in tiers, against the stops of the same route: exact alias, RapidFuzz token-sort ≥ 86, token-set ≥ 95 (ticket name contained in a longer GTFS name), no-space match ≥ 92 (Azad Pur vs Azadpur), then any stop in Delhi at ≥ 93 (flagged off-route). **Result: 93.5% of name occurrences matched** (70.9% exact, 8.8% fuzzy, 9.7% contained, 1.0% no-space, 3.0% off-route; 4.8% unmatched and 1.8% on routes absent from GTFS). A ticket needs a matched boarding stop; a missing or unmatched alighting stop is imputed as boarding + the route's median ride length (7.5% of kept tickets). **2,323,975 of 2,559,899 tickets (90.8%) are usable.**

## 4. Crowd model: flow per scheduled trip (`crowd/flow.py`, `model.py`)
1. For each route, day type (weekday/weekend) and time band (night, early, am_peak, midday, pm_peak, evening, by boarding time), put +pax at the boarding position and −pax at the alighting position and take a running sum along the route (`np.cumsum`). This gives the ticketed passengers whose ride covers each stretch.
2. Divide by (number of days in the cell) × (scheduled trips in that band from GTFS). Result `tix_load` = average ticketed passengers on board per scheduled trip on that stretch. Assumes every scheduled trip runs.
3. **Shrinkage** for thin cells: `est = (n·x + k·prior)/(n + k)`, k = 10 tickets, prior = the route's average for that band and day type, else the city-wide band average.
4. **Coverage calibration** (an assumption, in `config.py`): ticketed counts are scaled to estimated riders with a factor of **24.7** (riders per ticketed passenger), chosen so that the 90th percentile of well-observed weekday-peak stretch loads equals the assumed standing limit (75% of crush capacity). Effect: the busiest ~10% of weekday-peak route-stretches read as crowded. The **ranking** of routes and stretches does not depend on this factor; only the labels do (`outputs/sensitivity.csv`: the crowded share moves from 0.4% to 9.1% of all cells as the factor goes from 0.5× to 2×).
5. **Levels:** seats if load ≤ seats, standing if ≤ 0.75 × crush, else crowded. Assumed capacity: AC 33 seats / 60 crush, non-AC 36 / 70. [TEAM: replace with a cited source if you find one.]
6. **Display cap:** shown load never exceeds 1.3 × crush (some routes carry more tickets than their scheduled trips imply, so GTFS probably under-schedules them).
7. **Confidence:** tickets covering the stretch-cell: high ≥ 100, medium ≥ 20, else low; lowered one step where fewer than 2 trips are scheduled in the band. **62% of cells are low confidence**, a direct consequence of the thin ticket sample; the UI shows the flag on every option.
Output: 547,587 stretch-cells over 1,930 routes (`outputs/crowd_table.csv.gz`; route-level summary in `outputs/crowd_route_level.csv`). Overall level shares: 95.3% seats, 2.2% standing, 2.5% crowded; the weekday morning peak has the most crowded cells (5.9%).

## 5. Planner (`planner/engine.py`)
Walk links via KD-tree (500 m at the ends, 250 m for transfers); direct and one-transfer options; ride time from the GTFS representative trip; wait = half the headway (cap 20 min); transfer penalty 5 min. Each option takes the worst level and lowest confidence of its legs for the chosen time band and day type. "More comfortable" adds a penalty (seats 0, standing 5, crowded 15 min; halved at low confidence). About 1.2 s per query on the full network.

## 6. Validation (`crowd/validate.py`, `outputs/metrics.json`, `outputs/holdout_scores.csv`)
Time-based hold-out with three 7-day windows (never a random split): features from week 2 predict week 3 for every route-stretch-band cell; trained models learn week 1 → week 2 first. Only week-3 cells with ≥ 10 tickets count as reliable truth (121,120 cells).

| Model | MAE | RMSE | R² | Spearman |
|---|---|---|---|---|
| **Shrinkage model (ours)** | **0.257** | **0.454** | **0.778** | 0.839 |
| Gradient boosting (scikit-learn) | 0.275 | 0.481 | 0.751 | **0.904** |
| Route-level average | 0.383 | 0.656 | 0.537 | 0.704 |
| Linear regression, route/band/position only (no own history) | 0.584 | 0.857 | 0.211 | 0.644 |
| City-wide average | 0.561 | 1.035 | −0.153 | 0.326 |

(units: ticketed passengers on board per trip). The shrinkage model cuts the error of the route-level baseline by 33%. Linear regression is the weakest learned model because crowding depends on interactions (stretch × hour × route) that an additive model cannot express; gradient boosting learns them and ranks cells best but is not more accurate in absolute terms. Week-to-week stability of the raw pattern: Spearman 0.92. Level agreement between predicted and actual 3-class labels: 89.2% (shrinkage), 87.3% (boosting). Weekday boardings peak at 9, 8 and 18 h.
**What this does and does not show.** The estimate is consistent, predictable from past weeks and follows commute peaks. It does **not** prove absolute levels, because no ground-truth crowding exists in the data; absolute labels rest on the stated capacity and calibration assumptions.

## 6b. ML suite and the fallback for thin stretches (`crowd/ml.py`, `/api/ml/insights`)
Same time-based hold-out (train week 1 → 2, test week 2 → 3, cells with ≥ 10 test tickets: 140,043 train / 121,120 test rows). All models share one feature set: own earlier load and ticket count, route average, city average, band, day type, position along the route, route length, scheduled trips, AC flag.

| Regressor | MAE | RMSE | R² |
|---|---|---|---|
| Linear Regression | 0.283 | 0.458 | 0.775 |
| Lasso (L1) | 0.282 | 0.456 | 0.776 |
| **Random Forest** | **0.248** | **0.437** | **0.794** |
| Gradient Boosting | 0.275 | 0.481 | 0.751 |

(These differ from the 0.21 linear-regression row in section 6, which had no access to a cell's own history.) Classifiers for the crowd level: Logistic Regression accuracy 0.871, macro-F1 0.596; Gradient Boosting accuracy 0.886, **macro-F1 0.674**. Confusion matrix (rows actual seats / standing / crowded; columns predicted): [[94774, 3614, 1371], [3622, 2717, 2972], [1224, 1069, 9757]]: crowded stretches are found well (recall 81%), standing is the hardest class. Permutation importance: own earlier load 81%, scheduled trips 11%, own ticket count 4%, route average 3%. Lasso zeroes position, relative position and route length. Strongest correlation: own load vs route average (r = 0.82).
**Fallback for thin stretches.** 61% of stretch-cells have fewer than 20 tickets. For these a Random Forest predicts the load instead of the route-average shrinkage. It is trained and judged on **all** cells, never only on cells that later turned out well observed: that filter keeps busy cells only and made the first version over-predict (it produced 16% "crowded" cells; we caught and removed it). On 398,005 thin test cells: Random Forest MAE 0.170 vs 0.215 for shrinkage (21% lower); mean prediction 0.251 vs actual 0.244 (shrinkage over-predicts at 0.308). The API labels these `ml_fallback`; stretches with ≥ 20 tickets are `observed_tickets`.

## 7. Where estimates are least reliable
Low-confidence cells (62%); routes with few tickets; routes scheduled only once or twice in a band; the ~5% of stop names still unmatched and routes absent from GTFS (1.8%); imputed alighting stops (7.5%); free-fare and pass travellers who do not appear in tickets; only the most common stop pattern per route is used; GTFS has one all-days calendar, so weekday and weekend schedules are identical; one month of data, no seasons or festivals.

## 8. Reproducibility
`python run_pipeline.py` recreates every table and figure from raw data in about two minutes; `pytest tests` runs the tests; notebooks `01`–`05` walk through each step. Synthetic data (`scripts/00_make_synthetic.py`) exists only for testing.
