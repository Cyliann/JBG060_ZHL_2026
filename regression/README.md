# Road passability: three-class logistic regression

This folder contains a **direct multinomial logistic regression**. For each
road on an access-map date, it predicts the road's passability on the first
available map 10–14 days later. Its output is a probability (model
confidence) for **each** of the three labels:

```text
p_passable
p_passable_with_difficulties
p_impassable
```

The three probabilities sum to one. The model fits the three classes
directly; it does not first estimate a change probability or distribute one
using historical transition ratios.

The code is `fit_status_logistic.py`; the fitted model, predictions, and
evaluation are in `results/`. Its input tables are in this repository.

## 1. What one training example means

One row is a **road × current map date** pair. `road_id` identifies the route,
and `issue_date` is the nominal current map date. `current_status` has the
following encoding:

| Value | Current or future road condition |
| ---: | --- |
| 0 | Passable |
| 1 | Passable with difficulties |
| 2 | Impassable |

For each issue map, upstream preprocessing selects the **first available map
10–14 days later**. That map supplies `target_date` and `target_status` for
the same road. The regression's training label is simply

\[
y_i=\text{target_status}_i\in\{0,1,2\}.
\]

This is a three-class label, not a binary “changed/unchanged” label.
`target_status` and `target_date` are never included in the predictors.
`road_id` is used for data joining and reporting, not as a regression
feature. The input tables are:

- `../regression_input/regression_input.csv`: model-ready
  road-date observations and historical weather/flood measurements.
- `../road_data/roads_all(2).csv`: road-condition observations
  used to construct each road's history up to its current map.

The rainfall and flood windows contain complete calendar days ending on
`feature_cutoff_date`, the day **before** `issue_date`. Rainfall comes from
historical ERA5 road-grid averages. Flood features summarize product-detected
pixels within a 2 km buffer around an approximated route. Coordinates were
used upstream to build these features; they do not enter the regression as
columns. No future rain or flood forecast is an input.

## 2. The exact input vector

Let (X_i) be one row's **unscaled**, ordered, 18-dimensional feature
vector. `fit_status_logistic.py` passes these columns to scikit-learn in
exactly this order:

```text
X_i = (
   1  current_partial,
   2  current_impassable,
   3  season_sin,
   4  season_cos,
   5  log_status_age_days,
   6  recent_status_change,
   7  has_previous_map,
   8  ever_observed_change,
   9  previous_map_gap_days,
  10  log_rain_7d,
  11  rain_trend_log,
  12  flood_detected_days_7d,
  13  flood_trend_days,
  14  log_flood_intensity_7d,
  15  current_partial_x_log_rain_7d,
  16  current_partial_x_flood_detected_days_7d,
  17  current_impassable_x_log_rain_7d,
  18  current_impassable_x_flood_detected_days_7d
)
```

Definitions used below: `s` is the current status; `m` is the current map's
month (1–12). `R7` and `R14` are rainfall totals for the preceding 7 and 14
days. `F7` and `F14` count days with a flood-pixel detection near the road in
those windows. `I7` is the 7-day sum of matched flood-pixel detections divided
by approximate route length in km. The preceding, non-overlapping seven days
are `Rprev = R14 − R7` and `Fprev = F14 − F7`. Tiny negative subtraction
errors are clipped to zero; materially negative values raise an error.

| No. | Column | Exact construction |
| ---: | --- | --- |
| 1 | `current_partial` | `1(s = 1)`; otherwise 0. |
| 2 | `current_impassable` | `1(s = 2)`; otherwise 0. If `s = 0`, both no. 1 and no. 2 are 0. |
| 3 | `season_sin` | `sin(2π(m − 1)/12)`. |
| 4 | `season_cos` | `cos(2π(m − 1)/12)`. The two seasonal columns place December and January near each other. |
| 5 | `log_status_age_days` | `log(1 + days since the latest *observed* status change)`; if no change was observed, count from the road's first map. |
| 6 | `recent_status_change` | 1 if the current status differs from the immediately preceding available map for this road; otherwise 0. |
| 7 | `has_previous_map` | 1 if an earlier map exists for this road; otherwise 0. |
| 8 | `ever_observed_change` | 1 if a status change has been observed for this road up to and including the current map; otherwise 0. |
| 9 | `previous_map_gap_days` | Days since the preceding map for this road; 0 if none exists. |
| 10 | `log_rain_7d` | `log(1 + R7)`; rainfall is in mm. |
| 11 | `rain_trend_log` | `log(1 + R7) − log(1 + Rprev)`. |
| 12 | `flood_detected_days_7d` | `F7`; zero means no detection in this product, not proof that the road was dry. |
| 13 | `flood_trend_days` | `F7 − Fprev`. |
| 14 | `log_flood_intensity_7d` | `log(1 + I7)`; `I7` is pixel detections per route km, not flooded area in km². |
| 15 | `current_partial_x_log_rain_7d` | Feature 1 × feature 10. |
| 16 | `current_partial_x_flood_detected_days_7d` | Feature 1 × feature 12. |
| 17 | `current_impassable_x_log_rain_7d` | Feature 2 × feature 10. |
| 18 | `current_impassable_x_flood_detected_days_7d` | Feature 2 × feature 12. |

Features 5–9 are built by sorting **all** source map rows for each road by
date, including rows without a 10–14-day target. For any issue date, the
history uses only that map and earlier maps. The last four interactions allow
the rain/flood relationship to differ according to the road's current status.

### A real vector and its label

Road 55 is impassable (`current_status=2`) on **2024-01-19** and passable
with difficulties (`target_status=1`) on **2024-02-02**. Its environmental
measurements stop on **2024-01-18**. `F7=1` and `F14=3`, so
`Fprev=2` and `flood_trend_days=−1`. Rainfall in both windows is zero.
The unscaled input is, rounded:

```text
X_55,2024-01-19 = (
  0, 1, 0, 1, 2.70805, 0, 1, 0, 7,
  0, 0, 1, -1, 0.027007, 0, 0, 0, 1
)
y_55,2024-01-19 = 1
```

The fifth value is `log(1+14)=log(15)`: no earlier change was observed, and
this road's first map was 14 days earlier. The target `1` is used for
training, but it is **not** in (X_i).

## 3. How training works

The 2024 development period contains **5,001** road-date rows. There are
**201** pairs whose future status differs from their current status, but the
model uses the actual future class `0`, `1`, or `2` as (y_i). It does not
collapse the target to changed/unchanged.

First, a `StandardScaler` learns each input column's mean and scale **from
the training rows only** and transforms the 18 raw values:

\[
z_{ij}=(x_{ij}-\mu_j)/\sigma_j.
\]

The same saved scaler transforms validation and test rows. This applies to
binary indicators and interaction columns too. Within each validation fold,
the scaler is refitted on that fold's training subset; validation data never
sets its means or scales.

Next, `LogisticRegression(C=0.3, max_iter=2000)` fits **three class-specific
linear scores** on the standardized vector. For class (k\in\{0,1,2\}):

\[
a_{ik}=\beta_{k0}+\sum_{j=1}^{18}\beta_{kj}z_{ij},
\qquad
P(y_i=k\mid X_i)=\frac{e^{a_{ik}}}{e^{a_{i0}}+e^{a_{i1}}+e^{a_{i2}}}.
\]

This final softmax step produces the three class confidences **directly from
the multinomial regression**. Training minimizes multiclass cross-entropy
with L2 regularization; `C=0.3` is the inverse regularization strength.
There is no class weighting or resampling. The coefficients describe
predictive associations in standardized features, not causal effects.

The `predicted_status` is the class with the largest probability, and
`confidence` is that largest probability. The CSV also keeps each of the
three probabilities, so a user does not lose information by looking only at
the winning class. These are fitted model probabilities; they have not been
separately calibrated.

### Chronological validation

The script checks three later blocks of 2024 dates. In each fold, training
uses only rows whose **target map date is strictly before the first
validation issue date**, so a future road label cannot enter a prediction:

| Fold | Training rows / changed pairs | Validation issue dates | Validation rows / changed pairs |
| ---: | ---: | --- | ---: |
| 1 | 2,128 / 88 | 2024-05-31 to 2024-06-21 | 539 / 36 |
| 2 | 2,530 / 124 | 2024-07-04 to 2024-07-25 | 548 / 42 |
| 3 | 2,941 / 140 | 2024-08-01 to 2024-12-12 | 1,786 / 35 |

The final pipeline is fitted again on all 5,001 2024 development rows and
evaluated on **4,708** within-2025 rows. Cross-year pairs are excluded from
this fixed comparison. The 2025 set was viewed during earlier experiments,
so these numbers are exploratory rather than a fresh final holdout. Multiple
rows for one road are correlated; they are not independent physical events.

## 4. Run and outputs

From the repository root, with NumPy, pandas, scikit-learn, and joblib
installed:

```powershell
python regression/fit_status_logistic.py
```

The script defaults to the repository input tables above and writes into
`results/`. Pass `--input`, `--roads-csv`, and optionally `--output-dir` if
using different paths. If these packages are missing, install them with
`python -m pip install numpy pandas scikit-learn joblib`.

| File | Purpose |
| --- | --- |
| `fit_status_logistic.py` | Feature construction, direct three-class regression, time validation, and evaluation. |
| `results/status_logistic_model.joblib` | Fitted standardization + multinomial logistic pipeline. |
| `results/coefficients.csv` | One fitted coefficient per feature and target class, on the standardized scale. |
| `results/cv_metrics.csv` | Scores for the three 2024 validation blocks. |
| `results/test_metrics.json` | 2025 multiclass scores, confusion matrix, training counts, and SHA-256 hashes of the two source CSVs. |
| `results/test_predictions.csv` | One 2025 row per road/date, with all three class probabilities, predicted class, and confidence. |

On the 2025 diagnostic set, the direct model's accuracy is **93.56%**, but it
correctly identifies **0 of the 303 changed road-date pairs** by its highest
probability class. Thus its current three-class confidence output exists and
is reproducible, while its performance on the operationally important
changes remains weak. All 34 added 2025 observations for road 117 are
unchanged; the small accuracy increase from the earlier run mostly reflects
those additional easy rows. Overall accuracy largely reflects unchanged roads.

### Input-data version note

The `regression_input/` table was rebuilt after the Nadapal and Payuel
coordinate corrections on 2026-10-05. It now includes road 117 and revised
features for roads 111, 131, and 137. The saved model and `results/` files
above were refitted on that rebuilt table. `test_metrics.json` records the
input CSV hashes so a later data rebuild can be distinguished from this run.
