# G4 Resume Report — after accepted G3-007 checkpoint

## Control decision

- Date: 2026-08-24
- Original G4 base / current `main`: `68e3d453c7b803d2090cb1318f48e58eb18d6390`
- Accepted G3-007 candidate: `960712ed4ee7b2890328f90c9ac4cc97a4f6fd35`
- G3-007 Reviewer acceptance commit: `28e652cd3ad979efefa4269aa26ded123015a434`
- G3-007 verdict: `reviews/stage-03/G3_007_REVIEW_VERDICT.md` — **ACCEPTED**
- Accepted architecture decision: `docs/adr/0002-production-album-source-and-runtime-boundary.md`
- Active branch: `exec/g4-agent-delivery`

G3-007 is closed as an independently reviewed corrective checkpoint. Its source-side contract,
curated data, provenance and cache changes are now authorized inputs to the resumed G4 work.

There is intentionally **no physical merge to `main` at this checkpoint**. G3-007 was created
on top of the still-unaccepted G4 commit chain. Merging this branch into `main` now would also
merge all unaccepted G4 production/delivery work and violate the exact-SHA Gate protocol. The
accepted checkpoint therefore remains in the audited G4 branch history and will enter `main`
only through the eventual controlled G4 merge after the complete G4 candidate is accepted.
No cherry-pick/rebase/history rewrite is authorized or necessary.

## Restored G4 state

G4 returns from `BLOCKED_ARCHITECTURE` to the ordinary **CHANGES_REQUESTED** repair/re-review
loop. ADR-0002 is accepted and `blocking_adr` is cleared. G5 remains prohibited.

The Executor must read together:

1. `reviews/stage-04/REVIEW_VERDICT.md`, especially **G4 Re-review 4**;
2. `reviews/stage-04/ADR_0002_REVIEW.md`;
3. accepted `docs/adr/0002-production-album-source-and-runtime-boundary.md`, especially
   §5 acceptance tests and §8 Reviewer constraints;
4. accepted G3-007 source contracts and final verdict.

## Remaining authorized G4 repair scope

The resumed implementation must produce one cumulative G4 candidate against the unchanged
original base and close the following already-authorized work:

- **Production source composition / G4-007B:** use the accepted `CuratedAlbumSource`,
  `GenreSourceDescriptor`, `CandidateBatch`, SourceRegistry and `ValidatedSourceSet`; validate
  after FETCH and before SELECT, delivery claim or official-history mutation. External delivery
  must reject every sample/demo/missing/contradictory/forged source, while the real reviewed
  curated 3×3 path succeeds and traces outbound facts plus committed MBIDs to the same validated
  source set.
- **ADR-0001 binding / G4-002C:** enforce existing operation key run/channel/digest equality and
  attempt/receipt/operation association transactionally in SQLite and in-memory parity.
- **Migration / G4-002D + ADR-0002 D7:** implement and test the approved non-destructive v3
  forward migration for fresh, v1, both v2 physical layouts and v3; future/unknown layouts fail
  closed; never synthesize or delete delivery evidence.
- **Provider classification docs / G4-002E:** align documentation exactly with implemented
  ambiguity rules.
- **Token precedence / G4-007C:** distinguish omitted CLI override from an explicit override;
  cover config-only, CLI-override and missing-token public entrypoint paths without exposing the
  secret.
- **Deterministic v0.1 runtime / G4-009 + ADR-0002 D8:** config permits only deterministic mode,
  performs no external LLM call, stores a typed deterministic marker and does not fabricate a
  narrative or expose an unimplemented provider surface.
- **Runtime evidence / ADR-0002 §8.8:** journal the validated Genre and Album source IDs/digests,
  schema/query-policy/package versions and preserve traceability through outbound facts and
  official history.
- Apply the Master Plan / Implementation Plan amendments explicitly authorized by ADR-0002.

## Required acceptance evidence

- Run all ADR-0002 AC-1 through AC-8 and AC-9A tests; AC-9B remains conditional on the still
  undecided ODP-1 live-search path and must not be implemented implicitly.
- Re-run the full repository suite, Ruff and `git diff --check`.
- Do not weaken/delete existing G3-007 or G4 regression tests.
- Produce updated `reviews/stage-04/REPAIR_REPORT.md`, test evidence and `PROJECT_STATE` set to
  `G4 / READY_FOR_REVIEW`.
- Commit a new cumulative candidate and stop. Only the Reviewer may mark G4 `ACCEPTED`; do not
  merge, tag or begin G5 before that verdict.

## State result

**G3-007: CLOSED / ACCEPTED**

**G4: RESUMED / CHANGES_REQUESTED**

**G5: NOT AUTHORIZED**
