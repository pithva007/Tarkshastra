"""
TS-11 Stampede Window Predictor — FastAPI backend

Start: uvicorn main:app --host 0.0.0.0 --port $PORT
"""
import asyncio
import csv
import io
import math
import os
import random
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import uvicorn

from database import init_db, insert_alert, ack_alert, get_alerts, log_cpi, get_events, get_alert_by_id
from replay_data import REPLAY_FRAMES

# ── ML predictor (optional — graceful if models not yet trained) ──────────────
try:
    from ml.predictor import predict as ml_predict, load_models, model_info, predict_with_confidence
    _ML_AVAILABLE = True
except ImportError:
    _ML_AVAILABLE = False

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="TS-11 Stampede Predictor", version="2.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── WebSocket connection manager ──────────────────────────────────────────────
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        print(f"[ws] Client connected — total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        print(f"[ws] Client disconnected — total: {len(self.active_connections)}")

    async def broadcast(self, data: dict):
        dead: List[WebSocket] = []
        for ws in self.active_connections:
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            if ws in self.active_connections:
                self.active_connections.remove(ws)


manager = ConnectionManager()

# ── Corridor simulator state ──────────────────────────────────────────────────
CORRIDORS = ["Ambaji", "Dwarka", "Somnath", "Pavagadh"]

# Phase offsets so each corridor is independent
_PHASE_OFFSETS = {
    "Ambaji":   0.0,
    "Dwarka":   math.pi * 0.5,
    "Somnath":  math.pi * 1.0,
    "Pavagadh": math.pi * 1.5,
}

_sim_step: Dict[str, int] = {c: 0 for c in CORRIDORS}
_active_alerts: Dict[str, Optional[str]] = {c: None for c in CORRIDORS}
_consecutive_high: Dict[str, int] = {c: 0 for c in CORRIDORS}


def _generate_reading(corridor: str) -> dict:
    """Generate a realistic, non-zero CPI reading for a corridor."""
    step = _sim_step[corridor]
    _sim_step[corridor] += 1

    phase_offset = _PHASE_OFFSETS[corridor]
    # Sine wave: period ~300 steps (10 min at 2s interval) — gradual rise and fall
    sine_val = math.sin((step * 0.021) + phase_offset)  # -1 to 1

    # Map sine to a realistic range: 0.3 to 0.85
    base_cpi = 0.575 + sine_val * 0.275  # centre 0.575, amplitude 0.275

    # Add small random noise
    noise = random.uniform(-0.04, 0.04)
    base_cpi = max(0.25, min(0.95, base_cpi + noise))

    # Derive component values that produce this CPI
    # CPI = (flow_rate/2000)*0.5 + transport_burst*0.3 + chokepoint_density*0.2
    # Work backwards from CPI to get plausible components
    flow_rate = random.uniform(800, 1800)
    transport_burst = random.uniform(0.2, 0.8)
    chokepoint_density = random.uniform(0.3, 0.9)

    # Recalculate CPI from components (keeps formula consistent)
    cpi = (flow_rate / 2000) * 0.5 + transport_burst * 0.3 + chokepoint_density * 0.2
    cpi = round(max(0.25, min(0.95, cpi)), 3)

    # Track consecutive high readings
    if cpi > 0.70:
        _consecutive_high[corridor] += 1
    else:
        _consecutive_high[corridor] = 0

    # Classify surge type
    if _consecutive_high[corridor] >= 3 and cpi > 0.70:
        surge_type = "GENUINE_CRUSH"
    elif cpi >= 0.55:
        surge_type = "SELF_RESOLVING"
    else:
        surge_type = "SAFE"

    # Alert management
    alert_active = surge_type == "GENUINE_CRUSH"
    if alert_active:
        if _active_alerts[corridor] is None:
            ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            _active_alerts[corridor] = f"ALT_{ts}_{corridor[:3].upper()}"
    else:
        _active_alerts[corridor] = None

    alert_id = _active_alerts[corridor]

    # Time to breach
    if cpi < 0.85 and cpi >= 0.40:
        slope = 0.008 + (cpi - 0.40) * 0.02
        ttb_s = int((0.85 - cpi) / slope)
    elif cpi >= 0.85:
        ttb_s = 0
    else:
        ttb_s = None

    # ML confidence (deterministic from CPI)
    ml_confidence = min(99, max(50, int(50 + cpi * 50)))
    ml_risk_level = (
        "CRITICAL" if cpi >= 0.85 else
        "HIGH"     if cpi >= 0.70 else
        "MEDIUM"   if cpi >= 0.50 else
        "LOW"
    )

    return {
        "type":                   "cpi_update",
        "corridor":               corridor,
        "cpi":                    cpi,
        "flow_rate":              round(flow_rate, 1),
        "transport_burst":        round(transport_burst, 3),
        "chokepoint_density":     round(chokepoint_density, 3),
        "surge_type":             surge_type,
        "time_to_breach_seconds": ttb_s,
        "time_to_breach_minutes": round(ttb_s / 60, 1) if ttb_s is not None else None,
        "alert_active":           alert_active,
        "alert_id":               alert_id,
        "ml_confidence":          ml_confidence,
        "ml_risk_level":          ml_risk_level,
        "timestamp":              datetime.now(timezone.utc).isoformat(),
    }


# ── Background simulator task ─────────────────────────────────────────────────
async def run_simulator():
    print("[simulator] Loop started — broadcasting every 2s")
    while True:
        try:
            for corridor in CORRIDORS:
                try:
                    reading = _generate_reading(corridor)

                    # Log to DB (non-blocking, ignore errors)
                    try:
                        await log_cpi(
                            corridor=reading["corridor"],
                            cpi=reading["cpi"],
                            flow_rate=reading["flow_rate"],
                            transport_burst=reading["transport_burst"],
                            chokepoint_density=reading["chokepoint_density"],
                            surge_type=reading["surge_type"],
                            alert_fired=reading["alert_active"],
                        )
                    except Exception as db_err:
                        print(f"[simulator] DB log error ({corridor}): {db_err}")

                    if reading["alert_active"] and reading["alert_id"]:
                        try:
                            await insert_alert(
                                alert_id=reading["alert_id"],
                                corridor=reading["corridor"],
                                cpi=reading["cpi"],
                                surge_type=reading["surge_type"],
                                ml_confidence=reading.get("ml_confidence"),
                            )
                        except Exception:
                            pass

                    await manager.broadcast(reading)
                    print(f"[sim] {corridor}: CPI={reading['cpi']} {reading['surge_type']}")

                except Exception as corridor_err:
                    print(f"[simulator] Error for {corridor}: {corridor_err}")
                    continue

        except Exception as loop_err:
            print(f"[simulator] Outer loop error: {loop_err}")

        await asyncio.sleep(2)


# ── Lifecycle ─────────────────────────────────────────────────────────────────
@app.on_event("startup")
async def startup():
    print("=== Backend starting up ===")
    await init_db()
    asyncio.create_task(run_simulator())
    print("=== Simulator started ===")
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
        "connections": len(manager.active_connections),
        "corridors": CORRIDORS,
        "ts": datetime.now(timezone.utc).isoformat(),
    }


# ── WebSocket ─────────────────────────────────────────────────────────────────
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Keep connection alive — receive and ignore pings/messages
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
            except asyncio.TimeoutError:
                # Send ping to keep alive
                try:
                    await websocket.send_json({"type": "ping"})
                except Exception:
                    break
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        print(f"[ws] WebSocket error: {e}")
        manager.disconnect(websocket)


# ── Corridors ─────────────────────────────────────────────────────────────────
@app.get("/api/corridors")
async def corridors():
    return {"corridors": CORRIDORS}


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
    cpi = (
        (min(body.flow_rate or 0, 2000) / 2000) * 0.5
        + min(body.transport_burst or 0, 1.0) * 0.3
        + min(body.chokepoint_density or 0, 1.0) * 0.2
    )
    cpi = round(max(0.0, min(cpi, 1.0)), 3)

    if cpi >= 0.70:
        surge_type = "GENUINE_CRUSH"
    elif cpi >= 0.50:
        surge_type = "SELF_RESOLVING"
    else:
        surge_type = "SAFE"

    ttb_s = None
    if 0.40 <= cpi < 0.85:
        slope = 0.008 + (cpi - 0.40) * 0.02
        ttb_s = int((0.85 - cpi) / slope)
    elif cpi >= 0.85:
        ttb_s = 0

    ml_confidence = None
    if _ML_AVAILABLE:
        try:
            res = predict_with_confidence({
                "cpi": cpi,
                "flow_rate": body.flow_rate,
                "transport_burst": body.transport_burst,
                "chokepoint_density": body.chokepoint_density,
            })
            ml_confidence = res.get("confidence_score")
        except Exception:
            pass

    return {
        "cpi": cpi,
        "surge_type": surge_type,
        "time_to_breach_seconds": ttb_s,
        "ml_confidence": ml_confidence,
    }


# ── Incident Report ───────────────────────────────────────────────────────────
@app.get("/api/report/{alert_id}")
async def get_report(alert_id: str):
    alert = await get_alert_by_id(alert_id)
    if not alert:
        raise HTTPException(404, f"Alert {alert_id} not found")

    fired_dt = datetime.fromisoformat(alert["fired_at"])
    ack_times = {
        "police": alert.get("police_ack"),
        "temple": alert.get("temple_ack"),
        "gsrtc":  alert.get("gsrtc_ack"),
    }
    all_acked = all(v for v in ack_times.values())
    any_acked = any(v for v in ack_times.values())
    resolved_at = None
    duration_seconds = None

    if all_acked:
        resolved_dt = max(datetime.fromisoformat(t) for t in ack_times.values())
        resolved_at = resolved_dt.isoformat()
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
