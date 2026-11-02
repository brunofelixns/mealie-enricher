// Validate API evidence before checking out or executing the release tree.
function validateRelease(release, pulls, sha, repository, appSlug = '') {
  const actors = new Set(['github-actions[bot]']);
  if (appSlug) {
    if (!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(appSlug)) throw new Error('Identidad de App inválida');
    actors.add(`${appSlug}[bot]`);
  }
  if (release.draft || release.prerelease || !release.published_at) {
    throw new Error('Se requiere una release estable publicada');
  }
  if (release.author.type !== 'Bot' || !actors.has(release.author.login)) {
    throw new Error('El autor de la release no es un bot configurado');
  }
  const match = pulls.some(pull =>
    pull.merge_commit_sha === sha && pull.merged_at &&
    pull.base.ref === 'main' && pull.base.repo.full_name === repository &&
    pull.head.ref === 'release-please--branches--main' && pull.head.repo?.full_name === repository &&
    pull.user.type === 'Bot' && actors.has(pull.user.login) &&
    pull.labels.some(label => label.name === 'autorelease: tagged')
  );
  if (!match) throw new Error('La release debe proceder de la PR de versión fusionada en ese commit');
}

module.exports = {validateRelease};
