# Pre-public Git history identity rewrite

Date: 2026-09-19

Before OMDA's first remote publication, the Owner authorized a one-time local
history rewrite so every reachable commit and annotated tag uses the public
GitHub identity:

`UvOrangeJuvO <68496891+UvOrangeJuvO@users.noreply.github.com>`

No remote existed and nothing had been pushed when the rewrite occurred. The
repository's file trees, commit messages, commit dates, branch topology and
stage tags were retained; commit object IDs necessarily changed because Git
includes author and committer identity in each commit object.

Historical governance and review documents intentionally retain some
pre-rewrite SHA values as documentary evidence of the local review exchanges.
Those identifiers are archival references and are not expected to resolve in
the public repository. Current authoritative identifiers are recorded in
`governance/PROJECT_STATE.json` and the latest section of the applicable review
verdict.

A complete pre-rewrite recovery bundle is stored locally at
`var/private-backups/omda-pre-public-history-2026-09-19.bundle`. The `var/`
directory is ignored by Git, so this private recovery artifact is not part of
the repository and must never be uploaded as a Release asset.
