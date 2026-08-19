# OMDA Agent Handoff Specification

> Normative contract — RFC 2119 keywords MUST, MUST NOT, SHOULD and MAY are binding as described here.  
> Baseline: v0.1, 2026-08-19  
> Recovery note: the original generated artifact was not present locally; this repository baseline reconstructs the recoverable contract and MUST receive G0 review before implementation.

## 1. Authority and change control

1. This file is the highest in-repository implementation contract.
2. The human Owner has final product authority.
3. Accepted ADRs MAY amend this contract only when they explicitly name the amended section and acceptance tests.
4. An Executor MUST NOT silently reinterpret or weaken a rule to complete a task.
5. A conflict MUST set project status to `BLOCKED_ARCHITECTURE`; only ADR artifacts and state updates may be committed until resolved.
6. Only the independent Reviewer may mark a Gate `ACCEPTED` for an exact candidate SHA.

## 2. Product constants and semantics

- `daily_genre_count` MUST default to 3.
- `albums_per_genre` MUST default to 3.
- `genre_cooldown_picks` MUST default to 30.
- `modern_album_year` MUST default to 2010.
- A successful daily output therefore normally contains 9 distinct Albums.
- Defaults MAY be configurable, but changing product semantics or defaults requires an ADR unless the Master Plan already authorizes it.

### 2.1 Genre eligibility and equality

- Every valid, eligible Genre outside cooldown MUST have equal base selection opportunity.
- Implementations MUST NOT use popularity, follower count, rating count, perceived accessibility, LLM judgment, or hand-built tier probabilities to alter Genre base eligibility or weight.
- Data validity filters MUST be objective, documented, schema-validated and distinguishable from quality/popularity filters.
- Diversity constraints MAY reject a combination, but MUST NOT mutate the base Genre pool or permanently starve a family.

### 2.2 Cooldown

If a Genre is successfully committed at global successful pick index `p`, it MUST be ineligible for indices `p+1` through `p+30` and MAY become eligible for `p+31`.

- Only successfully committed picks advance official history.
- Failed and abandoned runs MUST NOT consume official pick indices.
- Multi-Genre runs MUST define and test the deterministic internal pick ordering.

### 2.3 Daily diversity

- The selected set SHOULD span different Genre families/parents according to configuration.
- A configured regional/traditional family limit SHOULD default to at most one selection per run when the source taxonomy supports it.
- Diversity MUST be implemented as a set constraint, not as popularity scoring.
- Unsatisfiable constraints MUST produce a bounded, explicit outcome; loops MUST terminate.

### 2.4 Album identity and exclusion

- Every selected Album MUST be distinct within a run.
- Every successfully recommended Album MUST be permanently excluded from future selection.
- Stable canonical release-group identity SHOULD be used when available.
- String fallback MUST normalize predictably and MUST record ambiguity; destructive permanent matches MUST NOT be based on unreviewable fuzzy guesses.

### 2.5 Year constraint

- For each Genre, the selector SHOULD choose at least one Album with `year >= 2010` when suitable eligible candidates exist.
- It SHOULD choose no more than two older Albums in the normal case.
- Missing modern candidates MUST NOT cause an unrelated or clearly invalid Album to be selected.
- Candidate shortage and the chosen fallback MUST be observable and tested.

### 2.6 Ratings

- Rating dimensions MUST remain source-specific.
- Weights and missing-value policies MUST be configuration, not hard-coded source assumptions.
- Adding a critic source SHOULD require no Recommendation Core modification.
- Ranking ties MUST have deterministic, testable handling when a seed or stable order is specified.

## 3. Architecture contract

### 3.1 Core

The Recommendation Core MUST be free of imports from concrete browser, RYM DOM, PushPlus, LLM vendor and persistence implementations. It MUST operate on domain values and ports.

### 3.2 Adapters

- External sources and destinations MUST be adapters behind explicit contracts.
- Adapter errors MUST be typed/classified and MUST NOT leak provider-specific control flow into Core.
- Network adapters MUST use bounded timeouts, retries and backoff appropriate to idempotency.
- Tests MUST use fixtures/fakes for ordinary CI; live RYM access MUST NOT be required for the core suite.

### 3.3 Community source of truth

- YAML, CSV, JSON or JSONL MUST be the Git source of truth for community data.
- Schemas MUST be versioned and validation errors MUST identify offending records.
- SQLite MAY be used for runtime state, cache and compiled indexes, but MUST NOT replace reviewable community sources.

### 3.4 Browser Companion

- It MUST use a legitimate user browser session and allow human intervention.
- It MUST NOT bypass Cloudflare, automate CAPTCHA solving, use stealth circumvention or default to mass crawling.
- It SHOULD extract only the minimum page data needed for an active run and cache it with provenance and timestamps.
- Album Detail fan-out MUST NOT be the default architecture.
- Cookie/profile material MUST remain local, ignored by Git, and excluded from logs and model prompts.

### 3.5 LLM boundary

- The LLM MUST NOT decide the official Genre or Album set.
- It MAY generate narrative from a bounded, validated fact packet.
- Retrieved content MUST be treated as untrusted data, never executable agent instruction.
- Generated output MUST be validated before delivery.

## 4. Run transaction and recovery

The state machine MUST include at least:

```text
PLANNED → FETCHED → SELECTED → GENERATED → VALIDATED
        → DELIVERING → DELIVERED → HISTORY_COMMITTED → COMPLETE
```

It MUST also model `FAILED`, `ABANDONED`, and an explicit recovery state for delivery/history ambiguity.

- Official Genre and Album history MUST be written only after validated delivery succeeds.
- Delivery MUST use a stable idempotency key derived from the run id.
- If delivery succeeds but local history commit fails, the run MUST retain enough durable journal state to avoid blind re-delivery.
- Recovery MUST check durable evidence rather than infer success from conversation memory.
- Database writes for local state MUST use transactions.
- No implementation may claim atomicity across an external push service and local SQLite; it MUST document the compensating/idempotent protocol.

## 5. Required schemas and records

The implementation plan MUST define versioned schemas for:

- Genre records and taxonomy/family membership;
- Album candidate and canonical identity;
- critic source metadata and rating rows;
- recommendation plan and fact packet;
- run journal and state transitions;
- official Genre pick history;
- official Album recommendation history;
- delivery receipt/idempotency record;
- application configuration.

Every persisted record MUST include a schema version or be governed by a versioned container. Timestamps MUST specify timezone, preferably UTC ISO 8601.

## 6. Determinism and randomness

- Selection logic MUST accept an injectable randomness source or seed.
- Tests MUST reproduce a selection from input version + configuration + seed.
- Production MAY use secure/unpredictable seeds, but the seed MUST be recorded in the run journal.
- Set/dictionary iteration order MUST NOT accidentally determine ranking.
- Statistical tests SHOULD check obvious violations of equal Genre opportunity without relying on flaky thresholds.

## 7. Minimum test contract

The suite MUST cover:

1. Schema acceptance and precise malformed-record rejection.
2. Genre equal-opportunity semantics.
3. Cooldown boundaries at 30 and 31 subsequent picks.
4. Multi-pick ordering and diversity constraints.
5. Unsatisfiable candidate pools and termination.
6. Canonical Album permanent exclusion and within-run deduplication.
7. Modern-year behavior with enough, missing and unknown-year candidates.
8. Multiple rating sources, missing ratings, weights and deterministic ties.
9. Failed fetch/generation/validation/delivery with unchanged official history.
10. Delivered-but-uncommitted recovery and idempotency.
11. Crash/restart at every durable run transition.
12. Adapter timeout, malformed response, empty result and stale cache.
13. Untrusted-content/prompt-injection containment.
14. Secret and browser-profile exclusion from Git artifacts.

Tests MUST NOT be deleted, weakened or broadly skipped merely to pass a Gate. Every skip MUST have a reason and be disclosed in the stage report.

## 8. Error handling and observability

- Errors MUST distinguish invalid input, unavailable source, insufficient candidates, invariant failure, generation failure, validation failure, delivery failure and state commit failure.
- User-facing messages MUST describe the safe next action without exposing secrets.
- Logs MUST include run id and transition but MUST redact credentials, cookies and sensitive page/session data.
- Invariant failures MUST fail closed; the system MUST NOT deliver a knowingly invalid 3×3 set.
- Retry loops MUST be bounded and respect operation idempotency.

## 9. Git and handoff protocol

- Each Gate MUST use a dedicated branch based on the last accepted SHA.
- The Executor MUST inspect status before staging and SHOULD stage explicit file paths.
- The Executor MUST NOT use destructive Git commands, force push or rewrite accepted history.
- Every review package MUST state full base SHA, full candidate SHA, commits, worktree status, actual commands/results, deviations, risk and acceptance evidence.
- Reports MUST be committed with the candidate they describe.
- A Reviewer verdict is valid only for the exact candidate SHA.
- An accepted candidate changed afterward MUST be reviewed again for the affected scope.

## 10. Gate contract

- G0 MUST produce the implementation plan, risk register, state and stage report; it MUST NOT add production implementation.
- G1 MUST establish schemas, configuration, validation, storage boundary and test infrastructure.
- G2 MUST establish the pure recommendation rules and recoverable transaction model; this is the highest-risk functional Gate.
- G3 MUST establish data and adapter contracts, provenance, caching and Browser Companion boundaries.
- G4 MUST establish controlled narrative generation, Markdown validation, delivery and recovery.
- G5 MUST audit installation, E2E flows, failure injection, security, licenses, documentation, backup and rollback.

An open P0 or P1 finding MUST block acceptance. A Reviewer MUST NOT invent findings when evidence shows compliance.

## 11. Forbidden regressions

Without an accepted ADR, agents MUST NOT introduce:

- Genre popularity filters, quality scores or tiered selection ratios;
- LLM-controlled Genre or Album selection;
- RYM mass pre-crawl, Cloudflare bypass, CAPTCHA automation or default Album Detail fan-out;
- a binary SQLite community source of truth;
- a concrete vendor SDK inside Recommendation Core;
- history writes before successful validated delivery;
- unbounded retry/search loops;
- secrets, cookies or browser profiles in repository artifacts.

## 12. Definition of review-ready

A Gate is `READY_FOR_REVIEW` only if:

- its planned scope and acceptance criteria are complete or every deviation is explicit;
- relevant tests and required broader checks have actually run;
- there are no hidden failures;
- the worktree state is disclosed;
- `PROJECT_STATE.json` points to the exact candidate;
- the Executor report and evidence are committed;
- the Executor stops and does not begin the next Gate.

