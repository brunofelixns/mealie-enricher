const {test} = require('node:test');
const assert = require('node:assert/strict');
const {validateRelease} = require('./provenance.cjs');
const release = {draft: false, prerelease: false, published_at: '2026-11-02',
  author: {type: 'Bot', login: 'github-actions[bot]'}};
const pull = {merge_commit_sha: 'a'.repeat(40), merged_at: '2026-11-02',
  base: {ref: 'main', repo: {full_name: 'owner/app'}},
  head: {ref: 'release-please--branches--main', repo: {full_name: 'owner/app'}},
  user: {type: 'Bot', login: 'github-actions[bot]'},
  labels: [{name: 'autorelease: tagged'}]};

test('configured App can release the existing legacy bot PR', () => {
  const appRelease = {...release, author: {type: 'Bot', login: 'mealie-release[bot]'}};
  const oldPull = {...pull, user: {type: 'Bot', login: 'github-actions[bot]'}};
  assert.doesNotThrow(() => validateRelease(appRelease, [oldPull], 'a'.repeat(40), 'owner/app', 'mealie-release'));
});

test('a different bot cannot forge matching PR and release authors', () => {
  const actor = {type: 'Bot', login: 'other-bot[bot]'};
  assert.throws(() => validateRelease({...release, author: actor}, [{...pull, user: actor}],
    'a'.repeat(40), 'owner/app', 'mealie-release'));
});

test('configured App can publish its own release PR', () => {
  const actor = {type: 'Bot', login: 'mealie-release[bot]'};
  assert.doesNotThrow(() => validateRelease({...release, author: actor}, [{...pull, user: actor}],
    'a'.repeat(40), 'owner/app', 'mealie-release'));
});

test('accept a published release from the exact merged bot PR', () => {
  assert.doesNotThrow(() => validateRelease(release, [pull], 'a'.repeat(40), 'owner/app'));
});

for (const [name, badRelease, badPull] of [
  ['manual release', {...release, author: {login: 'person'}}, pull],
  ['draft', {...release, draft: true}, pull],
  ['wrong commit', release, {...pull, merge_commit_sha: 'b'.repeat(40)}],
  ['unmerged PR', release, {...pull, merged_at: null}],
  ['wrong source branch', release, {...pull, head: {ref: 'feature'}}],
  ['fork source', release, {...pull, head: {...pull.head, repo: {full_name: 'fork/app'}}}],
  ['missing source repo', release, {...pull, head: {ref: pull.head.ref}}],
  ['wrong target repo', release, {...pull, base: {...pull.base, repo: {full_name: 'other/app'}}}],
]) {
  test(`reject ${name}`, () => {
    assert.throws(() => validateRelease(badRelease, [badPull], 'a'.repeat(40), 'owner/app'));
  });
}
