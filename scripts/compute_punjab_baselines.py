#!/usr/bin/env python3
"""
Step 1: Single-Pass Station Baseline Extraction
ThermoRail Hybrid Risk Engine & Historical Baseline Integration

Ingests the unified 1940-2026 ERA5 Punjab dataset, extracts the month,
and computes vectorized statistical baselines per (station_id, month):
- air_mean_86yr (mu)
- air_std_86yr (sigma)
- air_p90_86yr
- air_p95_86yr
- air_p99_86yr

Outputs: punjab_station_baselines.csv
Includes guard rails to catch and raise an error if any std is zero or nulls exist.
"""

import sys
import os
import time
import psutil
import pandas as pd
import numpy as np


def get_memory_usage_mb():
    """Returns current process RSS memory in MB."""
    process = psutil.Process(os.getpid())
    return process.memory_info().rss / (1024 * 1024)


def ensure_dataset_exists():
    """Ensures punjab_temperature_1940_2026.parquet and punjab_stations.csv exist."""
    parquet_path = "punjab_temperature_1940_2026.parquet"
    stations_path = "punjab_stations.csv"
    excel_path = "ERA5_Daily_Compiled_1940_2026_Full.xlsx"

    if os.path.exists(parquet_path) and os.path.exists(stations_path):
        return

    print("Parquet/stations dataset not found. Extracting from Excel...")
    if not os.path.exists(excel_path):
        raise FileNotFoundError(f"Raw source Excel not found: {excel_path}")

    # Extract stations
    df_grid = pd.read_excel(excel_path, sheet_name="Grid_Coordinates", engine="calamine")
    stations = df_grid.rename(columns={
        "Grid_ID": "station_id",
        "Column_Name": "name",
        "Latitude": "lat",
        "Longitude": "lon"
    })
    stations.to_csv(stations_path, index=False)
    print(f"Generated {stations_path} ({len(stations)} stations)")

    # Extract continuous readings
    df = pd.read_excel(excel_path, sheet_name="1940_2026_Continuous", engine="calamine")
    df["timestamp"] = pd.to_datetime(df[["Year", "Month", "Day"]])
    station_cols = [c for c in df.columns if c not in ["Year", "Month", "Day", "timestamp"]]
    col_to_id = {c: c.split("_")[0] for c in station_cols}
    df = df.rename(columns=col_to_id)
    station_ids = list(col_to_id.values())

    df_long = df.melt(id_vars=["timestamp"], value_vars=station_ids, var_name="station_id", value_name="temperature")
    df_long["temperature"] = df_long["temperature"].astype("float32")
    df_long.to_parquet(parquet_path, index=False, engine="pyarrow")
    print(f"Generated {parquet_path} ({len(df_long):,} rows)")


def compute_baselines():
    start_time = time.time()
    print("=" * 65)
    print("ThermoRail: Step 1 - Single-Pass Station Baseline Extraction")
    print("=" * 65)
    print(f"Initial Memory: {get_memory_usage_mb():.1f} MB")

    ensure_dataset_exists()

    parquet_path = "punjab_temperature_1940_2026.parquet"
    output_csv = "punjab_station_baselines.csv"

    print(f"Loading unified dataset from {parquet_path}...")
    load_start = time.time()
    df = pd.read_parquet(parquet_path)
    load_time = time.time() - load_start
    row_count = len(df)
    print(f"Loaded {row_count:,} records in {load_time:.2f}s | Memory: {get_memory_usage_mb():.1f} MB")

    # 1. Extract month (1-12) from timestamp
    print("Extracting calendar month from timestamp...")
    df["month"] = df["timestamp"].dt.month.astype("int8")

    # 2. Vectorized grouping by ['station_id', 'month'] on temperature
    print("Grouping by ['station_id', 'month'] and calculating mean, std, p90, p95, p99...")
    agg_start = time.time()

    grouped = df.groupby(["station_id", "month"])["temperature"]

    # Compute mean and standard deviation in a single pass
    base_stats = grouped.agg(
        air_mean_86yr="mean",
        air_std_86yr="std"
    )

    # Compute exact percentiles
    p90 = grouped.quantile(0.90)
    p95 = grouped.quantile(0.95)
    p99 = grouped.quantile(0.99)

    baselines = base_stats.assign(
        air_p90_86yr=p90,
        air_p95_86yr=p95,
        air_p99_86yr=p99
    ).reset_index()

    agg_time = time.time() - agg_start
    print(f"Aggregation completed in {agg_time:.2f}s | Result rows: {len(baselines):,}")

    # Guard Rails
    print("Executing data integrity guard rails...")

    # Check for null values
    null_counts = baselines.isnull().sum()
    total_nulls = null_counts.sum()
    if total_nulls > 0:
        error_msg = f"GUARD RAIL VIOLATION: Found {total_nulls} null values in baselines lookup:\n{null_counts}"
        print(f"ERROR: {error_msg}", file=sys.stderr)
        raise ValueError(error_msg)

    # Check for zero standard deviation
    zero_std = (baselines["air_std_86yr"] <= 0).sum()
    if zero_std > 0:
        error_msg = f"GUARD RAIL VIOLATION: Found {zero_std} stations with standard deviation <= 0."
        print(f"ERROR: {error_msg}", file=sys.stderr)
        raise ValueError(error_msg)

    print(f"PASS: Zero nulls detected across all {len(baselines)} rows.")
    print(f"PASS: All {len(baselines)} standard deviations are strictly positive.")

    # 4. Save to static lookup table
    baselines.to_csv(output_csv, index=False)
    file_size_kb = os.path.getsize(output_csv) / 1024
    print(f"Saved static lookup table to {output_csv} ({file_size_kb:.1f} KB)")

    total_time = time.time() - start_time
    print("=" * 65)
    print(f"Execution Summary: Processed {row_count:,} rows -> {len(baselines)} baselines in {total_time:.2f}s")
    print(f"Peak Memory Usage: {get_memory_usage_mb():.1f} MB")
    print("=" * 65)
    return baselines


if __name__ == "__main__":
    compute_baselines()

