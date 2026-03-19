/**
 * Frontend logic for the Radio Noise Calculator.
 * Handles: search (Overpass → map), simulate (noise model), choose-on-map (pick lat/lon).
 */

// ── DOM references ───────────────────────────────────────────────────────────
const searchForm    = document.getElementById('search-form');
const mapContainer  = document.getElementById('map-container');
const mapLoading    = document.getElementById('map-loading');
const metaCount     = document.getElementById('household-count');
const simulateBtn   = document.getElementById('simulate-btn');
const resultBox     = document.getElementById('result-box');
const resultValue   = document.getElementById('result-value');
const resultMeta    = document.getElementById('result-meta');

// Keys must match backend error keys (routes returns errors.lat, errors.form, etc.)
const searchErrorFields = {
  lat:    document.getElementById('error-lat'),
  lon:    document.getElementById('error-lon'),
  radius: document.getElementById('error-radius'),
  form:   document.getElementById('form-error'),
};

const simErrorFields = {
  freq:    document.getElementById('error-freq'),
  eirp:    document.getElementById('error-eirp'),
  height:  document.getElementById('error-height'),
  n_s:     document.getElementById('error-n_s'),
  epsilon: document.getElementById('error-epsilon'),
  sigma:   document.getElementById('error-sigma'),
  form:    document.getElementById('sim-form-error'),
};

let householdsReady = false;  // simulate button enabled only after a successful search

function clearErrors(fields) {
  Object.values(fields).forEach((el) => { if (el) el.textContent = ''; });
}

function setErrors(fields, errors) {
  // errors = { lat: "msg", form: "msg", ... }; falls back to fields.form if key missing
  Object.entries(errors).forEach(([key, msg]) => {
    const el = fields[key] || fields.form;
    if (el) el.textContent = msg;
  });
}

function setLoading(btn, isLoading) {
  if (isLoading) {
    btn.classList.add('loading');
    btn.disabled = true;
  } else {
    btn.classList.remove('loading');
    // Re-enable simulate only when households are ready.
    if (btn === simulateBtn) {
      btn.disabled = !householdsReady;
    } else {
      btn.disabled = false;
    }
  }
}

// ── Search ──────────────────────────────────────────────────────────────────

async function submitSearch(event) {
  event.preventDefault();
  clearErrors(searchErrorFields);
  resultBox.hidden = true;
  stopChooseOnMap();  // cancel pick mode before replacing map (iframe gets destroyed)

  const searchBtn = document.getElementById('search-btn');
  setLoading(searchBtn, true);
  mapLoading.classList.add('is-loading');
  mapLoading.setAttribute('aria-hidden', 'false');

  const formData = new FormData(searchForm);  // FormData reads input values by name
  const jsonData = {
    lat:    formData.get('lat'),
    lon:    formData.get('lon'),
    radius: formData.get('radius'),
  };

  try {
    const resp = await fetch('/search', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(jsonData),
    });

    const data = await resp.json();

    if (!resp.ok) {
      setErrors(searchErrorFields, data.errors || { form: 'An unexpected error occurred.' });
      householdsReady = false;
      simulateBtn.disabled = true;
      return;
    }

    if (data.map_html) {
      mapContainer.innerHTML = data.map_html;  // Folium injects an iframe with the map
      setTimeout(() => {
        // Leaflet needs invalidateSize after container is shown
        mapContainer.querySelectorAll('.leaflet-container').forEach((m) => {
          if (m._leaflet_id && m._leaflet_map) m._leaflet_map.invalidateSize();
        });
      }, 200);
    }

    if (data.meta && typeof data.meta.household_count !== 'undefined') {
      metaCount.textContent = String(data.meta.household_count);
    }

    householdsReady = true;
    simulateBtn.disabled = false;

  } catch (err) {
    setErrors(searchErrorFields, { form: 'Network error while fetching map. Please try again.' });
    console.error(err);
  } finally {
    setLoading(searchBtn, false);
    mapLoading.classList.remove('is-loading');
    mapLoading.setAttribute('aria-hidden', 'true');
  }
}

// ── Simulate ─────────────────────────────────────────────────────────────────

async function submitSimulation() {
  clearErrors(simErrorFields);
  resultBox.hidden = true;
  setLoading(simulateBtn, true);

  const jsonData = {  // read from input elements by id (must match index.html)
    freq:    document.getElementById('freq').value,
    eirp:    document.getElementById('eirp').value,
    height:  document.getElementById('height').value,
    n_s:     document.getElementById('n_s').value,
    epsilon: document.getElementById('epsilon').value,
    sigma:   document.getElementById('sigma').value,
  };

  try {
    const resp = await fetch('/simulate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(jsonData),
    });

    let data;
    try {
      data = await resp.json();
    } catch (_) {
      // e.g. server returned "NaN" or malformed JSON
      setErrors(simErrorFields, { form: 'Invalid response from server. See console for details.' });
      return;
    }

    if (!resp.ok) {
      setErrors(simErrorFields, data.errors || { form: 'An unexpected error occurred.' });
      return;
    }

    resultValue.textContent = Number(data.received_power).toFixed(2);
    resultMeta.textContent  = `Computed from ${data.source_count} noise source(s).`;
    resultBox.hidden = false;

  } catch (err) {
    setErrors(simErrorFields, { form: `Network error during simulation: ${err.message}` });
    console.error(err);
  } finally {
    setLoading(simulateBtn, false);
  }
}

// ── Choose on map ────────────────────────────────────────────────────────────
// Folium renders the map inside an iframe; we access Leaflet via iframe.contentWindow.

const chooseOnMapBtn  = document.getElementById('choose-on-map-btn');
const mapPickOverlay  = document.getElementById('map-pick-overlay');

/** Return the Leaflet L.Map instance inside the Folium iframe, or null. */
function getFoliumLeafletMap() {
  // Folium renders its map HTML inside an <iframe>
  const iframe = mapContainer.querySelector('iframe');
  if (!iframe || !iframe.contentWindow) return null;
  const iWin = iframe.contentWindow;
  // Leaflet stores every map instance in L.map._instances (Leaflet >=1.6),
  // but the most reliable way is to search iWin for variables that are L.Map instances.
  if (!iWin.L) return null;
  // Iterate all own properties of the iframe window looking for a Leaflet Map.
  for (const key of Object.keys(iWin)) {
    const val = iWin[key];
    if (val && val instanceof iWin.L.Map) return val;
  }
  return null;
}

let _pickHandler = null;

function startChooseOnMap() {
  const map = getFoliumLeafletMap();
  if (!map) return;

  // Show hint banner and toggle button state
  mapPickOverlay.hidden = false;
  chooseOnMapBtn.textContent = 'Cancel';
  chooseOnMapBtn.classList.add('active');

  // Use Leaflet's crosshair cursor while picking
  map.getContainer().style.cursor = 'crosshair';

  _pickHandler = function(e) {
    // e.latlng = { lat, lng } from Leaflet click event
    document.getElementById('lat').value = e.latlng.lat.toFixed(6);
    document.getElementById('lon').value = e.latlng.lng.toFixed(6);
    stopChooseOnMap();
  };
  map.once('click', _pickHandler);  // one-shot: handler auto-removed after first click
}

function stopChooseOnMap() {
  mapPickOverlay.hidden = true;
  chooseOnMapBtn.textContent = 'Choose on map';
  chooseOnMapBtn.classList.remove('active');

  const map = getFoliumLeafletMap();
  if (map) {
    map.getContainer().style.cursor = '';
    if (_pickHandler) {
      map.off('click', _pickHandler);  // remove if user cancelled before clicking
      _pickHandler = null;
    }
  }
}

if (chooseOnMapBtn) {
  chooseOnMapBtn.addEventListener('click', () => {
    if (chooseOnMapBtn.classList.contains('active')) {
      stopChooseOnMap();
    } else {
      startChooseOnMap();
    }
  });
}

// ── Event listeners ───────────────────────────────────────────────────────────

searchForm.addEventListener('submit', submitSearch);   // form submit → POST /search
simulateBtn.addEventListener('click', submitSimulation);  // button click → POST /simulate
