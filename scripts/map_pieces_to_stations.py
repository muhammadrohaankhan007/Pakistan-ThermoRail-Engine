#!/usr/bin/env python3
"""
Step 2: Spatial Grid-Point Mapping (Cells & Pieces)
Pakistan ThermoRail - Spatial Correlation Engine

Maps each of the 787 weather cells and 10,216 rail pieces to the nearest
ERA5 reanalysis grid point using a 3D spherical cKDTree:
1. Converts grid point coordinates (702 Punjab locations) and query points to 3D Cartesian coords on Earth's sphere.
2. Identifies nearest grid point and computes great-circle distance.
3. Tags each location with:
   - in_grid_coverage: True if distance <= 35.0 km, else False
   - nearest_grid_point_id: String ID if within 35 km, else None (null)
   - dist_to_grid_point_km: Floating-point great-circle distance in km

Outputs:
- cell_grid_mapping.csv (787 cells)
- piece_station_mapping.csv (10,216 rail pieces, maintained for backwards compatibility)
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


def map_cells_and_pieces():
    start_time = time.time()
    print("=" * 70)
    print("ThermoRail: Step 2 - Spatial Cell & Piece to Grid-Point Mapping")
    print("=" * 70)
    print(f"Initial Memory: {get_memory_usage_mb():.1f} MB")

    grid_csv = "punjab_stations.csv"  # 702 ERA5 grid points
    cells_csv = "cell_heat.csv"        # 787 cells
    geojson_path = "pk_rail_heat_v2.geojson"  # 10,216 pieces
    output_cells_mapping = "cell_grid_mapping.csv"
    output_pieces_mapping = "piece_station_mapping.csv"

    if not os.path.exists(grid_csv):
        raise FileNotFoundError(f"Missing {grid_csv}.")
    if not os.path.exists(cells_csv):
        raise FileNotFoundError(f"Missing {cells_csv}.")

    # 1. Load grid points and construct 3D KDTree
    print(f"Loading grid point metadata from {grid_csv}...")
    grid_df = pd.read_csv(grid_csv)
    # Ensure column is grid_point_id
    id_col = "station_id" if "station_id" in grid_df.columns else "grid_point_id"
    grid_ids = grid_df[id_col].values
    num_grid_pts = len(grid_df)
    print(f"Loaded {num_grid_pts} ERA5 grid points.")

    g_lats = np.radians(grid_df["lat"].values)
    g_lons = np.radians(grid_df["lon"].values)
    g_x = EARTH_RADIUS_KM * np.cos(g_lats) * np.cos(g_lons)
    g_y = EARTH_RADIUS_KM * np.cos(g_lats) * np.sin(g_lons)
    g_z = EARTH_RADIUS_KM * np.sin(g_lats)
    grid_coords_3d = np.column_stack([g_x, g_y, g_z])

    print("Constructing 3D spatial cKDTree index for ERA5 grid points...")
    tree = cKDTree(grid_coords_3d)

    # 2. Map 787 cells from cell_heat.csv
    print(f"\nMapping 787 cell centroids from {cells_csv}...")
    cells_df = pd.read_csv(cells_csv)
    c_lats = np.radians(cells_df["api_lat"].values)
    c_lons = np.radians(cells_df["api_lon"].values)
    c_x = EARTH_RADIUS_KM * np.cos(c_lats) * np.cos(c_lons)
    c_y = EARTH_RADIUS_KM * np.cos(c_lats) * np.sin(c_lons)
    c_z = EARTH_RADIUS_KM * np.sin(c_lats)
    cell_coords_3d = np.column_stack([c_x, c_y, c_z])

    chords_c, indices_c = tree.query(cell_coords_3d, k=1)
    arc_dists_c = 2.0 * EARTH_RADIUS_KM * np.arcsin(np.clip(chords_c / (2.0 * EARTH_RADIUS_KM), 0.0, 1.0))
    in_coverage_c = arc_dists_c <= THRESHOLD_KM

    cells_mapping = pd.DataFrame({
        "cell_id": cells_df["cell_id"],
        "api_lat": cells_df["api_lat"],
        "api_lon": cells_df["api_lon"],
        "in_grid_coverage": in_coverage_c,
        "nearest_grid_point_id": [grid_ids[idx] if in_coverage_c[i] else None for i, idx in enumerate(indices_c)],
        "raw_nearest_grid_point_id": grid_ids[indices_c],
        "dist_to_grid_point_km": np.round(arc_dists_c, 3),
        "air_max_c": cells_df["air_max_c"],
        "air_p95_c": cells_df["air_p95_c"]
    })
    cells_mapping.to_csv(output_cells_mapping, index=False)
    cov_count = int(in_coverage_c.sum())
    print(f"Cells in Punjab grid coverage (<= {THRESHOLD_KM} km): {cov_count} / {len(cells_df)} ({cov_count/len(cells_df)*100:.1f}%)")
    print(f"Fallback cells (> {THRESHOLD_KM} km): {len(cells_df) - cov_count} / {len(cells_df)}")
    print(f"Saved {output_cells_mapping}")

    # 3. Map rail pieces if GeoJSON exists
    if os.path.exists(geojson_path):
        print(f"\nMapping rail pieces from {geojson_path}...")
        with open(geojson_path, "r", encoding="utf-8") as f:
            geojson_data = json.load(f)
        features = geojson_data["features"]
        total_pieces = len(features)

        p_osm_ids = []
        p_pieces = []
        p_names = []
        p_cell_ids = []
        p_lats = []
        p_lons = []

        for f in features:
            p = f["properties"]
            p_osm_ids.append(p.get("osm_id"))
            p_pieces.append(p.get("piece"))
            p_names.append(p.get("name"))
            p_cell_ids.append(p.get("cell_id"))
            p_lats.append(float(p["lat"]))
            p_lons.append(float(p["lon"]))

        p_lats_rad = np.radians(p_lats)
        p_lons_rad = np.radians(p_lons)
        p_x = EARTH_RADIUS_KM * np.cos(p_lats_rad) * np.cos(p_lons_rad)
        p_y = EARTH_RADIUS_KM * np.cos(p_lats_rad) * np.sin(p_lons_rad)
        p_z = EARTH_RADIUS_KM * np.sin(p_lats_rad)
        piece_coords_3d = np.column_stack([p_x, p_y, p_z])

        chords_p, indices_p = tree.query(piece_coords_3d, k=1)
        arc_dists_p = 2.0 * EARTH_RADIUS_KM * np.arcsin(np.clip(chords_p / (2.0 * EARTH_RADIUS_KM), 0.0, 1.0))
        in_coverage_p = arc_dists_p <= THRESHOLD_KM

        pieces_mapping = pd.DataFrame({
            "piece_index": np.arange(total_pieces),
            "osm_id": p_osm_ids,
            "piece": p_pieces,
            "name": p_names,
            "cell_id": p_cell_ids,
            "lat": p_lats,
            "lon": p_lons,
            "has_86yr_baseline": in_coverage_p,
            "nearest_station_id": [grid_ids[idx] if in_coverage_p[i] else None for i, idx in enumerate(indices_p)],
            "nearest_grid_point_id": [grid_ids[idx] if in_coverage_p[i] else None for i, idx in enumerate(indices_p)],
            "dist_to_station_km": np.round(arc_dists_p, 3),
            "dist_to_grid_point_km": np.round(arc_dists_p, 3)
        })
        pieces_mapping.to_csv(output_pieces_mapping, index=False)
        p_cov = int(in_coverage_p.sum())
        print(f"Rail pieces in grid coverage: {p_cov:,} / {total_pieces:,} ({p_cov/total_pieces*100:.1f}%)")
        print(f"Saved {output_pieces_mapping}")

    print(f"\nStep 2 completed in {time.time() - start_time:.2f}s")
    print("=" * 70)


if __name__ == "__main__":
    map_cells_and_pieces()
