#!/usr/bin/env python3
"""
Step 4: Hybrid Risk & Live Forecast Engine
ThermoRail Hybrid Risk Engine & Historical Baseline Integration

Builds the daily production execution pipeline:
1. Calls Open-Meteo Live Forecast API for 787 cell points (hourly temperature_2m and soil_temperature_0cm over 7 days).
2. Calculates 7-day max and 95th-percentile temperatures per cell.
3. Applies Hybrid Risk Scoring:
   - Punjab pieces (has_86yr_baseline == True):
     Z = (T_forecast - mu) / sigma relative to 86-year station baseline for current month.
     * Z >= +2.0        -> Tier 1 (Critical Anomaly)
     * +1.2 <= Z < +2.0 -> Tier 2 (High Anomaly)
     * +0.5 <= Z < +1.2 -> Tier 3 (Moderate Anomaly)
     * Z < +0.5         -> Tier 4 (Baseline / Low)
   - Non-Punjab pieces (has_86yr_baseline == False):
     National quantile percentile cuts using national baseline parameters.
4. Merges calculated properties into GeoJSON and outputs web/public/data/pk_rail_forecast_v3.geojson
   (and pk_rail_forecast_v3.geojson in project root).
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


def get_memory_usage_mb():
    """Returns current process RSS memory in MB."""
    process = psutil.Process(os.getpid())
    return process.memory_info().rss / (1024 * 1024)


def fetch_live_forecast_cells(cells_df, cache_file="live_forecast_cache.json"):
    """
    Fetches 7-day hourly temperature forecasts for all 787 cell centroids.
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
                if len(cached_data) == total_cells:
                    return cached_data
            except Exception as e:
                print(f"Cache load failed: {e}. Fetching fresh data...")

    print(f"Fetching fresh 7-day hourly forecast from Open-Meteo for {total_cells} cells...")
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
            "hourly": ["temperature_2m", "soil_temperature_0cm"],
            "forecast_days": 7
        }

        # Request with retries
        success = False
        for attempt in range(4):
            try:
                resp = requests.get(OPEN_METEO_URL, params=params, timeout=25)
                if resp.status_code == 200:
                    data = resp.json()
                    # Handle single location vs multiple
                    if isinstance(data, dict):
                        data = [data]

                    for i, loc in enumerate(data):
                        c_id = cell_ids[i]
                        h = loc.get("hourly", {})
                        air_temps = [v for v in h.get("temperature_2m", []) if v is not None]
                        soil_temps = [v for v in h.get("soil_temperature_0cm", []) if v is not None]

                        if air_temps:
                            air_max = float(np.max(air_temps))
                            air_p95 = float(np.percentile(air_temps, 95))
                        else:
                            air_max = float(sub_df.iloc[i].get("air_max_c", 40.0))
                            air_p95 = float(sub_df.iloc[i].get("air_p95_c", 38.0))

                        if soil_temps:
                            soil_max = float(np.max(soil_temps))
                            soil_p95 = float(np.percentile(soil_temps, 95))
                        else:
                            soil_max = float(sub_df.iloc[i].get("soil_max_c", 42.0))
                            soil_p95 = float(sub_df.iloc[i].get("soil_p95_c", 40.0))

                        results[c_id] = {
                            "air_max_c": round(air_max, 1),
                            "air_p95_c": round(air_p95, 1),
                            "soil_max_c": round(soil_max, 1),
                            "soil_p95_c": round(soil_p95, 1)
                        }

                    success = True
                    break
                else:
                    print(f"Warning: Batch {b + 1} attempt {attempt + 1} HTTP {resp.status_code}. Retrying...")
                    time.sleep(1.5 * (attempt + 1))
            except Exception as ex:
                print(f"Warning: Batch {b + 1} attempt {attempt + 1} error: {ex}. Retrying...")
                time.sleep(1.5 * (attempt + 1))

        if not success:
            print(f"Fallback to static cell heat for batch {b + 1}...")
            for _, r in sub_df.iterrows():
                results[r["cell_id"]] = {
                    "air_max_c": float(r["air_max_c"]),
                    "air_p95_c": float(r["air_p95_c"]),
                    "soil_max_c": float(r["soil_max_c"]),
                    "soil_p95_c": float(r["soil_p95_c"])
                }

        print(f"  Processed batch {b + 1}/{total_batches} ({len(results)}/{total_cells} cells)...")
        time.sleep(0.3)

    # Save to cache
    try:
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
        print(f"Cached forecast results to {cache_file}")
    except Exception as e:
        print(f"Cache write warning: {e}")

    return results


def run_hybrid_forecast_pipeline():
    start_time = time.time()
    print("=" * 65)
    print("ThermoRail: Step 4 - Hybrid Risk & Live Forecast Engine")
    print("=" * 65)
    print(f"Initial Memory: {get_memory_usage_mb():.1f} MB")

    geojson_in = "pk_rail_heat_v2.geojson"
    geojson_out_root = "pk_rail_forecast_v3.geojson"
    geojson_out_web = os.path.join("web", "public", "data", "pk_rail_forecast_v3.geojson")
    cells_csv = "cell_heat.csv"
    mapping_csv = "piece_station_mapping.csv"
    baselines_csv = "punjab_station_baselines.csv"

    # Verify input prerequisites
    for req in [geojson_in, cells_csv, mapping_csv, baselines_csv]:
        if not os.path.exists(req):
            raise FileNotFoundError(f"Missing required file {req}. Run prior steps first.")

    # 1. Load cell metadata and fetch/retrieve live 7-day forecast
    cells_df = pd.read_csv(cells_csv)
    print(f"Loaded {len(cells_df)} cells from {cells_csv}.")
    cell_forecasts = fetch_live_forecast_cells(cells_df)

    # 2. Load Station Baselines lookup
    baselines_df = pd.read_csv(baselines_csv)
    current_month = datetime.datetime.now().month
    print(f"Target forecast calendar month: {current_month} ({datetime.date(2000, current_month, 1).strftime('%B')})")

    month_baselines = baselines_df[baselines_df["month"] == current_month].set_index("station_id")
    print(f"Active Punjab station baselines for month {current_month}: {len(month_baselines)} stations.")

    # 3. Load Piece-to-Station Mapping
    mapping_df = pd.read_csv(mapping_csv)
    mapping_by_idx = mapping_df.set_index("piece_index")

    # 4. Load base GeoJSON features
    print(f"Loading input GeoJSON: {geojson_in}...")
    load_start = time.time()
    with open(geojson_in, "r", encoding="utf-8") as f:
        base_geojson = json.load(f)

    features = base_geojson["features"]
    total_features = len(features)
    print(f"Loaded {total_features:,} features in {time.time() - load_start:.2f}s | Memory: {get_memory_usage_mb():.1f} MB")

    # Calculate national percentile parameters for fallback (based on current 7-day cell forecast)
    all_forecast_air_p95 = [cell_forecasts[cid]["air_p95_c"] for cid in cell_forecasts if cid in cell_forecasts]
    national_p50 = float(np.percentile(all_forecast_air_p95, 50))
    national_p80 = float(np.percentile(all_forecast_air_p95, 80))
    national_p95 = float(np.percentile(all_forecast_air_p95, 95))
    print(f"National Forecast Quantile Thresholds (P50/P80/P95): {national_p50:.1f} / {national_p80:.1f} / {national_p95:.1f} °C")

    # 5. Hybrid Scoring Algorithm Loop
    print("Executing hybrid risk evaluation across all rail pieces...")
    tier_counts = {"Tier 1": 0, "Tier 2": 0, "Tier 3": 0, "Tier 4": 0}
    punjab_eval_count = 0
    fallback_eval_count = 0

    for idx, feat in enumerate(features):
        props = feat["properties"]
        cid = props.get("cell_id")

        # Get cell forecast
        c_fc = cell_forecasts.get(cid, {
            "air_max_c": float(props.get("air_max_c", 35.0)),
            "air_p95_c": float(props.get("air_p95_c", 33.0)),
            "soil_max_c": float(props.get("soil_max_c", 37.0)),
            "soil_p95_c": float(props.get("soil_p95_c", 35.0))
        })

        t_air_p95 = c_fc["air_p95_c"]
        t_air_max = c_fc["air_max_c"]
        t_soil_p95 = c_fc["soil_p95_c"]
        t_soil_max = c_fc["soil_max_c"]

        # Retrieve spatial mapping
        m_row = mapping_by_idx.loc[idx]
        has_86yr = bool(m_row["has_86yr_baseline"])
        stat_id = m_row["nearest_station_id"]
        dist_km = float(m_row["dist_to_station_km"])

        z_score = None
        stat_mu = None
        stat_sigma = None
        scoring_method = None
        tier_code = None
        tier_label = None
        tier_rank = None

        if has_86yr and pd.notnull(stat_id) and str(stat_id) in month_baselines.index:
            # High-precision Punjab 86-Year Z-Score Engine
            b_row = month_baselines.loc[str(stat_id)]
            stat_mu = float(b_row["air_mean_86yr"])
            stat_sigma = float(b_row["air_std_86yr"])

            if stat_sigma > 0:
                z_score = round(float((t_air_p95 - stat_mu) / stat_sigma), 2)
            else:
                z_score = 0.0

            scoring_method = "punjab_86yr_zscore"
            punjab_eval_count += 1

            if z_score >= 2.0:
                tier_code = 1
                tier_label = "Tier 1 (Critical Anomaly)"
                tier_rank = "extreme"
            elif z_score >= 1.2:
                tier_code = 2
                tier_label = "Tier 2 (High Anomaly)"
                tier_rank = "high"
            elif z_score >= 0.5:
                tier_code = 3
                tier_label = "Tier 3 (Moderate Anomaly)"
                tier_rank = "elevated"
            else:
                tier_code = 4
                tier_label = "Tier 4 (Baseline / Low)"
                tier_rank = "moderate"
        else:
            # National Quantile Percentile Ranking Fallback Engine
            scoring_method = "national_quantile_fallback"
            fallback_eval_count += 1

            if t_air_p95 >= national_p95:
                tier_code = 1
                tier_label = "Tier 1 (Critical Anomaly)"
                tier_rank = "extreme"
            elif t_air_p95 >= national_p80:
                tier_code = 2
                tier_label = "Tier 2 (High Anomaly)"
                tier_rank = "high"
            elif t_air_p95 >= national_p50:
                tier_code = 3
                tier_label = "Tier 3 (Moderate Anomaly)"
                tier_rank = "elevated"
            else:
                tier_code = 4
                tier_label = "Tier 4 (Baseline / Low)"
                tier_rank = "moderate"

        # Tally counts
        tier_key = f"Tier {tier_code}"
        tier_counts[tier_key] = tier_counts.get(tier_key, 0) + 1

        # Update properties
        props["forecast_air_p95_c"] = t_air_p95
        props["forecast_air_max_c"] = t_air_max
        props["forecast_soil_p95_c"] = t_soil_p95
        props["forecast_soil_max_c"] = t_soil_max
        props["has_86yr_baseline"] = has_86yr
        props["nearest_station_id"] = str(stat_id) if pd.notnull(stat_id) else None
        props["dist_to_station_km"] = dist_km
        props["scoring_engine"] = scoring_method
        props["z_score"] = z_score
        props["station_mean_86yr"] = round(stat_mu, 2) if stat_mu is not None else None
        props["station_std_86yr"] = round(stat_sigma, 2) if stat_sigma is not None else None
        props["tier_code"] = tier_code
        props["tier_label"] = tier_label
        props["tier_rank"] = tier_rank
        props["tier_air"] = tier_rank
        props["tier_soil"] = tier_rank
        props["pipeline_version"] = "v3_hybrid_forecast"

    # Data Integrity Checks
    print("Executing output data integrity validation...")
    if len(features) != 10216:
        raise ValueError(f"Integrity check failed: Expected 10,216 features, got {len(features)}")

    # Check for NaNs in critical properties
    nan_found = 0
    for f in features:
        p = f["properties"]
        if p["tier_code"] is None or p["tier_rank"] is None:
            nan_found += 1
    if nan_found > 0:
        raise ValueError(f"Integrity check failed: Found {nan_found} features with null tier assignments.")

    print(f"PASS: Exactly {len(features):,} features verified.")
    print("PASS: Zero null tier assignments detected.")
    print(f"Punjab Z-Score evaluations: {punjab_eval_count:,} ({punjab_eval_count / total_features * 100:.1f}%)")
    print(f"National fallback evaluations: {fallback_eval_count:,} ({fallback_eval_count / total_features * 100:.1f}%)")
    print(f"Tier Distribution: {tier_counts}")

    # 6. Save GeoJSON outputs
    print(f"Writing updated forecast GeoJSON to {geojson_out_root}...")
    with open(geojson_out_root, "w", encoding="utf-8") as f:
        json.dump(base_geojson, f)
    print(f"Saved root copy ({os.path.getsize(geojson_out_root) / (1024 * 1024):.1f} MB)")

    # Web output
    os.makedirs(os.path.dirname(geojson_out_web), exist_ok=True)
    with open(geojson_out_web, "w", encoding="utf-8") as f:
        json.dump(base_geojson, f)
    print(f"Saved web production copy to {geojson_out_web} ({os.path.getsize(geojson_out_web) / (1024 * 1024):.1f} MB)")

    total_time = time.time() - start_time
    print("=" * 65)
    print(f"Execution Summary: Hybrid Risk Pipeline completed in {total_time:.2f}s")
    print(f"Peak Memory Usage: {get_memory_usage_mb():.1f} MB")
    print("=" * 65)
    return base_geojson


if __name__ == "__main__":
    run_hybrid_forecast_pipeline()

