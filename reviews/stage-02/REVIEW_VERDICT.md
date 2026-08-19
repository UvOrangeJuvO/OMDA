# Gate G2 Independent Review Verdict

## Reviewed object

- Reviewer: GPT-5.6 Sol in Codex
- Review date: 2026-08-19
- Gate: G2 — Recommendation Core and recoverable transaction model
- Base SHA: `731e0498fecdb0a28c84cf57d55c89569895a5bf`
- Candidate SHA: `5ae45fe436cffa000cc0684f6768f0afb504edb6`
- Candidate branch observed: `exec/g2-core`
- Executor report: `reviews/stage-02/EXECUTOR_REPORT.md`
- Test evidence: `reviews/stage-02/TEST_RESULTS.txt`

The candidate is a clean descendant of the exact accepted G1 merge/tag and contains one Gate-start commit, four implementation commits and one handoff commit. The diff stays within G2 source, tests and governance artifacts and does not enter G3. `git diff --check` passed. The Reviewer independently ran the complete suite and Ruff: 179 tests passed and Ruff passed.

Passing committed tests are not sufficient for this Gate. Independent boundary probes found two direct product-invariant failures and several ineffective recovery/observability tests.

## Findings

### [P0] G2-001 — Every plan restarts official Genre pick indices at 1, so the second successful run delivers and then cannot commit

- Location: `src/omda/orchestrator/run.py:91-153` (`Plan.genre_picks()`, `digest()`, `from_digest()`); `src/omda/orchestrator/run.py:235-249` and `:363-369`; `src/omda/core/genre.py:49-83`
- Evidence:
  - `Plan.genre_picks()` and `Plan.digest()` always enumerate the current plan as indices `1..count`.
  - The Orchestrator never reads `HistoryPort.latest_pick_index()` when building a plan.
  - `next_pick_index()` derives a supposed global index only from histories for Genres currently returned by `GenreSource`; a historical pick for a now-hidden/ineligible Genre is therefore invisible.
- Independent reproduction: with ten eligible Genres and distinct Album pools, run 1 reaches `COMPLETE` and commits indices 1–3. Run 2 selects three different, non-cooled Genres and reaches external delivery, then raises `InvariantFailureError: pick_index 1 already in official history`; latest official index remains 3. The error is not converted into the explicit delivered-but-uncommitted recovery result because `_deliver_and_commit()` catches only `StateCommitFailureError`.
- Impact: OMDA cannot complete a normal second day. Worse, the second output may already have been delivered while its Genre/Album history is absent, enabling future repeats and leaving recovery in an unhandled state. This violates the central global cooldown and transaction invariants.
- Violated contract: Handoff Spec §2.2, §4 and §7.3/§7.10; Master Plan §3.1/§6; Implementation Plan I-2 and T2.2/T2.6.
- Required correction:
  - read the single authoritative global next pick index from `HistoryPort.latest_pick_index() + 1` before planning;
  - represent the exact ordered `GenrePickRecord` values in `Plan` (or equivalent), rather than regenerating local indices later;
  - preserve those exact indices in `digest()`/`from_digest()` and recovery;
  - validate the planned sequence before delivery so an index conflict cannot first appear after external delivery;
  - never infer the global clock only from the currently visible Genre source.
- Acceptance tests:
  - at least three consecutive successful runs commit 1–3, 4–6 and 7–9 with both fake and SQLite;
  - a historical latest pick belonging to a Genre absent from the current source still advances the next global index;
  - a failed run consumes no indices;
  - delivered recovery uses the exact persisted indices and does not regenerate 1–3.

### [P1] G2-002 — Multi-pick cooldown and diversity are solved as one first-position filter plus probabilistic retries

- Location: `src/omda/core/genre.py:54-94`; `src/omda/core/diversity.py`; `src/omda/ports/domain.py`, `GenreRef`
- Evidence:
  - cooldown filtering is performed once using a single `nxt`, then all daily picks are sampled from that fixed pool;
  - eligibility is not re-evaluated for the deterministic internal positions `n`, `n+1`, `n+2`;
  - a hard 200-attempt rejection loop may report `InsufficientCandidatesError` even when a valid combination exists;
  - only one `family` string is modeled; the required `parents` taxonomy/set constraint is absent despite the Genre schema already carrying parents.
- Independent reproductions:
  1. With global latest index 30, a Genre last picked at 1 is unavailable for position 31 but becomes valid at 32. A four-position satisfiable sequence exists, yet the current planner filters it out once at position 31 and reports only three available Genres.
  2. With 100 Regional Genres (limit 1) plus two unrestricted Genres, a valid three-Genre set always exists. Across 20 fixed seeds, the rejection solver falsely reported insufficiency 18 times.
- Impact: valid Genres can lose opportunities at later positions, and satisfiable daily plans can fail based solely on random luck. Parent overlap is not enforced. This undermines equal base opportunity and the bounded-explicit solver contract.
- Required correction:
  - solve an **ordered** daily pick sequence and evaluate cooldown at each exact global pick position;
  - use a bounded complete feasibility method (for example, enumerate/construct valid combinations then sample from the valid space) so a valid solution is not mislabeled impossible;
  - model and enforce configured family/parent set membership without turning it into scoring;
  - define and test the equality semantics after conditioning on explicit diversity constraints.
- Acceptance tests: position-specific 30/31 boundaries inside one run; satisfiable skewed-family pools succeed for every tested seed; truly unsatisfiable pools terminate explicitly; overlapping parents are constrained; deterministic replay retains exact ordered picks.

### [P0] G2-003 — Album identity matching can both repeat a previously recommended Album and permanently exclude an unrelated one

- Location: `src/omda/core/album.py:23-80`
- Evidence:
  - exact `album_id` matching is incorrectly guarded by `candidate.identity is not None`; an ordinary `AlbumCandidate` with no nested identity is not excluded even when its `album_id` exactly matches official history;
  - canonical equality compares only `canonical_id`, not the `(canonical_source, canonical_id)` namespace;
  - canonical matching does not reject an ambiguous candidate identity;
  - ASCII-only normalization removes all non-`[a-z0-9]` text and strips accented characters rather than normalizing them predictably.
- Independent reproductions:
  - `AlbumCandidate(album_id="album-x", identity=None)` is **not** excluded by `AlbumIdentity(album_id="album-x")`;
  - a Discogs canonical id `123` is treated as equal to a MusicBrainz canonical id `123`, causing destructive false exclusion;
  - two distinct Japanese artist/title pairs in the same year both collapse to `("norm", "", "", "2020")` and are deduplicated as the same Album.
- Impact: the permanent no-repeat invariant is not enforced for the exact candidate shape used by current fakes, while unrelated releases can be falsely banned. Non-Latin music is especially exposed to false collisions.
- Violated contract: Handoff Spec §2.4/§7.6; Master Plan §3.2; Implementation Plan I-4/T2.4.
- Required correction:
  - always compare the candidate's authoritative `album_id` independently of whether a nested identity object exists;
  - namespace canonical identifiers by source and define safe behavior when the source is missing;
  - require trustworthy confidence on both sides before destructive canonical matching;
  - use Unicode-aware deterministic normalization (with explicit normalization/casefold rules), never ASCII deletion that collapses distinct scripts;
  - provide a reviewable normalized fallback representation with confidence when canonical identity is unavailable, or explicitly demonstrate why the source `album_id` is stable enough for permanent cross-run exclusion.
- Acceptance tests: exact album-id exclusion without nested identity; different canonical sources with the same raw id; ambiguous candidate/exclusion combinations; accented and non-Latin distinct titles; same release under renamed metadata; multi-run permanent exclusion.

### [P1] G2-004 — Modern-year fallback is neither observable nor consistently constrained

- Location: `src/omda/core/year.py:30-75`; `src/omda/orchestrator/run.py:285-320`
- Evidence:
  - when no modern candidate exists, the function returns an ordinary list indistinguishable from a fully compliant result;
  - no fallback/degradation reason or candidate count is added to the `Plan`, `RunOutcome` or journal;
  - the test named `test_no_modern_candidates_degrades_observably` merely inspects the returned old Albums and proves no observability;
  - the final fill loop ignores `max_older`.
- Independent reproductions:
  - a complete all-old run reaches `COMPLETE`; its journal contains no degradation/status/reason field at any transition;
  - `count=4`, one modern candidate and `max_older=2` returns one modern plus three old Albums, silently violating the supplied constraint.
- Impact: operators and later quality evaluation cannot distinguish a compliant plan from a fallback, and configurable selection counts can bypass the era constraint.
- Required correction:
  - return a structured selection result containing Albums plus constraint/fallback status, reason and relevant counts;
  - persist that evidence in the plan/journal and expose it in the run outcome/reporting path;
  - if the older cap cannot satisfy a configured count, use an explicit documented degradation or `InsufficientCandidatesError`; never silently fill past the cap.
- Acceptance tests: normal, no-modern, unknown-year and insufficient-suitable-era results assert both selected Albums and durable observable evidence; non-default count/cap combinations cannot silently violate the cap.

### [P1] G2-005 — The claimed crash/restart and idempotency coverage does not exercise the stated scenarios

- Location: `tests/integration/test_run_engine.py:228-300`; `src/omda/orchestrator/run.py:205-225` and `:371-397`
- Evidence:
  - `CRASH_POINTS` uses strings such as `"after-plan"`, while `StepwiseHistory` compares them directly to journal transitions such as `"PLANNED"`; none can match;
  - even with corrected names, `StepwiseHistory` raises **before** persisting the transition, not after the durable point named by the test;
  - the missing-receipt test clears an empty receipt map before running, then the run saves a new receipt and completes; it finally calls `recover("no-such-run")`, so it never tests the described delivered run with missing evidence;
  - `run(run_id)` never checks an existing journal and always starts a new plan for the same id;
  - recovery treats `HISTORY_COMMITTED` as complete in memory but does not append the durable `COMPLETE` transition.
- Independent reproductions:
  - injecting `"after-plan"` produces a normal `COMPLETE` run containing every transition; no crash occurred;
  - after a real injected failure while appending `COMPLETE`, recovery returns `COMPLETE` but the durable journal still ends at `HISTORY_COMMITTED`;
  - rerunning a completed id with a sufficiently large Genre pool appends a second delivery path, then fails on duplicate pick index; subsequent recovery raises the same invariant conflict rather than returning the original terminal outcome.
- Impact: the minimum crash/restart contract is untested, completed run ids are not idempotent, and durable state can disagree with the returned state. The stage report's crash-replay and missing-receipt claims are therefore not supported by the committed tests.
- Required correction:
  - make `run(run_id)` inspect durable state first: return/recover an existing run and never start a different plan under the same idempotency key;
  - on recovery from `HISTORY_COMMITTED`, durably append `COMPLETE` exactly once;
  - rebuild the crash harness to persist the selected transition and then simulate process death **after** it;
  - cover every durable window, including delivery receipt saved before `DELIVERED`, `DELIVERED`, atomic `HISTORY_COMMITTED`, and before/after `COMPLETE`;
  - test missing/failed/conflicting receipts against the same delivered run;
  - count actual delivery calls and external side effects separately;
  - inject receipt-save and journal-write failures around external delivery.
- Acceptance test: a table-driven crash/restart suite proves the expected durable tail, recovery result, delivery-call count, external-effect count and unchanged/committed history for every transition window; a repeated completed run id is a true idempotent replay.

### [P1] G2-006 — Journaled randomness evidence is not the seed and cannot reproduce the run

- Location: `src/omda/orchestrator/run.py:178-201` and `:235-249`; G2 report §7
- Evidence: the engine accepts only a mutable `random.Random`; it records `str(self._rng.random())` as `seed`, which consumes one random draw and is not the seed used to initialize the generator. `Config.seed` is not tied to the injected RNG, and no input data version is recorded.
- Independent reproduction: with `Config.seed="owner-seed"` and an RNG created from `"different-seed"`, the PLANNED journal records a decimal such as `0.23208921686133`, not either provenance value. That decimal cannot reconstruct the generator's prior state or prove which input/version produced the plan.
- Impact: a production recommendation cannot be reproduced from its durable evidence, contrary to a MUST-level contract and the Executor report's determinism claim.
- Violated contract: Handoff Spec §6; Master Plan §8; Implementation Plan I-10/R-010 and T2.1/T2.6.
- Required correction:
  - make the seed/provenance value explicit and bind RNG construction to it (or use a replayable RNG-state contract);
  - record the actual seed, input data version, relevant configuration/version and deterministic ordering basis without consuming the RNG merely for logging;
  - ensure recovery preserves the same evidence rather than regenerating it.
- Acceptance test: construct a fresh process using only the journaled seed + input version + configuration and prove it recreates the exact ordered Genre picks and Album plan.

## Acceptance matrix

| G2 criterion | Status | Evidence |
|---|---|---|
| T2.1 equal-opportunity Genre selection | **PARTIAL** | unconstrained uniform test passes; constrained solver can falsely fail valid pools |
| T2.2 global 30/31 cooldown and multi-pick order | **FAIL** | local indices restart at 1; per-position eligibility is not evaluated |
| T2.3 family/parent diversity, bounded complete result | **FAIL** | probabilistic false insufficiency; parent memberships absent |
| T2.4 permanent Album exclusion and run dedup | **FAIL** | exact repeats can pass; cross-source/non-Latin false matches occur |
| T2.5 year constraint and rating composition | **PARTIAL** | rating composition/ties pass; fallback observability and cap enforcement fail |
| T2.6 recoverable run transaction | **FAIL** | second run cannot commit; repeated ids and durable completion are not idempotent; crash tests are ineffective |
| Core purity / no concrete external dependencies | **PASS** | AST boundary test and source inspection |
| Determinism and durable reproducibility | **FAIL** | recorded decimal is not the injected seed; input version absent |
| No G3/G4 scope creep | **PASS** | no live adapter/network implementation found |
| Review package / clean Git evidence | **PASS** | exact SHAs, clean worktree, committed report and test output |

## Checks performed

- Verified exact base/candidate SHAs, merge-base, accepted tag ancestry, branch, clean worktree and commit sequence.
- Inspected the complete G2 implementation and test delta, not only the Executor report.
- Independently ran 179 tests with cache disabled: all passed.
- Independently ran Ruff: passed.
- Ran `git diff --check`: passed.
- Reproduced the second-run global-index failure and repeated-run recovery failure.
- Reproduced a position-specific cooldown false shortage and probabilistic diversity false failures.
- Reproduced exact Album repeat leakage, cross-source canonical false exclusion and non-Latin fallback collisions.
- Reproduced non-observable year degradation and `max_older` bypass.
- Demonstrated that the committed crash-point names cause a complete run rather than a crash.
- Reproduced a durable journal stuck at `HISTORY_COMMITTED` after recovery reports `COMPLETE`.
- Verified that journaled `seed` evidence is an unrelated consumed random value.
- No live network or external service was used.

## Required repair scope

Remain on `exec/g2-core`. The repair may touch G2 Core/Orchestrator/domain values, G1 Port/domain shapes only where required to carry already-approved G2 semantics, focused tests, and stage-02 evidence. Do not implement G3/G4 adapters, change product defaults, add popularity signals, weaken existing tests, merge, tag or enter G3.

Because this is the highest-risk functional Gate, repairs should be split into coherent commits: global ordered picks/Genre solver; Album identity/year result; transaction recovery/provenance; then the review package. If a correction truly requires changing an accepted product rule rather than implementing it, stop with `BLOCKED_ARCHITECTURE` and propose an ADR.

## Verdict

**CHANGES_REQUESTED**

Open blocking findings: G2-001 (P0), G2-002 (P1), G2-003 (P0), G2-004 (P1), G2-005 (P1), G2-006 (P1). G2 must not be merged and G3 must not begin.
