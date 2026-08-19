# Gate G2 Independent Re-review Verdict

## Reviewed object

- Reviewer: GPT-5.6 Sol in Codex
- Review date: 2026-08-19
- Gate: G2 — Recommendation Core and recoverable transaction model
- Original base SHA: `731e0498fecdb0a28c84cf57d55c89569895a5bf`
- Original candidate SHA: `5ae45fe436cffa000cc0684f6768f0afb504edb6`
- Previous Reviewer commit: `d07237ee243d556ed7f82c2c54277b9d0c454acb`
- New candidate SHA: `284fea8e08370ffe0a31cc1ad5f661eaa6bf314d`
- Candidate branch observed: `exec/g2-core`
- Executor report: `reviews/stage-02/EXECUTOR_REPORT.md`
- Test evidence: `reviews/stage-02/TEST_RESULTS.txt`

The new candidate is a clean descendant of the exact accepted G1 base and includes the
previous verdict plus three repair commits and one handoff commit. The worktree was clean,
the merge-base was the exact stated base, `git diff --check` passed, and the delta remains
inside G2 source, tests and governance artifacts. The Reviewer independently ran the full
suite with cache disabled: **206 passed**. Ruff also passed.

The repairs close the original global-index, Album matching, year-observability and basic
crash/idempotency reproductions. Passing tests are still insufficient for this highest-risk
Gate: independent boundary probes found two direct invariant failures, one unreplayable
randomness path and one parent-constraint integration gap.

## Previous findings — closure status

| Finding | Previous severity | Re-review status | Evidence |
|---|---:|---|---|
| G2-001 global pick indices restart at 1 | P0 | **CLOSED** | `Plan.pick_records` now preserves `latest_pick_index()+1...`; digest/recovery retain exact records; consecutive-run tests cover fake and SQLite. |
| G2-002 first-position cooldown, probabilistic retries, missing parents | P1 | **PARTIAL** | Position-specific cooldown and random false-insufficiency are repaired, and the Core exposes parent parameters. However, the 100,000-solution prefix breaks equal opportunity (G2-007), while the Orchestrator cannot receive or pass source parents (G2-010). |
| G2-003 unsafe/incomplete Album identity matching | P0 | **CLOSED** | Exact `album_id` exclusion is independent of nested identity; canonical IDs are source-namespaced; ambiguous destructive matches are blocked; Unicode fallback no longer collapses non-Latin scripts. Cross-source enrichment quality remains a G3 risk, not a reopened G2 blocker. |
| G2-004 year fallback unobservable and older cap bypassed | P1 | **CLOSED** | `AlbumSelectionResult` records status/reason/counts, journal digest preserves it, and cap shortfall is explicit. |
| G2-005 ineffective crash harness and repeated-run non-idempotency | P1 | **CLOSED** | The new harness persists before simulated death, repeated completed run IDs do not re-plan, and `HISTORY_COMMITTED` recovery appends `COMPLETE` once. Receipt-to-run binding is a separate newly identified transaction failure (G2-009). |
| G2-006 recorded RNG draw instead of replayable provenance | P1 | **PARTIAL** | The recorded value is now the construction seed and input/config versions are journaled, but a mutable engine-level RNG makes later runs depend on process lifetime (G2-008). |

## Open blocking findings

### [P0] G2-007 — The bounded solution prefix creates severe Genre-ID selection bias

- Location: `src/omda/core/genre.py:34`, `:52-92`, `:95-156`, `:159-203`;
  `tests/property/test_genre_equality.py`
- Evidence:
  - The solver sorts candidates by `genre_id`, performs depth-first enumeration, and stops
    once `len(solutions) >= 100_000`.
  - Selection is uniform only inside that lexicographically early prefix, not inside the
    valid solution space described by the module and report.
  - The committed equality test uses only 10 Genres, whose 720 ordered 3-pick solutions
    never reach the cap, so it cannot detect this production-size behavior.
- Independent reproduction with 100 unrestricted Genres and three picks:
  - the true ordered space has 970,200 solutions, but only 100,000 are retained;
  - only 11 of 100 Genres ever occur in position 1;
  - `g000` occurs 11,594 times across the retained selections while `g099` occurs 1,990
    times, a roughly 5.8x marginal difference;
  - late IDs have zero first-position opportunity solely because of their identifier.
- Impact: an arbitrary lexical ID becomes a hidden weighting signal. This directly violates
  OMDA's defining MUST-level equal-opportunity rule and the report's claim that sampling is
  uniform over the valid solution space.
- Violated contract: Handoff Spec §2.1 and §6; Master Plan §3.1; AGENTS.md non-negotiable
  Genre equality rule; Implementation Plan I-1/T2.1/D.3.
- Required correction: replace prefix truncation with an unbiased bounded method over the
  complete valid space (for example count-based dynamic programming/unranking, or another
  mathematically reviewable method). A limit may bound work, but must not silently turn
  stable ordering into probability weight.
- Acceptance tests:
  - use a pool whose valid ordered space is greater than 100,000;
  - prove every unconstrained Genre has equal marginal/positional opportunity within the
    documented non-flaky criterion;
  - permuting or renaming otherwise identical Genre IDs must not change their opportunity;
  - constrained satisfiable and unsatisfiable cases must remain bounded and deterministic.

### [P1] G2-008 — A journaled seed does not reproduce later runs across a process restart

- Location: `src/omda/orchestrator/run.py:240-269`, `:318-345`;
  `tests/integration/test_run_engine.py:486-524`; `src/omda/config.py:43-50`
- Evidence:
  - `RunEngine` constructs one mutable RNG in `__init__` and reuses it for every new run.
  - Every run journals the same seed string, without recording the RNG state or deriving a
    run-specific generator.
  - The committed replay test covers only the first run on an empty history.
- Independent reproduction:
  - run 1 in a long-lived engine and run 1 in a fresh engine both selected
    `g00, g01, g11`, producing identical official history;
  - the long-lived engine then selected `g05, g02, g06` for run 2;
  - restarting the process before run 2 with the same recorded seed, input version,
    configuration and identical official history selected `g02, g03, g06`;
  - both PLANNED records claimed the same provenance values.
- Additional boundary issue: `Config.seed` exists, but the constructor's default literal
  `"default"` is used unless a separate caller argument is supplied, so the accepted config
  seed channel is not actually bound to RNG construction.
- Impact: a valid later recommendation cannot be reconstructed from the journal evidence;
  output changes merely because the process restarted.
- Violated contract: Handoff Spec §6 MUST reproduce from input version + configuration +
  seed; Master Plan §8; Implementation Plan R-010/T2.1/T2.6.
- Required correction: create or derive an explicit per-run RNG from durable provenance,
  record the exact seed/derivation inputs used by that run, and define precedence with
  `Config.seed`. Do not rely on mutable RNG history held only in process memory.
- Acceptance test: after an identical first committed run, compare run 2 from a long-lived
  engine with run 2 after process restart; exact ordered Genres and Albums must match using
  only the journaled seed, input version and effective configuration.

### [P0] G2-009 — An `ok` receipt for another run/key is accepted and commits official history

- Location: `src/omda/orchestrator/run.py:456-488` and `:498-524`
- Evidence: before saving and trusting a receipt, the Orchestrator checks only
  `receipt.status == "ok"`; it does not bind `receipt.run_id`, `idempotency_key` or `channel`
  to the current run and expected delivery operation.
- Independent reproduction: a Delivery fake returned
  `DeliveryReceipt(run_id="another-run", idempotency_key="another-key", channel="fake",
  status="ok")` while processing `run-1:markdown`. The engine returned `COMPLETE`, committed
  three official Genre picks and nine Album exclusions, stored the receipt under
  `another-key`, and had no receipt at `run-1:markdown`.
- Impact: OMDA can permanently mutate official history without durable evidence that the
  current run was delivered. A later audit/recovery cannot connect the committed history to
  its delivery, violating the central deliver-before-history invariant.
- Violated contract: Handoff Spec §4, §7.10/§7.11 and §8; Implementation Plan I-10/T2.6;
  the immutable receipt/idempotency contract accepted in G1.
- Required correction: validate the returned receipt against the expected run ID, exact
  idempotency key, configured channel and allowed success status before saving it or
  committing history. A mismatch must fail closed into an explicit recoverable/manual-review
  state without official history mutation.
- Acceptance tests: separately inject wrong run ID, wrong key, wrong channel and invalid
  success status for both fake and SQLite histories; none may commit history. Exact matching
  receipts and exact idempotent replays must continue to succeed.

### [P1] G2-010 — Parent diversity exists only as a test-only Core parameter

- Location: `src/omda/ports/domain.py:40-47`; `src/omda/ports/genre.py:10-15`;
  `src/omda/orchestrator/run.py:333-345`; `src/omda/core/genre.py:159-196`
- Evidence:
  - `GenreRef` carries only `genre_id`, `name`, `family` and `eligible`; it does not carry the
    source taxonomy's required `parents` field.
  - `GenreSource` exposes only `list[GenreRef]`, and the Orchestrator calls
    `select_daily_genres` without `parents_by_genre` or `parent_limits`.
  - Parent tests call the Core function directly with a hand-built mapping; no orchestrated
    run can exercise the feature.
- Impact: G3 adapters cannot preserve the required Genre parent taxonomy through the
  accepted Port into the selection path, and a normal run silently behaves as if no parent
  constraint exists.
- Violated contract: Master Plan §3.1/§5; Implementation Plan I-3, B.1 and T2.3. Handoff
  Spec §2.3 marks configured parent diversity as SHOULD, but the approved G2 plan makes it a
  Gate deliverable.
- Required correction: carry reviewable parent memberships and configured parent limits
  across the Port/domain boundary and pass them into the Core, without introducing a score
  or popularity signal. If the team intends to defer all parent enforcement, document that
  as an explicit approved plan change rather than leaving an unreachable parameter.
- Acceptance test: an integration run whose only unconstrained selection would include two
  Genres sharing a limited parent must select a valid alternative or fail explicitly; the
  same test must prove no popularity weighting is introduced.

## Acceptance matrix

| G2 criterion | Status | Evidence |
|---|---|---|
| T2.1 equal-opportunity Genre selection | **FAIL** | 100,000-solution DFS prefix produces severe lexical-ID bias. |
| T2.2 global 30/31 cooldown and ordered picks | **PASS** | exact global records and position-specific checks are implemented and tested. |
| T2.3 family/parent diversity, bounded outcome | **PARTIAL** | family and direct Core parent tests pass; parent data/limits are unreachable in an orchestrated run. |
| T2.4 permanent Album exclusion and run dedup | **PASS** | previous direct identity failures are repaired; canonical and Unicode cases pass. |
| T2.5 year constraint and rating composition | **PASS** | structured fallback evidence and older cap behavior are repaired; rating tests pass. |
| T2.6 recoverable run transaction | **FAIL** | basic crash/idempotency paths pass, but an unbound success receipt commits official history. |
| Core purity / no concrete external dependencies | **PASS** | architecture tests and source inspection. |
| Determinism and durable reproducibility | **FAIL** | second-run output depends on whether the engine process was restarted. |
| No G3/G4 scope creep | **PASS** | repair delta contains no live adapter/network implementation. |
| Review package / Git evidence | **PARTIAL** | exact SHAs, clean tree and committed output exist; the handbook-named `REPAIR_REPORT.md` is absent, with repair evidence appended to `EXECUTOR_REPORT.md` instead. This is non-blocking. |

## Checks performed and limitations

- Verified exact base/new-candidate SHAs, merge-base, branch, clean worktree and repair
  commit sequence.
- Reviewed both `d07237e..284fea8` and the necessary `731e049..284fea8` regression surface.
- Independently ran `pytest -q -p no:cacheprovider`: **206 passed**.
- Independently ran Ruff: **passed**.
- Ran `git diff --check`: **passed**.
- Reproduced large-pool equality bias with 50- and 100-Genre pools.
- Reproduced second-run divergence between a long-lived engine and a restarted engine using
  identical seed/input/config/history evidence.
- Reproduced official history commit with a success receipt bound to another run/key/channel.
- Confirmed parent mappings are not representable through the current `GenreSource` result
  or passed by `RunEngine`.
- No production code, merge, tag, remote push or G3 work was performed. No live network or
  external service was used.

## Required repair scope

Remain on `exec/g2-core`. Repair only the unbiased Genre solver, durable per-run randomness
contract, receipt validation/state handling, parent taxonomy plumbing, focused regression
tests and stage-02 evidence. Do not implement G3/G4 adapters, change product defaults, add
popularity signals, weaken tests, merge, tag or enter G3. If parent/config plumbing truly
requires changing an accepted architecture rule rather than carrying already-approved G2
semantics, stop and propose an ADR.

## Verdict

**CHANGES_REQUESTED**

Open blockers: G2-007 (P0), G2-008 (P1), G2-009 (P0), G2-010 (P1). G2 must not be merged and
G3 must not begin. Acceptance would apply only to a future exact candidate SHA after these
findings are independently re-reviewed.
