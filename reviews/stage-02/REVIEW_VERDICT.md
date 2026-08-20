# Gate G2 Independent Re-review 6 Verdict

## Reviewed object

- Reviewer: GPT-5.6 Sol in Codex
- Review date: 2026-08-20
- Gate: G2 — Recommendation Core and recoverable transaction model
- Original base SHA: `731e0498fecdb0a28c84cf57d55c89569895a5bf`
- Previous candidate SHA: `0594b2774a3a5f07f15086dc1474af9d8ef5bce6`
- Previous Reviewer commit: `169e3eedd69710053e055c7a1b069c85c0dc0a85`
- New candidate SHA: `a9136bb25cd487f81255561a440fb5da1f424ad4`
- Candidate branch observed: `exec/g2-core`
- Executor report: `reviews/stage-02/EXECUTOR_REPORT.md`
- Repair report: `reviews/stage-02/REPAIR_REPORT.md`
- Test evidence: `reviews/stage-02/TEST_RESULTS.txt`

The candidate is a clean descendant of the exact accepted G1 base and contains the previous
Reviewer commit, two focused repair commits, and the handoff commit. The merge-base and
branch are correct, the worktree was clean at review start, `git diff --check` passed, and
no G3/G4 implementation was introduced.

The Reviewer independently ran the complete suite with cache disabled: **274 passed**. Ruff
also passed. The genuinely active solver path now has explicit pool and memo bounds; the
Reviewer independently exercised an exact 400-Genre active pool, which completed without
truncation in about 14.59 seconds. G2-013 is therefore closed.

One P1 remains. The Config change invokes the committed schema, but first applies the general
load-time `_normalise` function to an already-effective direct Config. That removes invalid
`None` values from non-nullable semantic fields, so the schema never sees them. Some malformed
nested direct values also fail through raw Python exceptions before reaching validation.

## Finding status summary

| Finding | Severity | Re-review status | Evidence |
|---|---:|---|---|
| G2-001 global ordered picks | P0 | **CLOSED** | Exact global records remain correct through commit and recovery. |
| G2-002 cooldown/diversity semantics | P1 | **CLOSED** | 30/31, stale history and active constraints pass. |
| G2-003 Album identity | P0 | **CLOSED** | Exact/canonical/ambiguity/Unicode protections remain passing. |
| G2-004 year fallback | P1 | **CLOSED** | Durable structured fallback evidence remains passing. |
| G2-005 crash/idempotency | P1 | **CLOSED** | Recovery remains journal-idempotent and never blindly re-delivers. |
| G2-006/G2-008 randomness provenance | P1 | **PARTIAL** | Valid configurations reproduce; a direct null semantic field can still create PLANNED before failure. |
| G2-007 equal-opportunity solver | P0 | **CLOSED** | Complete-space sampling remains unbiased; overflow is explicit, never truncated. |
| G2-009 receipt binding | P0 | **CLOSED** | Exact binding remains enforced before status interpretation. |
| G2-010 parent plumbing | P1 | **CLOSED** | Embedded and explicit parent memberships remain correct. |
| G2-011 configuration validation/immutability | P1 | **PARTIAL / OPEN** | Most direct fields now use Schema, but null and malformed nested types still bypass controlled validation. |
| G2-012 delivery ambiguity recovery | P1 | **CLOSED** | Success/failure/ambiguity classification and recovery pass. |
| G2-013 solver resource bounds | P1 | **CLOSED** | Active pool and memo caps are explicit; exact-cap active run terminated successfully. |

## Open blocking finding

### [P1] G2-011 — `_normalise` hides invalid nulls and nested types bypass controlled validation

- Location: `src/omda/config.py:46-118`; `tests/unit/test_config.py:222-282`
- Repaired:
  - ordinary scalar type/range violations now reach the committed config schema;
  - valid direct Config round-trips through `load_config`;
  - invalid delivery channel and the tested parent values reject before any run;
  - parent-map immutability remains correct.
- Remaining evidence:
  - `Config.__post_init__` validates `_normalise(config_to_dict(self))`;
  - `_normalise` removes every `None`, although only optional `seed` and
    `pushplus_token_env` may be omitted. Therefore `Config(daily_genre_count=None)` constructs
    successfully with an effective `None` count;
  - an independent run with that object wrote `PLANNED` and then raised an unhandled
    `TypeError`;
  - `Config(genre_parent_limits=None)` raises a raw `TypeError` while rendering the snapshot;
  - `Config(delivery={"channel": "markdown"})` raises a raw `AttributeError` before schema
    validation;
  - `DeliveryConfig(pushplus_token_env=123)` raises a raw regex `TypeError` rather than the
    controlled validation error required for a schema type violation;
  - the new tests cover string/bool/range cases and invalid channel, but not null semantic
    fields, container/nested-object types, or invalid environment-variable value types.
- Impact: the claimed complete boundary is not complete; a supported direct Config path can
  still leave a durable half-run and escape the bounded domain-error state machine.
- Required correction:
  - validate the exact effective snapshot without generically dropping nulls from required
    semantic fields;
  - omit only fields that are intentionally optional and unset (`seed` and
    `pushplus_token_env`), or express optional-null behavior explicitly in the schema;
  - guard/serialize malformed container and nested values so every direct field type reaches
    one controlled validation boundary rather than throwing `TypeError`/`AttributeError`;
  - keep the schema as the source of truth; do not add another drifting copy of all rules.
- Acceptance tests: direct `None` for each non-null semantic field; wrong type for
  `genre_parent_limits` and `delivery`; invalid type and pattern for `pushplus_token_env`;
  valid unset optionals; assert controlled rejection before any journal entry and no raw
  built-in exception after construction.

## Acceptance matrix

| G2 criterion | Status | Evidence |
|---|---|---|
| T2.1 equal opportunity | **PASS** | Complete-space sampling and overflow behavior pass. |
| T2.2 global cooldown/order | **PASS** | Global indices and cooldown boundaries pass. |
| T2.3 family/parent diversity and bounded result | **PASS** | Constraint correctness, active cap and memo cap pass independent review. |
| T2.4 Album identity/exclusion | **PASS** | Prior fixes remain passing. |
| T2.5 year/rating rules | **PASS** | Prior fixes remain passing. |
| T2.6 recoverable transaction | **PASS** | Delivery/recovery/history isolation pass. |
| Config/schema boundary | **PARTIAL** | Common invalid values reject; null/nested wrong types do not cross a controlled boundary. |
| Determinism/provenance | **PARTIAL** | Valid runs reproduce; a direct null count can journal before uncontrolled failure. |
| Core purity | **PASS** | Architecture tests pass. |
| No G3/G4 scope creep | **PASS** | Candidate remains within G2/foundation support and review files. |
| Review package / Git evidence | **PASS** | Exact SHAs, repair report and test output are committed. |

## Checks performed and limitations

- Verified exact base/candidate/previous-Reviewer ancestry, branch, repair chain, clean
  worktree and stage-02 package.
- Independently ran `pytest -q -p no:cacheprovider`: **274 passed**.
- Independently ran Ruff: **passed**.
- Ran `git diff --check`: **passed**.
- Re-ran prior valid/invalid scalar Config cases and valid round-trip behavior.
- Reproduced the direct null semantic field, wrong nested/container types and raw exception
  paths listed above.
- Independently exercised a genuinely active 400-Genre pool: exact unbiased solver completed
  in about 14.59 seconds, within both enforced bounds.
- Confirmed a pool over the active eligible cap fails immediately and explicitly.
- No production code, merge, tag, push, G3 work, live network or external service was used.

## Required repair scope

Remain on `exec/g2-core`. Repair only the final complete Config serialization/validation
boundary, focused regression tests and stage-02 evidence. Do not change solver bounds,
product defaults, selection rules, receipt logic or prior accepted behavior. Do not weaken
tests, merge, tag, push or enter G3. No ADR is needed.

## Verdict

**CHANGES_REQUESTED**

Open blocker: G2-011 (P1), PARTIAL. All recommendation, transaction and solver findings are
otherwise closed. G2 must not be merged and G3 must not begin. Acceptance applies only to a
future exact candidate after independent re-review.
