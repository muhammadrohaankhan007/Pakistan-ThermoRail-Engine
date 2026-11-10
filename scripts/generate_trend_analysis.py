#!/usr/bin/env python3
"""
Step 3: Decadal Warming Trend Portfolio Feature
ThermoRail Hybrid Risk Engine & Historical Baseline Integration

Builds a decadal trend analysis module quantifying warming shifts across
10-year packets (1940s, 1950s, ..., 2020s) for Punjab rail corridors:
1. Partitions historical readings by decade packets for each station.
2. Calculates the shift in 95th-percentile May-June temperatures between
   1940-1970 baseline vs 1996-2026 modern era (Delta T_decadal).
3. Associates stations with rail corridor segments and identifies top warming corridors.
4. Exports structured summary: decadal_heat_trends.json (and web/public/data/decadal_heat_trends.json).
"""

import sys
import os
import time
import json
import psutil
import pandas as pd
import numpy as np


def get_memory_usage_mb():
    """Returns current process RSS memory in MB."""
    process = psutil.Process(os.getpid())
    return process.memory_info().rss / (1024 * 1024)


def assign_decade(year):
    """Maps year to 10-year packet string."""
    if year < 1950:
        return "1940s"
    elif year < 1960:
        return "1950s"
    elif year < 1970:
        return "1960s"
    elif year < 1980:
        return "1970s"
    elif year < 1990:
        return "1980s"
    elif year < 2000:
        return "1990s"
    elif year < 2010:
        return "2000s"
    elif year < 2020:
        return "2010s"
    else:
        return "2020s"


DECADE_ORDER = ["1940s", "1950s", "1960s", "1970s", "1980s", "1990s", "2000s", "2010s", "2020s"]


def generate_trend_analysis():
    start_time = time.time()
    print("=" * 65)
    print("ThermoRail: Step 3 - Decadal Warming Trend Analysis")
    print("=" * 65)
    print(f"Initial Memory: {get_memory_usage_mb():.1f} MB")

    parquet_path = "punjab_temperature_1940_2026.parquet"
    stations_csv = "punjab_stations.csv"
    mapping_csv = "piece_station_mapping.csv"
    output_json = "decadal_heat_trends.json"
    web_output_json = os.path.join("web", "public", "data", "decadal_heat_trends.json")

    if not os.path.exists(parquet_path):
        raise FileNotFoundError(f"Missing {parquet_path}. Run Step 1 first.")
    if not os.path.exists(stations_csv):
        raise FileNotFoundError(f"Missing {stations_csv}.")

    # Load station metadata
    stations_df = pd.read_csv(stations_csv)
    station_meta = {row["station_id"]: {"name": row["name"], "lat": row["lat"], "lon": row["lon"]}
                    for _, row in stations_df.iterrows()}

    # Load piece mapping if present to associate rail corridor names
    corridor_names_by_station = {}
    if os.path.exists(mapping_csv):
        mapping_df = pd.read_csv(mapping_csv)
        punjab_pieces = mapping_df[mapping_df["has_86yr_baseline"]].dropna(subset=["nearest_station_id"])
        for stat_id, group in punjab_pieces.groupby("nearest_station_id"):
            named = group["name"].dropna().unique().tolist()
            if named:
                corridor_names_by_station[stat_id] = named[:3]
            else:
                corridor_names_by_station[stat_id] = ["Punjab Rail Network"]

    print(f"Loading temperature data from {parquet_path}...")
    load_start = time.time()
    df = pd.read_parquet(parquet_path)
    print(f"Loaded {len(df):,} records in {time.time() - load_start:.2f}s | Memory: {get_memory_usage_mb():.1f} MB")

    # Filter to May-June peak heat months
    print("Filtering to May-June historical temperature window...")
    df["year"] = df["timestamp"].dt.year
    df["month"] = df["timestamp"].dt.month
    mj = df[df["month"].isin([5, 6])].copy()
    mj["decade"] = mj["year"].apply(assign_decade)
    print(f"May-June subset: {len(mj):,} records")

    # 1. Overall regional decadal trend across all Punjab stations
    print("Computing regional decadal progression...")
    reg_p95 = mj.groupby("decade")["temperature"].quantile(0.95).round(2).to_dict()
    reg_mean = mj.groupby("decade")["temperature"].mean().round(2).to_dict()

    regional_trend = {}
    for dec in DECADE_ORDER:
        if dec in reg_p95:
            regional_trend[dec] = {
                "p95_c": float(reg_p95[dec]),
                "mean_c": float(reg_mean[dec])
            }

    # 2. Station-level comparisons: 1940-1970 vs 1996-2026
    print("Calculating 1940-1970 baseline vs 1996-2026 modern shifts...")
    early_mask = (mj["year"] >= 1940) & (mj["year"] <= 1970)
    recent_mask = (mj["year"] >= 1996) & (mj["year"] <= 2026)

    early_p95 = mj[early_mask].groupby("station_id")["temperature"].quantile(0.95).round(2)
    recent_p95 = mj[recent_mask].groupby("station_id")["temperature"].quantile(0.95).round(2)

    delta_series = (recent_p95 - early_p95).round(2)

    # 3. Station-level decadal progressions
    print("Calculating station-level decadal packet percentiles...")
    station_dec_p95 = mj.groupby(["station_id", "decade"])["temperature"].quantile(0.95).round(2).unstack()

    # Build corridor ranking list
    corridor_records = []
    for stat_id in stations_df["station_id"]:
        if stat_id in delta_series:
            d_val = float(delta_series[stat_id])
            e_val = float(early_p95[stat_id])
            r_val = float(recent_p95[stat_id])
            meta = station_meta.get(stat_id, {})
            c_names = corridor_names_by_station.get(stat_id, ["Punjab Rail Network"])

            prog = {}
            if stat_id in station_dec_p95.index:
                row_dec = station_dec_p95.loc[stat_id]
                for dec in DECADE_ORDER:
                    if dec in row_dec and pd.notnull(row_dec[dec]):
                        prog[dec] = float(row_dec[dec])

            corridor_records.append({
                "station_id": stat_id,
                "station_name": meta.get("name", stat_id),
                "lat": meta.get("lat"),
                "lon": meta.get("lon"),
                "associated_rail_corridors": c_names,
                "p95_baseline_1940_1970_c": e_val,
                "p95_modern_1996_2026_c": r_val,
                "delta_t_c": d_val,
                "decadal_progression_p95_c": prog
            })

    # Sort corridors by warming delta descending
    corridor_records.sort(key=lambda x: x["delta_t_c"], reverse=True)

    # Top warming corridors
    top_warming = corridor_records[:50]

    all_deltas = [c["delta_t_c"] for c in corridor_records]
    warming_count = sum(1 for d in all_deltas if d > 0)
    stable_cooling_count = sum(1 for d in all_deltas if d <= 0)

    summary_payload = {
        "metadata": {
            "title": "ThermoRail Punjab Decadal Heat Trend Analysis",
            "historical_span": "1940-2026 (86 Years)",
            "baseline_period": "1940-1970 (31 Years)",
            "modern_period": "1996-2026 (31 Years)",
            "target_months": "May-June Peak Exposure",
            "total_stations_analyzed": len(corridor_records),
            "generated_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        },
        "regional_overview": {
            "mean_delta_c": float(np.round(np.mean(all_deltas), 2)),
            "max_station_warming_c": float(np.max(all_deltas)),
            "min_station_warming_c": float(np.min(all_deltas)),
            "stations_with_warming_trend": warming_count,
            "stations_with_stable_or_cooling_trend": stable_cooling_count,
            "regional_decadal_progression": regional_trend
        },
        "top_warming_corridors": top_warming,
        "all_stations_summary": corridor_records
    }

    # Save to root JSON
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(summary_payload, f, indent=2)
    print(f"Exported decadal heat trends to {output_json} ({os.path.getsize(output_json) / 1024:.1f} KB)")

    # Save to web/public/data if web directory exists
    if os.path.exists(os.path.dirname(web_output_json)):
        with open(web_output_json, "w", encoding="utf-8") as f:
            json.dump(summary_payload, f, indent=2)
        print(f"Exported web asset copy to {web_output_json}")

    total_time = time.time() - start_time
    print("=" * 65)
    print("Top 5 Warming Corridors in Punjab:")
    for i, c in enumerate(top_warming[:5], 1):
        print(f"  {i}. {c['station_id']} ({c['station_name']}) at {c['lat']}N, {c['lon']}E: +{c['delta_t_c']:.2f} °C (P95 {c['p95_baseline_1940_1970_c']} -> {c['p95_modern_1996_2026_c']} °C)")
    print("=" * 65)
    print(f"Execution Summary: Processed trend analysis in {total_time:.2f}s | Peak Memory: {get_memory_usage_mb():.1f} MB")
    print("=" * 65)
    return summary_payload


if __name__ == "__main__":
    generate_trend_analysis()

