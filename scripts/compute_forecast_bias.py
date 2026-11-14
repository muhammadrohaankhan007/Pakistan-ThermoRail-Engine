#!/usr/bin/env python3
"""
Pakistan ThermoRail: Comprehensive Cross-Model Forecast Bias Audit & Estimation
Branch: bias-correction

Computes:
1. Mean bias across all 515 Punjab rail cells between Open-Meteo Operational Forecast Model
   (Historical Forecast API) and Copernicus ERA5 Reanalysis over April 1 - September 24, 2026 (177 days).
   bias = T_forecast_mean - T_ERA5_mean
   Saves: forecast_bias_by_cell.csv
2. Out-of-sample validation test:
   - Fit on April 1 - July 31, 2026 (122 days)
   - Test on August 1 - September 24, 2026 (55 days)
   - Evaluates residual bias and error (MAE / RMSE) before vs after per corridor point and overall.
3. Fallback cells (272 cells) comparison:
   - Compares 2026 forecast max vs archive summer max (air_max_c).
"""

import sys
import os
import json
import time
import math
import datetime
import numpy as np
import pandas as pd
import requests

HIST_FORECAST_URL = "https://historical-forecast-api.open-meteo.com/v1/forecast"
BATCH_SIZE = 25
START_DATE = "2026-04-01"
END_DATE = "2026-09-24"
SPLIT_DATE = "2026-07-31"  # Train: April-July (122 days), Test: August-September (55 days)

CORRIDOR_10_PTS = ["G009", "G068", "G172", "G203", "G253", "G304", "G353", "G398", "G430", "G499"]


def fetch_historical_forecast_batches(cells_df, cache_file="historical_forecast_cache.json"):
    """
    Fetches daily mean and max temperature from Open-Meteo Historical Forecast API for given cells.
    Caches results incrementally to disk after every batch.
    """
    total = len(cells_df)
    results = {}

    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                cached = json.load(f)
            # Verify cached format
            missing = [cid for cid in cells_df["cell_id"] if cid not in cached]
            if not missing:
                print(f"Loaded all {total} cells from {cache_file}.")
                return cached
            else:
                print(f"Cache partially present ({len(cached)}/{total}). Resuming from remaining {len(missing)} cells...")
                results = cached
        except Exception as e:
            print(f"Failed to read cache {cache_file}: {e}. Starting fresh...")

    total_batches = math.ceil(total / BATCH_SIZE)
    print(f"Fetching Historical Forecast API for {total} cells ({START_DATE} to {END_DATE})...")

    for b in range(total_batches):
        start_idx = b * BATCH_SIZE
        end_idx = min(start_idx + BATCH_SIZE, total)
        sub_df = cells_df.iloc[start_idx:end_idx]

        # Filter out cells already cached
        needed_sub = sub_df[~sub_df["cell_id"].isin(results)]
        if needed_sub.empty:
            continue

        lats = needed_sub["api_lat"].tolist()
        lons = needed_sub["api_lon"].tolist()
        cell_ids = needed_sub["cell_id"].tolist()

        params = {
            "latitude": lats,
            "longitude": lons,
            "start_date": START_DATE,
            "end_date": END_DATE,
            "daily": ["temperature_2m_mean", "temperature_2m_max"],
            "timezone": "auto"
        }

        success = False
        for attempt in range(6):
            try:
                resp = requests.get(HIST_FORECAST_URL, params=params, timeout=40)
                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data, dict):
                        data = [data]

                    for i, loc in enumerate(data):
                        cid = cell_ids[i]
                        d = loc.get("daily", {})
                        dates = d.get("time", [])
                        means = d.get("temperature_2m_mean", [])
                        maxes = d.get("temperature_2m_max", [])
                        results[cid] = {
                            "dates": dates,
                            "daily_mean_c": means,
                            "daily_max_c": maxes
                        }
                    success = True
                    break
                elif resp.status_code == 429:
                    # Open-Meteo rate limit window resets within ~30-60s
                    wait_sec = 20.0 if attempt == 0 else (35.0 if attempt == 1 else 60.0)
                    print(f"Batch {b + 1} HTTP 429 (rate limit), backing off {wait_sec:.0f}s (attempt {attempt + 1}/6)...", flush=True)
                    time.sleep(wait_sec)
                else:
                    wait_sec = 5.0 * (attempt + 1)
                    print(f"Batch {b + 1} HTTP {resp.status_code}, retrying in {wait_sec:.0f}s...", flush=True)
                    time.sleep(wait_sec)
            except Exception as ex:
                wait_sec = 5.0 * (attempt + 1)
                print(f"Batch {b + 1} attempt {attempt + 1} error: {ex}, retrying in {wait_sec:.0f}s...", flush=True)
                time.sleep(wait_sec)

        if not success:
            raise RuntimeError(f"Failed to fetch batch {b + 1}/{total_batches} from Historical Forecast API.")

        # Persist incremental progress immediately
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(results, f)

        print(f"Fetched batch {b + 1}/{total_batches} ({len(results)}/{total} cells cached).", flush=True)
        time.sleep(2.0)  # Safe spacing between calls to stay within minute quotas

    print(f"Saved complete forecast data to {cache_file}.")
    return results


def run_bias_analysis():
    print("=" * 80)
    print("Pakistan ThermoRail: Forecast Bias Analysis & Out-of-Sample Validation")
    print(f"Date Range: {START_DATE} to {END_DATE} (177 days)")
    print("=" * 80)

    # Load mapping
    df_cells = pd.read_csv("cell_grid_mapping.csv")
    punjab_cells = df_cells[df_cells["in_grid_coverage"] == True].copy()
    fallback_cells = df_cells[df_cells["in_grid_coverage"] == False].copy()
    print(f"Punjab Cells: {len(punjab_cells)} | Fallback Cells: {len(fallback_cells)}")

    # Load ERA5 2026 data
    print("Loading ERA5 reanalysis temperatures from punjab_temperature_1940_2026.parquet...")
    df_hist = pd.read_parquet("punjab_temperature_1940_2026.parquet")
    df_2026 = df_hist[
        (df_hist["timestamp"] >= START_DATE) & (df_hist["timestamp"] <= END_DATE)
    ].copy()
    df_2026["date"] = df_2026["timestamp"].dt.strftime("%Y-%m-%d")
    era5_lookup = {(r["station_id"], r["date"]): float(r["temperature"]) for _, r in df_2026.iterrows()}
    print(f"Loaded {len(era5_lookup):,} ERA5 daily mean values across {df_2026['station_id'].nunique()} stations.")

    # Load baseline std for sigma conversions
    df_base = pd.read_parquet("punjab_grid_point_baselines.parquet")
    col_std = "std_daily_mean_c" if "std_daily_mean_c" in df_base.columns else "std_daily_max_c"
    warm_stds = df_base[
        (df_base["day_of_year"] >= 91) & (df_base["day_of_year"] <= 267)
    ].groupby("grid_point_id")[col_std].mean().to_dict()

    # Load station metadata
    st_df = pd.read_csv("punjab_stations.csv").set_index("station_id")

    # Fetch / load Historical Forecast data for all 787 cells
    forecast_data = fetch_historical_forecast_batches(df_cells, cache_file="historical_forecast_cache.json")

    # =========================================================================
    # Part 1: Compute Per-Cell Bias Table (515 Punjab Cells)
    # =========================================================================
    print("\n--- Part 1: Computing Per-Cell Bias across 515 Punjab Cells ---")
    cell_bias_summary = []
    all_evaluations = []

    for _, row in punjab_cells.iterrows():
        cid = row["cell_id"]
        lat = float(row["api_lat"])
        lon = float(row["api_lon"])
        pt_id = row["nearest_grid_point_id"]

        f_entry = forecast_data.get(cid, {})
        dates = f_entry.get("dates", [])
        f_means = f_entry.get("daily_mean_c", [])

        diffs = []
        evals_for_cell = []
        for dt_str, f_mean in zip(dates, f_means):
            if f_mean is not None and (pt_id, dt_str) in era5_lookup:
                e_mean = era5_lookup[(pt_id, dt_str)]
                gap = f_mean - e_mean  # Model - ERA5
                diffs.append(gap)
                evals_for_cell.append({
                    "cell_id": cid,
                    "nearest_grid_point_id": pt_id,
                    "date": dt_str,
                    "f_mean": f_mean,
                    "e_mean": e_mean,
                    "gap": gap
                })

        all_evaluations.extend(evals_for_cell)

        if diffs:
            pt_sigma = warm_stds.get(pt_id, 2.5)
            mean_b = float(np.mean(diffs))
            med_b = float(np.median(diffs))
            std_b = float(np.std(diffs))
            mean_b_sig = mean_b / pt_sigma if pt_sigma > 0 else 0.0

            cell_bias_summary.append({
                "cell_id": cid,
                "lat": round(lat, 5),
                "lon": round(lon, 5),
                "nearest_grid_point_id": pt_id,
                "start_date": dates[0] if dates else START_DATE,
                "end_date": dates[-1] if dates else END_DATE,
                "n_days": len(diffs),
                "mean_bias_c": round(mean_b, 4),
                "median_bias_c": round(med_b, 4),
                "std_bias_c": round(std_b, 4),
                "mean_bias_sigma": round(mean_b_sig, 4)
            })

    df_cell_bias = pd.DataFrame(cell_bias_summary)
    df_cell_bias.to_csv("forecast_bias_by_cell.csv", index=False)
    print(f"Exported per-cell bias table to forecast_bias_by_cell.csv ({len(df_cell_bias)} rows).")

    # Overall 515 Punjab cells summary
    overall_mean_bias = float(df_cell_bias["mean_bias_c"].mean())
    overall_median_bias = float(df_cell_bias["median_bias_c"].median())
    overall_sigma_bias = float(df_cell_bias["mean_bias_sigma"].mean())
    pct_cool = float(np.mean(df_cell_bias["mean_bias_c"] < 0) * 100)

    print(f"\nOverall 515 Punjab Cells Summary (177 Days):")
    print(f"  Total Day-Cell Evaluations: {len(all_evaluations):,}")
    print(f"  Mean Bias (Model - ERA5):   {overall_mean_bias:+.3f} °C ({overall_sigma_bias:+.3f} σ)")
    print(f"  Median Bias:                {overall_median_bias:+.3f} °C")
    print(f"  Cells with Cool Bias (< 0): {pct_cool:.1f}% ({int(pct_cool*5.15)} / 515)")

    # =========================================================================
    # Part 2: Out-of-Sample Validation Test (Train: Apr-Jul, Test: Aug-Sep)
    # =========================================================================
    print("\n--- Part 2: Out-of-Sample Validation Test ---")
    print(f"Train Period: {START_DATE} to {SPLIT_DATE} (122 calendar days)")
    print(f"Test Period:  2026-08-01 to {END_DATE} (55 calendar days)")

    df_evals = pd.DataFrame(all_evaluations)
    df_evals["date_dt"] = pd.to_datetime(df_evals["date"])

    train_mask = df_evals["date"] <= SPLIT_DATE
    test_mask = df_evals["date"] > SPLIT_DATE

    df_train = df_evals[train_mask]
    df_test = df_evals[test_mask].copy()

    # Fit per-cell bias on training set:
    train_bias_by_cell = df_train.groupby("cell_id")["gap"].mean().to_dict()

    # Apply correction to test set: T_corrected = T_forecast - bias_train
    # residual_raw = f_mean - e_mean (which is gap)
    # residual_corr = (f_mean - bias_train) - e_mean = gap - bias_train
    df_test["bias_train"] = df_test["cell_id"].map(train_bias_by_cell)
    df_test["res_raw"] = df_test["gap"]
    df_test["res_corr"] = df_test["gap"] - df_test["bias_train"]

    # Overall test metrics
    raw_mean_test = float(df_test["res_raw"].mean())
    corr_mean_test = float(df_test["res_corr"].mean())
    raw_mae_test = float(df_test["res_raw"].abs().mean())
    corr_mae_test = float(df_test["res_corr"].abs().mean())
    raw_rmse_test = float(np.sqrt(np.mean(df_test["res_raw"]**2)))
    corr_rmse_test = float(np.sqrt(np.mean(df_test["res_corr"]**2)))

    print(f"\nOverall Out-of-Sample Test Results (All 515 Cells, Aug-Sep, {len(df_test):,} evaluations):")
    print(f"  Mean Bias:      Raw = {raw_mean_test:+.3f} °C  -->  Corrected = {corr_mean_test:+.3f} °C (Reduction: {abs(raw_mean_test) - abs(corr_mean_test):+.3f} °C)")
    print(f"  MAE:            Raw = {raw_mae_test:.3f} °C  -->  Corrected = {corr_mae_test:.3f} °C (Δ: {corr_mae_test - raw_mae_test:+.3f} °C)")
    print(f"  RMSE:           Raw = {raw_rmse_test:.3f} °C  -->  Corrected = {corr_rmse_test:.3f} °C (Δ: {corr_rmse_test - raw_rmse_test:+.3f} °C)")

    # Corridor 10 Points Breakdown in Test Period
    print("\nCorridor 10 Grid Points: Out-of-Sample Test Performance (August - September 2026):")
    print(f"{'Point':6} | {'Nearest City':20} | {'Train Bias':10} | {'Raw Test':10} | {'Corr Test':10} | {'Raw MAE':8} | {'Corr MAE':8} | {'Shrunk?'}")
    print("-" * 95)

    corridor_results = []
    for pt in CORRIDOR_10_PTS:
        pt_lat = float(st_df.loc[pt, "lat"])
        pt_lon = float(st_df.loc[pt, "lon"])
        pt_name = st_df.loc[pt, "name"]

        # Fetch or get historical forecast at exact grid point coordinates
        try:
            pt_resp = requests.get(HIST_FORECAST_URL, params={
                "latitude": pt_lat,
                "longitude": pt_lon,
                "start_date": START_DATE,
                "end_date": END_DATE,
                "daily": ["temperature_2m_mean"],
                "timezone": "auto"
            }, timeout=25).json()
            pt_daily = pt_resp.get("daily", {})
            p_dates = pt_daily.get("time", [])
            p_means = pt_daily.get("temperature_2m_mean", [])

            p_rows = []
            for dt_str, m_val in zip(p_dates, p_means):
                if (pt, dt_str) in era5_lookup and m_val is not None:
                    e_val = era5_lookup[(pt, dt_str)]
                    p_rows.append({"date": dt_str, "f": m_val, "e": e_val, "gap": m_val - e_val})

            df_p = pd.DataFrame(p_rows)
            p_train = df_p[df_p["date"] <= SPLIT_DATE]
            p_test = df_p[df_p["date"] > SPLIT_DATE].copy()

            train_b = float(p_train["gap"].mean())
            p_test["raw_res"] = p_test["gap"]
            p_test["corr_res"] = p_test["gap"] - train_b

            raw_test_b = float(p_test["raw_res"].mean())
            corr_test_b = float(p_test["corr_res"].mean())
            raw_mae = float(p_test["raw_res"].abs().mean())
            corr_mae = float(p_test["corr_res"].abs().mean())
            shrunk = abs(corr_test_b) < abs(raw_test_b)

            corridor_results.append({
                "point": pt,
                "name": pt_name,
                "train_bias": round(train_b, 2),
                "raw_test_bias": round(raw_test_b, 2),
                "corr_test_bias": round(corr_test_b, 2),
                "raw_mae": round(raw_mae, 2),
                "corr_mae": round(corr_mae, 2),
                "shrunk": shrunk
            })
            shrunk_str = "YES" if shrunk else "NO"
            print(f"{pt:6} | {pt_name:20} | {train_b:+9.2f}C | {raw_test_b:+9.2f}C | {corr_test_b:+9.2f}C | {raw_mae:7.2f}C | {corr_mae:7.2f}C | {shrunk_str}")
        except Exception as ex:
            print(f"Error evaluating {pt}: {ex}")

    # =========================================================================
    # Part 3: Fallback Cells (272 Cells) Audit
    # =========================================================================
    print("\n--- Part 3: Fallback Cells (272 Cells in Sindh & Balochistan) Audit ---")
    fallback_records = []
    for _, row in fallback_cells.iterrows():
        cid = row["cell_id"]
        hist_max = float(row["air_max_c"]) if pd.notnull(row["air_max_c"]) else 42.0
        f_entry = forecast_data.get(cid, {})
        maxes = [v for v in f_entry.get("daily_max_c", []) if v is not None]
        if maxes:
            f_peak_max = max(maxes)
            diff_to_archive = f_peak_max - hist_max
            fallback_records.append({
                "cell_id": cid,
                "lat": float(row["api_lat"]),
                "lon": float(row["api_lon"]),
                "hist_summer_max": hist_max,
                "forecast_2026_max": f_peak_max,
                "diff_to_archive": diff_to_archive
            })

    df_fb = pd.DataFrame(fallback_records)
    print(f"Evaluated {len(df_fb)} fallback cells:")
    print(f"  Archive Summer Max:       Mean = {df_fb['hist_summer_max'].mean():.2f} °C, Max = {df_fb['hist_summer_max'].max():.2f} °C")
    print(f"  2026 Forecast Season Max: Mean = {df_fb['forecast_2026_max'].mean():.2f} °C, Max = {df_fb['forecast_2026_max'].max():.2f} °C")
    print(f"  Mean Margin (2026 - Arch):{df_fb['diff_to_archive'].mean():+.2f} °C")
    print(f"  Cells where 2026 Max < Archive Max: {(df_fb['diff_to_archive'] < 0).mean()*100:.1f}% ({(df_fb['diff_to_archive'] < 0).sum()} / {len(df_fb)})")

    return {
        "df_cell_bias": df_cell_bias,
        "overall_mean_bias": overall_mean_bias,
        "overall_median_bias": overall_median_bias,
        "raw_mean_test": raw_mean_test,
        "corr_mean_test": corr_mean_test,
        "raw_mae_test": raw_mae_test,
        "corr_mae_test": corr_mae_test,
        "raw_rmse_test": raw_rmse_test,
        "corr_rmse_test": corr_rmse_test,
        "corridor_results": corridor_results,
        "df_fb": df_fb
    }


if __name__ == "__main__":
    run_bias_analysis()
