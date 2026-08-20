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
