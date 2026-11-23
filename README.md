# CrowdWise Delhi - crowd-aware bus journey planner

Transport Stack Hackathon 2026 (Delhi) - Problem 2, Phase 1.
A pipeline that turns **2.56 million bus e-tickets + the static GTFS timetable** into a crowd estimate for every **route, stretch, hour and day type**, a **journey planner** that shows that crowding next to every option, a **REST API** for the frontend, and a **machine-learning layer** with a strict time-based test.

> **Status:** everything below was run on the real October 2026 data. Numbers in this file come from those runs (`outputs/*.json`).

**Frontend (live demo):** https://crowdwise-delhi.ai.studio/ - source code: https://github.com/sujitnayak-web/CrowdWise-Delhi

## Live API (Google Cloud)
- Base URL: https://delhi-crowd-hackathon-1026044669617.asia-south1.run.app
- Interactive docs: https://delhi-crowd-hackathon-1026044669617.asia-south1.run.app/docs
- Health check: https://delhi-crowd-hackathon-1026044669617.asia-south1.run.app/api/health
- Example: `/api/plan?origin=Anand Vihar&destination=Connaught Place&time=18:30`

Deployed from the `Dockerfile` in this repository (FastAPI app `planner.app:app`). The first request after a quiet period can be slower while the service starts and loads the crowd table, so deploy Cloud Run with **`--min-instances=1`** (or ping `/api/health` on a schedule). CORS is open to all origins.

Run locally: `uvicorn planner.app:app --host 0.0.0.0 --port 8000`. The deployed entry point is `planner/app.py` on Google Cloud Run (the Dockerfile in this repo).
## Results at a glance
| What | Result |
|---|---|
| Tickets used | 2,559,899 in the file; 89.5% (2,290,902) usable after stop matching. **48.5% have no vehicle number and are all kept.** |
| Stop-name matching | 87.5% of name uses matched to a stop on the right route (exact 69.5%, partial 9.2%, fuzzy 8.8%; 89.2% including 1.7% no-space matches) |
| Crowd table | 1,770,724 hourly rows (route x stretch x hour x day type), plus 627,324 time-band rows |
| Temporal holdout (build from 1-21 Oct, test on unseen 22-31 Oct) | **83.5% tier agreement**, error 7.4 people; route-average baseline 73.9% / 12.6; city-average baseline 68.4% / 19.1 |
| Reliability (two independent halves of the month) | rank correlation **0.935** (0.960 where each half has 30+ tickets) |
| Model comparison (unseen days, cells with 10+ test tickets) | shrinkage estimate **R2 0.79** vs best ML 0.66 (Gradient Boosting); on unseen routes 0.74 vs 0.60. **Shrinkage wins, so it is what the API serves.** See "What the validation covers" |
| API speed | `/api/plan` about 0.1 s |

## How the crowd estimate works (one paragraph)
Each ticket says where a passenger boarded and left, so we spread it over the stretches it travelled (shifting the time forward with the timetable's travel times). Dividing by the **buses scheduled** on that stretch gives "ticketed riders per bus". Because the file holds only **mobile e-tickets (about 3-4% of riders)** and no pass holders, we scale it with a **configurable calibration layer** (`config.py`, base factor **42.9** = 1.5 pass-holder multiplier / 0.035 e-ticket capture rate, i.e. an assumed 3.5% of riders appear in the file and pass holders add 1.5x; low/high scenarios 20.0 / 66.7) and compare it with the bus's seats and capacity (AC / non-AC) to get **seats_available / standing_room / crowded**. Thin cells lean on their route-hour or route-band average and carry a **confidence** flag. For cells with under 10 tickets the API serves that same shrinkage estimate (`prediction_source = route_average`); the machine-learning fallback is **switched off** because it did not beat shrinkage (see below).

## Folder map
```
run_all.py            ONE command to rebuild everything from the raw files
config.py             every assumption and setting (read this first)
notebooks/            01 load+explore -> 02 GTFS+stop matching -> 03 crowd index -> 04 validation -> 05/06/07 ML lessons
scripts/07_ml_models.py   strict temporal ML split (the sparse-cell ML fallback is disabled: enabled = False)
fix_served_table.py   rebuilds outputs/crowd_table_served.parquet from the shrinkage table (no ML)
src/                  readable pandas code used by the notebooks and the API
planner/app.py        FastAPI REST API (CORS open)
tests/                28 tests (unit, API, served-table checks)
outputs/              results: figures, JSON metrics, crowd tables (Parquet), saved models
docs/                 TECHNICAL_NOTE, PROJECT_REPORT, API_CONTRACT, MODEL_COMPARISON
data/raw/             put tickets.csv and gtfs/ here (not in git)
```

## Get the data (not included: too large)
1. **Tickets** - `October-Delhi.csv.zip` from the hackathon (link in the problem statement) -> unzip and save as `data/raw/tickets.csv` (about 290 MB, 2,559,899 rows).
2. **Static GTFS** - request "Delhi Buses: GTFS Static Data - DTC / DoT" on https://delhi.transportstack.in -> unzip into `data/raw/gtfs/` (needs `stops.txt routes.txt trips.txt stop_times.txt`).

## Setup (Windows / macOS / Linux, Python 3.10-3.12)
```bash
conda create -n crowd python=3.12 -y && conda activate crowd      # or any virtualenv
pip install -r requirements.txt
copy .env.example .env                                           # (cp on macOS/Linux) only needed for MySQL
```
Storage is a **local SQLite file by default (zero setup)**. To use MySQL instead, put your details in `.env` and set `USE_MYSQL=1`.

## Run
```bash
python run_all.py --check        # are the input files in place?
python run_all.py                # everything: about 15-20 min, needs ~4 GB free RAM (8 GB comfortable)
python run_all.py --quick        # core only (notebooks 01-04 + ML): the crowd table, validation and the API data
uvicorn planner.app:app --host 0.0.0.0 --port 8000     # start the API  ->  http://localhost:8000/api/health
python -m pytest -q tests        # 28 tests
python fix_served_table.py       # only if you re-run scripts/07_ml_models.py: rebuild the served table from the shrinkage table
```
Or open `notebooks/` in Jupyter and run them in order - each one explains its step in plain English. The finished crowd tables are already in `outputs/`, so **the API starts immediately without re-running the pipeline.**

## API (details and JSON examples in `docs/API_CONTRACT.md`)
`/api/health` `/api/stops?q=` `/api/plan?origin=&destination=&time=HH:MM&day_type=&preference=` `/api/routes` `/api/routes/summary?day_type=&hour=` `/api/routes/{id}/crowd` `/api/operator/hotspots` (default `min_confidence=medium`, ranked by uncapped load) `/api/operator/network-profile` `/api/validation/summary` `/api/ml/insights`

## What the validation covers
Headline accuracy is measured on cells (route x weekday/weekend x hour) with **10+ test tickets**, on **ticket volume per day (log scale)**, with a strict time split (features 8-21 Oct, target 22-31 Oct) and a second test on routes held out of training. Source: `outputs/model_comparison/compare_results.csv`, exposed in `/api/validation/summary` under `headline_accuracy`.

| Test | Shrinkage (served) | Own-history baseline | Best ML (R2) | Global mean |
|---|---|---|---|---|
| R2, unseen days | **0.790** | 0.713 | 0.662 (Gradient Boosting) | -4.63 |
| R2, unseen routes | **0.743** | 0.662 | 0.605 (Gradient Boosting) | -4.48 |
| Tier accuracy / macro-F1, unseen days | 0.793 / 0.613 | 0.775 / 0.592 | 0.838 / 0.608 (SVM) | 0.018 / 0.011 |
| Tier accuracy / macro-F1, unseen routes | 0.776 / 0.605 | 0.758 / 0.583 | 0.833 / 0.599 (SVM) | 0.019 / 0.012 |

**This validates ticket volume, not crowding.** The crowd tier also depends on assumptions that nobody has validated: bus capacity (AC 33/60, non-AC 36/70) and the scale factor (42.9). The sensitivity test shows how far the tiers move if the scale is wrong. Older stretch-level numbers in `docs/TECHNICAL_NOTE.md` section 6 (target = load ratio, sparse-cell test) measure a different thing on a biased subset and must not be compared with the table above.

## Assumptions and limits (full list in `docs/TECHNICAL_NOTE.md`)
- The tickets are a **sample** of riders, so crowd levels depend on the calibration assumptions; we report a sensitivity test (tiers stay the same for about 92.6% / 89.2% of cells if the scale is wrong in either direction).
- The GTFS has one calendar for all 7 days, so weekend supply equals weekday supply.
- Bus size is not in the data (only AC / non-AC); capacities in `config.py` are assumptions.
- About 6.1% of name uses could not be matched and 8.4% of usable tickets have an assumed end stop.
- Quiet-looking cells are mostly **estimates** (see `prediction_source` in the API): observed tickets (10+) back 29.9% of stretch-hours; the other 70.1% use the shrinkage / route-average estimate (low confidence). Operator views default to medium+ confidence.
- Displayed load is capped at 1.5x crush capacity; hotspots are ranked by the uncapped `load_ratio_raw` so the top of the list is not a wall of ties.

## Credits
Built by the team with the help of AI tools: **Claude (Anthropic)** - pipeline, validation, ML and API code and documentation; **Gemini** and **Google AI Studio** - the frontend prototype and early backend experiments (its simulated data is NOT used anywhere in this project). Open-source libraries: pandas, NumPy, SciPy, scikit-learn, matplotlib, seaborn, RapidFuzz, SQLAlchemy, FastAPI, Uvicorn, PyArrow, Jupyter. Data: Transport Stack / IIIT Delhi (ONDC e-ticketing, DTC GTFS).


## Model versions
- The main project (repository root) is the V4 pipeline: hourly crowd table, REST API, ML layer with a strict time-based test, validation and documentation.
- An earlier V2 build was archived outside this repository; this repository contains only the V4 pipeline.
- `docs/MODEL_COMPARISON.md` and `scripts/compare_v2_vs_v4.py` compare the modelling approaches of both builds on identical data. Short version: they are close, and a simple shrinkage estimate beats both at route-hour level, so the shrinkage estimate is what is served, including for thin cells.
- Deployment: `Dockerfile` + `requirements-api.txt` (API only). `pytest.ini` limits tests to the main project.