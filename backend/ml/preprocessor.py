"""
preprocessor.py
===============
Feature engineering and sklearn preprocessing pipeline for the
crowd crush risk prediction model (t+10 min temporal prediction).

Exports
-------
build_preprocessing_pipeline(df)  ->  (X_df, y_series, pipeline)
apply_pipeline(pipeline, raw_df)  ->  np.ndarray
load_pipeline(path)               ->  Pipeline
save_pipeline(pipeline, path)
LABEL_MAP                         ->  {str: int}
LABEL_NAMES                       ->  {int: str}
TEMPORAL_SHIFT_MINUTES            ->  int  (10)
"""

from __future__ import annotations

import os
import joblib
import numpy as np
import pandas as pd
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler, OrdinalEncoder
from sklearn.compose import ColumnTransformer
from typing import Tuple

# ── Label mapping ─────────────────────────────────────────────────────────────
LABEL_MAP: dict[str, int] = {
    "Low":      0,  # SAFE
    "Moderate": 1,  # SURGE
    "High":     2,  # HIGH_RISK
    "Critical": 2,  # HIGH_RISK (merged)
}

LABEL_NAMES: dict[int, str] = {
    0: "SAFE",
    1: "SURGE",
    2: "HIGH_RISK",
}

# Predict risk this many minutes ahead
TEMPORAL_SHIFT_MINUTES: int = 10

# ── Raw feature columns present in the dataset ────────────────────────────────
_RAW_NUMERIC: list[str] = [
    "corridor_width_m",
    "entry_flow_rate_pax_per_min",
    "exit_flow_rate_pax_per_min",
    "transport_arrival_burst",
    "vehicle_count",
    "queue_density_pax_per_m2",
    "festival_peak",
    "pressure_index",
    "predicted_crush_window_min",
]

_RAW_CATEGORICAL: list[str] = ["location", "weather"]

# Populated after pipeline fit
FEATURE_COLS: list[str] = []


# ── Feature engineering ───────────────────────────────────────────────────────

def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Apply all feature engineering to a DataFrame.

    New features vs v1:
      flow_acceleration       — row-wise diff of entry_flow (renamed from delta_flow)
      transport_burst_indicator — binary flag: transport_arrival_burst > 0
      pressure_trend_slope    — slope of pressure_index over last 5 rows
      rolling_flow_3/5/10     — rolling mean of entry_flow
      rolling_density_3       — rolling mean of density
      rolling_pressure_3      — rolling mean of pressure_index
      density                 — entry_flow / corridor_width
      congestion_ratio        — entry_flow / (exit_flow + 1)
    """
    df = df.copy()

    # ── Primary engineered features ───────────────────────────────────────────
    df["density"] = (
        df["entry_flow_rate_pax_per_min"]
        / df["corridor_width_m"].replace(0, 1)
    )
    df["congestion_ratio"] = (
        df["entry_flow_rate_pax_per_min"]
        / (df["exit_flow_rate_pax_per_min"] + 1.0)
    )

    # Rate of change of entry flow (acceleration)
    df["flow_acceleration"] = df["entry_flow_rate_pax_per_min"].diff().fillna(0.0)

    # Binary transport burst indicator
    df["transport_burst_indicator"] = (
        df["transport_arrival_burst"] > 0
    ).astype(int)

    # Pressure trend slope over last 5 rows (linear regression slope proxy)
    def _rolling_slope(series: pd.Series, window: int = 5) -> pd.Series:
        """Approximate slope = (last - first) / window for a rolling window."""
        roll_last  = series.rolling(window=window, min_periods=2).apply(lambda x: x[-1])
        roll_first = series.rolling(window=window, min_periods=2).apply(lambda x: x[0])
        return ((roll_last - roll_first) / window).fillna(0.0)

    df["pressure_trend_slope"] = _rolling_slope(df["pressure_index"], window=5)

    # ── Rolling averages (min_periods=1 for single-row inference) ─────────────
    for w in (3, 5, 10):
        df[f"rolling_flow_{w}"] = (
            df["entry_flow_rate_pax_per_min"]
            .rolling(window=w, min_periods=1)
            .mean()
        )

    df["rolling_density_3"]  = df["density"].rolling(window=3, min_periods=1).mean()
    df["rolling_pressure_3"] = df["pressure_index"].rolling(window=3, min_periods=1).mean()

    return df


def _get_feature_names(engineered_df: pd.DataFrame) -> list[str]:
    """Return ordered list of all feature columns after engineering."""
    base = _RAW_NUMERIC + [
        "density",
        "congestion_ratio",
        "flow_acceleration",
        "transport_burst_indicator",
        "pressure_trend_slope",
        "rolling_flow_3",
        "rolling_flow_5",
        "rolling_flow_10",
        "rolling_density_3",
        "rolling_pressure_3",
    ]
    return [c for c in base if c in engineered_df.columns]


# ── Temporal shift (per-location) ─────────────────────────────────────────────

def apply_temporal_shift(
    df: pd.DataFrame,
    y: pd.Series,
    shift: int = TEMPORAL_SHIFT_MINUTES,
) -> Tuple[pd.DataFrame, pd.Series]:
    """
    Shift the target label forward by `shift` rows per location so the model
    learns: "given features at time t, predict risk at t + shift minutes."

    Rows where the future label is unavailable (last `shift` rows per location)
    are dropped to prevent NaN targets.
    """
    y_shifted = y.copy().astype(float)

    if "location" in df.columns:
        for loc in df["location"].unique():
            mask = df["location"] == loc
            y_shifted.loc[mask] = y.loc[mask].shift(-shift).values
    else:
        y_shifted = y.shift(-shift)

    # Drop rows with NaN target
    valid = y_shifted.notna()
    df    = df[valid].reset_index(drop=True)
    y_out = y_shifted[valid].astype(int).reset_index(drop=True)
    return df, y_out


# ── Pipeline builder ──────────────────────────────────────────────────────────

def build_preprocessing_pipeline(
    df: pd.DataFrame,
    temporal_shift: bool = True,
) -> Tuple[pd.DataFrame, pd.Series, Pipeline]:
    """
    Full offline preprocessing for training:
      1. Sort by timestamp
      2. Map risk_level labels
      3. Apply temporal shift (predict t+10)
      4. Engineer features
      5. Fit ColumnTransformer (OrdinalEncoder + StandardScaler)

    Parameters
    ----------
    df             : raw DataFrame loaded from TS-PS11.xlsx
    temporal_shift : if True (default), shift labels by TEMPORAL_SHIFT_MINUTES

    Returns
    -------
    X_df     : pd.DataFrame — feature columns (pre-transform, for pipeline.fit)
    y        : pd.Series   — integer labels (0,1,2) aligned with X_df
    pipeline : fitted sklearn Pipeline
    """
    global FEATURE_COLS

    # Sort chronologically so rolling features are correct
    if "timestamp" in df.columns:
        df = df.sort_values("timestamp").reset_index(drop=True)

    # Map labels (before temporal shift so shift is applied to integers)
    y = df["risk_level"].map(LABEL_MAP).astype(int)

    # Temporal shift: y at row i → risk at t+10
    if temporal_shift:
        df, y = apply_temporal_shift(df, y, shift=TEMPORAL_SHIFT_MINUTES)
        print(
            f"[preprocessor] Temporal shift applied (+{TEMPORAL_SHIFT_MINUTES} min). "
            f"Rows after drop: {len(df):,}"
        )

    # Feature engineering
    fe_df = engineer_features(df)

    numeric_features     = _get_feature_names(fe_df)
    categorical_features = [c for c in _RAW_CATEGORICAL if c in fe_df.columns]
    FEATURE_COLS         = categorical_features + numeric_features

    # ColumnTransformer: encode categoricals, scale numerics
    ct = ColumnTransformer(
        transformers=[
            (
                "cat",
                OrdinalEncoder(
                    handle_unknown="use_encoded_value",
                    unknown_value=-1,
                ),
                categorical_features,
            ),
            (
                "num",
                StandardScaler(),
                numeric_features,
            ),
        ],
        remainder="drop",
    )

    pipeline = Pipeline(steps=[("preprocessor", ct)])
    pipeline.fit(fe_df[FEATURE_COLS])

    # Attach metadata to pipeline for inference
    pipeline.feature_cols        = FEATURE_COLS
    pipeline.numeric_features    = numeric_features
    pipeline.categorical_features = categorical_features

    return fe_df[FEATURE_COLS], y, pipeline


def apply_pipeline(pipeline: Pipeline, raw_df: pd.DataFrame) -> np.ndarray:
    """
    Apply a fitted pipeline to a new DataFrame (inference path).
    Runs engineer_features automatically; missing columns filled with 0.
    """
    fe_df = engineer_features(raw_df)
    feature_cols = getattr(pipeline, "feature_cols", [])
    for col in feature_cols:
        if col not in fe_df.columns:
            fe_df[col] = 0.0
    return pipeline.transform(fe_df[feature_cols])


# ── Persistence helpers ───────────────────────────────────────────────────────

def save_pipeline(pipeline: Pipeline, path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    joblib.dump(pipeline, path)
    print(f"[preprocessor] Pipeline saved → {path}")


def load_pipeline(path: str) -> Pipeline:
    pipeline = joblib.load(path)
    global FEATURE_COLS
    FEATURE_COLS = getattr(pipeline, "feature_cols", FEATURE_COLS)
    return pipeline


# ── Single-row / sequence inference helpers ───────────────────────────────────

def dict_to_dataframe(data_dict: dict) -> pd.DataFrame:
    """
    Convert a single JSON/dict payload into a one-row DataFrame.
    Missing optional fields are filled with safe defaults.
    """
    defaults = {
        "location":                    "Ambaji",
        "corridor_width_m":            5,
        "entry_flow_rate_pax_per_min": 100.0,
        "exit_flow_rate_pax_per_min":  100.0,
        "transport_arrival_burst":     0,
        "vehicle_count":               5,
        "queue_density_pax_per_m2":    2.0,
        "weather":                     "Clear",
        "festival_peak":               0,
        "pressure_index":              30.0,
        "predicted_crush_window_min":  15,
    }
    row = {**defaults, **data_dict}
    # Keep only recognised feature columns
    allowed = set(_RAW_NUMERIC + _RAW_CATEGORICAL)
    row = {k: v for k, v in row.items() if k in allowed}
    return pd.DataFrame([row])


def sequence_to_dataframe(records: list[dict]) -> pd.DataFrame:
    """
    Convert a list of dicts (replay/historical sequence) into a DataFrame.
    Rolling features will be computed across the full sequence.
    """
    defaults = {
        "location":                    "Ambaji",
        "corridor_width_m":            5,
        "entry_flow_rate_pax_per_min": 100.0,
        "exit_flow_rate_pax_per_min":  100.0,
        "transport_arrival_burst":     0,
        "vehicle_count":               5,
        "queue_density_pax_per_m2":    2.0,
        "weather":                     "Clear",
        "festival_peak":               0,
        "pressure_index":              30.0,
        "predicted_crush_window_min":  15,
    }
    rows = [{**defaults, **r} for r in records]
    df   = pd.DataFrame(rows)
    allowed = set(_RAW_NUMERIC + _RAW_CATEGORICAL)
    df = df[[c for c in df.columns if c in allowed]]
    return df
