<div align="center">
<h1>🚌 CrowdWise Delhi</h1>
 
<h3>Crowd-aware bus journey planner for Delhi</h3>
 
<p>Estimates whether each bus option will have <b>seats</b>, <b>standing room</b>, or be <b>crowded</b>.<br>
<b>Transport Stack Hackathon 2026 · Problem 2 · Phase 1</b></p>
<p>
<img src="https://img.shields.io/badge/React-20232A?style=for-the-badge&logo=react&logoColor=61DAFB" alt="React">
<img src="https://img.shields.io/badge/TypeScript-3178C6?style=for-the-badge&logo=typescript&logoColor=white" alt="TypeScript">
<img src="https://img.shields.io/badge/Vite-646CFF?style=for-the-badge&logo=vite&logoColor=white" alt="Vite">
<img src="https://img.shields.io/badge/Tailwind_CSS-06B6D4?style=for-the-badge&logo=tailwindcss&logoColor=white" alt="Tailwind CSS">
<img src="https://img.shields.io/badge/Google_Maps-4285F4?style=for-the-badge&logo=googlemaps&logoColor=white" alt="Google Maps">
<img src="https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python">
<img src="https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white" alt="FastAPI">
<img src="https://img.shields.io/badge/Cloud_Run-4285F4?style=for-the-badge&logo=googlecloud&logoColor=white" alt="Google Cloud Run">
</p>
<p>
<img src="https://img.shields.io/badge/data-Oct_2026_e--tickets-F59E0B?style=flat-square" alt="Data">
<img src="https://img.shields.io/badge/timetable-DTC_GTFS-1F4D3A?style=flat-square" alt="GTFS">
<img src="https://img.shields.io/badge/tier_agreement-83.5%25-16A34A?style=flat-square" alt="Tier agreement">
</p>
<p>
<a href="https://crowdwise-delhi.ai.studio/"><b>Live demo</b></a> ·
<a href="https://delhi-crowd-hackathon-1026044669617.asia-south1.run.app/docs"><b>Live API</b></a>
</p>
</div>
---
 
## 📖 Contents
 
- [The problem](#-the-problem)
- [What it does](#-what-it-does)
- [Features](#-features)
- [How it works](#-how-it-works)
- [Validation](#-validation)
- [Limitations](#-limitations)
- [Repository structure](#-repository-structure)
- [Getting started](#-getting-started)
- [API](#-api)
- [Documentation](#-documentation)
- [Team and credits](#-team-and-credits)
- [License](#-license)
---
 
## 🎯 The problem
 
Delhi bus riders cannot tell whether the next bus will have seats or be packed, and operators cannot easily see which corridors are overloaded and when.
 
## ✨ What it does
 
CrowdWise combines **2.56 million October 2026 e-ticket records** with the **DTC GTFS timetable** to estimate crowding for each bus route option, by hour and day type.
 
- 🧑‍🤝‍🧑 **Riders** can choose a less crowded journey.
- 🚦 **Operators** can see which corridors are overloaded.
---
 
## 🧭 Features
 
| Section | What you can do |
| --- | --- |
| 🏠 **Home** | Network map with every route in its own colour. Click a route to focus on it. |
| 🗺️ **Crowd Map** | One route at a time, coloured by crowding, with a stops panel, search and filters. |
| 🧳 **Journey Planner** | Plan by origin and destination, or by route number. |
| 📊 **Operator View** | Ranked overloaded corridors and an hourly network load chart. |
| 🤖 **ML Insights** | Model performance and data coverage. |
 
### 🎨 Crowding colours
 
| Colour | Meaning |
| :---: | --- |
| 🟢 | Seats available |
| 🟠 | Standing room |
| 🔴 | Crowded |
| ⚪ | No data / low data |
 
---
 
## ⚙️ How it works
 
1. **Spread tickets over stretches:** each ticket is spread across the bus stretches (between stops) it covered, shifted forward in time using the timetable's travel times.
2. **Divide by scheduled buses:** ticket counts are divided by the number of scheduled buses for that route and hour.
3. **Calibrate:** a configurable factor (`backend/config.py`, base value 42.9) scales the counts up to account for riders who do not use e-tickets, such as pass holders.
4. **Compare with capacity:** the result is compared against seat and capacity assumptions (AC / non-AC) to give a crowding tier.
5. **Fill the gaps:** where there are fewer than 10 tickets, a shrinkage (route-average) estimate is used instead of observed data and is marked with lower confidence.
```text
 e-tickets + GTFS ──▶ data pipeline ──▶ crowd model ──▶ FastAPI ──▶ React frontend
```
 
---
 
## 🧪 Validation
 
Strict time split: the model is built from 1–21 Oct and tested on unseen 22–31 Oct.
 
| Method | Tier agreement |
| --- | --- |
| **CrowdWise model** | **83.5%** |
| Route-average baseline | 73.9% |
| City-average baseline | 68.4% |
 
A simple shrinkage estimate (R² 0.79) also beat the best machine-learning model (R² 0.66, Gradient Boosting), so it is what the API serves. Rank correlation between two independent halves of the month is 0.935.
 
> ⚠️ This validates **ticket volume** more than actual crowding. The capacity and scale assumptions have not been verified against real on-board counts.
 
---
 
## ⚠️ Limitations
 
- Estimates are **sample-based**, since only e-ticket riders (about 3–4%) are in the data.
- About **6% of stop names** could not be matched.
- About **70% of stretch-hours** have too few tickets and rely on estimates rather than observed data.
- Capacity and calibration assumptions are unverified. A sensitivity test shows tiers stay the same for about 89–93% of cells if the scale is wrong.
- The GTFS has one calendar for all 7 days, so weekend supply equals weekday supply.
---
 
## 📁 Repository structure
 
This is a monorepo.
 
```text
.
├── backend/     Python data pipeline, crowd model, notebooks, tests and FastAPI API
│   ├── planner/app.py     FastAPI app (planner.app:app)
│   ├── src/               pandas code used by notebooks and the API
│   ├── notebooks/         01 explore → 02 GTFS matching → 03 crowd index → 04 validation → 05–07 ML
│   ├── outputs/           precomputed crowd tables, metrics, figures, models
│   ├── docs/              technical note, project report, API contract, model comparison
│   └── Dockerfile         Cloud Run deployment
├── Frontend/    React + TypeScript + Vite app
│   ├── src/pages/         Home, Planner, CrowdMap, OperatorView, MLInsights
│   └── src/api/           API client
└── README.md
```
 
> Rebuilding the full pipeline needs the raw ticket and GTFS files, which are **not included** in this repository. The finished crowd tables are in `backend/outputs/`, so the API runs without them.
 
---
 
## 🚀 Getting started
 
### Frontend (against the live API)
 
Requires Node.js and npm.
 
```bash
cd Frontend
npm install
npm run dev          # http://localhost:3000
```
 
In development, requests to `/api/*` are proxied to the live Cloud Run API, so no local backend is needed.
 
Optional: create `Frontend/.env.local`.
 
| Variable | Description |
| --- | --- |
| `VITE_GOOGLE_MAPS_API_KEY` | Enables the Google Maps views (Home and Crowd Map). |
| `VITE_API_BASE_URL` | Backend base URL for **production builds** (for example the Cloud Run URL below). Ignored in dev. |
 
Other scripts: `npm run build`, `npm run preview`, `npm run lint`.
 
### Backend
 
Requires Python 3.10–3.12.
 
```bash
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn planner.app:app --host 0.0.0.0 --port 8000
```
 
Then open `http://localhost:8000/api/health` or `http://localhost:8000/docs`.
 
To use your local backend from the frontend, change the proxy `target` in `Frontend/vite.config.ts` to `http://localhost:8000`.
 
Optional: `python -m pytest -q tests` runs the 28 backend tests. `python run_all.py` rebuilds everything from raw data (see `backend/data/raw/README.md`).
 
---
 
## 🔌 API
 
**Live base URL:** `https://delhi-crowd-hackathon-1026044669617.asia-south1.run.app`
 
Interactive Swagger docs: `<base URL>/docs`
 
| Endpoint | Purpose |
| --- | --- |
| `GET /api/health` | Health check |
| `GET /api/stops?q=` | Stop search |
| `GET /api/plan?origin=&destination=&time=HH:MM&day_type=&preference=` | Journey planning |
| `GET /api/routes` | Route list |
| `GET /api/routes/summary?day_type=&hour=` | One row per route-direction |
| `GET /api/routes/{route_id}/crowd` | Stops and per-stretch crowding |
| `GET /api/operator/hotspots` | Ranked overloaded corridors |
| `GET /api/operator/network-profile` | Network load by hour |
| `GET /api/validation/summary` | Validation numbers |
| `GET /api/ml/insights` | Model metrics |
 
Example: `/api/plan?origin=Anand Vihar&destination=Connaught Place&time=18:30`
 
> ⏳ The first request after a quiet period can take several seconds while the service loads the crowd table. Deploy with `--min-instances=1` to avoid this.
 
---
 
## 📚 Documentation
 
- [`backend/docs/TECHNICAL_NOTE.md`](backend/docs/TECHNICAL_NOTE.md): method and assumptions
- [`backend/docs/PROJECT_REPORT.md`](backend/docs/PROJECT_REPORT.md): project report
- [`backend/docs/API_CONTRACT.md`](backend/docs/API_CONTRACT.md): endpoints and JSON examples
- [`backend/docs/MODEL_COMPARISON.md`](backend/docs/MODEL_COMPARISON.md): modelling comparison
---
 
## 👥 Team and credits
 
- **[Aditya Priyadarshan](https://github.com/Thankso112)**
- **[Sujit Kumar Nayak](https://github.com/sujitnayak-web)**
- **AI tools** were used in building this project: Claude (Anthropic) for the pipeline, validation, ML and API code and docs; Gemini and Google AI Studio for the frontend prototype.
- **Open-source libraries:** React, Vite, Tailwind CSS, FastAPI, pandas, scikit-learn and others (see `package.json` and `backend/requirements.txt`).
- **Data:** Transport Stack and IIIT Delhi (ONDC e-ticketing, DTC GTFS).
## 📄 License
 
See [`backend/LICENSE`](backend/LICENSE).
 
---
 
<p align="center">Made with ❤️ for <b>Transport Stack Hackathon 2026 · Delhi</b></p>
 
