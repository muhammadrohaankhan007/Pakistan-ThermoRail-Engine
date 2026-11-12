import 'maplibre-gl/dist/maplibre-gl.css';
import { Map, NavigationControl, Popup, setWorkerUrl } from 'maplibre-gl';
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?url';

setWorkerUrl(workerUrl);

// =============================================================================
// Operational Tiers & Color Schemes (Neutral to Warm Palette - NO GREEN)
// =============================================================================

const FORECAST_TIERS = ['strong_anomaly', 'elevated_anomaly', 'mild_anomaly', 'near_normal'];
const HISTORICAL_TIERS = ['extreme', 'high', 'elevated', 'moderate'];

const TIER_META = {
  // Forecast Operational Tiers
  strong_anomaly: {
    label: 'Strong Anomaly',
    short: 'Strong',
    color: '#ef4444',
    code: 1
  },
  elevated_anomaly: {
    label: 'Elevated Anomaly',
    short: 'Elevated',
    color: '#f97316',
    code: 2
  },
  mild_anomaly: {
    label: 'Mild Anomaly',
    short: 'Mild',
    color: '#eab308',
    code: 3
  },
  near_normal: {
    label: 'Near Normal',
    short: 'Near Normal',
    color: '#64748b', // Neutral Slate Gray - avoiding false all-clear green
    code: 4
  },

  // Historical Exposure Tiers (May-June 2026 Baseline)
  extreme: {
    label: 'Extreme',
    short: 'Extreme',
    color: '#ef4444',
    code: 1
  },
  high: {
    label: 'High',
    short: 'High',
    color: '#f97316',
    code: 2
  },
  elevated: {
    label: 'Elevated',
    short: 'Elevated',
    color: '#eab308',
    code: 3
  },
  moderate: {
    label: 'Moderate',
    short: 'Moderate',
    color: '#64748b',
    code: 4
  }
};

const TIER_COLORS = {
  strong_anomaly: '#ef4444',
  elevated_anomaly: '#f97316',
  mild_anomaly: '#eab308',
  near_normal: '#64748b',

  extreme: '#ef4444',
  high: '#f97316',
  elevated: '#eab308',
  moderate: '#64748b'
};

const MODE_NAMES = {
  forecast_tier: 'Forecast (7-Day Anomaly)',
  tier_rank: 'Combined (Historical Baseline)',
  tier_air: 'Air (P95 Baseline)',
  tier_soil: 'Ground (P95 Baseline)'
};

// Application state
let activeProp = 'forecast_tier'; // Defaults to live 7-day forecast
let isDemoMode = false;
let rawGeojsonData = null;
let rawForecastData = null;

const checkboxState = {
  strong_anomaly: true,
  elevated_anomaly: true,
  mild_anomaly: true,
  near_normal: true,

  extreme: true,
  high: true,
  elevated: true,
  moderate: true
};

const totalsByMode = {
  forecast_tier: { strong_anomaly: 0, elevated_anomaly: 0, mild_anomaly: 0, near_normal: 0, total: 0 },
  tier_rank: { extreme: 0, high: 0, elevated: 0, moderate: 0, total: 0 },
  tier_air: { extreme: 0, high: 0, elevated: 0, moderate: 0, total: 0 },
  tier_soil: { extreme: 0, high: 0, elevated: 0, moderate: 0, total: 0 }
};

/**
 * Escapes unsafe characters for HTML injection.
 */
function escapeHtml(str) {
  if (str == null) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

/**
 * Returns the active tier list for the current exposure mode.
 */
function getActiveTierList() {
  return activeProp === 'forecast_tier' ? FORECAST_TIERS : HISTORICAL_TIERS;
}

/**
 * Computes the total km and tier distribution for each mode from the GeoJSON features.
 */
function computeTotals(geojson) {
  for (const mode of ['forecast_tier', 'tier_rank', 'tier_air', 'tier_soil']) {
    if (mode === 'forecast_tier') {
      totalsByMode[mode] = { strong_anomaly: 0, elevated_anomaly: 0, mild_anomaly: 0, near_normal: 0, total: 0 };
    } else {
      totalsByMode[mode] = { extreme: 0, high: 0, elevated: 0, moderate: 0, total: 0 };
    }
  }

  for (const feat of geojson.features) {
    const props = feat.properties;
    const km = Number(props.length_km) || 0;
    for (const mode of ['forecast_tier', 'tier_rank', 'tier_air', 'tier_soil']) {
      const tier = props[mode];
      if (tier && totalsByMode[mode][tier] !== undefined) {
        totalsByMode[mode][tier] += km;
        totalsByMode[mode].total += km;
      }
    }
  }
}

/**
 * Renders the tier filter checkboxes with updated labels and color swatches.
 */
function renderFilterControls(onFilterChange) {
  const container = document.getElementById('tier-filter-list');
  if (!container) return;

  container.innerHTML = '';
  const currentTiers = getActiveTierList();

  for (const tier of currentTiers) {
    const meta = TIER_META[tier] || { label: tier, color: '#64748b' };
    const km = totalsByMode[activeProp][tier] || 0;
    const totalKm = totalsByMode[activeProp].total || 1;
    const pct = ((km / totalKm) * 100).toFixed(1);

    const item = document.createElement('label');
    item.className = 'filter-item';

    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.checked = checkboxState[tier];
    checkbox.dataset.tier = tier;

    checkbox.addEventListener('change', (e) => {
      checkboxState[tier] = e.target.checked;
      onFilterChange();
    });

    const swatch = document.createElement('span');
    swatch.className = 'color-swatch';
    swatch.style.backgroundColor = meta.color;

    const label = document.createElement('span');
    label.className = 'filter-label';
    label.textContent = meta.label;

    const count = document.createElement('span');
    count.className = 'filter-count';
    count.textContent = `${km.toFixed(1)} km (${pct}%)`;

    item.appendChild(checkbox);
    item.appendChild(swatch);
    item.appendChild(label);
    item.appendChild(count);
    container.appendChild(item);
  }
}

/**
 * Renders the Network Summary table showing km and share percentage per tier.
 */
function renderSummary() {
  const container = document.getElementById('tier-summary');
  const labelEl = document.getElementById('active-mode-label');
  if (!container) return;

  if (labelEl) {
    labelEl.textContent = MODE_NAMES[activeProp] || activeProp;
  }

  const currentTiers = getActiveTierList();
  const totals = totalsByMode[activeProp];
  const totalKm = totals.total || 0;

  let rowsHtml = '';
  for (const tier of currentTiers) {
    const meta = TIER_META[tier] || { label: tier, color: '#64748b' };
    const km = totals[tier] || 0;
    const pct = totalKm > 0 ? ((km / totalKm) * 100).toFixed(1) : '0.0';

    rowsHtml += `
      <tr>
        <td>
          <span class="color-swatch" style="background-color: ${meta.color}; display: inline-block; vertical-align: middle; margin-right: 6px;"></span>
          ${escapeHtml(meta.label)}
        </td>
        <td class="col-num">${km.toLocaleString('en-US', { minimumFractionDigits: 1, maximumFractionDigits: 1 })} km</td>
        <td class="col-num">${pct}%</td>
      </tr>
    `;
  }

  container.innerHTML = `
    <table class="summary-table">
      <thead>
        <tr>
          <th>Risk Tier</th>
          <th class="col-num">Length</th>
          <th class="col-num">Share</th>
        </tr>
      </thead>
      <tbody>
        ${rowsHtml}
      </tbody>
      <tfoot>
        <tr>
          <th>Total</th>
          <th class="col-num">${totalKm.toLocaleString('en-US', { minimumFractionDigits: 1, maximumFractionDigits: 1 })} km</th>
          <th class="col-num">100.0%</th>
        </tr>
      </tfoot>
    </table>
  `;
}

/**
 * Injects synthetic hot spell data into the GeoJSON features (?demo=hot).
 */
function applySyntheticHotSpell(geojson) {
  // Deterministic seed pattern based on piece index
  geojson.features.forEach((feat, idx) => {
    const p = feat.properties;
    const mod = idx % 100;
    if (mod < 15) {
      p.forecast_tier = 'strong_anomaly';
      p.forecast_z = 3.25;
      p.forecast_margin = 1.4;
      p.forecast_max_c = 46.8;
      p.peak_day = '2026-06-25';
    } else if (mod < 45) {
      p.forecast_tier = 'elevated_anomaly';
      p.forecast_z = 1.78;
      p.forecast_margin = -0.8;
      p.forecast_max_c = 44.2;
      p.peak_day = '2026-06-26';
    } else if (mod < 85) {
      p.forecast_tier = 'mild_anomaly';
      p.forecast_z = 0.88;
      p.forecast_margin = -3.2;
      p.forecast_max_c = 41.5;
      p.peak_day = '2026-06-27';
    } else {
      p.forecast_tier = 'near_normal';
      p.forecast_z = 0.21;
      p.forecast_margin = -7.5;
      p.forecast_max_c = 37.0;
      p.peak_day = '2026-06-28';
    }
  });
}

/**
 * Restores real forecast values from forecast.json into GeoJSON features.
 */
function restoreRealForecast(geojson, forecastData) {
  const cellsMap = forecastData.cells || {};
  geojson.features.forEach(feat => {
    const p = feat.properties;
    const cid = p.cell_id;
    const fc = cellsMap[cid];
    if (fc) {
      p.forecast_tier = fc.tier;
      p.forecast_engine = fc.engine;
      p.forecast_z = fc.z;
      p.forecast_margin = fc.margin;
      p.forecast_max_c = fc.forecast_max_c;
      p.peak_day = fc.peak_day;
      p.grid_point_id = fc.grid_point_id;
      p.dist_to_grid_point_km = fc.dist_to_grid_point_km;
      p.gate_passed = fc.gate_passed;
    } else {
      p.forecast_tier = 'near_normal';
      p.forecast_engine = 'fallback';
      p.forecast_z = null;
      p.forecast_margin = null;
      p.forecast_max_c = 30.0;
      p.peak_day = null;
      p.grid_point_id = null;
      p.dist_to_grid_point_km = null;
      p.gate_passed = false;
    }
  });
}

/**
 * Initializes the MapLibre map and binds event handlers.
 */
function initApp() {
  // 1. Start fetches immediately in parallel
  const geojsonPromise = fetch(import.meta.env.BASE_URL + 'data/pk_rail_heat_v2.geojson').then(r => {
    if (!r.ok) throw new Error(`HTTP ${r.status} fetching GeoJSON: ${r.statusText}`);
    return r.json();
  });

  const forecastPromise = fetch(import.meta.env.BASE_URL + 'data/forecast.json').then(r => {
    if (!r.ok) throw new Error(`HTTP ${r.status} fetching Forecast: ${r.statusText}`);
    return r.json();
  });

  // Check URL query for ?demo=hot
  const urlParams = new URLSearchParams(window.location.search);
  if (urlParams.get('demo') === 'hot') {
    isDemoMode = true;
  }

  // OpenFreeMap Positron vector basemap
  const map = new Map({
    container: 'map',
    style: 'https://tiles.openfreemap.org/styles/positron',
    center: [69.34, 29.8],
    zoom: 5.4
  });

  window.map = map;
  map.addControl(new NavigationControl({ showCompass: true }), 'top-right');

  // Register map.on('load') synchronously
  map.on('load', async () => {
    try {
      const [geojsonData, forecastData] = await Promise.all([geojsonPromise, forecastPromise]);
      rawGeojsonData = geojsonData;
      rawForecastData = forecastData;

      // 2. Client-side memory join: join forecast.json by cell_id
      restoreRealForecast(geojsonData, forecastData);

      // Handle Demo mode if active
      if (isDemoMode) {
        applySyntheticHotSpell(geojsonData);
        const demoBadge = document.getElementById('demo-badge');
        const demoBtn = document.getElementById('demo-toggle-btn');
        if (demoBadge) demoBadge.style.display = 'block';
        if (demoBtn) {
          demoBtn.classList.add('active');
          demoBtn.textContent = 'EXIT DEMO';
        }
      }

      // Build Map from osm_id to { km: sum of length_km, count: number of pieces }
      const waysMap = new globalThis.Map();
      for (const feat of geojsonData.features) {
        const p = feat.properties;
        const oid = p.osm_id;
        const km = Number(p.length_km) || 0;
        const existing = waysMap.get(oid);
        if (existing) {
          existing.km += km;
          existing.count += 1;
        } else {
          waysMap.set(oid, { km, count: 1 });
        }
      }

      // Compute summary totals from the joined object
      computeTotals(geojsonData);

      // 3. Check Staleness & Render Forecast Timestamp
      const genAtStr = forecastData.metadata?.generated_at;
      const timeEl = document.getElementById('forecast-time-line');
      const staleBanner = document.getElementById('staleness-banner');
      if (genAtStr && timeEl) {
        const genDate = new Date(genAtStr);
        const hoursOld = (Date.now() - genDate.getTime()) / (1000 * 3600);
        timeEl.textContent = `Forecast: ${genDate.toISOString().replace('.000', '')}`;

        if (hoursOld > 48 && staleBanner) {
          staleBanner.textContent = `⚠️ Forecast may be out of date (generated ${Math.round(hoursOld)}h ago).`;
          staleBanner.style.display = 'block';
        }
      }

      // 4. Check All-Clear State
      function updateAllClearBanner() {
        const allClearBanner = document.getElementById('all-clear-banner');
        if (!allClearBanner) return;

        if (activeProp === 'forecast_tier') {
          const nonNormalKm = (totalsByMode.forecast_tier.strong_anomaly || 0) +
                              (totalsByMode.forecast_tier.elevated_anomaly || 0) +
                              (totalsByMode.forecast_tier.mild_anomaly || 0);

          if (nonNormalKm === 0) {
            allClearBanner.innerHTML = `<strong>ℹ️ No heat anomaly detected in 7-day forecast.</strong><br>All rail segments are operating within near-normal climatological ranges.`;
            allClearBanner.style.display = 'block';
          } else {
            allClearBanner.style.display = 'none';
          }
        } else {
          allClearBanner.style.display = 'none';
        }
      }

      const statusEl = document.getElementById('status-line');
      if (statusEl) {
        statusEl.textContent = `Active Pipeline: ${geojsonData.features.length} rail segments loaded`;
      }

      // 5. Layer Filter Updates
      function updateLayerFilter() {
        const currentTiers = getActiveTierList();
        const activeTiers = currentTiers.filter(tier => checkboxState[tier]);

        let filterExp;
        if (activeTiers.length === 0) {
          filterExp = ['==', ['literal', 1], 2];
        } else if (activeTiers.length === currentTiers.length) {
          filterExp = null;
        } else {
          filterExp = ['in', ['get', activeProp], ['literal', activeTiers]];
        }

        if (map.getLayer('rail-lines-solid')) {
          map.setFilter('rail-lines-solid', filterExp);
        }
        if (map.getLayer('rail-lines-dashed')) {
          map.setFilter('rail-lines-dashed', filterExp);
        }
      }

      // 6. Layer Color Updates
      function updateLayerColor() {
        const colorExp = [
          'match',
          ['get', activeProp],
          'strong_anomaly', TIER_COLORS.strong_anomaly,
          'elevated_anomaly', TIER_COLORS.elevated_anomaly,
          'mild_anomaly', TIER_COLORS.mild_anomaly,
          'near_normal', TIER_COLORS.near_normal,

          'extreme', TIER_COLORS.extreme,
          'high', TIER_COLORS.high,
          'elevated', TIER_COLORS.elevated,
          'moderate', TIER_COLORS.moderate,
          '#64748b'
        ];

        if (map.getLayer('rail-lines-solid')) {
          map.setPaintProperty('rail-lines-solid', 'line-color', colorExp);
        }
        if (map.getLayer('rail-lines-dashed')) {
          map.setPaintProperty('rail-lines-dashed', 'line-color', colorExp);
        }
      }

      // Render controls and summary
      renderFilterControls(updateLayerFilter);
      renderSummary();
      updateAllClearBanner();

      // 7. Toggle Group Event Listeners
      const toggleButtons = document.querySelectorAll('.toggle-btn');
      toggleButtons.forEach(btn => {
        btn.addEventListener('click', () => {
          const newProp = btn.dataset.prop;
          if (newProp === activeProp) return;

          toggleButtons.forEach(b => b.classList.remove('active'));
          btn.classList.add('active');

          activeProp = newProp;

          updateLayerColor();
          updateLayerFilter();
          renderFilterControls(updateLayerFilter);
          renderSummary();
          updateAllClearBanner();
        });
      });

      // 8. Demo Toggle Event Listener
      const demoBtn = document.getElementById('demo-toggle-btn');
      const demoBadge = document.getElementById('demo-badge');
      if (demoBtn) {
        demoBtn.addEventListener('click', () => {
          isDemoMode = !isDemoMode;
          if (isDemoMode) {
            applySyntheticHotSpell(geojsonData);
            if (demoBadge) demoBadge.style.display = 'block';
            demoBtn.classList.add('active');
            demoBtn.textContent = 'EXIT DEMO';
          } else {
            restoreRealForecast(geojsonData, rawForecastData);
            if (demoBadge) demoBadge.style.display = 'none';
            demoBtn.classList.remove('active');
            demoBtn.textContent = 'DEMO HOT';
          }

          // Update map source
          const src = map.getSource('rail-source');
          if (src) src.setData(geojsonData);

          computeTotals(geojsonData);
          renderFilterControls(updateLayerFilter);
          renderSummary();
          updateLayerFilter();
          updateLayerColor();
          updateAllClearBanner();
        });
      }

      // 9. Add Map Source & Layers
      map.addSource('rail-source', {
        type: 'geojson',
        data: geojsonData
      });

      // Highlight layer for whole OSM way - underneath rail-lines
      map.addLayer({
        id: 'way-highlight',
        type: 'line',
        source: 'rail-source',
        filter: ['==', ['get', 'osm_id'], -1],
        layout: {
          'line-join': 'round',
          'line-cap': 'round'
        },
        paint: {
          'line-color': '#00e5ff',
          'line-width': [
            'interpolate',
            ['linear'],
            ['zoom'],
            4, 3.8,
            8, 6.5,
            12, 9.5
          ],
          'line-opacity': 0.85
        }
      });

      // Solid Rail Lines: Punjab Grid Z-Score Engine
      map.addLayer({
        id: 'rail-lines-solid',
        type: 'line',
        source: 'rail-source',
        filter: ['!=', ['get', 'forecast_engine'], 'fallback'],
        layout: {
          'line-join': 'round',
          'line-cap': 'round'
        },
        paint: {
          'line-color': [
            'match',
            ['get', activeProp],
            'strong_anomaly', TIER_COLORS.strong_anomaly,
            'elevated_anomaly', TIER_COLORS.elevated_anomaly,
            'mild_anomaly', TIER_COLORS.mild_anomaly,
            'near_normal', TIER_COLORS.near_normal,
            'extreme', TIER_COLORS.extreme,
            'high', TIER_COLORS.high,
            'elevated', TIER_COLORS.elevated,
            'moderate', TIER_COLORS.moderate,
            '#64748b'
          ],
          'line-width': [
            'interpolate',
            ['linear'],
            ['zoom'],
            4, 1.5,
            8, 2.8,
            12, 5.0
          ],
          'line-opacity': [
            'case',
            ['all', ['==', ['get', 'confidence'], 'high'], ['==', ['get', 'usage'], 'main']],
            0.95,
            ['==', ['get', 'confidence'], 'low'],
            0.35,
            0.65
          ]
        }
      });

      // Dashed Rail Lines: National Summer Record Fallback Engine
      map.addLayer({
        id: 'rail-lines-dashed',
        type: 'line',
        source: 'rail-source',
        filter: ['==', ['get', 'forecast_engine'], 'fallback'],
        layout: {
          'line-join': 'round',
          'line-cap': 'round'
        },
        paint: {
          'line-dasharray': [4, 2],
          'line-color': [
            'match',
            ['get', activeProp],
            'strong_anomaly', TIER_COLORS.strong_anomaly,
            'elevated_anomaly', TIER_COLORS.elevated_anomaly,
            'mild_anomaly', TIER_COLORS.mild_anomaly,
            'near_normal', TIER_COLORS.near_normal,
            'extreme', TIER_COLORS.extreme,
            'high', TIER_COLORS.high,
            'elevated', TIER_COLORS.elevated,
            'moderate', TIER_COLORS.moderate,
            '#64748b'
          ],
          'line-width': [
            'interpolate',
            ['linear'],
            ['zoom'],
            4, 1.5,
            8, 2.8,
            12, 5.0
          ],
          'line-opacity': [
            'case',
            ['all', ['==', ['get', 'confidence'], 'high'], ['==', ['get', 'usage'], 'main']],
            0.95,
            ['==', ['get', 'confidence'], 'low'],
            0.35,
            0.65
          ]
        }
      });

      // Highlight layer for the single clicked piece
      map.addLayer({
        id: 'piece-highlight',
        type: 'line',
        source: 'rail-source',
        filter: ['==', ['get', 'osm_id'], -1],
        layout: {
          'line-join': 'round',
          'line-cap': 'round'
        },
        paint: {
          'line-color': '#ffffff',
          'line-width': [
            'interpolate',
            ['linear'],
            ['zoom'],
            4, 2.8,
            8, 4.8,
            12, 7.5
          ],
          'line-opacity': 1.0
        }
      });

      updateLayerFilter();

      // Hover cursor
      ['rail-lines-solid', 'rail-lines-dashed'].forEach(layerId => {
        map.on('mouseenter', layerId, () => {
          map.getCanvas().style.cursor = 'pointer';
        });
        map.on('mouseleave', layerId, () => {
          map.getCanvas().style.cursor = '';
        });
      });

      let currentPopup = null;

      // Click Handler for Track Inspection
      function handleTrackClick(e) {
        if (!e.features || !e.features.length) return;
        const feature = e.features[0];
        const p = feature.properties;

        if (currentPopup) {
          const oldPopup = currentPopup;
          currentPopup = null;
          oldPopup.remove();
        }

        // Highlight whole way and single piece
        map.setFilter('way-highlight', ['==', ['get', 'osm_id'], p.osm_id]);
        map.setFilter('piece-highlight', [
          'all',
          ['==', ['get', 'osm_id'], p.osm_id],
          ['==', ['get', 'piece'], p.piece]
        ]);

        const lineName = p.name ? escapeHtml(p.name) : `Track Segment (OSM Way #${p.osm_id})`;
        const currentTier = p[activeProp] || (activeProp === 'forecast_tier' ? 'near_normal' : 'moderate');
        const meta = TIER_META[currentTier] || { label: currentTier, color: '#64748b' };
        const tierColor = meta.color;
        const tierLabel = meta.label;

        // Engine Details & Badging
        const isFallback = p.forecast_engine === 'fallback';
        const engineBadgeClass = isFallback ? 'badge-national' : 'badge-punjab';
        const engineBadgeText = isFallback ? 'National Summer Record Fallback' : 'Punjab Grid Z-Score Engine';

        let metricsHtml = '';

        if (activeProp === 'forecast_tier') {
          const zScoreStr = p.forecast_z != null ? `${Number(p.forecast_z).toFixed(2)} \u03c3` : 'N/A (National Fallback)';
          const marginStr = p.forecast_margin != null ? `${p.forecast_margin > 0 ? '+' : ''}${Number(p.forecast_margin).toFixed(1)} \u00b0C` : 'N/A (Punjab Z-Score)';
          const gridPointStr = p.grid_point_id
            ? `${escapeHtml(p.grid_point_id)} (${Number(p.dist_to_grid_point_km || 0).toFixed(1)} km)`
            : `Outside Coverage (${Number(p.dist_to_grid_point_km || 0).toFixed(1)} km from Punjab)`;
          const maxTempStr = p.forecast_max_c != null ? `${Number(p.forecast_max_c).toFixed(1)} \u00b0C` : '\u2014';
          const peakDayStr = p.peak_day ? escapeHtml(p.peak_day) : '\u2014';

          metricsHtml = `
            <span class="popup-key">Forecast Max (7-Day):</span>
            <span class="popup-val">${maxTempStr}</span>
            <span class="popup-key">Peak Anomaly Day:</span>
            <span class="popup-val">${peakDayStr}</span>
            <span class="popup-key">Historical Z-Score:</span>
            <span class="popup-val z-score-val">${escapeHtml(zScoreStr)}</span>
            <span class="popup-key">Summer Record Margin:</span>
            <span class="popup-val">${escapeHtml(marginStr)}</span>
            <span class="popup-key">Nearest Grid Point:</span>
            <span class="popup-val">${gridPointStr}</span>
          `;
        } else {
          // Historical Baseline Metrics
          const airP95 = p.air_p95_c != null ? `${Number(p.air_p95_c).toFixed(1)} \u00b0C` : '\u2014';
          const soilP95 = p.soil_p95_c != null ? `${Number(p.soil_p95_c).toFixed(1)} \u00b0C` : '\u2014';
          metricsHtml = `
            <span class="popup-key">Air P95 (May–June):</span>
            <span class="popup-val">${airP95}</span>
            <span class="popup-key">Soil P95 (May–June):</span>
            <span class="popup-val">${soilP95}</span>
          `;
        }

        // Length calculations for single piece and whole OSM way
        const thisPieceKm = p.length_km != null ? `${Number(p.length_km).toFixed(2)} km` : '\u2014';
        const wayInfo = waysMap.get(p.osm_id);
        const wayKm = wayInfo ? wayInfo.km : (Number(p.length_km) || 0);
        const wayKmFormatted = wayKm >= 100 ? wayKm.toFixed(1) : wayKm.toFixed(2);
        const pieceNum = (Number(p.piece) || 0) + 1;
        const totalPieces = wayInfo ? wayInfo.count : 1;
        const wholeWayStr = `${wayKmFormatted} km (piece ${pieceNum} of ${totalPieces})`;
        const usageConfidence = `${escapeHtml(p.usage || 'main')} / ${escapeHtml(p.confidence || 'high')}`;

        const popupHtml = `
          <div class="popup-title">${lineName}</div>
          <div class="popup-badges">
            <span class="popup-engine-badge ${engineBadgeClass}">
              ${escapeHtml(engineBadgeText)}
            </span>
            <span class="popup-tier-badge" style="background-color: ${tierColor};">
              ${escapeHtml(tierLabel)}
            </span>
          </div>
          <div class="popup-grid">
            ${metricsHtml}
            <span class="popup-key">This piece:</span>
            <span class="popup-val">${thisPieceKm}</span>
            <span class="popup-key">Whole OSM way:</span>
            <span class="popup-val">${wholeWayStr}</span>
            <span class="popup-key">Usage / Confidence:</span>
            <span class="popup-val">${usageConfidence}</span>
          </div>
          <div class="popup-footnote">Pieces are ~1 km cuts of an OSM way.</div>
          <div class="popup-disclaimer">Statistical anomaly relative to local normal; not a track-failure threshold.</div>
        `;

        const popup = new Popup({ closeButton: true, maxWidth: '350px' })
          .setLngLat(e.lngLat)
          .setHTML(popupHtml)
          .addTo(map);

        currentPopup = popup;

        popup.on('close', () => {
          map.setFilter('way-highlight', ['==', ['get', 'osm_id'], -1]);
          map.setFilter('piece-highlight', ['==', ['get', 'osm_id'], -1]);
          currentPopup = null;
        });
      }

      map.on('click', 'rail-lines-solid', handleTrackClick);
      map.on('click', 'rail-lines-dashed', handleTrackClick);

    } catch (err) {
      console.error('Failed to load ThermoRail pipeline:', err);
      const statusEl = document.getElementById('status-line');
      if (statusEl) {
        statusEl.textContent = `Error loading pipeline: ${err.message}`;
        statusEl.style.color = '#ef4444';
      }
    }
  });
}

// Boot application
initApp();
