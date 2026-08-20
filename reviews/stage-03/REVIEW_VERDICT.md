# Gate G3 Independent Review Verdict

## Reviewed object

- Reviewer: GPT-5.6 Sol in Codex
- Review date: 2026-08-20
- Gate: G3 — Data & Adapters
- Exact base SHA: `f69c540ee8d98741b9a90f2175fdde012ea81c45`
- Exact candidate SHA: `eaeacb7a6bb77e87cb3af62b41a053a3d60270fc`
- Candidate branch observed: `exec/g3-adapters`
- Executor report: `reviews/stage-03/EXECUTOR_REPORT.md`
- Test evidence: `reviews/stage-03/TEST_RESULTS.txt`

The candidate is a clean descendant of the exact accepted G2/main base. The merge-base is
correct, the worktree was clean at review start, `git diff --check` passed, and the complete
base-to-candidate delta was inspected. No G4 LLM, Markdown or delivery implementation was
introduced.

The ordinary suite and lint are green, but independent negative probes found five open P1
contract failures. They are not cosmetic: they can admit an ineligible Genre, distort
cross-source ratings, permanently bind an Album to the wrong canonical identity, hide stale
source evidence, or leave external access without the bounds promised by G3. Therefore G3
cannot be accepted yet.

## Findings

### [P1] G3-001 — Genre packages do not enforce eligibility or their provenance boundary

- Location: `src/omda/adapters/datasets.py:98-117`, `:132-155`;
  `data/schemas/genre_source.schema.json:12`; `data/genres/README.md:18-25`
- Evidence:
  - `list_eligible_genres()` appends every validated record, including
    `eligible: false`, even though the accepted `GenreSource` Port requires it to return only
    valid, eligible Genres. The Orchestrator passes this list directly into equal-opportunity
    selection and does not filter the flag later.
  - `records_file` is joined directly to `source_dir` without resolving and enforcing package
    containment. A package with `records_file: ../../outside.jsonl` is accepted and reads that
    external file.
  - A Genre record's `source` is never checked against `source.yaml.source_id`, and the
    metadata `source_id` is not checked against the package directory name despite the
    contribution guide promising both checks.
- Independent reproduction: a one-record package containing `eligible: false` returned
  `GenreRef(... eligible=False ...)`; a second package successfully loaded
  `../../outside.jsonl` whose record declared a different source, while exposing provenance
  from the claiming package.
- Impact: invalid/incomplete Genres can enter the official lottery, and data from another
  location/source can be relabelled with incorrect license and provenance. This violates the
  source-of-truth and objective-eligibility contracts.
- Required correction:
  - return only records whose validated `eligible` field is true (or rename/change the Port
    only through an ADR; the existing Port contract should be preserved);
  - require `source.yaml.source_id == source_dir.name` and every record's
    `source == source_id`;
  - restrict `records_file` to the declared package, preferably the exact reviewed filename,
    and reject absolute paths, traversal and symlink escapes;
  - add negative tests for all four cases and an Orchestrator-level test proving an
    `eligible: false` record can never be selected.

### [P1] G3-002 — Critic row scale can bypass the declared source scale and corrupt ranking

- Location: `src/omda/adapters/datasets.py:193-273`;
  `src/omda/core/rating.py:22-25`; `data/critics/README.md:47-52`
- Evidence: the adapter checks `rating` against the source-level min/max but accepts a blank,
  zero, negative or unrelated `rating_max`. Core normalizes by the row's `rating_max` when it
  is truthy and otherwise treats the raw number as already normalized.
- Independent reproduction: under a declared 1-to-5 source scale, `rating=4` with blank
  `rating_max` was accepted and composed as `4.0` rather than `0.8`; `rating=4,
  rating_max=1` was also accepted and composed as `4.0`.
- Impact: a text-only contribution can silently dominate or invert multi-source ranking even
  though its metadata declares a common scale. The contribution package is therefore not a
  safe implementation of the accepted rating contract.
- Required correction:
  - define one unambiguous normalization rule: normally fill the row denominator from
    `source.yaml.rating_scale_max` when omitted and require a supplied `rating_max` to match
    that declared scale;
  - validate `rating_scale_min < rating_scale_max`, require a positive denominator, and require
    each rating to be valid against both the declared and effective row scale;
  - add adapter-to-`compose_rating` integration tests for missing, zero, negative and mismatched
    denominators and prove normalized output stays within the documented range.

### [P1] G3-003 — A single unrelated MusicBrainz result is labelled `exact`

- Location: `src/omda/adapters/musicbrainz.py:172-231`, especially `:207-230` and
  `:271-278`; `tests/unit/test_musicbrainz_enricher.py:78-105`
- Evidence: response selection is based only on list cardinality. If MusicBrainz returns one
  item, the adapter accepts its ID without comparing title, artist, first-release year or
  search score, then sets `identity_confidence="exact"`. The candidate year is included in the
  cache key but not in the query or result verification. The positive fixture itself omits
  artist evidence yet expects exact confidence.
- Independent reproduction: a candidate for John Coltrane's *Blue Train* received a fabricated
  single result titled `Unrelated Album` by `Other Artist`; the adapter returned canonical ID
  `WRONG` with confidence `exact`.
- Impact: accepted G2 logic treats stable canonical identity as the permanent-exclusion key.
  One search anomaly can therefore permanently exclude the wrong Album or permit the actual
  Album to be recommended again. This is the exact R-004 P1 failure mode.
- Required correction:
  - validate every response item shape and translate malformed items into the domain error
    taxonomy;
  - use normalized title and complete artist-credit evidence, with year/score as reviewable
    corroboration when available; never infer `exact` from result count alone;
  - if zero or multiple plausible matches remain, preserve an explicit no-match/ambiguous
    outcome rather than installing a destructive canonical ID;
  - add fixtures for unrelated single result, same-title different artist, same artist/title
    with conflicting years, malformed list items and a genuinely exact response.

### [P1] G3-004 — MusicBrainz stale-cache fallback has no observable stale marker

- Location: `src/omda/adapters/musicbrainz.py:9-13`, `:136-155`, `:265-282`;
  `tests/unit/test_musicbrainz_enricher.py:250-269`; Executor report §4.2 and §5.7
- Evidence: `enrich()` passes `cache_status="stale"` after a failed refresh, but `_apply()`
  never uses or exposes that argument. `AlbumCandidate` contains no provenance/cache-status
  field, and the cache entry remains private. The test named
  `test_stale_cache_refresh_failure_degrades_explicitly` asserts only the old ID, not an
  observable stale state.
- Independent reproduction: stale fallback returned the same `AlbumCandidate` shape and
  `identity_confidence="exact"` as a fresh lookup; no caller can distinguish the two.
- Impact: downstream journal/output cannot report source age or decide whether stale evidence
  is acceptable. This contradicts the Master Plan's stale-data observability rule and the
  candidate's explicit provenance claim.
- Required correction:
  - make freshness, source, fetched-at and query-version observable through a small accepted
    enrichment result/provenance contract, or fail clearly when the current Port cannot carry
    required stale evidence;
  - do not overload `identity_confidence` with freshness;
  - add fresh, stale-success, stale-refresh-failure and persisted-cache round-trip assertions
    that inspect the caller-visible evidence.

### [P1] G3-005 — External-access bounds are incomplete for both MusicBrainz and RYM

- Location: `src/omda/adapters/musicbrainz.py:233-263`;
  `browser_companion/source.py:32-36`, `:66-109`;
  `governance/IMPLEMENTATION_PLAN.md:318-338`, OD-10 at `:539`
- Evidence:
  - MusicBrainz only sleeps after a failed response. Consecutive successful candidate lookups
    have no client-side pacing. Official MusicBrainz API guidance requires applications to
    stay at or below one call per second and use a meaningful contactable User-Agent; the
    placeholder `https://github.com/omda` is not demonstrated to be a real project/contact.
  - Browser Companion's `PageFetcher.fetch(url)` has no timeout/deadline argument and the
    source has no enforcement wrapper, so a legitimate browser bridge can block forever. The
    planned timeout test does not exist.
  - The source has no per-run page budget/run identity even though OD-10 assigns a configurable
    bounded budget to G3, and it accepts arbitrary `http(s)` targets as RYM provenance instead
    of constraining scheme/host/path.
- Impact: normal multi-Album operation can violate upstream service limits; a browser fetch can
  hang the run; repeated calls are not bounded per run; and a future live fetcher can be sent
  to an unrelated or local URL while the result is labelled RYM.
- Required correction:
  - implement injectable client-side pacing across successful MusicBrainz calls as well as
    retry backoff, and use a configurable meaningful User-Agent/contact;
  - make Browser Companion fetch deadlines/timeouts part of the executable contract and map
    timeout/fetcher exceptions to `SourceUnavailableError`;
  - implement and test a configurable per-run RYM page budget, reject budget overflow
    explicitly, and allow only the intended HTTPS RYM origin/path;
  - add deterministic fake-clock/sleeper tests for consecutive success pacing, timeout,
    budget exhaustion and URL rejection.

Reference checked during review: the official
[MusicBrainz API rate-limiting guidance](https://musicbrainz.org/doc/MusicBrainz_API/Rate_Limiting)
states the current average source-IP limit is one request per second and requires a meaningful,
contactable User-Agent.

### [P2] G3-006 — In-memory caches are called bounded but are unbounded, and page snapshots are mutable

- Location: `src/omda/adapters/musicbrainz.py:85-99`;
  `browser_companion/source.py:39-56`, `:86-109`
- Evidence: both caches use dictionaries with no capacity/eviction bound. `PageCacheEntry` is
  frozen but contains a mutable `dict`, and the source returns the same dictionary stored in
  cache. A caller can mutate a schema-validated extract and subsequent cache hits return the
  corrupted value without revalidation.
- Impact: long-lived processes can grow memory with every unique key and caller mutation can
  rewrite cached provenance. This is lower severity than the five blocking contract failures
  but contradicts the code's bounded/snapshot wording.
- Required correction: either implement/document a real capacity bound and deterministic
  eviction or stop claiming bounded storage; store immutable snapshots and return defensive
  copies (or immutable domain values), with mutation and eviction tests.

## Acceptance matrix

| G3 criterion | Status | Evidence |
|---|---|---|
| T3.1 existing data Port implementations | **FAIL** | G3-001 eligibility/package contract breach |
| T3.2 reviewable text data and provenance | **FAIL** | G3-001 path/source relabelling; G3-002 scale inconsistency |
| T3.3 MusicBrainz identity, limits, cache and degradation | **FAIL** | G3-003, G3-004 and MusicBrainz part of G3-005 |
| T3.4 Browser Companion boundary | **FAIL** | missing timeout/page budget/target restriction in G3-005 |
| T3.5 text-only critic contribution | **PARTIAL** | package flow works, but unsafe normalization remains |
| Ordinary CI uses fixtures/fakes and no live RYM | **PASS** | complete suite uses local fakes/fixtures |
| No bypass/CAPTCHA automation/mass pre-crawl/default Album Detail fan-out | **PASS** | source and contract inspection |
| Core/Orchestrator accepted G2 behavior unchanged | **PASS** | no G2 Core/Orchestrator delta |
| No G4 scope creep | **PASS** | no LLM/Markdown/PushPlus implementation |
| Open P0/P1 findings | **FIVE P1** | G3-001 through G3-005 |

## Independent checks performed

- Verified exact full SHAs, branch, clean starting worktree, merge-base and complete commit chain.
- Inspected all 34 changed files relevant to implementation, schemas, fixtures, tests, data and
  governance; `git diff --check` passed.
- Independently ran the complete suite with cache disabled: **350 passed**.
- Independently ran Ruff over `src`, `tests` and `browser_companion`: **passed**.
- Reproduced ineligible Genre admission, cross-package path escape/source relabelling,
  critic-scale misnormalization, unrelated-single-result exact identity and invisible stale
  fallback using temporary packages/fake transports only.
- Inspected official MusicBrainz search/rate-limit documentation; no live MusicBrainz or RYM
  request, external mutation, merge, tag, push or production-code edit was performed.

## Required repair scope

The Executor should remain on `exec/g3-adapters`, read this verdict, and create focused repair
commits. Allowed scope:

- dataset adapter/package validation, relevant schemas and contribution guides;
- MusicBrainz matching, caller-visible provenance/cache contract, pacing and configuration;
- Browser Companion timeout, RYM URL/page-budget contract and cache snapshot safety;
- focused unit/integration/contract/negative tests;
- G3 repair report, test evidence and state/risk updates;
- no Recommendation Core selection rewrite, no G4 LLM/Markdown/PushPlus implementation, no
  live RYM dependency and no anti-bot behavior.

If making stale provenance observable truly requires changing an accepted public Port/domain
contract, the Executor must stop at `BLOCKED_ARCHITECTURE` and submit an ADR instead of hiding
the state or repurposing identity confidence.

## Verdict

**CHANGES_REQUESTED**

Open blocking findings: G3-001, G3-002, G3-003, G3-004 and G3-005 (all P1). Candidate
`eaeacb7a6bb77e87cb3af62b41a053a3d60270fc` must not be merged, `gate-g3-accepted` must not
be created, and G4 must not begin.

---

## Re-review 1 — candidate `120eedd9c14b0b5014cc50a61c7e123abb4721db`

### Re-review identity and checks

- Original G3 base: `f69c540ee8d98741b9a90f2175fdde012ea81c45`
- Original G3 candidate: `eaeacb7a6bb77e87cb3af62b41a053a3d60270fc`
- Original Reviewer commit: `9178f145ed7c0210f5dd94af4c49b1d7a659f515`
- Repair candidate: `120eedd9c14b0b5014cc50a61c7e123abb4721db`
- Repair commits: `de30dd7`, `ab3e1b8`, `df989cd`, `ad26c2f`; review-package
  commit: `120eedd`
- Candidate branch observed: `exec/g3-adapters`
- Worktree at review start: clean
- Independent full suite: **382 passed**
- Ruff over `src`, `tests`, `browser_companion`: **passed**
- `git diff --check`: **passed**

The repair stays within G3 and retains the original Reviewer commit in the candidate chain.
The data-package validation, critic denominator normalization and cache snapshot/capacity
repairs are materially correct. However, three P1 findings remain partially open: canonical
identity is still promoted to `exact` when corroborating evidence is missing, stale evidence
was exposed through a concrete-adapter-only parallel API, and the new external-access bounds
can be disabled or bypassed with accepted constructor values/URLs.

### Original finding status

| Finding | Re-review status | Evidence |
|---|---|---|
| G3-001 Genre eligibility/provenance | **CLOSED** | `eligible:false` is filtered; source/package/path containment checks are enforced before records leave the adapter. |
| G3-002 critic scale consistency | **CLOSED** | blank denominator inherits source max; invalid/mismatched scales reject; adapter-to-Core normalization is tested. |
| G3-003 canonical exactness | **PARTIAL / OPEN** | title/artist and conflicting years are checked, but missing/malformed year and absent/low search confidence still install `exact`. |
| G3-004 stale evidence | **PARTIAL / OPEN** | the existing Port now fails clearly, but a second concrete-only enrichment interface bypasses the accepted Port mapping. |
| G3-005 external-access bounds | **PARTIAL / OPEN** | defaults exist, but timeout/pacing can be non-finite, disabled or absent; RYM path restriction is normalization-bypassable; default contact remains a placeholder. |
| G3-006 bounded immutable caches | **CLOSED for the original cache objects** | FIFO capacities and defensive page snapshots work; a new unbounded run-budget ledger is tracked separately as G3-007. |

### [P1] G3-003 remains open — incomplete evidence still becomes destructive `exact` identity

- Location: `src/omda/adapters/musicbrainz.py:247-315`, especially `_parse_item()`,
  `_matches()` and `_year_conflict()`
- Evidence: normalized title and artist equality are now required, which closes the original
  unrelated-result counterexample. But `_year_conflict()` returns false when either year is
  missing, and response `score` is never validated or used. A single item with the same
  self-titled Album/artist, no usable release year and absent or zero score is therefore
  labelled `identity_confidence="exact"`.
- Independent reproduction: candidate `Weezer / Weezer / 1994` plus a single response item
  `id="wrong-self-titled-id", title="Weezer", artist-credit=["Weezer"]` with no
  `first-release-date` or score produced an exact MusicBrainz identity. The same occurred with
  `first-release-date="unknown"` and `score=0`.
- Impact: self-titled/reused Album names can still bind to the wrong release-group and become a
  permanent exclusion key. The result is based on less evidence than the accepted normalized
  fallback, which includes artist, title **and year**.
- Required correction:
  - distinguish missing/unparseable corroboration from non-conflict; when candidate year is
    known, require a valid compatible first-release year before installing a destructive
    canonical identity;
  - validate the search confidence/score shape and define a conservative, reviewable threshold
    or fail closed when sufficient evidence is absent;
  - do not call a title/artist-only match `exact` merely because it is the only returned item;
  - add same-artist/self-titled fixtures covering missing year, malformed year, low/missing
    score and a fully corroborated exact result.

### [P1] G3-004 remains open — stale provenance was implemented as a parallel adapter API

- Location: `src/omda/adapters/musicbrainz.py:153-205`;
  `src/omda/ports/album.py:20-24`; `src/omda/ports/domain.py:66-79`;
  `src/omda/ports/__init__.py`
- Evidence: the accepted `AlbumEnricher` Port still exposes only `enrich() -> AlbumCandidate`.
  The repair adds `MusicBrainzEnricher.enrich_with_evidence()` directly on the concrete
  adapter and adds `AlbumEvidence`, but the method is not part of any Port, is not usable by
  the Orchestrator without importing the concrete MusicBrainz adapter, and has no other caller.
  This is a second vendor-specific application contract, contrary to the G3 one-adapter-to-one-
  existing-Port mapping. `AlbumEvidence` is not even re-exported from `omda.ports`.
- Positive closure: `enrich()` now correctly raises a typed error with stale metadata after a
  failed refresh, so silent stale reuse itself is fixed.
- Impact: if downstream code follows the repair report and consumes caller-visible evidence,
  it must couple directly to the MusicBrainz implementation. That breaks the accepted
  `Orchestrator -> Ports <- Adapters` dependency direction and gives other enrichers no parity
  contract.
- Required correction:
  - simplest path: keep the fail-clearly behavior on the existing Port and remove the unused
    concrete-only `enrich_with_evidence()`/`AlbumEvidence` surface, updating stale docstrings;
  - if successful enrichment evidence must be application-visible, stop at
    `BLOCKED_ARCHITECTURE` and propose an ADR for one provider-neutral `AlbumEnricher` result
    contract, then update Port parity/fakes/contract tests only after approval;
  - do not retain a parallel public method merely to avoid acknowledging a Port change.

### [P1] G3-005 remains open — new bounds can be disabled or URL-normalized away

- Location: `src/omda/adapters/musicbrainz.py:118-150`, `:327-364`;
  `browser_companion/source.py:47-51`, `:100-118`, `:166-190`
- Evidence:
  - Browser Companion accepts `fetch_timeout=None`, `0`, negative, `inf` and `nan`, then passes
    each value to the fetcher. `None`/infinite values directly defeat the promised bounded
    deadline, while the Protocol itself defaults to `None`.
  - MusicBrainz accepts `pacing_seconds=0`, `inf` and `nan`; zero/NaN disables pacing and the
    non-finite values can fail outside the typed adapter boundary. Connect/read timeouts and
    backoff parameters likewise have no positive-finite validation.
  - `_check_url()` checks only the raw path prefix. URLs such as
    `https://rateyourmusic.com/genre/../release/album/x/` and percent-encoded `..`/slash
    variants pass and are sent to the fetcher; browser/HTTP normalization can resolve them
    outside `/genre/`, defeating the stated no-Album-Detail target restriction.
  - `DEFAULT_USER_AGENT` still points to generic `https://github.com/omda`; the repository has
    no Git remote or maintainer contact establishing that URL as this project's contact point.
    The repair made it configurable but did not ensure the live default is meaningful.
- Independent reproduction: every timeout value above reached the fake fetcher unchanged;
  all three traversal/encoded URLs reached it; MusicBrainz zero/NaN pacing completed with no
  pacing sleep.
- Impact: a production run can still hang indefinitely, exceed the upstream request policy or
  reach a non-Genre RYM page while reporting a bounded compliant source. Therefore the planned
  G3 timeout/access contract is not yet enforceable.
- Required correction:
  - validate every timeout, delay, backoff, TTL and pacing value as the appropriate finite,
    positive bounded type; if a pre-throttled transport is supported, model it explicitly
    rather than treating zero/NaN as compliant live pacing;
  - make `PageFetcher.fetch()` require a finite timeout, not default to `None`;
  - canonicalize/decode the URL safely and reject dot segments, encoded path separators,
    userinfo, ports and any non-canonical target before fetching; add the exact bypass fixtures;
  - require an explicit, meaningful contact User-Agent for live construction or replace the
    placeholder only when the real project URL/contact exists;
  - preserve domain-typed errors for invalid configuration and runtime failures.

Official MusicBrainz guidance still requires no more than one call per second and a meaningful,
contactable User-Agent:
[MusicBrainz API rate limiting](https://musicbrainz.org/doc/MusicBrainz_API/Rate_Limiting).

### [P2] G3-007 — the new per-run budget ledger grows without a lifecycle bound

- Location: `browser_companion/source.py:118`, `:162-190`
- Evidence: `_budget_used` retains one dictionary entry for every distinct run id forever.
  The page cache is now capacity-bounded, but the same long-lived companion object can still
  grow without limit through the budget ledger; there is no release/reset or bounded eviction.
- Required correction: make budget state run-scoped and discard it at run completion, or use a
  bounded lifecycle-aware ledger with an explicit cleanup operation and tests. Cleanup must not
  allow a still-active run to reset its budget and exceed the limit.

### [P2] G3-008 — critic package documentation and runtime checks still diverge

- Location: `data/critics/README.md:17-25`, `:47-52`;
  `src/omda/adapters/datasets.py:222-239`, `:289-308`
- Evidence: the guide says `source_id` must match the package directory, but the critic adapter
  checks only rows against metadata. It also does not document the new rule that blank
  `rating_max` inherits `rating_scale_max`, a supplied value must equal it, and source scale
  bounds must be strictly ordered with a positive denominator.
- Required correction: enforce the documented directory/source invariant for critic packages
  and update the contribution guide with the exact normalization and validation rules plus a
  working blank-denominator example.

### Re-review 1 assessment

| G3 criterion | Result |
|---|---|
| Genre eligibility and package provenance | **PASS** |
| Critic numeric normalization | **PASS WITH P2 DOC GAP** |
| Canonical identity safety | **FAIL — G3-003** |
| Stale-cache fail-closed behavior | **PASS** |
| Single provider-neutral Port mapping | **FAIL — G3-004** |
| Bounded/compliant external access | **FAIL — G3-005** |
| Cache capacity and immutable snapshots | **PASS** |
| Ordinary fixture-only CI / no anti-bot behavior | **PASS** |
| Open P0/P1 findings | **THREE P1** |

### Re-review 1 verdict

**CHANGES_REQUESTED**

G3-001, G3-002 and the original G3-006 cache defects are closed. G3-003, G3-004 and G3-005
remain blocking P1 findings; G3-007 and G3-008 are P2 follow-ups to fix with the focused repair.
Candidate `120eedd9c14b0b5014cc50a61c7e123abb4721db` must not be merged,
`gate-g3-accepted` must not be created, and G4 must not begin.

---

## Re-review 2 — candidate `e8baf77787d552b086489f78850e71e1e363f0be`

### Re-review identity and checks

- Original G3 base: `f69c540ee8d98741b9a90f2175fdde012ea81c45`
- Previous repair candidate: `120eedd9c14b0b5014cc50a61c7e123abb4721db`
- Previous Reviewer commit: `443638e0c3807d49b1726060413d6c0cd985cacc`
- New repair candidate: `e8baf77787d552b086489f78850e71e1e363f0be`
- Repair commits: `981deab`, `10a1ef7`; review-package commit: `e8baf77`
- Candidate branch observed: `exec/g3-adapters`
- Merge base of original base and new candidate: exact original base
  `f69c540ee8d98741b9a90f2175fdde012ea81c45`
- Worktree at review start: clean
- Independent full suite: **411 passed in 4.00s**
- Ruff over `src`, `tests`, `browser_companion`: **passed**
- `git diff --check` over original base to new candidate: **passed**
- Tracked cookie/profile/database/`.env` filename scan: **no matches**
- Scope audit: no G4 implementation, merge, tag, live RYM dependency, anti-bot code or accepted
  G2 contract change observed

The repairs correctly close the parallel concrete-only enrichment API and implement the critic
package directory invariant. They also add positive-finite validation for the principal timeout,
delay and TTL settings. The candidate nevertheless remains unsafe to accept: the MusicBrainz
score parser rejects the provider's documented JSON representation while accepting non-finite or
arbitrarily low numeric scores as exact evidence; Browser Companion run budgets can be reset by
the new automatic ledger eviction; and several claimed external-access bounds remain bypassable.

### Original finding status

| Finding | Re-review status | Evidence |
|---|---|---|
| G3-001 Genre eligibility/provenance | **CLOSED** | No regression; ineligible records stay filtered and package/source/path containment remains enforced. |
| G3-002 critic scale consistency | **CLOSED** | No runtime regression; declared denominator rules and Core normalization remain tested. |
| G3-003 canonical exactness | **PARTIAL / OPEN (P1)** | Missing year/score now fails closed, but the real documented string score is rejected while low/non-finite numeric scores install `exact`. |
| G3-004 stale evidence / Port parity | **CLOSED** | `enrich_with_evidence` and `AlbumEvidence` are removed; stale refresh failure remains observable through the accepted Port error path. |
| G3-005 external-access bounds | **PARTIAL / OPEN (P1)** | Main time values are validated, but page/run counts and retry count are not bounded integer types; non-canonical URL variants and the placeholder User-Agent remain. |
| G3-006 bounded immutable caches | **PARTIAL / OPEN (P2)** | Snapshot/FIFO behavior is intact, but non-integer/non-finite capacities can disable the capacity bound. |
| G3-007 run-budget ledger lifecycle | **OPEN, raised to P1** | Capacity is bounded, but automatic eviction resets a still-active run and permits it to exceed its page budget. |
| G3-008 critic documentation parity | **PARTIAL / OPEN (P2)** | Runtime directory invariant and rules are documented, but the advertised blank-denominator CSV example is not a valid working row. |

### [P1] G3-003 remains open — the score contract rejects real responses and accepts unsafe confidence

- Location: `src/omda/adapters/musicbrainz.py:243-267`, `:269-316`, `:325-337`;
  `tests/unit/test_musicbrainz_enricher.py:85-101`, `:498-545`
- Evidence:
  - MusicBrainz's official search API documentation shows JSON search scores as strings such as
    `"score": "100"`. `_parse_item()` accepts only Python `int`/`float`, so a provider-shaped
    successful release-group result raises `SourceUnavailableError("... malformed 'score'")`.
    All success fixtures use the non-provider shape `score=100`, so the test suite misses this.
  - Conversely, numeric `0.01`, `NaN` and `Infinity` all pass `_sufficient_evidence()` and install
    `identity_confidence="exact"`. `NaN <= 0` is false, so the current positivity check is not a
    finiteness check. There is still no conservative, reviewable confidence threshold: any
    positive value is treated as sufficient.
- Independent reproduction: one otherwise fully matching `Blue Train / John Coltrane / 1958`
  response produced these outcomes:
  - `score="100"` -> typed source failure instead of enrichment;
  - `score=0.01`, `score=NaN`, `score=Infinity` -> canonical ID `mb-id` installed as `exact`.
- Impact: the live adapter can reject ordinary valid search results, while malformed or extremely
  weak confidence can become the permanent Album exclusion key. This is both a production
  compatibility defect and the canonical-misidentification risk R-004.
- Violated contract: MP “Album canonical identity” forbids silent destructive fuzzy matching;
  Implementation Plan I-4/T2.4 and T3.3 require predictable canonical identity and a working
  MusicBrainz release-group adapter; the prior G3-003 correction explicitly required validated
  score shape plus a conservative threshold.
- Required acceptance:
  - parse the provider's documented decimal-string score representation into one finite numeric
    domain with an explicit valid range; reject booleans, non-finite values, malformed strings and
    out-of-range values through the typed source boundary;
  - define one named, documented, conservative minimum score for destructive `exact` identity;
  - add provider-shaped `"100"`, below-threshold, boundary, `NaN`/`Infinity`, malformed and
    fully corroborated self-titled fixtures; only sufficient title + full artist credit + required
    year + threshold score may install a canonical ID.

Official response-shape evidence: [MusicBrainz API search documentation](https://musicbrainz.org/doc/MusicBrainz_API/Search).

### [P1] G3-005 remains open — page/retry bounds and live identification are not enforceable

- Location: `browser_companion/source.py:48-56`, `:73-80`, `:112-145`, `:202-253`;
  `src/omda/adapters/musicbrainz.py:29`, `:97-101`, `:118-163`, `:349-377`
- Evidence:
  - `max_pages_per_run` and `max_tracked_runs` only use `<= 0`. `NaN` and `Infinity` are accepted;
    with `max_pages_per_run` set to either value, three distinct uncached pages for one run all
    reached the fetcher and the promised budget never exhausted. Fractional and boolean counts
    are also accepted despite the setting being an integer count.
  - `max_retries` likewise lacks a non-negative integer check. `1.5`, `NaN` and `Infinity` pass
    construction and later escape as raw `TypeError` from `range()`; a string fails as a raw
    comparison `TypeError`, and `True` is silently treated as one retry.
  - `_check_url()` still passes non-canonical variants including a backslash traversal target
    `https://rateyourmusic.com/genre/..\\release/album/x/` and double-encoded separators/traversal
    to the fetcher. A browser-facing boundary must reject these before downstream URL
    normalization, not merely observe that a single `unquote()` still begins with `/genre/`.
  - `DEFAULT_USER_AGENT` is still `omda/0.1 (+https://github.com/omda) enrichment`. This repository
    has no remote or maintainer contact proving that generic URL is contactable for this project.
    The constructor accepts and sends that default, while the repair report's statement that a
    runtime layer supplies a live contact is not backed by a runtime composition in this Gate.
- Impact: a configuration accepted as valid can disable the per-run external-access limit or fail
  outside the adapter's typed boundary; a non-canonical target can reach the browser fetcher; and
  the default live request does not satisfy the upstream identification contract.
- Violated contract: Implementation Plan T3.3/T3.4 and OD-10 require bounded external behavior
  and a per-run RYM budget; the prior G3-005 acceptance required every bound to have the
  appropriate finite type, canonical targets, and an explicit meaningful contact User-Agent.
- Required acceptance:
  - validate page counts and retry counts as integers (excluding booleans), with a documented
    finite upper bound where appropriate; invalid construction must fail deterministically before
    any fetch;
  - reject backslashes, residual/double percent encoding and every non-canonical target before the
    `PageFetcher` boundary, with the exact counterexamples above as regression tests;
  - require an explicit contactable User-Agent at construction until a real project contact
    exists, or introduce a real verified project contact and use it as the default;
  - keep the already-correct positive-finite timeout/delay/TTL checks.

Official upstream policy requires at most one request per second and a User-Agent with enough
information to contact maintainers:
[MusicBrainz API rate limiting](https://musicbrainz.org/doc/MusicBrainz_API/Rate_Limiting).

### [P1] G3-007 remains open — FIFO eviction lets an active run reset and exceed its budget

- Location: `browser_companion/source.py:145`, `:189-199`, `:241-253`;
  `tests/unit/test_browser_companion.py:342-367`
- Evidence: `_consume_budget()` evicts the oldest ledger entry whenever a new `run_id` arrives at
  capacity, without knowing whether the evicted run is finished. With both limits set to one:
  1. `r1` fetches page A (uses its only page);
  2. `r2` fetches page B (silently evicts active `r1`);
  3. `r1` fetches page C (silently evicts `r2` and succeeds again).
  The fake fetcher receives all three requests, so `r1` has fetched two pages despite a declared
  maximum of one. The new test explicitly expects `budget_used("r1") == 0` after eviction and
  therefore codifies the reset instead of checking the “still-active run” requirement.
- Impact: interleaved runs can repeatedly rotate IDs and bypass the RYM page ceiling. The ledger
  is memory-bounded, but the externally important request budget is no longer a hard bound.
- Violated contract: OD-10 requires a per-run bounded page budget; the previous G3-007 acceptance
  explicitly stated that cleanup must not let a still-active run reset and exceed its limit.
- Required acceptance: remove silent eviction of active ledgers. Use explicit lifecycle cleanup
  (`finish_run`) plus fail-closed capacity handling, or track completion separately. Add the exact
  `r1 -> r2 -> r1` interleaving test and prove the third request is rejected without reaching the
  fetcher. A new run may reuse an identifier only after an explicit completed-run lifecycle rule.

### [P2] G3-006 is partially reopened — cache capacity accepts values that disable the bound

- Location: `browser_companion/source.py:73-101`;
  `src/omda/adapters/musicbrainz.py:89-112`
- Evidence: `PageCache(max_entries=NaN/Infinity/1.5/True)` and
  `EnrichmentCache(max_entries=NaN/Infinity/1.5/True)` all construct successfully. For `NaN` or
  `Infinity`, `len(entries) >= max_entries` never becomes true, making the supposedly bounded
  cache unbounded.
- Impact: a long-lived process can grow either cache without limit under accepted configuration.
- Required acceptance: require `max_entries` to be a positive integer excluding booleans; add
  constructor regression tests for non-finite, fractional, boolean, zero and negative inputs.

### [P2] G3-008 remains partially open — the blank-denominator example is not a working CSV row

- Location: `data/critics/README.md:61-70`
- Evidence: the example row
  `my-source,album-b,3,,            # blank -> rating_max = 5, stored as 3/5` has five cells, but
  the fifth cell is a literal comment and is parsed as `review_url`. The runtime validator then
  rejects it because it is not an HTTP(S) URL. CSV has no inline-comment syntax here.
- Impact: a contributor following the advertised working example creates a rejected package.
- Required acceptance: make the CSV code block itself valid (leave the fifth cell truly blank)
  and put the explanation outside the row; add a docs/example smoke test or parse the example
  shape through the adapter.

### [P2] G3-009 — the MusicBrainz module contract still documents removed stale fallback behavior

- Location: `src/omda/adapters/musicbrainz.py:9-13` versus `:167-201`
- Evidence: the module docstring says refresh failure “falls back to the stale value” with a stale
  marker. The repaired accepted-Port implementation intentionally does the opposite: it raises a
  typed stale-refresh failure and does not return the stale candidate.
- Impact: maintainers can implement Orchestrator recovery against behavior the adapter no longer
  provides, obscuring the intentional G3-004 fail-closed decision.
- Required acceptance: update the module-level contract to state that stale refresh failure is
  observable as a typed error carrying stale provenance and that stale identity is not served.

### Re-review 2 acceptance matrix

| G3 criterion | Result |
|---|---|
| Genre eligibility and package provenance | **PASS** |
| Critic numeric normalization/runtime invariants | **PASS** |
| Critic contribution guide executable accuracy | **FAIL (P2) — G3-008** |
| Canonical identity safety and live MusicBrainz response compatibility | **FAIL (P1) — G3-003** |
| Stale-cache fail-closed behavior | **PASS** |
| Single provider-neutral Port mapping | **PASS** |
| Bounded/compliant external access | **FAIL (P1) — G3-005/G3-007** |
| Cache capacity and immutable snapshots | **PARTIAL (P2) — G3-006** |
| Browser Companion human-intervention/no-circumvention boundary | **PASS** |
| Ordinary fixture-only CI and Core isolation | **PASS** |
| G3 scope / no G4 implementation | **PASS** |
| Open P0/P1 findings | **THREE P1** |

### Re-review 2 checks and limitations

- Reviewed the full original `base..new candidate` diff and the
  `120eedd..e8baf77` repair increment; verified exact ancestry and commit chain.
- Re-ran all 411 tests and Ruff using the WorkBuddy Python environment because the system and
  bundled Codex Python runtimes do not include the repository's optional test tools.
- Ran independent in-memory adversarial probes for provider-shaped/low/non-finite MusicBrainz
  scores, invalid retry/page/cache bounds, interleaved run IDs and non-canonical RYM URLs.
- Did not make live MusicBrainz or RYM requests; provider behavior was checked against official
  MusicBrainz documentation and all runtime reproductions used local fakes.
- Did not modify production code, merge, tag, push or enter G4.

### Re-review 2 verdict

**CHANGES_REQUESTED**

G3-001, G3-002 and G3-004 are closed. G3-003 and G3-005 remain blocking P1 findings, and the
G3-007 repair introduces a directly reproducible active-run budget bypass, also P1. G3-006,
G3-008 and G3-009 are focused P2 corrections to include in the same repair. Candidate
`e8baf77787d552b086489f78850e71e1e363f0be` must not be merged,
`gate-g3-accepted` must not be created, and G4 must not begin.

---

## Re-review 3 — candidate `98b13b892787caf0dd52e511a2e8913d53e380e9`

### Re-review identity and checks

- Original G3 base: `f69c540ee8d98741b9a90f2175fdde012ea81c45`
- Previous repair candidate: `e8baf77787d552b086489f78850e71e1e363f0be`
- Previous Reviewer commit: `033e599468ff8677b262d1714c67a6a7bcc6eacb`
- New repair candidate: `98b13b892787caf0dd52e511a2e8913d53e380e9`
- Repair commit: `ce67bd3`; review-package commit: `98b13b8`
- Candidate branch observed: `exec/g3-adapters`
- Merge base of original base and new candidate: exact original base
  `f69c540ee8d98741b9a90f2175fdde012ea81c45`
- Worktree at review start: clean
- Independent full suite: **463 passed in 5.08s**
- Ruff over `src`, `tests`, `browser_companion`: **passed**
- `git diff --check` over original base to new candidate: **passed**
- Tracked cookie/profile/database/`.env` filename scan: **no matches**
- Scope audit: no G4 implementation, merge, tag, live RYM dependency, anti-bot code or accepted
  G2 contract change observed

The repair correctly parses provider-shaped MusicBrainz string scores, applies a named 90-point
threshold, rejects non-finite confidence, makes page/run/cache counts integer typed, rejects the
reported URL normalization bypasses, fails closed at run-ledger capacity and removes the stale
fallback documentation error. One canonical-identity P1 remains: the stricter matching semantics
reuse the old `v1` cache namespace, so a canonical ID accepted by the previous weak rule bypasses
the new score policy on a fresh cache hit.

### Finding status

| Finding | Re-review status | Evidence |
|---|---|---|
| G3-001 Genre eligibility/provenance | **CLOSED** | No regression. |
| G3-002 critic scale consistency | **CLOSED** | No runtime regression. |
| G3-003 canonical exactness | **PARTIAL / OPEN (P1)** | Live lookup is corrected, but pre-threshold `v1` cache entries are still accepted as current exact identities. |
| G3-004 stale evidence / Port parity | **CLOSED** | No regression; only the accepted Port exists and stale refresh fails observably. |
| G3-005 external-access bounds | **PASS WITH P2 UA VALIDATION GAP** | Reported numeric and URL bypasses are closed; explicit UA is required, but “contactable” is not actually validated. |
| G3-006 bounded immutable caches | **CLOSED** | Capacity type, FIFO and snapshot behavior pass. |
| G3-007 run-budget ledger lifecycle | **CLOSED** | Active ledgers are never evicted; new runs fail closed at capacity and explicit finish releases state. |
| G3-008 critic documentation parity | **PARTIAL / OPEN (P2)** | CSV now parses, but the prose still contradicts both its own example and runtime storage. |
| G3-009 stale-cache module documentation | **CLOSED** | Module contract now matches fail-closed implementation. |

### [P1] G3-003 remains open — the strengthened identity rule did not invalidate weaker `v1` cache entries

- Location: `src/omda/adapters/musicbrainz.py:49-56`, `:93-109`, `:202-218`,
  `:239-251`, `:370-383`, `:434-448`
- Evidence:
  - The previous candidate accepted any positive numeric score as sufficient for `exact`. The new
    candidate correctly requires `MIN_EXACT_SCORE = 90.0`, but `QUERY_VERSION` remains `"v1"`.
  - The cache key begins with `QUERY_VERSION`, and a fresh hit is passed directly to `_apply()`;
    cached entries do not retain the score needed to re-evaluate the new threshold.
  - The cache is expressly designed to be overridable by a persistent backend, and each entry
    carries query-version provenance. Keeping the same namespace after a destructive identity
    acceptance change defeats that versioning boundary.
- Independent reproduction:
  1. Construct the current query key for `Blue Train / John Coltrane / 1958`.
  2. Seed a fresh `v1` `EnrichmentEntry` with canonical ID `pre-threshold-id`, emulating an entry
     produced by the prior positive-score rule.
  3. Call the repaired enricher. It returns `pre-threshold-id` with
     `identity_confidence="exact"` and makes **zero** transport calls.
- Impact: an identity that would fail the new 90-point rule can survive the repair and become a
  permanent exclusion key. The provider parser and threshold tests all pass because none exercise
  cache migration across the policy change.
- Violated contract: MP canonical identity and Implementation Plan I-4/T2.4 prohibit ambiguous
  permanent exclusion; R-004 is P1. G3 T3.3 explicitly requires versioned, provenance-carrying
  cache behavior, and the G3-003 repair must apply to cached as well as newly fetched evidence.
- Required acceptance:
  - advance the MusicBrainz query/cache policy version (for example `v2`) whenever matching or
    destructive-identity acceptance semantics change;
  - add a regression test that seeds an old-version, previously acceptable canonical entry and
    proves the current policy does not serve it as `exact` and instead performs/requires a current
    lookup;
  - retain all corrected provider-string, threshold, finiteness and year/title/artist tests.

### [P2] G3-005 — “contactable User-Agent” is asserted but only non-emptiness is enforced

- Location: `src/omda/adapters/musicbrainz.py:43-47`, `:167-172`;
  `tests/unit/test_musicbrainz_enricher.py:29`, `:237-251`
- Evidence: requiring an explicit value correctly removes the unsafe placeholder default, but
  values such as `"x"`, `"omda/0.1"` and `"not contactable"` all construct successfully. The only
  negative regression supplies `None`; it does not prove the documented contact requirement.
- Impact: runtime composition can satisfy the constructor while still sending an upstream-policy-
  noncompliant anonymous identifier. The safe default is now fail-closed, so this is no longer the
  earlier P1 default-path defect.
- Required acceptance: either validate a documented `Application/version (contact URL or email)`
  shape at the adapter boundary, or model/document a provider-neutral validated configuration
  boundary that cannot silently substitute a non-contact string. Add app-only/nonsense rejection
  and URL/email acceptance tests.

MusicBrainz requires enough User-Agent information to contact maintainers:
[MusicBrainz API rate limiting](https://musicbrainz.org/doc/MusicBrainz_API/Rate_Limiting).

### [P2] G3-008 remains partially open — the now-parseable example still describes the wrong cells and storage behavior

- Location: `data/critics/README.md:61-74`;
  `src/omda/adapters/datasets.py:281-345`; `src/omda/core/rating.py:22-25`;
  `tests/unit/test_dataset_adapters.py:746-776`
- Evidence:
  - The guide says to keep the “fifth cell” empty, but the blank denominator is the **fourth** cell
    and the example's fifth `review_url` cell is populated.
  - It says album-b “is stored as `3/5` (not `3.0`)”. The adapter and its new test do the opposite:
    they store `CriticRatingRow(rating=3.0, rating_max=5.0)`; Recommendation Core later computes
    `3.0 / 5.0` during composition.
- Impact: the CSV itself works, but contributors and future adapter authors are given a false
  representation contract.
- Required acceptance: state that the fourth `rating_max` cell is blank, the adapter fills and
  stores `rating_max=5.0` alongside raw `rating=3.0`, and Core normalizes that pair to `3/5`.
  Extend the existing README test through `compose_rating()` or assert the corrected wording.

### Re-review 3 acceptance matrix

| G3 criterion | Result |
|---|---|
| Genre eligibility and package provenance | **PASS** |
| Critic numeric runtime normalization | **PASS** |
| Critic contribution documentation accuracy | **FAIL (P2) — G3-008** |
| New MusicBrainz response parsing and confidence threshold | **PASS** |
| Canonical identity safety across cache-policy versions | **FAIL (P1) — G3-003** |
| Stale-cache fail-closed behavior and Port parity | **PASS** |
| Bounded Browser Companion access and active-run lifecycle | **PASS** |
| Cache capacity and immutable snapshots | **PASS** |
| Explicit MusicBrainz identification | **PARTIAL (P2) — G3-005** |
| Browser Companion human-intervention/no-circumvention boundary | **PASS** |
| Ordinary fixture-only CI and Core isolation | **PASS** |
| G3 scope / no G4 implementation | **PASS** |
| Open P0/P1 findings | **ONE P1** |

### Re-review 3 checks and limitations

- Reviewed the full original `base..new candidate` diff and the
  `033e599..98b13b8` repair increment; verified exact ancestry and commit chain.
- Re-ran all 463 tests and Ruff using the WorkBuddy Python environment.
- Reproduced old-policy fresh-cache reuse and explicit but non-contact User-Agent acceptance with
  local fakes; no live MusicBrainz or RYM requests were made.
- Rechecked the repaired score, count, URL, ledger, cache and README regression tests and found no
  weakening beyond the disclosed replacement of the incorrect FIFO-reset expectation.
- Did not modify production code, merge, tag, push or enter G4.

### Re-review 3 verdict

**CHANGES_REQUESTED**

G3-006, G3-007 and G3-009 are closed, and the direct network path for G3-003/G3-005 is materially
repaired. G3-003 remains one blocking P1 because the unchanged `v1` cache namespace bypasses the
new destructive-identity threshold. G3-005 and G3-008 have focused P2 corrections to include in
the same repair. Candidate `98b13b892787caf0dd52e511a2e8913d53e380e9` must not be merged,
`gate-g3-accepted` must not be created, and G4 must not begin.

---

## Re-review 4 — candidate `f4ca34f168899d98f83fd23d2b081836e1cbd7f5`

### Re-review identity and checks

- Original G3 base: `f69c540ee8d98741b9a90f2175fdde012ea81c45`
- Previous repair candidate: `98b13b892787caf0dd52e511a2e8913d53e380e9`
- Previous Reviewer commit: `068b49df50ed5d7cf3bfbd931b43507a21b7ee8e`
- New repair candidate: `f4ca34f168899d98f83fd23d2b081836e1cbd7f5`
- Repair commit: `fd925e8`; review-package commit: `f4ca34f`
- Candidate branch observed: `exec/g3-adapters`
- Merge base of original base and new candidate: exact original base
  `f69c540ee8d98741b9a90f2175fdde012ea81c45`
- Worktree at review start: clean
- Independent full suite: **474 passed in 3.31s**
- Ruff over `src`, `tests`, `browser_companion`: **passed**
- `git diff --check` over original base to new candidate: **passed**
- Tracked cookie/profile/database/`.env` filename scan: **no matches**
- Scope audit: no G4 implementation, merge, tag, live RYM dependency, anti-bot code or accepted
  G2 contract change observed

The `v2` cache namespace plus same-key version check closes the last canonical-identity P1: old
weak-policy entries are no longer served and the current lookup is required. The critic guide now
matches adapter storage and Core composition. The only remaining defect is the User-Agent format
validator: it searches for a few substrings rather than validating the declared complete shape,
so obviously non-contactable and control-character values still pass construction.

### Finding status

| Finding | Re-review status | Evidence |
|---|---|---|
| G3-001 Genre eligibility/provenance | **CLOSED** | No regression. |
| G3-002 critic scale consistency | **CLOSED** | No regression. |
| G3-003 canonical exactness/cache policy | **CLOSED** | `QUERY_VERSION=v2`; old-key and same-key/old-field entries cannot short-circuit current lookup. |
| G3-004 stale evidence / Port parity | **CLOSED** | No regression. |
| G3-005 external-access bounds and identification | **PARTIAL / OPEN (P2)** | All numeric, URL, pacing and ledger defects are closed; the new contact format predicate remains trivially bypassable. |
| G3-006 bounded immutable caches | **CLOSED** | No regression. |
| G3-007 run-budget ledger lifecycle | **CLOSED** | No regression. |
| G3-008 critic documentation parity | **CLOSED** | README and end-to-end normalization test now agree. |
| G3-009 stale-cache module documentation | **CLOSED** | No regression. |

### [P2] G3-005 remains open — the contact predicate accepts empty, anonymous and control-character contacts

- Location: `src/omda/adapters/musicbrainz.py:169-180`, `:463-485`;
  `tests/unit/test_musicbrainz_enricher.py:834-875`
- Evidence: `_is_contactable_user_agent()` checks only that the first character is alphanumeric
  and that the string contains one of a few marker substrings. It does not enforce the documented
  application/version token, complete contact field, host/email, closing syntax, or absence of
  control characters.
- Independent reproduction: all of these values construct successfully:
  - `x(+https://)` — no application/version separation and an empty URL;
  - `x <@>` — empty local part and domain;
  - `anonymous/1.0 (+https://)` — explicitly anonymous with an empty contact;
  - `app (+mailto:)` — no version and an empty mailbox;
  - `app/1 (+https://example.org)\r\nX-Test: injected` — trailing CRLF/header content.
- Impact: the adapter and report claim that non-contact strings cannot be substituted, but runtime
  configuration can still send an upstream-policy-noncompliant identifier. Control characters may
  also escape as a provider-specific transport failure or unsafe header content rather than being
  rejected at the adapter configuration boundary.
- Violated contract: the prior G3-005 acceptance explicitly required a documented
  `Application/version (contact URL or email)` shape. MusicBrainz requires enough information to
  contact the application's maintainers.
- Required acceptance:
  - validate the **entire** User-Agent value, reject ASCII control characters/CR/LF and trailing
    content, and require a real application token plus `/version`;
  - parse the contact portion: HTTP(S) URLs need a non-empty hostname; `mailto:` and angle-bracket
    forms need non-empty local/domain parts; do not accept the word “anonymous” as the app token;
  - add the five exact counterexamples above as negative tests, while retaining valid URL,
    `mailto:` and angle-email cases.

Official requirement: [MusicBrainz API rate limiting](https://musicbrainz.org/doc/MusicBrainz_API/Rate_Limiting).

### Re-review 4 acceptance matrix

| G3 criterion | Result |
|---|---|
| Genre and critic runtime data contracts | **PASS** |
| Critic contribution documentation and composition example | **PASS** |
| MusicBrainz response parsing and confidence threshold | **PASS** |
| Canonical identity safety across cache-policy versions | **PASS** |
| Stale-cache fail-closed behavior and Port parity | **PASS** |
| Browser Companion URL/page/run/cache boundaries | **PASS** |
| MusicBrainz explicit contact identification | **PARTIAL (P2) — G3-005** |
| Human-intervention/no-circumvention boundary | **PASS** |
| Ordinary fixture-only CI and Core isolation | **PASS** |
| G3 scope / no G4 implementation | **PASS** |
| Open P0/P1 findings | **NONE** |

### Re-review 4 checks and limitations

- Reviewed the full original `base..new candidate` diff and the
  `068b49d..f4ca34f` repair increment; verified exact ancestry and commit chain.
- Re-ran all 474 tests and Ruff using the WorkBuddy Python environment.
- Independently reproduced old-cache invalidation and the five malformed User-Agent cases using
  local fakes; no live MusicBrainz or RYM requests were made.
- No test weakening, production-code edit by Reviewer, merge, tag, push or G4 work was performed.

### Re-review 4 verdict

**CHANGES_REQUESTED**

There are no remaining P0/P1 findings, and G3-003/G3-008 are closed. However, G3's own external-
access identification criterion is not complete while G3-005's validator accepts empty,
anonymous and control-character contacts contrary to its declared contract. Complete this one
focused P2 correction, rerun the Gate suite and resubmit. Candidate
`f4ca34f168899d98f83fd23d2b081836e1cbd7f5` must not be merged,
`gate-g3-accepted` must not be created, and G4 must not begin.
