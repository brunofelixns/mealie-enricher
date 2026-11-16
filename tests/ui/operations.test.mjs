import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

// Minimal DOM boundary for the shipped script; HTTP responses are controlled here.
// No browser/network dependency, and no production test hooks or real credentials.
function harness(respond) {
  const nodes = new Map();
  function node(id, attrs = '') {
    return {
      id, value: attrs.match(/value="([^"]*)"/)?.[1] || '',
      hidden: /\bhidden\b/.test(attrs), disabled: false, checked: false,
      dataset: {}, textContent: '', listeners: {},
      addEventListener(type, handler) { this.listeners[type] = handler; },
      removeAttribute(name) { delete this[name]; },
      querySelector() { return this.button ||= node(id + '-submit'); },
      async fire(type) {
        if (this.disabled || (type === 'submit' && this.button?.disabled)) return;
        return this.listeners[type]?.({ currentTarget: this, preventDefault() {} });
      },
    };
  }
  const markup = fs.readFileSync('src/mealie_enricher/templates/operations.html', 'utf8');
  for (const match of markup.matchAll(/<\w+\b([^>]*\bid="([^"]+)"[^>]*)>/g)) {
    nodes.set(match[2], node(match[2], match[1]));
  }
  nodes.get('pricing-panel').dataset.enabled = 'true';
  const actions = ['sync', 'refresh'].map(action => {
    const button = node(action);
    button.dataset = { pricingAction: action, endpoint: '/pricing/' + action };
    return button;
  });
  const calls = [];
  vm.runInNewContext(fs.readFileSync('src/mealie_enricher/templates/operations.js', 'utf8'), {
    document: { getElementById: id => nodes.get(id), querySelectorAll: () => actions },
    fetch: async (url, options) => { calls.push({ url, ...options }); return respond(url, options); },
    AbortController, URLSearchParams, setTimeout, clearTimeout, setInterval() {},
  });
  return { nodes, calls, actions, async connect(token = 'synthetic-pricing-token') {
    nodes.get('pricing-token').value = token;
    await nodes.get('pricing-connect-form').fire('submit');
  } };
}
const response = (data, status = 200) => new Response(JSON.stringify(data), { status });
const status = () => response({ progress: { phase: 'idle', running: false, total: null, completed: 0 } });
function deferred() {
  let resolve;
  const promise = new Promise(done => { resolve = done; });
  return { promise, resolve };
}

test('disconnect ignores a late protected status response', async () => {
  const pending = deferred();
  let requests = 0;
  const app = harness(() => ++requests === 1 ? status() : pending.promise);
  await app.connect();
  const inspect = app.nodes.get('pricing-inspect').fire('click');
  await app.nodes.get('pricing-disconnect').fire('click');
  pending.resolve(status());
  await inspect;
  assert.equal(app.nodes.get('pricing-live').hidden, true);
  assert.equal(app.nodes.get('pricing-connection').textContent, 'Sin conectar');
});

test('a stale unauthorized response cannot disconnect a newer connection', async () => {
  const pending = deferred();
  let requests = 0;
  const app = harness(() => ++requests === 2 ? pending.promise : status());
  await app.connect('synthetic-old-token');
  const inspect = app.nodes.get('pricing-inspect').fire('click');
  await app.nodes.get('pricing-disconnect').fire('click');
  await app.connect('synthetic-new-token');
  pending.resolve(response({ error: 'old token rejected' }, 401));
  await inspect;
  assert.equal(app.nodes.get('pricing-live').hidden, false);
  assert.match(app.nodes.get('pricing-connection').textContent, /^Conectado/);
});

test('an accepted backfill stays latched until another batch is explicitly prepared', async () => {
  const app = harness(() => response({ status: 'accepted' }, 202));
  app.nodes.get('backfill-confirm').checked = true;
  await app.nodes.get('backfill-form').fire('submit');
  await app.nodes.get('backfill-form').fire('submit');
  assert.equal(app.calls.length, 1);
  assert.equal(app.nodes.get('backfill-confirm').checked, false);
  await app.nodes.get('backfill-rearm').fire('click');
  app.nodes.get('backfill-confirm').checked = true;
  await app.nodes.get('backfill-form').fire('submit');
  assert.equal(app.calls.length, 2);
});

test('recipe operations send the real endpoint payloads and report accepted work', async () => {
  const app = harness(() => response({ status: 'accepted' }, 202));
  app.nodes.get('recipe-slug').value = 'arroz-con-pollo';
  app.nodes.get('recipe-action').value = 'estimate';
  await app.nodes.get('recipe-action-form').fire('submit');
  assert.equal(app.calls[0].url, '/estimate');
  assert.deepEqual(JSON.parse(app.calls[0].body), { content: { slug: 'arroz-con-pollo' } });
  app.nodes.get('recipe-action').value = 'webhook';
  await app.nodes.get('recipe-action-form').fire('submit');
  assert.equal(app.calls[1].url, '/webhook');
  assert.deepEqual(JSON.parse(app.calls[1].body), { document_data: { recipe_slug: 'arroz-con-pollo', document_type: 'recipe' } });
  assert.match(app.nodes.get('operation-message').textContent, /Solicitud aceptada/);
});

test('forced pricing refresh uses the token and the existing force parameter', async () => {
  const app = harness((url, options) => options.method === 'POST' ? response({ status: 'accepted' }, 202) : (url === '/pricing/progress' ? response({ running: false }) : status()));
  await app.connect();
  app.nodes.get('pricing-force').checked = true;
  await app.actions[1].fire('click');
  const command = app.calls.find(call => call.method === 'POST');
  assert.equal(command.url, '/pricing/refresh?force=true');
  assert.equal(command.headers.Authorization, 'Bearer synthetic-pricing-token');
  assert.equal(app.nodes.get('pricing-token').value, '');
});
