"""
train.py
========
Offline training pipeline for the crowd crush risk classifier.

Usage (from backend/ directory):
    python -m ml.train
    python -m ml.train --data /path/to/TS-PS11.csv --output ml/models

Steps
-----
1. Load & validate dataset
2. Feature engineering
3. Encode labels (Low→0 SAFE, Moderate→1 SURGE, High/Critical→2 HIGH_RISK)
4. Build & fit preprocessing pipeline
5. Train-Test split (80/20, stratified)
6. 5-fold StratifiedKFold cross-validation with XGBoost
7. Final model training with early stopping
8. Evaluation: accuracy, F1, confusion matrix, train-vs-test gap check
9. Save crowd_model.pkl + preprocessing_pipeline.pkl
"""

from __future__ import annotations

import argparse
import os
import sys
import warnings

warnings.filterwarnings("ignore", category=UserWarning)

import joblib
import numpy as np
import pandas as pd

from sklearn.model_selection import train_test_split, StratifiedKFold
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
)
from sklearn.utils.class_weight import compute_sample_weight
from xgboost import XGBClassifier

# ── Local imports ─────────────────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))  # backend/
from ml.preprocessor import (
    build_preprocessing_pipeline,
    apply_pipeline,
    save_pipeline,
    LABEL_MAP,
    LABEL_NAMES,
)

# ── Default paths ─────────────────────────────────────────────────────────────
_BACKEND_DIR  = os.path.dirname(os.path.dirname(__file__))
_DEFAULT_DATA = os.path.join(_BACKEND_DIR, "TS-PS11.csv")
_DEFAULT_OUT  = os.path.join(os.path.dirname(__file__), "models")


# ── Data loading ──────────────────────────────────────────────────────────────

def load_data(path: str) -> pd.DataFrame:
    """Load dataset from Excel (.xlsx / .csv with xlsx magic bytes)."""
    print(f"[train] Loading data from: {path}")
    try:
        df = pd.read_excel(path, engine="openpyxl")
    except Exception:
        df = pd.read_csv(path)
    print(f"[train] Loaded {len(df):,} rows × {df.shape[1]} columns")
    return df


def validate_data(df: pd.DataFrame) -> None:
    """Basic schema assertions."""
    required = [
        "entry_flow_rate_pax_per_min", "exit_flow_rate_pax_per_min",
        "corridor_width_m", "queue_density_pax_per_m2",
        "pressure_index", "risk_level",
    ]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"[train] Missing required columns: {missing}")
    unknown_labels = set(df["risk_level"].unique()) - set(LABEL_MAP.keys())
    if unknown_labels:
        raise ValueError(f"[train] Unknown risk_level values: {unknown_labels}")


# ── Model configuration ───────────────────────────────────────────────────────

def get_xgb_params() -> dict:
    """
    XGBoost hyperparameters tuned for:
      - 3-class classification
      - Imbalanced dataset
      - Overfitting prevention (L1, L2, subsampling, early stopping)
    """
    return {
        "objective":       "multi:softprob",
        "num_class":       3,
        "eval_metric":     "mlogloss",
        "n_estimators":    500,            # upper bound; early stopping cuts this
        "learning_rate":   0.05,
        "max_depth":       6,
        "subsample":       0.8,
        "colsample_bytree": 0.8,
        "reg_alpha":       0.1,            # L1
        "reg_lambda":      1.0,            # L2
        "min_child_weight": 5,
        "random_state":    42,
        "n_jobs":          -1,
        "verbosity":       0,
    }


# ── Printing utilities ────────────────────────────────────────────────────────

def _print_section(title: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def _print_metrics(prefix: str, y_true, y_pred) -> float:
    acc = accuracy_score(y_true, y_pred)
    f1  = f1_score(y_true, y_pred, average="weighted")
    print(f"  {prefix} — Accuracy: {acc:.4f}  |  F1 (weighted): {f1:.4f}")
    return acc


# ── Training pipeline ─────────────────────────────────────────────────────────

def run_training(data_path: str, output_dir: str) -> None:
    os.makedirs(output_dir, exist_ok=True)

    # 1. Load & validate
    _print_section("1. Data Loading & Validation")
    df = load_data(data_path)
    validate_data(df)
    print(f"[train] Class distribution:\n{df['risk_level'].value_counts().to_string()}")

    # 2. Preprocessing pipeline & feature engineering
    _print_section("2. Feature Engineering & Preprocessing Pipeline")
    X_df, y, pipeline = build_preprocessing_pipeline(df)
    X = pipeline.transform(X_df)
    print(f"[train] Feature matrix shape: {X.shape}")
    print(f"[train] Features used: {pipeline.feature_cols}")
    print(f"[train] Label distribution: {dict(zip(*np.unique(y, return_counts=True)))}")

    # 3. Train-test split
    _print_section("3. Train-Test Split (80/20, stratified)")
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    # Convert to numpy to avoid pandas index misalignment in CV loop
    y_train = np.array(y_train)
    y_test  = np.array(y_test)
    print(f"[train] Train: {X_train.shape[0]:,} | Test: {X_test.shape[0]:,}")

    # 4. Class-weight sample weighting
    sample_weights = compute_sample_weight(class_weight="balanced", y=y_train)
    print("[train] Sample weights computed (balanced) for class imbalance.")

    # 5. Cross-validation — manual loop so we can pass per-fold sample_weight
    _print_section("4. Cross-Validation (5-fold StratifiedKFold)")
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    cv_scores: list[float] = []
    for fold, (tr_idx, val_idx) in enumerate(skf.split(X_train, y_train), 1):
        Xf_tr, Xf_val = X_train[tr_idx], X_train[val_idx]
        yf_tr, yf_val = y_train[tr_idx], y_train[val_idx]
        sw_fold = compute_sample_weight("balanced", yf_tr)
        fold_model = XGBClassifier(**get_xgb_params())
        fold_model.fit(Xf_tr, yf_tr, sample_weight=sw_fold, verbose=False)
        yf_pred = fold_model.predict(Xf_val)
        fold_f1 = f1_score(yf_val, yf_pred, average="weighted")
        cv_scores.append(fold_f1)
        print(f"    Fold {fold}: F1 = {fold_f1:.4f}")

    cv_arr = np.array(cv_scores)
    print(f"[train] CV F1 (weighted) per fold: {np.round(cv_arr, 4)}")
    print(f"[train] CV Mean: {cv_arr.mean():.4f} \u00b1 {cv_arr.std():.4f}")

    # 6. Final model training with early stopping
    _print_section("5. Final Model Training (XGBoost + Early Stopping)")
    model = XGBClassifier(**get_xgb_params(), early_stopping_rounds=20)
    model.fit(
        X_train, y_train,
        sample_weight=sample_weights,
        eval_set=[(X_test, y_test)],
        verbose=False,
    )
    actual_trees = model.best_iteration + 1 if hasattr(model, "best_iteration") else model.n_estimators
    print(f"[train] Best iteration: {actual_trees} trees (early stopped)")

    # 7. Evaluation
    _print_section("6. Evaluation")
    y_train_pred = model.predict(X_train)
    y_test_pred  = model.predict(X_test)

    train_acc = _print_metrics("TRAIN", y_train, y_train_pred)
    test_acc  = _print_metrics("TEST ", y_test,  y_test_pred)
    gap = train_acc - test_acc
    overfitting_flag = "⚠️  WARNING: possible overfit!" if gap > 0.05 else "✅ OK"
    print(f"\n[train] Train-Test accuracy gap: {gap:.4f}  {overfitting_flag}")

    print("\n[train] Classification Report (Test set):")
    target_names = [LABEL_NAMES[i] for i in sorted(LABEL_NAMES)]
    print(
        classification_report(
            y_test, y_test_pred,
            target_names=target_names,
            digits=4,
        )
    )

    print("[train] Confusion Matrix (Test set):")
    cm = confusion_matrix(y_test, y_test_pred)
    header = f"{'':>10}" + "".join(f"{n:>12}" for n in target_names)
    print(header)
    for i, row in enumerate(cm):
        print(f"{target_names[i]:>10}" + "".join(f"{v:>12}" for v in row))

    # 8. Feature importance
    _print_section("7. Feature Importances (top 10)")
    importances = model.feature_importances_
    feat_names  = pipeline.feature_cols
    top = sorted(zip(feat_names, importances), key=lambda x: -x[1])[:10]
    for name, imp in top:
        bar = "█" * int(imp * 100)
        print(f"  {name:<40} {imp:.4f}  {bar}")

    # 9. Save artifacts
    _print_section("8. Saving Artifacts")
    model_path    = os.path.join(output_dir, "crowd_model.pkl")
    pipeline_path = os.path.join(output_dir, "preprocessing_pipeline.pkl")

    joblib.dump(model, model_path)
    print(f"[train] Model saved    → {model_path}")

    save_pipeline(pipeline, pipeline_path)

    print("\n[train] ✅ Training complete!\n")


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Train crowd crush risk classifier"
    )
    parser.add_argument(
        "--data",
        default=_DEFAULT_DATA,
        help=f"Path to dataset (default: {_DEFAULT_DATA})",
    )
    parser.add_argument(
        "--output",
        default=_DEFAULT_OUT,
        help=f"Directory to save model artifacts (default: {_DEFAULT_OUT})",
    )
    args = parser.parse_args()
    run_training(args.data, args.output)


if __name__ == "__main__":
    main()
