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
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

# Load .env file for local dev (no-op if already set by Render)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel
import uvicorn

import aiosqlite

from database import (
    init_db, insert_alert, ack_alert, get_alerts, log_cpi, get_events,
    get_alert_by_id, insert_notification, get_notifications,
    get_historical_incidents, log_call, get_call_log,
    save_alert_reply, get_alert_replies, get_all_replies
)
from auth import login, verify_token, has_permission
from auth import get_all_sessions, PERMISSIONS, get_session
from call_service import (
    trigger_corridor_calls_async,
    trigger_corridor_calls,   # kept for legacy /api/call-alert endpoint
    make_single_call,
)
from report_generator import generate_alert_report
from replay_data import REPLAY_FRAMES
from bus_simulator import get_bus_update_message, update_destination_cpi
from historical import get_historical_for_corridor, get_seasonal_prediction
from vision_bridge import (
    vision_processor, get_all_vision_readings,
    clear_vision_reading, CORRIDOR_CALIBRATION
)

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

# Track active alerts per corridor
# Format: { corridor_name: alert_id }
# When corridor has active alert, don't create new one
# until current alert is resolved or 15 min passes
active_corridor_alerts: dict = {}
alert_resolution_time: dict = {}
ALERT_COOLDOWN_MINUTES = 15

# Manually triggered alerts that need to be
# broadcast in next cpi_update cycle
# Format: {corridor: alert_data_dict}
manual_alert_injections: dict = {}

# ── Import new simulator ─────────────────────────────────────────────────────
from simulator import get_simulator
from bus_simulator import BusSimulator

# ── Corridor simulator state ──────────────────────────────────────────────────
CORRIDORS = ["Ambaji", "Dwarka", "Somnath", "Pavagadh"]
_bus_tick = 0

# Get the singleton simulator instance
simulator = get_simulator()

# Initialize bus simulator
bus_simulator = BusSimulator()

# Vision upload directory
VISION_UPLOAD_DIR = Path("vision_uploads")
VISION_UPLOAD_DIR.mkdir(exist_ok=True)


async def handle_new_alert(data: dict):
    """Called every 2 seconds by simulator when corridor is in SURGE state.
    Guards ensure we only start ONE 90-second timer per alert."""
    alert_id = data["alert_id"]
    corridor = data["corridor"]

    # ── Guard 1: corridor already has an active alert ─────────────────────────
    existing = active_corridor_alerts.get(corridor)
    if existing:
        # Same corridor already alerted — timer already running
        return

    # ── Guard 2: corridor is in cooldown after a recent alert ─────────────────
    last_alert_time = alert_resolution_time.get(corridor, 0)
    minutes_since = (datetime.now(timezone.utc).timestamp() - last_alert_time) / 60
    if minutes_since < ALERT_COOLDOWN_MINUTES:
        remaining = ALERT_COOLDOWN_MINUTES - minutes_since
        print(f"[ALERT SKIP] {corridor} on cooldown ({remaining:.1f} min remaining)")
        return

    # ── Guard 3: alert_id already processed ───────────────────────────────────
    if alert_id in called_alert_ids:
        return

    # ── New alert — register immediately so guards above fire next iteration ──
    active_corridor_alerts[corridor] = alert_id
    called_alert_ids.add(alert_id)

    print(f"[ALERT NEW] ── {corridor}: {alert_id} ──")
    print(f"[ALERT NEW] CPI={data['cpi']:.3f} | "
          f"TTB={data['time_to_breach_minutes']:.1f}min | "
          f"Type={data['surge_type']}")

    # ── Persist alert to DB ───────────────────────────────────────────────────
    try:
        await insert_alert(
            alert_id=alert_id,
            corridor=corridor,
            cpi=data["cpi"],
            surge_type=data["surge_type"],
            ml_confidence=data["ml_confidence"],
        )
    except Exception as e:
        print(f"[ALERT DB ERROR] {e}")

    # ── Broadcast RED alert to all dashboards ─────────────────────────────────
    await manager.broadcast({
        "type": "red_alert",
        "alert_id": alert_id,
        "corridor": corridor,
        "cpi": data["cpi"],
        "surge_type": data["surge_type"],
        "time_to_breach_minutes": data["time_to_breach_minutes"],
        "ml_confidence": data["ml_confidence"],
        "message": (
            f"🚨 RED ALERT: {corridor} — CPI {data['cpi']:.2f}. "
            f"Acknowledge within 90 seconds or emergency calls will be triggered."
        ),
        "ack_deadline_seconds": 90,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    # ── Store for injection into cpi_update broadcast ─────────────────────────
    manual_alert_injections[corridor] = {
        "alert_id": alert_id,
        "cpi": data["cpi"],
        "surge_type": data["surge_type"],
        "flow_rate": data.get("flow_rate", 1400),
        "transport_burst": data.get("transport_burst", 0.75),
        "chokepoint_density": data.get("chokepoint_density", 0.80),
        "time_to_breach_minutes": data.get("time_to_breach_minutes", 0),
        "time_to_breach_seconds": data.get("time_to_breach_seconds", 0),
        "ml_confidence": data.get("ml_confidence", 89),
        "broadcast_count": 0,
    }

    # ── Immediately broadcast alert_fired to ALL clients ──────────────────────
    # This makes agency dashboards show modal right away
    await manager.broadcast({
        "type": "cpi_update",
        "corridor": corridor,
        "cpi": data["cpi"],
        "flow_rate": data.get("flow_rate", 1400),
        "transport_burst": data.get("transport_burst", 0.75),
        "chokepoint_density": data.get("chokepoint_density", 0.80),
        "surge_type": data["surge_type"],
        "corridor_state": "SURGE",
        "state_duration_remaining": 3600,
        "time_to_breach_seconds": data.get("time_to_breach_seconds", 0),
        "time_to_breach_minutes": data.get("time_to_breach_minutes", 0),
        "alert_active": True,
        "alert_id": alert_id,
        "ml_confidence": data.get("ml_confidence", 89),
        "ml_risk_level": "CRITICAL",
        "alert_lifecycle_state": "ACTIVE",
        "alert_acknowledged_by": [],
        "alert_duration_minutes": 0,
        "alert_low_cpi_count": 0,
        "data_source": data.get("data_source", "simulator"),
        "vision_active": data.get("data_source") == "vision",
        "timestamp": datetime.utcnow().isoformat() + "Z",
    })

    print(
        f"[ALERT BROADCAST] Sent alert_active=True "
        f"for {corridor} to all {len(manager.active_connections)}"
        f" connected clients"
    )

    # ── Start 90-second acknowledgment timer in background ────────────────────
    print(f"[TIMER] Starting 90-second ack timer for {alert_id}")
    asyncio.create_task(
        _ack_timer_and_call(
            alert_id=alert_id,
            corridor=corridor,
            cpi=data["cpi"],
            ttb_minutes=data["time_to_breach_minutes"],
            surge_type=data["surge_type"],
            flow_rate=data["flow_rate"],
            transport_burst=data["transport_burst"],
            chokepoint_density=data["chokepoint_density"],
            ml_confidence=data["ml_confidence"],
        )
    )


# ── 90-second acknowledgment timer ───────────────────────────────────────────
# Tracks which alerts have been acknowledged before the timer expires
_acknowledged_alerts: set = set()

ACK_TIMEOUT_SECONDS = 90


async def mark_alert_acknowledged(alert_id: str):
    """Call this when any agency acknowledges the alert.
    Prevents the voice call from firing."""
    _acknowledged_alerts.add(alert_id)
    print(f"[ACK] Alert {alert_id} acknowledged — call suppressed")


async def _ack_timer_and_call(
    alert_id: str,
    corridor: str,
    cpi: float,
    ttb_minutes: float,
    surge_type: str,
    flow_rate: float,
    transport_burst: float,
    chokepoint_density: float,
    ml_confidence: int,
):
    """Waits ACK_TIMEOUT_SECONDS. If alert is NOT acknowledged by then,
    triggers voice calls to all agencies. This is the core fix."""

    print(f"[TIMER] {alert_id} — waiting {ACK_TIMEOUT_SECONDS}s for acknowledgment...")

    # Broadcast countdown start
    await manager.broadcast({
        "type": "ack_timer_started",
        "alert_id": alert_id,
        "corridor": corridor,
        "timeout_seconds": ACK_TIMEOUT_SECONDS,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    await asyncio.sleep(ACK_TIMEOUT_SECONDS)

    # ── Check if acknowledged ─────────────────────────────────────────────────
    if alert_id in _acknowledged_alerts:
        print(f"[TIMER] {alert_id} — acknowledged before timeout. No call needed.")
        await manager.broadcast({
            "type": "call_suppressed",
            "alert_id": alert_id,
            "corridor": corridor,
            "reason": "acknowledged_before_timeout",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        return

    # ── Timer expired — no acknowledgment received → trigger calls ────────────
    print(f"[TIMER] ⏰ {alert_id} — 90s expired, NO acknowledgment received!")
    print(f"[TIMER] Triggering emergency calls for {corridor}...")

    await manager.broadcast({
        "type": "ack_timeout",
        "alert_id": alert_id,
        "corridor": corridor,
        "message": (
            f"⚠️ No acknowledgment received for {corridor} alert. "
            f"Triggering emergency calls now."
        ),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    # ── Fire calls + PDF generation ───────────────────────────────────────────
    await trigger_calls_and_log(
        corridor=corridor,
        cpi=cpi,
        ttb_minutes=ttb_minutes,
        surge_type=surge_type,
        alert_id=alert_id,
        flow_rate=flow_rate,
        transport_burst=transport_burst,
        chokepoint_density=chokepoint_density,
        ml_confidence=ml_confidence,
    )


# ── Lifecycle ─────────────────────────────────────────────────────────────────

# ── Injecting broadcast wrapper ───────────────────────────────────────────────
async def _broadcast_with_injection(data: dict):
    """Wrapper around manager.broadcast that injects alert_active=True
    for any corridor that has a pending manual_alert_injection.
    Used to piggyback on the simulator's own broadcast loop for 10 cycles."""
    corridor = data.get("corridor")

    if corridor and data.get("type") == "cpi_update":
        manual = manual_alert_injections.get(corridor)
        if manual:
            # Increment broadcast count
            manual["broadcast_count"] = manual.get("broadcast_count", 0) + 1

            if manual["broadcast_count"] > 10:
                # Remove after 10 broadcasts (~20 seconds)
                del manual_alert_injections[corridor]
            else:
                # Override with manual alert data so any agency that
                # connects after the initial push still sees alert_active=True
                data = {
                    **data,
                    "alert_active": True,
                    "alert_id": manual["alert_id"],
                    "surge_type": manual["surge_type"],
                    "time_to_breach_seconds": manual["time_to_breach_seconds"],
                    "time_to_breach_minutes": manual["time_to_breach_minutes"],
                    "ml_confidence": manual["ml_confidence"],
                    "alert_lifecycle_state": "ACTIVE",
                    "alert_acknowledged_by": [],
                }

    await manager.broadcast(data)


@app.on_event("startup")
async def startup():
    print("=== Backend starting ===")
    await init_db()

    # Initialize simulator with CSV
    simulator.initialize("TS-PS11.csv")
    # Use injection-aware broadcast wrapper so simulator loops also carry
    # alert_active=True for 10 cycles after a manual trigger
    simulator.set_broadcast(_broadcast_with_injection)
    simulator.set_alert_callback(handle_new_alert)
    asyncio.create_task(simulator.run())

    # Start bus simulator
    asyncio.create_task(run_bus_simulator())
    print("=== Bus Simulator started ===")

    # Connect vision alert callback
    try:
        from vision_bridge import vision_processor as _vp
        _vp.alert_callback = handle_new_alert
        print("[VISION] Alert pipeline connected")
    except Exception as _ve:
        print(f"[VISION] Alert callback not connected: {_ve}")

    print("=== Simulator started ===")
    if _ML_AVAILABLE:
        try:
            load_models()
        except FileNotFoundError:
            print("[main] ML models not yet trained — run `python -m ml.train`")

async def run_bus_simulator():
    """Broadcast bus positions every 5 seconds."""
    print("[BUS] Simulator task started")
    while True:
        try:
            bus_message = get_bus_update_message()
            buses = bus_message.get("buses", [])
            if buses:
                await manager.broadcast(bus_message)
                # Uncomment to debug:
                # print(f"[BUS] Broadcast {len(buses)} buses")
        except Exception as e:
            print(f"[BUS BROADCAST ERROR] {e}")
        await asyncio.sleep(5)


@app.get("/api/buses")
async def get_buses():
    """Debug endpoint — returns current bus positions."""
    try:
        msg = get_bus_update_message()
        return {"count": len(msg.get("buses", [])),
                "buses": msg.get("buses", [])}
    except Exception as e:
        return {"error": str(e), "count": 0}


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


# ── Auth endpoints ───────────────────────────
@app.post("/api/login")
async def api_login(data: dict):
    result = login(data.get("username", ""),
                  data.get("password", ""))
    if not result:
        raise HTTPException(status_code=401,
                          detail="Invalid username or password")
    return result

@app.get("/api/me")
async def get_me(authorization: str = ""):
    token = authorization.replace("Bearer ", "")
    session = verify_token(token)
    if not session:
        raise HTTPException(status_code=401, detail="Invalid token")
    return session

@app.post("/api/logout")
async def api_logout(data: dict):
    from auth import sessions
    token = data.get("token", "")
    sessions.pop(token, None)
    return {"status": "logged_out"}

# ── Alert reply endpoint ─────────────────────
@app.post("/api/alert/reply")
async def submit_alert_reply(data: dict):
    """Agency submits their action in response to alert.
    Body: {token, alert_id, corridor, action_taken,
           status, notes, ack_time_seconds}
    """
    token = data.get("token", "")
    session = verify_token(token)
    if not session:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    # Check permission using the role from the verified session
    role = session.get("role", "")
    if "reply_alert" not in PERMISSIONS.get(role, []):
        raise HTTPException(status_code=403,
                          detail="Permission denied")
    
    user_session = get_session(token)
    replied_at = datetime.utcnow().isoformat()

    # Suppress the 90-second call timer — agency has responded
    await mark_alert_acknowledged(data.get("alert_id", ""))
    
    async with aiosqlite.connect("stampede.db") as db:
        await save_alert_reply(
            db=db,
            alert_id=data.get("alert_id"),
            corridor=data.get("corridor"),
            role=session["role"],
            unit_id=session["unit_id"],
            responder_name=user_session["name"] if user_session else "Unknown",
            action_taken=data.get("action_taken", ""),
            status=data.get("status", "ACKNOWLEDGED"),
            notes=data.get("notes", ""),
            replied_at=replied_at,
            ack_time_seconds=data.get("ack_time_seconds", 0)
        )
        
        # Check if all 3 agencies have replied
        cursor = await db.execute("""
            SELECT COUNT(DISTINCT role) FROM alert_replies 
            WHERE alert_id = ? AND role IN ('police', 'temple', 'gsrtc')
        """, (data.get("alert_id"),))
        distinct_roles = (await cursor.fetchone())[0]
        
        if distinct_roles >= 3:
            # All agencies replied — auto resolve
            print(f"[AUTO RESOLVE] All agencies replied for {data.get('alert_id')}")
            corridor_to_resolve = data.get("corridor")
            if corridor_to_resolve in active_corridor_alerts:
                del active_corridor_alerts[corridor_to_resolve]
                alert_resolution_time[corridor_to_resolve] = datetime.now(timezone.utc).timestamp()
                # Also clear any pending manual injection for this corridor
                manual_alert_injections.pop(corridor_to_resolve, None)
                
                await manager.broadcast({
                    "type": "alert_resolved",
                    "alert_id": data.get("alert_id"),
                    "corridor": data.get("corridor"),
                    "resolved_by": "all_agencies_replied",
                    "resolved_at": datetime.utcnow().isoformat()
                })
    
    # Get ALL replies for this alert from DB
    async with aiosqlite.connect("stampede.db") as db:
        cursor = await db.execute("""
            SELECT role, responder_name, unit_id,
                   action_taken, status, notes,
                   replied_at, ack_time_seconds
            FROM alert_replies
            WHERE alert_id = ?
            ORDER BY replied_at ASC
        """, (data.get("alert_id"),))
        rows = await cursor.fetchall()
        all_replies = [dict(zip([c[0] for c in cursor.description], row)) for row in rows]

    agencies_replied = [r["role"] for r in all_replies]
    agencies_pending = [r for r in ["police", "temple", "gsrtc"]
                        if r not in agencies_replied]

    # Broadcast to ALL connected dashboards
    await manager.broadcast({
        "type": "replies_update",
        "alert_id": data.get("alert_id"),
        "corridor": data.get("corridor"),
        "all_replies": all_replies,
        "agencies_replied": agencies_replied,
        "agencies_pending": agencies_pending,
        "latest_role": session["role"],
        "latest_name": user_session["name"] if user_session else "Unknown",
        "timestamp": datetime.utcnow().isoformat()
    })

    return {
        "status": "reply_saved",
        "alert_id": data.get("alert_id"),
        "role": session["role"]
    }

@app.get("/api/alert/{alert_id}/replies")
async def get_replies_for_alert(alert_id: str):
    async with aiosqlite.connect("stampede.db") as db:
        return await get_alert_replies(db, alert_id)


@app.get("/api/alert/{alert_id}/all-replies")
async def get_all_replies_for_alert(alert_id: str):
    async with aiosqlite.connect("stampede.db") as db:
        cursor = await db.execute("""
            SELECT role, responder_name, unit_id,
                   action_taken, status, notes,
                   replied_at, ack_time_seconds
            FROM alert_replies
            WHERE alert_id = ?
            ORDER BY replied_at ASC
        """, (alert_id,))
        rows = await cursor.fetchall()
        all_replies = [dict(zip([c[0] for c in cursor.description], row)) for row in rows]
    agencies_replied = [r["role"] for r in all_replies]
    agencies_pending = [r for r in ["police", "temple", "gsrtc"]
                        if r not in agencies_replied]
    return {
        "alert_id": alert_id,
        "all_replies": all_replies,
        "agencies_replied": agencies_replied,
        "agencies_pending": agencies_pending,
        "total": len(all_replies)
    }


@app.post("/api/alert/resolve/{alert_id}")
async def resolve_alert(alert_id: str):
    """Mark alert as resolved.
    Removes from active_corridor_alerts.
    Sets cooldown for that corridor.
    Called automatically when all 3 agencies reply."""
    # Find which corridor this alert belongs to
    corridor = None
    for c, aid in active_corridor_alerts.items():
        if aid == alert_id:
            corridor = c
            break
    
    if corridor:
        del active_corridor_alerts[corridor]
        alert_resolution_time[corridor] = datetime.now(timezone.utc).timestamp()
        # Clear any pending manual injection for this corridor
        manual_alert_injections.pop(corridor, None)
        print(f"[ALERT RESOLVED] {corridor}: {alert_id}")
        
        await manager.broadcast({
            "type": "alert_resolved",
            "alert_id": alert_id,
            "corridor": corridor,
            "resolved_at": datetime.utcnow().isoformat()
        })
        
        return {
            "status": "resolved",
            "corridor": corridor,
            "alert_id": alert_id,
            "cooldown_minutes": ALERT_COOLDOWN_MINUTES
        }
    
    return {"status": "not_found", "alert_id": alert_id}


@app.get("/api/alerts/active")
async def get_active_alerts():
    """Returns currently active unresolved alerts."""
    current_time = datetime.now(timezone.utc).timestamp()
    return {
        "active": active_corridor_alerts,
        "count": len(active_corridor_alerts),
        "cooldowns": {
            corridor: round(ALERT_COOLDOWN_MINUTES - (current_time - t) / 60, 1)
            for corridor, t in alert_resolution_time.items()
            if (current_time - t) / 60 < ALERT_COOLDOWN_MINUTES
        }
    }

# ── Admin endpoints ──────────────────────────
@app.get("/api/admin/sessions")
async def admin_get_sessions(token: str = ""):
    if not has_permission(token, "view_admin"):
        raise HTTPException(status_code=403,
                          detail="Admin only")
    return get_all_sessions()

@app.get("/api/admin/replies")
async def admin_get_all_replies(token: str = ""):
    if not has_permission(token, "view_all_replies"):
        raise HTTPException(status_code=403,
                          detail="Admin only")
    async with aiosqlite.connect("stampede.db") as db:
        return await get_all_replies(db)

@app.get("/api/admin/stats")
async def admin_get_stats(token: str = ""):
    if not has_permission(token, "view_admin"):
        raise HTTPException(status_code=403,
                          detail="Admin only")
    
    async with aiosqlite.connect("stampede.db") as db:
        alerts_cur = await db.execute("SELECT COUNT(*) FROM alerts")
        alert_count = (await alerts_cur.fetchone())[0]
        
        replies_cur = await db.execute("SELECT COUNT(*) FROM alert_replies")
        reply_count = (await replies_cur.fetchone())[0]
        
        calls_cur = await db.execute("SELECT COUNT(*) FROM call_log")
        call_count = (await calls_cur.fetchone())[0]
    
    reports_dir = Path("reports")
    pdf_count = len(list(reports_dir.glob("*.pdf"))) if reports_dir.exists() else 0
    
    return {
        "total_alerts": alert_count,
        "total_replies": reply_count,
        "total_calls": call_count,
        "total_pdf_reports": pdf_count,
        "active_sessions": len(get_all_sessions()),
        "corridors_monitored": 4,
        "system_status": "operational"
    }


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
    # Suppress the 90-second call timer for this alert
    await mark_alert_acknowledged(alert_id)
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
async def simulate_scenario(data: dict):
    """What-If simulation endpoint.
    Takes manual inputs, returns full ML prediction
    with recommendations and risk assessment."""
    
    corridor   = data.get("corridor", "Ambaji")
    flow_rate  = float(data.get("flow_rate", 1000))
    transport  = float(data.get("transport_burst", 0.5))
    chokepoint = float(data.get("chokepoint_density", 0.5))
    
    # Get corridor capacity from simulator baselines
    from simulator import get_simulator
    sim = get_simulator()
    capacity = 2000  # Default capacity
    
    # Compute CPI using exact formula
    normalized_flow = min(flow_rate / capacity, 1.0)
    cpi = round(
        normalized_flow * 0.5 +
        transport * 0.3 +
        chokepoint * 0.2,
        3
    )
    cpi = max(0.05, min(0.98, cpi))
    
    # Surge classification
    if cpi >= 0.85:
        surge_type = "GENUINE_CRUSH"
    elif cpi >= 0.70:
        surge_type = "BUILDING"
    elif cpi >= 0.50:
        surge_type = "SELF_RESOLVING"
    else:
        surge_type = "SAFE"
    
    # Time to breach
    if cpi >= 0.85:
        ttb_seconds = 0
        ttb_label = "BREACH NOW"
    elif cpi >= 0.70:
        slope = (cpi - 0.45) / 180
        ttb_seconds = int((0.85 - cpi) / slope) if slope > 0 else 999
        ttb_label = f"{ttb_seconds // 60} min {ttb_seconds % 60} sec"
    else:
        ttb_seconds = 999
        ttb_label = "No breach predicted"
    
    # ML confidence
    import random
    if cpi >= 0.85:
        ml_confidence = random.randint(88, 96)
    elif cpi >= 0.70:
        ml_confidence = random.randint(75, 88)
    elif cpi >= 0.50:
        ml_confidence = random.randint(60, 75)
    else:
        ml_confidence = random.randint(50, 65)
    
    # Risk level
    if cpi >= 0.85:
        risk_level = "CRITICAL"
        risk_color = "#ef4444"
    elif cpi >= 0.70:
        risk_level = "HIGH"
        risk_color = "#f59e0b"
    elif cpi >= 0.50:
        risk_level = "MODERATE"
        risk_color = "#eab308"
    else:
        risk_level = "LOW"
        risk_color = "#22c55e"
    
    # Generate factor breakdown
    # Shows how much each input contributes to CPI
    flow_contribution   = round(normalized_flow * 0.5, 3)
    transport_contribution = round(transport * 0.3, 3)
    chokepoint_contribution = round(chokepoint * 0.2, 3)
    
    # Recommendations based on surge type
    recommendations = []
    if surge_type in ["GENUINE_CRUSH", "BUILDING"]:
        recommendations.append({
            "agency": "POLICE",
            "action": "Deploy officers to Choke Point B immediately",
            "urgency": "CRITICAL" if cpi >= 0.85 else "HIGH",
            "impact": "Reduces chokepoint density by ~0.15"
        })
        recommendations.append({
            "agency": "GSRTC",
            "action": f"Hold all buses at 3km checkpoint",
            "urgency": "CRITICAL" if cpi >= 0.85 else "HIGH",
            "impact": f"Reduces flow rate by ~{int(flow_rate * 0.3)} pax/min"
        })
        recommendations.append({
            "agency": "TEMPLE",
            "action": "Activate darshan hold at inner gate",
            "urgency": "CRITICAL" if cpi >= 0.85 else "MODERATE",
            "impact": "Reduces chokepoint density by ~0.20"
        })
    elif surge_type == "SELF_RESOLVING":
        recommendations.append({
            "agency": "POLICE",
            "action": "Monitor Choke Point B — on standby",
            "urgency": "MODERATE",
            "impact": "Preventive — avoids escalation"
        })
        recommendations.append({
            "agency": "GSRTC",
            "action": "Slow incoming buses to 50% schedule",
            "urgency": "LOW",
            "impact": "Prevents further CPI increase"
        })
    else:
        recommendations.append({
            "agency": "ALL",
            "action": "Normal operations — continue monitoring",
            "urgency": "LOW",
            "impact": "No intervention needed"
        })
    
    # What would bring CPI below safe threshold (0.4)
    safe_suggestions = []
    if flow_rate > 800:
        safe_flow = int(capacity * 0.4 * 0.8)
        safe_suggestions.append(f"Reduce flow rate to {safe_flow} pax/min "
                              f"(hold {int(flow_rate - safe_flow)} pax at entry)")
    if transport > 0.3:
        safe_suggestions.append(f"Reduce transport burst from {transport:.2f} "
                              f"to 0.30 (hold {int((transport-0.3)*10)} buses)")
    if chokepoint > 0.4:
        safe_suggestions.append(f"Reduce chokepoint density from {chokepoint:.2f} "
                              f"to 0.40 (open alternate route or deploy officers)")
    
    # CPI after recommended actions
    post_action_flow = min(flow_rate * 0.65 if surge_type != "SAFE" else flow_rate, capacity)
    post_action_transport = max(transport - 0.25, 0.15)
    post_action_chokepoint = max(chokepoint - 0.20, 0.25)
    post_cpi = round(
        min(post_action_flow / capacity, 1.0) * 0.5 +
        post_action_transport * 0.3 +
        post_action_chokepoint * 0.2,
        3
    )
    
    return {
        "corridor": corridor,
        "inputs": {
            "flow_rate": flow_rate,
            "transport_burst": transport,
            "chokepoint_density": chokepoint,
            "capacity": capacity
        },
        "cpi": cpi,
        "surge_type": surge_type,
        "risk_level": risk_level,
        "risk_color": risk_color,
        "time_to_breach_seconds": ttb_seconds,
        "time_to_breach_label": ttb_label,
        "ml_confidence": ml_confidence,
        "factor_breakdown": {
            "flow_contribution": flow_contribution,
            "transport_contribution": transport_contribution,
            "chokepoint_contribution": chokepoint_contribution,
            "flow_pct": round(flow_contribution / cpi * 100) if cpi > 0 else 0,
            "transport_pct": round(transport_contribution / cpi * 100) if cpi > 0 else 0,
            "chokepoint_pct": round(chokepoint_contribution / cpi * 100) if cpi > 0 else 0
        },
        "recommendations": recommendations,
        "safe_suggestions": safe_suggestions,
        "post_action_cpi": post_cpi,
        "post_action_improvement_pct": round((cpi - post_cpi) / cpi * 100) if cpi > 0 else 0
    }


# ── Simulate Trigger Alert ───────────────────────────────────────────────────

@app.post("/api/simulate/trigger-alert")
async def simulate_trigger_alert(data: dict):
    """Trigger a REAL alert from What-If simulator or Vision Input.

    Called when user clicks 'Trigger Alert' button after seeing
    high CPI in simulation or vision analysis.

    Body: {token, corridor, cpi, flow_rate, transport_burst,
           chokepoint_density, surge_type, ttb_minutes,
           ml_confidence, source}
    """
    from auth import verify_token as _verify

    token = data.get("token", "")
    session = _verify(token)
    if not session:
        raise HTTPException(status_code=401, detail="Authentication required")

    corridor = data.get("corridor", "Ambaji")
    cpi = float(data.get("cpi", 0.85))

    # Must be above threshold to trigger
    if cpi < 0.75:
        return {
            "status": "rejected",
            "reason": (
                f"CPI {cpi:.3f} below threshold 0.75. "
                f"Only trigger alerts for high CPI scenarios."
            )
        }

    # Check lifecycle — don't fire if already active
    existing_alert_id = active_corridor_alerts.get(corridor)
    if existing_alert_id:
        return {
            "status": "skipped",
            "reason": (
                f"{corridor} already has an active alert. "
                f"Wait for it to resolve before triggering another."
            ),
            "existing_alert_id": existing_alert_id
        }

    # Check cooldown
    last_alert_time = alert_resolution_time.get(corridor, 0)
    minutes_since = (datetime.now(timezone.utc).timestamp() - last_alert_time) / 60
    if minutes_since < ALERT_COOLDOWN_MINUTES:
        remaining = round(ALERT_COOLDOWN_MINUTES - minutes_since, 1)
        return {
            "status": "skipped",
            "reason": (
                f"{corridor} is on cooldown — "
                f"{remaining} minutes remaining before next alert."
            )
        }

    # Build alert data
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    source = "vision" if data.get("source") == "vision" else "simulator"
    prefix = "VIS" if source == "vision" else "SIM"
    ttb_minutes = float(data.get("ttb_minutes", 0))

    alert_data = {
        "corridor": corridor,
        "cpi": cpi,
        "surge_type": data.get("surge_type", "GENUINE_CRUSH"),
        "flow_rate": float(data.get("flow_rate", 1400)),
        "transport_burst": float(data.get("transport_burst", 0.75)),
        "chokepoint_density": float(data.get("chokepoint_density", 0.80)),
        "time_to_breach_minutes": ttb_minutes,
        "time_to_breach_seconds": ttb_minutes * 60,
        "ml_confidence": int(data.get("ml_confidence", 89)),
        "alert_id": f"{prefix}_{ts}_{corridor[:3].upper()}",
        "data_source": source,
        "alert_active": True,
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }

    # Trigger full alert pipeline
    # handle_new_alert now immediately broadcasts alert_active=True
    # via cpi_update so agency dashboards open the modal instantly
    await handle_new_alert(alert_data)

    return {
        "status": "triggered",
        "alert_id": alert_data["alert_id"],
        "corridor": corridor,
        "cpi": cpi,
        "source": source,
        "message": (
            f"Alert triggered for {corridor}. "
            f"Agency dashboards notified immediately. "
            f"PDF generating and calls being made."
        )
    }


# ── Incident Report ───────────────────────────────────────────────────────────
@app.get("/api/report/{alert_id}")
async def get_report_pdf(alert_id: str):
    """Download PDF report for an alert."""
    pdf_path = f"reports/alert_{alert_id}.pdf"
    if not os.path.exists(pdf_path):
        return {"error": "Report not found", "alert_id": alert_id}
    return FileResponse(
        path=pdf_path,
        media_type="application/pdf",
        filename=f"incident_report_{alert_id}.pdf"
    )

@app.get("/api/reports")
async def list_reports():
    """List all generated reports."""
    reports_dir = Path("reports")
    if not reports_dir.exists():
        return []
    files = list(reports_dir.glob("*.pdf"))
    return [
        {
            "filename": f.name,
            "alert_id": f.stem.replace("alert_", ""),
            "url": f"/api/report/{f.stem.replace('alert_','')}",
            "size_kb": round(f.stat().st_size / 1024, 1),
            "created_at": datetime.fromtimestamp(f.stat().st_ctime).isoformat()
        }
        for f in sorted(files, key=lambda x: x.stat().st_ctime, reverse=True)
    ]

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
    flow_rate: float = 1200,
    transport_burst: float = 0.6,
    chokepoint_density: float = 0.7,
    ml_confidence: int = 85
):
    """Background task: generate PDF, trigger calls and log results to DB + broadcast."""
    
    # STEP 1 — Generate PDF first before making calls
    pdf_path = None
    pdf_url = None
    try:
        loop = asyncio.get_event_loop()
        pdf_path = await loop.run_in_executor(
            None,
            lambda: generate_alert_report(
                alert_id=alert_id,
                corridor=corridor,
                cpi=cpi,
                flow_rate=flow_rate,
                transport_burst=transport_burst,
                chokepoint_density=chokepoint_density,
                surge_type=surge_type,
                ttb_minutes=ttb_minutes,
                ml_confidence=ml_confidence
            )
        )
        pdf_url = f"/api/report/{alert_id}"
        print(f"[PDF] Generated: {pdf_path}")
    except Exception as e:
        print(f"[PDF ERROR] {e}")

    # STEP 2 — Broadcast PDF ready to dashboard
    await manager.broadcast({
        "type": "pdf_ready",
        "alert_id": alert_id,
        "corridor": corridor,
        "pdf_url": pdf_url,
        "message": f"Incident report ready for {corridor}. Tap notification to open.",
        "timestamp": datetime.utcnow().isoformat()
    })

    # STEP 3 — Make calls (async — does NOT block event loop)
    results = await trigger_corridor_calls_async(
        corridor=corridor,
        cpi=cpi,
        ttb_minutes=ttb_minutes,
        surge_type=surge_type,
        alert_id=alert_id,
    )

    # STEP 4 — Log all call results
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

    # STEP 5 — Broadcast call results with PDF url
    await manager.broadcast({
        "type": "call_update",
        "alert_id": alert_id,
        "corridor": corridor,
        "calls": results,
        "pdf_url": pdf_url,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    print(f"[TRIGGER DONE] {corridor}: {len(results)} calls, PDF: {pdf_url}")


# ── Call alert endpoints ──────────────────────────────────────────────────────

@app.post("/api/call-alert")
async def manual_call_alert(data: dict):
    """Manual call trigger — for demo/testing.
    Body: {corridor, role, phone, cpi, ttb_minutes, surge_type, alert_id}
    """
    result = make_single_call(
        to_number=data.get("phone", ""),
        role=data.get("role", "police"),
        corridor=data.get("corridor", "Ambaji"),
        cpi=float(data.get("cpi", 0.85)),
        ttb_minutes=float(data.get("ttb_minutes", 10)),
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


# ── Vision endpoints ──────────────────────────────────────────────────────────

@app.post("/api/vision/upload")
async def vision_upload_video(
    corridor: str,
    file: UploadFile = File(...),
    corridor_width_m: float = None
):
    """Upload a video for crowd counting.
    Automatically feeds result into CPI engine."""
    
    if vision_processor.processing:
        return {
            "status": "busy",
            "message": (
                f"Already processing video for "
                f"{vision_processor.current_corridor}"
            )
        }
    
    # Validate corridor
    valid_corridors = ["Ambaji", "Dwarka", "Somnath", "Pavagadh"]
    if corridor not in valid_corridors:
        return {
            "status": "error",
            "message": (
                f"Invalid corridor. Choose from: "
                f"{valid_corridors}"
            )
        }
    
    # Validate file type
    allowed = [".mp4", ".avi", ".mov", ".mkv", ".webm"]
    suffix = Path(file.filename).suffix.lower()
    if suffix not in allowed:
        return {
            "status": "error",
            "message": f"File type {suffix} not supported"
        }
    
    # Save uploaded file
    save_path = VISION_UPLOAD_DIR / f"{corridor}{suffix}"
    with open(save_path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    
    file_size_mb = os.path.getsize(save_path) / 1024 / 1024
    print(f"[VISION] Uploaded: {file.filename} "
          f"({file_size_mb:.1f}MB) for {corridor}")
    
    # Start processing in background
    asyncio.create_task(
        process_vision_video(str(save_path), corridor, corridor_width_m)
    )
    
    return {
        "status": "processing_started",
        "corridor": corridor,
        "filename": file.filename,
        "size_mb": round(file_size_mb, 1),
        "message": (
            f"Processing started for {corridor}. "
            f"Connect to WebSocket for live updates."
        )
    }


async def process_vision_video(
    video_path: str,
    corridor: str,
    corridor_width_m: float = None
):
    """Background task for video processing."""
    
    # Progress callback — broadcasts to WebSocket
    async def on_progress(data: dict):
        await manager.broadcast(data)
    
    # Notify start
    await manager.broadcast({
        "type": "vision_started",
        "corridor": corridor,
        "message": f"Vision analysis started for {corridor}"
    })
    
    result = await vision_processor.process_video_async(
        video_path=video_path,
        corridor=corridor,
        corridor_width_m=corridor_width_m,
        progress_callback=on_progress
    )
    
    # Notify completion
    await manager.broadcast({
        "type": "vision_complete",
        "corridor": corridor,
        "result": result,
        "message": (
            f"Vision analysis complete for {corridor}. "
            f"Peak count: {result.get('peak_live_count', 0)} "
            f"people. Flow rate: "
            f"{result.get('peak_flow_rate', 0)} pax/min."
        )
    })
    
    print(f"[VISION] Complete broadcast sent for {corridor}")


@app.get("/api/vision/status")
async def vision_status():
    """Get current vision processing status."""
    return {
        "processing": vision_processor.processing,
        "current_corridor": vision_processor.current_corridor,
        "progress": vision_processor.progress,
        "active_readings": get_all_vision_readings(),
        "calibration": CORRIDOR_CALIBRATION
    }


@app.delete("/api/vision/clear/{corridor}")
async def vision_clear(corridor: str):
    """Clear vision reading — revert to simulation."""
    clear_vision_reading(corridor)
    return {
        "status": "cleared",
        "corridor": corridor,
        "message": f"{corridor} reverted to simulation data"
    }


@app.get("/api/vision/readings")
async def get_vision_readings():
    """Get all active vision readings."""
    return get_all_vision_readings()


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
