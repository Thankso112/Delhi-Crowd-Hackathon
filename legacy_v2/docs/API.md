# CrowdWise-compatible API (FastAPI) — for the frontend team

Python backend that implements the 8-endpoint contract from `server.ts` / `types.ts` / `api.test.ts` on the **real Delhi data** (2,574 route-directions, 6,825 stops, 547,587 crowd cells). Crowd levels are **typical** for a time band and day type (not live), estimated from October 2026 e-ticket data.

## Run
```bash
pip install -r requirements.txt
python run_pipeline.py                 # once, builds the data the API serves (~4 min)
python -m api.main                     # http://localhost:8000   (PORT=3000 python -m api.main to use another port)
# interactive docs: http://localhost:8000/docs      OpenAPI JSON: /openapi.json
python -m pytest -q tests/test_api.py  # contract tests (port of api.test.ts + error checks)
```
Startup takes about 12 s (loads everything into memory). A plan query takes about 1.9 s; everything else is fast.

## Connect your Express + Vite app
Keep the frontend as is and send `/api/*` to this service. CORS is already open (`*`), so a direct call works too.
```ts
// vite.config.ts
server: { proxy: { '/api': 'http://localhost:8000' } }
```
In `server.ts`, replace the local engine routes by a proxy, e.g. `http-proxy-middleware`: `app.use('/api', createProxyMiddleware({ target: 'http://localhost:8000' }))`.

## Endpoints
| Endpoint | Notes |
|---|---|
| `GET /api/health`, `/api/meta` | `HealthResponse`. `calibration.effective_scale_factor` = 24.7 riders per ticketed passenger; `eticket_capture_rate` = 1/24.7 = 0.040; `pass_holder_multiplier` = 1.0 (not separable from the factor, see technical note) |
| `GET /api/stops?q=&limit=` | `{query, count, stops[]}`; each stop has `stop_id, stop_name, lat, lng, num_routes, match_method, match_score`. Empty `q` returns the busiest hubs. Aliases work (`Kashmiri Gate` → Kashmere Gate, `CP` → Connaught Place) |
| `GET /api/plan?origin=&destination=&time=&day_type=&preference=&limit=` | origin/destination = stop name or `"lat,lng"`; also `olat,olon,dlat,dlon`. `preference` = `fastest` / `balanced` / `comfortable` (`fast`/`comfort` accepted). Returns `JourneyPlanResponse` |
| `GET /api/routes?q=&limit=&offset=` | `{total, count, limit, offset, routes[]}` with `route_id, route_short_name, direction_id, num_stops, is_ac, origin_stop, destination_stop, route_long_name, trips_per_day` |
| `GET /api/routes/{route_id_or_short_name}/crowd?day_type=&hour=&direction_id=` | ordered `stops[]`, `segments[]` (one per stretch), `polyline`, `summary` |
| `GET /api/operator/hotspots?day_type=&hour=&limit=&min_confidence=` | `{count, hotspots[]}` ranked by load ratio, with `suggested_extra_buses_hr` |
| `GET /api/ml/insights` | `MlInsightsResponse` (4 regressors, 2 classifiers, confusion matrix, importances, Lasso, correlations, concepts, fallback stats) |
| `GET /api/validation/summary` | hold-out scores, calibration, sensitivity, limitations (shape is ours, see below) |
| anything else under `/api/` | JSON `404 {error:{code:"ENDPOINT_NOT_FOUND",...}}` |

Errors always look like `{"error": {"code", "message", "details?"}}`: `400 MISSING_PARAMS`, `400 BAD_TIME`, `404 STOP_NOT_FOUND`, `404 ROUTE_NOT_FOUND`, `404 ENDPOINT_NOT_FOUND`.

## Field meanings (decisions we made where the contract was silent)
- **`load_ratio`** = estimated passengers on board ÷ **crush capacity** of that bus (AC 60, non-AC 70; assumptions in `config.py`), capped at 1.3. 1.0 = packed.
- **Levels** `seats_available` (load ≤ seated capacity), `standing_room` (≤ 75% of crush), `crowded`. `unknown` only if a route has no data at all.
- **`polyline`** = `[[lat, lng], ...]` (Leaflet order). **`segments[]`** per leg = one entry per stretch between consecutive stops: `sequence, from_stop, to_stop, from_stop_id, to_stop_id, load_ratio, est_passengers, crowd_level, confidence, prediction_source, ticket_count`.
- **`prediction_source`**: `observed_tickets` (the stretch has at least 20 tickets behind it), `ml_fallback` (thin stretch filled by the Random Forest), `route_average` (no cell for that band: average of the route's other bands). On a leg or option it is the most common source among its stretches.
- **`ticket_count`**: tickets covering the stretch; on a leg/option the median across stretches (the evidence behind the estimate). **`confidence`** `high ≥ 100`, `medium ≥ 20`, else `low` tickets per stretch (lowered one step where the band has under 2 scheduled trips); on a leg/option the median stretch.
- **`max_crowd_level` / `max_load_ratio`** = the worst stretch of the leg/option; `avg_*` = the mean. **`tag`** = `fastest`, `most_comfortable`, `direct` or `with_transfer`.
- **Leg times** `departure_time` / `arrival_time` (HH:MM) = requested time + walk + expected wait (half the headway, capped at 20 min) + ride from GTFS.
- **`departure_shifts`** re-evaluates the same buses at other departure times (±15 to ±120 min) and lists only shifts that improve crowding. The crowd model has 6 time bands (night, early, am_peak, midday, pm_peak, evening), so a shift only changes the level if it crosses a band boundary.
- **`suggested_extra_buses_hr`** = extra buses per hour needed to bring the stretch down to the standing limit (75% of crush), based on scheduled trips per hour in that band; capped at 20. Ranking uses the load ratio, ties (capped values) broken by ticket count.
- **`/api/validation/summary`** shape is ours (the contract does not define it): `mode, calibration, holdout, stability_spearman_w2_vs_w3, level_accuracy, skill_vs_route_baseline, sensitivity_to_coverage_factor, share_low_confidence_cells, fallback_stats, ticket_resolution, stop_matching_report, limitations[]`.

## Differences from the TypeScript engine you may notice
- Runs on the full Delhi network, so `routes`/`stops`/`crowd_cells` are in the thousands (your tests only require ≥ 20 / 40 / 1000).
- Direction is part of the Delhi route name (`534UP`, `534DOWN`); `route_id` is unique per route-direction and `direction_id` is always 0 in the feed.
- `pass_holder_multiplier` is 1.0 because free-fare/pass travellers are absent from the ticket file and are folded into the single scale factor.
- Anything not in `types.ts` (`polyline`, `segments`, route and operator response shapes, validation summary) is our design; tell us if your React code expects different names and we adapt.

## Honest limits (also in `GET /api/validation/summary`)
Typical crowding by time band, not live. The ticket file is a thin sample (about one ticketed passenger per scheduled trip per day), so counts are scaled by a stated calibration whose absolute level labels are assumptions; **rankings do not depend on it**. No ground-truth crowding exists, so metrics show consistency and predictability over time, not absolute accuracy. 62% of stretches are low confidence and flagged as such.
