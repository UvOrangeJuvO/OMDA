# ADR-0002 Independent Review

## Reviewed object

- Reviewer: GPT-5.6 Sol in Codex
- Review date: 2026-08-22
- ADR: `docs/adr/0002-production-album-source-and-runtime-boundary.md`
- ADR proposal commit: `702d1d3f4b34527403474d783882549d123d56ef`
- Parent Reviewer commit: `790f36f99a859da3b2578462d76e6b2cac4051ad`
- Repository state observed: `BLOCKED_ARCHITECTURE / ADR_PENDING`
- ADR status observed: `Proposed`
- Production-code/test changes in the ADR proposal: none

The proposal commit is a clean, documentation-only descendant of the previous Reviewer
commit. It changes only ADR-0002, the G4 Executor report and project state. The worktree was
clean at review start, and `git diff --check` passed.

## Summary

The proposal makes several correct high-level choices:

- sample/demo Albums must never pass the external-delivery boundary;
- RYM mass crawling, Album Detail fan-out and anti-bot bypass remain prohibited;
- MusicBrainz release-group MBID remains the canonical Album identity;
- v0.1 may honestly be deterministic/no-LLM instead of using a fake local echo;
- the outstanding delivery binding, token precedence, documentation and schema-version
  findings remain owned and have explicit acceptance tests.

ADR-0002 is not yet safe or implementable as written. The central licensing premise is
incorrect: MusicBrainz officially classifies user tags (including genre associations) and
search indexes as **supplementary data**, not CC0 core data. D1 discovers release groups using
the `tag` search field, so the candidate relation and any redistributed snapshot cannot simply
be labelled CC0 without resolving that mixed/derived-data boundary. The public web service is
also documented as free for non-commercial use, which matters to an open-source project's
distribution and deployment story.

The proposal also places a new data-source adapter in G4 despite the accepted plan assigning
data/source adapters exclusively to G3, turns runtime API cache into tracked Git data, lacks a
bounded pagination/exhaustion strategy for permanent Album exclusion, and proposes destructive
removal of delivery evidence as a schema rollback. These are architecture issues rather than
implementation details. The ADR must remain Proposed.

## Findings requiring revision

### ADR2-001 — The selected tag-search source is not an unqualified CC0 dataset

- Location: ADR D1/D2 (`:76-105`), risk table (`:220-227`) and references.
- Official MusicBrainz documentation splits its database into CC0 core data and
  CC BY-NC-SA 3.0 supplementary data. Its database breakdown explicitly lists:
  - user-submitted tags, including genre associations; and
  - search indexes
  as supplementary data.
- D1's `query=tag:<genre>` depends directly on those tag associations and the search index.
  The returned title/artist/MBID fields may be core facts, but the Genre-to-release-group
  candidate relation and a snapshot selected through it are at minimum mixed/derived from the
  supplementary source. The ADR cannot record the whole source and Git package as CC0.
- MusicBrainz's API documentation additionally says non-commercial web-service use is free and
  directs commercial users to commercial plans/contact. “Open-source code” does not by itself
  resolve service-use or redistributed-data licensing.
- Required revision:
  1. separate licenses for core release-group facts, supplementary tag/genre associations,
     the web-service access terms and OMDA's derived candidate package;
  2. state attribution/share-alike/non-commercial implications and keep data licensing
     separate from the code license;
  3. obtain an explicit Owner product decision on whether a non-commercial-only live source
     is acceptable for v0.1, or select a source/path compatible with the intended project use;
  4. revise the option comparison to include at least a curated community
     Genre-to-release-group-MBID package with per-source licensing, and a fail-closed mode when
     no legally compatible candidate source is installed.
- Official references:
  - `https://musicbrainz.org/doc/About/Data_License`
  - `https://musicbrainz.org/doc/MusicBrainz_Database`
  - `https://musicbrainz.org/doc/MusicBrainz_API`

### ADR2-002 — Runtime cache is incorrectly conflated with Git community source of truth

- Location: ADR D2 `:98-102`, impact `:207-214`; Master Plan `:64-69`, `:115-117`;
  SPEC §3.3.
- D2 says live query snapshots are “cached as Git JSONL packages” and then uses the community
  source-of-truth rule to justify that cache. The baseline says the opposite operationally:
  curated community data is reviewable Git text, while local runtime cache belongs under the
  Git-ignored `var/` boundary (SQLite or another bounded local cache).
- A normal recommendation run must not modify tracked repository data. Automatic promotion of
  live responses into Git also bypasses contribution review, license review and reproducible
  provenance validation.
- Required revision: define two separate paths:
  - **runtime cache**: bounded, local, ignored by Git, TTL/provenance aware and safe to delete;
  - **curated community package**: created only by an explicit export/import contribution
    workflow, schema-validated and human-reviewed before commit, with its own license/source
    manifest.
  A runtime cache hit must not be described as Git source of truth.

### ADR2-003 — D4 contradicts the accepted exclusive Gate ownership

- Location: ADR D4 `:118-125`, option table `:187-193`; IMPLEMENTATION_PLAN
  `:292-305`.
- The accepted plan states that **data/source-class adapter implementations**, including
  MusicBrainz/community sources, cache, provenance and error mapping, are owned exclusively by
  G3. G4 owns LLM, Markdown and delivery. Consuming an `AlbumSource` from `run.py` does not turn
  the source adapter itself into a delivery-layer implementation.
- D4 says G4-010 changes no G3 boundary while adding exactly such an adapter under G4. Both
  claims cannot be true.
- Required revision: choose one truthful governance path. The recommended minimal path is a
  narrowly reopened G3 corrective task for `MusicBrainzAlbumSource` plus source contract/cache/
  provenance tests, followed by return to the still-blocked G4 for production composition and
  delivery gating. If the ADR instead moves source adapters into G4, it must explicitly amend
  the exclusive Gate contract and explain why duplicating ownership is safer; it cannot call
  that “no boundary change.”

### ADR2-004 — The tag query does not yet define a safe, relevant or sustainable Album pool

- Location: ADR D1 `:82-87`, D3 `:107-116`, AC-9 `:255-257`.
- MusicBrainz confirms that `tag` is a valid release-group search field, but its search API is
  Lucene-based and requires reserved characters to be escaped for literal input. Directly
  interpolating an external Genre name into `tag:<genre>` leaves spaces, quotes, colons,
  slashes and other syntax semantically undefined.
- Release-group search covers Albums, Singles, EPs and other primary/secondary types. The ADR
  does not decide which types satisfy OMDA's capital-A Album product meaning or filter out
  irrelevant result types.
- Always requesting the first 10 results is not a long-term source. After permanent history
  exclusion, the same top page is quickly exhausted even when more valid candidates exist.
  Search-index ordering and updates also make an unstated offset policy non-reproducible.
- RYM Genre names and MusicBrainz folksonomy tags are not guaranteed to be identical. There is
  no versioned Genre-to-query mapping, alias policy, exact tag rule or relevance threshold.
- Required revision:
  - specify escaped/quoted query construction and test hostile/special-character Genre names;
  - define allowed release-group primary/secondary types and required fields;
  - define a versioned Genre-to-MusicBrainz query/tag mapping with observable “no mapping” and
    “insufficient candidates” outcomes;
  - define bounded pagination/cursor behavior, cache keys and query-version invalidation so
    permanent history can move beyond page one without unbounded crawling;
  - state how search scores/tag evidence are used only for relevance and never become a
    popularity filter or alter Genre equal weighting.

### ADR2-005 — The request budget and pacing are not shared across MusicBrainz clients

- Location: ADR D3 `:107-116`, D1 `:84-87`, risk table `:224-225`.
- Reusing code from `MusicBrainzEnricher` does not automatically share its pacing state.
  A separate AlbumSource and Enricher can each satisfy an internal one-second delay while their
  combined calls exceed MusicBrainz's application/IP guidance. Concurrent runs make this worse.
- The ADR budgets only “successful requests.” Failed attempts and retries are still outbound
  load and must consume the same finite budget. OD-10 is specifically the RYM per-run page
  budget; it cannot silently become the MusicBrainz budget.
- Required revision: define one composition-owned MusicBrainz request coordinator shared by
  source and enricher, with one contactable User-Agent, host allowlist, pacing, retry accounting
  and a total attempt budget. Specify concurrent-run behavior (for example a single-run lock or
  shared limiter) and count **every HTTP attempt**, not only successes. Preserve MusicBrainz's
  documented maximum average of one request per second for the complete client.
- Official references:
  - `https://musicbrainz.org/doc/MusicBrainz_API/Rate_Limiting`
  - `https://musicbrainz.org/doc/MusicBrainz_API/Search`

### ADR2-006 — The production-source gate has no single enforceable provenance contract

- Location: ADR D2 `:98-105`, D5 `:127-136`, impact `:197-205`, AC-1/AC-2
  `:233-239`.
- D2 proposes `source/query/fetched_at/query_version/license`; D5 requires
  `license/origin_url/retrieved_at`; the field names and cardinality disagree. The ADR also
  leaves the public contract as “`AlbumSource.provenance()` or a field on every candidate.”
  Those are materially different models.
- Testing `source != sample` is not proof of provenance. A malformed adapter or imported file
  can self-label as an allowlisted string. The important invariant is that the selected facts
  and canonical IDs are bound to one validated source batch and its license/query evidence.
- Required revision: choose one versioned schema, preferably a `CandidateBatch`/source envelope
  with immutable source descriptor plus per-candidate MBID/facts, and define exactly where the
  trusted composition validates it before journal claim or delivery. Define origin URL/query,
  retrieval timestamp, query policy version, license identifier, demo flag and content digest
  consistently. AC-1 must also prove the committed identity and outbound fact both belong to
  that validated batch; AC-2 must cover missing, contradictory and forged provenance, not only
  a literal `sample` label.

### ADR2-007 — The proposed v3 rollback destroys durable delivery evidence

- Location: ADR D7 `:154-168`; Accepted ADR-0001 §15-5; IMPLEMENTATION_PLAN T2.6
  rollback contract.
- `attempt_id` is the association added specifically to bind receipt evidence to a delivery
  attempt. D7 proposes rollback by deleting that column. That is a destructive down-migration
  of real delivery/recovery evidence and reopens the ambiguity ADR-0001 was accepted to close.
- “`user_version >= 2` is legal” is also too broad: unknown future versions must fail closed,
  not be treated as compatible. Existing version-2 databases can have either the intended
  ADR layout (column present) or the buggy implementation layout (column absent), so version
  number alone is not a sufficient migration precondition.
- Required revision:
  - make v3 a forward migration with backup/restore and forward-fix rollback; do not delete
    attempt evidence from a real runtime database;
  - support and test v1, both observed v2 physical layouts, and v3 by inspecting the schema in
    one transactional migration;
  - preserve null only for genuine legacy rows, add the column idempotently, then set v3;
  - fail closed for `user_version > 3` or an unknown schema fingerprint;
  - document old-binary compatibility rather than claiming a destructive v3→v2 downgrade is
    harmless.

### ADR2-008 — The no-LLM decision is sound, but the v0.1 config must not advertise an inactive provider

- Location: ADR D6 `:138-152`, AC-8 `:252-254`.
- Defining v0.1 as deterministic/no-LLM is an acceptable safety and honesty choice, provided
  the Master Plan and implementation plan are amended explicitly. The external execution
  model used to develop OMDA is unrelated to OMDA's runtime LLM mode.
- A `provider` config value that exists in v0.1 but is neither implemented nor activated is a
  misleading public surface. A template sentence should likewise not be archived as if it were
  model-generated narrative.
- Required revision: for the v0.1 config schema either allow only `deterministic`, or make
  `provider` fail closed during config validation before any run/journal/network side effect
  with an explicit “not supported in v0.1” error. Store no narrative (or a typed deterministic
  report mode marker), not a fake generated sentence. State that adding provider mode later
  requires its own implemented adapter, schema/version change, cost/secret controls and Gate
  acceptance.

## Required revised acceptance additions

In addition to the proposal's AC-1 through AC-9 after correction, the revised ADR must require:

1. License/provenance fixtures distinguish CC0 core facts from supplementary tag/search
   evidence; no generated package is labelled CC0 as a whole without a valid basis.
2. A normal runtime query writes only to a Git-ignored cache; an explicit export/contribution
   workflow is the only path that creates reviewable Git data.
3. Lucene-reserved and multiword Genre names cannot alter query structure; missing mappings and
   irrelevant release-group types fail clearly.
4. After page-one candidates enter permanent history, bounded pagination can discover a later
   page; exhausted/unstable results fail without sample substitution or history pollution.
5. Source + enricher share one request coordinator; every attempt across both consumes the
   budget and combined call timestamps respect the service pacing rule.
6. Provenance schema inconsistencies, missing digest/origin/license and a source falsely
   claiming production status all fail before PushPlus and before official-history mutation.
7. v2-with-column, v2-without-column and future-version databases follow the revised safe v3
   migration/fail-closed rules without deleting delivery evidence.

## Scope and governance

- `BLOCKED_ARCHITECTURE / ADR_PENDING` remains the correct project state.
- ADR-0002 must remain `Proposed`; the Executor must not write `Accepted`.
- No D1-D8 implementation, merge, tag or G5 work is authorized by this review.
- Keep the correct parts of the proposal: sample fail-closed, canonical release-group MBID,
  RYM/anti-bot prohibitions, deterministic v0.1 direction, G4-002C/G4-007C/G4-002E repairs and
  explicit acceptance mapping.
- Revising this ADR must not reopen rejected popularity filters, LLM selection, mass prefetch,
  RYM Album Detail fan-out or browser circumvention.

## Decision

**REVISE**

ADR-0002 at `702d1d3f4b34527403474d783882549d123d56ef` is not accepted. Revise the
license/source decision, runtime-vs-Git cache boundary, Gate ownership, query/pagination/rate
contract, provenance schema and non-destructive v3 migration. Return one new documentation-only
ADR candidate; do not begin G4-010 or any other production implementation before Reviewer
acceptance.
