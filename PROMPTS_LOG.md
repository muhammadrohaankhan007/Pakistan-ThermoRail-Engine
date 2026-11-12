# Pakistan ThermoRail - Agent Directives & Prompt History

This document records the chronological prompts and directives given to AI agents for the Pakistan ThermoRail Engine project. It provides full context and architectural rationale so future AI models and engineers can explain, maintain, and extend the system.

---

## Directive 1: ThermoRail Hybrid Risk Engine & Historical Baseline Integration

**Timestamp:** 2026-11-10T23:16:15+05:00  
**Role:** Senior Data & Systems Engineer  
**Objective:** Upgrade the ThermoRail Pakistan pipeline from a static relative-tier visualization into a dual-engine production risk pipeline.

### Architectural Pillars:
1. **Punjab Corridors (86-Year High Precision):** Uses a unified 1940–2026 ERA5 station dataset to calculate location-specific Z-scores ($Z = \frac{T - \mu}{\sigma}$) relative to historical monthly norms.
2. **Non-Punjab Corridors (National Fallback):** Uses national quantile percentile ranking based on the May–June 2026 baseline.
3. **Decadal Trend Portfolio Feature:** Generates a decadal warming analysis comparing historical 10-year temperature distributions to highlight long-term thermal shifts along Pakistan's rail corridors.

### Prompt Text:
```markdown
# AGENT DIRECTIVE: ThermoRail Hybrid Risk Engine & Historical Baseline Integration

## System Role & Objective
You are acting as a Senior Data & Systems Engineer. Your task is to upgrade the ThermoRail Pakistan pipeline from a static relative-tier visualization into a dual-engine production risk pipeline. 

You will build a hybrid scoring architecture:
1. Punjab Corridors (86-Year High Precision): Uses a unified 1940–2026 ERA5 station dataset to calculate location-specific Z-scores (Z = (T - \mu)/\sigma) relative to historical monthly norms.
2. Non-Punjab Corridors (National Fallback): Uses national quantile percentile ranking based on the May–June 2026 baseline.
3. Decadal Trend Portfolio Feature: Generates a decadal warming analysis comparing historical 10-year temperature distributions to highlight long-term thermal shifts along Pakistan's rail corridors.

## Workspace & Context Limits
- Working Directory: Project root (C:\Users\Dell\Pictures\Hustle\projects\pakistan thermorail)
- Primary Source Files: 
  - pk_rail_heat_v2.geojson (10,216 piece segments)
  - cell_heat.csv (787 cell metadata)
  - punjab_temperature_1940_2026.parquet (Unified 1940–2026 ERA5 Punjab station dataset)
  - punjab_stations.csv (Station metadata containing station_id, name, lat, lon)
- Safety Rule: Do not overwrite or delete raw base GeoJSON inputs. Create new modular Python scripts under a /scripts directory and save resulting updated GeoJSONs with explicit versioning (pk_rail_forecast_v3.geojson).

## Required Implementation Steps

### Step 1: Single-Pass Station Baseline Extraction (scripts/compute_punjab_baselines.py)
Write a vectorized script using Pandas and NumPy that ingests the full 1940–2026 Punjab dataset in a single pass:
1. Extract month (1–12) from the timestamp column.
2. Group by ['station_id', 'month'] on the temperature field.
3. Compute exact statistical baselines:
   - air_mean_86yr (\mu)
   - air_std_86yr (\sigma)
   - air_p90_86yr, air_p95_86yr, air_p99_86yr
4. Output the static lookup table to punjab_station_baselines.csv. Include guard rails to catch and raise an error if any standard deviation is zero or if null values exist.

### Step 2: Spatial Piece-to-Station Mapping (scripts/map_pieces_to_stations.py)
Write a spatial binding script using scipy.spatial.cKDTree:
1. Convert coordinates of punjab_stations.csv and the center points (lat, lon) of all 10,216 rail pieces from pk_rail_heat_v2.geojson into radians.
2. Query the KDTree using Earth's mean radius (6371 km).
3. Tag each rail piece with:
   - has_86yr_baseline: True if within 35 km of a valid Punjab station; False otherwise.
   - nearest_station_id: String ID of the nearest station (or null).
   - dist_to_station_km: Floating-point distance in km.
4. Save metadata output as piece_station_mapping.csv.

### Step 3: Decadal Warming Trend Portfolio Feature (scripts/generate_trend_analysis.py)
Build a decadal trend analysis module to quantify warming shifts across 10-year packets (1940s, 1950s, ..., 2020s):
1. Partition historical readings by decade packets for each station.
2. Calculate the shift in 95th-percentile May–June temperatures between 1940–1970 vs 1996–2026 (\Delta T_decadal).
3. Export a structured summary decadal_heat_trends.json detailing top warming corridors in Punjab. This will serve as an analytics feature for portfolio/dashboard display.

### Step 4: Hybrid Risk & Live Forecast Engine (scripts/fetch_hybrid_forecast.py)
Build the daily execution pipeline:
1. Call the Open-Meteo Live Forecast API (https://api.open-meteo.com/v1/forecast) for the 787 cell points using hourly variables temperature_2m and soil_temperature_0cm over a 7-day window.
2. Calculate the 7-day max and 95th-percentile temperatures for each cell.
3. Apply the Hybrid Risk Scoring Algorithm:
   - For Pieces with has_86yr_baseline == True:
     - Retrieve matching station baselines (\mu, \sigma) for the current month.
     - Compute Z-Score: Z = (T_forecast - \mu) / \sigma.
     - Assign Tiers based on standard deviation bounds:
       - Z >= +2.0 -> Tier 1 (Critical Anomaly)
       - +1.2 <= Z < +2.0 -> Tier 2 (High Anomaly)
       - +0.5 <= Z < +1.2 -> Tier 3 (Moderate Anomaly)
       - Z < +0.5 -> Tier 4 (Baseline / Low)
   - For Pieces with has_86yr_baseline == False:
     - Fall back to national quantile percentile cuts using May–June 2026 national parameters.
4. Merge calculated values into the GeoJSON properties and output web/public/data/pk_rail_forecast_v3.geojson.
```


---

## Directive 2: ThermoRail Web Map Frontend Integration (v3 Forecast & Decadal Trends)

**Timestamp:** 2026-11-10T23:48:20+05:00  
**Role:** Senior Frontend Engineer  
**Objective:** Update the ThermoRail MapLibre GL web app (`web/`) to render the new `pk_rail_forecast_v3.geojson` dual-engine forecast layer and integrate an interactive Decadal Climate Warming drawer using `decadal_heat_trends.json`.

### Prompt Text:
```markdown
# AGENT DIRECTIVE: ThermoRail Web Map Frontend Integration (v3 Forecast & Decadal Trends)

## System Role & Objective
You are a Senior Frontend Engineer. Your task is to update the ThermoRail MapLibre GL web app (`web/`) to render the new `pk_rail_forecast_v3.geojson` dual-engine forecast layer and integrate an interactive Decadal Climate Warming drawer using `decadal_heat_trends.json`.

## Workspace & Data Context
- Working Directory: `web/` folder inside the project root (C:\Users\Dell\Pictures\Hustle\projects\pakistan thermorail\web)
- Data Files Available:
  - web/public/data/pk_rail_forecast_v3.geojson (10,216 rail pieces with hybrid risk tiers, Z-scores, and station metadata)
  - web/public/data/decadal_heat_trends.json (1940s–2020s climate warming metrics across station nodes)

## Required Implementation Steps

### Step 1: Update Data Source & Layer Logic (`web/src/main.js`)
1. Switch the MapLibre source URL from `/data/pk_rail_heat_v2.geojson` to `/data/pk_rail_forecast_v3.geojson`.
2. Ensure line styling dynamically colors track segments based on `tier_rank` (or active view toggle: `tier_rank`, `tier_air`, `tier_soil`):
   - Tier 1 (Critical): `#ef4444` (Red)
   - Tier 2 (High): `#f97316` (Orange)
   - Tier 3 (Moderate): `#eab308` (Yellow)
   - Tier 4 (Low / Normal): `#22c55e` (Green)
3. Faintly fade low-confidence or non-mainline tracks using property styling.

### Step 2: Build Enhanced Dual-Engine Interactive Popups
Update the click popup for track segments to clearly differentiate between the two scoring engines:
1. Engine Badge:
   - If `has_86yr_baseline == true`: Display a blue badge labeled "Punjab 86-Yr Z-Score Engine".
   - If `has_86yr_baseline == false`: Display an amber badge labeled "National Quantile Fallback".
2. Metrics Display:
   - Segment Name / ID: `props.name` or `props.segment_id`
   - Risk Tier: `Tier ${props.tier_rank}`
   - Historical Z-Score: `${Number(props.z_score).toFixed(2)} \sigma` (or `N/A (National Fallback)`)
   - Nearest Station: `${props.nearest_station_id}` (`${props.dist_to_station_km.toFixed(1)} km`)
   - 7-Day Forecast Air P95: `${props.air_p95}°C`
   - 7-Day Forecast Soil P95: `${props.soil_p95}°C`

### Step 3: Implement Decadal Warming Analytics UI Component
1. Fetch `/data/decadal_heat_trends.json` asynchronously on page load.
2. Add a collapsible UI side-card or drawer titled "Decadal Climate Shift (1940–2026)".
3. Render key portfolio statistics from the JSON:
   - Top warming station corridors in Punjab (e.g., Station G026 shift of +3.67°C).
   - A clean summary showing maximum temperature escalation over time along the ML-1 corridor.

### Step 4: UI Polish & Layout (`web/index.html` and `web/style.css`)
1. Ensure UI panels (Controls, Legend, Decadal Analytics) fit cleanly on screen over the dark raster basemap without overlapping map controls.
2. Maintain dark glassmorphism styling (`background: rgba(15, 23, 42, 0.88)`).
3. Escape all user-facing strings to prevent XSS.

## Acceptance Criteria
1. Map renders all 10,216 rail pieces from `pk_rail_forecast_v3.geojson` with zero console errors.
2. Clicking a line inside Punjab shows the Z-score (\sigma) and weather station distance.
3. Clicking a line outside Punjab gracefully shows the National Quantile fallback badge.
4. The Decadal Analytics panel successfully loads and displays climate warming trends.
```


---

## Directive 1 (Revised): Statistical Normalization, 1991–2020 WMO Baseline & Heat Risk Gate

**Timestamp:** 2026-11-13T00:10:31+05:00  
**Role:** Senior Data & Systems Engineer  
**Objective:** Resolve statistical discrepancies in Directive 1:
1. **Daily Max on Both Sides:** Baseline computed from daily maximum temperatures per grid point and day-of-year ($\pm 7$ day moving window), forecast computed from daily maximums (1 Z per day over 7 days).
2. **Stationary 30-Year Normal (1991–2020):** Baseline restricted to WMO standard 1991–2020 climatology to avoid historical warming trend contamination.
3. **Heat Risk Gate ($\text{GATE\_C} = 3.0^\circ\text{C}$):** Suppresses off-season/winter false positives by requiring forecast max $\ge (\text{May–June } P_{95} - \text{GATE\_C})$.
4. **Fallback Engine:** Outside grid points, margin = forecast max $-$ cell May–June record (`air_max_c`).
5. **Terminology:** Uses "grid point" (never "station"). Tier labels: `strong_anomaly`, `elevated_anomaly`, `mild_anomaly`, `near_normal`.
6. **Lightweight Output:** Emits compact `web/public/data/forecast.json` (~60 KB) keyed by `cell_id`.
7. **Empirical Calibration Check:** Validated against 30 random historical days (empirically $Z \ge 2.0$ at 1.76%, $Z \ge 1.0$ at 19.60%).
8. **Automated Daily Pipeline:** GitHub Actions cron workflow (`0 6 * * *`) builds and deploys `forecast.json` without committing to `main`.

### Prompt Text:
```markdown
Revise the scripts. Do not re-pull any Open-Meteo history; reuse the parquet. 
1. Baselines from DAILY MAXIMUM temperature: per grid point and day-of-year (+/-7 day window), mean and std of the daily max, over 1991-2020 only. Guards: no nulls, std > 0. Keep the full 1940-2026 series only for decadal_heat_trends.json. 
2. Forecast: compare each forecast day's max with that day's baseline (z per day, 7 days). Piece score = max z over the 7 days; store peak_day and forecast_max_c. 
3. Gate: only flag a piece if z >= threshold AND forecast max >= (that point's May-June 95th percentile of daily max) - GATE_C, with GATE_C = 3 as a documented, arbitrary parameter. 
4. Outside the grid-point coverage: use margin = forecast daily max minus the cell's May-June maximum (air_max_c from cell_heat.csv). Mark these rows engine = "fallback". 
5. Names: say "grid point", never "station". Tier labels: strong_anomaly, elevated_anomaly, mild_anomaly, near_normal. No "critical" or "safe" wording. 
6. Output: one small web/public/data/forecast.json keyed by cell_id, with generated_at (UTC), engine, peak_day, forecast_max_c, z (or margin), tier. No new full GeoJSON. 
7. Add a calibration check: score 30 random past days using the 1991-2020 baseline and report the share in each tier. Expect about 2% at z >= 2 and about 16% at z >= 1. Report the numbers. If they are far off, stop and tell me. 
8. Add a GitHub Actions cron workflow that runs the script daily and publishes forecast.json with the site, without committing daily to main.
```
