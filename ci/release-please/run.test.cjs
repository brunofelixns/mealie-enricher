const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {Version} = require('release-please/build/src/version');
const {Generic} = require('release-please/build/src/updaters/generic');
const {GenericToml} = require('release-please/build/src/updaters/generic-toml');
const {PyProjectToml} = require('release-please/build/src/updaters/python/pyproject-toml');
const root = path.resolve(__dirname, '../..');

test('actual SDK updates only our lock entry and Docker version', () => {
  const config = JSON.parse(fs.readFileSync(path.join(root, 'release-please-config.json')));
  const version = Version.parse('2.3.4');
  const extra = config.packages['.']['extra-files'];
  const lockConfig = extra.find(file => file.path === 'uv.lock');
  const lock = new GenericToml(lockConfig.jsonpath, version).updateContent(
    'version = 1\n[[package]]\nname = "other"\nversion = "99.0.0"\n' +
    '[[package]]\nname = "mealie-enricher"\nversion = "1.0.0"\n'
  );
  assert.match(lock, /name = "other"\nversion = "99.0.0"/);
  assert.match(lock, /name = "mealie-enricher"\nversion = "2.3.4"/);
  const docker = new Generic({version}).updateContent(fs.readFileSync(path.join(root, 'Dockerfile'), 'utf8'));
  assert.match(docker, /^ARG VERSION=2\.3\.4$/m);
  assert.match(docker, /python:3\.14\.6-slim/);
  const project = new PyProjectToml({version}).updateContent(
    '[project]\nname="mealie-enricher"\nversion="1.0.0"\n'
  );
  assert.match(project, /version\s*=\s*"2\.3\.4"/);
});

test('manager recalculates policy after tagging the merged release', async () => {
  const {manage} = require('./run.cjs');
  let lastTag = '1.0.0';
  const proposals = [];
  const dispatched = [];
  await manage({
    createReleases: async () => {lastTag = '1.1.0'; return [{tagName: 'v1.1.0'}];},
    refreshPolicy: async () => lastTag === '1.1.0' ? '1.1.1' : '1.1.0',
    createPullRequests: async version => proposals.push(version),
    dispatch: async release => dispatched.push(release.tagName),
  });
  assert.deepEqual(proposals, ['1.1.1']);
  assert.deepEqual(dispatched, ['v1.1.0']);
});

test('a subsequent PR failure does not lose the created release dispatch', async () => {
  const {manage} = require('./run.cjs');
  const dispatched = [];
  await assert.rejects(manage({
    createReleases: async () => [{tagName: 'v1.0.1'}],
    dispatch: async release => dispatched.push(release.tagName),
    refreshPolicy: async () => '1.0.2',
    createPullRequests: async () => {throw new Error('API unavailable');},
  }), /API unavailable/);
  assert.deepEqual(dispatched, ['v1.0.1']);
});
