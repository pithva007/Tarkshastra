"""
predictor.py
============
Production inference module — structured, dashboard-ready JSON output.

Public API
----------
predict(data_dict)                 -> dict  (XGBoost model)
predict_sequence(records)          -> list[dict]
predict_with_confidence(features)  -> {surge_type, confidence_score, risk_level}
predict_time_to_breach(cpi_history)-> float | None  (seconds)
load_models()                      -> None  (pre-load at startup)
model_info()                       -> dict

predict_with_confidence output
------------------------------
{
  "surge_type":       "SAFE" | "SELF_RESOLVING" | "GENUINE_CRUSH",
  "confidence_score": int,   # 0–100
  "risk_level":       "LOW" | "MEDIUM" | "HIGH" | "CRITICAL"
}
"""

from __future__ import annotations

import os
import joblib
import numpy as np
from datetime import datetime, timezone
from typing import Optional

from ml.preprocessor import (
    apply_pipeline,
    dict_to_dataframe,
    sequence_to_dataframe,
    engineer_simple_features,
    LABEL_NAMES,
    SIMPLE_FEATURES,
    SIMPLE_LABEL_NAMES,
    load_pipeline,
    TEMPORAL_SHIFT_MINUTES,
)

# ── Paths ─────────────────────────────────────────────────────────────────────
_BASE_DIR     = os.path.dirname(__file__)
MODEL_PATH    = os.path.join(_BASE_DIR, "models", "crowd_model.pkl")
PIPELINE_PATH = os.path.join(_BASE_DIR, "models", "preprocessing_pipeline.pkl")

# Simple RF model paths (ml/model.pkl, ml/scaler.pkl)
SIMPLE_MODEL_PATH  = os.path.join(_BASE_DIR, "model.pkl")
SIMPLE_SCALER_PATH = os.path.join(_BASE_DIR, "scaler.pkl")

# ── Singleton state — XGBoost (existing) ─────────────────────────────────────
_model              = None
_pipeline           = None
_loaded             = False
_feature_importance : dict[str, float] = {}

# ── Singleton state — Simple RF ───────────────────────────────────────────────
_simple_model    = None
_simple_scaler   = None
_simple_loaded   = False
_simple_accuracy : float | None = None


def _ensure_loaded() -> None:
    """Lazily load XGBoost model + pipeline from disk (once per process)."""
    global _model, _pipeline, _loaded, _feature_importance
    if _loaded:
        return
    if not os.path.exists(MODEL_PATH):
        raise FileNotFoundError(
            f"Trained model not found at {MODEL_PATH}. "
            "Run `python -m ml.train` first."
        )
    if not os.path.exists(PIPELINE_PATH):
        raise FileNotFoundError(
            f"Pipeline not found at {PIPELINE_PATH}. "
            "Run `python -m ml.train` first."
        )
    _model    = joblib.load(MODEL_PATH)
    _pipeline = load_pipeline(PIPELINE_PATH)

    feat_names  = getattr(_pipeline, "feature_cols", [])
    importances = getattr(_model, "feature_importances_", np.array([]))
    if len(feat_names) == len(importances):
        _feature_importance = dict(zip(feat_names, importances.tolist()))

    _loaded = True
    print("[predictor] XGBoost model and pipeline loaded successfully.")


def _load_simple() -> None:
    """Lazily load simple RF model + scaler (once per process)."""
    global _simple_model, _simple_scaler, _simple_loaded, _simple_accuracy
    if _simple_loaded:
        return
    if not os.path.exists(SIMPLE_MODEL_PATH):
        return  # will fall back to rule-based
    if not os.path.exists(SIMPLE_SCALER_PATH):
        return

    try:
        artifact = joblib.load(SIMPLE_MODEL_PATH)
        # Model file may contain {"model": ..., "accuracy": ...}
        if isinstance(artifact, dict):
            _simple_model    = artifact.get("model")
            _simple_accuracy = artifact.get("accuracy")
        else:
            _simple_model = artifact

        _simple_scaler = joblib.load(SIMPLE_SCALER_PATH)
        _simple_loaded = True
        print("[predictor] Simple RF model loaded successfully.")
    except Exception as e:
        print(f"[predictor] Failed to load simple RF model: {e}")


def load_models() -> None:
    """Pre-load all artifacts at startup (zero cold-start latency)."""
    _load_simple()
    try:
        _ensure_loaded()
    except FileNotFoundError as e:
        print(f"[predictor] {e}")


# ── Rule-based fallback ───────────────────────────────────────────────────────

def _rule_based_confidence(cpi: float, slope: float = 0.0) -> dict:
    """Compute surge type + confidence from CPI thresholds."""
    if cpi >= 0.85 or (cpi >= 0.70 and slope > 0.025):
        return {
            "surge_type":       "GENUINE_CRUSH",
            "confidence_score": min(99, int(60 + cpi * 39)),
            "risk_level":       "CRITICAL",
        }
    if cpi >= 0.70:
        return {
            "surge_type":       "GENUINE_CRUSH",
            "confidence_score": int(55 + (cpi - 0.70) * 150),
            "risk_level":       "HIGH",
        }
    if cpi >= 0.50:
        return {
            "surge_type":       "SELF_RESOLVING",
            "confidence_score": int(45 + (cpi - 0.50) * 100),
            "risk_level":       "MEDIUM",
        }
    return {
        "surge_type":       "SAFE",
        "confidence_score": int(max(50, 95 - int(cpi * 80))),
        "risk_level":       "LOW",
    }


def _risk_level_from_label(label_id: int, cpi: float) -> str:
    if label_id == 2 or cpi >= 0.85:
        return "CRITICAL"
    if label_id == 1 and cpi >= 0.70:
        return "HIGH"
    if label_id == 1:
        return "MEDIUM"
    return "LOW"


# ── predict_with_confidence ───────────────────────────────────────────────────

def predict_with_confidence(features: dict) -> dict:
    """
    Lightweight surge classification with confidence score.
    Used for WebSocket broadcast enrichment (ml_confidence, ml_risk_level).

    Input keys (all optional, with defaults):
      cpi               float  0–1
      flow_rate         float  pax/min
      transport_burst   float  0–1
      chokepoint_density float 0–1
      cpi_slope         float  CPI units/s
      cpi_history       list   recent CPI values (newest last)

    Returns:
      {surge_type, confidence_score (0-100), risk_level}
    """
    _load_simple()

    cpi        = float(features.get("cpi", 0.3))
    cpi_slope  = float(features.get("cpi_slope", 0.0))
    cpi_history: list = features.get("cpi_history", [])

    # Compute rolling mean from history if provided
    if cpi_history and len(cpi_history) >= 2:
        rolling_mean = float(np.mean(cpi_history[-5:]))
        if len(cpi_history) >= 5:
            cpi_slope = float(
                (cpi_history[-1] - cpi_history[-5]) / (4 * 2.0)
            )  # 4 steps × 2s each
    else:
        rolling_mean = cpi

    if _simple_loaded and _simple_model is not None and _simple_scaler is not None:
        try:
            import pandas as pd
            row = {
                "flow_rate":         float(features.get("flow_rate", 100.0)),
                "transport_burst":   float(features.get("transport_burst", 0.2)),
                "chokepoint_density": float(features.get("chokepoint_density", 0.3)),
                "cpi_rolling_mean_5": rolling_mean,
                "cpi_slope":         cpi_slope,
                "hour_of_day":       datetime.now(timezone.utc).hour,
                "day_type":          int(features.get("day_type", 0)),
            }
            X_raw = pd.DataFrame([row])[SIMPLE_FEATURES]
            X = _simple_scaler.transform(X_raw)
            label_id   = int(_simple_model.predict(X)[0])
            proba      = _simple_model.predict_proba(X)[0]
            confidence = int(round(float(proba[label_id]) * 100))
            surge_type = SIMPLE_LABEL_NAMES.get(label_id, "SAFE")
            risk_level = _risk_level_from_label(label_id, cpi)
            return {
                "surge_type":       surge_type,
                "confidence_score": confidence,
                "risk_level":       risk_level,
            }
        except Exception as e:
            print(f"[predictor] Simple RF inference failed: {e}, using rule-based")

    return _rule_based_confidence(cpi, cpi_slope)


# ── predict_time_to_breach ────────────────────────────────────────────────────

def predict_time_to_breach(cpi_history: list, breach_threshold: float = 0.85) -> Optional[float]:
    """
    Estimate seconds until CPI reaches breach_threshold using linear slope.

    Parameters
    ----------
    cpi_history : list of recent CPI floats (newest last), at 2s intervals
    breach_threshold : default 0.85

    Returns
    -------
    float seconds, or None if slope ≤ 0 or already breached
    """
    if not cpi_history or len(cpi_history) < 2:
        return None

    current_cpi = float(cpi_history[-1])
    if current_cpi >= breach_threshold:
        return 0.0

    window = min(5, len(cpi_history))
    hist = cpi_history[-window:]

    # Slope in CPI units per second (each reading = 2s interval)
    if window >= 2:
        slope = (hist[-1] - hist[0]) / ((window - 1) * 2.0)
    else:
        return None

    if slope <= 0.0005:
        return None

    ttb = (breach_threshold - current_cpi) / slope
    return max(0.0, float(ttb))


# ── Internal decision engines ─────────────────────────────────────────────────

def _crush_risk_window(
    label_id:       int,
    pressure_index: float,
    congestion_ratio: float,
    crush_window_raw: Optional[float],
) -> dict:
    if crush_window_raw is not None and 1 <= crush_window_raw <= 30:
        estimated = int(round(crush_window_raw))
    else:
        if pressure_index >= 85:
            estimated = 4
        elif pressure_index >= 70:
            estimated = 8
        elif pressure_index >= 55:
            estimated = 12
        elif pressure_index >= 40:
            estimated = 20
        else:
            estimated = 35

    if label_id == 2:
        estimated = min(estimated, 8)
    elif label_id == 1:
        estimated = min(estimated, 15)

    if estimated <= 5:
        status = "CRITICAL"
        note   = "Breach imminent — immediate intervention required"
    elif estimated <= 10:
        status = "WARNING"
        note   = f"Breach predicted in ~{estimated} min (8–12 min window)"
    elif estimated <= 18:
        status = "WATCH"
        note   = f"Elevated pressure — monitor closely ({estimated} min horizon)"
    else:
        status = "SAFE_ZONE"
        note   = f"Normal operations — no breach expected in {estimated}+ min"

    return {"estimated_minutes": estimated, "status": status, "note": note}


def _classification_type(
    label_id:         int,
    congestion_ratio: float,
    flow_acceleration: float,
    pressure_trend: float,
) -> str:
    if label_id == 0:
        return "N/A"
    rising_congestion = congestion_ratio > 2.5
    accelerating_flow = flow_acceleration > 0
    rising_pressure   = pressure_trend > 0
    if rising_congestion and accelerating_flow and rising_pressure:
        return "GENUINE_BUILDUP"
    return "SELF_RESOLVING_SURGE"


def _agency_actions(label_id: int, pressure_index: float) -> dict:
    if label_id == 2:
        return {
            "police":    {"action": "DEPLOY",        "message": "Deploy crowd control units immediately. Activate emergency protocols.", "priority": "CRITICAL"},
            "temple":    {"action": "HOLD_DARSHAN",   "message": "Halt darshan entry immediately. Redirect queues to designated holding areas.", "priority": "CRITICAL"},
            "transport": {"action": "HOLD_BUSES",     "message": "Hold all incoming buses. No new arrivals for minimum 20 minutes.", "priority": "CRITICAL"},
        }
    if label_id == 1:
        if pressure_index >= 65:
            return {
                "police":    {"action": "DEPLOY",           "message": "Deploy additional units. Crowd control teams on standby at corridor entry.", "priority": "HIGH"},
                "temple":    {"action": "REDIRECT_QUEUE",   "message": "Redirect incoming pilgrims to alternate queue immediately.", "priority": "HIGH"},
                "transport": {"action": "STAGGER_ARRIVALS", "message": "Stagger bus arrivals by 10-minute intervals. No batch drops.", "priority": "HIGH"},
            }
        return {
            "police":    {"action": "MONITOR",          "message": "Increase patrol density. Monitor situation actively.", "priority": "HIGH"},
            "temple":    {"action": "REDIRECT_QUEUE",   "message": "Gently redirect overflow queue to secondary holding zone.", "priority": "HIGH"},
            "transport": {"action": "STAGGER_ARRIVALS", "message": "Coordinate with depot — stagger next 3 trips by 5 minutes each.", "priority": "HIGH"},
        }
    return {
        "police":    {"action": "STANDBY",     "message": "Standard monitoring. Maintain situational awareness.", "priority": "LOW"},
        "temple":    {"action": "NORMAL_FLOW", "message": "Continue normal darshan operations.", "priority": "LOW"},
        "transport": {"action": "NORMAL",      "message": "Maintain standard bus schedule.", "priority": "LOW"},
    }


def _feature_explanation(input_df, top_n: int = 5) -> list[dict]:
    if not _feature_importance:
        return []
    sorted_feats = sorted(_feature_importance.items(), key=lambda x: -x[1])[:top_n]
    explanation  = []
    for rank, (feat, imp) in enumerate(sorted_feats, 1):
        val = input_df[feat].iloc[0] if feat in input_df.columns else "N/A"
        if isinstance(val, (float, np.floating)):
            val = round(float(val), 3)
        elif isinstance(val, (np.integer,)):
            val = int(val)
        explanation.append({"rank": rank, "feature": feat, "importance": round(float(imp), 4), "value": val})
    return explanation


# ── Core predict function (XGBoost) ──────────────────────────────────────────

def predict(data_dict: dict) -> dict:
    """Predict crowd crush risk using XGBoost model."""
    _ensure_loaded()

    raw_df = dict_to_dataframe(data_dict)
    pressure_index   = float(raw_df.get("pressure_index", [30.0]).iloc[0])
    crush_window_raw = raw_df.get("predicted_crush_window_min", [None]).iloc[0]

    X = apply_pipeline(_pipeline, raw_df)

    label_id   = int(_model.predict(X)[0])
    proba      = _model.predict_proba(X)[0]
    confidence = float(proba[label_id])

    from ml.preprocessor import engineer_features
    fe_df = engineer_features(raw_df)

    congestion_ratio  = float(fe_df.get("congestion_ratio",  [1.0]).iloc[0])
    flow_acceleration = float(fe_df.get("flow_acceleration", [0.0]).iloc[0])
    pressure_trend    = float(fe_df.get("pressure_trend_slope", [0.0]).iloc[0])

    return {
        "prediction":   LABEL_NAMES[label_id],
        "confidence":   round(confidence, 4),
        "label_id":     label_id,
        "probabilities": {
            LABEL_NAMES[i]: round(float(proba[i]), 4)
            for i in range(len(proba)) if i in LABEL_NAMES
        },
        "pressure_index":           round(pressure_index, 2),
        "crush_risk_window":        _crush_risk_window(label_id, pressure_index, congestion_ratio, crush_window_raw),
        "classification_type":      _classification_type(label_id, congestion_ratio, flow_acceleration, pressure_trend),
        "agency_actions":           _agency_actions(label_id, pressure_index),
        "feature_explanation":      _feature_explanation(fe_df),
        "temporal_horizon_minutes": TEMPORAL_SHIFT_MINUTES,
    }


# ── Replay / sequence mode ────────────────────────────────────────────────────

def predict_sequence(records: list[dict]) -> list[dict]:
    """Run predictions over a historical sequence (replay mode)."""
    _ensure_loaded()

    from ml.preprocessor import engineer_features

    if not records:
        return []

    seq_df  = sequence_to_dataframe(records)
    fe_full = engineer_features(seq_df)

    results = []
    for i in range(len(records)):
        row_fe           = fe_full.iloc[[i]]
        pressure_index   = float(seq_df.iloc[i].get("pressure_index", 30.0))
        crush_window_raw = seq_df.iloc[i].get("predicted_crush_window_min")

        feature_cols = getattr(_pipeline, "feature_cols", [])
        for col in feature_cols:
            if col not in row_fe.columns:
                row_fe = row_fe.copy()
                row_fe[col] = 0.0
        X = _pipeline.transform(row_fe[feature_cols])

        label_id   = int(_model.predict(X)[0])
        proba      = _model.predict_proba(X)[0]
        confidence = float(proba[label_id])

        congestion_ratio  = float(row_fe.get("congestion_ratio",  [1.0]).iloc[0])
        flow_acceleration = float(row_fe.get("flow_acceleration", [0.0]).iloc[0])
        pressure_trend    = float(row_fe.get("pressure_trend_slope", [0.0]).iloc[0])

        results.append({
            "step":         i,
            "prediction":   LABEL_NAMES[label_id],
            "confidence":   round(confidence, 4),
            "label_id":     label_id,
            "probabilities": {
                LABEL_NAMES[j]: round(float(proba[j]), 4)
                for j in range(len(proba)) if j in LABEL_NAMES
            },
            "pressure_index":           round(pressure_index, 2),
            "crush_risk_window":        _crush_risk_window(label_id, pressure_index, congestion_ratio, crush_window_raw),
            "classification_type":      _classification_type(label_id, congestion_ratio, flow_acceleration, pressure_trend),
            "agency_actions":           _agency_actions(label_id, pressure_index),
            "feature_explanation":      _feature_explanation(row_fe),
            "temporal_horizon_minutes": TEMPORAL_SHIFT_MINUTES,
        })

    return results


# ── Model metadata ────────────────────────────────────────────────────────────

def model_info() -> dict:
    """Return metadata about loaded models."""
    _load_simple()

    info: dict = {
        "model_type":               "XGBoost (primary) + RandomForest (simple)",
        "classes":                  list(LABEL_NAMES.values()),
        "temporal_horizon_minutes": TEMPORAL_SHIFT_MINUTES,
        "features":                 SIMPLE_FEATURES,
        "simple_model_loaded":      _simple_loaded,
        "model_path":               MODEL_PATH,
        "pipeline_path":            PIPELINE_PATH,
        "simple_model_path":        SIMPLE_MODEL_PATH,
        "simple_scaler_path":       SIMPLE_SCALER_PATH,
    }

    if _simple_accuracy is not None:
        info["accuracy"] = _simple_accuracy
        info["trained_on"] = "TS-PS11.csv"

    try:
        _ensure_loaded()
        info["xgb_loaded"] = True
        info["top_features"] = sorted(
            _feature_importance.items(), key=lambda x: -x[1]
        )[:5] if _feature_importance else []
        if hasattr(_model, "n_features_in_"):
            info["n_features"] = _model.n_features_in_
    except FileNotFoundError:
        info["xgb_loaded"] = False

    return info
