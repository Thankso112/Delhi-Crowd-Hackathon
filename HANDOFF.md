# HANDOFF — Delhi Bus Crowd (Transport Stack Hackathon 2026, Problem 2 / Phase 1)
Deadline: 24 Nov 2026, 6:29 PM IST (aim: evening of 23 Nov). Team registered (3 members).

## State: runs end to end on the REAL data (October-Delhi.csv + GTFS), ~2 min
Real run results are in outputs/ and documented in docs/TECHNICAL_NOTE.md. Pipeline: `python run_pipeline.py`; app: `streamlit run app.py`; tests/notebooks pass on synthetic data (`set DATA_MODE=synthetic`).
Key real-data findings: 49% of tickets have no vehicle number (so NO trip inference; model = ticketed flow per scheduled GTFS trip); tickets are a thin sample (~1 pax per scheduled trip per day) and have no free tickets, so counts are scaled to riders with a coverage factor (24.7, an assumption: P90 of weekday-peak stretch load = standing limit); stop-name match 93.5%; 90.8% of tickets usable; hold-out R² (week 2 -> 3): shrinkage 0.78, gradient boosting 0.75, route avg 0.54, linear regression 0.21.

## Backend API (new)
`python -m api.main` serves the CrowdWise 8-endpoint contract (docs/API.md) on the real data; `pytest tests/test_api.py` = port of api.test.ts (9 tests pass). ML suite in crowd/ml.py (RF fallback for thin stretches; trained WITHOUT filtering on the outcome, see TECHNICAL_NOTE 6b). Unknown to us: transitEngine.ts, the frontend's expected shapes for polyline/segments/routes/operator/validation: ours are documented in docs/API.md; adapt if the React code differs.

## Remaining work
1. User: open the Streamlit app in a real browser and check layout/mobile (only tested with Streamlit AppTest). 2. Fill [TEAM: ...] gaps in docs (capacity source, team names). 3. Push to a public GitHub repo (the sandbox has no GitHub login), record the 3-min video (docs/DEMO_SCRIPT.md), submit.
4. Optional improvements: raise stop matching above 93.5% (read outputs/unmatched_names.csv); keep several stop patterns per route; use the optional vehicle-known tickets to estimate how many scheduled trips really run; FastAPI backend for the frontend team (matching the organizers' API contract if one exists in 03_api_contract_reference); operator heatmap.
5. The 'confidence' is low for 62% of cells (thin sample): this is honest, not a bug; the UI shows it.

## Rules for any continuing agent
- Do not change metric definitions in crowd/validate.py when comparing variants (docs/ARENA.md). Work on a branch; compare outputs/metrics.json.
- Never present synthetic numbers as results. Run `python -m pytest -q tests` and a clean-clone check before declaring done.
- Sandbox has ~3 GB RAM: free dataframes between steps (see run_pipeline.py).

## PASTE-READY PROMPT FOR THE NEXT CLAUDE
> You are continuing "Which bus has room?", a crowd-aware Delhi bus journey planner for Transport Stack Hackathon 2026 (Problem 2, Phase 1; deadline 24 Nov 2026 6:29 PM IST). The attached repo `delhi-bus-crowd` (zip) already runs end to end on the real data. Read HANDOFF.md, README.md and docs/TECHNICAL_NOTE.md first. Your task: [PASTE ONE TARGET HERE]. Constraints: keep metric definitions in crowd/validate.py; never present synthetic numbers as results; keep assumptions in config.py; keep the pipeline re-runnable from raw data; run pytest before finishing. If you are near your usage limit (~90%), stop, update HANDOFF.md and give me a new continuation prompt.
