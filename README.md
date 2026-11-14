# Pakistan-ThermoRail-Engine

A web map and live anomaly monitoring engine of heat exposure along Pakistan's railway network, built from open geospatial and meteorological data.

## What it does
- Ingests railway track alignments from OpenStreetMap, segmented into ~1 km pieces (10,216 segments across 4,158 continuous OSM ways).
- Computes baseline climatology and live 7-day thermal risk anomalies using a dual-engine architecture:
  1. **Punjab Grid Point Engine (1991–2020 WMO Normal):** Location-specific Z-scores ($Z = \frac{T_{\text{corrected, mean}} - \mu}{\sigma}$) calculated against 30-year day-of-year normal baselines ($\pm 7$-day moving window) derived from Copernicus ERA5 24-hour daily mean temperatures. Open-Meteo operational numerical forecast models exhibited an average $-0.86^\circ\text{C}$ ($-0.35\sigma$) cool bias relative to ERA5 reanalysis across Punjab (reaching $-1.35^\circ\text{C}$ to $-1.62^\circ\text{C}$ along the ML-1 mainline). An empirical per-cell additive bias correction ($T_{\text{corrected}} = T_{\text{forecast}} - \text{bias}_{\text{cell}}$) is applied, shrinking out-of-sample prediction error (MAE reduced by 29.3%, RMSE reduced by 25.3%) and restoring mainline anomaly sensitivity while retaining raw forecast temperatures in track popups.
  2. **National Fallback Engine:** For areas outside Punjab grid coverage (Sindh, Balochistan, KPK), calculates operational margins relative to historical summer maximum records ($\text{margin} = T_{\text{forecast, max}} - \text{cell\_air\_max\_c}$). Uses arbitrary stopgap cutoffs ($0^\circ\text{C}, -2^\circ\text{C}, -5^\circ\text{C}$) until 1991–2020 baselines are extended nationwide. Fallback daily maximums match historical summer maximums within $+0.09^\circ\text{C}$ on average, requiring no bias adjustment.
- Features a seasonal **Heat Risk Gate** ($\text{GATE\_C} = 3.0^\circ\text{C}$): requires forecast daily mean to reach within $3.0^\circ\text{C}$ of the grid point's historical May–June 95th percentile daily mean before triggering alerts, eliminating off-season/winter false positives. (Previous iterations compared daily max to daily mean $P_{95}$, giving the forecast an unintended $\sim 5.5^\circ\text{C}$ diurnal advantage; this has been corrected to like-for-like daily mean comparison).

## Statistical & Scientific Specifications
- **Climatological Variable:** 24-hour daily mean of `temperature_2m` from ERA5 reanalysis on a 0.25° grid (1991–2020 standard climatological normal period).
- **Diurnal Representation:** Forecast daily maximum temperatures are retrieved and displayed in track popups as physical references, but anomaly Z-scores and the heat gate are strictly computed from 24-hour daily mean temperatures.
- **Cross-Model Bias Audit & Out-of-Sample Validation:** Full audit across all 515 Punjab cells over April 1 – September 24, 2026 (91,155 evaluations). The operational model ran on average $-0.861^\circ\text{C}$ ($-0.348\sigma$, median $-0.920^\circ\text{C}$) cooler than ERA5, with 91.5% of cells exhibiting a cool bias. An additive correction fit on April–July (122 days) and tested on August–September (55 days; 28,325 evaluations) collapsed systematic test bias from $-0.814^\circ\text{C}$ to $+0.068^\circ\text{C}$ (91.6% reduction) and reduced MAE from $1.210^\circ\text{C}$ to $0.856^\circ\text{C}$ ($-29.3\%$). The per-cell correction is saved in `forecast_bias_by_cell.csv` and applied to daily means before Z-scoring.
- **Fallback Engine Audit:** Audit of 272 fallback cells in Sindh/Balochistan shows forecast summer maximums match historical archive summer records within $+0.09^\circ\text{C}$ on average (92.6% matching or exceeding archive maximums), confirming no cool-bias correction is needed for fallback cells.
- **Statistical Calibration (30 random historical days, 1991–2020):**
  - $Z \ge 2.0$ (Strong Anomaly): 1.75% (Theoretical normal: 2.28%)
  - $Z \ge 1.2$ (Elevated Anomaly): 13.35% (Theoretical normal: 11.51%)
  - $Z \ge 1.0$: 19.60% (Theoretical normal: 15.87%)
  - $Z < 0.5$ (Near Normal): 63.17% (Theoretical normal: 69.15%)
- **Synthetic $+3\sigma$ Verification:**
  - Autumn baseline (November): 0 / 515 Punjab cells pass the heat gate (demoted to near-normal), preventing cold-season false alarms.
  - Summer baseline (June): 515 / 515 Punjab cells pass the gate and reach Tier 1 (Strong Anomaly).
- **Hot Spell Replay (June 24–30, 2026):** Replaying the peak 2026 summer heatwave under the bias-corrected pipeline activates 543 / 787 cells (69.0%) into anomaly tiers (85 Strong, 207 Elevated, 251 Mild). 251 Punjab cells shift tiers under the correction, elevating 91 mainline corridor cells from mild anomaly to elevated anomaly ($Z \ge 1.2$) and 7 cells to strong anomaly ($Z \ge 2.0$).

## Operational Pipeline Architecture
- Static Network: `web/public/data/pk_rail_heat_v2.geojson` (~8.5 MB, 10,216 LineString features).
- Live Forecast Payload: `web/public/data/forecast.json` (~307 KB), updated daily via automated GitHub Actions cron workflow (`.github/workflows/deploy.yml`) without daily repository commits.
- Tracked Cron Input Files:
  1. `punjab_grid_point_baselines.parquet` (DOY 1–366 daily mean & std per grid point)
  2. `punjab_grid_point_gate_p95.csv` (May–June 95th percentile daily mean per grid point)
  3. `cell_grid_mapping.csv` (787 cell centroid coordinates, elevation, and grid point mapping)
  4. `forecast_bias_by_cell.csv` (empirical per-cell bias corrections for 515 Punjab cells)
  5. `requirements.txt` (Python runtime dependencies)
- Front-End Map: MapLibre GL JS vanilla application with OpenFreeMap Positron vector basemap, dynamic layer filters, multi-mode exposure toggle, interactive popup inspections, and unmissable demo badge.

## Limits & Operational Disclaimers
- Temperatures originate from numerical reanalysis and weather forecasting models (~10–25 km grid spacing); they reflect ambient/model air values rather than direct rail-steel thermometry.
- Tiers denote statistical anomalies relative to local climate, not physical track deformation or buckling thresholds.
- Do not rely on this system as a deterministic safety-critical railway signaling system.

## Credits & Licensing
- **Railway Geometry:** &copy; OpenStreetMap contributors, licensed under the Open Database License (ODbL).
- **Copernicus Reanalysis:** Contains modified Copernicus Climate Change Service information 2026. Neither the European Commission nor ECMWF is responsible for any use that may be made of the Copernicus information or data it contains.
- **Weather API:** Weather forecasts and historical archives retrieved from [Open-Meteo.com](https://open-meteo.com/) (CC BY 4.0). Free tier usage is non-commercial; operational/commercial deployments require an appropriate Open-Meteo subscription.
- **Basemap:** [OpenFreeMap](https://openfreemap.org/) / [OpenMapTiles](https://openmaptiles.org/) / &copy; OpenStreetMap contributors.
