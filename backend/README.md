<div align="center">

# 🚌 CrowdWise Delhi · Backend

### Crowding predictions for every Delhi bus route, hour by hour.

REST API behind the CrowdWise Delhi journey planner, built for **Transport Stack Hackathon 2026 · Problem 2**.

<br/>

![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Google Cloud Run](https://img.shields.io/badge/Cloud_Run-4285F4?style=for-the-badge&logo=googlecloud&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white)
![REST API](https://img.shields.io/badge/REST-JSON_API-1F4D3A?style=for-the-badge)

![Routes](https://img.shields.io/badge/route--directions-2%2C574-F59E0B?style=flat-square)
![Records](https://img.shields.io/badge/ticket_records-2.56M-F59E0B?style=flat-square)
![R2](https://img.shields.io/badge/R%C2%B2_unseen_days-0.79-16A34A?style=flat-square)
![R2 routes](https://img.shields.io/badge/R%C2%B2_unseen_routes-0.743-16A34A?style=flat-square)
![CORS](https://img.shields.io/badge/CORS-open-64748B?style=flat-square)

</div>

---

## ✨ What does it do?

The backend turns static **GTFS** data and about **2.56 million** October 2026 ETM / e-ticket records into crowding estimates for every route-direction, at any **hour** and **day type** (weekday or weekend).

- 📍 Estimates load and crowding for each route and each stretch between stops.
- 🚦 Ranks overloaded corridors for operators.
- 🧳 Plans journeys that take crowding into account.
- 🤖 Reports model validation and coverage.

**Coverage:** 2,574 route-directions (1,406 base routes).

---

## 🌐 Live service

**Base URL:** `https://delhi-crowd-hackathon-1026044669617.asia-south1.run.app`

- Hosted on Google Cloud Run, region `asia-south1`.
- CORS is open to all origins.
- One instance is kept warm. A request after a quiet period can still take about 8–9 seconds, so clients should use a 30 second timeout with one retry.

---

## 🔌 API endpoints

| Endpoint | Purpose |
| --- | --- |
| `GET /api/health` | Health check |
| `GET /api/routes` | Route list |
| `GET /api/routes/summary?day_type=&hour=` | One row per route-direction (about 1 MB). Fetch once per day type and hour, and cache it. |
| `GET /api/routes/{route_id}/crowd` | Stops and per-stretch crowding for one route-direction |
| `GET /api/operator/hotspots` | Ranked overloaded corridors |
| `GET /api/operator/network-profile` | Network load for all 24 hours |
| `GET /api/plan` | Journey planning |
| `GET /api/stops` | Stops |
| `GET /api/ml/insights` | Model metrics and data coverage |
| `GET /api/validation/summary` | Validation results |

Full request and response types: [`docs/API_CONTRACT.md`](docs/API_CONTRACT.md). Typed TypeScript client with examples: [`frontend_integration/apiClient.ts`](frontend_integration/apiClient.ts).

### Hotspots query options

| Parameter | Values | Default |
| --- | --- | --- |
| `day_type` | `weekday`, `weekend` | n/a |
| `hour` | `0` to `23`, or `all` | n/a |
| `min_confidence` | `low`, `medium`, `high` | `medium` |
| `limit` | number of rows | n/a |

---

## 📦 Response fields

### `/api/routes/summary` row

| Field | Meaning |
| --- | --- |
| `route_id` | Unique per route-direction. Safe to pass to `/api/routes/{route_id}/crowd`. |
| `route_short_name`, `route_long_name` | Route number and full name |
| `direction_id`, `direction` | Direction of travel |
| `busiest_stretch` | Busiest stretch of the route (null if no data) |
| `load_ratio_raw` | Uncapped load ratio. Sort and colour by this. |
| `load_pct` | Load percentage, capped at 100 for display |
| `crowd_level` | Crowding level, or `unknown` when there is no data |
| `confidence` | `low`, `medium` or `high` |
| `prediction_source` | `observed_tickets` or `route_average` |
| `ticket_count` | Tickets behind the estimate |
| `scheduled_buses_hr` | Scheduled buses per hour |

### Hotspot extras

| Field | Meaning |
| --- | --- |
| `load_ratio_raw`, `load_pct_raw`, `estimated_load_raw` | Uncapped values. `load_pct_raw` can be 1557 or more, so cap it when displaying. |
| `load_ratio`, `load_pct`, `estimated_load` | Capped at 1.5, 100 and 90 |
| `suggested_extra_buses_hr` | Based on the raw load, so it can be large (for example 40) |

---

## 📐 How to read the data

- **No data:** rows with `crowd_level: "unknown"`, `confidence: "low"` and null `load_pct`, `load_ratio_raw` and `busiest_stretch`. At weekday 09:00, about 1,000 of 2,574 rows are like this. This is expected.
- **Low confidence:** `confidence === "low"` or `prediction_source === "route_average"`.
- **Null hours:** in `hourly_network` and `/api/operator/network-profile`, hours with too little medium or high confidence data return `cells: 0` and null averages. Treat these as "no data", not zero load.
- **Busiest stretch:** ignores the first and last 2 stops, and stretches with fewer than 10 tickets.
- **Crowded share:** about 6% of the network overall, and about 30% at weekday 09:00. Earlier versions showed 57% because of a model artefact, so the lower number is correct.

---

## 🧪 Model validation

| Test | R² |
| --- | --- |
| Unseen days | **0.79** |
| Unseen routes | **0.743** |

These come from the `headline_accuracy` block in `/api/validation/summary`. The older `temporal_holdout_w1_w3_to_w4` block is a different, earlier test, so label the two differently if you show both.

---

## 🛠️ Tech stack

| Layer | Technology |
| --- | --- |
| Language | Python |
| API | FastAPI |
| Data | GTFS + ETM / e-ticket records |
| Model | Gradient-boosted regression |
| Hosting | Google Cloud Run (`asia-south1`) |
| Container | Docker |

---

## 🚀 Run locally

```bash
git clone https://github.com/Thankso112/Delhi-Crowd-Hackathon.git
cd Delhi-Crowd-Hackathon/backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8080
```

Then open `http://localhost:8080/api/health`.

### Environment variables

| Variable | Description |
| --- | --- |
| `PORT` | Port the server listens on (Cloud Run sets this) |

---

## ☁️ Deploy to Cloud Run

```bash
gcloud run deploy delhi-crowd-hackathon \
  --source . \
  --region asia-south1 \
  --allow-unauthenticated \
  --min-instances 1
```

`--min-instances 1` keeps one instance warm to avoid slow cold starts.

---

## 📁 Project structure

```text
backend/
├── docs/
│   └── API_CONTRACT.md        Endpoint and field reference
├── frontend_integration/
│   └── apiClient.ts           Typed client with examples
├── main.py                    API app
├── requirements.txt           Python dependencies
└── Dockerfile                 Container build
```

---

## 🔗 Frontend

The web app that uses this API: [CrowdWise-Delhi](https://github.com/sujitnayak-web/CrowdWise-Delhi)

---

<div align="center">

Made with ❤️ for **Transport Stack Hackathon 2026 · Delhi**

</div>
## Model versions
- The main project (repository root) is the V4 pipeline: hourly crowd table, REST API, ML layer with a strict time-based test, validation and documentation.
- An earlier V2 build was archived outside this repository; this repository contains only the V4 pipeline.
- `docs/MODEL_COMPARISON.md` and `scripts/compare_v2_vs_v4.py` compare the modelling approaches of both builds on identical data. Short version: they are close, and a simple shrinkage estimate beats both at route-hour level, so the shrinkage estimate is what is served, including for thin cells.
- Deployment: `Dockerfile` + `requirements-api.txt` (API only). `pytest.ini` limits tests to the main project.
