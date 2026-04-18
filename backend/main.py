"""
TS-11 Stampede Window Predictor — FastAPI backend

Start: uvicorn main:app --host 0.0.0.0 --port $PORT
"""
import asyncio
import base64
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

import aiosqlite

from database import (
    init_db, insert_alert, ack_alert, get_alerts, log_cpi, get_events,
    get_alert_by_id, insert_notification, get_notifications,
    get_historical_incidents, log_call, get_call_log,
)
from call_service import trigger_corridor_calls, make_alert_call
from replay_data import REPLAY_FRAMES
from bus_simulator import get_bus_update_message, update_destination_cpi
from historical import get_historical_for_corridor, get_seasonal_prediction

# ── ML predictor (optional — graceful if models not yet trained) ──────────────
try:
    from ml.predictor import predict as ml_predict, load_models, model_info, predict_with_confidence
    _ML_AVAILABLE = True
except ImportError:
    _ML_AVAILABLE = False

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="TS-11 Stampede Predictor", version="3.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Demo users ────────────────────────────────────────────────────────────────
DEMO_USERS = {
    "driver_001": {
        "password": "driver123",
        "role": "driver",
        "name": "Ramesh Patel",
        "unit_id": "GJ-01-BUS-042",
        "route": "Ahmedabad → Ambaji",
    },
    "police_001": {
        "password": "police123",
        "role": "police",
        "name": "Inspector Mehta",
        "unit_id": "Ambaji PS",
        "station": "Ambaji Police Station",
    },
    "temple_001": {
        "password": "temple123",
        "role": "temple",
        "name": "Trustee Sharma",
        "unit_id": "Ambaji Temple",
        "premises": "Main Sanctum Area",
    },
    "gsrtc_001": {
        "password": "gsrtc123",
        "role": "gsrtc",
        "name": "Controller Joshi",
        "unit_id": "GSRTC Depot 4",
        "zone": "North Corridor",
    },
}

ROLE_REDIRECT = {
    "driver": "/?agency=driver",
    "police": "/?agency=police",
    "temple": "/?agency=temple",
    "gsrtc":  "/?agency=gsrtc",
}

# Active sessions: token → { role, unit_id, name, username }
_active_sessions: Dict[str, dict] = {}


def _make_token(role: str, unit_id: str) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    raw = f"{role}:{unit_id}:{ts}"
    return base64.b64encode(raw.encode()).decode()


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

# Track which alert_ids have already triggered calls
# Prevents duplicate calls for same alert
called_alert_ids: set = set()

# ── Corridor simulator state ──────────────────────────────────────────────────
CORRIDORS = ["Ambaji", "Dwarka", "Somnath", "Pavagadh"]

_PHASE_OFFSETS = {
    "Ambaji":   0.0,
    "Dwarka":   math.pi * 0.5,
    "Somnath":  math.pi * 1.0,
    "Pavagadh": math.pi * 1.5,
}

_sim_step: Dict[str, int] = {c: 0 for c in CORRIDORS}
_active_alerts: Dict[str, Optional[str]] = {c: None for c in CORRIDORS}
_consecutive_high: Dict[str, int] = {c: 0 for c in CORRIDORS}
_bus_tick = 0


def _generate_reading(corridor: str) -> dict:
    step = _sim_step[corridor]
    _sim_step[corridor] += 1

    phase_offset = _PHASE_OFFSETS[corridor]
    sine_val = math.sin((step * 0.021) + phase_offset)
    base_cpi = 0.575 + sine_val * 0.275
    noise = random.uniform(-0.04, 0.04)
    base_cpi = max(0.25, min(0.95, base_cpi + noise))

    flow_rate = random.uniform(800, 1800)
    transport_burst = random.uniform(0.2, 0.8)
    chokepoint_density = random.uniform(0.3, 0.9)

    cpi = (flow_rate / 2000) * 0.5 + transport_burst * 0.3 + chokepoint_density * 0.2
    cpi = round(max(0.25, min(0.95, cpi)), 3)

    if cpi > 0.70:
        _consecutive_high[corridor] += 1
    else:
        _consecutive_high[corridor] = 0

    if _consecutive_high[corridor] >= 3 and cpi > 0.70:
        surge_type = "GENUINE_CRUSH"
    elif cpi >= 0.55:
        surge_type = "SELF_RESOLVING"
    else:
        surge_type = "SAFE"

    alert_active = surge_type == "GENUINE_CRUSH"
    if alert_active:
        if _active_alerts[corridor] is None:
            ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            _active_alerts[corridor] = f"ALT_{ts}_{corridor[:3].upper()}"
    else:
        _active_alerts[corridor] = None

    alert_id = _active_alerts[corridor]

    if cpi < 0.85 and cpi >= 0.40:
        slope = 0.008 + (cpi - 0.40) * 0.02
        ttb_s = int((0.85 - cpi) / slope)
    elif cpi >= 0.85:
        ttb_s = 0
    else:
        ttb_s = None

    ml_confidence = min(99, max(50, int(50 + cpi * 50)))
    ml_risk_level = (
        "CRITICAL" if cpi >= 0.85 else
        "HIGH"     if cpi >= 0.70 else
        "MEDIUM"   if cpi >= 0.50 else
        "LOW"
    )

    # Keep bus simulator in sync with corridor CPI
    update_destination_cpi(corridor, cpi)

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
    global _bus_tick
    print("[simulator] Loop started — broadcasting every 2s")
    while True:
        try:
            for corridor in CORRIDORS:
                try:
                    reading = _generate_reading(corridor)

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

                    # === PHONE CALL TRIGGER ===
                    if (
                        reading.get("alert_active")
                        and reading.get("surge_type") == "GENUINE_CRUSH"
                        and reading.get("cpi", 0) >= 0.85
                        and reading.get("alert_id") not in called_alert_ids
                    ):
                        called_alert_ids.add(reading["alert_id"])
                        print(
                            f"[CALLS] Triggering calls for {corridor} "
                            f"alert {reading['alert_id']}"
                        )
                        asyncio.create_task(
                            trigger_calls_and_log(
                                corridor=corridor,
                                cpi=reading["cpi"],
                                ttb_minutes=reading.get("time_to_breach_minutes") or 0,
                                surge_type=reading["surge_type"],
                                alert_id=reading["alert_id"],
                            )
                        )

                except Exception as corridor_err:
                    print(f"[simulator] Error for {corridor}: {corridor_err}")
                    continue

            # Broadcast bus positions every 5 seconds (every 2-3 CPI cycles)
            _bus_tick += 1
            if _bus_tick % 3 == 0:
                try:
                    bus_msg = get_bus_update_message(_bus_tick)
                    await manager.broadcast(bus_msg)
                except Exception as bus_err:
                    print(f"[simulator] Bus update error: {bus_err}")

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
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
            except asyncio.TimeoutError:
                try:
                    await websocket.send_json({"type": "ping"})
                except Exception:
                    break
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        print(f"[ws] WebSocket error: {e}")
        manager.disconnect(websocket)


# ── Auth ──────────────────────────────────────────────────────────────────────
class LoginBody(BaseModel):
    role: str
    username: str
    password: str
    unit_id: Optional[str] = None


@app.post("/api/login")
async def login(body: LoginBody):
    user = DEMO_USERS.get(body.username)
    if not user:
        raise HTTPException(401, "Invalid username or password")
    if user["password"] != body.password:
        raise HTTPException(401, "Invalid username or password")
    if user["role"] != body.role:
        raise HTTPException(401, f"Username does not match role '{body.role}'")

    token = _make_token(user["role"], user["unit_id"])
    _active_sessions[token] = {
        "role":     user["role"],
        "unit_id":  user["unit_id"],
        "name":     user["name"],
        "username": body.username,
    }

    redirect_url = ROLE_REDIRECT.get(user["role"], "/") + f"&token={token}"

    return {
        "token":        token,
        "role":         user["role"],
        "unit_id":      user["unit_id"],
        "name":         user["name"],
        "redirect_url": redirect_url,
    }


@app.get("/api/me")
async def me(token: str):
    session = _active_sessions.get(token)
    if not session:
        raise HTTPException(401, "Invalid or expired token")
    return session


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


# ── Notifications ─────────────────────────────────────────────────────────────
class NotifyBody(BaseModel):
    corridor: str
    alert_id: str
    cpi: float
    surge_type: str
    message: str


ROLE_MESSAGES = {
    "driver": lambda b: (
        f"⚠ ALERT: {b.corridor} corridor CPI {b.cpi:.2f}. "
        f"Hold at checkpoint — do NOT proceed to temple."
    ),
    "police": lambda b: (
        f"🚨 URGENT: Crush risk at {b.corridor}. "
        f"Deploy to Choke Point B immediately. Alert ID: {b.alert_id}"
    ),
    "temple": lambda b: (
        f"🛕 ACTION: Activate darshan hold NOW. "
        f"CPI: {b.cpi:.2f} — {b.surge_type}. Redirect pilgrims to Queue C."
    ),
    "gsrtc": lambda b: (
        f"🚌 HOLD BUSES: {b.corridor} at capacity. "
        f"Hold all vehicles at 3km checkpoint."
    ),
}


@app.post("/api/notify")
async def notify(body: NotifyBody):
    inserted = []
    for role, msg_fn in ROLE_MESSAGES.items():
        msg = msg_fn(body)
        nid = await insert_notification(
            alert_id=body.alert_id,
            role=role,
            unit_id="broadcast",
            message=msg,
        )
        inserted.append({"role": role, "id": nid})
    return {"status": "sent", "notifications": inserted}


@app.get("/api/notifications")
async def get_notifs(role: Optional[str] = None, limit: int = 20):
    rows = await get_notifications(role=role, limit=limit)
    return {"notifications": rows}


# ── Historical ────────────────────────────────────────────────────────────────
@app.get("/api/historical/{corridor}")
async def historical(corridor: str):
    rows = await get_historical_incidents(corridor)
    if not rows:
        # Fall back to in-memory data
        rows = get_historical_for_corridor(corridor)
    return {"corridor": corridor, "incidents": rows}


@app.get("/api/prediction/seasonal/{corridor}")
async def seasonal_prediction(corridor: str, hour: Optional[int] = None):
    prediction = get_seasonal_prediction(corridor, current_hour=hour)
    return prediction


# ── Call alert helpers ────────────────────────────────────────────────────────

async def trigger_calls_and_log(
    corridor: str,
    cpi: float,
    ttb_minutes: float,
    surge_type: str,
    alert_id: str,
):
    """Background task: trigger calls and log results to DB + broadcast."""
    results = trigger_corridor_calls(
        corridor=corridor,
        cpi=cpi,
        ttb_minutes=ttb_minutes,
        surge_type=surge_type,
        alert_id=alert_id,
    )

    async with aiosqlite.connect("stampede.db") as db:
        for r in results:
            await log_call(
                db=db,
                alert_id=alert_id,
                corridor=corridor,
                role=r.get("role", ""),
                phone_number=r.get("number", ""),
                call_sid=r.get("sid", ""),
                status=r.get("status", ""),
                reason=r.get("reason", ""),
                cpi=cpi,
                surge_type=surge_type,
            )

    # Broadcast call status to all connected dashboards
    await manager.broadcast({
        "type":      "call_update",
        "alert_id":  alert_id,
        "corridor":  corridor,
        "calls":     results,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    print(f"[CALLS DONE] {len(results)} calls processed for {corridor}")


# ── Call alert endpoints ──────────────────────────────────────────────────────

@app.post("/api/call-alert")
async def manual_call_alert(data: dict):
    """Manual call trigger — for demo/testing.
    Body: {corridor, role, phone, cpi, ttb_minutes, surge_type, alert_id}
    """
    result = make_alert_call(
        to_number=data.get("phone", ""),
        role=data.get("role", "police"),
        corridor=data.get("corridor", "Ambaji"),
        cpi=float(data.get("cpi", 0.85)),
        ttb_minutes=float(data.get("ttb_minutes", 10)),
        surge_type=data.get("surge_type", "GENUINE_CRUSH"),
        alert_id=data.get("alert_id", "MANUAL_TEST"),
    )

    async with aiosqlite.connect("stampede.db") as db:
        await log_call(
            db=db,
            alert_id=data.get("alert_id", "MANUAL_TEST"),
            corridor=data.get("corridor", "Ambaji"),
            role=data.get("role", "police"),
            phone_number=data.get("phone", ""),
            call_sid=result.get("sid", ""),
            status=result.get("status", ""),
            reason=result.get("reason", ""),
            cpi=float(data.get("cpi", 0.85)),
            surge_type=data.get("surge_type", "GENUINE_CRUSH"),
        )

    return result


@app.get("/api/call-log")
async def get_calls(limit: int = 50):
    """Get recent call history."""
    async with aiosqlite.connect("stampede.db") as db:
        return await get_call_log(db, limit)


@app.get("/api/call-log/{alert_id}")
async def get_calls_for_alert(alert_id: str):
    """Get all calls made for a specific alert."""
    async with aiosqlite.connect("stampede.db") as db:
        cursor = await db.execute(
            "SELECT * FROM call_log WHERE alert_id = ? ORDER BY called_at DESC",
            (alert_id,),
        )
        rows = await cursor.fetchall()
        return [
            dict(zip([col[0] for col in cursor.description], row))
            for row in rows
        ]


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
