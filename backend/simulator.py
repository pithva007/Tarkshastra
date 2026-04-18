"""
CPI (Corridor Pressure Index) simulation engine with realistic state machine.

Each corridor has a STATE:
- NORMAL    → CPI slowly varies 0.2 to 0.5
- BUILDING  → CPI rising 0.5 to 0.75 over 3-5 minutes
- SURGE     → CPI stays HIGH 0.75 to 0.92 for 8-15 minutes
- RESOLVING → CPI slowly drops back to normal over 3-5 minutes

Baseline values are derived from TS-PS11.csv at startup.
"""
import os
import time
import uuid
import random
import math
from collections import deque
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# ── Constants ─────────────────────────────────────────────────────────────────
BREACH_THRESHOLD = 0.85
ALERT_LEAD_MINUTES = 12
DENSITY_DANGER_THRESHOLD = 8.0

# ── Load CSV baselines ────────────────────────────────────────────────────────
_CSV_PATH = os.path.join(os.path.dirname(__file__), "TS-PS11.csv")

def _load_baselines() -> Dict[str, dict]:
    defaults = {
        "Ambaji":   {"capacity_ppm": 442, "mean_flow": 130.4, "mean_transport": 0.293, "mean_density": 2.629, "width": 5.2},
        "Dwarka":   {"capacity_ppm": 433, "mean_flow": 129.2, "mean_transport": 0.299, "mean_density": 2.628, "width": 5.1},
        "Somnath":  {"capacity_ppm": 433, "mean_flow": 129.8, "mean_transport": 0.304, "mean_density": 2.647, "width": 5.1},
        "Pavagadh": {"capacity_ppm": 433, "mean_flow": 130.0, "mean_transport": 0.300, "mean_density": 2.616, "width": 5.1},
    }
    try:
        df = pd.read_excel(_CSV_PATH, engine="openpyxl")
        for loc in defaults:
            g = df[df["location"] == loc]
            if g.empty:
                continue
            mean_width = float(g["corridor_width_m"].mean())
            defaults[loc] = {
                "capacity_ppm":   round(mean_width * 85, 1),
                "mean_flow":      round(float(g["entry_flow_rate_pax_per_min"].mean()), 1),
                "mean_transport": round(float(g["transport_arrival_burst"].mean()), 4),
                "mean_density":   round(float(g["queue_density_pax_per_m2"].mean()), 4),
                "width":          round(mean_width, 2),
            }
        print(f"[simulator] CSV baselines loaded from {_CSV_PATH}")
    except Exception as exc:
        print(f"[simulator] CSV load failed ({exc}); using hardcoded defaults")
    return defaults

CORRIDOR_BASELINES: Dict[str, dict] = _load_baselines()

CORRIDOR_META = {
    "Ambaji":   {"chokepoints": 3, "location": (23.7267, 72.8503)},
    "Dwarka":   {"chokepoints": 2, "location": (22.2394, 68.9678)},
    "Somnath":  {"chokepoints": 2, "location": (20.8880, 70.4013)},
    "Pavagadh": {"chokepoints": 2, "location": (22.4673, 73.5315)},
}

# ── ML predictor (lazy import, graceful if not available) ─────────────────────
_ml_predict_fn = None
_ml_tried      = False

def _get_ml_predict():
    global _ml_predict_fn, _ml_tried
    if _ml_tried:
        return _ml_predict_fn
    _ml_tried = True
    try:
        from ml.predictor import predict_with_confidence
        _ml_predict_fn = predict_with_confidence
    except Exception:
        pass
    return _ml_predict_fn


# ── Corridor state machine for realistic CPI simulation ──────────────────────
CORRIDOR_STATES = {}  # corridor_name → state dict

def init_corridor_state(corridor):
    """Initialize corridor state with random phase offset."""
    return {
        "state": "NORMAL",
        "cpi": random.uniform(0.2, 0.4),
        "state_entered_at": time.time(),
        "state_duration": random.uniform(600, 1200),  # 10-20 minutes in normal
        "target_cpi": random.uniform(0.2, 0.4),
        "phase_offset": random.uniform(0, 6.28)
    }

def update_cpi(corridor_name, state_dict):
    """Update CPI based on current state.
    Called every 2 seconds.
    Returns new CPI value."""
    state = state_dict["state"]
    elapsed = time.time() - state_dict["state_entered_at"]
    duration = state_dict["state_duration"]
    progress = min(elapsed / duration, 1.0)
    
    if state == "NORMAL":
        # Gentle sine wave variation 0.2-0.5
        base = 0.35
        variation = 0.12
        cpi = base + variation * math.sin(time.time() * 0.05 + state_dict["phase_offset"])
        
        # Trigger BUILDING randomly
        if elapsed > duration:
            state_dict["state"] = "BUILDING"
            state_dict["state_entered_at"] = time.time()
            state_dict["state_duration"] = random.uniform(180, 300)  # 3-5 minutes
            state_dict["target_cpi"] = random.uniform(0.78, 0.92)
            print(f"[SURGE STARTING] {corridor_name} → BUILDING")
            
    elif state == "BUILDING":
        # CPI rises linearly toward target
        start_cpi = 0.45
        cpi = start_cpi + (state_dict["target_cpi"] - start_cpi) * progress
        # Add small noise
        cpi += random.uniform(-0.02, 0.02)
        
        if progress >= 1.0:
            state_dict["state"] = "SURGE"
            state_dict["state_entered_at"] = time.time()
            state_dict["state_duration"] = random.uniform(480, 900)  # 8-15 minutes
            print(f"[SURGE ACTIVE] {corridor_name} → SURGE")
            
    elif state == "SURGE":
        # CPI stays high with small fluctuations
        peak = state_dict["target_cpi"]
        cpi = peak + random.uniform(-0.04, 0.04)
        cpi = max(0.75, min(0.95, cpi))
        
        if progress >= 1.0:
            state_dict["state"] = "RESOLVING"
            state_dict["state_entered_at"] = time.time()
            state_dict["state_duration"] = random.uniform(180, 300)  # 3-5 minutes
            print(f"[RESOLVING] {corridor_name} → RESOLVING")
            
    elif state == "RESOLVING":
        # CPI drops back to normal
        start_cpi = state_dict["target_cpi"]
        end_cpi = random.uniform(0.2, 0.4)
        cpi = start_cpi + (end_cpi - start_cpi) * progress
        cpi += random.uniform(-0.02, 0.02)
        
        if progress >= 1.0:
            state_dict["state"] = "NORMAL"
            state_dict["state_entered_at"] = time.time()
            state_dict["state_duration"] = random.uniform(600, 1200)  # 10-20 minutes
            print(f"[NORMAL] {corridor_name} → NORMAL")
    
    state_dict["cpi"] = round(max(0.1, min(0.98, cpi)), 3)
    return state_dict["cpi"]

# Initialize all 4 corridors at startup with different phase offsets
CORRIDOR_STATES = {
    "Ambaji":   init_corridor_state("Ambaji"),
    "Dwarka":   init_corridor_state("Dwarka"),
    "Somnath":  init_corridor_state("Somnath"),
    "Pavagadh": init_corridor_state("Pavagadh"),
}

# Force different starting states for demo variety
CORRIDOR_STATES["Ambaji"]["state_duration"] = 300
CORRIDOR_STATES["Dwarka"]["state_entered_at"] = time.time() - 500
CORRIDOR_STATES["Pavagadh"]["state"] = "BUILDING"
CORRIDOR_STATES["Pavagadh"]["state_entered_at"] = time.time() - 120
CORRIDOR_STATES["Pavagadh"]["target_cpi"] = 0.88


class CorridorSimulator:
    def __init__(self, name: str):
        self.name = name
        self.baseline = CORRIDOR_BASELINES[name]
        self.cpi_history: deque = deque(maxlen=10)
        self.step = 0
        self.consecutive_high = 0
        self._active_alert_id: Optional[str] = None

    def tick(self) -> dict:
        self.step += 1
        
        # Use realistic state machine for CPI
        cpi = update_cpi(self.name, CORRIDOR_STATES[self.name])
        
        # Generate other metrics based on CPI
        flow_rate = self._sim_flow(cpi)
        transport = self._sim_transport(cpi)
        density = self._sim_density(cpi)

        self.cpi_history.append(cpi)
        self.consecutive_high = (self.consecutive_high + 1) if cpi > 0.70 else 0

        slope = self._slope()
        ttb_s = self._ttb_seconds(cpi, slope)
        surge = self._classify(cpi, slope, ttb_s)
        alert_active, alert_id = self._manage_alert(surge)

        # ── ML confidence enrichment ──────────────────────────────────────────
        ml_confidence = 70
        ml_risk_level = "MEDIUM"
        ml_fn = _get_ml_predict()
        if ml_fn is not None:
            try:
                ml_res = ml_fn({
                    "cpi":               cpi,
                    "flow_rate":         flow_rate,
                    "transport_burst":   transport,
                    "chokepoint_density": density,
                    "cpi_slope":         slope,
                    "cpi_history":       list(self.cpi_history),
                })
                ml_confidence = ml_res.get("confidence_score", 70)
                ml_risk_level = ml_res.get("risk_level", "MEDIUM")
            except Exception:
                pass

        # Add corridor state info to broadcast
        state_dict = CORRIDOR_STATES[self.name]
        state_duration_remaining = max(0, int(state_dict["state_duration"] - (time.time() - state_dict["state_entered_at"])))

        return {
            "type":                   "cpi_update",
            "corridor":               self.name,
            "cpi":                    round(cpi, 3),
            "flow_rate":              round(flow_rate, 1),
            "transport_burst":        round(transport, 3),
            "chokepoint_density":     round(density, 3),
            "surge_type":             surge,
            "time_to_breach_seconds": round(ttb_s, 1) if ttb_s is not None else None,
            "alert_active":           alert_active,
            "alert_id":               alert_id,
            "corridor_state":         state_dict["state"],
            "state_duration_remaining": state_duration_remaining,
            "consecutive_high":       self.consecutive_high,
            "ml_confidence":          ml_confidence,
            "ml_risk_level":          ml_risk_level,
            "timestamp":              datetime.now(timezone.utc).isoformat(),
        }

    def _sim_flow(self, cpi: float) -> float:
        """Generate flow rate based on CPI."""
        base = self.baseline["mean_flow"]
        # Higher CPI = higher flow rate
        multiplier = 1.0 + (cpi - 0.3) * 2.0
        flow = base * max(0.5, multiplier)
        noise = np.random.normal(0, base * 0.04)
        return float(max(10.0, flow + noise))

    def _sim_transport(self, cpi: float) -> float:
        """Generate transport burst based on CPI."""
        # Higher CPI = higher transport burst
        base = 0.2 + (cpi - 0.2) * 1.5
        return float(np.clip(base + np.random.normal(0, 0.04), 0.0, 1.0))

    def _sim_density(self, cpi: float) -> float:
        """Generate density based on CPI."""
        base = self.baseline["mean_density"]
        # Higher CPI = higher density
        multiplier = 1.0 + (cpi - 0.3) * 3.0
        density = base * max(0.3, multiplier)
        return float(max(0.2, density + np.random.normal(0, 0.15)))

    def _slope(self) -> float:
        if len(self.cpi_history) < 5:
            return 0.0
        hist = list(self.cpi_history)
        return (hist[-1] - hist[-5]) / 8.0

    def _ttb_seconds(self, cpi: float, slope: float) -> Optional[float]:
        if slope < 0.0005:
            return None
        secs = (BREACH_THRESHOLD - cpi) / slope
        return max(0.0, secs)

    def _classify(self, cpi: float, slope: float, ttb_s: Optional[float]) -> str:
        hist = list(self.cpi_history)
        if len(hist) >= 2 and hist[-2] > 0.01:
            if (hist[-2] - hist[-1]) / hist[-2] > 0.15:
                return "SELF_RESOLVING"
        if self.consecutive_high >= 3 and cpi > 0.70:
            return "GENUINE_CRUSH"
        if ttb_s is not None and ttb_s <= ALERT_LEAD_MINUTES * 60 and cpi > 0.50:
            return "PREDICTED_BREACH"
        if cpi > 0.75:
            return "HIGH_PRESSURE"
        return "NORMAL"

    def _manage_alert(self, surge: str) -> Tuple[bool, Optional[str]]:
        is_alert = surge in ("GENUINE_CRUSH", "PREDICTED_BREACH", "HIGH_PRESSURE")
        if is_alert:
            if self._active_alert_id is None:
                self._active_alert_id = (
                    f"ALT_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{self.name[:3].upper()}"
                )
            return True, self._active_alert_id
        else:
            self._active_alert_id = None
            return False, None


# ── Module-level simulator pool ───────────────────────────────────────────────
_pool: Dict[str, CorridorSimulator] = {
    name: CorridorSimulator(name) for name in CORRIDOR_BASELINES
}


def get_all_readings() -> List[dict]:
    return [sim.tick() for sim in _pool.values()]


def get_corridor_reading(corridor: str) -> Optional[dict]:
    sim = _pool.get(corridor)
    return sim.tick() if sim else None


def get_corridors() -> List[str]:
    return list(_pool.keys())


def get_corridor_config() -> dict:
    return {
        name: {**CORRIDOR_BASELINES[name], **CORRIDOR_META.get(name, {})}
        for name in CORRIDOR_BASELINES
    }