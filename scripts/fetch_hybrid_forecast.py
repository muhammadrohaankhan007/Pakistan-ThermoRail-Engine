#!/usr/bin/env python3
"""
Step 4: Hybrid Risk & Live Daily Forecast Engine (Revised Directive 1 & 2)
Pakistan ThermoRail - Live Operational Anomaly Pipeline

Produces a lightweight daily forecast.json keyed by cell_id:
1. Baselines from 24-HOUR DAILY MEAN temperature (1991-2020 WMO normal period):
   - Requests hourly temperature_2m and daily temperature_2m_max from Open-Meteo.
   - Computes each local day's 24-hour mean temperature.
   - Compares each forecast day's daily mean to that day's DOY baseline (+/-7 day window).
   - Computes daily Z-scores: Z = (T_forecast_mean - mu) / sigma with NO empirical offset.
   - Cell score = max Z over the 7-day forecast window; stores peak_day, forecast_mean_c, and forecast_max_c.
2. Heat Risk Gate (documented parameter: GATE_C = 3.0 deg C):
   - A cell is ONLY flagged if Z >= threshold AND forecast daily mean >= (grid_point_may_june_p95_daily_mean - GATE_C).
   - If below this threshold, the cell is classified as 'near_normal' to suppress mild/winter false alarms.
3. Fallback Engine (outside Punjab grid point coverage):
   - margin = forecast daily max minus cell's May-June maximum (air_max_c from cell_heat.csv).
   - Tiered by margin relative to summer records (arbitrary stopgap cutoffs: 0 C, -2 C, -5 C); marked engine = 'fallback'.
4. Terminology:
   - Uses 'grid point' (never 'station').
   - Tier labels: strong_anomaly, elevated_anomaly, mild_anomaly, near_normal (no 'critical' or 'safe').
5. Output:
   - Writes web/public/data/forecast.json (and forecast.json at root), ~65 KB, keyed by cell_id.
   - Retains forecast daily max as a secondary physical display value for popups.
"""

import sys
import os
import time
import json
import math
import psutil
import datetime
import requests
import pandas as pd
import numpy as np

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
BATCH_SIZE = 50
GATE_C = 3.0  # Documented parameter: forecast daily mean must come within GATE_C of May-June P95 daily mean


def get_memory_usage_mb():
    """Returns current process RSS memory in MB."""
    process = psutil.Process(os.getpid())
    return process.memory_info().rss / (1024 * 1024)


def fetch_live_daily_forecasts(cells_df, cache_file="live_forecast_cache.json"):
    """
    Fetches 7-day hourly and daily temperature forecasts for all 787 cell centroids.
    Extracts 24-hour daily means and daily maximums.
    Uses batching of 50 locations per call with caching and exponential retry backoff.
    """
    total_cells = len(cells_df)
    results = {}

    # Check cache if valid (< 6 hours old)
    if os.path.exists(cache_file):
        file_age_hours = (time.time() - os.path.getmtime(cache_file)) / 3600.0
        if file_age_hours < 6.0:
            print(f"Loading cached live forecast from {cache_file} (age: {file_age_hours:.1f} hours)...")
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    cached_data = json.load(f)
                # Verify schema has daily_mean_c
                sample_val = next(iter(cached_data.values())) if cached_data else {}
                if len(cached_data) == total_cells and "daily_mean_c" in sample_val:
                    return cached_data
            except Exception as e:
                print(f"Cache load failed: {e}. Fetching fresh data...")

    print(f"Fetching fresh 7-day hourly & daily forecast from Open-Meteo for {total_cells} cells...")
    total_batches = math.ceil(total_cells / BATCH_SIZE)

    for b in range(total_batches):
        start_idx = b * BATCH_SIZE
        end_idx = min(start_idx + BATCH_SIZE, total_cells)
        sub_df = cells_df.iloc[start_idx:end_idx]

        lats = sub_df["api_lat"].tolist()
        lons = sub_df["api_lon"].tolist()
        cell_ids = sub_df["cell_id"].tolist()

        params = {
            "latitude": lats,
            "longitude": lons,
            "daily": ["temperature_2m_max", "temperature_2m_mean"],
            "hourly": ["temperature_2m"],
            "timezone": "auto",
            "forecast_days": 7
        }

        success = False
        for attempt in range(5):
            try:
                resp = requests.get(OPEN_METEO_URL, params=params, timeout=30)
                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data, dict):
                        data = [data]

                    for i, loc in enumerate(data):
                        c_id = cell_ids[i]
                        d = loc.get("daily", {})
                        dates = d.get("time", [])
                        max_temps = [v for v in d.get("temperature_2m_max", []) if v is not None]
                        api_daily_means = [v for v in d.get("temperature_2m_mean", []) if v is not None]

                        h = loc.get("hourly", {})
                        h_times = h.get("time", [])
                        h_temps = h.get("temperature_2m", [])

                        # Group hourly temperatures by date to compute precise 24-hr local means
                        day_hourly = {}
                        for t_str, temp in zip(h_times, h_temps):
                            if temp is not None:
                                day_key = t_str[:10]
                                day_hourly.setdefault(day_key, []).append(temp)

                        mean_temps = []
                        for dt_str in dates:
                            h_vals = day_hourly.get(dt_str, [])
                            if h_vals:
                                mean_temps.append(round(float(np.mean(h_vals)), 2))
                            else:
                                idx = len(mean_temps)
                                if idx < len(api_daily_means):
                                    mean_temps.append(float(api_daily_means[idx]))
                                elif idx < len(max_temps):
                                    mean_temps.append(float(max_temps[idx]) - 5.0)
                                else:
                                    mean_temps.append(25.0)

                        if dates and max_temps:
                            results[c_id] = {
                                "dates": dates,
                                "daily_max_c": max_temps,
                                "daily_mean_c": mean_temps
                            }
                        else:
                            # Fallback if specific cell returned empty
                            results[c_id] = {
                                "dates": [datetime.date.today().isoformat()],
                                "daily_max_c": [float(sub_df.iloc[i].get("air_max_c", 35.0))],
                                "daily_mean_c": [float(sub_df.iloc[i].get("air_max_c", 35.0)) - 6.0]
                            }
                    success = True
                    break
                elif resp.status_code == 429:
                    wait_sec = 4.0 * (attempt + 1)
                    print(f"Batch {b + 1} HTTP 429 (rate limit), backing off {wait_sec}s...")
                    time.sleep(wait_sec)
                else:
                    wait_sec = 2.0 * (attempt + 1)
                    print(f"Batch {b + 1} HTTP {resp.status_code}, retrying in {wait_sec}s...")
                    time.sleep(wait_sec)
            except Exception as ex:
                wait_sec = 3.0 * (attempt + 1)
                print(f"Batch {b + 1} attempt {attempt + 1} error: {ex}, retrying in {wait_sec}s...")
                time.sleep(wait_sec)

        if not success:
            error_msg = f"CRITICAL: Open-Meteo batch {b + 1}/{total_batches} failed after 5 retries. Aborting pipeline to prevent stale/corrupt deployment."
            print(error_msg, file=sys.stderr)
            raise RuntimeError(error_msg)

        time.sleep(0.35)  # Rate limit courtesy buffer

    print(f"Successfully retrieved forecasts for {len(results)} cells.")
    try:
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(results, f)
        print(f"Cached forecast responses to {cache_file}")
    except Exception as e:
        print(f"Failed to write cache: {e}")

    return results


def score_cell_forecast(cell_row, f_entry, base_lookup, gate_lookup, gate_c=GATE_C):
    """
    Evaluates a single cell's 7-day forecast against the baseline and heat risk gate.
    Used by both the live operational pipeline and the validation benchmark suite.
    """
    c_id = cell_row["cell_id"]
    in_cov = bool(cell_row["in_grid_coverage"])
    pt_id = cell_row["nearest_grid_point_id"] if in_cov else None
    dist_km = float(cell_row["dist_to_grid_point_km"]) if pd.notnull(cell_row["dist_to_grid_point_km"]) else None
    cell_hist_max = float(cell_row["air_max_c"]) if pd.notnull(cell_row["air_max_c"]) else 42.0

    dates = f_entry.get("dates", [])
    daily_maxes = f_entry.get("daily_max_c", [])
    daily_means = f_entry.get("daily_mean_c", [])

    if not dates or not daily_maxes or not daily_means:
        dates = [datetime.date.today().isoformat()]
        daily_maxes = [cell_hist_max]
        daily_means = [cell_hist_max - 6.0]

    if in_cov and pt_id and pt_id in gate_lookup:
        daily_z_scores = []
        for d_str, t_mean, t_max in zip(dates, daily_means, daily_maxes):
            try:
                dt = datetime.date.fromisoformat(d_str)
                doy = dt.timetuple().tm_yday
            except Exception:
                doy = 1
            mu, sigma = base_lookup.get((pt_id, doy), (t_mean, 2.0))
            z_day = (t_mean - mu) / sigma if sigma > 0 else 0.0
            daily_z_scores.append((z_day, d_str, t_mean, t_max))

        daily_z_scores.sort(key=lambda x: x[0], reverse=True)
        peak_z, peak_day, peak_mean, peak_max = daily_z_scores[0]
        max_forecast_max_c = max(daily_maxes)
        max_forecast_mean_c = max(daily_means)

        mj_p95_ref = gate_lookup[pt_id]
        gate_threshold = mj_p95_ref - gate_c
        gate_passed = max_forecast_mean_c >= gate_threshold

        if gate_passed:
            if peak_z >= 2.0:
                tier = "strong_anomaly"
            elif peak_z >= 1.2:
                tier = "elevated_anomaly"
            elif peak_z >= 0.5:
                tier = "mild_anomaly"
            else:
                tier = "near_normal"
        else:
            tier = "near_normal"

        return {
            "engine": "punjab_zscore",
            "grid_point_id": pt_id,
            "dist_to_grid_point_km": round(dist_km, 1) if dist_km is not None else None,
            "peak_day": peak_day,
            "forecast_mean_c": round(float(peak_mean), 1),
            "forecast_max_c": round(float(max_forecast_max_c), 1),
            "z": round(float(peak_z), 2),
            "margin": None,
            "gate_passed": bool(gate_passed),
            "tier": tier
        }, tier, "punjab_zscore"

    else:
        max_idx = int(np.argmax(daily_maxes))
        peak_day = dates[max_idx] if max_idx < len(dates) else dates[0]
        max_forecast_max_c = max(daily_maxes)
        peak_mean = daily_means[max_idx] if max_idx < len(daily_means) else (max_forecast_max_c - 5.0)
        margin = max_forecast_max_c - cell_hist_max

        if margin >= 0.0:
            tier = "strong_anomaly"
        elif margin >= -2.0:
            tier = "elevated_anomaly"
        elif margin >= -5.0:
            tier = "mild_anomaly"
        else:
            tier = "near_normal"

        return {
            "engine": "fallback",
            "grid_point_id": None,
            "dist_to_grid_point_km": round(dist_km, 1) if dist_km is not None else None,
            "peak_day": peak_day,
            "forecast_mean_c": round(float(peak_mean), 1),
            "forecast_max_c": round(float(max_forecast_max_c), 1),
            "z": None,
            "margin": round(float(margin), 1),
            "gate_passed": False,
            "tier": tier
        }, tier, "fallback"


def evaluate_forecast_dataset(df_cells, forecast_data, base_lookup, gate_lookup, gate_c=GATE_C):
    """
    Evaluates all cells in a dataset using score_cell_forecast.
    """
    cells_output = {}
    tier_counts = {
        "strong_anomaly": 0,
        "elevated_anomaly": 0,
        "mild_anomaly": 0,
        "near_normal": 0
    }
    engine_counts = {
        "punjab_zscore": 0,
        "fallback": 0
    }

    for _, cell_row in df_cells.iterrows():
        c_id = cell_row["cell_id"]
        f_entry = forecast_data.get(c_id, {})
        cell_dict, tier, engine = score_cell_forecast(cell_row, f_entry, base_lookup, gate_lookup, gate_c=gate_c)
        cells_output[c_id] = cell_dict
        tier_counts[tier] += 1
        engine_counts[engine] += 1

    return cells_output, tier_counts, engine_counts


def run_pipeline():
    start_time = time.time()
    print("=" * 70)
    print("ThermoRail: Step 4 - Hybrid Risk & Forecast Engine (Daily Mean / 1991-2020)")
    print("=" * 70)
    print(f"Initial Memory: {get_memory_usage_mb():.1f} MB")

    baselines_parquet = "punjab_grid_point_baselines.parquet"
    baselines_csv = "punjab_grid_point_baselines.csv"
    gate_csv = "punjab_grid_point_gate_p95.csv"
    cell_mapping_csv = "cell_grid_mapping.csv"
    output_forecast_json = "forecast.json"
    web_forecast_json = os.path.join("web", "public", "data", "forecast.json")

    # 1. Load baselines, gate thresholds, and cell mapping
    if os.path.exists(baselines_parquet):
        print(f"Loading 1991-2020 daily mean baselines from {baselines_parquet}...")
        df_base = pd.read_parquet(baselines_parquet)
    elif os.path.exists(baselines_csv):
        print(f"Loading 1991-2020 daily mean baselines from {baselines_csv}...")
        df_base = pd.read_csv(baselines_csv)
    else:
        raise FileNotFoundError(f"Missing baselines table ({baselines_parquet} or {baselines_csv}). Run Step 1 first.")

    if not os.path.exists(gate_csv):
        raise FileNotFoundError(f"Missing {gate_csv}. Run Step 1 first.")
    if not os.path.exists(cell_mapping_csv):
        raise FileNotFoundError(f"Missing {cell_mapping_csv}. Run Step 2 first.")

    # Determine column names for mean and std
    col_mean = "mean_daily_mean_c" if "mean_daily_mean_c" in df_base.columns else "mean_daily_max_c"
    col_std = "std_daily_mean_c" if "std_daily_mean_c" in df_base.columns else "std_daily_max_c"

    # Fast baseline lookup: (grid_point_id, day_of_year) -> (mean, std)
    base_lookup = {}
    for _, row in df_base.iterrows():
        base_lookup[(row["grid_point_id"], int(row["day_of_year"]))] = (
            float(row[col_mean]),
            float(row[col_std])
        )

    print(f"Loading May-June daily mean P95 gate thresholds from {gate_csv}...")
    df_gate = pd.read_csv(gate_csv)
    col_p95 = "may_june_p95_daily_mean_c" if "may_june_p95_daily_mean_c" in df_gate.columns else ("may_june_p95_c" if "may_june_p95_c" in df_gate.columns else df_gate.columns[1])
    gate_lookup = dict(zip(df_gate["grid_point_id"], df_gate[col_p95]))

    print(f"Loading cell-to-grid mapping from {cell_mapping_csv}...")
    df_cells = pd.read_csv(cell_mapping_csv)
    total_cells = len(df_cells)
    print(f"Loaded {total_cells} cells.")

    # 2. Fetch live 7-day hourly & daily forecasts
    forecast_data = fetch_live_daily_forecasts(df_cells)

    # 3. Evaluate each cell with hybrid scoring and heat gate
    print("\nEvaluating hybrid risk tiers and heat risk gate across all cells...")
    cells_output, tier_counts, engine_counts = evaluate_forecast_dataset(
        df_cells, forecast_data, base_lookup, gate_lookup, gate_c=GATE_C
    )

    # 4. Assemble final lightweight forecast payload
    now_utc = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    forecast_payload = {
        "metadata": {
            "title": "Pakistan ThermoRail - 7-Day Live Rail Heat Anomaly Forecast",
            "generated_at": now_utc,
            "climatological_variable": "24-hour daily mean temperature (temperature_2m)",
            "baseline_period": "1991-2020 WMO Standard Climatological Normal",
            "statistical_metric": "Daily mean Z-score relative to DOY baseline (+/-7 day window)",
            "heat_gate_parameter_c": GATE_C,
            "gate_rule": f"Flagged anomaly requires forecast daily mean >= (grid point May-June P95 daily mean - {GATE_C} deg C)",
            "gate_rationale": "Suppresses mild seasonal or winter alerts; piece must experience near-summer peak thermal conditions to trigger risk tiers",
            "fallback_note": "Non-Punjab corridors use arbitrary stopgap cutoffs (-2.0 C, -5.0 C) against 2026 summer maximum until 1991-2020 baselines are extended nationwide",
            "total_cells": total_cells,
            "engine_counts": engine_counts,
            "tier_summary": tier_counts
        },
        "cells": cells_output
    }

    # 5. Export lightweight JSON files
    os.makedirs(os.path.dirname(web_forecast_json), exist_ok=True)
    for p in [output_forecast_json, web_forecast_json]:
        with open(p, "w", encoding="utf-8") as f:
            json.dump(forecast_payload, f, indent=2)
        print(f"Exported lightweight forecast to {p} ({os.path.getsize(p) / 1024:.1f} KB)")

    total_time = time.time() - start_time
    print("\n" + "=" * 70)
    print("ThermoRail: Pipeline Execution Summary")
    print("=" * 70)
    print(f"Total Processed Cells: {total_cells}")
    print(f"  * Punjab Grid Z-Score Engine: {engine_counts['punjab_zscore']} cells")
    print(f"  * National Fallback Engine:   {engine_counts['fallback']} cells")
    print("\nTier Distribution:")
    for tier_name, count in tier_counts.items():
        pct = (count / total_cells) * 100
        print(f"  * {tier_name:18}: {count:4d} cells ({pct:5.1f}%)")
    print(f"\nExecution Duration: {total_time:.2f}s | Peak Memory: {get_memory_usage_mb():.1f} MB")
    print("=" * 70)

    return forecast_payload


if __name__ == "__main__":
    run_pipeline()
