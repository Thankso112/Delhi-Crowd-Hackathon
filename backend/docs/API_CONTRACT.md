# API contract - CrowdWise Delhi backend

Base URL (local): `http://localhost:8000` - start with `uvicorn planner.app:app --host 0.0.0.0 --port 8000`.
Base URL (deployed, Google Cloud Run): `https://delhi-crowd-hackathon-1026044669617.asia-south1.run.app` - every path below works against either base URL.
Interactive docs: `{base}/docs` (local: `http://localhost:8000/docs`; deployed: `https://delhi-crowd-hackathon-1026044669617.asia-south1.run.app/docs`). CORS is open to every origin (`*`), including the private-network preflight, so a page served from a public https address can call a server on `localhost`.
All responses are JSON. Errors always look like `{"error": {"code", "message", "details"}}` - never an HTML page.
Numbers below come from the real run (long lists shortened with `...`). The plan and route examples were captured before the ML fallback was switched off, so their load values and `prediction_source` can differ from the live API; `/docs` shows live output.

**Crowd tiers:** `seats_available` | `standing_room` | `crowded` (and `unknown` when no bus is scheduled at that hour). **Confidence:** `high` | `medium` | `low`.
**`prediction_source`:** `observed_tickets` (10+ tickets behind the number), `ml_fallback` (reserved: the ML fallback is disabled, so the API does not return it), `route_average` (fallback to the route-hour / route-band average).
**`load_ratio`** = estimated people on board / bus capacity (calibrated, capped at 1.5). Show *crowd_level* to commuters; do not recompute the tier from the ratio in the UI.
**`schedule_undercount`** = true when `load_ratio_raw > 3` (the GTFS schedule probably lists fewer buses than actually run). Show a "check schedule data" warning, not a crowd emergency.

## Endpoints
| Endpoint | Purpose |
|---|---|
| `GET /api/health` | status, counts, calibration settings |
| `GET /api/stops?q=&limit=15` | autocomplete (empty `q` -> `{"count":0,"stops":[]}`, never an error) |
| `GET /api/plan?origin=&destination=&time=HH:MM&day_type=weekday\|weekend&preference=balanced\|fastest\|comfortable` | journey options with crowd per leg + departure shifts. `origin`/`destination` accept a stop name, a stop_id, or `lat,lon` (or use `olat,olon,dlat,dlon`) |
| `GET /api/routes?q=&limit=100&offset=0` | route-directions |
| `GET /api/routes/{route_id}/crowd?day_type=&hour=&direction_id=` | stops, polyline and per-stretch crowd (`route_id` can be the GTFS id, the short name like `425DOWN`, or the number `425`) |
| `GET /api/operator/hotspots?day_type=&hour=&limit=20&min_confidence=medium\|low\|high` | most overloaded route-directions (one row each: its busiest stretch), ranked by BOUNDED raw load `min(load_ratio_raw, 3.0)`, then ticket count; rows with `schedule_undercount: true` come after unflagged rows. Default `min_confidence=medium` |
| `GET /api/routes/summary?day_type=&hour=` | one row per route-direction for the map: its busiest qualifying stretch (see below) |
| `GET /api/operator/network-profile?day_type=` | average load ratio per hour (for the operator bar chart) |
| `GET /api/validation/summary` | validation numbers from the real run |
| `GET /api/ml/insights` | ML split, models, metrics, confusion matrix, concepts |

## GET /api/health
```json
{
  "status": "ok",
  "mode": "real",
  "ready": true,
  "counts": {
    "routes": 1406,
    "route_directions": 2574,
    "stops": 6825,
    "crowd_cells": 1770724
  },
  "map_center": {
    "lat": 28.631,
    "lng": 77.217
  },
  "ml_fallback_model": "none (disabled: shrinkage estimate is served)",
  "crowd_table_file": "crowd_table_served.parquet",
  "calibration": {
    "eticket_capture_rate": 0.035,
    "pass_holder_multiplier": 1.5,
    "effective_scale_factor": 42.86,
    "capacity_ac": {
      "seats": 33,
      "crush": 60
    },
    "capacity_nonac": {
      "seats": 36,
      "crush": 70
    }
  },
  "startup_seconds": 6.6
}
```

## GET /api/stops?q=nehru&limit=2
```json
{
  "query": "nehru",
  "count": 2,
  "stops": [
    {
      "stop_id": "2560",
      "stop_name": "Nehru Place Terminal",
      "name": "Nehru Place Terminal",
      "lat": 28.549,
      "lng": 77.257,
      "lon": 77.257,
      "match_score": 92,
      "routes_count": 65,
      "sample_routes": ["244UP", "306UP", "374ADOWN", "..."]
    },
    {
      "stop_id": "2280",
      "stop_name": "Nehru Nagar",
      "name": "Nehru Nagar",
      "lat": 28.568,
      "lng": 77.254,
      "lon": 77.254,
      "match_score": 92,
      "routes_count": 50,
      "sample_routes": ["0543A(NS)UP", "0TMS(+)(NS)UP", "243DOWN", "..."]
    }
  ]
}
```

## GET /api/plan?origin=Anand Vihar&destination=Connaught Place&time=18:00&day_type=weekday
(first option and its legs shown; `path` is `[lat, lng]` pairs for map polylines)
```json
{
  "query": {
    "origin": "Anand Vihar",
    "destination": "Connaught Place",
    "time": "18:00",
    "hour": 18,
    "day_type": "weekday",
    "preference": "balanced"
  },
  "resolved_origin": {
    "stop_id": "9428",
    "stop_name": "Anand Vihar",
    "lat": 28.659,
    "lng": 77.311,
    "match_method": "exact",
    "match_score": 100
  },
  "resolved_destination": {
    "stop_id": "365",
    "stop_name": "Shivaji Stadium Terminal ( Connaught Place )",
    "lat": 28.632,
    "lng": 77.216,
    "match_method": "substring",
    "match_score": 84
  },
  "options": [
    {
      "total_duration_min": 55,
      "in_vehicle_min": 36,
      "wait_min": 16,
      "walk_min": 3,
      "transfers": 1,
      "max_crowd_level": "crowded",
      "avg_crowd_level": "standing_room",
      "max_load_ratio": 1.113,
      "avg_load_ratio": 0.596,
      "confidence": "low",
      "prediction_source": "route_average",
      "ticket_count": 338,
      "legs": [
        {
          "route_id": "1886",
          "route_short_name": "39AUP",
          "from_stop": {"stop_id": "5694", "stop_name": "Anand Vihar", "lat": 28.658, "lng": 77.311},
          "to_stop": {"stop_id": "813", "stop_name": "Rainy Well", "lat": 28.628, "lng": 77.261},
          "departure_time": "18:11",
          "arrival_time": "18:31",
          "ride_min": 20.7,
          "wait_min": 10.0,
          "num_stops": 13,
          "is_ac": true,
          "agency": "DTC",
          "max_crowd_level": "crowded",
          "max_load_ratio": 1.113,
          "avg_load_ratio": 0.89,
          "ticket_count": 96,
          "confidence": "low",
          "prediction_source": "route_average",
          "path": [[28.658, 77.311], [28.658, 77.311], ["..."]],
          "stop_sequence": ["Anand Vihar", "Ram Vihar", "Jagriti Enclave", "..."]
        },
        {
          "route_id": "2342",
          "route_short_name": "85EXTUP",
          "from_stop": {"stop_id": "813", "stop_name": "Rainy Well", "lat": 28.628, "lng": 77.261},
          "to_stop": {"stop_id": "5100", "stop_name": "Shivaji Stadium Terminal", "lat": 28.633, "lng": 77.215},
          "departure_time": "18:37",
          "arrival_time": "18:53",
          "ride_min": 15.7,
          "wait_min": 6.0,
          "num_stops": 8,
          "is_ac": true,
          "agency": "DTC",
          "max_crowd_level": "seats_available",
          "max_load_ratio": 0.318,
          "avg_load_ratio": 0.302,
          "ticket_count": 242,
          "confidence": "high",
          "prediction_source": "observed_tickets",
          "path": [[28.628, 77.261], [28.628, 77.252], ["..."]],
          "stop_sequence": ["Rainy Well", "Delhi Secretariat", "ITO AGCR /  ITO", "..."]
        }
      ],
      "walk_to_first_m": 38,
      "walk_from_last_m": 132,
      "transfer_walk_m": 0,
      "option_id": "opt-1",
      "rank": 1,
      "tag": "balanced"
    }
  ],
  "departure_shifts": [
    {
      "shift_minutes": 15,
      "departure_time": "18:15",
      "improves_crowding": false,
      "previous_crowd_level": "crowded",
      "new_crowd_level": "crowded",
      "load_ratio_delta": 0.0,
      "summary": "Leaving 15 min later does not noticeably reduce crowding."
    },
    {
      "shift_minutes": 30,
      "departure_time": "18:30",
      "improves_crowding": false,
      "previous_crowd_level": "crowded",
      "new_crowd_level": "crowded",
      "load_ratio_delta": 0.0,
      "summary": "Leaving 30 min later does not noticeably reduce crowding."
    }
  ],
  "note": null
}
```

`departure_shifts[].improves_crowding` is true only when leaving later lowers the worst tier or the load ratio by 0.05 or more. Options are ranked by `preference`; `tag` is one of `fastest`, `most_comfortable`, `balanced`, `alternative`.

## GET /api/routes?q=nehru&limit=2
```json
{
  "total": 91,
  "count": 2,
  "offset": 0,
  "routes": [
    {
      "route_id": "1309",
      "route_short_name": "D-004STL-KNDDOWN",
      "direction_id": 1,
      "origin_stop": "Sunehari Pulla Depot / Jawahar Lal Nehru Stadium Terminal",
      "destination_stop": "Kushak Nallah Depot",
      "num_stops": 5,
      "is_ac": false,
      "has_crowd_data": false,
      "agency": "DIMTS",
      "description": "Sunehari Pulla Depot / Jawahar Lal Nehru Stadium Terminal to Kushak Nallah Depot"
    },
    {
      "route_id": "1312",
      "route_short_name": "D-006DOWN",
      "direction_id": 1,
      "origin_stop": "Sunehari Pulla Depot / Jawahar Lal Nehru Stadium Terminal",
      "destination_stop": "Anand Vihar ISBT Terminal",
      "num_stops": 25,
      "is_ac": true,
      "has_crowd_data": true,
      "agency": "DIMTS",
      "description": "Sunehari Pulla Depot / Jawahar Lal Nehru Stadium Terminal to Anand Vihar ISBT Terminal"
    }
  ]
}
```

## GET /api/routes/425DOWN/crowd?day_type=weekday&hour=9
```json
{
  "route_id": "1919",
  "route_short_name": "425DOWN",
  "direction_id": 1,
  "is_ac": true,
  "day_type": "weekday",
  "hour": 9,
  "description": "Hamdard Nagar / Sangam Vihar to ISBT Kashmere Gate City Bus Terminal / ISBT Maharana Pratap Bus Terminal",
  "agency": "DTC",
  "summary": {
    "max_crowd_level": "crowded",
    "max_load_ratio": 1.5,
    "peak_estimated_load": 90.0,
    "seated_capacity": 33,
    "capacity": 60,
    "total_tickets_in_hour": 6633,
    "scheduled_buses_hr": 7
  },
  "stops": [
    {"sequence": 0, "stop_id": "2301", "stop_name": "Hamdard Nagar / Sangam Vihar", "lat": 28.512, "lng": 77.249},
    {"sequence": 1, "stop_id": "2302", "stop_name": "Majeedia Hospital", "lat": 28.515, "lng": 77.253}
  ],
  "polyline": [[28.512, 77.249], [28.515, 77.253]],
  "segments": [
    {
      "sequence": 0,
      "from_stop_id": "2301",
      "to_stop_id": "2302",
      "from_stop_name": "Hamdard Nagar / Sangam Vihar",
      "to_stop_name": "Majeedia Hospital",
      "from_lat": 28.512,
      "from_lng": 77.249,
      "to_lat": 28.515,
      "to_lng": 77.253,
      "estimated_load": 81.2,
      "seated_capacity": 33,
      "capacity": 60,
      "load_ratio": 1.354,
      "crowd_level": "crowded",
      "scheduled_buses_hr": 7,
      "ticket_count": 251,
      "confidence": "high",
      "prediction_source": "observed_tickets",
      "data_source": "calibrated_estimate"
    }
  ]
}
```

## GET /api/routes/summary?day_type=weekday&hour=9
One row per route-direction (2,574 in the current data: `counts.route_directions` in `/api/health`). `busiest_stretch` is the stretch with the highest UNCAPPED load that is at least 3 stops from either end of the route (terminal hops ignored) and has `ticket_count >= 10`; if no stretch qualifies, all stretches with data are used. `load_pct` is capped at 100 for display, `load_ratio_raw` is not capped. `schedule_undercount` is true when `load_ratio_raw > 3`. Routes with no data at that hour get `crowd_level: "unknown"`, `confidence: "low"` and null load/stretch. `ticket_count`, `confidence`, `prediction_source` and `scheduled_buses_hr` describe the busiest stretch.
```json
{
  "day_type": "weekday", "hour": 9, "count": 2574,
  "routes": [
    {"route_id": "1", "route_short_name": "102ADOWN", "direction_id": 1, "direction": "Down",
     "route_long_name": "Rohini Sec 22 Terminal to Azadpur Terminal",
     "busiest_stretch": "Rohini Sec 7 and sec 8,9 \u2013 Rohini Sec 7/8/9 Crossing",
     "load_ratio_raw": 0.769, "load_pct": 77, "schedule_undercount": false,
     "crowd_level": "standing_room", "confidence": "medium",
     "prediction_source": "observed_tickets", "ticket_count": 22, "scheduled_buses_hr": 1},
    {"route_id": "...", "route_short_name": "...", "direction_id": 0, "direction": "Up", "route_long_name": "...",
     "busiest_stretch": null, "load_ratio_raw": null, "load_pct": null, "schedule_undercount": false,
     "crowd_level": "unknown", "confidence": "low",
     "prediction_source": "route_average", "ticket_count": 0, "scheduled_buses_hr": 0}
  ]
}
```

## GET /api/operator/hotspots?day_type=weekday&hour=9&limit=2&min_confidence=medium
Ranked by a BOUNDED raw load, `min(load_ratio_raw, 3.0)`, then `ticket_count`. Rows with `load_ratio_raw > 3` get `schedule_undercount: true` (the GTFS schedule probably lists fewer buses than actually run, so tickets / listed buses blows up); they are ranked after unflagged rows and the UI should show a "check schedule data" warning, not a crowd emergency. `load_ratio_raw` itself stays uncapped. `suggested_extra_buses_hr` is capped at `scheduled_buses_hr` (never more than doubling the listed service). `load_ratio` / `load_pct` / `estimated_load` stay capped (1.5x) for display; `load_ratio_raw`, `load_pct_raw` and `estimated_load_raw` are uncapped; `suggested_extra_buses_hr` uses `estimated_load_raw`. `hourly_network` uses medium+ confidence cells only; hours with none have `cells: 0` and null values; `overloaded_count` = route-directions with a crowded stretch at medium+ confidence.

The raw fields (`load_ratio_raw`, `load_pct_raw`, `estimated_load_raw`) and `schedule_undercount` are present on every row; they are omitted from the first example row only to keep it short.
```json
{
  "day_type": "weekday",
  "hour": 9,
  "min_confidence": "medium",
  "count": 2,
  "hotspots": [
    {
      "rank": 1,
      "route_id": "3369",
      "route_short_name": "D-7701AUP",
      "direction_id": 0,
      "hour": 9,
      "is_ac": true,
      "from_stop_id": "9972",
      "from_stop_name": "Gaushala Road",
      "to_stop_id": "9971",
      "to_stop_name": "South Asian University",
      "from_lat": 28.483,
      "from_lng": 77.189,
      "to_lat": 28.482,
      "to_lng": 77.201,
      "estimated_load": 90.0,
      "seated_capacity": 33,
      "capacity": 60,
      "load_ratio": 1.5,
      "crowd_level": "crowded",
      "schedule_undercount": false,
      "scheduled_buses_hr": 2,
      "suggested_extra_buses_hr": 2,
      "ticket_count": 570,
      "confidence": "high",
      "prediction_source": "observed_tickets"
    },
    {
      "rank": 2,
      "route_id": "2040",
      "route_short_name": "525UP",
      "direction_id": 0,
      "hour": 9,
      "is_ac": true,
      "from_stop_id": "2772",
      "from_stop_name": "Asian Market",
      "to_stop_id": "2773",
      "to_stop_name": "Saket Crossing",
      "from_lat": 28.517,
      "from_lng": 77.221,
      "to_lat": 28.518,
      "to_lng": 77.217,
      "estimated_load": 90.0,
      "seated_capacity": 33,
      "capacity": 60,
      "load_ratio": 1.5,
      "load_ratio_raw": 15.57,
      "load_pct_raw": 1557,
      "estimated_load_raw": 934.2,
      "crowd_level": "crowded",
      "schedule_undercount": true,
      "scheduled_buses_hr": 2,
      "suggested_extra_buses_hr": 2,
      "ticket_count": 826,
      "confidence": "high",
      "prediction_source": "observed_tickets"
    }
  ]
}
```
(Row 2 is flagged `schedule_undercount: true` because its raw ratio is 15.57, so it is ranked after the unflagged row 1 even though it has more tickets, and its `suggested_extra_buses_hr` is capped at its 2 listed buses.)

## GET /api/operator/network-profile?day_type=weekday
Only cells with `ticket_count >= 10`. All 24 hours are returned; hours with no such cells have `cells: 0` and null `avg_load_ratio` / `crowded_share`.
```json
{
  "day_type": "weekday",
  "hours": [
    {"hour": 0, "avg_load_ratio": 0.431, "crowded_share": 0.158, "cells": 279},
    {"hour": 1, "avg_load_ratio": 0.542, "crowded_share": 0.241, "cells": 145},
    {"hour": 2, "avg_load_ratio": 0.452, "crowded_share": 0.043, "cells": 116},
    "..."
  ]
}
```

## GET /api/validation/summary
Includes `headline_accuracy` (cells with 10+ test tickets: R2 0.79 unseen days, 0.74 unseen routes for the served shrinkage model, with baselines, best ML model, tier accuracy and macro-F1) and `what_is_validated` (this validates ticket volume per cell; the crowd tier also depends on the assumed capacity and scale factor). Both keys are omitted from the example below for brevity; `/docs` shows them live. `fallback_stats` is computed from the served table (ML fallback off).
```json
{
  "mode": "real",
  "dataset": {
    "total_tickets": 2559899,
    "null_vehicle_share": 0.485,
    "stop_match_rate_on_route_pct": 87.5,
    "tickets_usable_share": 0.895,
    "holiday_dates_treated_as_weekend": ["2026-10-02", "2026-10-20"],
    "n_crowd_cells": 1770724
  },
  "temporal_holdout_w1_w3_to_w4": {
    "train_days": "2026-10-01 to 2026-10-21",
    "test_days": "2026-10-22 to 2026-10-31",
    "tier_agreement_pct": 83.535,
    "mae_people": 7.351,
    "spearman": 0.875,
    "baselines": [
      {"predictor": "City baseline (band average)", "cells": 172773, "tier_agreement_pct": 68.366, "MAE_people": 19.057, "spearman": 0.186},
      {"predictor": "Route baseline (route x band)", "cells": 172773, "tier_agreement_pct": 73.902, "MAE_people": 12.638, "spearman": 0.697}
    ],
    "note": "evaluated on cells with 10+ tickets in the unseen period"
  },
  "reliability": {
    "split_half_odd_even_spearman": 0.935,
    "split_half_first_vs_second_half_spearman": 0.911
  },
  "sensitivity": [
    {"scenario": "low", "scale": 20.0, "seats_available": 97.9, "standing_room": 1.1, "crowded": 1.0, "same_tier_as_base_pct": 92.6, "same_tier_high_confidence_pct": 76.4},
    {"scenario": "base", "scale": 42.9, "seats_available": 91.6, "standing_room": 3.5, "crowded": 4.9, "same_tier_as_base_pct": 100.0, "same_tier_high_confidence_pct": 100.0},
    {"scenario": "high", "scale": 66.7, "seats_available": 84.4, "standing_room": 5.7, "crowded": 10.0, "same_tier_as_base_pct": 89.2, "same_tier_high_confidence_pct": 69.5}
  ],
  "organizer_curve_check": [
    {"daytype": "weekday", "hour": 9, "organizer": 13000, "ours": 14327.0, "difference_pct": 10.2},
    {"daytype": "weekday", "hour": 18, "organizer": 8500, "ours": 9902.0, "difference_pct": 16.5},
    {"daytype": "weekend", "hour": 9, "organizer": 8000, "ours": 7971.0, "difference_pct": -0.4},
    "..."
  ],
  "tier_distribution": {"crowded": 0.061, "seats_available": 0.899, "standing_room": 0.04},
  "confidence_distribution": {"low": 0.701, "medium": 0.17, "high": 0.129},
  "fallback_stats": {
    "total_segments": 1770724,
    "observed_segments": 529075,
    "ml_fallback_segments": 0,
    "ml_fallback_pct": 0.0,
    "route_average_segments": 1241649
  },
  "generated_from": "real run outputs (outputs/*.json)"
}
```

## GET /api/ml/insights
```json
{
  "split_method": "Strict temporal split: features from 1-14 Oct (weeks 1-2), training target 15-21 Oct (week 3), test on unseen 22-31 Oct. Test cells need 10+ tickets.",
  "preprocessing_summary": "Winsorise features and training target at the 1st/99th percentile of TRAIN data, then StandardScaler, both fitted on train rows only inside one Pipeline. Row cap for SVM (12,000) and KNN search (40,000).",
  "train_rows": 149024,
  "test_rows": 245383,
  "test_sparse_rows": 29035,
  "active_fallback_model": "none (disabled: shrinkage estimate is served)",
  "ml_fallback_enabled": false,
  "fallback_stats": {
    "total_segments": 1770724,
    "observed_segments": 529075,
    "ml_fallback_segments": 0,
    "ml_fallback_pct": 0.0,
    "route_average_segments": 1241649
  },
  "regression_models": [
    {"name": "OLS (linear regression)", "mae": 0.19, "rmse": 0.243, "r2": 0.711, "mae_sparse": 0.231},
    {"name": "Ridge", "mae": 0.19, "rmse": 0.243, "r2": 0.711, "mae_sparse": 0.231},
    {"name": "Lasso", "mae": 0.191, "rmse": 0.244, "r2": 0.708, "mae_sparse": 0.233},
    "..."
  ],
  "baselines": [
    {"name": "BASELINE route x hour average (weeks 1-2)", "mae": 0.293, "rmse": 0.406, "r2": 0.197, "mae_sparse": 0.452},
    {"name": "BASELINE weeks 1-2 shrinkage estimate", "mae": 0.21, "rmse": 0.313, "r2": 0.522, "mae_sparse": 0.451}
  ],
  "classification_models": [
    {"name": "KNN (k=15, chosen on validation)", "accuracy": 0.703, "macro_f1": 0.578},
    {"name": "SVM (RBF, class_weight=balanced, 12k-row cap)", "accuracy": 0.696, "macro_f1": 0.646},
    {"name": "BASELINE tier from weeks 1-2 shrinkage estimate", "accuracy": 0.691, "macro_f1": 0.609},
    "..."
  ],
  "best_classifier": "SVM (RBF, class_weight=balanced, 12k-row cap)",
  "knn_k_scores": {"3": 0.575, "5": 0.574, "9": 0.581, "15": 0.582, "25": 0.581, "45": 0.571},
  "confusion_matrix": {
    "labels": ["seats_available", "standing_room", "crowded"],
    "matrix": [
      [70787, 24380, 4310],
      [8940, 19428, 11145],
      [3089, 22706, 80598]
    ]
  },
  "feature_importance": [
    {"feature": "own_A_idx_ratio", "weight": 0.364},
    {"feature": "buses_per_hour", "weight": 0.271},
    {"feature": "own_A_tix", "weight": 0.133}
  ],
  "lasso_zeroed_features": ["hour", "is_pm_peak", "is_up", "..."],
  "top_correlated_pairs": [
    {"feature_a": "n_stops", "feature_b": "route_len_km", "pearson_r": 0.924},
    {"feature_a": "own_A_idx_ratio", "feature_b": "routehour_A_idx_ratio", "pearson_r": 0.84},
    {"feature_a": "pos", "feature_b": "pos_frac", "pearson_r": 0.785},
    "..."
  ],
  "caveats": [
    "The 'sparse cell' test only includes cells that later had 10+ tickets (we need a reliable answer to score against). Such cells were BUSIER than they looked in weeks 1-2, which favours any model that can infer 'this place and hour is busy' from location and time. The advantage over the baselines on sparse cells is therefore real but overstated; cells that stay sparse cannot be scored at all."
  ],
  "concepts": [
    {
      "term": "Train / test split",
      "summary": "Hide part of the data while the model learns, then score it on the hidden part, so we test understanding and not memory.",
      "example": "A student practises on past papers and is judged on a new paper."
    },
    {
      "term": "Temporal split",
      "summary": "Train on the past and test on the future, never the other way round, so no future information leaks into training.",
      "example": "Predict next week's bus crowding from the previous three weeks only."
    }
  ],
  "scale_factor": 42.86
}
```

## Errors
`GET /api/plan?origin=Nehru Place` -> HTTP 400
```json
{
  "error": {
    "code": "MISSING_PARAMS",
    "message": "Both 'origin' and 'destination' are required (stop name, stop_id or 'lat,lon').",
    "details": {}
  }
}
```
`GET /api/plan?origin=zzzz&destination=Nehru Place` -> HTTP 404
```json
{
  "error": {
    "code": "STOP_NOT_FOUND",
    "message": "No stop matched the origin 'zzzz'. Use /api/stops?q= to search.",
    "details": {
      "origin": "zzzz"
    }
  }
}
```
Other codes: `BAD_TIME` (400), `ROUTE_NOT_FOUND` (404), `ENDPOINT_NOT_FOUND` (404).
