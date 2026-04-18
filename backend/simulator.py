"""
CPI (Corridor Pressure Index) simulation engine.

Baseline values are derived from TS-PS11.csv at startup.

Formula (from problem statement):
  CPI = (flow_rate / capacity_ppm) * 0.5
      + transport_burst_factor * 0.3
      + chokepoint_density * 0.2

All three components are normalised to [0, 1] before weighting.
CPI output is clamped to [0.0, 1.0].
"""
import os
import time
import uuid
import random
from collections import deque
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# ── Constants ─────────────────────────────────────────────────────────────────
BREACH_THRESHOLD = 0.85
ALERT_LEAD_MINUTES = 12          # fire alert when TTB ≤ this
DENSITY_DANGER_THRESHOLD = 8.0   # pax/m² — normalisation denominator

# ── Load CSV baselines ────────────────────────────────────────────────────────
_CSV_PATH = os.path.join(os.path.dirname(__file__), "TS-PS11.csv")

def _load_baselines() -> Dict[str, dict]:
    """Return per-corridor stats derived from the dataset."""
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
                "capacity_ppm": round(mean_width * 85, 1),
                "mean_flow":    round(float(g["entry_flow_rate_pax_per_min"].mean()), 1),
                "mean_transport": round(float(g["transport_arrival_burst"].mean()), 4),
                "mean_density": round(float(g["queue_density_pax_per_m2"].mean()), 4),
                "width":        round(mean_width, 2),
            }
        print(f"[simulator] CSV baselines loaded from {_CSV_PATH}")
    except Exception as exc:
        print(f"[simulator] CSV load failed ({exc}); using hardcoded defaults")
    return defaults

CORRIDOR_BASELINES: Dict[str, dict] = _load_baselines()

# Additional corridor metadata (not in CSV)
CORRIDOR_META = {
    "Ambaji":   {"chokepoints": 3, "location": (24.3368, 72.8502)},
    "Dwarka":   {"chokepoints": 2, "location": (22.2394, 68.9678)},
    "Somnath":  {"chokepoints": 4, "location": (20.8880, 70.4012)},
    "Pavagadh": {"chokepoints": 3, "location": (22.4962, 73.5247)},
}


# ── Phase state machine ────────────────────────────────────────────────────────
_PHASE_TRANSITIONS = {
    "normal":          (["normal", "surge"],                [0.70, 0.30]),
    "surge":           (["critical", "surge_resolving"],    [0.40, 0.60]),
    "critical":        (["surge_resolving", "normal"],       [0.70, 0.30]),
    "surge_resolving": (["normal"],                         [1.00]),
}


class CorridorSimulator:
    def __init__(self, name: str):
        self.name = name
        self.baseline = CORRIDOR_BASELINES[name]
        self.cpi_history: deque = deque(maxlen=10)
        self.step = 0
        self.consecutive_high = 0          # CPI > 0.70 streak
        self._phase = "normal"
        self._phase_timer = 0
        self._phase_duration = random.randint(50, 100)
        self._active_alert_id: Optional[str] = None

    # ── Public tick ──────────────────────────────────────────────────────────
    def tick(self) -> dict:
        self.step += 1
        self._advance_phase()

        flow_rate    = self._sim_flow()
        transport    = self._sim_transport()
        density      = self._sim_density()

        # Normalise components to [0, 1]
        norm_flow    = min(flow_rate / self.baseline["capacity_ppm"], 1.0)
        norm_density = min(density / DENSITY_DANGER_THRESHOLD, 1.0)

        cpi = norm_flow * 0.5 + transport * 0.3 + norm_density * 0.2
        cpi = float(np.clip(cpi + np.random.normal(0, 0.007), 0.0, 1.0))

        self.cpi_history.append(cpi)
        self.consecutive_high = (self.consecutive_high + 1) if cpi > 0.70 else 0

        slope   = self._slope()
        ttb_s   = self._ttb_seconds(cpi, slope)
        surge   = self._classify(cpi, slope, ttb_s)
        alert_active, alert_id = self._manage_alert(surge)

        return {
            "type":                 "cpi_update",
            "corridor":             self.name,
            "cpi":                  round(cpi, 3),
            "flow_rate":            round(flow_rate, 1),
            "transport_burst":      round(transport, 3),
            "chokepoint_density":   round(norm_density, 3),
            "surge_type":           surge,
            "time_to_breach_seconds": round(ttb_s, 1) if ttb_s is not None else None,
            "alert_active":         alert_active,
            "alert_id":             alert_id,
            "phase":                self._phase,
            "consecutive_high":     self.consecutive_high,
            "timestamp":            datetime.now(timezone.utc).isoformat(),
        }

    # ── Phase machine ─────────────────────────────────────────────────────────
    def _advance_phase(self):
        self._phase_timer += 1
        if self._phase_timer < self._phase_duration:
            return
        self._phase_timer = 0
        self._phase_duration = random.randint(20, 60)
        phases, weights = _PHASE_TRANSITIONS.get(self._phase, (["normal"], [1.0]))
        self._phase = random.choices(phases, weights=weights)[0]

    # ── Component simulators ──────────────────────────────────────────────────
    def _sim_flow(self) -> float:
        b = self.baseline
        mult = {"normal": 1.05, "surge": 1.55, "critical": 2.0, "surge_resolving": 1.15}
        base = b["mean_flow"] * mult.get(self._phase, 1.0)
        base += 0.08 * b["capacity_ppm"] * np.sin(self.step * 0.12)
        noise = np.random.normal(0, b["mean_flow"] * 0.04)
        return float(max(10.0, base + noise))

    def _sim_transport(self) -> float:
        b = {"normal": 0.20, "surge": 0.60, "critical": 0.85, "surge_resolving": 0.25}
        base = b.get(self._phase, 0.20) * (self.baseline["mean_transport"] / 0.30)
        return float(np.clip(base + np.random.normal(0, 0.04), 0.0, 1.0))

    def _sim_density(self) -> float:
        b = {"normal": 1.0, "surge": 2.2, "critical": 3.5, "surge_resolving": 1.3}
        base = self.baseline["mean_density"] * b.get(self._phase, 1.0)
        return float(max(0.2, base + np.random.normal(0, 0.15)))

    # ── Analytics ─────────────────────────────────────────────────────────────
    def _slope(self) -> float:
        if len(self.cpi_history) < 5:
            return 0.0
        hist = list(self.cpi_history)
        # slope = (CPI[-1] - CPI[-5]) / time_delta  (each step = 2s, so 4 steps = 8s)
        return (hist[-1] - hist[-5]) / 8.0

    def _ttb_seconds(self, cpi: float, slope: float) -> Optional[float]:
        if slope < 0.0005:
            return None
        secs = (BREACH_THRESHOLD - cpi) / slope
        return max(0.0, secs)

    def _classify(self, cpi: float, slope: float, ttb_s: Optional[float]) -> str:
        hist = list(self.cpi_history)
        # Self-resolving: CPI dropped >15% in last 2 readings
        if len(hist) >= 2 and hist[-2] > 0.01:
            if (hist[-2] - hist[-1]) / hist[-2] > 0.15:
                return "SELF_RESOLVING"
        # Genuine crush
        if self.consecutive_high >= 3 and cpi > 0.70:
            return "GENUINE_CRUSH"
        # Predicted breach within window
        if ttb_s is not None and ttb_s <= ALERT_LEAD_MINUTES * 60 and cpi > 0.50:
            return "PREDICTED_BREACH"
        # Elevated
        if cpi > 0.75:
            return "HIGH_PRESSURE"
        return "NORMAL"

    def _manage_alert(self, surge: str) -> Tuple[bool, Optional[str]]:
        """Create or clear alert_id based on current surge classification."""
        is_alert = surge in ("GENUINE_CRUSH", "PREDICTED_BREACH", "HIGH_PRESSURE")
        if is_alert:
            if self._active_alert_id is None:
                self._active_alert_id = f"ALT_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{self.name[:3].upper()}"
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
