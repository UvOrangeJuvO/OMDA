# Stage-05 Review Package — G5 Release Audit

G5 starts from the controlled G4 merge commit
`d9944aa27bede364daf3ef93256016d5954792f6` on branch
`exec/g5-release-audit`.

This Gate is limited to the approved release-audit scope in
`governance/IMPLEMENTATION_PLAN.md` C.5:

- T5.1 clean-environment installation and dry-run verification;
- T5.2 end-to-end and failure-injection matrix;
- T5.3 secret/security scanning and dependency/data license inventory;
- T5.4 backup/restore rehearsal and contribution documentation;
- T5.5 at least seven controlled observations and a release-candidate proposal.

The Executor must place its cumulative report and reproducible evidence in this
directory, set `PROJECT_STATE` only to `READY_FOR_REVIEW`, commit one exact
candidate and stop. Only the Reviewer may produce the final release audit and
return `RELEASE_CANDIDATE_ACCEPTED`.

This initialization does not implement G5 tasks, create an RC/release tag,
enable automatic daily scheduling, push a ref, or publish anything.
