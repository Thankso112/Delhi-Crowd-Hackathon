<div align="center">

# 🚌 CrowdWise Delhi

### Know how crowded your bus is, before you board.

A crowdedness-aware bus journey planner for Delhi, built for **Transport Stack Hackathon 2026 · Problem 2**.

<br/>

![React](https://img.shields.io/badge/React_19-20232A?style=for-the-badge&logo=react&logoColor=61DAFB)
![TypeScript](https://img.shields.io/badge/TypeScript-3178C6?style=for-the-badge&logo=typescript&logoColor=white)
![Vite](https://img.shields.io/badge/Vite_8-646CFF?style=for-the-badge&logo=vite&logoColor=white)
![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS_4-06B6D4?style=for-the-badge&logo=tailwindcss&logoColor=white)
![Leaflet](https://img.shields.io/badge/Leaflet-199900?style=for-the-badge&logo=leaflet&logoColor=white)
![Google Cloud Run](https://img.shields.io/badge/Cloud_Run-4285F4?style=for-the-badge&logo=googlecloud&logoColor=white)

![Node](https://img.shields.io/badge/node-%3E%3D20-339933?style=flat-square&logo=nodedotjs&logoColor=white)
![Maps](https://img.shields.io/badge/map-no_API_key_needed-1F4D3A?style=flat-square)
![Data](https://img.shields.io/badge/data-2.56M_ticket_records-F59E0B?style=flat-square)
![Hackathon](https://img.shields.io/badge/Transport_Stack-Hackathon_2026-E11D48?style=flat-square)

</div>

---

## ✨ What is CrowdWise?

CrowdWise joins static **GTFS** data with about **2.56 million** October 2026 ETM / e-ticket records to estimate how full a bus will be on a route, at a given **hour** and **day type** (weekday or weekend).

- 🧑‍🤝‍🧑 **Riders** pick a less crowded journey.
- 🚦 **Operators** see which corridors are overloaded and when.

---

## 🎨 Crowding colours

| Colour | Meaning | Load |
| :---: | --- | --- |
| 🟢 | Seats available | under 52% |
| 🟠 | Standing room | 52% to 78% |
| 🔴 | Crowded | 78% or more |
| ⚪ | No data / low data | not enough tickets |

---

## 🧭 Features

| Section | What you can do |
| --- | --- |
| 🏠 **Home** | Network map with every route in its own colour. Click a route to focus on it and see its stops. |
| 🗺️ **Crowd Map** | View one route at a time, coloured by crowding. Search and filter (Crowded, Seats, Low confidence, Not enough data), open the stops panel, switch map labels and satellite view. |
| 🧳 **Journey Planner** | Plan by origin and destination, or by route number. |
| 📊 **Operator View** | Ranked overloaded corridors, hourly network load chart, confidence and prediction source for each row. |
| 🤖 **ML Insights** | Model performance and data coverage. |

---

## 🛠️ Tech stack

| Layer | Technology |
| --- | --- |
| Language | TypeScript |
| UI | React 19 |
| Build tool | Vite 8 |
| Styling | Tailwind CSS 4 |
| Maps | Leaflet 1.9 with CARTO tiles, Esri World Imagery for satellite (no key or billing) |
| Icons | lucide-react |
| Testing | `node:test` through `tsx` |
| Backend | Python API on Google Cloud Run |
| Data | GTFS + ETM / e-ticket records |

---

## 🚀 Getting started

**Prerequisites:** Node.js 20 or newer, and npm.

```bash
git clone https://github.com/sujitnayak-web/CrowdWise-Delhi.git
cd CrowdWise-Delhi
npm install
cp .env.example .env
npm run dev
```

In development, requests to `/api` are proxied to the backend by the Vite dev server (see `vite.config.ts`).

### ⚙️ Environment variables

| Variable | Description |
| --- | --- |
| `VITE_API_BASE_URL` | Backend base URL. If empty in a production build, the app falls back to `https://delhi-crowd-hackathon-1026044669617.asia-south1.run.app`. Trailing slashes are removed. |

### 📜 Scripts

| Command | What it does |
| --- | --- |
| `npm run dev` | Start the dev server |
| `npm run build` | Production build |
| `npm run preview` | Preview the production build |
| `npm test` | Run unit tests |

---

## 📁 Project structure

```text
src/
├── api/          API client (fetchJson with timeout + retry, endpoint helpers)
├── components/   UI sections (Home map, Crowd Map, Planner, Operator View, ML Insights)
│   └── map/      Leaflet wrapper (MapView, MapPolyline, MapOverlay)
├── config/       API base URL resolution
├── types/        Shared TypeScript types
└── utils/        Crowding levels, ranking, route filters, map geometry
```

---

## 🔌 Backend API

Base URL: `https://delhi-crowd-hackathon-1026044669617.asia-south1.run.app`

| Endpoint | Purpose |
| --- | --- |
| `GET /api/health` | Health check |
| `GET /api/routes` | Route list |
| `GET /api/routes/summary?day_type=&hour=` | Load, crowding and confidence for every route-direction |
| `GET /api/routes/{route_id}/crowd` | Stops and per-stretch crowding for one route |
| `GET /api/operator/hotspots` | Ranked overloaded corridors |
| `GET /api/operator/network-profile` | Network load by hour |
| `GET /api/plan` | Journey planning |
| `GET /api/stops` | Stops |
| `GET /api/ml/insights` | Model metrics |

> ⏳ The first request after a quiet period can be slow while the server wakes up. The client uses a **30 second timeout**, retries **once after 2 seconds**, then shows an error banner with a **Retry** button.

---

## 📐 How crowding is shown

- Displayed load is capped at **100%**. When the backend sends the raw (uncapped) value, routes are sorted and coloured by the raw value.
- **No data**: the API returned nothing for that route at that hour (shown in grey).
- **Low confidence**: a number exists, but it is low confidence or a route-average estimate.

---

## ☁️ Deployment

Set `VITE_API_BASE_URL` in your hosting environment if you use a different backend, then run:

```bash
npm run build
```

and deploy the `dist/` folder.

---

<div align="center">

Made with ❤️ for **Transport Stack Hackathon 2026 · Delhi**

</div>
