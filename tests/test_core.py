"""
Tests.  Run:  python -m pytest -q tests
 * the UNIT tests use tiny hand-made data (answers worked out by hand) and always run
 * the API tests need the pipeline outputs (python run_all.py) and are skipped if those are missing
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config
from src.common import norm_name, norm_route, tier_of, confidence_of, capacity_of, to_percentile, level_of_pct
from src import crowd, gtfs, trips, tickets

# ---------------------------------------------------------------- text cleaning
def test_norm_name_variants():
    assert norm_name("ANAND VIHAR I.S.B.T.") == norm_name("Anand Vihar ISBT")
    assert norm_name("Rohini Sec 7 ") == norm_name("rohini sector 7")
    assert norm_name(None) == "" and norm_name(float("nan")) == ""

def test_norm_route():
    assert norm_route(" 0534 ") == "534" and norm_route("8adown") == "8ADOWN" and norm_route("433UP") == "433UP"

# ---------------------------------------------------------------- calibration and tiers
def test_scale_math():
    assert config.SCALE["base"] == pytest.approx(config.PASS_MULTIPLIER["base"] / config.EKT_CAPTURE_RATE["base"])
    assert config.SCALE["low"] < config.SCALE["base"] < config.SCALE["high"]          # sensitivity scenarios are ordered

def test_tier_boundaries():
    ac, nonac = config.CAPACITY["ac"], config.CAPACITY["nonac"]
    assert tier_of(ac["seats"], 1) == "seats_available" and tier_of(ac["seats"] + 1, 1) == "standing_room"
    assert tier_of(0.75 * ac["crush"], 1) == "standing_room" and tier_of(0.75 * ac["crush"] + 1, 1) == "crowded"
    assert tier_of(nonac["seats"], 0) == "seats_available" and tier_of(nonac["seats"] + 1, 0) == "standing_room"
    assert list(capacity_of([1, 0])) == [ac["crush"], nonac["crush"]]

def test_confidence_and_levels():
    assert list(confidence_of([5, 15, 50])) == ["low", "medium", "high"]
    assert list(level_of_pct([10, 60, 95])) == ["low", "medium", "high"]
    assert to_percentile([5], [1, 2, 3, 4, 5, 6, 7, 8, 9, 10])[0] == pytest.approx(50.0)

# ---------------------------------------------------------------- holidays
def test_holiday_detection():
    days = pd.date_range("2026-10-05", periods=5).strftime("%Y-%m-%d").tolist()            # Mon-Fri
    rows = [d for d in days for _ in range(100)] + ["2026-10-06"] * 0                     # all normal
    df = pd.DataFrame({"date": rows})
    df = pd.concat([df[df.date != "2026-10-07"], df[df.date == "2026-10-07"].head(40)])     # Wednesday sells only 40% -> holiday-like
    off = tickets.detect_offdays(df)
    assert list(off.date) == ["2026-10-07"]

# ---------------------------------------------------------------- the running-load idea (NULL-vehicle tickets are used like any other)
PAT = pd.DataFrame({"route_n": ["R1UP"] * 4, "idx": [0, 1, 2, 3], "cum_sec": [0, 600, 1200, 1800],
                    "stop_name": ["A", "B", "C", "D"], "stop_id": list("abcd"), "lat": 28.6, "lon": 77.2})
PAT["name_n"] = PAT.stop_name.str.lower()

def _tix(rows):
    d = pd.DataFrame(rows, columns=["route_n", "b", "a", "pax", "ts", "daytype"]); d["ts"] = pd.to_datetime(d.ts); return d

def test_explode_demand_counts_every_stretch_travelled():
    # 2 passengers ride stops 0->2 (stretches 0,1);  1 passenger rides stops 1->3 (stretches 1,2). No vehicle numbers anywhere.
    t = _tix([("R1UP", 0, 2, 2, "2026-10-05 08:00:00", "weekday"), ("R1UP", 1, 3, 1, "2026-10-05 08:10:00", "weekday")])
    d = crowd.explode_demand(t, PAT).set_index(["hour", "pos"])
    assert d.loc[(8, 0), "pax_sum"] == 2 and d.loc[(8, 1), "pax_sum"] == 3 and d.loc[(8, 2), "pax_sum"] == 1

def test_time_shift_along_the_route():
    t = _tix([("R1UP", 0, 3, 1, "2026-10-05 08:50:00", "weekday")])      # boards 08:50; stretch 1 at 09:00 and stretch 2 at 09:10 (timetable: 10 min per stretch)
    d = crowd.explode_demand(t, PAT).set_index(["hour", "pos"])
    assert (8, 0) in d.index and (9, 1) in d.index and (9, 2) in d.index        # the ride crosses into the next hour

def test_crowd_table_small():
    t = _tix([("R1UP", 0, 3, 60, "2026-10-05 08:00:00", "weekday")])
    supply = pd.DataFrame({"route_n": "R1UP", "hour": 8, "pos": [0, 1, 2], "n_sched": 1})
    attrs = pd.DataFrame({"route_n": ["R1UP"], "route": ["R1UP"], "is_ac": [1], "n_tickets": [1]})
    out = crowd.build_crowd_tables(crowd.explode_demand(t, PAT), supply, {"weekday": 1, "weekend": 1}, PAT, attrs)
    ct = out["crowd_table"]
    wk = ct[(ct.daytype == "weekday") & (ct.hour == 8)]
    assert len(wk) == 3 and (wk.load_ratio <= config.LOAD_CAP_RATIO + 1e-9).all()       # one row per stretch, loads capped
    assert (ct[ct.daytype == "weekend"].ticket_count == 0).all()                         # no weekend tickets -> zero, not missing
    assert set(ct.crowd_level) <= {"seats_available", "standing_room", "crowded"}
    assert wk.est_load.max() > ct[ct.daytype == "weekend"].est_load.max()                # a busy bus beats an empty one

# ---------------------------------------------------------------- stop matching and locating tickets
def test_alias_matching_splits_composite_names():
    pat = pd.DataFrame({"route_n": ["R1UP"] * 2, "stop_name": ["Laxmi Nagar Metro Station / Laxmi Nagar", "Azadpur"], "idx": [0, 1]})
    pat["name_n"] = pat.stop_name.map(norm_name)
    counts = pd.DataFrame({"route_raw": ["R1UP"] * 2, "name": ["Laxmi Nagar", "Azad Pur"], "n": [10, 5]})
    m = gtfs.match_stop_names(counts, pat).set_index("name")
    assert m.loc["Laxmi Nagar", "method"] == "exact_route" and m.loc["Laxmi Nagar", "gtfs_name_n"] == pat.name_n[0]
    assert m.loc["Azad Pur", "gtfs_name_n"] == "azadpur"                                  # spacing difference still matches

def test_locate_tickets_handles_missing_end_stop():
    sm = pd.DataFrame({"route_raw": ["R1UP"] * 3, "name": ["A", "C", "B"], "gtfs_name_n": ["a", "c", "b"]})
    tk = pd.DataFrame({"route_raw": ["R1UP", "R1UP"], "start_name": ["A", "B"], "end_name": ["C", None], "pax": [1, 1], "vehicle": [None, None],
                       "ts": pd.to_datetime(["2026-10-05 08:00", "2026-10-05 08:05"]), "is_ac": [1, 1], "date": "2026-10-05", "hour": 8, "dow": 0, "daytype": "weekday"})
    out, rep = trips.locate_tickets(tk, sm, PAT)
    assert len(out) == 2 and list(out.b) == [0, 1] and out.a[0] == 2                       # NULL-vehicle tickets are kept
    assert out.imputed_end.tolist() == [False, True] and (out.a > out.b).all()

# ---------------------------------------------------------------- the API (needs the pipeline outputs)
ready = (config.OUT / "crowd_table.parquet").exists() and all((config.OUT / "artifacts" / f"{n}.parquet").exists() for n in ("route_patterns", "route_hourly", "route_attrs"))
needs_data = pytest.mark.skipif(not ready, reason="run `python run_all.py` first to create the crowd table")

@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from planner.app import app
    with TestClient(app) as c:
        yield c

@needs_data
def test_api_health_and_calibration(client):
    h = client.get("/api/health").json()
    assert h["ready"] and h["counts"]["stops"] > 1000 and h["calibration"]["effective_scale_factor"] == pytest.approx(config.SCALE["base"], abs=0.01)

@needs_data
def test_api_empty_stop_query_is_empty_list_not_error(client):
    r = client.get("/api/stops?q="); assert r.status_code == 200 and r.json()["stops"] == []
    assert client.get("/api/stops?q=nehru").json()["count"] > 0

@needs_data
def test_api_plan_shape_and_errors(client):
    r = client.get("/api/plan", params=dict(origin="Anand Vihar", destination="Connaught Place", time="18:00", day_type="weekday")).json()
    assert r["options"] and len(r["departure_shifts"]) == 2
    o = r["options"][0]
    for k in ("option_id", "rank", "tag", "total_duration_min", "max_crowd_level", "max_load_ratio", "confidence", "prediction_source", "ticket_count", "legs"):
        assert k in o
    assert o["prediction_source"] in ("observed_tickets", "ml_fallback", "route_average") and "ticket_count" in o["legs"][0]
    assert client.get("/api/plan?origin=Nehru Place").status_code == 400
    assert client.get("/api/plan?origin=zzzzqqq&destination=Nehru Place").status_code == 404

@needs_data
def test_api_routes_hotspots_validation_ml(client):
    assert client.get("/api/routes?limit=3").json()["count"] == 3
    h = client.get("/api/operator/hotspots?hour=9&limit=10").json()["hotspots"]
    assert len({x["route_short_name"] for x in h}) == len(h)                                   # one row per route
    assert client.get("/api/routes/NOT_A_ROUTE/crowd").status_code == 404
    assert "dataset" in client.get("/api/validation/summary").json() and "split_method" in client.get("/api/ml/insights").json()
    assert client.get("/api/nope").status_code == 404 and client.get("/api/nope").headers["content-type"].startswith("application/json")

@needs_data
def test_api_cors_open_and_private_network(client):
    r = client.options("/api/plan", headers={"Origin": "https://example.ai.studio", "Access-Control-Request-Method": "GET", "Access-Control-Request-Private-Network": "true"})
    assert r.status_code == 200 and r.headers["access-control-allow-origin"] == "*"
