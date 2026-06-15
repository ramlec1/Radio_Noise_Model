/**
 * Frontend logic for the Radio Noise Calculator.
 * Handles: propagation model UI, search (Overpass → map), simulate (noise model),
 * choose-on-map (pick lat/lon), and JSON download.
 */

// ── DOM references ───────────────────────────────────────────────────────────
const searchForm    = document.getElementById('search-form');
const mapContainer  = document.getElementById('map-container');
const mapLoading    = document.getElementById('map-loading');
const metaCount     = document.getElementById('household-count');
const simulateBtn   = document.getElementById('simulate-btn');
const resultBox      = document.getElementById('result-box');
const resultValue    = document.getElementById('result-value');
const resultMeta     = document.getElementById('result-meta');
const downloadJsonBtn = document.getElementById('download-json-btn');
const propModelsContainer = document.getElementById('propagation-models');
const addPropModelBtn = document.getElementById('add-prop-model-btn');
const propModelsError = document.getElementById('propagation-models-error');

// Keys must match backend error keys.
const searchErrorFields = {
  lat:    document.getElementById('error-lat'),
  lon:    document.getElementById('error-lon'),
  radius: document.getElementById('error-radius'),
  form:   document.getElementById('form-error'),
};

const simStaticErrorFields = {
  freq:            document.getElementById('error-freq'),
  eirp:            document.getElementById('error-eirp'),
  source_height:   document.getElementById('error-source_height'),
  receiver_height: document.getElementById('error-receiver_height'),
  form:            document.getElementById('sim-form-error'),
  propagation_models: propModelsError,
};

let householdsReady = false;

/** Registry fetched from /api/propagation-models on page load. */
let propagationRegistry = [];  // [{key, label, env_fields: {field_key: {label,type,min,max,default,step}}}]

/** Download data from the last successful simulation. */
let lastSimulationData = null;

// ── Error helpers ─────────────────────────────────────────────────────────────

function clearErrors(fields) {
  Object.values(fields).forEach((el) => { if (el) el.textContent = ''; });
}

function clearAllSimErrors() {
  clearErrors(simStaticErrorFields);
  // Clear per-model error elements
  propModelsContainer.querySelectorAll('.error').forEach((el) => { el.textContent = ''; });
}

function setErrors(fields, errors) {
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
    if (btn === simulateBtn) {
      btn.disabled = !householdsReady;
    } else {
      btn.disabled = false;
    }
  }
}

// ── Propagation model UI ──────────────────────────────────────────────────────

/**
 * Render the environment field inputs for a given model key inside a container element.
 */
function renderEnvFields(container, modelKey, index) {
  container.innerHTML = '';
  const modelMeta = propagationRegistry.find((m) => m.key === modelKey);
  if (!modelMeta) return;

  const fields = modelMeta.env_fields;
  if (Object.keys(fields).length === 0) {
    container.innerHTML = '<p class="prop-model-no-params">No additional parameters required.</p>';
    return;
  }

  Object.entries(fields).forEach(([fieldKey, fieldMeta]) => {
    const fieldDiv = document.createElement('div');
    fieldDiv.className = 'field';

    const label = document.createElement('label');
    label.setAttribute('for', `pm-${index}-${fieldKey}`);
    label.textContent = fieldMeta.label;

    const input = document.createElement('input');
    input.id = `pm-${index}-${fieldKey}`;
    input.name = `pm-${index}-${fieldKey}`;
    input.type = fieldMeta.type || 'number';
    if (fieldMeta.step !== undefined && fieldMeta.step !== null) input.step = String(fieldMeta.step);
    if (fieldMeta.min !== undefined && fieldMeta.min !== null) input.min = String(fieldMeta.min);
    if (fieldMeta.max !== undefined && fieldMeta.max !== null) input.max = String(fieldMeta.max);
    if (fieldMeta.default !== undefined && fieldMeta.default !== null) input.value = String(fieldMeta.default);

    const errorDiv = document.createElement('div');
    errorDiv.className = 'error';
    errorDiv.id = `error-pm-${index}-${fieldKey}`;

    fieldDiv.appendChild(label);
    fieldDiv.appendChild(input);
    fieldDiv.appendChild(errorDiv);
    container.appendChild(fieldDiv);
  });
}

/**
 * Create and append a propagation model block.
 * index: 0-based position; canDelete: whether to show a delete button.
 */
function addPropModelBlock(selectedKey) {
  const index = propModelsContainer.children.length;
  const canDelete = index > 0;

  const block = document.createElement('div');
  block.className = 'prop-model-block';
  block.dataset.index = String(index);

  // Header: dropdown + optional delete button
  const header = document.createElement('div');
  header.className = 'prop-model-header';

  const select = document.createElement('select');
  select.className = 'prop-model-select';
  select.id = `pm-${index}-model`;
  select.setAttribute('aria-label', 'Propagation model');
  propagationRegistry.forEach((m) => {
    const option = document.createElement('option');
    option.value = m.key;
    option.textContent = m.label;
    if (selectedKey && m.key === selectedKey) option.selected = true;
    select.appendChild(option);
  });

  const selectError = document.createElement('div');
  selectError.className = 'error';
  selectError.id = `error-pm-${index}-model`;

  const selectWrap = document.createElement('div');
  selectWrap.className = 'field prop-model-select-field';
  const selectLabel = document.createElement('label');
  selectLabel.setAttribute('for', `pm-${index}-model`);
  selectLabel.textContent = 'Model';
  selectWrap.appendChild(selectLabel);
  selectWrap.appendChild(select);
  selectWrap.appendChild(selectError);

  header.appendChild(selectWrap);

  if (canDelete) {
    const deleteBtn = document.createElement('button');
    deleteBtn.type = 'button';
    deleteBtn.className = 'btn-outline btn-delete-model';
    deleteBtn.setAttribute('aria-label', 'Remove this propagation model');
    deleteBtn.innerHTML = '<i class="fa-solid fa-trash"></i>';
    deleteBtn.addEventListener('click', () => removePropModelBlock(block));
    header.appendChild(deleteBtn);
  }

  // Environment fields container
  const envFields = document.createElement('div');
  envFields.className = 'prop-model-env-fields field-row';

  block.appendChild(header);
  block.appendChild(envFields);
  propModelsContainer.appendChild(block);

  // Render initial env fields for the selected model
  const initialKey = selectedKey || (propagationRegistry[0] && propagationRegistry[0].key);
  if (initialKey) renderEnvFields(envFields, initialKey, index);

  // Re-render env fields when model changes
  select.addEventListener('change', () => {
    renderEnvFields(envFields, select.value, index);
  });
}

function removePropModelBlock(block) {
  block.remove();
  // Re-index remaining blocks so IDs stay consistent
  Array.from(propModelsContainer.children).forEach((b, i) => {
    b.dataset.index = String(i);
    // Update select id/aria
    const sel = b.querySelector('select');
    if (sel) {
      sel.id = `pm-${i}-model`;
      const lbl = b.querySelector('.prop-model-select-field label');
      if (lbl) lbl.setAttribute('for', `pm-${i}-model`);
      const selErr = b.querySelector('.prop-model-select-field .error');
      if (selErr) selErr.id = `error-pm-${i}-model`;
    }
    // Update env field ids
    const envContainer = b.querySelector('.prop-model-env-fields');
    if (envContainer && sel) {
      const modelKey = sel.value;
      renderEnvFields(envContainer, modelKey, i);
    }
  });
}

// ── Load propagation registry on page load ────────────────────────────────────

async function loadPropagationRegistry() {
  try {
    const resp = await fetch('/api/propagation-models');
    if (!resp.ok) return;
    propagationRegistry = await resp.json();
    // Render the initial (mandatory) propagation model block
    if (propagationRegistry.length > 0) {
      addPropModelBlock(propagationRegistry[0].key);
    }
  } catch (err) {
    console.error('Failed to load propagation registry:', err);
  }
}

loadPropagationRegistry();

if (addPropModelBtn) {
  addPropModelBtn.addEventListener('click', () => {
    addPropModelBlock();
  });
}

// ── Search ──────────────────────────────────────────────────────────────────

async function submitSearch(event) {
  event.preventDefault();
  clearErrors(searchErrorFields);
  resultBox.hidden = true;
  stopChooseOnMap();

  const searchBtn = document.getElementById('search-btn');
  setLoading(searchBtn, true);
  mapLoading.classList.add('is-loading');
  mapLoading.setAttribute('aria-hidden', 'false');

  const formData = new FormData(searchForm);
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
      lastSimulationData = null;
      updateDownloadButtonState();
      simulateBtn.disabled = true;
      return;
    }

    if (data.map_html) {
      mapContainer.innerHTML = data.map_html;
      setTimeout(() => {
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
    // Reset download state; simulation has not run yet for this new search
    lastSimulationData = null;
    updateDownloadButtonState();

  } catch (err) {
    setErrors(searchErrorFields, { form: 'Network error while fetching map. Please try again.' });
    lastSimulationData = null;
    updateDownloadButtonState();
    console.error(err);
  } finally {
    setLoading(searchBtn, false);
    mapLoading.classList.remove('is-loading');
    mapLoading.setAttribute('aria-hidden', 'true');
  }
}

searchForm.addEventListener('submit', submitSearch);

// ── Refresh ──────────────────────────────────────────────────────────────────

async function loadPreviewMap() {
  const lat = document.getElementById('lat').value;
  const lon = document.getElementById('lon').value;
  const radius = document.getElementById('radius').value;
  const resp = await fetch('/refresh-map', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ lat, lon, radius }),
  });
  const data = await resp.json();
  if (!resp.ok) return;
  mapContainer.innerHTML = data.map_html;
}

const refreshBtn = document.getElementById('refresh-btn');
if (refreshBtn) {
  refreshBtn.addEventListener('click', loadPreviewMap);
}

// ── Choose on map ────────────────────────────────────────────────────────────

const chooseOnMapBtn  = document.getElementById('choose-on-map-btn');
const mapPickOverlay  = document.getElementById('map-pick-overlay');

function getFoliumLeafletMap() {
  const iframe = mapContainer.querySelector('iframe');
  if (!iframe || !iframe.contentWindow) return null;
  const iWin = iframe.contentWindow;
  if (!iWin.L) return null;
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

  mapPickOverlay.hidden = false;
  chooseOnMapBtn.textContent = 'Cancel';
  chooseOnMapBtn.classList.add('active');
  map.getContainer().style.cursor = 'crosshair';

  _pickHandler = function(e) {
    document.getElementById('lat').value = e.latlng.lat.toFixed(6);
    document.getElementById('lon').value = e.latlng.lng.toFixed(6);
    stopChooseOnMap();
  };
  map.once('click', _pickHandler);
}

function stopChooseOnMap() {
  mapPickOverlay.hidden = true;
  chooseOnMapBtn.textContent = 'Choose on map';
  chooseOnMapBtn.classList.remove('active');

  const map = getFoliumLeafletMap();
  if (map) {
    map.getContainer().style.cursor = '';
    if (_pickHandler) {
      map.off('click', _pickHandler);
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

// ── Download JSON ─────────────────────────────────────────────────────────────

function downloadSimulationJson() {
  if (!lastSimulationData) return;
  const json = JSON.stringify(lastSimulationData, null, 2);
  const blob = new Blob([json], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'radio_noise_simulation.json';
  a.click();
  URL.revokeObjectURL(url);
}

function updateDownloadButtonState() {
  if (downloadJsonBtn) {
    downloadJsonBtn.disabled = !lastSimulationData;
  }
}

if (downloadJsonBtn) {
  downloadJsonBtn.addEventListener('click', () => {
    downloadSimulationJson();
  });
}

// ── Simulate ─────────────────────────────────────────────────────────────────

/** Collect the current propagation model blocks into the JSON payload format. */
function collectPropModels() {
  const blocks = Array.from(propModelsContainer.children);
  return blocks.map((block, i) => {
    const select = block.querySelector('select');
    const modelKey = select ? select.value : '';

    const modelMeta = propagationRegistry.find((m) => m.key === modelKey);
    const envParams = {};
    if (modelMeta) {
      Object.keys(modelMeta.env_fields).forEach((fieldKey) => {
        const input = document.getElementById(`pm-${i}-${fieldKey}`);
        if (input) envParams[fieldKey] = input.value;
      });
    }
    return { model: modelKey, env_params: envParams };
  });
}

/** Display per-model errors returned from the backend (key format: pm-{i}-{field}). */
function setPropModelErrors(errors) {
  Object.entries(errors).forEach(([key, msg]) => {
    // Check for static sim fields first
    if (simStaticErrorFields[key]) {
      simStaticErrorFields[key].textContent = msg;
      return;
    }
    // Per-model errors: pm-0-n_s → error-pm-0-n_s
    const errorEl = document.getElementById(`error-${key}`);
    if (errorEl) {
      errorEl.textContent = msg;
    } else {
      // Fallback: show in the general sim error area
      const formErr = document.getElementById('sim-form-error');
      if (formErr) formErr.textContent = msg;
    }
  });
}

async function submitSimulation() {
  clearAllSimErrors();
  resultBox.hidden = true;
  setLoading(simulateBtn, true);

  const propModels = collectPropModels();

  const jsonData = {
    freq:             document.getElementById('freq').value,
    eirp:             document.getElementById('eirp').value,
    source_height:    document.getElementById('source_height').value,
    receiver_height:  document.getElementById('receiver_height').value,
    propagation_models: propModels,
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
      simStaticErrorFields.form.textContent = 'Invalid response from server. See console for details.';
      return;
    }

    if (!resp.ok) {
      setPropModelErrors(data.errors || { form: 'An unexpected error occurred.' });
      return;
    }

    resultValue.textContent = Number(data.received_power).toFixed(2);
    resultMeta.textContent  = `Computed from ${data.source_count} noise source(s).`;
    resultBox.hidden = false;

    // Store download data from simulation result
    lastSimulationData = data.download_data || null;
    updateDownloadButtonState();

  } catch (err) {
    simStaticErrorFields.form.textContent = `Network error during simulation: ${err.message}`;
    console.error(err);
  } finally {
    setLoading(simulateBtn, false);
  }
}

simulateBtn.addEventListener('click', submitSimulation);
