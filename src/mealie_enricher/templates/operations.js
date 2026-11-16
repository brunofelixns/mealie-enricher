(function () {
  'use strict';
  var token = '';
  var connectionVersion = 0;
  var backfillAccepted = false;
  var pricingBusy = false;
  var pricingRunning = false;
  var pollBusy = false;
  var pricingEnabled = document.getElementById('pricing-panel').dataset.enabled === 'true';
  var stages = {
    selecting_postal_code: 'Seleccionando código postal', categories: 'Consultando categorías',
    products: 'Descargando productos', publishing: 'Guardando catálogo', refreshing: 'Actualizando precios de recetas', waiting_catalog: 'Esperando el catálogo de Mercadona'
  };
  function byId(id) { return document.getElementById(id); }
  function text(id, value) { byId(id).textContent = value == null ? '—' : String(value); }
  function date(value) { return value ? new Date(value * 1000).toLocaleString() : 'Todavía no'; }
  function duration(value) {
    if (value == null) return 'Sin estimación';
    var seconds = Math.max(0, Math.round(value));
    if (seconds < 60) return seconds + ' s';
    if (seconds < 3600) return Math.floor(seconds / 60) + ' min ' + seconds % 60 + ' s';
    return Math.floor(seconds / 3600) + ' h ' + Math.floor(seconds % 3600 / 60) + ' min';
  }
  function showResult(message, data, error) {
    byId('operation-result').hidden = false;
    byId('operation-message').className = error ? 'op-error' : '';
    text('operation-message', message);
    text('operation-json', typeof data === 'string' ? data : JSON.stringify(data, null, 2));
  }
  async function request(endpoint, method, body) {
    var headers = {};
    var version = connectionVersion;
    if (endpoint.indexOf('/pricing/') === 0) {
      if (!token) throw new Error('Introduce el token administrativo y pulsa Conectar.');
      headers.Authorization = 'Bearer ' + token;
    }
    var controller = new AbortController();
    var timer = setTimeout(function () { controller.abort(); }, 15000);
    try {
      var options = { method: method || 'GET', headers: headers, cache: 'no-store', credentials: 'same-origin', redirect: 'error', signal: controller.signal };
      if (body !== undefined) { headers['Content-Type'] = 'application/json'; options.body = JSON.stringify(body); }
      var response = await fetch(endpoint, options);
      var raw = await response.text();
      if (endpoint.indexOf('/pricing/') === 0 && version !== connectionVersion) {
        throw new Error('La conexión de precios ha cambiado.');
      }
      var data;
      try { data = JSON.parse(raw); } catch (_) { data = raw; }
      if (!response.ok) {
        var detail = data && (data.error || data.message);
        var failure = new Error('HTTP ' + response.status + ': ' + (detail || raw || response.statusText));
        failure.status = response.status;
        throw failure;
      }
      return { status: response.status, data: data };
    } catch (error) {
      if (error.name === 'AbortError') throw new Error('La consulta ha tardado demasiado. Comprueba la conexión antes de repetir una acción.');
      throw error;
    } finally { clearTimeout(timer); }
  }
  function updatePricingButtons() {
    document.querySelectorAll('[data-pricing-action]').forEach(function (button) {
      button.disabled = !token || pricingBusy || pricingRunning;
    });
    byId('pricing-force').disabled = !token || pricingBusy || pricingRunning;
  }
  function renderProgress(data) {
    pricingRunning = Boolean(data.running);
    var label = pricingRunning ? (stages[data.stage] || 'Preparando operación') : ({ idle: 'Sin operaciones activas', partial: 'Revisión pendiente', error: 'La operación ha fallado', interrupted: 'Operación interrumpida', waiting_catalog: 'Esperando el catálogo de Mercadona' }[data.phase] || 'Sin operaciones activas');
    text('pricing-stage', label);
    text('pricing-counter', data.total == null ? 'Total todavía desconocido' : data.completed + ' / ' + data.total + (data.percent == null ? '' : ' · ' + data.percent + ' %'));
    if (data.percent == null) byId('pricing-progress').removeAttribute('value');
    else byId('pricing-progress').value = data.percent;
    byId('pricing-progress').hidden = !pricingRunning;
    text('pricing-postal', data.postal_code);
    text('pricing-catalog', data.catalog_ready ? 'Disponible' : 'Esperando la primera descarga completa');
    text('pricing-elapsed', duration(data.elapsed_seconds));
    text('pricing-eta', duration(data.eta_seconds));
    var activity = data.last_activity_at ? 'Último avance: ' + date(data.last_activity_at) : 'Todavía no hay actividad registrada.';
    if (pricingRunning && data.seconds_since_activity > 120) activity += ' · Sin avance reciente; comprueba el estado completo.';
    if (pricingRunning && data.current) activity += ' · Elemento: ' + data.current;
    text('pricing-activity', activity);
    byId('pricing-error').hidden = !data.last_error;
    text('pricing-error', data.last_error_detail || data.last_error);
    renderRecipeProgress(data.recipes, data.phase);
    updatePricingButtons();
  }
  function renderRecipeProgress(recipes, phase) {
    byId('pricing-recipes').hidden = !recipes;
    if (!recipes) return;
    text('pricing-recipes-state', recipes.running ? 'Actualización en curso' : (phase === 'idle' ? 'Revisión terminada' : 'Revisión pendiente o interrumpida'));
    text('pricing-recipes-count', recipes.completed + ' / ' + (recipes.total == null ? '-' : recipes.total) + ' revisadas · ' + recipes.succeeded + ' sin fallo técnico · ' + recipes.failed + ' con error o pendientes');
    text('pricing-recipes-prices', recipes.priced == null ? '' : recipes.priced + ' con coste completo · ' + recipes.incomplete + ' pendientes de datos');
    text('pricing-recipe-current', recipes.current ? (recipes.running ? 'Receta actual: ' : 'Última receta revisada: ') + recipes.current : 'Preparando la revisión de recetas.');
    if (recipes.total) byId('pricing-recipes-progress').value = Math.min(100, recipes.completed / recipes.total * 100);
    else byId('pricing-recipes-progress').removeAttribute('value');
    byId('pricing-recipes-progress').hidden = !recipes.running;
  }
  function renderStatus(data) {
    text('pricing-success', date(data.last_success));
    text('pricing-next', data.auto_sync ? date(data.next_run) : 'Programación desactivada');
    if (data.progress) renderProgress(data.progress);
    byId('pricing-live').hidden = false;
  }
  function disconnect() {
    connectionVersion += 1;
    token = '';
    pricingBusy = false;
    pollBusy = false;
    pricingRunning = false;
    byId('pricing-token').value = '';
    byId('pricing-live').hidden = true;
    byId('pricing-disconnect').hidden = true;
    text('pricing-connection', 'Sin conectar');
    updatePricingButtons();
  }
  function pricingError(error, version) {
    if (version !== connectionVersion) return;
    if (error.status === 401) disconnect();
    showResult(error.message, {}, true);
  }
  async function pollPricing() {
    if (!token || !pricingEnabled || pollBusy) return;
    var version = connectionVersion;
    pollBusy = true;
    try {
      var result = await request('/pricing/progress');
      if (!token) return;
      renderProgress(result.data);
      text('pricing-connection', 'Conectado · actualización automática');
      if (!result.data.running) renderStatus((await request('/pricing/status')).data);
    } catch (error) {
      if (version !== connectionVersion) return;
      if (error.status === 401) { pricingError(error, version); return; }
      text('pricing-connection', 'No se ha podido actualizar el estado');
      text('pricing-activity', error.message + ' Los datos visibles corresponden a la última consulta correcta.');
    } finally { if (version === connectionVersion) pollBusy = false; }
  }
  byId('pricing-connect-form').addEventListener('submit', async function (event) {
    event.preventDefault();
    var form = event.currentTarget;
    var button = form.querySelector('[type=submit]');
    if (button.disabled || !pricingEnabled) return;
    var enteredToken = byId('pricing-token').value.trim();
    disconnect();
    var version = connectionVersion;
    button.disabled = true;
    token = enteredToken;
    try {
      renderStatus((await request('/pricing/status')).data);
      byId('pricing-token').value = '';
      byId('pricing-disconnect').hidden = false;
      text('pricing-connection', 'Conectado · actualización automática');
    } catch (error) {
      if (version === connectionVersion) {
        disconnect();
        showResult(error.message, {}, true);
      }
    } finally { if (version === connectionVersion || !token) button.disabled = !pricingEnabled; }
  });
  byId('pricing-disconnect').addEventListener('click', disconnect);
  document.querySelectorAll('[data-pricing-action]').forEach(function (button) {
    button.addEventListener('click', async function () {
      if (pricingBusy || pricingRunning || !token) return;
      var version = connectionVersion;
      pricingBusy = true;
      updatePricingButtons();
      var endpoint = button.dataset.endpoint;
      if (button.dataset.pricingAction === 'refresh' && byId('pricing-force').checked) endpoint += '?force=true';
      try {
        var result = await request(endpoint, 'POST', {});
        showResult(result.data.status === 'running' ? 'Ya hay una operación en curso.' : 'Solicitud aceptada. El progreso se actualizará aquí; el trabajo todavía no ha terminado.', result.data);
        pricingRunning = true;
        await pollPricing();
      } catch (error) { pricingError(error, version); }
      finally { if (version === connectionVersion) { pricingBusy = false; updatePricingButtons(); } }
    });
  });
  byId('pricing-inspect').addEventListener('click', async function () {
    var version = connectionVersion;
    try {
      var result = await request('/pricing/status');
      renderStatus(result.data);
      showResult('Estado completo de Mercadona.', result.data);
    } catch (error) { pricingError(error, version); }
  });
  function bindForm(id, operation) {
    byId(id).addEventListener('submit', async function (event) {
      event.preventDefault();
      var button = event.currentTarget.querySelector('[type=submit]');
      if (button.disabled) return;
      button.disabled = true;
      try {
        var result = await operation();
        if (id === 'backfill-form' && result.status === 202) {
          backfillAccepted = true;
          byId('backfill-confirm').checked = false;
          byId('backfill-rearm').hidden = false;
        }
        showResult(result.status === 202 ? 'Solicitud aceptada. Consulta el historial para ver el resultado del procesamiento.' : 'Consulta completada.', result.data);
        if (typeof pollHistory === 'function') pollHistory();
      } catch (error) { showResult(error.message, {}, true); }
      finally { button.disabled = id === 'backfill-form' && backfillAccepted; }
    });
  }
  bindForm('recipe-action-form', function () {
    var slug = byId('recipe-slug').value.trim();
    if (!slug) throw new Error('Introduce el identificador de una receta.');
    return byId('recipe-action').value === 'webhook'
      ? request('/webhook', 'POST', { document_data: { recipe_slug: slug, document_type: 'recipe' } })
      : request('/estimate', 'POST', { content: { slug: slug } });
  });
  bindForm('backfill-form', function () {
    if (!byId('backfill-confirm').checked) throw new Error('Confirma el procesamiento en lote.');
    return request('/backfill', 'POST', {});
  });
  byId('backfill-rearm').addEventListener('click', function () {
    backfillAccepted = false;
    byId('backfill-form').querySelector('[type=submit]').disabled = false;
    byId('backfill-rearm').hidden = true;
    showResult('Comprueba en el historial que el lote anterior ha terminado antes de confirmar otro.', {});
  });
  bindForm('health-form', function () { return request('/health'); });
  bindForm('history-query-form', function () {
    var params = new URLSearchParams({ limit: byId('history-limit').value, offset: byId('history-offset').value });
    if (byId('history-since').value) params.set('since', String(new Date(byId('history-since').value).getTime()));
    return request('/estimator/history.json?' + params.toString());
  });
  updatePricingButtons();
  setInterval(pollPricing, 2500);
})();
