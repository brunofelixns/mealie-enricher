const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {Version} = require('release-please/build/src/version');
const {Generic} = require('release-please/build/src/updaters/generic');
const {GenericToml} = require('release-please/build/src/updaters/generic-toml');
const {PyProjectToml} = require('release-please/build/src/updaters/python/pyproject-toml');
const root = path.resolve(__dirname, '../..');

test('SDK file selection remains compatible with the patched minimatch', async () => {
  const {BranchFileCache} = require('@google-automations/git-file-utils');
  const cache = new BranchFileCache({}, {owner: 'owner', repo: 'app'}, 'main');
  cache.treeEntryIterator = async function* () {
    for (const path of ['pyproject.toml', 'ci/settings.toml', 'README.md']) yield {path};
  };
  assert.deepEqual(await cache.findFilesByGlob('**/*.toml'), ['pyproject.toml', 'ci/settings.toml']);
});

test('manifest produces the branch accepted by publication provenance', async () => {
  const {Manifest} = require('release-please');
  const baseline = JSON.parse(fs.readFileSync(path.join(root, '.release-please-manifest.json'), 'utf8'))['.'];
  const github = {
    repository: {owner: 'owner', repo: 'app', defaultBranch: 'main'},
    getFileJson: async name => JSON.parse(fs.readFileSync(path.join(root, name), 'utf8')),
    getFileContentsOnBranch: async name => ({parsedContent: fs.readFileSync(path.join(root, name), 'utf8')}),
    findFilesByFilenameAndRef: async () => [],
    releaseIterator: async function* () {yield {tagName: `v${baseline}`, sha: 'a'.repeat(40), notes: ''};},
    mergeCommitIterator: async function* () {
      yield {sha: 'b'.repeat(40), message: 'ops(ci): update pipeline', files: ['ci/example']};
      yield {sha: 'a'.repeat(40), message: 'chore: baseline', files: []};
    },
  };
  const manifest = await Manifest.fromManifest(github, 'main');
  const pulls = await manifest.buildPullRequests();
  assert.equal(pulls.length, 1);
  assert.equal(pulls[0].headRefName, 'release-please--branches--main');
});

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

test('real project lock stays byte-identical except for its own package version', () => {
  const config = JSON.parse(fs.readFileSync(path.join(root, 'release-please-config.json'), 'utf8'));
  const lockConfig = config.packages['.']['extra-files'].find(file => file.path === 'uv.lock');
  const before = fs.readFileSync(path.join(root, 'uv.lock'), 'utf8');
  const version = Version.parse('2.3.4');
  const after = new GenericToml(lockConfig.jsonpath, version).updateContent(before);
  const packageEntry = /\[\[package\]\]\r?\nname = "mealie-enricher"\r?\nversion = "[^"]+"/;
  assert.match(before, packageEntry);
  assert.equal(after, before.replace(packageEntry, entry => entry.replace(/version = "[^"]+"/, 'version = "2.3.4"')));
  const project = new PyProjectToml({version}).updateContent(fs.readFileSync(path.join(root, 'pyproject.toml'), 'utf8'));
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

test('rerun recovers a created release after dispatch failed', async () => {
  const {manage} = require('./run.cjs');
  const release = {tagName: 'v1.0.1'};
  const base = {
    refreshPolicy: async () => '1.0.2', createPullRequests: async () => {},
    recoverReleases: async () => [release],
  };
  await assert.rejects(manage({...base, createReleases: async () => [release],
    dispatch: async () => {throw new Error('dispatch failed');}}), /dispatch failed/);
  const recovered = [];
  await manage({...base, createReleases: async () => [],
    dispatch: async value => recovered.push(value.tagName)});
  assert.deepEqual(recovered, ['v1.0.1']);
});

test('main advancing before PR creation aborts the proposal', async () => {
  const {manage} = require('./run.cjs');
  const proposals = [];
  await assert.rejects(manage({
    createReleases: async () => [], dispatch: async () => {},
    refreshPolicy: async () => '1.0.1',
    assertCurrent: async () => {throw new Error('main advanced');},
    createPullRequests: async value => proposals.push(value),
  }), /main advanced/);
  assert.deepEqual(proposals, []);
});

test('recovery discovers only bot releases with a merged PR and no receipt', async () => {
  const {findUnpublishedReleases} = require('./run.cjs');
  const listReleases = () => {};
  const listPullRequestsAssociatedWithCommit = () => {};
  const release = {tag_name: 'v1.0.1', body: '', draft: false, prerelease: false,
    published_at: '2026-11-02', author: {type: 'Bot', login: 'github-actions[bot]'}};
  const pull = {merge_commit_sha: 'a'.repeat(40), merged_at: '2026-11-02',
    base: {ref: 'main', repo: {full_name: 'owner/app'}},
    head: {ref: 'release-please--branches--main', repo: {full_name: 'owner/app'}},
    user: {type: 'Bot', login: 'github-actions[bot]'}, labels: [{name: 'autorelease: tagged'}]};
  const github = {
    rest: {repos: {listReleases, listPullRequestsAssociatedWithCommit},
      git: {getRef: async () => ({data: {object: {type: 'commit', sha: 'a'.repeat(40)}}})}},
    paginate: async method => method === listReleases ? [release,
      {...release, tag_name: 'v1.0.2', body: '<!-- ghcr-evidence -->'},
      {...release, tag_name: 'v1.0.3', author: {type: 'User', login: 'owner'}},
      {...release, tag_name: 'v1.0.0'}] : [pull],
  };
  assert.deepEqual(await findUnpublishedReleases(github, {owner: 'owner', repo: 'app'}),
    [{tagName: 'v1.0.1'}]);
});
