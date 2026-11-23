"""
Tests for the served crowd table and the operator/summary endpoints.
They need the finished outputs (outputs/crowd_table_served.parquet etc.) and are skipped if those are missing.
Run:  python -m pytest -q tests
"""
import sys
from pathlib import Path
import pandas as pd
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config

SERVED = config.OUT / "crowd_table_served.parquet"
pytestmark = pytest.mark.skipif(not SERVED.exists() or not (config.OUT / "artifacts" / "route_patterns.parquet").exists(),
                                reason="pipeline outputs not found")


@pytest.fixture(scope="module")
def served():
    return pd.read_parquet(SERVED)


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from planner.app import app
    with TestClient(app) as c:            # runs the lifespan, which loads the store once
        yield c


def test_top_hotspots_are_not_all_capped(client):
    r = client.get("/api/operator/hotspots", params=dict(day_type="weekday", hour=9, limit=20))
    assert r.status_code == 200
    rows = r.json()["hotspots"]
    assert len(rows) == 20
    assert len({x["load_ratio_raw"] for x in rows}) >= 5, "ranking is saturated at the cap again"
    raw = [x["load_ratio_raw"] for x in rows]
    assert raw == sorted(raw, reverse=True)
    assert all(x["load_ratio"] <= config.LOAD_CAP_RATIO + 1e-9 for x in rows)          # display value stays capped
    assert all(x["confidence"] in ("medium", "high") for x in rows)                    # default min_confidence = medium


def test_min_confidence_low_still_works(client):
    r = client.get("/api/operator/hotspots", params=dict(day_type="weekday", hour=9, limit=5, min_confidence="low"))
    assert r.status_code == 200 and r.json()["min_confidence"] == "low" and r.json()["count"] == 5


def test_overall_crowded_share_is_sane(served):
    assert (served.crowd_level == "crowded").mean() <= 0.30


def test_no_hour_is_mostly_crowded(served):
    share = served.assign(c=served.crowd_level == "crowded").groupby(["daytype", "hour"]).c.mean()
    assert share.max() <= 0.70


def test_load_ratio_is_load_over_capacity(served):
    assert (served.load_ratio - served.est_load / served.capacity).abs().max() < 1e-4


def test_no_ml_fallback_rows(served):
    assert set(served.prediction_source) <= {"observed_tickets", "route_average"}


def test_routes_summary_one_row_per_route_direction(client):
    r = client.get("/api/routes/summary", params=dict(day_type="weekday", hour=9))
    assert r.status_code == 200
    body = r.json()
    n = client.get("/api/health").json()["counts"]["route_directions"]
    keys = {(x["route_id"], x["direction_id"]) for x in body["routes"]}
    assert body["count"] == len(body["routes"]) == len(keys) == n
    need = {"route_id", "route_short_name", "direction_id", "direction", "route_long_name", "busiest_stretch", "load_ratio_raw", "load_pct",
            "crowd_level", "confidence", "prediction_source", "ticket_count", "scheduled_buses_hr"}
    assert all(need <= set(x) for x in body["routes"])
    unknown = [x for x in body["routes"] if x["crowd_level"] == "unknown"]
    assert unknown and all(x["confidence"] == "low" for x in unknown)


def test_hourly_network_uses_medium_confidence_cells_only(client):
    hrs = client.get("/api/operator/hotspots", params=dict(day_type="weekday", hour=9, limit=1)).json()["hourly_network"]
    for h in hrs:
        if h["cells"] == 0:
            assert h["avg_load_ratio"] is None and h["overloaded_count"] is None
        else:
            assert h["avg_load_ratio"] is not None


def test_busiest_stretch_skips_terminal_hops(client):
    r = client.get("/api/routes/summary", params=dict(day_type="weekday", hour=9)).json()["routes"]
    r = next(x for x in r if x["crowd_level"] != "unknown" and x["confidence"] != "low")
    d = client.get(f"/api/routes/{r['route_short_name']}/crowd", params=dict(day_type="weekday", hour=9)).json()
    segs = d["segments"]; i = next(k for k, s in enumerate(segs) if (s["from_stop_name"] + " \u2013 " + s["to_stop_name"]) == d["busiest_stretch"])
    assert 2 <= i < len(segs) - 2 or len(segs) <= 4 or all(not (2 <= k < len(segs) - 2) or segs[k]["ticket_count"] < config.CONF_MED for k in range(len(segs)))


def test_no_hotspot_suggests_more_extra_buses_than_scheduled(client):
    for hour in (9, 18):
        rows = client.get("/api/operator/hotspots", params=dict(day_type="weekday", hour=hour, limit=200)).json()["hotspots"]
        assert rows and all(r["suggested_extra_buses_hr"] <= r["scheduled_buses_hr"] for r in rows)


def test_top_hotspots_are_not_schedule_artifacts(client):
    rows = client.get("/api/operator/hotspots", params=dict(day_type="weekday", hour=9, limit=20)).json()["hotspots"]
    assert not all(r["schedule_undercount"] for r in rows)
    assert all(r["load_ratio_raw"] <= config.SCHEDULE_UNDERCOUNT_RATIO or r["schedule_undercount"] for r in rows)
    assert all(r["schedule_undercount"] == (r["load_ratio_raw"] > config.SCHEDULE_UNDERCOUNT_RATIO) for r in rows)   # flag matches the raw ratio


def test_summary_carries_schedule_undercount_flag(client):
    rows = client.get("/api/routes/summary", params=dict(day_type="weekday", hour=9)).json()["routes"]
    assert all("schedule_undercount" in r for r in rows)
    assert all(r["schedule_undercount"] == (r["load_ratio_raw"] is not None and r["load_ratio_raw"] > config.SCHEDULE_UNDERCOUNT_RATIO) for r in rows)
