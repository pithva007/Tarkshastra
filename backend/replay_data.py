"""
Pre-recorded 20-minute near-crush scenario for Ambaji corridor.

Timeline (240 frames × 5 s = 20 min):
  00:00 – 05:00  Normal operations   CPI 0.30 – 0.40
  05:00 – 08:00  Surge building      CPI 0.40 – 0.65
  08:00          PREDICTION FIRES    TTB = 10 min → peak at 18:00
  08:00 – 15:00  Escalating          CPI 0.65 – 0.84
  15:00 – 18:00  Critical zone       CPI 0.84 – 0.92
  18:00          CRUSH PEAK          CPI 0.92
  18:00 – 20:00  Resolution          CPI 0.92 → 0.38
"""
import math
import random
from typing import List

random.seed(42)

FRAMES = 240          # 5-s intervals → 20 min
PRED_FRAME = 96       # 08:00 — prediction fires
PEAK_FRAME = 216      # 18:00 — crush peak (exactly 10 min after prediction)
CORRIDOR = "Ambaji"
CAPACITY_PPM = 442.0  # from CSV baseline (pax / min)


def _cpi_curve(i: int) -> float:
    t = i / 12.0  # minutes
    if t < 3.0:
        v = 0.28 + t * 0.022
    elif t < 5.0:
        v = 0.347 + (t - 3.0) * 0.038
    elif t < 8.0:
        v = 0.423 + (t - 5.0) * 0.072
    elif t < 10.0:
        v = 0.639 + (t - 8.0) * 0.048
    elif t < 15.0:
        v = 0.735 + (t - 10.0) * 0.021
    elif t < 18.0:
        v = 0.840 + (t - 15.0) * 0.026
    elif t < 18.5:
        v = 0.918 + (t - 18.0) * 0.004
    elif t < 20.0:
        v = 0.920 - ((t - 18.5) / 1.5) * 0.565
    else:
        v = 0.33
    noise = random.gauss(0, 0.010)
    return max(0.0, min(1.0, v + noise))


def _flow(cpi: float) -> float:
    base = 80 + cpi * 440
    return round(max(10.0, base + random.gauss(0, 18)), 1)


def _transport(cpi: float) -> float:
    return round(max(0.0, min(1.0, 0.12 + cpi * 0.75 + random.gauss(0, 0.025))), 3)


def _density(cpi: float) -> float:
    return round(max(0.2, min(1.0, 0.15 + cpi * 0.78 + random.gauss(0, 0.018))), 3)


def _slope_approx(i: int) -> float:
    ahead = _cpi_curve(min(i + 4, FRAMES - 1))
    behind = _cpi_curve(max(i - 4, 0))
    return (ahead - behind) / 16.0  # 16 s span


def generate_frames() -> List[dict]:
    frames = []
    for i in range(FRAMES):
        cpi = _cpi_curve(i)
        t_min = i / 12.0
        mm = int(t_min)
        ss = int((t_min % 1) * 60)

        flow = _flow(cpi)
        transport = _transport(cpi)
        density = _density(cpi)
        slope = _slope_approx(i)

        # time_to_breach_seconds — only meaningful between prediction and peak
        if PRED_FRAME <= i < PEAK_FRAME and slope > 0.0003:
            ttb_s = round(max(0.0, (PEAK_FRAME - i) * 5), 1)  # each frame = 5 s
        else:
            ttb_s = None

        prediction_fired = (i == PRED_FRAME)
        crush_peak = (i == PEAK_FRAME)

        # Surge type
        if i < PRED_FRAME:
            surge_type = "NORMAL"
        elif i < PEAK_FRAME:
            surge_type = "PREDICTED_BREACH"
        elif i < PEAK_FRAME + 12:
            surge_type = "GENUINE_CRUSH"
        elif crush_peak or i > PEAK_FRAME + 4:
            surge_type = "SELF_RESOLVING"
        else:
            surge_type = "NORMAL"

        # Alert status
        alert_active = surge_type not in ("NORMAL",)
        alert_id = (
            f"ALT_REPLAY_AMBAJI_001" if alert_active else None
        )

        # Alert message
        if surge_type == "PREDICTED_BREACH":
            alert_msg = f"WARNING: Breach predicted in {int(ttb_s // 60) if ttb_s else '?'} min — slope rising" if ttb_s else "WARNING: Pressure building"
        elif surge_type == "GENUINE_CRUSH":
            alert_msg = "CRITICAL: Genuine crush developing in Ambaji — deploy all units"
        elif surge_type == "SELF_RESOLVING":
            alert_msg = "MONITOR: Pressure dropping — surge self-resolving"
        else:
            alert_msg = ""

        frames.append({
            "index":                   i,
            "timestamp_s":             i * 5,
            "timestamp_label":         f"{mm:02d}:{ss:02d}",
            "corridor":                CORRIDOR,
            "cpi":                     round(cpi, 3),
            "flow_rate":               flow,
            "transport_burst":         transport,
            "chokepoint_density":      density,
            "slope":                   round(slope, 5),
            "surge_type":              surge_type,
            "time_to_breach_seconds":  ttb_s,
            "alert_active":            alert_active,
            "alert_id":                alert_id,
            "prediction_fired":        prediction_fired,
            "crush_peak":              crush_peak,
            "alert_message":           alert_msg,
            "phase": (
                "normal" if i < 60
                else "surge" if i < PRED_FRAME
                else "critical" if i <= PEAK_FRAME + 12
                else "surge_resolving"
            ),
        })
    return frames


# Module-level cache — generated once on import
REPLAY_FRAMES: List[dict] = generate_frames()
