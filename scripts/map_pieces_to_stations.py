#!/usr/bin/env python3
"""
Step 2: Spatial Piece-to-Station Mapping
ThermoRail Hybrid Risk Engine & Historical Baseline Integration

Binds each of the 10,216 rail pieces to the nearest historical Punjab station
using a 3D spherical cKDTree:
1. Converts station and rail piece coordinates into radians and 3D unit coordinates.
2. Queries the KDTree scaled to Earth's mean radius (6371 km).
3. Tags each rail piece with:
   - has_86yr_baseline: True if distance <= 35.0 km, else False
   - nearest_station_id: Station string ID if within 35 km, else None (null)
   - dist_to_station_km: Floating-point great-circle distance in km

Outputs: piece_station_mapping.csv
"""

import sys
import os
import time
import json
import psutil
import pandas as pd
import numpy as np
from scipy.spatial import cKDTree

EARTH_RADIUS_KM = 6371.0
THRESHOLD_KM = 35.0


def get_memory_usage_mb():
    """Returns current process RSS memory in MB."""
    process = psutil.Process(os.getpid())
    return process.memory_info().rss / (1024 * 1024)


def map_pieces_to_stations():
    start_time = time.time()
    print("=" * 65)
    print("ThermoRail: Step 2 - Spatial Piece-to-Station Mapping")
    print("=" * 65)
    print(f"Initial Memory: {get_memory_usage_mb():.1f} MB")

    stations_csv = "punjab_stations.csv"
    geojson_path = "pk_rail_heat_v2.geojson"
    output_csv = "piece_station_mapping.csv"

    if not os.path.exists(stations_csv):
        raise FileNotFoundError(f"Missing {stations_csv}. Run Step 1 first.")
    if not os.path.exists(geojson_path):
        raise FileNotFoundError(f"Missing {geojson_path}.")

    # 1. Load stations and convert to radians
    print(f"Loading station metadata from {stations_csv}...")
    stations = pd.read_csv(stations_csv)
    print(f"Loaded {len(stations)} stations.")

    stat_lats = np.radians(stations["lat"].values)
    stat_lons = np.radians(stations["lon"].values)

    # 3D Cartesian coordinates on sphere
    stat_x = EARTH_RADIUS_KM * np.cos(stat_lats) * np.cos(stat_lons)
    stat_y = EARTH_RADIUS_KM * np.cos(stat_lats) * np.sin(stat_lons)
    stat_z = EARTH_RADIUS_KM * np.sin(stat_lats)
    stat_coords_3d = np.column_stack([stat_x, stat_y, stat_z])

    print("Constructing 3D spatial cKDTree index for stations...")
    tree_start = time.time()
    tree = cKDTree(stat_coords_3d)
    print(f"Index built in {time.time() - tree_start:.4f}s")

    # 2. Load rail pieces from GeoJSON
    print(f"Loading rail pieces from {geojson_path}...")
    load_start = time.time()
    with open(geojson_path, "r", encoding="utf-8") as f:
        geojson_data = json.load(f)

    features = geojson_data["features"]
    total_pieces = len(features)
    print(f"Loaded {total_pieces:,} rail features in {time.time() - load_start:.2f}s | Memory: {get_memory_usage_mb():.1f} MB")

    # Extract center coordinates and metadata
    osm_ids = []
    pieces = []
    names = []
    cell_ids = []
    lats = []
    lons = []

    for f in features:
        p = f["properties"]
        osm_ids.append(p.get("osm_id"))
        pieces.append(p.get("piece"))
        names.append(p.get("name"))
        cell_ids.append(p.get("cell_id"))
        lats.append(float(p["lat"]))
        lons.append(float(p["lon"]))

    p_lats_rad = np.radians(lats)
    p_lons_rad = np.radians(lons)

    p_x = EARTH_RADIUS_KM * np.cos(p_lats_rad) * np.cos(p_lons_rad)
    p_y = EARTH_RADIUS_KM * np.cos(p_lats_rad) * np.sin(p_lons_rad)
    p_z = EARTH_RADIUS_KM * np.sin(p_lats_rad)
    piece_coords_3d = np.column_stack([p_x, p_y, p_z])

    # 3. Query the KDTree
    print(f"Querying nearest station for {total_pieces:,} pieces...")
    query_start = time.time()
    chords, nearest_indices = tree.query(piece_coords_3d, k=1)

    # Convert chord distance to great-circle arc distance
    arc_distances = 2.0 * EARTH_RADIUS_KM * np.arcsin(np.clip(chords / (2.0 * EARTH_RADIUS_KM), 0.0, 1.0))
    query_time = time.time() - query_start
    print(f"Spatial query completed in {query_time:.3f}s")

    # 4. Tag each rail piece
    station_id_array = stations["station_id"].values
    matched_station_ids = station_id_array[nearest_indices]

    has_baseline = arc_distances <= THRESHOLD_KM
    # nearest_station_id is string if within 35km, else None (null)
    final_station_ids = [matched_station_ids[i] if has_baseline[i] else None for i in range(total_pieces)]

    mapping_df = pd.DataFrame({
        "piece_index": np.arange(total_pieces),
        "osm_id": osm_ids,
        "piece": pieces,
        "name": names,
        "cell_id": cell_ids,
        "lat": lats,
        "lon": lons,
        "has_86yr_baseline": has_baseline,
        "nearest_station_id": final_station_ids,
        "dist_to_station_km": np.round(arc_distances, 3),
        "raw_nearest_station_id": matched_station_ids  # retains geometric nearest station for reference
    })

    # Data integrity checks
    if len(mapping_df) != total_pieces:
        raise ValueError(f"Integrity check failed: Expected {total_pieces} rows, got {len(mapping_df)}")

    punjab_count = int(has_baseline.sum())
    fallback_count = total_pieces - punjab_count
    print(f"Punjab pieces (within {THRESHOLD_KM} km): {punjab_count:,} ({punjab_count / total_pieces * 100:.1f}%)")
    print(f"National fallback pieces (> {THRESHOLD_KM} km): {fallback_count:,} ({fallback_count / total_pieces * 100:.1f}%)")

    # Export mapping CSV
    mapping_df.to_csv(output_csv, index=False)
    file_size_kb = os.path.getsize(output_csv) / 1024
    print(f"Saved piece-station mapping to {output_csv} ({file_size_kb:.1f} KB)")

    total_time = time.time() - start_time
    print("=" * 65)
    print(f"Execution Summary: Processed {total_pieces:,} pieces in {total_time:.2f}s")
    print(f"Peak Memory Usage: {get_memory_usage_mb():.1f} MB")
    print("=" * 65)
    return mapping_df


if __name__ == "__main__":
    map_pieces_to_stations()

