# CrowdWise Delhi – Crowd-Aware Bus Journey Planner
 
**Transport Stack Hackathon 2026 (Delhi) – Problem 2, Phase 1**
 
Every route option shows whether you will get **seats / standing room / a crowded bus**, estimated from **2.56 million October 2026 bus e-tickets + the static DTC GTFS timetable**.
 
This repository is a monorepo:
 
| Folder | What it is | Stack |
|---|---|---|
| [`backend/`](backend/) | Data pipeline, crowd model, ML layer, validation, REST API | Python, pandas, scikit-learn, FastAPI |
| [`Frontend/`](Frontend/) | Web app: journey planner, crowd map, operator view, ML insights | React 19, TypeScript, Vite, Tailwind |
 
> **Status:** everything below was run on the real October 2026 data. Numbers come from `backend/outputs/*.json`.
 
## Live links
 
| | URL |
|---|---|
| Frontend demo | https://crowdwise-delhi.ai.studio/ |
| API base | https://delhi-crowd-hackathon-1026044669617.asia-south1.run.app |
| API docs (Swagger) | https://delhi-crowd-hackathon-1026044669617.asia-south1.run.app/docs |
| Health check | https://delhi-crowd-hackathon-1026044669617.asia-south1.run.app/api/health |
| Example query | `/api/plan?origin=Anand Vihar&destination=Connaught Place&time=18:30` |
 
The API is deployed on Google Cloud Run from `backend/Dockerfile` (FastAPI app `planner.app:app`). The first request after a quiet period can be slower while the crowd table loads, so deploy with `--min-instances=1` (or ping `/api/health` on a schedule). CORS is open to all origins.
 
## Results at a glance
 
| What | Result |
|---|---|
| Tickets used | 2,559,899 in the file; 89.5% (2,290,902) usable after stop matching. **48.5% have no vehicle number and are all kept.** |
| Stop-name matching | 87.5% of name uses matched to a stop on the right route (exact 69.5%, partial 9.2%, fuzzy 8.8%) |
| Crowd table | 1,770,724 hourly rows (route × stretch × hour × day type), plus 627,324 time-band rows |
| Temporal holdout (build from 1–21 Oct, test on unseen 22–31 Oct) | **83.5% tier agreement**, error 7.4 people (route-average baseline 73.9% / 12.6; city-average baseline 68.4% / 19.1) |
| Reliability (two independent halves of the month) | rank correlation **0.935** (0.960 where each half has 30+ tickets) |
| Model comparison (unseen days, cells with 10+ test tickets) | shrinkage estimate **R² 0.79** vs best ML 0.66 (Gradient Boosting). **Shrinkage wins, so it is what the API serves.** |
| API speed | `/api/plan` ≈ 0.1 s |
 
## How the crowd estimate works
 
Each ticket says where a passenger boarded and left, so we spread it over the stretches it travelled (shifting time forward using the timetable's travel times). Dividing by the **buses scheduled** on that stretch gives "ticketed riders per bus".
 
Because the file holds only **mobile e-tickets (about 3–4% of riders)** and no pass holders, we scale it with a **configurable calibration layer** (`backend/config.py`, base factor **42.9** = 1.5 pass-holder multiplier ÷ 0.035 e-ticket capture rate; low/high scenarios 20.0 / 66.7). The result is compared with the bus's seats and capacity (AC / non-AC) to produce **seats_available / standing_room / crowded**.
 
Thin cells lean on their route-hour or route-band average and carry a **confidence** flag. For cells with under 10 tickets the API serves that shrinkage estimate (`prediction_source = route_average`); the ML fallback is **switched off** because it did not beat shrinkage.
 
## Repository layout
 
```
.
├── backend/
│   ├── run_all.py            ONE command to rebuild everything from the raw files
│   ├── config.py             every assumption and setting (read this first)
│   ├── notebooks/            01 load+explore → 02 GTFS+stop matching → 03 crowd index → 04 validation → 05/06/07 ML
│   ├── scripts/              strict temporal ML split, V2 vs V4 comparison
│   ├── src/                  readable pandas code used by the notebooks and the API
│   ├── planner/app.py        FastAPI REST API (CORS open)
│   ├── tests/                28 tests (unit, API, served-table checks)
│   ├── outputs/              figures, JSON metrics, crowd tables (Parquet), saved models
│   ├── docs/                 TECHNICAL_NOTE, PROJECT_REPORT, API_CONTRACT, MODEL_COMPARISON
│   ├── data/raw/             put tickets.csv and gtfs/ here (not in git)
│   ├── Dockerfile            Cloud Run deployment (uses requirements-api.txt)
│   └── requirements*.txt
└── Frontend/
    ├── src/pages/            Home, Planner, CrowdMap, OperatorView, MLInsights
    ├── src/components/       crowding ribbon/badge, route planner, maps, status banner, etc.
    ├── src/api/              API client for the backend
    ├── src/config/api.ts     API base URL handling
    ├── src/utils/            route/transit/map helpers (with tests)
    └── vite.config.ts        dev server; proxies /api to the deployed backend
```
 
## Quick start
 
### Option A – run only the frontend (uses the live API)
 
Requires Node.js.
 
```bash
cd Frontend
npm install
npm run dev          # http://localhost:3000
```
 
In dev mode, requests to `/api/*` are proxied to the deployed Cloud Run backend, so no local backend is needed.
 
Optional environment variables (create `Frontend/.env.local`):
 
| Variable | Purpose |
|---|---|
| `VITE_GOOGLE_MAPS_API_KEY` | Enables the Google Maps views (crowd map, network map) |
| `VITE_API_BASE_URL` | Backend URL for production builds (e.g. the Cloud Run URL) |
 
Other scripts: `npm run build` (production build), `npm run preview`, `npm run lint` (type-check).
 
### Option B – run the backend locally
 
Python 3.10–3.12. The finished crowd tables are already in `backend/outputs/`, so **the API starts immediately without re-running the pipeline.**
 
```bash
cd backend
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn planner.app:app --host 0.0.0.0 --port 8000     # http://localhost:8000/api/health
```
 
To point the local frontend at your local backend, build/run it with `VITE_API_BASE_URL=http://localhost:8000` or change the proxy target in `Frontend/vite.config.ts`.
 
### Option C – rebuild the whole pipeline from raw data
 
The raw data is not included (too large):
 
1. **Tickets** – `October-Delhi.csv.zip` from the hackathon → unzip and save as `backend/data/raw/tickets.csv` (≈290 MB, 2,559,899 rows).
2. **Static GTFS** – request "Delhi Buses: GTFS Static Data – DTC / DoT" on https://delhi.transportstack.in → unzip into `backend/data/raw/gtfs/` (needs `stops.txt routes.txt trips.txt stop_times.txt`).
```bash
cd backend
cp .env.example .env              # only needed if you want MySQL (SQLite is the zero-setup default)
python run_all.py --check         # are the input files in place?
python run_all.py                 # everything: ~15–20 min, ~4 GB free RAM (8 GB comfortable)
python run_all.py --quick         # core only (notebooks 01–04 + ML)
python -m pytest -q tests         # 28 tests
python fix_served_table.py        # only if you re-run scripts/07_ml_models.py
```
 
Or open `backend/notebooks/` in Jupyter and run them in order – each one explains its step in plain English.
 
## API
 
Full details and JSON examples are in [`backend/docs/API_CONTRACT.md`](backend/docs/API_CONTRACT.md).
 
| Endpoint | Purpose |
|---|---|
| `/api/health` | Service status |
| `/api/stops?q=` | Stop search |
| `/api/plan?origin=&destination=&time=HH:MM&day_type=&preference=` | Journey options with crowd level |
| `/api/routes`, `/api/routes/summary?day_type=&hour=` | Route list and summary |
| `/api/routes/{id}/crowd` | Stretch-by-stretch crowding for a route |
| `/api/operator/hotspots` | Hotspot ranking (default `min_confidence=medium`, ranked by uncapped load) |
| `/api/operator/network-profile` | Network-wide profile |
| `/api/validation/summary` | Validation numbers |
| `/api/ml/insights` | ML layer results |
 
## What the validation covers
 
Headline accuracy is measured on cells (route × weekday/weekend × hour) with **10+ test tickets**, on **ticket volume per day (log scale)**, with a strict time split (features 8–21 Oct, target 22–31 Oct) and a second test on routes held out of training.
 
| Test | Shrinkage (served) | Own-history baseline | Best ML | Global mean |
|---|---|---|---|---|
| R², unseen days | **0.790** | 0.713 | 0.662 (Gradient Boosting) | −4.63 |
| R², unseen routes | **0.743** | 0.662 | 0.605 (Gradient Boosting) | −4.48 |
| Tier accuracy / macro-F1, unseen days | 0.793 / 0.613 | 0.775 / 0.592 | 0.838 / 0.608 (SVM) | 0.018 / 0.011 |
| Tier accuracy / macro-F1, unseen routes | 0.776 / 0.605 | 0.758 / 0.583 | 0.833 / 0.599 (SVM) | 0.019 / 0.012 |
 
**This validates ticket volume, not crowding.** The crowd tier also depends on assumptions nobody has validated: bus capacity (AC 33/60, non-AC 36/70) and the scale factor (42.9). A sensitivity test shows how far the tiers move if the scale is wrong. See `backend/docs/TECHNICAL_NOTE.md` for details.
 
## Assumptions and limits
 
- The tickets are a **sample** of riders, so crowd levels depend on the calibration assumptions. Sensitivity test: tiers stay the same for about 92.6% / 89.2% of cells if the scale is wrong in either direction.
- The GTFS has one calendar for all 7 days, so weekend supply equals weekday supply.
- Bus size is not in the data (only AC / non-AC); capacities in `config.py` are assumptions.
- About 6.1% of name uses could not be matched, and 8.4% of usable tickets have an assumed end stop.
- Quiet-looking cells are mostly **estimates** (see `prediction_source` in the API): observed tickets (10+) back 29.9% of stretch-hours; the other 70.1% use the shrinkage / route-average estimate (low confidence). Operator views default to medium+ confidence.
- Displayed load is capped at 1.5× crush capacity; hotspots are ranked by the uncapped `load_ratio_raw` so the top of the list is not a wall of ties.
## Further documentation
 
- [`backend/docs/TECHNICAL_NOTE.md`](backend/docs/TECHNICAL_NOTE.md) – method and assumptions
- [`backend/docs/PROJECT_REPORT.md`](backend/docs/PROJECT_REPORT.md) – project report
- [`backend/docs/API_CONTRACT.md`](backend/docs/API_CONTRACT.md) – endpoints and JSON examples
- [`backend/docs/MODEL_COMPARISON.md`](backend/docs/MODEL_COMPARISON.md) – V2 vs V4 modelling comparison
## Team
 
- **Aditya Priyadarshan** ([@Thankso112](https://github.com/Thankso112))
- **Sujit Kumar Nayak** ([@sujitnayak-web](https://github.com/sujitnayak-web))
- **Saitirtha Behera**  ([@SaitirthaBehera](https://github.com/SaitirthaBehera))
## Credits
 
Built with the help of AI tools: **Claude (Anthropic)** – pipeline, validation, ML and API code and documentation; **Gemini** and **Google AI Studio** – the frontend prototype and early backend experiments (its simulated data is NOT used anywhere in this project).
 
Open-source libraries: pandas, NumPy, SciPy, scikit-learn, matplotlib, seaborn, RapidFuzz, SQLAlchemy, FastAPI, Uvicorn, PyArrow, Jupyter, React, Vite, Tailwind CSS.
 
Data: Transport Stack / IIIT Delhi (ONDC e-ticketing, DTC GTFS).
 
## License
 
See [`backend/LICENSE`](backend/LICENSE).
 
