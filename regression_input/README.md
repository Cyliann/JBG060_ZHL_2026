# Road passability regression input

This folder is generated from the road-status CSV in `road_data` and the
separate `../data-JBG060-2026` download. The generator is
`processing_data/build_regression_input.py` in this repository. It does not fit
a regression model.

## Files

- `regression_input.parquet`: labeled road-date rows with complete spatial
  features and geometry quality `ok`. This is the first modeling table.
- `regression_input.csv`: the same modeling table for quick inspection.
- `labeled_road_dates.parquet`: all road-date rows with a 10-14 day target,
  including roads whose geometry still needs checking.
- `road_date_features.parquet`: all map dates, including those without a target
  map in the 10-14 day window.
- `road_daily_flood.parquet`: daily counts of detected flood pixels near each
  route, useful for auditing the time aggregation.
- `road_geometries.geojson`: piecewise straight route approximation by
  `road_id`, with geometry quality flags.
- `qa.json`: counts, exclusions, settings and basic validation results.

## How flood pixels are matched to roads

`roads_all(2).csv` names each road's `from`, `via`, and `to` places.
`road_data/with_coords.csv` supplies their latitude and longitude. The
preprocessor connects consecutive places with straight segments using the
latest road map as its reference geometry. It converts both road segments
and flood-pixel coordinates to a meter-based projection, buffers each route
by 2 km by default, and matches a detected pixel to a road when the pixel's
point falls in that buffer. A pixel can match more than one nearby road;
duplicate observations of the same pixel for one road and date are counted
once. This produces daily pixel counts and a daily detected/not-detected
indicator for each road.

For every issue map, the daily values are summed over the preceding 7 or 14
complete days. The current map date is excluded. The `*_per_km` features
divide pixel counts by the approximate route length. These are nearby flood
**detections**, not direct observations that the road surface was submerged.

## What one row means

`issue_date` is the road-map date. `current_status` is its label: 0 passable,
1 partially passable, 2 impassable. `target_date` is the first available map
10-14 days later, and `target_status` is the same road's label on that map.
`y_blocked` is 1 when `target_status == 2`; for this binary definition, partial
passability is grouped with passability. It means red on the Logistics Cluster
map, not impassability for every possible vehicle. Keep `target_status` for a three-class
or alternative binary analysis. `new_blocked` is defined only for roads whose
current status is 0 or 1. `evaluation_split` separates within-2024 development,
within-2025 testing, and cross-year rows.

All `*_7d` and `*_14d` features use complete calendar-day windows ending on
`feature_cutoff_date`, the day **before** `issue_date`. Flood features count
detected pixel-days in a 2 km buffer around the route; the per-km variants
divide by approximate straight-line route length. ERA5 rainfall and runoff
features are length-weighted road-grid averages of daily totals, in mm.
`current_partial` and `current_impassable` are ready-to-use status indicators;
the passable category is the reference.

For an initial model, use `current_partial`, `current_impassable`, selected
flood/rain/runoff windows and a season encoding derived from `issue_month`.
`road_id` is a join key; `target_date`, `target_status`, `y_blocked` and
`new_blocked` contain outcome information and are **not predictors**.

## Assumptions and limits

- Route geometry is derived from the final 2025-12-24 place sequence and
  straight connections between places. The historical route geometry is
  assumed stable. Road 133 has two disconnected pieces.
- The current `regression_input` files were rebuilt after the Nadapal and
  Payuel coordinate corrections on 2026-10-05. Road 117 now has spatial
  features. Road 112 (`Akun` versus `Akon`) remains excluded because its
  place match is unverified.
- The compact flood files contain detected event pixels from a 3-day composite,
  not a complete daily valid-observation mask. Zero means **no detection in
  this product**, not verified dry conditions. Buffer width is an assumption.
- ERA5 is historical reanalysis. This table tests prediction from lagged
  observations and current road state. It does not evaluate a third-party
  flood-forecast input.
- Map dates are nominal map dates; actual survey/publication times are not in
  the road CSV. Road conditions are access-map classes and are not labeled by
  cause, so `y_blocked` is not proof of flood-caused closure.
- The final 2025 network GeoJSON `weight` and contemporaneous `truck_type`
  were not used as weather or road predictors.

## Regenerate

From the repository root, with the project's data-processing dependencies
installed:

```powershell
python processing_data/build_regression_input.py `
  --roads-csv 'road_data/roads_all(2).csv' `
  --coords-csv 'road_data/with_coords.csv' `
  --data-root '../data-JBG060-2026' `
  --output-dir '../regression_input_rebuilt'
```

Review the rebuilt `qa.json` and refit the model before replacing the
committed input files. The command above leaves those files unchanged.

The saved regression model and results predate this input rebuild and must be
refitted before they are interpreted as results for the current data. The
model uses 2024 for development and 2025 as an exploratory diagnostic set;
2025 has already been examined and is not a fresh final holdout. Read
`qa.json` before modeling: 13,239 source rows are repeated road observations,
not 13,239 independent road closures.
