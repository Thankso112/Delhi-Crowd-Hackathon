"""
REST API for the CrowdWise Delhi frontend.   Run:   uvicorn planner.app:app --host 0.0.0.0 --port 8000

Everything is loaded ONCE at start-up (src/serving.py), so each request is a quick lookup (a /api/plan takes ~0.05-0.1 s).
Errors are always JSON:  {"error": {"code": ..., "message": ..., "details": {...}}}   - never an HTML page.
"""
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import config
from src.serving import CrowdStore
from src.planner import Planner

STATE = {}


@asynccontextmanager
async def lifespan(app):
    t = time.time()
    STATE["store"] = CrowdStore()
    STATE["planner"] = Planner(STATE["store"])
    STATE["loaded_in_s"] = round(time.time() - t, 1)
    yield


app = FastAPI(title="CrowdWise Delhi - crowd-aware bus planner API", version="1.0", lifespan=lifespan)
# CORS open to every origin; allow_private_network lets a public https page (e.g. an AI Studio preview) call a server on localhost
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"], expose_headers=["*"], allow_private_network=True)


class ApiError(Exception):
    def __init__(self, status, code, message, **details):
        self.status, self.code, self.message, self.details = status, code, message, details


@app.exception_handler(ApiError)
async def _api_error(_, e: ApiError):
    return JSONResponse(status_code=e.status, content={"error": {"code": e.code, "message": e.message, "details": e.details}})


def _day(v):
    return "weekend" if str(v or "weekday").lower() in ("weekend", "sat", "sun", "holiday") else "weekday"


def _int(v, default, lo=None, hi=None):
    try:
        x = int(float(v))
    except (TypeError, ValueError):
        return default
    return x if lo is None else max(lo, min(hi, x))


# ------------------------------------------------------------------ endpoints
@app.get("/api/health")
@app.get("/api/meta")
def health():
    h = STATE["store"].health(); h["startup_seconds"] = STATE["loaded_in_s"]
    return h


@app.get("/api/stops")
def stops(q: str = "", limit: int = 15):
    return STATE["store"].search_stops(q, limit)                 # empty q -> {"count": 0, "stops": []}


@app.get("/api/plan")
def plan(origin: str = "", destination: str = "", time: str = "18:00", day_type: str = "", daytype: str = "", preference: str = "balanced",
         olat: float = None, olon: float = None, dlat: float = None, dlon: float = None):
    s, pl = STATE["store"], STATE["planner"]
    o_text = origin or (f"{olat},{olon}" if olat is not None and olon is not None else "")
    d_text = destination or (f"{dlat},{dlon}" if dlat is not None and dlon is not None else "")
    if not o_text or not d_text:
        raise ApiError(400, "MISSING_PARAMS", "Both 'origin' and 'destination' are required (stop name, stop_id or 'lat,lon').")
    try:
        hh, mm = (int(x) for x in time.split(":")[:2]); assert 0 <= hh < 24 and 0 <= mm < 60
    except Exception:
        raise ApiError(400, "BAD_TIME", "time must look like HH:MM (24-hour), e.g. 18:00.", time=time)
    o, d = s.resolve_place(o_text), s.resolve_place(d_text)
    for label, r, txt in (("origin", o, o_text), ("destination", d, d_text)):
        if r is None:
            raise ApiError(404, "STOP_NOT_FOUND", f"No stop matched the {label} '{txt}'. Use /api/stops?q= to search.", **{label: txt})
    pref = preference if preference in ("balanced", "fastest", "comfortable") else "balanced"
    dt = _day(day_type or daytype)
    r = pl.plan((o["lat"], o["lng"]), (d["lat"], d["lng"]), f"{hh:02d}:{mm:02d}", dt, pref)
    return dict(query=dict(origin=o_text, destination=d_text, time=f"{hh:02d}:{mm:02d}", hour=hh, day_type=dt, preference=pref),
                resolved_origin=o, resolved_destination=d, options=r["options"], departure_shifts=r["departure_shifts"], note=r["note"])


@app.get("/api/routes")
def routes(q: str = "", limit: int = 100, offset: int = 0):
    return STATE["store"].list_routes(q, limit, offset)


@app.get("/api/routes/{route_id}/crowd")
def route_crowd(route_id: str, day_type: str = "", daytype: str = "", hour: int = 18, direction_id: int = None):
    s = STATE["store"]
    rn = s.find_route(route_id, direction_id)
    if rn is None:
        raise ApiError(404, "ROUTE_NOT_FOUND", f"Route '{route_id}' was not found. Query /api/routes to list available route IDs.", route_id=route_id)
    return s.route_crowd(rn, _day(day_type or daytype), _int(hour, 18, 0, 23))


@app.get("/api/operator/hotspots")
@app.get("/api/operator")
def hotspots(day_type: str = "", daytype: str = "", hour: str = "9", limit: int = 20, min_confidence: str = "low"):
    h = None if str(hour).lower() == "all" else _int(hour, 9, 0, 23)
    return STATE["store"].hotspots(_day(day_type or daytype), h, limit, min_confidence if min_confidence in ("low", "medium", "high") else "low")


@app.get("/api/operator/network-profile")
def network_profile(day_type: str = "", daytype: str = ""):
    return STATE["store"].network_profile(_day(day_type or daytype))


@app.get("/api/validation/summary")
def validation_summary():
    return STATE["store"].validation_summary()


@app.get("/api/ml/insights")
def ml_insights():
    return STATE["store"].ml_insights()


@app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
def unknown(path: str, request: Request):
    raise ApiError(404, "ENDPOINT_NOT_FOUND", f"Unknown API endpoint: {request.method} {request.url.path}")
