"""
Live bus position simulator for TS-11 Stampede Predictor.

Simulates 8 GSRTC buses on real Gujarat pilgrimage routes.
Positions interpolate along waypoints every 5 seconds.
Broadcasts bus_update WebSocket messages.
"""
import math
import random
from datetime import datetime, timezone
from typing import Dict, List, Optional

# ── Bus definitions ────────────────────────────────────────────────────────────
BUSES = [
    {
        "id": "GJ-01-BUS-042",
        "driver": "Ramesh Patel",
        "route": "Ahmedabad → Ambaji",
        "destination": "Ambaji",
        "waypoints": [
            [23.0225, 72.5714],
            [23.2156, 72.6412],
            [23.4521, 72.7234],
            [23.5812, 72.7891],
            [23.6534, 72.8012],
            [23.7267, 72.8503],
        ],
    },
    {
        "id": "GJ-05-BUS-118",
        "driver": "Suresh Modi",
        "route": "Rajkot → Dwarka",
        "destination": "Dwarka",
        "waypoints": [
            [22.3039, 70.8022],
            [22.2156, 70.4523],
            [22.2394, 68.9678],
        ],
    },
    {
        "id": "GJ-12-BUS-067",
        "driver": "Vijay Shah",
        "route": "Surat → Somnath",
        "destination": "Somnath",
        "waypoints": [
            [21.1702, 72.8311],
            [21.0423, 71.9812],
            [20.9412, 71.3821],
            [20.8880, 70.4013],
        ],
    },
    {
        "id": "GJ-08-BUS-234",
        "driver": "Mahesh Trivedi",
        "route": "Vadodara → Pavagadh",
        "destination": "Pavagadh",
        "waypoints": [
            [22.3072, 73.1812],
            [22.3891, 73.3421],
            [22.4673, 73.5315],
        ],
    },
    {
        "id": "GJ-03-BUS-089",
        "driver": "Dinesh Chauhan",
        "route": "Gandhinagar → Ambaji",
        "destination": "Ambaji",
        "waypoints": [
            [23.2156, 72.6369],
            [23.4012, 72.7123],
            [23.6012, 72.7891],
            [23.7267, 72.8503],
        ],
    },
    {
        "id": "GJ-07-BUS-156",
        "driver": "Kiran Joshi",
        "route": "Bhavnagar → Somnath",
        "destination": "Somnath",
        "waypoints": [
            [21.7645, 72.1519],
            [21.3456, 71.6234],
            [20.8880, 70.4013],
        ],
    },
    {
        "id": "GJ-09-BUS-301",
        "driver": "Amit Desai",
        "route": "Anand → Dwarka",
        "destination": "Dwarka",
        "waypoints": [
            [22.5645, 72.9289],
            [22.4712, 71.6234],
            [22.2394, 68.9678],
        ],
    },
    {
        "id": "GJ-11-BUS-445",
        "driver": "Pravin Patel",
        "route": "Surat → Pavagadh",
        "destination": "Pavagadh",
        "waypoints": [
            [21.1702, 72.8311],
            [21.8923, 73.0234],
            [22.4673, 73.5315],
        ],
    },
]

# Destination CPI lookup — keyed by destination name, updated externally
_destination_cpi: Dict[str, float] = {
    "Ambaji": 0.5,
    "Dwarka": 0.5,
    "Somnath": 0.5,
    "Pavagadh": 0.5,
}

# Per-bus progress state
_bus_state: Dict[str, dict] = {}


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


def _total_route_km(waypoints: List[List[float]]) -> float:
    total = 0.0
    for i in range(len(waypoints) - 1):
        total += _haversine_km(waypoints[i][0], waypoints[i][1], waypoints[i + 1][0], waypoints[i + 1][1])
    return total


def _init_bus_state():
    for bus in BUSES:
        bid = bus["id"]
        if bid not in _bus_state:
            _bus_state[bid] = {
                "progress": random.uniform(0.05, 0.85),
                "speed_kmh": random.uniform(45, 65),
                "passengers": random.randint(28, 52),
            }


def _interpolate_position(waypoints: List[List[float]], progress: float):
    """Return (lat, lng) for a given progress 0.0–1.0 along waypoints."""
    if progress <= 0.0:
        return waypoints[0][0], waypoints[0][1]
    if progress >= 1.0:
        return waypoints[-1][0], waypoints[-1][1]

    # Build cumulative distances
    segs = []
    total = 0.0
    for i in range(len(waypoints) - 1):
        d = _haversine_km(waypoints[i][0], waypoints[i][1], waypoints[i + 1][0], waypoints[i + 1][1])
        segs.append(d)
        total += d

    target = progress * total
    cum = 0.0
    for i, seg_len in enumerate(segs):
        if cum + seg_len >= target:
            t = (target - cum) / seg_len if seg_len > 0 else 0
            lat = waypoints[i][0] + t * (waypoints[i + 1][0] - waypoints[i][0])
            lng = waypoints[i][1] + t * (waypoints[i + 1][1] - waypoints[i][1])
            return lat, lng
        cum += seg_len

    return waypoints[-1][0], waypoints[-1][1]


def update_destination_cpi(corridor: str, cpi: float):
    """Called by main simulator to keep CPI values current."""
    if corridor in _destination_cpi:
        _destination_cpi[corridor] = cpi


def tick_buses(step: int) -> List[dict]:
    """Advance all buses one step and return their current state."""
    _init_bus_state()
    results = []

    for bus in BUSES:
        bid = bus["id"]
        state = _bus_state[bid]
        waypoints = bus["waypoints"]
        destination = bus["destination"]

        # Advance progress — each tick is 5 seconds
        speed_kmh = state["speed_kmh"] + random.uniform(-3, 3)
        speed_kmh = max(30, min(80, speed_kmh))
        state["speed_kmh"] = speed_kmh

        total_km = _total_route_km(waypoints)
        km_per_tick = (speed_kmh / 3600) * 5  # 5-second tick
        progress_delta = km_per_tick / total_km if total_km > 0 else 0

        state["progress"] = (state["progress"] + progress_delta) % 1.0

        lat, lng = _interpolate_position(waypoints, state["progress"])

        # Distance remaining to destination
        dest_lat, dest_lng = waypoints[-1][0], waypoints[-1][1]
        distance_km = _haversine_km(lat, lng, dest_lat, dest_lng)

        # ETA
        eta_minutes = int((distance_km / speed_kmh) * 60) if speed_kmh > 0 else 999

        # Alert status based on destination CPI
        dest_cpi = _destination_cpi.get(destination, 0.5)
        if dest_cpi >= 0.75:
            alert_status = "hold"
            alert_message = f"{destination} CPI at {dest_cpi:.2f} — STOP at checkpoint immediately"
        elif dest_cpi >= 0.55:
            alert_status = "caution"
            alert_message = f"{destination} CPI at {dest_cpi:.2f} — prepare to hold at checkpoint"
        else:
            alert_status = "normal"
            alert_message = f"{destination} CPI at {dest_cpi:.2f} — proceed normally"

        # Slight passenger variation
        if random.random() < 0.1:
            state["passengers"] = max(10, min(60, state["passengers"] + random.randint(-3, 3)))

        results.append({
            "id": bid,
            "driver": bus["driver"],
            "route": bus["route"],
            "destination": destination,
            "lat": round(lat, 6),
            "lng": round(lng, 6),
            "progress": round(state["progress"], 4),
            "eta_minutes": eta_minutes,
            "distance_km": round(distance_km, 1),
            "speed_kmh": round(speed_kmh, 1),
            "alert_status": alert_status,
            "alert_message": alert_message,
            "passengers": state["passengers"],
        })

    return results


def get_bus_update_message(step: int) -> dict:
    """Return a full bus_update WebSocket message."""
    buses = tick_buses(step)
    return {
        "type": "bus_update",
        "buses": buses,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
