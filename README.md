# Pakistan-ThermoRail-Engine

A web map and live anomaly monitoring engine of heat exposure along Pakistan's railway network, built from open geospatial and meteorological data.

## What it does
- Ingests railway track alignments from OpenStreetMap, segmented into ~1 km pieces (10,216 segments across 4,158 continuous OSM ways).
- Computes baseline climatology and live 7-day thermal risk anomalies using a dual-engine architecture:
  1. **Punjab Grid Point Engine (1991–2020 WMO Normal):** Location-specific Z-scores ($Z = \frac{T - \mu}{\sigma}$) calculated against 30-year day-of-year normal baselines ($\pm 7$-day moving window) derived from Copernicus ERA5 reanalysis.
  2. **National Fallback Engine:** For areas outside Punjab grid coverage (Sindh, Balochistan, KPK), calculates operational margins relative to historical summer maximum records ($\text{margin} = T_{\text{forecast, max}} - \text{cell\_air\_max\_c}$).
- Features a seasonal **Heat Risk Gate** ($\text{GATE\_C} = 3.0^\circ\text{C}$): requires forecast peaks to approach historical May–June summer maximums before triggering alerts, eliminating off-season/winter false positives.

## Operational Pipeline Architecture
- Static Network: `web/public/data/pk_rail_heat_v2.geojson` (~8.5 MB, 10,216 LineString features).
- Live Forecast Payload: `web/public/data/forecast.json` (~225 KB), updated daily via automated GitHub Actions cron workflow (`.github/workflows/deploy.yml`) without daily repository commits.
- Front-End Map: MapLibre GL JS vanilla application with OpenFreeMap Positron vector basemap, dynamic layer filters, multi-mode exposure toggle, interactive popup inspections, and demo modes.

## Limits & Operational Disclaimers
- Temperatures originate from numerical reanalysis and weather forecasting models (~10–25 km grid spacing); they reflect ambient/model air values rather than direct rail-steel thermometry.
- Tiers denote statistical anomalies relative to local climate, not physical track deformation or buckling thresholds.
- Do not rely on this system as a deterministic safety-critical railway signaling system.

## Credits & Licensing
- **Railway Geometry:** &copy; OpenStreetMap contributors, licensed under the Open Database License (ODbL).
- **Copernicus Reanalysis:** Contains modified Copernicus Climate Change Service information 2026. Neither the European Commission nor ECMWF is responsible for any use that may be made of the Copernicus information or data it contains.
- **Weather API:** Weather forecasts and historical archives retrieved from [Open-Meteo.com](https://open-meteo.com/) (CC BY 4.0). Free tier usage is non-commercial; operational/commercial deployments require an appropriate Open-Meteo subscription.
- **Basemap:** [OpenFreeMap](https://openfreemap.org/) / [OpenMapTiles](https://openmaptiles.org/) / &copy; OpenStreetMap contributors.
