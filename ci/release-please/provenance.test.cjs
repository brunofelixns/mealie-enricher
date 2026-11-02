const {test} = require('node:test');
const assert = require('node:assert/strict');
const {validateRelease} = require('./provenance.cjs');
const release = {draft: false, prerelease: false, published_at: '2026-11-02',
  author: {login: 'release-bot[bot]'}};
const pull = {merge_commit_sha: 'a'.repeat(40), merged_at: '2026-11-02',
  base: {ref: 'main', repo: {full_name: 'owner/app'}},
  head: {ref: 'release-please--branches--main'},
  user: {type: 'Bot', login: 'release-bot[bot]'},
  labels: [{name: 'autorelease: tagged'}]};

test('accept a published release from the exact merged bot PR', () => {
  assert.doesNotThrow(() => validateRelease(release, [pull], 'a'.repeat(40), 'owner/app'));
});

for (const [name, badRelease, badPull] of [
  ['manual release', {...release, author: {login: 'person'}}, pull],
  ['draft', {...release, draft: true}, pull],
  ['wrong commit', release, {...pull, merge_commit_sha: 'b'.repeat(40)}],
  ['unmerged PR', release, {...pull, merged_at: null}],
  ['wrong source branch', release, {...pull, head: {ref: 'feature'}}],
  ['wrong target repo', release, {...pull, base: {...pull.base, repo: {full_name: 'other/app'}}}],
]) {
  test(`reject ${name}`, () => {
    assert.throws(() => validateRelease(badRelease, [badPull], 'a'.repeat(40), 'owner/app'));
  });
}
