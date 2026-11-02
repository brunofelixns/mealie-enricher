// Official Release Please SDK; this dependency is used only in CI.
const {GitHub, Manifest} = require('release-please');
const {execFileSync} = require('node:child_process');
const {validateRelease} = require('./provenance.cjs');

async function dispatchValidation(github, repo, ref, tag) {
  const {data} = await github.rest.actions.listWorkflowRuns({
    ...repo, workflow_id: 'ci-release.yml', event: 'workflow_dispatch', branch: 'main', per_page: 100,
  });
  if (data.workflow_runs.some(run => run.display_title === `Publicar ${tag}` && run.status !== 'completed')) return;
  await github.rest.actions.createWorkflowDispatch({
    ...repo, workflow_id: 'ci-release.yml', ref, inputs: {release_tag: tag},
  });
}

async function manage({createReleases, refreshPolicy, createPullRequests, dispatch,
  recoverReleases = async () => [], assertCurrent = async () => {}}) {
  const releases = (await createReleases()).filter(Boolean);
  const scheduled = new Set();
  for (const release of releases) {
    await dispatch(release);
    scheduled.add(release.tagName);
  }
  for (const release of await recoverReleases()) {
    if (!scheduled.has(release.tagName)) await dispatch(release);
  }
  const version = await refreshPolicy();
  await assertCurrent();
  await createPullRequests(version);
  await assertCurrent();
  return releases;
}

async function findUnpublishedReleases(github, repo) {
  const releases = await github.paginate(github.rest.repos.listReleases, {...repo, per_page: 100});
  const pending = [];
  for (const release of releases) {
    if (release.draft || release.prerelease || release.author.type !== 'Bot' ||
        release.tag_name === 'v1.0.0' || release.tag_name === 'v1.13.0' ||
        !/^v\d+\.\d+\.\d+$/.test(release.tag_name) ||
        (release.body || '').includes('<!-- ghcr-evidence -->')) continue;
    let {data: {object}} = await github.rest.git.getRef({...repo, ref: `tags/${release.tag_name}`});
    for (let depth = 0; object.type === 'tag'; depth++) {
      if (depth > 5) throw new Error('Cadena de tags excesiva');
      const {data} = await github.rest.git.getTag({...repo, tag_sha: object.sha});
      object = data.object;
    }
    if (object.type !== 'commit') continue;
    const pulls = await github.paginate(github.rest.repos.listPullRequestsAssociatedWithCommit,
      {...repo, commit_sha: object.sha, per_page: 100});
    try {validateRelease(release, pulls, object.sha, `${repo.owner}/${repo.repo}`);}
    catch {continue;}
    pending.push({tagName: release.tag_name});
  }
  return pending;
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
    recoverReleases: () => findUnpublishedReleases(github, repo),
    assertCurrent: async () => {
      const {data} = await github.rest.git.getRef({...repo, ref: 'heads/main'});
      if (data.object.sha !== context.sha) throw new Error('main avanzó; reintentar sobre la revisión vigente');
    },
    refreshPolicy: async () => {
      execFileSync('git', ['fetch', 'origin', 'refs/heads/main:refs/remotes/origin/main', '--tags', '--no-recurse-submodules']);
      const current = execFileSync('git', ['rev-parse', 'refs/remotes/origin/main'], {encoding: 'utf8'}).trim();
      if (current !== context.sha) throw new Error('main avanzó; no proponer una versión sobre código antiguo');
      const result = execFileSync('python', ['ci/release_policy.py', 'plan'], {encoding: 'utf8'});
      return JSON.parse(result).next_version;
    },
    createPullRequests: async version => (await createManifest(version)).createPullRequests(),
  });
  core.setOutput('releases_created', releases.length > 0);
}

module.exports = {run, manage, findUnpublishedReleases};
