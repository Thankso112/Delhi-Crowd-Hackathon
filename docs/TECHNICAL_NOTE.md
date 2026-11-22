# Technical note - method, assumptions, validation, limits

Transport Stack Hackathon 2026 (Delhi), Problem 2. All numbers are from the real run on October 2026 data.

## 1. Data and what we found in it
| Fact | Value |
|---|---|
| Tickets | 2,559,899 over 31 days, 2,259 route-directions, 6,809 vehicles |
| Vehicle number missing | **48.5%** (stored as the text `NULL`). Organizers: do not drop them. We do not. |
| Route names | carry the direction (`8UP`, `8ADOWN`); the GTFS has one pattern per direction (2,574 route-directions, 6,825 stops) |
| Who is in the file | mobile e-tickets only (ONDC), about 3-4% of ridership, no pass holders |
| Holiday-like days | 2026-10-02, 2026-10-20 (a weekday selling under 60% of a normal weekday) - treated like weekend days |
| GTFS calendar | one service for all 7 days, so weekend supply = weekday supply (a stated limitation) |

**Finding that shaped the design:** rebuilding bus trips from tickets does not work on this data. Grouping tickets by vehicle gave 600,380 "trips" with a **median of 1 ticket** each. The file is a thin sample, so we do not reconstruct trips (notebook 03, section 3).

## 2. Method
1. **Stop matching** (`src/gtfs.py`): names are normalised (case, punctuation, Stn/ISBT/Mkt...), then matched *inside the ticket's own route first*: exact or alias (composite GTFS names such as "Laxmi Nagar Metro Station / Laxmi Nagar" are split on "/"), fuzzy, partial ("Mahipal Pur" in "Mahipal Pur Village"), no-space. Result: exact 69.5%, partial 9.2%, fuzzy 8.8%, no-space 1.7%; off-route 2.9% (unusable); unmatched 6.1%; route not in GTFS 1.8%. Unmatched names are in `outputs/02_unmatched_names.csv`.
2. **Locate each ticket** (`src/trips.py`): boarding stop `b` and alighting stop `a` on its route. Missing or unmatched end stop (8.4% of usable tickets) -> the route's typical ride length. 89.5% of tickets are usable.
3. **Demand** (`src/crowd.py`): a ticket is on board stretches `b ... a-1`; the time at each stretch is shifted forward by the timetable's travel time, so a long ride is counted in the right hour.
4. **Supply**: scheduled buses per stretch and hour, from GTFS trip start times plus travel times.
5. **Index** = ticketed riders / (days x scheduled buses). A scheduled stretch with no tickets correctly gets 0.
6. **Fallback chain and confidence:** `stretch-hour -> route-hour -> route-band -> city`. A thin cell is blended with its fallback (shrinkage, K = 10 tickets). Confidence: 30+ tickets high, 10+ medium, else low; one step lower if fewer than 2 buses are scheduled in the band.
7. **Calibration** (`config.py`): people on board = index x scale. Scale = pass-holder multiplier / e-ticket capture rate = base 1.5 / 0.035 = 42.9 (low 20.0, high 66.7). Capacity: AC 33 seats / 60 maximum, non-AC 36 / 70 (assumptions; bus size is not in the data). Tiers: up to the seats = `seats_available`; up to 75% of maximum = `standing_room`; above = `crowded`. Loads are capped at 1.5x capacity because on some routes the GTFS lists fewer buses than really run, which inflates tickets per bus (the raw value is kept as `est_load_raw`).
8. **Planner** (`src/planner.py`): direct and one-transfer options (KD-tree, 500 m walk to the first/last stop, 250 m between stops), real clock times, crowd looked up stretch by stretch at the hour the bus passes, ranking by `fastest / balanced / comfortable`, and **departure shifts** (+15 / +30 min) showing whether waiting reduces crowding.

## 3. Validation (what we can and cannot show)
There is **no ground truth** for on-board counts in this data, so we test reliability, robustness and plausibility - and say so.

**Temporal holdout** - table built from 1-21 Oct only, tested on the unseen 22-31 Oct (cells with 10+ tickets in the unseen period, 172,773 cells):
| Predictor | Tier agreement | Error (people on board) | Rank correlation |
|---|---|---|---|
| City baseline (band average) | 68.4% | 19.1 | 0.186 |
| Route baseline (route x band) | 73.9% | 12.6 | 0.697 |
| **Our model (stretch, shrunk)** | **83.5%** | **7.4** | **0.875** |

**Reliability** - two independent halves of the month: rank correlation 0.935 (odd vs even days), 0.960 where each half has 30+ tickets, 0.911 (first vs second half); the same level (Quiet/Moderate/Busy) in both halves 85.6% of the time. Shrinkage raises reliability from 0.894 (none) to 0.935 (K = 10). Dropping tickets with an assumed end stop changes the ranking very little (0.991).

**Sensitivity to the calibration** (tier shares seats / standing / crowded, %): low scale 97.9/1.1/1.0; base 91.6/3.5/4.9; high 84.4/5.7/10.0. 92.6% of cells keep their tier under the low scale and 89.2% under the high scale. The *ranking* of stretches never changes with the scale - only where the tier boundaries fall. Trust the ordering and the peaks; treat absolute "people on board" as an estimate with a range.

**Organizer curve check** - ticketed passengers per hour on an average day:
| Day type | Hour | Organizer | Ours | Difference |
|---|---|---|---|---|
| weekday | 9:00 | 13,000 | 14,327 | +10.2% |
| weekday | 18:00 | 8,500 | 9,902 | +16.5% |
| weekend | 9:00 | 8,000 | 7,971 | -0.4% |
| weekend | 18:00 | 4,500 | 5,168 | +14.8% |

Figures: `outputs/figures/hourly_pattern.png`, `busiest_corridors.png`, `stability.png`, `temporal_holdout.png`, `sensitivity.png`.

## 4. Where the estimates are least reliable
- Stretch-hours with few tickets (most of the table): see `confidence` and `prediction_source` on every API segment.
- Routes with few scheduled buses or where the GTFS under-counts buses (loads capped).
- Weekends (GTFS has no weekend timetable) and the unexplained quiet Sunday 18 Oct.
- Stop matching: 6.1% unmatched; partial matches are plausible but not proven correct (audit table in notebook 02).
- Free-pass and cash riders are invisible; if they behave differently from e-ticket users some routes are mis-ranked.
- Bus size (12 m vs 9 m) is unknown; capacity is an AC / non-AC assumption.

## 5. Pass holders, early / late alighting
Pass holders are covered only through the multiplier in the calibration layer (an assumption, with a sensitivity test). The ticket's planned end stop is used as the alighting stop; when it is missing we assume the route's typical ride length.

## 6. Machine-learning layer (`scripts/07_ml_models.py`)
**Strict time split:** features from 1-14 Oct (weeks 1-2), training target 15-21 Oct (week 3), test on the unseen 22-31 Oct. Features: time, position on the route, distance to the centre, bus frequency, AC, plus what weeks 1-2 said (route and route-hour averages, the cell's own estimate and ticket count). Winsorising at the 1st/99th percentile and `StandardScaler` are fitted on training rows only, inside one Pipeline.
Train rows 149,024, test rows 245,383 (29,035 with under 10 tickets in weeks 1-2).

**Regression on `load_ratio`** (people on board / capacity; unseen days):
| Model | MAE | RMSE | R2 | MAE on sparse cells |
|---|---|---|---|---|
| OLS (linear regression) | 0.190 | 0.243 | 0.711 | 0.231 |
| Ridge | 0.190 | 0.243 | 0.711 | 0.231 |
| Lasso | 0.191 | 0.244 | 0.708 | 0.233 |
| Elastic Net | 0.191 | 0.244 | 0.710 | 0.232 |
| Gradient Boosting | 0.174 | 0.233 | 0.736 | 0.201 |
| BASELINE route x hour average (weeks 1-2) | 0.293 | 0.406 | 0.197 | 0.452 |
| BASELINE weeks 1-2 shrinkage estimate | 0.210 | 0.313 | 0.522 | 0.451 |

**Classification into tiers** (KNN with k chosen on a validation split, SVM with a 12,000-row cap):
| Model | Accuracy | Macro-F1 |
|---|---|---|
| KNN (k=15, chosen on validation) | 0.703 | 0.578 |
| SVM (RBF, class_weight=balanced, 12k-row cap) | 0.696 | 0.646 |
| BASELINE tier from weeks 1-2 shrinkage estimate | 0.691 | 0.609 |
| BASELINE tier from route x hour average | 0.595 | 0.515 |

Most important features (Ridge, normalised): own_A_idx_ratio (0.36), buses_per_hour (0.27), own_A_tix (0.13), is_weekend (0.07). Features Lasso set to zero: hour, is_pm_peak, is_up, pos, pos_frac, towards_centre, route_len_km, route_A_idx_ratio.

**Fallback: DISABLED.** An ML fallback for stretch-hours with fewer than 10 tickets was built and then switched off (`enabled = False` in `scripts/07_ml_models.py`). It was trained on busy cells (10+ tickets) and, applied to the 65% of cells with fewer tickets, raised their median load from 3.6 to 78 people, so 57% of all stretch-hours came out 'crowded'. The route-hour comparison (`outputs/model_comparison/`) shows the shrinkage estimate beats every ML model (R2 0.79 vs 0.66). The API therefore serves the shrinkage table: `prediction_source` is `observed_tickets` (10+ tickets, 29.9%) or `route_average` (70.1%). The table above is a stretch-level test on a selected subset and is not the headline accuracy.

**Caveats (important):**
- The 'sparse cell' test only includes cells that later had 10+ tickets (we need a reliable answer to score against). Such cells were BUSIER than they looked in weeks 1-2, which favours any model that can infer 'this place and hour is busy' from location and time. The advantage over the baselines on sparse cells is therefore real but overstated; cells that stay sparse cannot be scored at all.
- The fallback is applied with features built from the whole month (not only weeks 1-2), a slightly different window from training.
- The target is itself an estimate built from a SAMPLE of riders (mobile e-tickets) scaled by an assumed factor; ML learns to predict that estimate, not a head-count.

Plain-English teaching versions of these models (random split vs unseen-routes split, cross-validation, GridSearchCV, K-Means, PCA) are in notebooks 05-07.

## 7. Assumptions list (all in `config.py`)
e-ticket capture rate 3.5% (low 5%, high 3%); pass-holder multiplier 1.5 (1.0 / 2.0); capacities AC 33/60 and non-AC 36/70; standing limit 75% of maximum; load cap 1.5x; shrinkage K = 10; confidence thresholds 10 and 30 tickets; minimum 2 scheduled trips per band; holiday rule 60% of a normal weekday; walking radii 500 m / 250 m, speed 1.25 m/s; crowd penalty for "comfortable" ranking 0 / 5 / 15 min.

## 8. Appendix - ML concepts used
- **Train / test split** - Hide part of the data while the model learns, then score it on the hidden part, so we test understanding and not memory. *Example: A student practises on past papers and is judged on a new paper.*
- **Temporal split** - Train on the past and test on the future, never the other way round, so no future information leaks into training. *Example: Predict next week's bus crowding from the previous three weeks only.*
- **Feature scaling (StandardScaler)** - Rescale every column to a similar range so no column dominates only because its numbers are bigger. *Example: Distance in km and hour of day are put on the same scale before KNN measures 'closeness'.*
- **Winsorizing** - Cut extreme values back to the 1st and 99th percentile of the training data so a few huge numbers cannot distort the model. *Example: One day with a ticket-system glitch is capped instead of ruining the average.*
- **Linear Regression (OLS)** - Fits the best straight line (a weighted sum of features) through the data to predict a number. *Example: Predicting house price from size, bedrooms and age.*
- **Ridge and Lasso (regularisation)** - Linear regression with a brake: Ridge shrinks all weights, Lasso can shrink some to exactly zero, which also selects features. *Example: A teacher who stops you explaining a result with too many reasons.*
- **Elastic Net** - A mix of Ridge and Lasso, useful when several features overlap. *Example: Latitude, longitude and distance to the centre all describe 'where', so their weights are shared sensibly.*
- **KNN (K-Nearest Neighbours)** - To predict a new case, look at the K most similar known cases and let them vote (or average them). *Example: Judging a restaurant by the ratings of the 10 most similar ones nearby.*
- **SVM (Support Vector Machine)** - Draws the boundary between classes with the widest possible safety margin; with a kernel the boundary can curve. *Example: Separating spam from normal mail with the cleanest dividing line.*
- **Decision Tree** - A flow-chart of yes/no questions that ends in an answer; easy to read but can memorise noise if too deep. *Example: A doctor's triage chart.*
- **Random Forest** - Many different trees vote and their answers are averaged, which is steadier than any single tree. *Example: Asking 200 people to guess the sweets in a jar and taking the average.*
- **Gradient Boosting** - Builds trees one after another, each fixing the mistakes of the previous ones. *Example: A student who redoes only the questions they got wrong, round after round.*
- **Logistic Regression** - A linear model that outputs the probability of each class instead of a number. *Example: A bank estimating the chance a loan will be repaid.*
- **Naive Bayes** - Classifies using probabilities and pretends the features are independent, which makes it very fast. *Example: Spam filters multiply the probabilities of the words in a mail.*
- **K-Means clustering** - With no labels, groups similar items by repeatedly moving K group centres to the middle of their members. *Example: Grouping bus routes into 'morning commuter' and 'all-day' types.*
- **PCA (Principal Component Analysis)** - Squeezes many columns into a few new ones that keep most of the information, so data can be drawn on a 2-D plot. *Example: Plotting routes described by six numbers on a single flat map.*
- **Cross-validation** - Repeats the train/test experiment several times on different hidden parts and averages the scores, so one lucky split cannot fool us. *Example: Five mock exams instead of one.*
- **GridSearchCV (hyper-parameter tuning)** - Tries every combination of a model's settings with cross-validation and keeps the best. *Example: Trying several oven temperatures and times to find the best cake.*
- **Overfitting** - The model memorises the training data and does worse on new data; shown by a big gap between train and test scores. *Example: Learning last year's answers by heart instead of the subject.*
- **MAE, RMSE and R2** - MAE is the average size of the error, RMSE punishes big errors more, R2 is the share of variation explained (1 perfect, 0 no better than the average). *Example: An exam score shows how far off you were on average.*
- **Accuracy, macro-F1 and confusion matrix** - Accuracy is the share of correct labels; macro-F1 treats every class equally, even rare ones; the confusion matrix shows which classes get mixed up. *Example: A spam filter that is 95% accurate but never catches a rare scam would score poorly on macro-F1.*
