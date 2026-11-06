import 'maplibre-gl/dist/maplibre-gl.css';
import { Map, NavigationControl, Popup, setWorkerUrl } from 'maplibre-gl';
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?url';

setWorkerUrl(workerUrl);

const TIERS = ['moderate', 'elevated', 'high', 'extreme'];

const TIER_COLORS = {
  moderate: '#4575b4',
  elevated: '#fee090',
  high: '#f46d43',
  extreme: '#a50026'
};

const MODE_NAMES = {
  tier_rank: 'Combined',
  tier_air: 'Air',
  tier_soil: 'Ground'
};

// Application state
let activeProp = 'tier_rank';
const checkboxState = {
  moderate: true,
  elevated: true,
  high: true,
  extreme: true
};

const totalsByMode = {
  tier_rank: { moderate: 0, elevated: 0, high: 0, extreme: 0, total: 0 },
  tier_air: { moderate: 0, elevated: 0, high: 0, extreme: 0, total: 0 },
  tier_soil: { moderate: 0, elevated: 0, high: 0, extreme: 0, total: 0 }
};

/**
 * Escapes unsafe characters for HTML injection.
 * OpenStreetMap tag values like `name` can contain arbitrary characters.
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
 * Renders the tier filter checkboxes.
 */
function renderFilterControls(onFilterChange) {
  const container = document.getElementById('tier-filter-list');
  if (!container) return;

  container.innerHTML = '';

  TIERS.forEach(tier => {
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
    swatch.style.backgroundColor = TIER_COLORS[tier];

    const label = document.createElement('span');
    label.className = 'tier-label';
    label.textContent = tier;

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
          <span class="color-swatch" style="background-color: ${TIER_COLORS[tier]};"></span>
          ${tier}
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
          <th>Tier</th>
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
 * Initializes the MapLibre map and binds event handlers.
 */
function initApp() {
  // Start the fetch immediately
  const dataPromise = fetch('/data/pk_rail_heat_v2.geojson').then(r => {
    if (!r.ok) throw new Error(`HTTP ${r.status}: ${r.statusText}`);
    return r.json();
  });

  // Grayscale OpenStreetMap raster basemap
  const map = new Map({
    container: 'map',
    style: {
      version: 8,
      sources: {
        'osm-tiles': {
          type: 'raster',
          tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
          tileSize: 256,
          attribution: 'Railway data &copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> contributors. Weather data: <a href="https://open-meteo.com/" target="_blank" rel="noopener">Open-Meteo.com</a>.',
          maxzoom: 19
        }
      },
      layers: [
        {
          id: 'osm-tiles-layer',
          type: 'raster',
          source: 'osm-tiles',
          paint: {
            'raster-saturation': -1,
            'raster-contrast': 0.08,
            'raster-opacity': 0.9
          }
        }
      ]
    },
    center: [69.34, 29.8],
    zoom: 5.4
  });

  window.map = map;

  map.addControl(new NavigationControl({ showCompass: true }), 'top-right');

  // Register map.on('load') synchronously right after new Map(...), before any await
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
        statusEl.textContent = `Loaded ${geojsonData.features.length} features`;
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
          'moderate', TIER_COLORS.moderate,
          'elevated', TIER_COLORS.elevated,
          'high', TIER_COLORS.high,
          'extreme', TIER_COLORS.extreme,
          '#cccccc'
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
          'line-opacity': 0.8
        }
      });

      // Main line layer colored by tier
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
            'moderate', TIER_COLORS.moderate,
            'elevated', TIER_COLORS.elevated,
            'high', TIER_COLORS.high,
            'extreme', TIER_COLORS.extreme,
            '#cccccc'
          ],
          'line-width': [
            'interpolate',
            ['linear'],
            ['zoom'],
            4, 1.3,
            8, 2.5,
            12, 4.5
          ],
          'line-opacity': 0.9
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

      // Click popup displaying line and exposure details
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

        const lineName = p.name ? escapeHtml(p.name) : 'Unnamed Railway Line';
        const currentTier = p[activeProp] || 'unknown';
        const tierColor = TIER_COLORS[currentTier] || '#6b7280';
        const badgeTextColor = currentTier === 'elevated' ? '#1f2937' : '#ffffff';
        const modeLabel = MODE_NAMES[activeProp];

        const airP95 = p.air_p95_c != null ? `${Number(p.air_p95_c).toFixed(1)} °C` : '—';
        const soilP95 = p.soil_p95_c != null ? `${Number(p.soil_p95_c).toFixed(1)} °C` : '—';
        const diffVal = p.soil_minus_air_p95 != null
          ? `${Number(p.soil_minus_air_p95) > 0 ? '+' : ''}${Number(p.soil_minus_air_p95).toFixed(1)} °C`
          : '—';

        // Length calculations for single piece and whole OSM way
        const thisPieceKm = p.length_km != null ? `${Number(p.length_km).toFixed(2)} km` : '—';
        const wayInfo = waysMap.get(p.osm_id);
        const wayKm = wayInfo ? wayInfo.km : (Number(p.length_km) || 0);
        const wayKmFormatted = wayKm >= 100 ? wayKm.toFixed(1) : wayKm.toFixed(2);
        const pieceNum = (Number(p.piece) || 0) + 1;
        const totalPieces = wayInfo ? wayInfo.count : 1;
        const wholeWayStr = `${wayKmFormatted} km (piece ${pieceNum} of ${totalPieces})`;

        const popupHtml = `
          <div class="popup-title">${lineName}</div>
          <div class="popup-tier-badge" style="background-color: ${tierColor}; color: ${badgeTextColor};">
            ${escapeHtml(modeLabel)}: ${escapeHtml(currentTier)}
          </div>
          <div class="popup-grid">
            <span class="popup-key">Air (P95):</span>
            <span class="popup-val">${airP95}</span>
            <span class="popup-key">Soil (P95, 0–7 cm):</span>
            <span class="popup-val">${soilP95}</span>
            <span class="popup-key">Soil − Air (P95):</span>
            <span class="popup-val">${diffVal}</span>
            <span class="popup-key">This piece:</span>
            <span class="popup-val">${thisPieceKm}</span>
            <span class="popup-key">Whole OSM way:</span>
            <span class="popup-val">${wholeWayStr}</span>
            <span class="popup-key">Usage:</span>
            <span class="popup-val">${escapeHtml(p.usage || '—')}</span>
            <span class="popup-key">Gauge:</span>
            <span class="popup-val">${p.gauge ? escapeHtml(p.gauge) + ' mm' : '—'}</span>
            <span class="popup-key">Electrified:</span>
            <span class="popup-val">${escapeHtml(p.electrified || '—')}</span>
            <span class="popup-key">Confidence:</span>
            <span class="popup-val">${escapeHtml(p.confidence || '—')}</span>
            <span class="popup-key">Cell ID:</span>
            <span class="popup-val">${escapeHtml(p.cell_id || '—')}</span>
          </div>
          <div class="popup-footnote">Pieces are ~1 km cuts of an OSM way.</div>
        `;

        const popup = new Popup({ closeButton: true, maxWidth: '330px' })
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
    } catch (err) {
      console.error('Failed to load rail heat data:', err);
    }
  });
}

initApp();
