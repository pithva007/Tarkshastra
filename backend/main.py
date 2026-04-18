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

from simulator import get_all_readings, get_corridor_reading, get_corridors, get_corridor_config
from database import init_db, insert_alert, ack_alert, get_alerts, log_cpi, get_events
from replay_data import REPLAY_FRAMES

# ── ML predictor (optional — graceful if models not yet trained) ──────────────
try:
    from ml.predictor import predict as ml_predict, load_models, model_info
    _ML_AVAILABLE = True
except ImportError:
    _ML_AVAILABLE = False

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="TS-11 Stampede Predictor", version="2.0.0")

_frontend = os.getenv("FRONTEND_URL", "*")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[_frontend, "http://localhost:5173", "http://localhost:4173", "*"],
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
            # Persist to CPI log
            await log_cpi(
                corridor=r["corridor"],
                cpi=r["cpi"],
                flow_rate=r["flow_rate"],
                transport_burst=r["transport_burst"],
                chokepoint_density=r["chokepoint_density"],
                surge_type=r["surge_type"],
                alert_fired=r["alert_active"],
            )
            # Persist new alerts to alerts table
            if r["alert_active"] and r["alert_id"]:
                await insert_alert(
                    alert_id=r["alert_id"],
                    corridor=r["corridor"],
                    cpi=r["cpi"],
                    surge_type=r["surge_type"],
                )
        # Broadcast all corridor readings in one message
        await mgr.broadcast({"type": "cpi_batch", "data": readings})
        await asyncio.sleep(2)


# ── Lifecycle ─────────────────────────────────────────────────────────────────
@app.on_event("startup")
async def startup():
    await init_db()
    asyncio.create_task(_broadcast_loop())
    # Pre-load ML models so first request has no cold-start latency
    if _ML_AVAILABLE:
        try:
            load_models()
        except FileNotFoundError:
            print("[main] ML models not yet trained — run `python -m ml.train` to enable /api/ml/predict")


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
            await ws.receive_text()  # keep-alive / client pings
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
class AckBody(BaseModel):
    agency: str  # police | temple | gsrtc


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
    buf = io.StringIO()
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


# ── ML Prediction ────────────────────────────────────────────────────────────
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
    """
    Predict crowd crush risk level using the trained XGBoost model.

    Returns:
      prediction   : SAFE | SURGE | HIGH_RISK
      confidence   : probability of the predicted class
      probabilities: breakdown for all 3 classes
    """
    if not _ML_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="ML module is unavailable. Check that scikit-learn and xgboost are installed.",
        )
    try:
        result = ml_predict(body.model_dump())
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc) + " — run `python -m ml.train` to train the model first.",
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Prediction failed: {exc}")
    return result


@app.get("/api/ml/info")
async def ml_info_endpoint():
    """Return metadata about the loaded ML model."""
    if not _ML_AVAILABLE:
        raise HTTPException(status_code=503, detail="ML module unavailable.")
    try:
        return model_info()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
