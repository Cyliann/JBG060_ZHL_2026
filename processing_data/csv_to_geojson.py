import csv
import json
from typing import Any


def process_node(row: dict[str, Any], node_coords: dict) -> (dict, dict):
    # Extract coordinates and properties
    lon = float(row["lon"])
    lat = float(row["lat"])
    node_id = row["node_id"]
    name = row["name"]
    degree = int(row["degree"])

    # Create GeoJSON feature
    feature = {
        "type": "Feature",
        "geometry": {
            "type": "Point",
            "coordinates": [lon, lat],  # GeoJSON uses [lon, lat]
        },
        "properties": {"node_id": node_id, "name": name, "degree": degree},
    }
    node_coords[node_id] = [lon, lat]  # GeoJSON uses [lon, lat]
    return (feature, node_coords)


def edges_to_geojson(edges_file, nodes_csv_file, geojson_file):
    """
    Convert an edges file to GeoJSON format with LineStrings.

    Expected edges CSV columns: source_node_id, target_node_id, [skip_column]
    Expected nodes CSV columns: node_id, name, degree, lat, lon
    """

    # First, load node coordinates from the nodes CSV
    node_coords = {}
    features = []

    with open(nodes_csv_file, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        node_coords = {}

        for row in reader:
            try:
                (feature, node_coords) = process_node(row, node_coords)
                features.append(feature)
            except (ValueError, KeyError) as e:
                print(f"Skipping node row with error: {e}")
                continue
    print(f"Loaded coordinates for {len(node_coords)} nodes")

    # Now process edges
    skipped_edges = 0

    with open(edges_file, encoding="utf-8") as f:
        # Since the file is space-separated, we use delimiter=' '
        reader = csv.reader(f, delimiter=" ")

        edge_id = 0
        for row in reader:
            try:
                source_id = str(row[0]).strip()
                target_id = str(row[1]).strip()
                # row[2] is skipped

                # Check if both nodes exist in our coordinate dictionary
                if source_id not in node_coords or target_id not in node_coords:
                    print(f"Skipping row {row}. No coordinates")
                    skipped_edges += 1
                    continue

                # Create GeoJSON feature for the edge
                feature = {
                    "type": "Feature",
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [node_coords[source_id], node_coords[target_id]],
                    },
                    "properties": {
                        "edge_id": edge_id,
                        "source": source_id,
                        "target": target_id,
                    },
                }
                features.append(feature)
                edge_id += 1
            except (ValueError, KeyError, IndexError) as e:
                print(f"Skipping edge row {row} with error: {e}")
                skipped_edges += 1
                continue

    # Create GeoJSON FeatureCollection
    geojson_data = {"type": "FeatureCollection", "features": features}

    # Write to file
    with open(geojson_file, "w", encoding="utf-8") as f:
        json.dump(geojson_data, f, indent=2)

    print(f"Successfully created {geojson_file} with {len(features)} edges")
    if skipped_edges > 0:
        print(f"Skipped {skipped_edges} edges (missing node coordinates)")


if __name__ == "__main__":
    edges_to_geojson(
        "../road_network/roads_2025-12-24_new.edges",
        "../road_data/with_coords.csv",
        "roadmap.geojson",
    )
