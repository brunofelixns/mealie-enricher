// Validate API evidence before checking out or executing the release tree.
function validateRelease(release, pulls, sha, repository) {
  if (release.draft || release.prerelease || !release.published_at) {
    throw new Error('Se requiere una release estable publicada');
  }
  const match = pulls.some(pull =>
    pull.merge_commit_sha === sha && pull.merged_at &&
    pull.base.ref === 'main' && pull.base.repo.full_name === repository &&
    pull.head.ref === 'release-please--branches--main' &&
    pull.user.type === 'Bot' && pull.user.login === release.author.login &&
    pull.labels.some(label => label.name === 'autorelease: tagged')
  );
  if (!match) throw new Error('La release debe proceder de la PR de versión fusionada en ese commit');
}

module.exports = {validateRelease};
