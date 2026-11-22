"""CrowdWise-compatible HTTP API (FastAPI).   Run:  uvicorn api.main:app --port 8000     (docs at /docs)
Implements the 8-endpoint contract in docs/API.md on the real Delhi data."""
import os, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from api.engine import TransitEngine

t0 = time.perf_counter()
engine = TransitEngine()
print(f"[CrowdWise API] Engine ready in {round((time.perf_counter() - t0) * 1000)}ms ({len(engine.patterns)} route-directions, {len(engine.stops)} stops, {len(engine.cells)} crowd cells, ML fallback = {engine.ml['active_fallback_model']})", flush=True)

app = FastAPI(title="CrowdWise Delhi bus crowding API", version="1.0",
              description="Crowdedness-aware bus journey planning for Delhi. Crowd levels are typical (by time band and day type), estimated from October 2026 e-ticket data; not live.")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET", "POST", "OPTIONS"], allow_headers=["*"], max_age=86400)

def err(status, code, message, details=None):
    return JSONResponse(status_code=status, content=dict(error=dict(code=code, message=message, **({"details": details} if details else {}))))

def to_int(v, default):
    try: return int(v)
    except (TypeError, ValueError): return default

@app.get("/")
def root():
    return dict(service="CrowdWise Delhi bus crowding API", docs="/docs", health="/api/health")

@app.get("/api/health")
@app.get("/api/meta")
def health():
    return engine.getHealth()

@app.get("/api/stops")
def stops(q: str = "", limit: int = 15):
    return engine.searchStops(q, limit)

@app.get("/api/plan")
def plan(request: Request):
    """origin/destination = stop name or 'lat,lng' (or olat,olon / dlat,dlon); time=HH:MM; day_type=weekday|weekend; preference=fastest|balanced|comfortable; limit."""
    qp = request.query_params
    origin, destination = qp.get("origin", ""), qp.get("destination", "")
    if not origin and qp.get("olat") and qp.get("olon"): origin = f"{qp['olat']},{qp['olon']}"
    if not destination and qp.get("dlat") and qp.get("dlon"): destination = f"{qp['dlat']},{qp['dlon']}"
    if not origin or not destination:
        return err(400, "MISSING_PARAMS", "Both origin and destination query parameters are required.", dict(required=["origin", "destination"]))
    res = engine.planJourney(origin, destination, qp.get("time", "18:00"), qp.get("day_type", qp.get("daytype", "weekday")), qp.get("preference", qp.get("mode", "balanced")), to_int(qp.get("limit"), 5))
    if res.get("error"):
        return JSONResponse(status_code=400 if res["error"]["code"] == "BAD_TIME" else 404, content=res)
    return res

@app.get("/api/routes")
def routes(q: str = "", limit: int = 100, offset: int = 0):
    return engine.listRoutes(q, limit, offset)

@app.get("/api/routes/{route_id}/crowd")
def route_crowd(route_id: str, request: Request):
    qp = request.query_params
    day = "weekend" if qp.get("day_type", qp.get("daytype", "weekday")) == "weekend" else "weekday"
    d = qp.get("direction_id")
    out = engine.getRouteCrowd(route_id, day, to_int(qp.get("hour"), 18), to_int(d, None) if d is not None else None)
    if out is None:
        return err(404, "ROUTE_NOT_FOUND", f"Route '{route_id}' was not found. Query /api/routes to list available route IDs.", dict(route_id=route_id))
    return out

@app.get("/api/operator/hotspots")
@app.get("/api/operator")
def operator(request: Request):
    qp = request.query_params
    return engine.getOperatorHotspots(qp.get("day_type", qp.get("daytype", "weekday")), to_int(qp.get("hour"), 9), to_int(qp.get("limit"), 20), qp.get("min_confidence", "low"))

@app.get("/api/ml/insights")
def ml_insights():
    return {k: v for k, v in engine.ml.items()}

@app.get("/api/validation/summary")
def validation_summary():
    return engine.getValidationSummary()

@app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
def not_found(path: str, request: Request):          # unknown /api/* is always JSON, never HTML
    return err(404, "ENDPOINT_NOT_FOUND", f"Unknown API endpoint: {request.method} {request.url.path}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
