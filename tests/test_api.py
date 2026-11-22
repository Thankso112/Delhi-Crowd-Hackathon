"""Python port of the frontend team's api.test.ts, plus error-contract checks. Runs against the REAL processed data
(run `python run_pipeline.py` first); skipped when it is missing."""
import sys
from pathlib import Path
import pytest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import config
ready = (config.PROC / "ml_insights.json").exists() and config.MODE == "real"
pytestmark = pytest.mark.skipif(not ready, reason="needs real processed data (python run_pipeline.py)")

@pytest.fixture(scope="module")
def c():
    from fastapi.testclient import TestClient
    from api.main import app
    return TestClient(app)

LEVELS = {"seats_available", "standing_room", "crowded"}
SOURCES = {"observed_tickets", "ml_fallback", "route_average"}

def test_health(c):
    h = c.get("/api/health").json()
    assert h["status"] == "ok" and h["ready"] is True
    assert h["counts"]["routes"] >= 20 and h["counts"]["stops"] >= 40 and h["counts"]["crowd_cells"] > 1000
    assert {"eticket_capture_rate", "pass_holder_multiplier", "effective_scale_factor", "capacity_ac", "capacity_nonac"} <= set(h["calibration"])
    assert c.get("/api/meta").json()["status"] == "ok"

def test_stops_autocomplete(c):
    e = c.get("/api/stops", params={"q": "", "limit": 15}).json()
    assert e["count"] == 15 and e["stops"][0]["stop_id"] and isinstance(e["stops"][0]["lat"], float) and isinstance(e["stops"][0]["lng"], float)
    d = c.get("/api/stops", params={"q": "delhi", "limit": 15}).json()
    assert d["count"] >= 2 and any("delhi" in s["stop_name"].lower() for s in d["stops"])
    a = c.get("/api/stops", params={"q": "Kashmiri Gate", "limit": 5}).json()
    assert a["count"] >= 1 and "Kashmere Gate" in a["stops"][0]["stop_name"]

def test_plan_comfortable(c):
    r = c.get("/api/plan", params=dict(origin="Anand Vihar", destination="Connaught Place", time="08:00", day_type="weekday", preference="comfortable"))
    assert r.status_code == 200
    j = r.json(); assert len(j["options"]) >= 2
    o = j["options"][0]
    assert o["prediction_source"] in SOURCES and isinstance(o["ticket_count"], int) and o["max_crowd_level"] in LEVELS
    assert len(o["legs"]) >= 1 and len(o["legs"][0]["polyline"]) >= 2 and len(o["legs"][0]["segments"]) >= 1
    assert {"resolved_origin", "resolved_destination", "departure_shifts", "note", "query"} <= set(j)

def test_departure_shifts(c):
    j = c.get("/api/plan", params=dict(origin="Anand Vihar", destination="Connaught Place", time="18:30", day_type="weekday", preference="balanced")).json()
    assert len(j["options"]) >= 1 and isinstance(j["departure_shifts"], list) and len(j["departure_shifts"]) >= 1
    assert j["departure_shifts"][0]["improves_crowding"] is True

def test_routes_and_route_crowd(c):
    lst = c.get("/api/routes", params={"q": "", "limit": 50, "offset": 0}).json()
    assert lst["total"] >= 20
    first = lst["routes"][0]
    by_id = c.get(f"/api/routes/{first['route_id']}/crowd", params={"day_type": "weekday", "hour": 8}).json()
    assert len(by_id["stops"]) == first["num_stops"] and len(by_id["segments"]) == first["num_stops"] - 1
    assert by_id["segments"][0]["prediction_source"] in SOURCES
    name = next(r["route_short_name"] for r in c.get("/api/routes", params={"q": "DOWN", "limit": 5}).json()["routes"])
    assert c.get(f"/api/routes/{name}/crowd", params={"day_type": "weekday", "hour": 18}).json()["route_short_name"] == name

def test_operator_hotspots(c):
    r = c.get("/api/operator/hotspots", params={"day_type": "weekday", "hour": 8, "limit": 25}).json()
    h = r["hotspots"]
    assert r["count"] == 25 and h[0]["rank"] == 1 and h[0]["load_ratio"] >= h[1]["load_ratio"]
    assert isinstance(h[0]["ticket_count"], int) and h[0]["prediction_source"] in SOURCES and isinstance(h[0]["suggested_extra_buses_hr"], int)

def test_ml_insights(c):
    m = c.get("/api/ml/insights").json()
    assert m["train_rows"] > 0 and m["test_rows"] > 0 and len(m["regression_models"]) == 4 and len(m["classification_models"]) == 2
    cm = m["confusion_matrix"]; assert len(cm["labels"]) == 3 and len(cm["matrix"]) == 3 and len(cm["matrix"][0]) == 3
    fs = m["fallback_stats"]; assert fs["total_segments"] > 0 and fs["ml_fallback_segments"] > 0
    assert len(m["feature_importance"]) >= 4 and len(m["concepts"]) >= 4

def test_validation_summary(c):
    v = c.get("/api/validation/summary").json()
    assert "holdout" in v and "calibration" in v and len(v["limitations"]) >= 3

def test_error_contract(c):
    r = c.get("/api/plan", params={"origin": "x"}); assert r.status_code == 400 and r.json()["error"]["code"] == "MISSING_PARAMS"
    r = c.get("/api/plan", params={"origin": "zzzzqqq", "destination": "yyyyxxx"}); assert r.status_code == 404 and "error" in r.json()
    r = c.get("/api/routes/NOPE-ROUTE/crowd"); assert r.status_code == 404 and r.json()["error"]["code"] == "ROUTE_NOT_FOUND"
    r = c.get("/api/nope"); assert r.status_code == 404 and r.json()["error"]["code"] == "ENDPOINT_NOT_FOUND"
    r = c.options("/api/plan", headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "GET"}); assert r.headers.get("access-control-allow-origin") in ("*", "http://localhost:3000")
