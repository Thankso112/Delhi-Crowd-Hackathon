# HANDOFF - final state

## What this repository is
V4 pipeline (repository root) + the archived V2 build (`legacy_v2/`). The finished tables and models are in `outputs/`, so the API starts without the raw data.

## Run
    pip install -r requirements.txt
    uvicorn planner.app:app --port 8000          # http://localhost:8000/api/health
    python -m pytest -q tests                    # 16 tests
Rebuilding everything from raw data (not needed for the API): put `tickets.csv` and the GTFS `.txt` files in `data/raw/`, then `python run_all.py --check` and `python run_all.py` (about 25-35 minutes).

## Deploy (Google Cloud)
The root `Dockerfile` serves `planner.app:app` on `$PORT`. The service needs about 1-2 GiB of memory (the hourly crowd table has 1.77M rows).

## Known limits
- Typical, not live, crowding; one month of data; the ticket file is a sample (mobile e-tickets), so absolute labels depend on the calibration in `config.py`.
- At route-hour level a simple shrinkage estimate beat all ML models (`docs/MODEL_COMPARISON.md`); ML is a fallback for thin cells and its advantage there carries a selection caveat (`outputs/ml_metrics.json`, `caveats`).
- Never run on Python 3.14; use 3.10-3.12.