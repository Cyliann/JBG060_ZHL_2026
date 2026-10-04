"""Build dated, road-level inputs for the South Sudan passability model.

The script reads source data without modifying it. All weather and flood
features end on the day before the road-map issue date. Flood counts mean
detected flood pixels; zero does not certify a cloud-free, dry observation.
"""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import shapely
import xarray as xr
from pyproj import Transformer
from shapely.geometry import LineString, MultiLineString, mapping
from shapely.strtree import STRtree


WGS84_TO_METERS = Transformer.from_crs(
    "EPSG:4326", "+proj=aeqd +lat_0=7.5 +lon_0=30 +datum=WGS84 +units=m", always_xy=True
)
METERS_TO_WGS84 = Transformer.from_crs(
    "+proj=aeqd +lat_0=7.5 +lon_0=30 +datum=WGS84 +units=m", "EPSG:4326", always_xy=True
)
FLOOD_TYPES = (("compact_recurring", 0), ("compact_unusual", 1))
TILES = ("h20v08", "h21v08")


def load_statuses(path: Path) -> pd.DataFrame:
    roads = pd.read_csv(path, encoding="utf-8-sig")
    required = {"road_id", "date", "from", "to", "via", "condition_code"}
    missing = required - set(roads.columns)
    if missing:
        raise ValueError(f"Road table missing columns: {sorted(missing)}")
    roads["date"] = pd.to_datetime(roads["date"], errors="raise").dt.normalize()
    if roads.duplicated(["road_id", "date"]).any():
        raise ValueError("Duplicate road_id/date labels")
    if not roads["condition_code"].isin([0, 1, 2]).all():
        raise ValueError("Unexpected road condition code")
    return roads


def route_pairs(row: pd.Series) -> list[tuple[str, str]]:
    if int(row.road_id) == 133:
        return [("Kaikang", "Roriak"), ("Mayom", "Kilo 30")]
    via = [] if pd.isna(row.via) else [part.strip() for part in str(row.via).split(";")]
    places = [str(row["from"]).strip(), *via, str(row["to"]).strip()]
    return list(zip(places, places[1:]))


def build_routes(roads: pd.DataFrame, coords_path: Path) -> dict[int, dict]:
    coords = pd.read_csv(coords_path)
    if coords["name"].duplicated().any():
        raise ValueError("Duplicate place names in coordinate table")
    points = {row["name"]: (float(row["lon"]), float(row["lat"])) for _, row in coords.iterrows()}
    latest = roads.loc[roads["date"] == roads["date"].max()].sort_values("road_id")
    if latest["road_id"].duplicated().any():
        raise ValueError("Latest map has duplicate road IDs")

    routes: dict[int, dict] = {}
    for _, row in latest.iterrows():
        road_id = int(row.road_id)
        pairs = route_pairs(row)
        status = "ok"
        lines_wgs84 = []
        lines_meters = []
        for left, right in pairs:
            if left == "Akun" or right == "Akun":
                status = "unverified_akun_akon_alias"
            a = points.get("Akon" if left == "Akun" else left)
            b = points.get("Akon" if right == "Akun" else right)
            if a is None or b is None:
                status = "unmatched_place"
                continue
            ax, ay = WGS84_TO_METERS.transform(*a)
            bx, by = WGS84_TO_METERS.transform(*b)
            if math.hypot(ax - bx, ay - by) < 1:
                status = "zero_length_segment"
                continue
            lines_wgs84.append(LineString([a, b]))
            lines_meters.append(LineString([(ax, ay), (bx, by)]))
        if len(lines_wgs84) != len(pairs) and status == "ok":
            status = "incomplete_geometry"
        routes[road_id] = {
            "status": status,
            "pairs": pairs,
            "geometry_wgs84": MultiLineString(lines_wgs84) if lines_wgs84 else None,
            "segments_meters": lines_meters,
            "length_km": sum(line.length for line in lines_meters) / 1000 if status == "ok" else np.nan,
        }
    return routes


def flood_daily(
    routes: dict[int, dict], flood_root: Path, start: pd.Timestamp, end: pd.Timestamp,
    buffer_km: float, batch_size: int,
) -> tuple[pd.DataFrame, dict]:
    ready = [(road_id, route) for road_id, route in routes.items() if route["status"] == "ok"]
    road_ids = [road_id for road_id, _ in ready]
    buffers = [MultiLineString(route["segments_meters"]).buffer(buffer_km * 1000) for _, route in ready]
    tree = STRtree(buffers)
    bounds = [route["geometry_wgs84"].bounds for _, route in ready]
    padding = buffer_km / 100 + 0.02  # Conservative degrees throughout South Sudan.
    lon_min = min(box[0] for box in bounds) - padding
    lat_min = min(box[1] for box in bounds) - padding
    lon_max = max(box[2] for box in bounds) + padding
    lat_max = max(box[3] for box in bounds) + padding

    hits = []
    raw_rows = 0
    for year in range(start.year, end.year + 1):
        for directory, flood_type in FLOOD_TYPES:
            for tile in TILES:
                path = flood_root / directory / f"flood_events_{tile}_{year}.parquet"
                if not path.is_file():
                    raise FileNotFoundError(path)
                parquet = pq.ParquetFile(path)
                for batch in parquet.iter_batches(batch_size=batch_size, columns=["date", "lat", "lon"]):
                    frame = batch.to_pandas()
                    raw_rows += len(frame)
                    frame["date"] = pd.to_datetime(frame["date"], errors="coerce").dt.normalize()
                    frame = frame.loc[frame["date"].between(start, end)]
                    if frame.empty:
                        continue
                    frame = frame.loc[
                        frame["lat"].between(lat_min, lat_max)
                        & frame["lon"].between(lon_min, lon_max)
                    ].copy()
                    if frame.empty:
                        continue
                    x, y = WGS84_TO_METERS.transform(frame["lon"].to_numpy(), frame["lat"].to_numpy())
                    point_index, buffer_index = tree.query(shapely.points(x, y), predicate="intersects")
                    if len(point_index):
                        matched = frame.iloc[point_index][["date", "lat", "lon"]].copy()
                        matched["road_id"] = np.asarray(road_ids, dtype=np.int32)[buffer_index]
                        matched["flood_type"] = flood_type
                        hits.append(matched)
                print(f"Flood scan: {year} {directory} {tile}: {parquet.metadata.num_rows:,} rows")

    if hits:
        events = pd.concat(hits, ignore_index=True)
        events = events.sort_values("flood_type", ascending=False).drop_duplicates(
            ["road_id", "date", "lat", "lon"], keep="first"
        )
        daily = events.groupby(["road_id", "date"], as_index=False).agg(
            flood_pixel_detections=("flood_type", "size"),
            unusual_pixel_detections=("flood_type", "sum"),
        )
        matched_rows = len(events)
    else:
        daily = pd.DataFrame(columns=["road_id", "date", "flood_pixel_detections", "unusual_pixel_detections"])
        matched_rows = 0
    calendar = pd.MultiIndex.from_product(
        [list(routes), pd.date_range(start, end, freq="D")], names=["road_id", "date"]
    ).to_frame(index=False)
    daily = calendar.merge(daily, on=["road_id", "date"], how="left", validate="one_to_one")
    valid_ids = {road_id for road_id, route in ready}
    valid = daily["road_id"].isin(valid_ids)
    for column in ("flood_pixel_detections", "unusual_pixel_detections"):
        daily.loc[valid, column] = daily.loc[valid, column].fillna(0)
    daily["flood_detected"] = (daily["flood_pixel_detections"] > 0).where(valid)
    daily["unusual_flood_detected"] = (daily["unusual_pixel_detections"] > 0).where(valid)
    return daily, {"raw_flood_rows_scanned": raw_rows, "matched_road_pixel_days": matched_rows}


def route_grid_weights(routes: dict[int, dict], latitude: np.ndarray, longitude: np.ndarray,
                       sample_km: float) -> dict[int, list[tuple[int, int, float]]]:
    result = {}
    for road_id, route in routes.items():
        if route["status"] != "ok":
            continue
        weights = defaultdict(float)
        for segment in route["segments_meters"]:
            count = max(1, math.ceil(segment.length / (sample_km * 1000)))
            for index in range(count):
                point = segment.interpolate((index + 0.5) * segment.length / count)
                lon, lat = METERS_TO_WGS84.transform(point.x, point.y)
                lat_idx = int(np.abs(latitude - lat).argmin())
                lon_idx = int(np.abs(longitude - lon).argmin())
                weights[(lat_idx, lon_idx)] += segment.length / count
        total = sum(weights.values())
        result[road_id] = [(lat_idx, lon_idx, weight / total) for (lat_idx, lon_idx), weight in weights.items()]
    return result


def era5_daily(routes: dict[int, dict], era5_dir: Path, start: pd.Timestamp,
               end: pd.Timestamp, sample_km: float) -> pd.DataFrame:
    parts = []
    grid_weights = None
    grid_shape = None
    for year in range(start.year, end.year + 1):
        path = era5_dir / f"ERA5_{year}.nc"
        if not path.is_file():
            raise FileNotFoundError(path)
        with xr.open_dataset(path) as ds:
            shape = (tuple(ds["latitude"].values), tuple(ds["longitude"].values))
            if grid_weights is None:
                grid_weights = route_grid_weights(
                    routes, ds["latitude"].values, ds["longitude"].values, sample_km
                )
                grid_shape = shape
            elif shape != grid_shape:
                raise ValueError("ERA5 coordinate grid changed between years")
            used_cells = [cell for weights in grid_weights.values() for cell in weights]
            lat_min = min(lat for lat, _, _ in used_cells)
            lat_max = max(lat for lat, _, _ in used_cells)
            lon_min = min(lon for _, lon, _ in used_cells)
            lon_max = max(lon for _, lon, _ in used_cells)
            subset = ds[["tp", "ro"]].isel(
                latitude=slice(lat_min, lat_max + 1), longitude=slice(lon_min, lon_max + 1)
            )
            daily = subset.resample(valid_time="1D").sum(min_count=1)
            dates = pd.to_datetime(daily["valid_time"].values).normalize()
            tp = daily["tp"].values
            ro = daily["ro"].values
            for road_id, cells in grid_weights.items():
                lat_index = np.array([lat - lat_min for lat, _, _ in cells])
                lon_index = np.array([lon - lon_min for _, lon, _ in cells])
                weight = np.array([value for _, _, value in cells])
                rain_samples = tp[:, lat_index, lon_index]
                runoff_samples = ro[:, lat_index, lon_index]
                rain = np.sum(rain_samples * weight, axis=1) * 1000
                runoff = np.sum(runoff_samples * weight, axis=1) * 1000
                rain[~np.isfinite(rain_samples).all(axis=1)] = np.nan
                runoff[~np.isfinite(runoff_samples).all(axis=1)] = np.nan
                parts.append(pd.DataFrame({
                    "road_id": road_id, "date": dates, "rain_mm": rain, "runoff_mm": runoff
                }))
        print(f"ERA5 aggregation: {year}")
    weather = pd.concat(parts, ignore_index=True)
    return weather.loc[weather["date"].between(start, end)].reset_index(drop=True)


def build_panel(roads: pd.DataFrame, routes: dict[int, dict], flood: pd.DataFrame,
                weather: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    daily = flood.merge(weather, on=["road_id", "date"], how="left", validate="one_to_one")
    daily = daily.sort_values(["road_id", "date"]).reset_index(drop=True)
    lengths = {road_id: route["length_km"] for road_id, route in routes.items()}
    daily["route_length_km"] = daily["road_id"].map(lengths)
    daily["flood_pixel_detections_per_km"] = daily["flood_pixel_detections"] / daily["route_length_km"]
    daily["unusual_pixel_detections_per_km"] = daily["unusual_pixel_detections"] / daily["route_length_km"]
    daily["flood_detected"] = daily["flood_detected"].astype("Float64")
    daily["unusual_flood_detected"] = daily["unusual_flood_detected"].astype("Float64")
    windows = {
        "flood_detected": "flood_detected_days",
        "unusual_flood_detected": "unusual_flood_detected_days",
        "flood_pixel_detections_per_km": "flood_pixel_days_per_km",
        "unusual_pixel_detections_per_km": "unusual_pixel_days_per_km",
        "rain_mm": "rain_mm",
        "runoff_mm": "runoff_mm",
    }
    for source, output in windows.items():
        for days in (7, 14):
            daily[f"{output}_{days}d"] = daily.groupby("road_id")[source].transform(
                lambda series: series.shift(1).rolling(days, min_periods=days).sum()
            )
    feature_columns = [name for name in daily.columns if name.endswith("_7d") or name.endswith("_14d")]
    map_table = roads[["road_id", "date", "condition_code"]].rename(
        columns={"date": "issue_date", "condition_code": "current_status"}
    )
    features = daily[["road_id", "date", *feature_columns]].rename(columns={"date": "issue_date"})
    panel = map_table.merge(features, on=["road_id", "issue_date"], how="left", validate="one_to_one")
    panel["geometry_status"] = panel["road_id"].map({key: value["status"] for key, value in routes.items()})
    panel["route_length_km"] = panel["road_id"].map(lengths)
    panel["feature_cutoff_date"] = panel["issue_date"] - pd.Timedelta(days=1)
    panel["issue_year"] = panel["issue_date"].dt.year
    panel["issue_month"] = panel["issue_date"].dt.month
    panel["current_partial"] = panel["current_status"].eq(1).astype("int8")
    panel["current_impassable"] = panel["current_status"].eq(2).astype("int8")

    dates = list(pd.DatetimeIndex(map_table["issue_date"].unique()).sort_values())
    future = {}
    for issue in dates:
        candidates = [date for date in dates if 10 <= (date - issue).days <= 14]
        if candidates:
            future[issue] = candidates[0]
    panel["target_date"] = panel["issue_date"].map(future)
    targets = map_table.rename(columns={"issue_date": "target_date", "current_status": "target_status"})
    panel = panel.merge(targets, on=["road_id", "target_date"], how="left", validate="many_to_one")
    panel["horizon_days"] = (panel["target_date"] - panel["issue_date"]).dt.days
    panel["y_blocked"] = panel["target_status"].eq(2).where(panel["target_status"].notna()).astype("Int64")
    at_risk = panel["target_status"].notna() & panel["current_status"].ne(2)
    panel["new_blocked"] = panel["target_status"].eq(2).where(at_risk).astype("Int64")
    labeled = panel.loc[panel["target_status"].notna()].copy()
    labeled["evaluation_split"] = np.select(
        [
            (labeled["issue_year"] == 2024) & (labeled["target_date"].dt.year == 2024),
            (labeled["issue_year"] == 2025) & (labeled["target_date"].dt.year == 2025),
        ],
        ["development_2024", "test_2025"],
        default="cross_year_or_other",
    )
    return panel, labeled


def write_geometries(routes: dict[int, dict], path: Path) -> None:
    features = []
    for road_id, route in routes.items():
        features.append({
            "type": "Feature",
            "properties": {
                "road_id": road_id, "geometry_status": route["status"],
                "route_length_km": None if pd.isna(route["length_km"]) else route["length_km"],
            },
            "geometry": mapping(route["geometry_wgs84"]) if route["geometry_wgs84"] else None,
        })
    path.write_text(json.dumps({"type": "FeatureCollection", "features": features}), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--roads-csv", type=Path, required=True)
    parser.add_argument("--coords-csv", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--buffer-km", type=float, default=2.0)
    parser.add_argument("--sample-km", type=float, default=10.0)
    parser.add_argument("--flood-batch-size", type=int, default=100_000)
    args = parser.parse_args()
    if args.buffer_km <= 0 or args.sample_km <= 0 or args.flood_batch_size <= 0:
        parser.error("Buffer, sample spacing and batch size must be positive")
    return args


def main() -> None:
    args = parse_args()
    roads = load_statuses(args.roads_csv)
    routes = build_routes(roads, args.coords_csv)
    start = roads["date"].min() - pd.Timedelta(days=14)
    end = roads["date"].max()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    print(f"Roads: {len(routes)}, date coverage: {start.date()} to {end.date()}")
    flood, flood_qa = flood_daily(
        routes, args.data_root / "flood_masks", start, end,
        args.buffer_km, args.flood_batch_size,
    )
    weather = era5_daily(routes, args.data_root / "rainfall and runoff", start, end, args.sample_km)
    panel, labeled = build_panel(roads, routes, flood, weather)
    feature_columns = [
        column for column in labeled.columns if column.endswith("_7d") or column.endswith("_14d")
    ]
    model_ready = labeled.loc[
        labeled["geometry_status"].eq("ok") & labeled[feature_columns].notna().all(axis=1)
    ].copy()
    if not labeled["horizon_days"].between(10, 14).all():
        raise ValueError("Target outside the 10-14 day horizon")
    if not (labeled["feature_cutoff_date"] < labeled["issue_date"]).all():
        raise ValueError("Feature cutoff is not before the issue date")
    flood.to_parquet(args.output_dir / "road_daily_flood.parquet", index=False)
    panel.to_parquet(args.output_dir / "road_date_features.parquet", index=False)
    labeled.to_parquet(args.output_dir / "labeled_road_dates.parquet", index=False)
    model_ready.to_parquet(args.output_dir / "regression_input.parquet", index=False)
    model_ready.to_csv(args.output_dir / "regression_input.csv", index=False)
    write_geometries(routes, args.output_dir / "road_geometries.geojson")
    qa = {
        "road_count": len(routes),
        "geometry_status_counts": pd.Series([route["status"] for route in routes.values()]).value_counts().to_dict(),
        "map_rows": len(panel),
        "labeled_rows": len(labeled),
        "model_ready_rows": len(model_ready),
        "issue_dates_with_target": int(labeled["issue_date"].nunique()),
        "horizon_days": labeled["horizon_days"].value_counts().sort_index().to_dict(),
        "evaluation_split": labeled["evaluation_split"].value_counts().to_dict(),
        "new_blocked": int(labeled["new_blocked"].sum()),
        "spatial_features_missing_rows": int(labeled["flood_detected_days_14d"].isna().sum()),
        "weather_features_missing_rows": int(labeled["rain_mm_14d"].isna().sum()),
        "buffer_km": args.buffer_km,
        "sample_spacing_km": args.sample_km,
        "feature_cutoff": "day before issue_date",
        "geometry_reference": str(roads["date"].max().date()),
        "excluded_spatial_roads": [
            road_id for road_id, route in routes.items() if route["status"] != "ok"
        ],
        "zero_flood_detection_means": "no compact-product flood pixel matched; not verified dry",
        **flood_qa,
    }
    (args.output_dir / "qa.json").write_text(json.dumps(qa, indent=2), encoding="utf-8")
    print(json.dumps(qa, indent=2))


if __name__ == "__main__":
    main()
