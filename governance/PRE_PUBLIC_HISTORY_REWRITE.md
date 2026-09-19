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

## Privacy scrub before the first Beta Release

After the initial `main` push but before any tag or Release existed, a dedicated
privacy audit found historical absolute workstation paths in review evidence.
With explicit Owner authorization, all local branches and stage tags were
rewritten again so those values use portable placeholders:

- `<REPO_ROOT>` for the repository checkout;
- `<WORKBUDDY_PYTHON>` for the Executor interpreter;
- `<OWNER_PREFACE_SOURCE>` for the local Owner-draft attachment;
- `<USER_HOME>` for any other local home-directory reference.

The same pass removed contiguous synthetic credential fixtures from old test
revisions and replaced one plausible-looking test-only email with a reserved
`.invalid` address. No real credential was found. The public `main` branch was
then updated only with `--force-with-lease`, conditional on the previously
verified remote commit, and audited again before the first Beta Release.

A second local-only recovery bundle is stored at
`var/private-backups/omda-pre-privacy-scrub-2026-09-19.bundle`. Like the earlier
bundle, it is ignored by Git and must never be uploaded or distributed.
