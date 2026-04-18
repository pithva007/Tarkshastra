"""
predictor.py
============
Production inference module — structured, dashboard-ready JSON output.

Public API
----------
predict(data_dict)           -> dict  (single reading)
predict_sequence(records)    -> list[dict]  (replay / historical sequence)
load_models()                -> None  (pre-load at startup)
model_info()                 -> dict

Output schema (predict)
-----------------------
{
  "prediction":          "SAFE" | "SURGE" | "HIGH_RISK",
  "confidence":          float,          # 0–1
  "label_id":            int,            # 0 / 1 / 2
  "probabilities":       {"SAFE": f, "SURGE": f, "HIGH_RISK": f},
  "pressure_index":      float,          # 0–100 from input
  "crush_risk_window": {
    "estimated_minutes": int,
    "status":            "SAFE_ZONE" | "WATCH" | "WARNING" | "CRITICAL",
    "note":              str
  },
  "classification_type": "SELF_RESOLVING_SURGE" | "GENUINE_BUILDUP" | "N/A",
  "agency_actions": {
    "police":    {"action": str, "message": str, "priority": str},
    "temple":    {"action": str, "message": str, "priority": str},
    "transport": {"action": str, "message": str, "priority": str}
  },
  "feature_explanation": [
    {"rank": int, "feature": str, "importance": float, "value": float|str},
    ...  # top-5 global feature importances with input values
  ],
  "temporal_horizon_minutes": 10
}
"""

from __future__ import annotations

import os
import joblib
import numpy as np
from typing import Optional

from ml.preprocessor import (
    apply_pipeline,
    dict_to_dataframe,
    sequence_to_dataframe,
    LABEL_NAMES,
    load_pipeline,
    TEMPORAL_SHIFT_MINUTES,
)

# ── Paths ─────────────────────────────────────────────────────────────────────
_BASE_DIR     = os.path.dirname(__file__)
MODEL_PATH    = os.path.join(_BASE_DIR, "models", "crowd_model.pkl")
PIPELINE_PATH = os.path.join(_BASE_DIR, "models", "preprocessing_pipeline.pkl")

# ── Singleton state ───────────────────────────────────────────────────────────
_model              = None
_pipeline           = None
_loaded             = False
_feature_importance : dict[str, float] = {}   # {feature_name: importance}


def _ensure_loaded() -> None:
    """Lazily load model + pipeline from disk (once per process)."""
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

    # Cache global feature importances for explanation
    feat_names = getattr(_pipeline, "feature_cols", [])
    importances = getattr(_model, "feature_importances_", np.array([]))
    if len(feat_names) == len(importances):
        _feature_importance = dict(zip(feat_names, importances.tolist()))

    _loaded = True
    print("[predictor] Model and pipeline loaded successfully.")


def load_models() -> None:
    """Pre-load artifacts at startup (zero cold-start latency)."""
    _ensure_loaded()


# ── Internal decision engines ─────────────────────────────────────────────────

def _crush_risk_window(
    label_id:       int,
    pressure_index: float,
    congestion_ratio: float,
    crush_window_raw: Optional[float],
) -> dict:
    """
    Estimate how many minutes until corridor breach (8–12 min logic).
    Uses raw `predicted_crush_window_min` from input if available,
    otherwise derives from pressure_index.
    """
    # Use dataset-provided window if sensible
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

    # Override towards imminent if HIGH_RISK detected
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

    return {
        "estimated_minutes": estimated,
        "status":            status,
        "note":              note,
    }


def _classification_type(
    label_id:         int,
    congestion_ratio: float,
    flow_acceleration: float,
    pressure_trend: float,
) -> str:
    """
    Distinguish between surge types:
      GENUINE_BUILDUP       — congestion + density rising together
      SELF_RESOLVING_SURGE  — spike but flow improving / plateau
      N/A                   — SAFE prediction
    """
    if label_id == 0:
        return "N/A"

    rising_congestion = congestion_ratio > 2.5
    accelerating_flow = flow_acceleration > 0
    rising_pressure   = pressure_trend > 0

    if rising_congestion and accelerating_flow and rising_pressure:
        return "GENUINE_BUILDUP"
    else:
        return "SELF_RESOLVING_SURGE"


def _agency_actions(label_id: int, pressure_index: float) -> dict:
    """
    Generate agency-specific recommended actions based on risk level.
    Each action has: action, message, priority.
    """
    if label_id == 2:  # HIGH_RISK
        return {
            "police": {
                "action":   "DEPLOY",
                "message":  "Deploy crowd control units immediately. Activate emergency protocols.",
                "priority": "CRITICAL",
            },
            "temple": {
                "action":   "HOLD_DARSHAN",
                "message":  "Halt darshan entry immediately. Redirect queues to designated holding areas.",
                "priority": "CRITICAL",
            },
            "transport": {
                "action":   "HOLD_BUSES",
                "message":  "Hold all incoming buses. No new arrivals for minimum 20 minutes.",
                "priority": "CRITICAL",
            },
        }
    elif label_id == 1:  # SURGE
        # Fine-tune by pressure index within SURGE
        if pressure_index >= 65:
            police_action  = "DEPLOY"
            police_msg     = "Deploy additional units. Crowd control teams on standby at corridor entry."
            temple_action  = "REDIRECT_QUEUE"
            temple_msg     = "Redirect incoming pilgrims to alternate queue immediately."
            transport_action = "STAGGER_ARRIVALS"
            transport_msg  = "Stagger bus arrivals by 10-minute intervals. No batch drops."
        else:
            police_action  = "MONITOR"
            police_msg     = "Increase patrol density. Monitor situation actively."
            temple_action  = "REDIRECT_QUEUE"
            temple_msg     = "Gently redirect overflow queue to secondary holding zone."
            transport_action = "STAGGER_ARRIVALS"
            transport_msg  = "Coordinate with depot — stagger next 3 trips by 5 minutes each."

        return {
            "police":    {"action": police_action,    "message": police_msg,    "priority": "HIGH"},
            "temple":    {"action": temple_action,    "message": temple_msg,    "priority": "HIGH"},
            "transport": {"action": transport_action, "message": transport_msg, "priority": "HIGH"},
        }
    else:  # SAFE
        return {
            "police": {
                "action":   "STANDBY",
                "message":  "Standard monitoring. Maintain situational awareness.",
                "priority": "LOW",
            },
            "temple": {
                "action":   "NORMAL_FLOW",
                "message":  "Continue normal darshan operations.",
                "priority": "LOW",
            },
            "transport": {
                "action":   "NORMAL",
                "message":  "Maintain standard bus schedule.",
                "priority": "LOW",
            },
        }


def _feature_explanation(input_df, top_n: int = 5) -> list[dict]:
    """
    Return top-N globally important features with their input values.
    Uses pre-cached feature_importances_ from the trained model.
    """
    if not _feature_importance:
        return []

    # Sort by global importance
    sorted_feats = sorted(
        _feature_importance.items(), key=lambda x: -x[1]
    )[:top_n]

    explanation = []
    for rank, (feat, imp) in enumerate(sorted_feats, 1):
        val = input_df[feat].iloc[0] if feat in input_df.columns else "N/A"
        # Round floats for readability
        if isinstance(val, (float, np.floating)):
            val = round(float(val), 3)
        elif isinstance(val, (np.integer,)):
            val = int(val)
        explanation.append({
            "rank":       rank,
            "feature":    feat,
            "importance": round(float(imp), 4),
            "value":      val,
        })
    return explanation


# ── Core predict function ─────────────────────────────────────────────────────

def predict(data_dict: dict) -> dict:
    """
    Predict crowd crush risk at t+10 minutes from a single real-time reading.

    Parameters
    ----------
    data_dict : dict — raw sensor/form JSON payload

    Returns
    -------
    Structured dict (see module docstring for full schema).
    """
    _ensure_loaded()

    # Build single-row DataFrame
    raw_df = dict_to_dataframe(data_dict)

    # Read raw values we need for output enrichment (before scaling)
    pressure_index    = float(raw_df.get("pressure_index", [30.0]).iloc[0])
    crush_window_raw  = raw_df.get("predicted_crush_window_min", [None]).iloc[0]

    # Apply preprocessing (engineer features + encode + scale)
    X = apply_pipeline(_pipeline, raw_df)

    # XGBoost inference
    label_id   = int(_model.predict(X)[0])
    proba      = _model.predict_proba(X)[0]   # shape (3,)
    confidence = float(proba[label_id])

    # ── Read engineered values needed for decision logic ──────────────────────
    from ml.preprocessor import engineer_features
    fe_df = engineer_features(raw_df)

    congestion_ratio  = float(fe_df.get("congestion_ratio",  [1.0]).iloc[0])
    flow_acceleration = float(fe_df.get("flow_acceleration", [0.0]).iloc[0])
    pressure_trend    = float(fe_df.get("pressure_trend_slope", [0.0]).iloc[0])

    # ── Build rich output ─────────────────────────────────────────────────────
    return {
        "prediction":   LABEL_NAMES[label_id],
        "confidence":   round(confidence, 4),
        "label_id":     label_id,
        "probabilities": {
            LABEL_NAMES[i]: round(float(proba[i]), 4)
            for i in range(len(proba))
            if i in LABEL_NAMES
        },
        "pressure_index":           round(pressure_index, 2),
        "crush_risk_window":        _crush_risk_window(
            label_id, pressure_index, congestion_ratio, crush_window_raw
        ),
        "classification_type":      _classification_type(
            label_id, congestion_ratio, flow_acceleration, pressure_trend
        ),
        "agency_actions":           _agency_actions(label_id, pressure_index),
        "feature_explanation":      _feature_explanation(fe_df),
        "temporal_horizon_minutes": TEMPORAL_SHIFT_MINUTES,
    }


# ── Replay / sequence mode ────────────────────────────────────────────────────

def predict_sequence(records: list[dict]) -> list[dict]:
    """
    Run predictions over a historical sequence (replay mode).

    Rolling features (3/5/10 min averages, trend slope) are computed
    across the full sequence, giving richer context than isolated calls.

    Parameters
    ----------
    records : list of dicts — ordered sequence of readings (oldest first)

    Returns
    -------
    list of prediction dicts, one per input record
    """
    _ensure_loaded()

    from ml.preprocessor import engineer_features

    if not records:
        return []

    # Build full-sequence DataFrame for coherent rolling features
    seq_df  = sequence_to_dataframe(records)
    fe_full = engineer_features(seq_df)

    results = []
    for i in range(len(records)):
        row_fe = fe_full.iloc[[i]]

        # Get raw values
        pressure_index   = float(seq_df.iloc[i].get("pressure_index", 30.0))
        crush_window_raw = seq_df.iloc[i].get("predicted_crush_window_min")

        # Transform single row using full-sequence pipeline
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
            "crush_risk_window":        _crush_risk_window(
                label_id, pressure_index, congestion_ratio, crush_window_raw
            ),
            "classification_type":      _classification_type(
                label_id, congestion_ratio, flow_acceleration, pressure_trend
            ),
            "agency_actions":           _agency_actions(label_id, pressure_index),
            "feature_explanation":      _feature_explanation(row_fe),
            "temporal_horizon_minutes": TEMPORAL_SHIFT_MINUTES,
        })

    return results


# ── Model metadata ────────────────────────────────────────────────────────────

def model_info() -> dict:
    """Return metadata about the loaded model."""
    _ensure_loaded()
    info = {
        "model_type":              type(_model).__name__,
        "classes":                 list(LABEL_NAMES.values()),
        "temporal_horizon_minutes": TEMPORAL_SHIFT_MINUTES,
        "top_features": sorted(
            _feature_importance.items(), key=lambda x: -x[1]
        )[:5] if _feature_importance else [],
        "model_path":    MODEL_PATH,
        "pipeline_path": PIPELINE_PATH,
    }
    if hasattr(_model, "n_features_in_"):
        info["n_features"] = _model.n_features_in_
    return info
