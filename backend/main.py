"""
TS-11 Stampede Window Predictor — FastAPI backend

Start: uvicorn main:app --host 0.0.0.0 --port $PORT
"""
import asyncio
import csv
import io
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import uvicorn

from simulator import (
    get_all_readings, get_corridor_reading, get_corridors,
    get_corridor_config, CORRIDOR_BASELINES, DENSITY_DANGER_THRESHOLD,
)
from database import init_db, insert_alert, ack_alert, get_alerts, log_cpi, get_events, get_alert_by_id
from replay_data import REPLAY_FRAMES

# ── ML predictor (optional — graceful if models not yet trained) ──────────────
try:
    from ml.predictor import predict as ml_predict, load_models, model_info, predict_with_confidence
    _ML_AVAILABLE = True
except ImportError:
    _ML_AVAILABLE = False

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="TS-11 Stampede Predictor", version="2.1.0")

_frontend = os.getenv("FRONTEND_URL", "*")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[_frontend, "http://localhost:5173", "http://localhost:4173", "https://frontend-bnr9.onrender.com", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── WebSocket connection manager ──────────────────────────────────────────────
class _Manager:
    def __init__(self):
        self.connections: Set[WebSocket] = set()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.connections.add(ws)

    def disconnect(self, ws: WebSocket):
        self.connections.discard(ws)

    async def broadcast(self, data: dict):
        dead: Set[WebSocket] = set()
        for ws in self.connections:
            try:
                await ws.send_json(data)
            except Exception:
                dead.add(ws)
        self.connections -= dead


mgr = _Manager()


# ── Background CPI broadcast (every 2 s) ─────────────────────────────────────
async def _broadcast_loop():
    while True:
        readings = get_all_readings()
        for r in readings:
            await log_cpi(
                corridor=r["corridor"],
                cpi=r["cpi"],
                flow_rate=r["flow_rate"],
                transport_burst=r["transport_burst"],
                chokepoint_density=r["chokepoint_density"],
                surge_type=r["surge_type"],
                alert_fired=r["alert_active"],
            )
            if r["alert_active"] and r["alert_id"]:
                await insert_alert(
                    alert_id=r["alert_id"],
                    corridor=r["corridor"],
                    cpi=r["cpi"],
                    surge_type=r["surge_type"],
                    ml_confidence=r.get("ml_confidence"),
                )
        await mgr.broadcast({"type": "cpi_batch", "data": readings})
        await asyncio.sleep(2)


# ── Lifecycle ─────────────────────────────────────────────────────────────────
@app.on_event("startup")
async def startup():
    await init_db()
    asyncio.create_task(_broadcast_loop())
    if _ML_AVAILABLE:
        try:
            load_models()
        except FileNotFoundError:
            print("[main] ML models not yet trained — run `python -m ml.train`")


# ── Health ────────────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {
        "status": "ok",
        "corridors": get_corridors(),
        "replay_frames": len(REPLAY_FRAMES),
        "ts": datetime.now(timezone.utc).isoformat(),
    }


# ── WebSocket ─────────────────────────────────────────────────────────────────
@app.websocket("/ws")
async def websocket(ws: WebSocket):
    await mgr.connect(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        mgr.disconnect(ws)


# ── Corridors ─────────────────────────────────────────────────────────────────
@app.get("/api/corridors")
async def corridors():
    return {"corridors": get_corridors(), "config": get_corridor_config()}


# ── Alerts ────────────────────────────────────────────────────────────────────
@app.get("/api/alerts")
async def alerts(limit: int = 50):
    rows = await get_alerts(limit)
    return {"alerts": rows}


# ── Acknowledge ───────────────────────────────────────────────────────────────
@app.post("/api/ack/{alert_id}/{agency}")
async def acknowledge(alert_id: str, agency: str):
    if agency not in ("police", "temple", "gsrtc"):
        raise HTTPException(400, "agency must be police, temple, or gsrtc")
    ok = await ack_alert(alert_id, agency)
    if not ok:
        raise HTTPException(404, "alert not found or already acknowledged")
    return {"status": "acknowledged", "alert_id": alert_id, "agency": agency}


# ── Events (CPI log) ──────────────────────────────────────────────────────────
@app.get("/api/events")
async def events(limit: int = 50):
    rows = await get_events(limit)
    return {"events": rows}


@app.get("/api/events/export")
async def export_events():
    rows = await get_events(limit=1000)
    buf  = io.StringIO()
    if rows:
        writer = csv.DictWriter(buf, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    buf.seek(0)
    filename = f"ts11_events_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── Replay ────────────────────────────────────────────────────────────────────
@app.get("/api/replay")
async def replay_frame(frame: int = 0):
    if not REPLAY_FRAMES:
        raise HTTPException(404, "No replay data")
    idx = max(0, min(frame, len(REPLAY_FRAMES) - 1))
    return {"frame": REPLAY_FRAMES[idx], "index": idx, "total": len(REPLAY_FRAMES)}


@app.get("/api/replay/all")
async def replay_all():
    return {"frames": REPLAY_FRAMES, "total": len(REPLAY_FRAMES)}


# ── ML Prediction ─────────────────────────────────────────────────────────────
class MLPredictRequest(BaseModel):
    location: Optional[str] = "Ambaji"
    corridor_width_m: Optional[float] = 5.0
    entry_flow_rate_pax_per_min: Optional[float] = 100.0
    exit_flow_rate_pax_per_min: Optional[float] = 100.0
    transport_arrival_burst: Optional[int] = 0
    vehicle_count: Optional[int] = 5
    queue_density_pax_per_m2: Optional[float] = 2.0
    weather: Optional[str] = "Clear"
    festival_peak: Optional[int] = 0
    pressure_index: Optional[float] = 30.0
    predicted_crush_window_min: Optional[int] = 15


@app.post("/api/ml/predict")
async def ml_predict_endpoint(body: MLPredictRequest):
    if not _ML_AVAILABLE:
        raise HTTPException(503, "ML module is unavailable.")
    try:
        result = ml_predict(body.model_dump())
    except FileNotFoundError as exc:
        raise HTTPException(503, str(exc) + " — run `python -m ml.train` first.")
    except Exception as exc:
        raise HTTPException(500, f"Prediction failed: {exc}")
    return result


@app.get("/api/ml/info")
async def ml_info_endpoint():
    if not _ML_AVAILABLE:
        raise HTTPException(503, "ML module unavailable.")
    try:
        return model_info()
    except FileNotFoundError as exc:
        raise HTTPException(503, str(exc))


# ── What-If Simulator ─────────────────────────────────────────────────────────
class SimulateBody(BaseModel):
    corridor: Optional[str] = "Ambaji"
    flow_rate: Optional[float] = 100.0
    transport_burst: Optional[float] = 0.2
    chokepoint_density: Optional[float] = 0.3


@app.post("/api/simulate")
async def simulate_endpoint(body: SimulateBody):
    """
    Pure what-if CPI calculation — does NOT affect live simulation.
    Returns: {cpi, surge_type, time_to_breach_seconds, ml_confidence}
    """
    baseline = CORRIDOR_BASELINES.get(body.corridor, CORRIDOR_BASELINES["Ambaji"])

    norm_flow    = min((body.flow_rate or 0) / baseline["capacity_ppm"], 1.0)
    norm_density = min(body.chokepoint_density or 0, 1.0)
    transport    = min(body.transport_burst or 0, 1.0)

    cpi = norm_flow * 0.5 + transport * 0.3 + norm_density * 0.2
    cpi = round(max(0.0, min(cpi, 1.0)), 3)

    # Surge type from CPI thresholds
    if cpi >= 0.85:
        surge_type = "GENUINE_CRUSH"
    elif cpi >= 0.70:
        surge_type = "GENUINE_CRUSH"
    elif cpi >= 0.50:
        surge_type = "SELF_RESOLVING"
    else:
        surge_type = "SAFE"

    # Estimate TTB: assume steady 1% CPI rise per 2s (simple model)
    if cpi < 0.85 and cpi >= 0.40:
        assumed_slope = 0.008 + (cpi - 0.40) * 0.02
        ttb_s = int((0.85 - cpi) / assumed_slope)
    elif cpi >= 0.85:
        ttb_s = 0
    else:
        ttb_s = None

    # ML confidence
    ml_confidence = None
    if _ML_AVAILABLE:
        try:
            res = predict_with_confidence({
                "cpi":               cpi,
                "flow_rate":         body.flow_rate,
                "transport_burst":   transport,
                "chokepoint_density": norm_density,
            })
            ml_confidence = res.get("confidence_score")
        except Exception:
            pass

    return {
        "cpi":                    cpi,
        "surge_type":             surge_type,
        "time_to_breach_seconds": ttb_s,
        "ml_confidence":          ml_confidence,
    }


# ── Incident Report ───────────────────────────────────────────────────────────
@app.get("/api/report/{alert_id}")
async def get_report(alert_id: str):
    """
    Return a full incident report for a given alert_id.
    """
    alert = await get_alert_by_id(alert_id)
    if not alert:
        raise HTTPException(404, f"Alert {alert_id} not found")

    fired_dt = datetime.fromisoformat(alert["fired_at"])

    ack_times = {
        "police": alert.get("police_ack"),
        "temple": alert.get("temple_ack"),
        "gsrtc":  alert.get("gsrtc_ack"),
    }

    all_acked  = all(v for v in ack_times.values())
    any_acked  = any(v for v in ack_times.values())
    resolved_at = None
    duration_seconds = None

    if all_acked:
        resolved_dt  = max(datetime.fromisoformat(t) for t in ack_times.values())
        resolved_at  = resolved_dt.isoformat()
        duration_seconds = int((resolved_dt - fired_dt).total_seconds())
        outcome = "FULLY_RESOLVED"
    elif any_acked:
        outcome = "PARTIAL_ACK"
    else:
        outcome = "UNACKNOWLEDGED"

    return {
        "alert_id":         alert_id,
        "corridor":         alert["corridor"],
        "peak_cpi":         alert["cpi"],
        "surge_type":       alert["surge_type"],
        "fired_at":         alert["fired_at"],
        "police_ack_time":  ack_times["police"],
        "temple_ack_time":  ack_times["temple"],
        "gsrtc_ack_time":   ack_times["gsrtc"],
        "ml_confidence":    alert.get("ml_confidence"),
        "duration_seconds": duration_seconds,
        "resolved_at":      resolved_at,
        "outcome":          outcome,
    }


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
