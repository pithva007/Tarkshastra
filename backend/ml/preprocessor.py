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
load_and_clean(csv_path)          ->  pd.DataFrame
normalize(df, scaler)             ->  np.ndarray
LABEL_MAP                         ->  {str: int}
LABEL_NAMES                       ->  {int: str}
TEMPORAL_SHIFT_MINUTES            ->  int  (10)
SIMPLE_FEATURES                   ->  list[str]
SIMPLE_LABEL_MAP                  ->  {str: int}
SIMPLE_LABEL_NAMES                ->  {int: str}
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

# Simple model labels (matching simulator surge_type)
SIMPLE_LABEL_MAP: dict[str, int] = {
    "Low":      0,  # SAFE
    "Moderate": 1,  # SELF_RESOLVING
    "High":     2,  # GENUINE_CRUSH
    "Critical": 2,  # GENUINE_CRUSH
}

SIMPLE_LABEL_NAMES: dict[int, str] = {
    0: "SAFE",
    1: "SELF_RESOLVING",
    2: "GENUINE_CRUSH",
}

# Features for the simple RandomForest model
SIMPLE_FEATURES: list[str] = [
    "flow_rate",
    "transport_burst",
    "chokepoint_density",
    "cpi_rolling_mean_5",
    "cpi_slope",
    "hour_of_day",
    "day_type",
]

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


# ── Data loading helpers ──────────────────────────────────────────────────────

def load_and_clean(csv_path: str) -> pd.DataFrame:
    """
    Load raw CSV/Excel dataset, clean nulls and fix dtypes.
    Returns a cleaned DataFrame ready for feature engineering.
    """
    try:
        df = pd.read_excel(csv_path, engine="openpyxl")
    except Exception:
        df = pd.read_csv(csv_path)

    # Drop fully-empty rows
    df = df.dropna(how="all").reset_index(drop=True)

    # Fill numeric NaNs with column medians
    for col in _RAW_NUMERIC:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
            df[col] = df[col].fillna(df[col].median())

    # Fill categorical NaNs
    for col in _RAW_CATEGORICAL:
        if col in df.columns:
            df[col] = df[col].fillna("Unknown")

    # Ensure risk_level column is clean
    if "risk_level" in df.columns:
        df["risk_level"] = df["risk_level"].str.strip()

    return df


def normalize(df: pd.DataFrame, scaler: StandardScaler) -> np.ndarray:
    """
    Apply a fitted StandardScaler to a DataFrame and return scaled array.
    Columns must match scaler's expected feature set.
    """
    return scaler.transform(df)


# ── Feature engineering ───────────────────────────────────────────────────────

def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Apply all feature engineering to a DataFrame.

    New features vs v1:
      flow_acceleration       — row-wise diff of entry_flow
      transport_burst_indicator — binary flag: transport_arrival_burst > 0
      pressure_trend_slope    — slope of pressure_index over last 5 rows
      rolling_flow_3/5/10     — rolling mean of entry_flow
      rolling_density_3       — rolling mean of density
      rolling_pressure_3      — rolling mean of pressure_index
      density                 — entry_flow / corridor_width
      congestion_ratio        — entry_flow / (exit_flow + 1)
    """
    df = df.copy()

    df["density"] = (
        df["entry_flow_rate_pax_per_min"]
        / df["corridor_width_m"].replace(0, 1)
    )
    df["congestion_ratio"] = (
        df["entry_flow_rate_pax_per_min"]
        / (df["exit_flow_rate_pax_per_min"] + 1.0)
    )

    df["flow_acceleration"] = df["entry_flow_rate_pax_per_min"].diff().fillna(0.0)

    df["transport_burst_indicator"] = (
        df["transport_arrival_burst"] > 0
    ).astype(int)

    def _rolling_slope(series: pd.Series, window: int = 5) -> pd.Series:
        roll_last  = series.rolling(window=window, min_periods=2).apply(lambda x: x[-1])
        roll_first = series.rolling(window=window, min_periods=2).apply(lambda x: x[0])
        return ((roll_last - roll_first) / window).fillna(0.0)

    df["pressure_trend_slope"] = _rolling_slope(df["pressure_index"], window=5)

    for w in (3, 5, 10):
        df[f"rolling_flow_{w}"] = (
            df["entry_flow_rate_pax_per_min"]
            .rolling(window=w, min_periods=1)
            .mean()
        )

    df["rolling_density_3"]  = df["density"].rolling(window=3, min_periods=1).mean()
    df["rolling_pressure_3"] = df["pressure_index"].rolling(window=3, min_periods=1).mean()

    return df


def engineer_simple_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Build the simple feature set for the RandomForest model.
    Maps raw CSV columns to SIMPLE_FEATURES.
    """
    df = df.copy()

    # flow_rate
    if "entry_flow_rate_pax_per_min" in df.columns:
        df["flow_rate"] = df["entry_flow_rate_pax_per_min"]
    elif "flow_rate" not in df.columns:
        df["flow_rate"] = 100.0

    # transport_burst
    if "transport_arrival_burst" in df.columns:
        df["transport_burst"] = df["transport_arrival_burst"]
    elif "transport_burst" not in df.columns:
        df["transport_burst"] = 0.2

    # chokepoint_density (normalized 0-1)
    if "queue_density_pax_per_m2" in df.columns:
        df["chokepoint_density"] = (df["queue_density_pax_per_m2"] / 8.0).clip(0.0, 1.0)
    elif "chokepoint_density" not in df.columns:
        df["chokepoint_density"] = 0.3

    # cpi proxy column
    cpi_col = "pressure_index" if "pressure_index" in df.columns else "cpi"
    if cpi_col not in df.columns:
        df[cpi_col] = 30.0

    # cpi_rolling_mean_5
    df["cpi_rolling_mean_5"] = (
        df[cpi_col].rolling(window=5, min_periods=1).mean() / 100.0
    ).clip(0.0, 1.0)

    # cpi_slope
    def _slope(series, window=5):
        rl = series.rolling(window=window, min_periods=2).apply(lambda x: x[-1])
        rf = series.rolling(window=window, min_periods=2).apply(lambda x: x[0])
        return ((rl - rf) / (window * 100.0)).fillna(0.0)

    df["cpi_slope"] = _slope(df[cpi_col], window=5)

    # hour_of_day
    if "timestamp" in df.columns:
        try:
            df["hour_of_day"] = pd.to_datetime(df["timestamp"]).dt.hour
        except Exception:
            df["hour_of_day"] = 10
    elif "hour_of_day" not in df.columns:
        df["hour_of_day"] = 10

    # day_type (festival_peak → 0/1)
    if "festival_peak" in df.columns:
        df["day_type"] = df["festival_peak"].astype(int)
    elif "day_type" not in df.columns:
        df["day_type"] = 0

    return df[SIMPLE_FEATURES]


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
    """
    y_shifted = y.copy().astype(float)

    if "location" in df.columns:
        for loc in df["location"].unique():
            mask = df["location"] == loc
            y_shifted.loc[mask] = y.loc[mask].shift(-shift).values
    else:
        y_shifted = y.shift(-shift)

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
    Full offline preprocessing for XGBoost training.
    Returns X_df, y, fitted sklearn Pipeline.
    """
    global FEATURE_COLS

    if "timestamp" in df.columns:
        df = df.sort_values("timestamp").reset_index(drop=True)

    y = df["risk_level"].map(LABEL_MAP).astype(int)

    if temporal_shift:
        df, y = apply_temporal_shift(df, y, shift=TEMPORAL_SHIFT_MINUTES)
        print(
            f"[preprocessor] Temporal shift applied (+{TEMPORAL_SHIFT_MINUTES} min). "
            f"Rows after drop: {len(df):,}"
        )

    fe_df = engineer_features(df)

    numeric_features     = _get_feature_names(fe_df)
    categorical_features = [c for c in _RAW_CATEGORICAL if c in fe_df.columns]
    FEATURE_COLS         = categorical_features + numeric_features

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

    pipeline.feature_cols         = FEATURE_COLS
    pipeline.numeric_features     = numeric_features
    pipeline.categorical_features = categorical_features

    return fe_df[FEATURE_COLS], y, pipeline


def apply_pipeline(pipeline: Pipeline, raw_df: pd.DataFrame) -> np.ndarray:
    """Apply a fitted pipeline to a new DataFrame (inference path)."""
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
    """Convert a single JSON/dict payload into a one-row DataFrame."""
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
    allowed = set(_RAW_NUMERIC + _RAW_CATEGORICAL)
    row = {k: v for k, v in row.items() if k in allowed}
    return pd.DataFrame([row])


def sequence_to_dataframe(records: list[dict]) -> pd.DataFrame:
    """Convert a list of dicts (replay/historical) into a DataFrame."""
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
