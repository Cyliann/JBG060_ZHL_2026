"""Fit the selected binary GBDT and save its road/date probabilities.

Class 0 is passable. Class 1 combines passable with difficulties and
impassable. All predictors are available before the issue map date; the
target is the first map 10–14 days later.
"""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

from fit_status_logistic import FEATURES, prepare_data


ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "regression_input/regression_input.csv"
ROADS = ROOT / "road_data/roads_all(2).csv"
FEATURE_OUTPUT = ROOT / "regression_input/gbdt_model_features.csv"
OUTPUT = ROOT / "regression/gbdt_results"
PARAMETERS = {
    "max_leaf_nodes": 7,
    "max_iter": 150,
    "learning_rate": 0.05,
    "min_samples_leaf": 50,
    "l2_regularization": 1.0,
    "early_stopping": False,
    "random_state": 42,
}


def main() -> None:
    data = prepare_data(INPUT, ROADS)
    data["current_binary"] = data["current_status"].ne(0).astype(int)
    data["target_binary"] = data["target_status"].ne(0).astype(int)
    train = data.loc[data["evaluation_split"].eq("development_2024")]
    test = (data.loc[data["evaluation_split"].eq("test_2025")]
            .sort_values(["issue_date", "road_id"]).reset_index(drop=True))
    if train.empty or test.empty or train["target_date"].max() >= test["issue_date"].min():
        raise ValueError("Missing split or overlapping training outcomes and test dates")

    model = HistGradientBoostingClassifier(**PARAMETERS)
    model.fit(train[FEATURES], train["target_binary"])
    if model.classes_.tolist() != [0, 1]:
        raise ValueError("Expected model classes [0, 1]")
    probability = model.predict_proba(test[FEATURES])[:, 1]
    if not np.isfinite(probability).all():
        raise ValueError("Model produced a non-finite probability")
    actual = test["target_binary"].to_numpy()
    predicted = (probability >= 0.5).astype(int)
    tn, fp, fn, tp = confusion_matrix(actual, predicted, labels=[0, 1]).ravel()

    feature_columns = ["road_id", "issue_date", "target_date", "evaluation_split",
                       "current_status", "target_status", *FEATURES]
    data[feature_columns].to_csv(FEATURE_OUTPUT, index=False)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    result_columns = ["road_id", "issue_date", "target_date", "current_status",
                      "target_status", "current_binary", "target_binary"]
    results = test[result_columns].copy()
    results["p_impassable_gbdt"] = probability
    results.to_csv(OUTPUT / "gbdt_probabilities_2025.csv", index=False)
    latest = results.loc[results["issue_date"].eq(results["issue_date"].max())]
    latest.to_csv(OUTPUT / "latest_historical_snapshot.csv", index=False)
    joblib.dump(model, OUTPUT / "gbdt_model.joblib")

    new_restricted = (test["current_binary"].eq(0) & test["target_binary"].eq(1)).to_numpy()
    reopening = (test["current_binary"].eq(1) & test["target_binary"].eq(0)).to_numpy()
    metrics = {
        "test_rows": len(test),
        "decision_threshold": 0.5,
        "accuracy": float(accuracy_score(actual, predicted)),
        "restricted_precision": float(precision_score(actual, predicted)),
        "restricted_recall": float(recall_score(actual, predicted)),
        "restricted_f1": float(f1_score(actual, predicted)),
        "macro_f1": float(f1_score(actual, predicted, average="macro")),
        "tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp),
        "roc_auc": float(roc_auc_score(actual, probability)),
        "average_precision": float(average_precision_score(actual, probability)),
        "brier": float(brier_score_loss(actual, probability)),
        "new_restricted_rows": int(new_restricted.sum()),
        "new_restricted_caught": int((new_restricted & (predicted == 1)).sum()),
        "reopening_rows": int(reopening.sum()),
        "reopenings_caught": int((reopening & (predicted == 0)).sum()),
    }
    (OUTPUT / "test_metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    manifest = {
        "model": "HistGradientBoostingClassifier",
        "class_0": "passable",
        "class_1": "passable with difficulties or impassable",
        "target": "first access map 10-14 days after issue_date",
        "features_in_order": FEATURES,
        "parameters": PARAMETERS,
        "train_rows_2024": len(train),
        "test_rows_2025": len(test),
        "input_sha256": sha256(INPUT.read_bytes()).hexdigest(),
        "road_status_sha256": sha256(ROADS.read_bytes()).hexdigest(),
        "model_sha256": sha256((OUTPUT / "gbdt_model.joblib").read_bytes()).hexdigest(),
    }
    (OUTPUT / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Saved {len(train)} training rows and {len(test)} test probabilities to {OUTPUT}")
    print(f"Accuracy {metrics['accuracy']:.4f}; restricted F1 {metrics['restricted_f1']:.4f}")


if __name__ == "__main__":
    main()
