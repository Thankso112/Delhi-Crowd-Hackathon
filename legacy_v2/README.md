> **Archived V2 build.** The maintained project is in the repository root; the live API is at https://delhi-crowd-hackathon-1026044669617.asia-south1.run.app.

# Which bus has room? — crowd-aware bus journey planner for Delhi
Transport Stack Hackathon 2026 (Delhi), Problem 2, Phase 1.
 
A journey planner on static GTFS where **every option carries a crowd level (Seats available / Standing room / Crowded) and a confidence flag**, estimated from October 2026 bus-ticket records. The crowd model is the core contribution; the planner (direct + one transfer) exists to put that estimate in front of commuters.
 
## Live API (deployed)
- Base URL: https://delhi-crowd-hackathon-1026044669617.asia-south1.run.app
- Interactive docs: https://delhi-crowd-hackathon-1026044669617.asia-south1.run.app/docs
- Health check: https://delhi-crowd-hackathon-1026044669617.asia-south1.run.app/api/health
- Example: `/api/plan?origin=Anand Vihar&destination=Connaught Place&time=18:30`
Hosted on a free server that sleeps after about 15 minutes of inactivity, so the first request after a pause can take up to 2 minutes while the engine reloads. CORS is open to all origins.
 
## Quick start (Anaconda Prompt)
 
```bash
conda create -n buscrowd python=3.11 -y
conda activate buscrowd
pip install -r requirements.txt
```
 
### A. Real data (what we submit)
1. Tickets: download <https://pub-091bd9e794bb4877b10b29e6df80f065.r2.dev/2026-10/October-Delhi.csv.zip>, unzip, save as `data/raw/tickets.csv`.
2. GTFS: from delhi.transportstack.in put `stops.txt routes.txt trips.txt stop_times.txt` (and the other .txt files) in `data/raw/gtfs/`. (Ignore macOS junk files starting with `_`.)
3. Check the ticket header against `config.COL` (edit if names differ).
4. Learn the pipeline step by step in Jupyter, **or** run it all at once:
```bash
jupyter lab                      # open notebooks/01 ... 05 in order
python run_pipeline.py           # same steps, one command (add --db to also save to SQL)
streamlit run app.py             # the web app, opens in your browser
```
Outputs: `docs/data_profile.md`, `outputs/match_report.md`, `outputs/unmatched_names.csv`, `outputs/resolution_report.md`, `outputs/crowd_table.csv.gz` (city-wide crowd table, every stretch) and `outputs/crowd_route_level.csv`, `outputs/metrics.json`, `outputs/validation.md`, `outputs/figures/`.
 
### B. Synthetic demo (no data needed; for testing only)
```bash
set DATA_MODE=synthetic              # Windows Anaconda Prompt  (Mac/Linux: export DATA_MODE=synthetic)
python scripts/00_make_synthetic.py
python run_pipeline.py
streamlit run app.py
python -m pytest -q tests
```
Synthetic runs show a "Demo data" banner. **Their numbers are test artefacts, not findings.** In notebooks, uncomment the `DATA_MODE = "synthetic"` line instead.
 
## Backend API for the frontend team
```bash
python -m api.main        # http://localhost:8000  (interactive docs at /docs)
```
FastAPI service implementing the CrowdWise 8-endpoint contract on the real data: stop search with aliases, crowd-aware journey plans with timed legs, per-stretch crowding, departure-time shifts, route catalogue, operator hotspots with suggested extra buses, ML insights and validation summary. Details, field meanings and how to connect an Express/Vite frontend: `docs/API.md`. Contract tests: `pytest tests/test_api.py`.
 
Main endpoint: `GET /api/plan?origin=...&destination=...&time=HH:MM` with optional `day_type` (`weekday` or `weekend`), `preference` (`fastest`, `balanced` or `comfortable`) and `limit`. `origin` and `destination` are a stop name or `lat,lng`.
 
The repo includes the processed tables in `data/processed/`, so the API starts without the raw ticket file. The raw data is only needed to re-run `run_pipeline.py`. To fit a 512 MB free host, the API loads the crowd table with only the columns it needs and compact data types.
 
## The stack (all Python)
pandas + NumPy (data and load maths) · RapidFuzz (fuzzy stop names) · scikit-learn `LinearRegression` (baseline model) · Matplotlib + seaborn (charts) · SciPy KD-tree (walking links) · FastAPI + uvicorn (backend API) · SQLAlchemy with SQLite or MySQL (optional storage) · Streamlit + folium (analyst/demo app) · Jupyter notebooks (learning and explaining) · Docker + Render (deployment).
 
## Notebooks (read these first)
| Notebook | What you learn |
|---|---|
| `01_explore_tickets` | What a ticket row means, data quality checks, daily and hourly rhythm |
| `02_match_stops_and_resolve` | GTFS patterns, fuzzy stop-name matching, boarding/alighting positions |
| `03_crowd_model` | Flow with `np.cumsum`, shrinkage, calibration, crowd levels, heatmap |
| `04_validation_and_ml` | Time-based hold-out: our model vs linear regression vs gradient boosting, R², sensitivity |
| `05_sql_and_planner` | SQL queries with pandas (SQLite or MySQL), the journey planner |
 
## Code map (small, readable modules in `crowd/`)
`text.py` name cleaning and crowd levels · `ingest.py` load + profile · `gtfs.py` route patterns · `matching.py` fuzzy matching · `trips.py` ticket positions · `flow.py` ticketed flow per scheduled trip · `load.py` running-sum demo · `model.py` crowd table · `validate.py` hold-out, regression, gradient boosting · `db.py` SQL helpers. `crowd/ml.py` is the ML suite and thin-cell fallback; `planner/engine.py` is the journey planner; `api/` is the FastAPI backend; `app.py` is the Streamlit UI; `config.py` holds every assumption.
 
## Method in one paragraph
Real-data facts drive the method: half the tickets have no vehicle number (so no trips) and the file is a thin sample of ridership (about 1 passenger per scheduled trip per day). So we (1) match ticket stop names to the route's own GTFS stops (composite names handled as aliases; 93.5% matched), (2) take direction from the route name (`8UP` / `8ADOWN`), (3) compute ticketed flow along each route with a running sum of boardings minus alightings (`np.cumsum`), (4) divide by days and **scheduled GTFS trips** to get ticketed passengers per bus per stretch, (5) shrink thinly observed cells toward the route average, (6) scale to riders with a stated calibration factor and compare with assumed capacity to get seats / standing / crowded, plus a confidence flag. Validation is a time-based hold-out (week 2 predicts week 3): our model R² 0.78 vs linear regression 0.21 and gradient boosting 0.75. Details: `docs/TECHNICAL_NOTE.md`; all constants are in `config.py`.
 
## Assumptions that are NOT in the data
Seated and crush capacity (AC 33/60, non-AC 36/70), the "standing" threshold (75% of crush) and the coverage calibration (90th percentile of weekday-peak stretch loads = standing limit, giving a factor of about 24.7). They are in `config.py`; `outputs/sensitivity.csv` shows how the level shares move. Rankings do not depend on them.
 
## Limitations (summary)
Typical, not live, crowding. No seasons or festivals (one month). The ticket file is a thin sample and free-fare/pass travellers appear to be missing, so absolute labels depend on a stated calibration; 62% of cells are low confidence and flagged as such. One stop pattern per route is used. About 5% of name occurrences stay unmatched (`outputs/unmatched_names.csv`). See the technical note for the least reliable estimates.
 
## Repo layout
`config.py` assumptions · `crowd/` pipeline modules · `notebooks/` · `run_pipeline.py` · `app.py` Streamlit UI · `planner/` engine · `api/` FastAPI backend · `Dockerfile` deployment image · `tests/` · `docs/` note, proposal, demo script, checklist · `outputs/` generated reports.
 
## Credits
Open-source: pandas, NumPy, SciPy, scikit-learn, RapidFuzz, Matplotlib, seaborn, Streamlit, folium (Leaflet), SQLAlchemy, Jupyter, OpenStreetMap tiles. Data: Transport Stack Hackathon ticket data and Delhi static GTFS (delhi.transportstack.in). AI tools: Claude (Anthropic) assisted with code and documentation; the team reviewed and is responsible for the submission.
 
