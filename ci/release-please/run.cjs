// Official Release Please SDK; this dependency is used only in CI.
const {GitHub, Manifest} = require('release-please');
const {execFileSync} = require('node:child_process');

async function dispatchValidation(github, repo, ref, tag) {
  await github.rest.actions.createWorkflowDispatch({
    ...repo, workflow_id: 'ci-release.yml', ref, inputs: {release_tag: tag},
  });
}

async function manage({createReleases, refreshPolicy, createPullRequests, dispatch}) {
  const releases = (await createReleases()).filter(Boolean);
  for (const release of releases) {
    await dispatch(release);
  }
  const version = await refreshPolicy();
  await createPullRequests(version);
  return releases;
}

async function run({github, context, core}) {
  const repo = context.repo;
  const sdk = await GitHub.create({
    ...repo, token: process.env.GH_TOKEN, defaultBranch: 'main',
  });
  const createManifest = version => Manifest.fromManifest(
    sdk, 'main', 'release-please-config.json', '.release-please-manifest.json',
    {}, undefined, version,
  );
  const releases = await manage({
    createReleases: async () => (await createManifest()).createReleases(),
    dispatch: release => dispatchValidation(github, repo, 'main', release.tagName),
    refreshPolicy: async () => {
      execFileSync('git', ['fetch', 'origin', '--tags', '--no-recurse-submodules']);
      const result = execFileSync('python', ['ci/release_policy.py', 'plan'], {encoding: 'utf8'});
      return JSON.parse(result).next_version;
    },
    createPullRequests: async version => (await createManifest(version)).createPullRequests(),
  });
  core.setOutput('releases_created', releases.length > 0);
}

module.exports = {run, manage};
