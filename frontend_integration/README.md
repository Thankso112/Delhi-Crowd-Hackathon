# Connecting the CrowdWise frontend to this backend

The backend is a Python API (`planner/app.py`). The frontend must call it instead of using placeholder data.

## 1. Run the backend (two commands)
```bash
pip install -r requirements.txt
uvicorn planner.app:app --host 0.0.0.0 --port 8000        # then open http://localhost:8000/api/health
```
The finished crowd tables are in `outputs/`, so it starts at once (about 10 s to load).

## 2. Point the frontend at it
Either set `.env` in the frontend: `VITE_API_BASE_URL=http://localhost:8000`
or leave it empty and add the proxy from `vite.proxy.snippet.ts` (then browser CORS never matters while developing).
Copy `apiClient.ts` into `src/api/`.

## 3. Replace the placeholder data
The frontend repo I reviewed (`CrowdWise-Delhi`, 2 commits) took everything from `src/data/delhiBusNetwork.ts` and `src/utils/delhiRouting.ts`. Replace:
| Frontend function / data | API call |
|---|---|
| `BUS_STOPS` + the From/To dropdowns | `api.stops(text)` with a debounced search box (all 6,825 stops) |
| `findBusJourneys(...)` | `api.plan(origin, destination, time, dayType, preference)` |
| `getMapRouteOverlays(...)` | `api.routeCrowd(routeId, dayType, hour)` per route (draw `polyline`, colour each segment by `crowd_level`) |
| `getOverloadedRouteRows(...)` | `api.hotspots(dayType, hour)` |
| `getHourlyNetworkProfile(...)` | `api.networkProfile(dayType)` |
| ML Insights tab | `api.mlInsights()` |
Show the tier from `max_crowd_level` (`TIER_LABEL`) and the bar from `loadPct(max_load_ratio)`. **Do not recompute the tier from the percentage** (the old UI used 52% / 78% cut-offs; the backend's calibrated limits differ).

## 4. Three bugs from your integration reports
1. **Retry loop in `CrowdMapSection`** - remember routes that already failed:
```ts
const tried = useRef(new Set<string>());
async function loadRoute(id: string) {
  if (tried.current.has(id)) return;          // never retry the same failed route automatically
  tried.current.add(id);
  try { /* await api.routeCrowd(...) */ } catch { /* show the error once; the "Retry" button clears tried.current */ }
}
```
2. **Empty `q` in `StopAutocomplete`** - `api.stops('')` already returns an empty list without a request (and the backend returns `{"stops": []}` instead of an error). Also debounce typing by about 250 ms.
3. **No timeout in `fetchJson`** - fixed in `apiClient.ts` (15 s, then a readable error).

## 5. Text to change (these claims are not true for this data)
- Remove **"ETM"**, **"telemetry"** and the invented "91% ETM coverage" labels. The data is **mobile e-tickets (ONDC) + static GTFS**. Use `SOURCE_LABEL[prediction_source]` and `ticket_count` ("based on 312 e-tickets").
- Footer: "Data: ONDC e-ticketing (Oct 2026) and static GTFS (DTC/DIMTS), via Transport Stack." Add a one-line note: *"Crowding is an estimate: e-tickets are about 3-4% of riders, scaled with stated assumptions."*
- Route names: use `route_short_name` plus `origin_stop -> destination_stop` from `/api/routes` (real GTFS), not invented names. Agency comes from `agency` (DTC / DIMTS).

## 6. Before the demo
- `GET /api/health` returns `"mode": "real"` (not synthetic).
- Plan Anand Vihar -> Connaught Place (18:00, weekday) and Nehru Place -> Kashmiri Gate (09:00, weekday): both return options with crowd chips and departure shifts.
- Open the operator view: hotspots list different routes.
- The map basemap (Leaflet / Google) is left as your teammate built it; only the data source changes. Never commit a Google Maps key.
