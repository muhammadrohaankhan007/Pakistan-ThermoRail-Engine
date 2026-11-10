import 'maplibre-gl/dist/maplibre-gl.css';
import { Map, NavigationControl, Popup, setWorkerUrl } from 'maplibre-gl';
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?url';

setWorkerUrl(workerUrl);

const TIERS = ['extreme', 'high', 'elevated', 'moderate'];

const TIER_META = {
  extreme: {
    label: 'Tier 1 (Critical)',
    short: 'Critical',
    color: '#ef4444',
    code: 1
  },
  high: {
    label: 'Tier 2 (High)',
    short: 'High',
    color: '#f97316',
    code: 2
  },
  elevated: {
    label: 'Tier 3 (Moderate)',
    short: 'Moderate',
    color: '#eab308',
    code: 3
  },
  moderate: {
    label: 'Tier 4 (Low / Normal)',
    short: 'Low / Normal',
    color: '#22c55e',
    code: 4
  }
};

const TIER_COLORS = {
  extreme: '#ef4444',
  high: '#f97316',
  elevated: '#eab308',
  moderate: '#22c55e'
};

const MODE_NAMES = {
  tier_rank: 'Combined (Hybrid)',
  tier_air: 'Air (P95 Forecast)',
  tier_soil: 'Ground (P95 Forecast)'
};

// Application state
let activeProp = 'tier_rank';
const checkboxState = {
  extreme: true,
  high: true,
  elevated: true,
  moderate: true
};

const totalsByMode = {
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
 * Computes the total km and tier distribution for each mode from the GeoJSON features.
 */
function computeTotals(geojson) {
  // Reset totals
  for (const mode of ['tier_rank', 'tier_air', 'tier_soil']) {
    totalsByMode[mode] = { extreme: 0, high: 0, elevated: 0, moderate: 0, total: 0 };
  }

  for (const feat of geojson.features) {
    const props = feat.properties;
    const km = Number(props.length_km) || 0;
    for (const mode of ['tier_rank', 'tier_air', 'tier_soil']) {
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

  TIERS.forEach(tier => {
    const meta = TIER_META[tier];
    const item = document.createElement('label');
    item.className = 'tier-item';

    const left = document.createElement('div');
    left.className = 'tier-item-left';

    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.className = 'tier-checkbox';
    checkbox.value = tier;
    checkbox.checked = checkboxState[tier];
    checkbox.addEventListener('change', () => {
      checkboxState[tier] = checkbox.checked;
      onFilterChange();
    });

    const swatch = document.createElement('span');
    swatch.className = 'color-swatch';
    swatch.style.backgroundColor = meta.color;

    const label = document.createElement('span');
    label.className = 'tier-label';
    label.textContent = meta.label;

    left.appendChild(checkbox);
    left.appendChild(swatch);
    left.appendChild(label);
    item.appendChild(left);
    container.appendChild(item);
  });
}

/**
 * Renders the summary table under the legend for the active toggle mode.
 */
function renderSummary() {
  const container = document.getElementById('tier-summary');
  const modeLabel = document.getElementById('active-mode-label');
  if (modeLabel) {
    modeLabel.textContent = MODE_NAMES[activeProp];
  }
  if (!container) return;

  const modeTotals = totalsByMode[activeProp];
  const totalKm = modeTotals.total;

  let rowsHtml = '';
  TIERS.forEach(tier => {
    const meta = TIER_META[tier];
    const km = modeTotals[tier];
    const pct = totalKm > 0 ? (km / totalKm) * 100 : 0;
    const formattedKm = km.toLocaleString('en-US', {
      minimumFractionDigits: 1,
      maximumFractionDigits: 1
    });
    const formattedPct = pct.toFixed(1);

    rowsHtml += `
      <tr>
        <td class="col-tier">
          <span class="color-swatch" style="background-color: ${meta.color};"></span>
          ${escapeHtml(meta.label)}
        </td>
        <td class="col-num">${formattedKm} km</td>
        <td class="col-num">${formattedPct}%</td>
      </tr>
    `;
  });

  const formattedTotalKm = totalKm.toLocaleString('en-US', {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1
  });

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
        <tr class="total-row">
          <th>Total</th>
          <th class="col-num">${formattedTotalKm} km</th>
          <th class="col-num">100.0%</th>
        </tr>
      </tfoot>
    </table>
  `;
}

/**
 * Loads and renders the Decadal Climate Shift Drawer from decadal_heat_trends.json.
 */
async function initDecadalDrawer(map) {
  const drawer = document.getElementById('decadal-drawer');
  const toggleBtn = document.getElementById('decadal-toggle-btn');
  const closeBtn = document.getElementById('decadal-close-btn');
  const content = document.getElementById('decadal-content');
  const body = document.getElementById('decadal-body');
  const badge = document.getElementById('decadal-badge');

  if (!drawer || !toggleBtn || !content || !body) return;

  // Toggle drawer behavior
  function toggleDrawer(open) {
    const isOpening = open !== undefined ? open : drawer.classList.contains('collapsed');
    if (isOpening) {
      drawer.classList.remove('collapsed');
      content.style.display = 'flex';
      toggleBtn.setAttribute('aria-expanded', 'true');
    } else {
      drawer.classList.add('collapsed');
      content.style.display = 'none';
      toggleBtn.setAttribute('aria-expanded', 'false');
    }
  }

  toggleBtn.addEventListener('click', () => toggleDrawer());
  if (closeBtn) {
    closeBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      toggleDrawer(false);
    });
  }

  try {
    const trendsUrl = import.meta.env.BASE_URL + 'data/decadal_heat_trends.json';
    const resp = await fetch(trendsUrl);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}: ${resp.statusText}`);
    const data = await resp.json();

    const reg = data.regional_overview || {};
    const maxWarm = reg.max_station_warming_c != null ? `+${reg.max_station_warming_c.toFixed(2)}°C` : '+3.67°C';
    if (badge) badge.textContent = `Max ${maxWarm}`;

    const meanWarm = reg.mean_delta_c != null ? `${reg.mean_delta_c > 0 ? '+' : ''}${reg.mean_delta_c.toFixed(2)}°C` : '—';
    const warmingCount = reg.stations_with_warming_trend || 0;
    const totalCount = data.metadata?.total_stations_analyzed || 702;

    // Render KPI grid and Top Warming Corridors
    const topCorridors = data.top_warming_corridors || [];
    let corridorRowsHtml = '';

    topCorridors.slice(0, 15).forEach((item, idx) => {
      const deltaSign = item.delta_t_c > 0 ? '+' : '';
      const deltaClass = item.delta_t_c >= 2.0 ? 'delta-high' : 'delta-mod';
      const cName = (item.associated_rail_corridors && item.associated_rail_corridors[0]) || 'Punjab Rail Network';

      corridorRowsHtml += `
        <div class="corridor-item" data-lat="${item.lat}" data-lon="${item.lon}" title="Click to fly to this rail corridor">
          <div class="corridor-info">
            <span class="corridor-name">${idx + 1}. ${escapeHtml(cName)}</span>
            <span class="corridor-details">Station ${escapeHtml(item.station_id)} (${item.lat}°N, ${item.lon}°E) &bull; Base ${item.p95_baseline_1940_1970_c}°C &rarr; Mod ${item.p95_modern_1996_2026_c}°C</span>
          </div>
          <span class="corridor-delta ${deltaClass}">${deltaSign}${item.delta_t_c.toFixed(2)}°C</span>
        </div>
      `;
    });

    // Render regional decadal progression
    const progression = reg.regional_decadal_progression || {};
    const decKeys = Object.keys(progression);
    let barsHtml = '';
    const minP95 = 37.0;
    const maxP95 = 40.0;

    decKeys.forEach((dec) => {
      const val = progression[dec]?.p95_c || 38.0;
      const heightPct = Math.max(10, Math.min(100, ((val - minP95) / (maxP95 - minP95)) * 100));
      const isRecent = dec === '2020s' || dec === '2010s';

      barsHtml += `
        <div class="dec-bar-col" title="${dec}: ${val}°C (May–June P95)">
          <span class="dec-bar-val">${val.toFixed(1)}</span>
          <div class="dec-bar ${isRecent ? 'highlight-recent' : ''}" style="height: ${heightPct}%;"></div>
          <span class="dec-bar-label">${dec.slice(2)}</span>
        </div>
      `;
    });

    body.innerHTML = `
      <div class="kpi-grid">
        <div class="kpi-card">
          <div class="kpi-label">Peak Station Shift</div>
          <div class="kpi-val highlight-warm">${maxWarm}</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-label">Mean Shift</div>
          <div class="kpi-val">${meanWarm}</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-label">Warming Nodes</div>
          <div class="kpi-val">${warmingCount} / ${totalCount}</div>
        </div>
      </div>

      <div class="progression-section">
        <div class="progression-title">Regional May–June P95 Progression (1940s–2020s)</div>
        <div class="progression-bars">
          ${barsHtml}
        </div>
      </div>

      <div class="progression-section">
        <div class="section-header-inline">
          <div class="progression-title">Top Warming Rail Corridors</div>
          <span class="section-subtitle">Click to locate</span>
        </div>
        <div class="corridors-list">
          ${corridorRowsHtml}
        </div>
      </div>
    `;

    // Bind click events on corridor items to fly to coordinates
    body.querySelectorAll('.corridor-item').forEach(el => {
      el.addEventListener('click', () => {
        const lat = parseFloat(el.dataset.lat);
        const lon = parseFloat(el.dataset.lon);
        if (!isNaN(lat) && !isNaN(lon) && map) {
          map.flyTo({
            center: [lon, lat],
            zoom: 9.5,
            essential: true
          });
        }
      });
    });

  } catch (err) {
    console.error('Failed to load decadal climate trends:', err);
    body.innerHTML = `<div class="drawer-loading">Unable to load climate trend analysis.</div>`;
  }
}

/**
 * Initializes the MapLibre map and binds event handlers.
 */
function initApp() {
  // Start the fetch immediately from the v3 dual-engine forecast GeoJSON
  const dataPromise = fetch(import.meta.env.BASE_URL + 'data/pk_rail_forecast_v3.geojson').then(r => {
    if (!r.ok) throw new Error(`HTTP ${r.status}: ${r.statusText}`);
    return r.json();
  });

  // OpenFreeMap Positron vector basemap
  const map = new Map({
    container: 'map',
    style: 'https://tiles.openfreemap.org/styles/positron',
    center: [69.34, 29.8],
    zoom: 5.4
  });

  window.map = map;

  map.addControl(new NavigationControl({ showCompass: true }), 'top-right');

  // Register map.on('load') synchronously right after new Map(...)
  map.on('load', async () => {
    try {
      const geojsonData = await dataPromise;

      // Build a Map from osm_id to { km: sum of length_km, count: number of pieces }
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

      // Compute summary totals from the single fetched object
      computeTotals(geojsonData);

      const statusEl = document.getElementById('status-line');
      if (statusEl) {
        statusEl.textContent = `Active Pipeline: ${geojsonData.features.length} rail segments loaded`;
      }

      // Updates layer filter based on active property and checkbox states
      function updateLayerFilter() {
        if (!map.getLayer('rail-lines')) return;
        const activeTiers = TIERS.filter(tier => checkboxState[tier]);

        if (activeTiers.length === 0) {
          map.setFilter('rail-lines', ['==', ['literal', 1], 2]);
        } else if (activeTiers.length === TIERS.length) {
          map.setFilter('rail-lines', null);
        } else {
          map.setFilter('rail-lines', ['in', ['get', activeProp], ['literal', activeTiers]]);
        }
      }

      // Updates line layer color based on active exposure mode
      function updateLayerColor() {
        if (!map.getLayer('rail-lines')) return;
        map.setPaintProperty('rail-lines', 'line-color', [
          'match',
          ['get', activeProp],
          'extreme', TIER_COLORS.extreme,
          'high', TIER_COLORS.high,
          'elevated', TIER_COLORS.elevated,
          'moderate', TIER_COLORS.moderate,
          '#64748b'
        ]);
      }

      // Initialize UI controls
      renderFilterControls(updateLayerFilter);
      renderSummary();

      // Mode toggle buttons (Combined / Air / Ground)
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
          renderSummary();
        });
      });

      // Pass the already-fetched GeoJSON data directly to the map source
      map.addSource('rail-source', {
        type: 'geojson',
        data: geojsonData
      });

      // Highlight layer for the whole OSM way (long stretch) - underneath rail-lines
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

      // Main line layer colored by risk anomaly tier
      // Faintly fades low-confidence or non-mainline tracks using property styling
      map.addLayer({
        id: 'rail-lines',
        type: 'line',
        source: 'rail-source',
        layout: {
          'line-join': 'round',
          'line-cap': 'round'
        },
        paint: {
          'line-color': [
            'match',
            ['get', activeProp],
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
            4, 1.4,
            8, 2.8,
            12, 5.0
          ],
          'line-opacity': [
            'case',
            ['all', ['==', ['get', 'confidence'], 'high'], ['==', ['get', 'usage'], 'main']],
            0.95,
            ['==', ['get', 'confidence'], 'low'],
            0.35,
            0.65 // Medium confidence or non-mainline
          ]
        }
      });

      // Highlight layer for the single clicked piece - on top of rail-lines
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

      // Hover cursor styling
      map.on('mouseenter', 'rail-lines', () => {
        map.getCanvas().style.cursor = 'pointer';
      });
      map.on('mouseleave', 'rail-lines', () => {
        map.getCanvas().style.cursor = '';
      });

      let currentPopup = null;

      // Enhanced Dual-Engine Interactive Popup
      map.on('click', 'rail-lines', (e) => {
        if (!e.features || !e.features.length) return;
        const feature = e.features[0];
        const p = feature.properties;

        if (currentPopup) {
          const oldPopup = currentPopup;
          currentPopup = null;
          oldPopup.remove();
        }

        // Highlight whole way and the single clicked piece
        map.setFilter('way-highlight', ['==', ['get', 'osm_id'], p.osm_id]);
        map.setFilter('piece-highlight', [
          'all',
          ['==', ['get', 'osm_id'], p.osm_id],
          ['==', ['get', 'piece'], p.piece]
        ]);

        const lineName = p.name ? escapeHtml(p.name) : `Track Segment (OSM Way #${p.osm_id})`;
        const currentTier = p[activeProp] || 'moderate';
        const meta = TIER_META[currentTier] || TIER_META.moderate;
        const tierColor = meta.color;
        const tierDisplay = p.tier_label || meta.label;

        // Dual-Engine Badging
        const has86yr = Boolean(p.has_86yr_baseline);
        const engineBadgeClass = has86yr ? 'badge-punjab' : 'badge-national';
        const engineBadgeText = has86yr ? 'Punjab 86-Yr Z-Score Engine' : 'National Quantile Fallback';

        // Historical Z-Score & Nearest Station display
        const zScoreVal = p.z_score != null ? `${Number(p.z_score).toFixed(2)} \u03c3` : 'N/A (National Fallback)';
        const stationText = p.nearest_station_id
          ? `${escapeHtml(p.nearest_station_id)} (${Number(p.dist_to_station_km).toFixed(1)} km)`
          : `N/A (${Number(p.dist_to_station_km || 0).toFixed(1)} km from Punjab)`;

        // Forecast values
        const airP95 = p.forecast_air_p95_c != null
          ? `${Number(p.forecast_air_p95_c).toFixed(1)} \u00b0C`
          : (p.air_p95_c != null ? `${Number(p.air_p95_c).toFixed(1)} \u00b0C` : '\u2014');

        const soilP95 = p.forecast_soil_p95_c != null
          ? `${Number(p.forecast_soil_p95_c).toFixed(1)} \u00b0C`
          : (p.soil_p95_c != null ? `${Number(p.soil_p95_c).toFixed(1)} \u00b0C` : '\u2014');

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
              ${escapeHtml(tierDisplay)}
            </span>
          </div>
          <div class="popup-grid">
            <span class="popup-key">Historical Z-Score:</span>
            <span class="popup-val z-score-val">${escapeHtml(zScoreVal)}</span>
            <span class="popup-key">Nearest Station:</span>
            <span class="popup-val">${stationText}</span>
            <span class="popup-key">7-Day Forecast Air (P95):</span>
            <span class="popup-val">${airP95}</span>
            <span class="popup-key">7-Day Forecast Soil (P95):</span>
            <span class="popup-val">${soilP95}</span>
            <span class="popup-key">This piece:</span>
            <span class="popup-val">${thisPieceKm}</span>
            <span class="popup-key">Whole OSM way:</span>
            <span class="popup-val">${wholeWayStr}</span>
            <span class="popup-key">Usage / Confidence:</span>
            <span class="popup-val">${usageConfidence}</span>
          </div>
          <div class="popup-footnote">Pieces are ~1 km cuts of an OSM way.</div>
        `;

        const popup = new Popup({ closeButton: true, maxWidth: '350px' })
          .setLngLat(e.lngLat)
          .setHTML(popupHtml)
          .addTo(map);

        currentPopup = popup;

        popup.on('close', () => {
          if (currentPopup === popup) {
            currentPopup = null;
            map.setFilter('way-highlight', ['==', ['get', 'osm_id'], -1]);
            map.setFilter('piece-highlight', ['==', ['get', 'osm_id'], -1]);
          }
        });
      });

      // Initialize the Decadal Climate Shift Drawer
      initDecadalDrawer(map);

    } catch (err) {
      console.error('Failed to load rail forecast data:', err);
    }
  });
}

initApp();
