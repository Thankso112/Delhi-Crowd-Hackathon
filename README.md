<div align="center">

# 🚌 CrowdWise Delhi

### Crowd-aware bus journey planner for Delhi

Estimates whether each bus option will have **seats**, **standing room**, or be **crowded**.<br/>
**Transport Stack Hackathon 2026 · Problem 2 · Phase 1**

<br/>

![React](https://img.shields.io/badge/React-20232A?style=for-the-badge&logo=react&logoColor=61DAFB)
![TypeScript](https://img.shields.io/badge/TypeScript-3178C6?style=for-the-badge&logo=typescript&logoColor=white)
![Vite](https://img.shields.io/badge/Vite-646CFF?style=for-the-badge&logo=vite&logoColor=white)
![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-06B6D4?style=for-the-badge&logo=tailwindcss&logoColor=white)
![Leaflet](https://img.shields.io/badge/Leaflet-199900?style=for-the-badge&logo=leaflet&logoColor=white)
![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![Google Cloud Run](https://img.shields.io/badge/Cloud_Run-4285F4?style=for-the-badge&logo=googlecloud&logoColor=white)

![Data](https://img.shields.io/badge/data-Oct_2026_e--tickets-F59E0B?style=flat-square)
![GTFS](https://img.shields.io/badge/timetable-DTC_GTFS-1F4D3A?style=flat-square)
![Tier agreement](https://img.shields.io/badge/tier_agreement-83.5%25-16A34A?style=flat-square)

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
- [Team and credits](#-team-and-credits)
- [License](#-license)

---

## 🎯 The problem

Delhi bus riders cannot tell whether the next bus will have seats or be packed, and operators cannot easily see which corridors are overloaded and when.

## ✨ What it does

CrowdWise combines **October 2026 e-ticket records** with the **DTC GTFS timetable** to estimate crowding for each bus route option, by hour and day type.

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

1. **Spread tickets over stretches:** each ticket is spread across the bus stretches (between stops) it covered.
2. **Divide by scheduled buses:** ticket counts are divided by the number of scheduled buses for that route and hour.
3. **Calibrate:** a calibration factor scales the counts up to account for riders who do not use e-tickets.
4. **Compare with capacity:** the result is compared against seat and capacity assumptions to give a crowding tier.
5. **Fill the gaps:** where there are too few tickets, estimates are used instead of observed data, and marked with lower confidence.

```text
 e-tickets + GTFS ──▶ data pipeline ──▶ crowd model ──▶ FastAPI ──▶ React frontend
```

---

## 🧪 Validation

On a late-October holdout:

| Method | Tier agreement |
| --- | --- |
| **CrowdWise model** | **about 83.5%** |
| Route-average baseline | about 73.9% |

> ⚠️ This validates **ticket volume** more than actual crowding. The capacity and scale assumptions have not been verified against real on-board counts.

---

## ⚠️ Limitations

- Estimates are **sample-based**, since only e-ticket riders are counted.
- About **6% of stop names** could not be matched.
- Most **low-ticket cells** rely on estimates rather than observed data.
- Capacity and calibration assumptions are unverified.

---

## 📁 Repository structure

This is a monorepo.

```text
.
├── backend/     Python data pipeline, crowd model and FastAPI API
├── frontend/    React + TypeScript app   (TODO: confirm folder name)
└── README.md
```

> Rebuilding the full pipeline needs the raw ticket and GTFS files, which are **not included** in this repository.

---

## 🚀 Getting started

### Frontend (against the live API)

Requires Node.js and npm.

```bash
cd frontend            # TODO: confirm folder name
npm install
cp .env.example .env
npm run dev
```

| Variable | Description |
| --- | --- |
| `VITE_API_BASE_URL` | Backend base URL. If empty in a production build, the app falls back to the Cloud Run URL below. |

### Backend

Requires Python.

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8080     # TODO: confirm module name
```

Then open `http://localhost:8080/api/health`.

---

## 🔌 API

**Live base URL:** `https://delhi-crowd-hackathon-1026044669617.asia-south1.run.app`

Interactive Swagger docs: `<base URL>/docs` (TODO: confirm path)

| Endpoint | Purpose |
| --- | --- |
| `GET /api/health` | Health check |
| `GET /api/routes` | Route list |
| `GET /api/routes/summary?day_type=&hour=` | One row per route-direction |
| `GET /api/routes/{route_id}/crowd` | Stops and per-stretch crowding |
| `GET /api/operator/hotspots` | Ranked overloaded corridors |
| `GET /api/operator/network-profile` | Network load by hour |
| `GET /api/plan` | Journey planning |
| `GET /api/stops` | Stops |
| `GET /api/ml/insights` | Model metrics |

> ⏳ The first request after a quiet period can take several seconds. The frontend uses a 30 second timeout and retries once.

---

## 👥 Team and credits

- **Team:** TODO: add the three contributors' names and roles.
- **AI tools** were used in building this project.
- **Open-source libraries:** React, Vite, Tailwind CSS, Leaflet, FastAPI and others (see `package.json` and `requirements.txt`).
- **Data:** Transport Stack and IIIT Delhi.

## 📄 License

See [`backend/LICENSE`](backend/LICENSE).

---

<div align="center">

Made with ❤️ for **Transport Stack Hackathon 2026 · Delhi**

</div>
