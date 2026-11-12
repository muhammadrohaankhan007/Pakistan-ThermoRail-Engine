#!/usr/bin/env python3
"""
Step 1: Grid-Point Daily Maximum Baseline Extraction & Calibration Check
Pakistan ThermoRail - Climatological Baseline Engine (1991-2020 WMO Normal)

Vectorized extraction of daily maximum temperature baselines from ERA5 reanalysis:
1. Filters unified dataset to 1991-2020 (WMO standard 30-year normal period).
2. Computes daily maximum baseline per grid point and day-of-year (DOY 1-366):
   - Centered +/-7 day moving window (15-day climatological sample per DOY).
   - Mean of daily max (mu)
   - Standard deviation of daily max (sigma)
3. Computes each grid point's May-June 95th percentile of daily max (for the heat risk gate).
4. Data Integrity Guard Rails:
   - Asserts zero null values across all grid points and days of year.
   - Asserts all standard deviations are strictly positive (sigma > 0).
5. Statistical Calibration Check:
   - Evaluates 30 random past historical days from 1991-2020 against the DOY baselines.
   - Reports the empirical share of points at z >= 2.0 (expected ~2%) and z >= 1.0 (expected ~16%).
   - Flags an error if statistics deviate substantially from standard normal theory.
"""

import sys
import os
import time
import psutil
import numpy as np
import pandas as pd


def get_memory_usage_mb():
    """Returns current process RSS memory in MB."""
    process = psutil.Process(os.getpid())
    return process.memory_info().rss / (1024 * 1024)


def ensure_source_parquet():
    """Confirms source parquet exists."""
    parquet_path = "punjab_temperature_1940_2026.parquet"
    if not os.path.exists(parquet_path):
        raise FileNotFoundError(f"Missing required source dataset: {parquet_path}")
    return parquet_path


def compute_doy_baselines():
    start_time = time.time()
    print("=" * 70)
    print("ThermoRail: Step 1 - Grid-Point Daily Max Baselines (1991-2020 Normal)")
    print("=" * 70)
    print(f"Initial Memory: {get_memory_usage_mb():.1f} MB")

    parquet_path = ensure_source_parquet()
    output_baselines_csv = "punjab_grid_point_baselines.csv"
    output_baselines_parquet = "punjab_grid_point_baselines.parquet"
    output_gate_p95_csv = "punjab_grid_point_gate_p95.csv"

    # 1. Ingest dataset and filter to 1991-2020 baseline window
    print("Loading 1940-2026 parquet and filtering to 1991-2020 (30-year normal)...")
    t0 = time.time()
    df = pd.read_parquet(parquet_path)
    df["year"] = df["timestamp"].dt.year
    df_30 = df[(df["year"] >= 1991) & (df["year"] <= 2020)].copy()
    print(f"Loaded {len(df_30):,} records for 1991-2020 in {time.time() - t0:.2f}s")

    # Rename station_id to grid_point_id for consistent terminology
    df_30 = df_30.rename(columns={"station_id": "grid_point_id"})

    # 2. Pivot to date x grid_point_id matrix for fast vectorization
    print("Pivoting daily records to date x grid point matrix...")
    pivot = df_30.pivot(index="timestamp", columns="grid_point_id", values="temperature")
    grid_point_ids = pivot.columns.tolist()
    dates = pivot.index
    doys = dates.dayofyear.values  # 1 to 366
    mat = pivot.values  # Shape: (10958, num_grid_points)
    num_grid_points = mat.shape[1]
    print(f"Matrix shape: {mat.shape} (10,958 calendar days x {num_grid_points} grid points)")

    # 3. Compute DOY baselines with +/-7 day window (15-day centered window)
    print("Computing mean and std of daily max per day-of-year (+/-7 day circular window)...")
    t_doy = time.time()
    means = np.zeros((366, num_grid_points), dtype=np.float32)
    stds = np.zeros((366, num_grid_points), dtype=np.float32)

    for d in range(1, 367):
        # Circular difference on 365 days
        diff = np.abs(doys - d)
        diff = np.minimum(diff, 365 - diff)
        mask = diff <= 7
        sub = mat[mask, :]
        means[d - 1, :] = sub.mean(axis=0)
        stds[d - 1, :] = sub.std(axis=0, ddof=1)

    print(f"Calculated 366 DOY baselines in {time.time() - t_doy:.2f}s")

    # 4. Guard Rails
    print("Executing statistical integrity guard rails...")
    if np.isnan(means).any():
        raise ValueError("GUARD RAIL FAILURE: NaN found in baseline means!")
    if np.isnan(stds).any():
        raise ValueError("GUARD RAIL FAILURE: NaN found in baseline standard deviations!")
    if (stds <= 0).any():
        min_std = stds.min()
        raise ValueError(f"GUARD RAIL FAILURE: Found standard deviation <= 0 (min: {min_std})!")

    print(f"PASS: Zero null values across all {366 * num_grid_points:,} baseline values.")
    print(f"PASS: All standard deviations are strictly positive (min std: {stds.min():.3f} C).")

    # 5. Compute May-June 95th percentile of daily max per grid point (for the heat gate)
    print("Computing May-June 95th percentile of daily max per grid point (for heat risk gate)...")
    mj_mask = df_30["timestamp"].dt.month.isin([5, 6])
    mj_df = df_30[mj_mask]
    mj_p95 = mj_df.groupby("grid_point_id")["temperature"].quantile(0.95).reset_index()
    mj_p95 = mj_p95.rename(columns={"temperature": "may_june_p95_c"})
    mj_p95.to_csv(output_gate_p95_csv, index=False)
    print(f"Saved May-June P95 thresholds to {output_gate_p95_csv} ({len(mj_p95)} grid points)")

    # 6. Save tabular baseline lookups
    baseline_records = []
    for d in range(1, 367):
        for idx, g_id in enumerate(grid_point_ids):
            baseline_records.append({
                "grid_point_id": g_id,
                "day_of_year": d,
                "mean_daily_max_c": round(float(means[d - 1, idx]), 3),
                "std_daily_max_c": round(float(stds[d - 1, idx]), 3)
            })

    df_baselines = pd.DataFrame(baseline_records)
    df_baselines.to_csv(output_baselines_csv, index=False)
    df_baselines.to_parquet(output_baselines_parquet, index=False, engine="pyarrow")
    print(f"Saved baseline lookup tables: {output_baselines_csv} and {output_baselines_parquet}")

    # 7. Calibration Check: Score 30 random past days against the 1991-2020 baseline
    print("\n" + "=" * 70)
    print("ThermoRail: Statistical Calibration Check (30 Random Historical Days)")
    print("=" * 70)
    np.random.seed(42)
    sample_indices = np.random.choice(len(dates), size=30, replace=False)
    sample_dates = dates[sample_indices]

    z_scores = []
    for idx in sample_indices:
        d = doys[idx]
        actual_t = mat[idx, :]
        mu = means[d - 1, :]
        sigma = stds[d - 1, :]
        z = (actual_t - mu) / sigma
        z_scores.extend(z)

    z_arr = np.array(z_scores)
    total_evals = len(z_arr)
    share_ge_2 = float(np.mean(z_arr >= 2.0) * 100)
    share_ge_1 = float(np.mean(z_arr >= 1.0) * 100)
    share_ge_05 = float(np.mean(z_arr >= 0.5) * 100)
    share_lt_05 = float(np.mean(z_arr < 0.5) * 100)

    print(f"Total calibration evaluations: {total_evals:,} (30 days x {num_grid_points} grid points)")
    print(f"  * Share at z >= 2.0 (strong anomaly):   {share_ge_2:6.2f}%  (Target: ~2%, Normal theory: 2.28%)")
    print(f"  * Share at z >= 1.0 (elevated anomaly): {share_ge_1:6.2f}%  (Target: ~16%, Normal theory: 15.87%)")
    print(f"  * Share at z >= 0.5 (mild anomaly):     {share_ge_05:6.2f}%  (Target: ~31%, Normal theory: 30.85%)")
    print(f"  * Share at z <  0.5 (near normal):      {share_lt_05:6.2f}%  (Target: ~69%, Normal theory: 69.15%)")

    # Assert calibration sanity: if share at z >= 2.0 is > 10% or < 0.2%, or z >= 1.0 is > 30% or < 5%
    if share_ge_2 > 10.0 or share_ge_2 < 0.2:
        raise ValueError(f"CALIBRATION WARNING: share z >= 2.0 ({share_ge_2:.2f}%) deviates excessively from 2%!")
    if share_ge_1 > 30.0 or share_ge_1 < 5.0:
        raise ValueError(f"CALIBRATION WARNING: share z >= 1.0 ({share_ge_1:.2f}%) deviates excessively from 16%!")

    print("\nCalibration check PASSED: Empirical distributions match standard normal baseline expectations.")
    print(f"Total Execution Time: {time.time() - start_time:.2f}s")
    print("=" * 70)

    return {
        "share_ge_2": share_ge_2,
        "share_ge_1": share_ge_1,
        "share_ge_05": share_ge_05,
        "share_lt_05": share_lt_05,
        "num_grid_points": num_grid_points
    }


if __name__ == "__main__":
    compute_doy_baselines()
