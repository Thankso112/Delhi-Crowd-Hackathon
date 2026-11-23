# Presentation guide - demo script and viva answers

## 3-minute demo video (matches the judging weights)
| Time | Show | Say |
|---|---|---|
| 0:00-0:20 | Problem | A packed bus is slow and hard to stand in; planners show time, not crowding. |
| 0:20-1:00 | Pipeline (`outputs/figures/03_route_heatmap.png`, README folder map) | 2.56 M e-tickets + GTFS -> crowd per route, stretch, hour. Half the tickets have no vehicle number; we keep them all. Tickets are a 3-4% sample, so there is a calibration layer with a sensitivity test. |
| 1:00-2:00 | Frontend planner, live API | Anand Vihar -> Connaught Place, 18:00 weekday: options with Seats/Standing/Crowded chips, confidence, "leave 15 min later". Then Nehru Place -> Kashmiri Gate 09:00. Operator view: most overloaded routes. |
| 2:00-2:40 | Validation (`temporal_holdout.png`, `hourly_pattern.png`) | Built from 1-21 Oct, tested on unseen 22-31 Oct: 83.5% tier agreement vs 73.9% route average and 68.4% city average. Peaks match the organizers' curve. |
| 2:40-3:00 | Limits | Sample of riders, assumed scale, no weekend timetable, bus size unknown, ML fallback caveat. |

## Numbers to remember
2,559,899 tickets - 48.5% no vehicle (all kept) - 87.5% names matched on route - 89.5% tickets usable - 1,770,724 hourly cells - scale 42.9 (low 20.0, high 66.7) - holdout 83.5% - split-half 0.935 - plan about 0.1 s.

## Likely questions and honest answers
1. **Why not rebuild bus trips?** We tried: 600,380 trips with a median of 1 ticket. The file is a sample, so per-bus counts are meaningless. We aggregate by route/stretch/hour instead.
2. **Why keep tickets without a vehicle number?** The organizers confirmed; they are about half the data and are missing evenly across routes and hours (notebook 01, section 6).
3. **Are these real head-counts?** No. Tickets are about 3-4% of riders. People on board = index x 42.9, an assumption we test (low/high scenarios).
4. **How sure are you of the scale?** Not sure - that is why tiers are tested under low and high scales (92.6% / 89.2% of cells keep their tier) and why the ranking of stretches does not depend on it.
5. **How do you know it works?** No ground truth exists. We show stability (two halves: 0.935), a temporal holdout against baselines, plausibility (peaks, weekday vs weekend), and robustness to assumptions.
6. **What is the temporal holdout?** Build from 1-21 Oct, compare with 22-31 Oct. Tier agreement 83.5% vs 73.9% (route average) and 68.4% (city average).
7. **Where is it least reliable?** Cells with few tickets (most of the table), weekends, routes with few scheduled buses, unmatched stop names.
8. **How do you handle thin data?** Shrinkage towards route-hour/route-band, confidence flags, and an ML fallback for cells with under 10 tickets.
9. **Why is the ML fallback believable?** It is tested on unseen days against baselines; but the sparse-cell test has a selection effect, which we state.
10. **Which ML models and why?** Linear/Ridge/Lasso/Elastic Net (simple, explainable), KNN and SVM (distance and margin methods), Gradient Boosting (best accuracy on tables). Strict temporal split to avoid leakage.
11. **What is overfitting?** Memorising training data; shown by a big train-test gap (notebook 05, KNN with K=1 and deep trees).
12. **How do pass holders enter?** Only through the multiplier in the calibration (1.5 base). Free travel is invisible in tickets.
13. **What about early or late alighting?** We use the ticket's end stop; if missing we assume the route's typical ride length (8.4% of usable tickets).
14. **Holidays?** A weekday selling under 60% of normal is treated like a weekend day (2026-10-02, 2026-10-20).
15. **Can judges rerun it?** `python run_all.py`; finished tables are shipped, so the API starts at once.
16. **Did you use the AI Studio backend?** No - its data was simulated. It is not used anywhere.
17. **What would you do next?** Validate against GPS/on-board counts, an alias table for unmatched names, several stop patterns per route, real-time data.
