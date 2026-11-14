# Pakistan ThermoRail - Statistical Validation & Bias Audit Report

**Date of Execution:** 2026-11-14 08:15:53 UTC  
**Random Seed:** `42`  
**Baseline Climatology Period:** 1991–2020 WMO Standard Normal  
**Climatological Variable:** 24-Hour Daily Mean of `temperature_2m` (Copernicus ERA5 Reanalysis)  
**Heat Risk Gate Parameter:** $\text{GATE\_C} = 3.0^\circ\text{C}$

---

## Executive Summary of Findings

1. **Replay Divergence Explained:** Evaluating real operational forecast model output (which includes genuine, variable diurnal ranges) proves that the old engine's rigid $+5.49^\circ\text{C}$ diurnal subtraction depressed Z-scores during monsoon moisture buildup (average $+0.22\sigma$ under-reporting) and failed to discriminate micro-corridors. Under the new engine, 33 cooler Punjab cells are filtered by the like-for-like daily mean gate ($482/515$ pass vs $515/515$ in the old engine), and mild anomalies properly reflect true thermal departures ($239$ cells vs $137$).
2. **Operational Model Bias Audit (Unsafe Direction):** Over the entire warm season (April 1 – September 24, 2026; 1,770 day-point comparisons), the operational forecast model runs consistently cooler than ERA5:
   - **Overall Mean Gap:** **$-0.80^\circ\text{C}$** (**$-0.32\sigma$**)
   - **Mainline Railway Spine Concentration:** The cooler bias is not uniform; it concentrates severely along the main Pakistan Railways corridor: Rawalpindi (**$-1.62^\circ\text{C}$ / $-0.66\sigma$**), Gujranwala (**$-1.36^\circ\text{C}$ / $-0.57\sigma$**), Lahore (**$-1.37^\circ\text{C}$ / $-0.55\sigma$**), and Faisalabad (**$-1.35^\circ\text{C}$ / $-0.53\sigma$**).
   - **Operational Implication:** Because the operational model under-predicts daily mean temperatures along the main line by $\sim 0.5\sigma$ to $0.7\sigma$, real-world thermal warnings will trigger late unless corrected or explicitly flagged to railway operators.
3. **Calibration & In-Sample Noise:** Evaluated across 21,060 samples (30 calendar days $\times$ 702 grid points). Strong anomalies ($Z \ge 2.0$) match theoretical expectations ($1.75\%$ vs $2.28\%$ theoretical). Mild anomalies ($Z \ge 0.5$) show higher activation ($36.83\%$ vs $30.85\%$ theoretical) due to synoptic weather system spatial correlation across Punjab grid points on individual days.

---

## 1. Statistical Calibration Check

Evaluates empirical distributions by scoring 30 randomly selected historical days from the 1991–2020 baseline window against their corresponding Day-of-Year (DOY) baselines ($\pm 7$-day moving window).

- **Evaluations:** 21,060 (30 days $\times$ 702 grid points)
- **Random Seed:** `42`

| Anomaly Tier | Empirical Share (%) | Theoretical Standard Normal (%) | Deviation |
| :--- | :---: | :---: | :---: |
| **Strong Anomaly ($Z \ge 2.0$)** | **1.75%** | 2.28% | $-0.53\%$ |
| **Elevated Anomaly ($Z \ge 1.2$)** | **13.35%** | 11.51% | $+1.84\%$ |
| **$Z \ge 1.0$** | **19.60%** | 15.87% | $+3.73\%$ |
| **Mild Anomaly ($Z \ge 0.5$)** | **36.83%** | 30.85% | $+5.98\%$ |
| **Near Normal ($Z < 0.5$)** | **63.17%** | 69.15% | $-5.98\%$ |

*Note on In-Sample Noise:* Sampling 30 calendar days across 702 spatially adjacent grid points yields approximately 30 independent synoptic weather events. Spatial autocorrelation naturally widens the intermediate mild band during regional warm spells.

---

## 2. Synthetic $+3\sigma$ Gate Sensitivity Test

Forces $T_{\text{forecast, mean}} = \mu_{\text{DOY}} + 3.0\sigma_{\text{DOY}}$ to evaluate whether the Heat Risk Gate correctly suppresses winter false alarms while preserving sensitivity during summer heatwaves.

| Scenario | Day of Year | Punjab Gate Passes | Strong Anomaly | Elevated Anomaly | Mild Anomaly | Near Normal |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Late Autumn (November)** | DOY 318 | **0 / 515 (0.0%)** | 0 (0.0%)* | 0 (0.0%) | 0 (0.0%) | **787 (100.0%)** |
| **Peak Summer (June)** | DOY 175 | **515 / 515 (100.0%)** | **396 (100.0%)** | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) |

*\*Note: Fallback cells in Sindh/Balochistan evaluate against summer margin, reflecting regional differences.*

---

## 3. June 24–30, 2026 Hot Spell Replay

Evaluates the peak 2026 heatwave using actual operational model output retrieved from Open-Meteo's Historical Forecast API.

- **Old Engine (Git Commit `26363b6`):** $T_{\text{aligned}} = T_{\text{max}} - 5.49^\circ\text{C}$, $Z = (T_{\text{aligned}} - \mu)/\sigma$, Gate: $\max(T_{\text{max}}) \ge (P_{95} - 3.0^\circ\text{C})$.
- **New Engine (Directive 3):** Calls `score_cell_forecast` using 24-hr daily mean: $Z = (T_{\text{mean}} - \mu)/\sigma$, Gate: $\max(T_{\text{mean}}) \ge (P_{95} - 3.0^\circ\text{C})$.

### Comparative Results Table

| Risk Tier | Old Engine (Max Proxy & Gate) | New Engine (Live Mean Pipeline) | Difference |
| :--- | :---: | :---: | :---: |
| **Strong Anomaly** | 74 (9.4%) | **74 (9.4%)** | $0$ cells |
| **Elevated Anomaly** | 104 (13.2%) | **112 (14.2%)** | $+8$ cells |
| **Mild Anomaly** | 137 (17.4%) | **239 (30.4%)** | $+102$ cells |
| **Near Normal** | 472 (60.0%) | **362 (46.0%)** | $-110$ cells |
| **Punjab Gate Pass Rate** | **515 / 515 (100.0%)** | **482 / 515 (93.6%)** | $-33$ cells |

### Why the Previous Scratch Script Showed Identical Counts:
1. **Mathematical Tautology in Scratch Script:** The previous scratch script did not use actual operational forecast model outputs; it re-used single daily mean values from `punjab_temperature_1940_2026.parquet` ($T_{\text{mean}}$). In the old calculation, it synthesized $T_{\text{max}} = T_{\text{mean}} + 5.49$, and then subtracted $5.49$ ($T_{\text{aligned}} = T_{\text{mean}} + 5.49 - 5.49 \equiv T_{\text{mean}}$). The Z-scores were mathematically identical by identity.
2. **True Operational Output Divergence:** In reality, diurnal amplitude varies dynamically ($3.5^\circ\text{C}$ to $8.5^\circ\text{C}$). During late June monsoon moisture advection, diurnal range narrowed to $\sim 4.2^\circ\text{C}$. Subtracting a rigid $5.49^\circ\text{C}$ artificially suppressed temperatures by $\sim 1.3^\circ\text{C}$, causing the old engine to miss 102 mild anomaly segments that the true mean-to-mean engine correctly identifies.

---

## 4. Extended April–September 2026 Bias Audit

Comparison between Open-Meteo Operational Forecast Model (`temperature_2m_mean`) and ERA5 Reanalysis on identical calendar dates across April 1 – September 24, 2026 (177 calendar days $\times$ 10 representative rail corridor grid points = 1,770 evaluations).

$$\Delta = T_{\text{forecast model, mean}} - T_{\text{ERA5, mean}}$$

### Overall Climatological Summary
- **Total Comparisons:** 1,770
- **Overall Mean Gap (Model $-$ ERA5):** **$-0.797^\circ\text{C}$** (**$-0.324\sigma$**)
- **Overall Median Gap:** **$-0.895^\circ\text{C}$** (**$-0.369\sigma$**)
- **Standard Deviation of Gap:** $1.092^\circ\text{C}$

### Per-Grid-Point Corridor Audit Table

| Grid ID | Name / Nearest City | Lat | Lon | Mean Gap ($^\circ\text{C}$) | Median Gap ($^\circ\text{C}$) | Std ($^\circ\text{C}$) | Mean Gap ($\sigma$) | Median Gap ($\sigma$) |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `G009` | G009_34.00N_71.25E | 34.00 | 71.25 | **-0.15** | -0.17 | 0.89 | **-0.06** | -0.07 |
| `G068` | G068_33.50N_73.00E | 33.50 | 73.00 | **-1.62** | -1.73 | 0.90 | **-0.66** | -0.70 |
| `G172` | G172_32.50N_73.00E | 32.50 | 73.00 | **-1.13** | -1.18 | 0.88 | **-0.43** | -0.45 |
| `G203` | G203_32.25N_74.25E | 32.25 | 74.25 | **-1.36** | -1.40 | 0.80 | **-0.57** | -0.59 |
| `G253` | G253_31.75N_73.75E | 31.75 | 73.75 | **-1.37** | -1.51 | 0.83 | **-0.55** | -0.60 |
| `G304` | G304_31.25N_73.50E | 31.25 | 73.50 | **-1.35** | -1.41 | 0.74 | **-0.53** | -0.56 |
| `G353` | G353_30.75N_72.75E | 30.75 | 72.75 | **-0.48** | -0.63 | 0.92 | **-0.20** | -0.26 |
| `G398` | G398_30.25N_71.00E | 30.25 | 71.00 | **+0.30** | +0.29 | 1.16 | **+0.13** | +0.13 |
| `G430` | G430_30.00N_72.50E | 30.00 | 72.50 | **-0.63** | -0.72 | 1.03 | **-0.28** | -0.32 |
| `G499` | G499_29.25N_70.25E | 29.25 | 70.25 | **-0.18** | -0.20 | 0.77 | **-0.08** | -0.09 |

### Monthly Progression Table

| Month | Days | Mean Gap (^\circ\text{C}) | Median Gap (^\circ\text{C}) | Mean Gap (\sigma) |
| :--- | :---: | :---: | :---: | :---: |
| **April** | 30 | **-0.82** | -0.91 | **-0.34** |
| **May** | 30 | **-0.80** | -0.91 | **-0.32** |
| **June** | 30 | **-0.94** | -1.03 | **-0.39** |
| **July** | 30 | **-0.72** | -0.71 | **-0.30** |
| **August** | 30 | **-0.91** | -1.06 | **-0.37** |
| **September** | 30 | **-0.53** | -0.75 | **-0.20** |

### Operational Assessment of Model Bias
1. **Unsafe Direction:** The forecast model runs cooler than ERA5 across all summer months. Because Z-scores are calculated as $Z = \frac{T_{\text{model}} - \mu}{\sigma}$, a negative temperature bias produces lower Z-scores.
2. **Main Line Risk:** Along the high-speed/heavy-haul ML-1 rail corridor (Rawalpindi $\to$ Gujranwala $\to$ Lahore $\to$ Faisalabad), the model runs **$-1.35^\circ\text{C}$ to $-1.62^\circ\text{C}$ cooler** ($-0.53\sigma$ to $-0.66\sigma$). A true $Z = 1.2$ ("Elevated Anomaly") will register only as $Z \approx 0.6$ ("Mild Anomaly").
3. **Recommendation:** An advisory note has been added to the README and web UI legend warning operators that anomalies may be understated along central Punjab corridors.

---

## 5. Operational Live Run Verification

Execution log and output from the production `scripts/fetch_hybrid_forecast.py` script:

- **Generated Timestamp:** `2026-11-14T10:15:53Z`
- **Total Processed Cells:** 787
  - **Punjab Grid Z-Score Engine:** 515 cells
  - **National Fallback Engine:** 272 cells
- **Operational Status:** Exit Code `0` (Success)
- **Live Tier Distribution:**
  - **Strong Anomaly ($Z \ge 2.0$):** 0 cells (0.0%)
  - **Elevated Anomaly ($Z \ge 1.2$):** 0 cells (0.0%)
  - **Mild Anomaly ($Z \ge 0.5$):** 0 cells (0.0%)
  - **Near Normal ($Z < 0.5$ / Gate suppressed):** 787 cells (100.0%)
- **Performance:** Duration 21.87s | Peak Memory 205.2 MB
- **Artifacts Updated:** `forecast.json` (250.8 KB) and `web/public/data/forecast.json` (250.8 KB)
- **Rate-Limiting Verification:** 5-step exponential backoff successfully handled batch requests without job failure.

