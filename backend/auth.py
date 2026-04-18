import os
import time
import base64
import json
from typing import Optional

DEMO_USERS = {
    "admin_001": {
        "password": "admin123",
        "role": "admin",
        "name": "Admin Controller",
        "unit_id": "HQ_CONTROL",
        "display_name": "Emergency Control HQ",
        "color": "#EF4444"
    },
    "police_001": {
        "password": "police123",
        "role": "police",
        "name": "Inspector Mehta",
        "unit_id": "AMBAJI_PS",
        "display_name": "Ambaji Police Station",
        "color": "#3B82F6"
    },
    "police_002": {
        "password": "police456",
        "role": "police",
        "name": "Inspector Shah",
        "unit_id": "PAVAGADH_PS",
        "display_name": "Pavagadh Police Station",
        "color": "#3B82F6"
    },
    "gsrtc_001": {
        "password": "gsrtc123",
        "role": "gsrtc",
        "name": "Controller Joshi",
        "unit_id": "GSRTC_DEPOT_4",
        "display_name": "GSRTC North Zone Control",
        "color": "#F59E0B"
    },
    "gsrtc_002": {
        "password": "gsrtc456",
        "role": "gsrtc",
        "name": "Driver Ramesh Patel",
        "unit_id": "GJ-01-BUS-042",
        "display_name": "Bus GJ-01-BUS-042",
        "color": "#F59E0B"
    },
    "temple_001": {
        "password": "temple123",
        "role": "temple",
        "name": "Trustee Sharma",
        "unit_id": "AMBAJI_TEMPLE",
        "display_name": "Ambaji Temple Trust",
        "color": "#8B5CF6"
    },
    "temple_002": {
        "password": "temple456",
        "role": "temple",
        "name": "Manager Patel",
        "unit_id": "PAVAGADH_TEMPLE",
        "display_name": "Pavagadh Temple Trust",
        "color": "#8B5CF6"
    }
}

# Role permissions
PERMISSIONS = {
    "admin": [
        "view_dashboard", "view_map", "view_alerts",
        "view_events", "view_history", "view_replay",
        "view_compare", "view_admin", "view_pdf",
        "acknowledge_alert", "reply_alert",
        "view_all_replies", "manage_users",
        "configure_thresholds", "view_call_log",
        "export_all", "view_all_agencies"
    ],
    "police": [
        "view_dashboard", "view_map", "view_alerts",
        "view_events", "view_history", "view_compare",
        "view_pdf", "acknowledge_alert", "reply_alert"
    ],
    "gsrtc": [
        "view_dashboard", "view_map", "view_alerts",
        "view_events", "view_compare", "view_pdf",
        "acknowledge_alert", "reply_alert", "view_buses"
    ],
    "temple": [
        "view_dashboard", "view_map", "view_alerts",
        "view_events", "view_history", "view_compare",
        "view_pdf", "acknowledge_alert", "reply_alert"
    ]
}

# Active sessions store
sessions = {}

def generate_token(username: str, role: str, unit_id: str) -> str:
    payload = {
        "username": username,
        "role": role,
        "unit_id": unit_id,
        "issued_at": time.time()
    }
    encoded = base64.b64encode(json.dumps(payload).encode()).decode()
    return encoded

def verify_token(token: str) -> Optional[dict]:
    try:
        decoded = json.loads(base64.b64decode(token).decode())
        # Token valid for 24 hours
        if time.time() - decoded["issued_at"] > 86400:
            return None
        return decoded
    except Exception:
        return None

def login(username: str, password: str) -> Optional[dict]:
    user = DEMO_USERS.get(username)
    if not user or user["password"] != password:
        return None
    
    token = generate_token(username, user["role"], user["unit_id"])
    sessions[token] = {
        **user,
        "username": username,
        "token": token,
        "logged_in_at": time.time()
    }
    
    return {
        "token": token,
        "role": user["role"],
        "name": user["name"],
        "unit_id": user["unit_id"],
        "display_name": user["display_name"],
        "color": user["color"],
        "permissions": PERMISSIONS[user["role"]]
    }

def get_session(token: str) -> Optional[dict]:
    return sessions.get(token)

def has_permission(token: str, permission: str) -> bool:
    session = get_session(token)
    if not session:
        return False
    role = session["role"]
    return permission in PERMISSIONS.get(role, [])

def get_all_sessions() -> list:
    return [
        {
            "username": s["username"],
            "role": s["role"],
            "name": s["name"],
            "unit_id": s["unit_id"],
            "logged_in_at": s["logged_in_at"]
        }
        for s in sessions.values()
    ]