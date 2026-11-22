import os, sys
from pathlib import Path
import numpy as np, pytest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATA_MODE", "synthetic")
from crowd.text import norm_name, norm_route, level_of, confidence_of, band_of
from crowd.load import load_along_trip

def test_norm_name_variants():
    assert norm_name("ANAND VIHAR I.S.B.T.") == norm_name("Anand Vihar ISBT")
    assert norm_name("Rohini Sec 7 ") == norm_name("rohini sector 7")
    assert norm_name(None) == "" and norm_name(float("nan")) == ""
    assert norm_name("Nehru Pl Metro Stn").endswith("metro station")

def test_norm_route():
    assert norm_route(" 0534 ") == "534" and norm_route("534a") == "534A"

def test_levels_and_confidence():
    assert list(level_of([10, 45, 80], [0, 0, 0])) == ["seats", "standing", "crowded"]
    assert level_of(40, 1) == "standing" and level_of(30, 1) == "seats"     # AC buses have fewer seats
    assert list(confidence_of([5, 50, 300])) == ["low", "medium", "high"]
    assert band_of(8) == "am_peak" and band_of(18) == "pm_peak" and band_of(23) == "evening"

def test_running_load():
    """2 pax board at 0 and alight at 2; 1 pax boards at 1 and alights at 3 (4 stops => 3 stretches)."""
    assert list(load_along_trip(np.array([0, 1]), np.array([2, 3]), np.array([2, 1]), n_stops=4)) == [2, 3, 1]

ready = (ROOT / "data/synthetic/processed/crowd_segments.parquet").exists()
@pytest.mark.skipif(not ready, reason="run `DATA_MODE=synthetic python run_pipeline.py` first")
def test_planner_end_to_end():
    from planner.engine import Planner
    r = Planner().plan((28.6469, 77.3160), (28.6315, 77.2167), "18:00", "weekday", "fast")
    assert r["options"], "expected at least one option"
    o = r["options"][0]
    assert o["crowd_level"] in {"seats", "standing", "crowded"} and o["confidence"] in {"low", "medium", "high"}

@pytest.mark.skipif(not ready, reason="run the synthetic pipeline first")
def test_streamlit_app_runs():
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=90).run()
    assert not at.exception
    at.button[0].click().run()
    assert not at.exception
