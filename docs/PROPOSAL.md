# Proposal — Which bus has room? (Problem 2, crowdedness-aware journey planning)

**Problem.** Delhi commuters see a route and a time, not how full the bus will be. Overcrowding pushes people onto worse options and hides overloaded corridors from planners.

**Solution.** A bus journey planner for all of Delhi, built on static GTFS, where each option shows a crowd level (Seats available / Standing room / Crowded) and a confidence flag. Levels come from a model of on-board load estimated from one month of ticket data: tickets are linked to routes, directions and stops, grouped into inferred trips, and turned into load along each route by time of day and day type.

**What is novel.** (1) A flow-per-scheduled-trip method that works although half the tickets lack vehicle numbers and none carries a trip or stop ID. (2) Honest uncertainty: confidence flags, shrinkage for thin data, a stated coverage calibration with a sensitivity analysis, and a time-based hold-out compared against regression and gradient boosting. (3) A "faster vs more comfortable" ranking that trades minutes for crowding.

**Feasibility.** Runs on a laptop in minutes with pandas and Parquet; full pipeline re-runnable from raw data with one script; working prototype with map UI.

**Impact.** Commuters can shift to a slightly later or different bus with room; operators get a city-wide crowd table and an overloaded-routes view to guide frequency and capacity decisions.

**Limits.** Typical, not real-time; one month of data; ticketed riders only; capacity assumed. These are stated in the technical note and visible in the product.

**Team.** [TEAM: names and roles]
