"""Fit multinomial logistic regression for road status 10–14 days later."""

from __future__ import annotations

import argparse
import json
from hashlib import sha256
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score, log_loss
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


FEATURES = [
    "current_partial",
    "current_impassable",
    "season_sin",
    "season_cos",
    "log_status_age_days",
    "recent_status_change",
    "has_previous_map",
    "ever_observed_change",
    "previous_map_gap_days",
    "log_rain_7d",
    "rain_trend_log",
    "flood_detected_days_7d",
    "flood_trend_days",
    "log_flood_intensity_7d",
    "current_partial_x_log_rain_7d",
    "current_partial_x_flood_detected_days_7d",
    "current_impassable_x_log_rain_7d",
    "current_impassable_x_flood_detected_days_7d",
]

VALIDATION_BLOCKS = [
    ("2024-05-31", "2024-06-21"),
    ("2024-07-04", "2024-07-25"),
    ("2024-08-01", "2024-12-12"),
]


def road_history(path: Path) -> pd.DataFrame:
    roads = pd.read_csv(path, encoding="utf-8-sig", parse_dates=["date"])
    required = {"road_id", "date", "condition_code"}
    if required - set(roads.columns):
        raise ValueError(f"Road table missing: {sorted(required - set(roads.columns))}")
    if roads.duplicated(["road_id", "date"]).any():
        raise ValueError("Duplicate road/date in road-status source")

    roads = roads.sort_values(["road_id", "date"]).reset_index(drop=True)
    by_road = roads.groupby("road_id", sort=False)
    previous_status = by_road["condition_code"].shift()
    previous_date = by_road["date"].shift()
    roads["has_previous_map"] = previous_status.notna().astype(int)
    roads["recent_status_change"] = (
        previous_status.notna() & roads["condition_code"].ne(previous_status)
    ).astype(int)
    roads["previous_map_gap_days"] = (roads["date"] - previous_date).dt.days.fillna(0)
    roads["last_change_date"] = roads["date"].where(roads["recent_status_change"].eq(1))
    roads["last_change_date"] = roads.groupby("road_id")["last_change_date"].ffill()
    roads["ever_observed_change"] = roads["last_change_date"].notna().astype(int)
    first_date = roads.groupby("road_id")["date"].transform("min")
    anchor_date = roads["last_change_date"].fillna(first_date)
    roads["log_status_age_days"] = np.log1p((roads["date"] - anchor_date).dt.days)
    return roads[
        [
            "road_id", "date", "condition_code", "log_status_age_days",
            "recent_status_change", "has_previous_map", "ever_observed_change",
            "previous_map_gap_days",
        ]
    ].rename(columns={"date": "issue_date", "condition_code": "history_current_status"})


def prepare_data(input_path: Path, roads_path: Path) -> pd.DataFrame:
    data = pd.read_csv(
        input_path, parse_dates=["issue_date", "target_date", "feature_cutoff_date"]
    )
    required = {
        "road_id", "issue_date", "target_date", "feature_cutoff_date",
        "current_status", "target_status", "evaluation_split", "issue_month",
        "current_partial", "current_impassable", "rain_mm_7d", "rain_mm_14d",
        "flood_detected_days_7d", "flood_detected_days_14d",
        "flood_pixel_days_per_km_7d",
    }
    if required - set(data.columns):
        raise ValueError(f"Model table missing: {sorted(required - set(data.columns))}")
    if data.duplicated(["road_id", "issue_date"]).any():
        raise ValueError("Duplicate modeling road/date")
    if not data["feature_cutoff_date"].eq(data["issue_date"] - pd.Timedelta(days=1)).all():
        raise ValueError("Feature cutoff must be the day before the issue map")
    if not (data["target_date"] - data["issue_date"]).dt.days.between(10, 14).all():
        raise ValueError("Target map must be 10–14 days after the issue map")

    data = data.merge(road_history(roads_path), on=["road_id", "issue_date"],
                      how="left", validate="one_to_one")
    if data["history_current_status"].isna().any():
        raise ValueError("A modeling row has no matching road-status map")
    if not data["history_current_status"].eq(data["current_status"]).all():
        raise ValueError("Current status differs from the road-status source")
    data["current_status"] = data["current_status"].astype(int)
    data["target_status"] = data["target_status"].astype(int)
    if not data["current_status"].isin([0, 1, 2]).all() or not data["target_status"].isin([0, 1, 2]).all():
        raise ValueError("Status must be 0, 1, or 2")
    if not data["current_partial"].eq(data["current_status"].eq(1)).all():
        raise ValueError("current_partial does not match current_status")
    if not data["current_impassable"].eq(data["current_status"].eq(2)).all():
        raise ValueError("current_impassable does not match current_status")

    angle = 2 * np.pi * (data["issue_month"] - 1) / 12
    data["season_sin"] = np.sin(angle)
    data["season_cos"] = np.cos(angle)
    recent_rain = data["rain_mm_7d"]
    previous_rain = data["rain_mm_14d"] - recent_rain
    recent_flood = data["flood_detected_days_7d"]
    previous_flood = data["flood_detected_days_14d"] - recent_flood
    if (previous_rain < -1e-6).any() or (previous_flood < -1e-6).any():
        raise ValueError("A 14-day total is smaller than its last 7 days")
    data["log_rain_7d"] = np.log1p(recent_rain)
    data["rain_trend_log"] = np.log1p(recent_rain) - np.log1p(previous_rain.clip(lower=0))
    data["flood_trend_days"] = recent_flood - previous_flood.clip(lower=0)
    data["log_flood_intensity_7d"] = np.log1p(data["flood_pixel_days_per_km_7d"])
    for status in ("current_partial", "current_impassable"):
        for weather in ("log_rain_7d", "flood_detected_days_7d"):
            data[f"{status}_x_{weather}"] = data[status] * data[weather]
    if data[FEATURES].isna().any().any() or not np.isfinite(data[FEATURES].to_numpy()).all():
        raise ValueError("Missing or non-finite regression feature")
    data["actual_change"] = data["current_status"].ne(data["target_status"]).astype(int)
    return data


def fit(train: pd.DataFrame):
    if sorted(train["target_status"].unique().tolist()) != [0, 1, 2]:
        raise ValueError("Training period must include all three target statuses")
    model = make_pipeline(StandardScaler(), LogisticRegression(C=0.3, max_iter=2000))
    model.fit(train[FEATURES], train["target_status"])
    return model


def predict_probabilities(model, data: pd.DataFrame) -> np.ndarray:
    classes = model.named_steps["logisticregression"].classes_.tolist()
    if classes != [0, 1, 2]:
        raise ValueError(f"Unexpected class order: {classes}")
    probability = model.predict_proba(data[FEATURES])
    if probability.shape != (len(data), 3) or not np.allclose(probability.sum(axis=1), 1):
        raise ValueError("Three class probabilities must sum to one")
    return probability


def evaluate(data: pd.DataFrame, probability: np.ndarray) -> dict:
    actual = data["target_status"].to_numpy()
    current = data["current_status"].to_numpy()
    predicted = probability.argmax(axis=1)
    changed = actual != current
    confusion = pd.crosstab(
        pd.Series(actual, name="actual"), pd.Series(predicted, name="predicted")
    ).reindex(index=[0, 1, 2], columns=[0, 1, 2], fill_value=0)
    return {
        "rows": len(data),
        "issue_dates": int(data["issue_date"].nunique()),
        "actual_class_0": int((actual == 0).sum()),
        "actual_class_1": int((actual == 1).sum()),
        "actual_class_2": int((actual == 2).sum()),
        "actual_changes": int(changed.sum()),
        "accuracy": float(accuracy_score(actual, predicted)),
        "macro_f1": float(f1_score(actual, predicted, labels=[0, 1, 2], average="macro")),
        "multiclass_log_loss": float(log_loss(actual, probability, labels=[0, 1, 2])),
        "multiclass_brier": float(np.mean(np.sum((probability - np.eye(3)[actual]) ** 2, axis=1))),
        "predicted_changes_by_argmax": int((predicted != current).sum()),
        "correct_changed_status": int((predicted[changed] == actual[changed]).sum()),
        "mean_highest_probability": float(probability.max(axis=1).mean()),
        "confusion_matrix": confusion.to_numpy().tolist(),
    }


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input", type=Path,
        default=project_root / "regression_input/regression_input.csv",
    )
    parser.add_argument(
        "--roads-csv", type=Path,
        default=project_root / "road_data/roads_all(2).csv",
    )
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).resolve().parent / "results")
    args = parser.parse_args()

    data = prepare_data(args.input, args.roads_csv)
    development = data.loc[data["evaluation_split"].eq("development_2024")].copy()
    test = data.loc[data["evaluation_split"].eq("test_2025")].copy()
    if development.empty or test.empty:
        raise ValueError("Both 2024 development and 2025 test periods are required")
    if development["target_date"].max() >= test["issue_date"].min():
        raise ValueError("2024 training outcomes overlap the 2025 test period")

    cv_rows = []
    for fold, (first, last) in enumerate(VALIDATION_BLOCKS, start=1):
        first, last = pd.Timestamp(first), pd.Timestamp(last)
        train = development.loc[development["target_date"] < first]
        validation = development.loc[development["issue_date"].between(first, last)]
        if train.empty or validation.empty:
            raise ValueError(f"Empty train or validation data in fold {fold}")
        model = fit(train)
        probability = predict_probabilities(model, validation)
        cv_rows.append({
            "fold": fold,
            "train_rows": len(train),
            "train_changes": int(train["actual_change"].sum()),
            "last_train_target_date": str(train["target_date"].max().date()),
            "validation_first_issue_date": str(first.date()),
            "validation_last_issue_date": str(last.date()),
            **{key: value for key, value in evaluate(validation, probability).items()
               if key != "confusion_matrix"},
        })

    model = fit(development)
    probability = predict_probabilities(model, test)
    test_metrics = evaluate(test, probability)
    test_metrics.update({
        "training_rows": len(development),
        "training_changes": int(development["actual_change"].sum()),
        "input_csv_sha256": sha256(args.input.read_bytes()).hexdigest(),
        "road_status_csv_sha256": sha256(args.roads_csv.read_bytes()).hexdigest(),
    })
    predictions = test[
        ["road_id", "issue_date", "target_date", "current_status", "target_status", "actual_change"]
    ].copy()
    for status, label in enumerate(("passable", "passable_with_difficulties", "impassable")):
        predictions[f"p_{label}"] = probability[:, status]
    predictions["predicted_status"] = probability.argmax(axis=1)
    predictions["confidence"] = probability.max(axis=1)
    predictions = predictions.sort_values(["issue_date", "road_id"])
    coefficients = model.named_steps["logisticregression"].coef_
    coefficient_table = pd.DataFrame(
        [
            {"target_class": status, "feature": feature,
             "coefficient_per_scaled_unit": coefficients[status, index]}
            for status in (0, 1, 2)
            for index, feature in enumerate(FEATURES)
        ]
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(cv_rows).to_csv(args.output_dir / "cv_metrics.csv", index=False)
    predictions.to_csv(args.output_dir / "test_predictions.csv", index=False)
    coefficient_table.to_csv(args.output_dir / "coefficients.csv", index=False)
    with (args.output_dir / "test_metrics.json").open("w", encoding="utf-8") as file:
        json.dump(test_metrics, file, indent=2)
    joblib.dump(model, args.output_dir / "status_logistic_model.joblib")
    print(f"2024 training: {len(development)} rows, {int(development['actual_change'].sum())} changes")
    print(f"2025 test: {test_metrics['rows']} rows, {test_metrics['actual_changes']} changes")
    print(f"2025 accuracy: {test_metrics['accuracy']:.4f}; "
          f"correct changed statuses: {test_metrics['correct_changed_status']} "
          f"of {test_metrics['actual_changes']}")
    print(f"Results: {args.output_dir}")


if __name__ == "__main__":
    main()
