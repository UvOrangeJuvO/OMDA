# G3-007 Checkpoint Independent Review Verdict

## Reviewed object

- Reviewer: GPT-5.6 Sol in Codex
- Review date: 2026-08-22
- Checkpoint: G3-007 — curated production source boundary
- Exact original base SHA: `68e3d453c7b803d2090cb1318f48e58eb18d6390`
- Exact candidate SHA: `07851eb4c8cb13a3bb2a06382c74e6cba7c3c27a`
- Accepted ADR-0002 Reviewer checkpoint: `883b86ffb3cb4cdda0216786b91ea163ae4cfce3`
- Candidate branch observed: `exec/g4-agent-delivery`
- Executor report: `reviews/stage-03/G3_007_EXECUTOR_REPORT.md`
- Executor test evidence: `reviews/stage-03/G3_007_TEST_RESULTS.txt`

The candidate is a descendant of the exact original base and the merge-base is correct. The
worktree was clean at review start. The complete base-to-candidate chain and the focused
`883b86f..07851eb` G3-007 increment were inspected. The focused increment contains only
source/data contracts, curated packages, contribution/cache code, tests and governance
artifacts; it does not add further G4 production composition, PushPlus wiring, migration or LLM
runtime changes. G4 therefore remains frozen as required by ADR-0002 §8.3.

The ordinary suite, lint and diff-format checks are green. Independent semantic probes,
however, show that the checkpoint's claimed real 3×3 source proof is not true: every Genre is
served the same 20 Albums, none of the 20 records has a Genre binding or canonical MBID, and a
registered demo Genre can be represented by a `ValidatedSourceSet` whose `is_demo` value is
false. These are open P1 contract failures, so this checkpoint cannot be accepted.

## Findings

### [P1] G3-007-001 — Album batches are not bound to the requested Genre

- Location: `data/schemas/album_candidate.schema.json:4-20`;
  `data/albums/curated-omda/albums.jsonl:1-20`;
  `src/omda/adapters/curated.py:60-75`, `:196-218`;
  `tests/integration/test_g3_007_checkpoint.py:38-67`
- Evidence/reproduction:
  - The Album schema and all 20 records contain no `genre_id` or equivalent reviewed
    Genre-membership field.
  - `_build_batch(genre)` never uses `genre`; it copies every record into every batch.
  - `candidates_for_genre()` then overwrites each returned candidate's Genre tuple with the
    requested Genre, relabelling unrelated records rather than proving membership.
  - Independent probe: Ambient and Bebop each returned 20 records with exactly equal Album-ID
    sequences. The Ambient batch contained `curated-omda-bebop-0001` and
    `curated-omda-bebop-0002` immediately after its four Ambient-labelled IDs.
  - The checkpoint test loops over five Genres but only checks `len(batch) >= 3`; the same
    batch therefore satisfies all five iterations.
- Impact: OMDA may recommend Bebop/Krautrock/Tuareg/IDM records as Ambient and vice versa. The
  source does not establish a real Genre-specific candidate relation and can fill a 3×3 run
  with unrelated Albums, contrary to the product rule and ADR-0002's curated
  Genre→release-group source decision.
- Violated contract: Master Plan §3.2 and §6; ADR-0002 D1/D6, AC-1, AC-9A and §8.2/§8.8.
- Required acceptance:
  1. add an explicit, schema-validated Genre binding to each Album record and to the batch
     request/envelope; preserve it through import/export and include it in the digest;
  2. filter by exact reviewed Genre binding and reject unknown, contradictory or empty
     coverage rather than relabelling records;
  3. add negative tests proving no Album from another Genre can enter the requested batch and
     positive tests proving the five real batches are not identical;
  4. exercise actual deterministic 3×3 selection from these packages, including permanent
     history exclusion and explicit exhaustion/shortage behavior.

### [P1] G3-007-002 — The selected curated source contains no canonical release-group identity

- Location: `data/albums/curated-omda/albums.jsonl:1-20`;
  `data/schemas/album_candidate.schema.json:9-13`;
  `src/omda/ports/source.py:59-69`;
  `src/omda/adapters/curated.py:288-296`;
  `tests/integration/test_g3_007_checkpoint.py:70-88`;
  `reviews/stage-03/G3_007_EXECUTOR_REPORT.md:42-49`
- Evidence/reproduction:
  - All 20 production-labelled records omit `mbid`; the independent count was **0/20**.
  - `_identity_for()` consequently returns `None`, so the existing AlbumSource path exposes
    no stable canonical identity.
  - The test named `test_committed_identity_and_facts_trace_to_validated_batch` does not run
    the engine, commit history or assert one MBID. It only builds a dictionary of source
    strings and checks that those strings are nonempty.
  - The report defers canonical identity to future G4 wiring of `MusicBrainzEnricher`, but the
    accepted default source is specifically a curated Genre→release-group-MBID package and
    G4 has not yet been authorized to repair a missing source-side identity contract.
- Impact: the checkpoint cannot prove canonical permanent exclusion or that the eventually
  committed identity belongs to the validated source batch. Runtime fallback to local
  `album_id` does not close the release-group identity requirement.
- Violated contract: SPEC §2.4; Master Plan §3.2/§5; ADR-0002 D1/D2/D6, AC-1, AC-9A and
  §8.8.
- Required acceptance:
  1. populate the production curated package with verified MusicBrainz release-group MBIDs
     and record their provenance, without enabling the unapproved live tag-search source;
  2. require and validate canonical MBID for production Album records while retaining an
     explicitly demo-only/legacy fixture path where appropriate;
  3. reject duplicate canonical IDs and prove MBID changes affect the batch digest;
  4. replace the current evidence-name test with assertions that selected production records
     have valid canonical identity from the same validated batch. G4 may later prove journal,
     outbound and committed-history wiring, but G3-007 must supply the identity-bearing source.

### [P1] G3-007-003 — Genre provenance and demo policy are not content-bound or fail-closed

- Location: `src/omda/ports/source.py:37-57`, `:88-120`, `:166-186`;
  `src/omda/adapters/datasets.py:120-150`;
  `tests/integration/test_g3_007_checkpoint.py:91-95`;
  `tests/unit/test_source_contracts.py:164-219`
- Evidence/reproduction:
  - `GenreSourceDescriptor` adds no Genre content digest, even though ADR-0002 requires the
    Genre source ID and digest to be run evidence.
  - `ValidatedSourceSet.is_demo` inspects only Album batches and ignores
    `genre_descriptors`.
  - Independent probe with a registry entry matching `rym-sample` produced
    `descriptor.demo=True` but `ValidatedSourceSet.is_demo=False` when paired with a non-demo
    Album batch.
  - `assemble_validated_source_set()` also accepts an entirely empty source set and returns
    `is_demo=False`; it does not enforce any Genre-to-batch coverage or cardinality.
  - The demo checkpoint test asserts only the raw descriptor flag, so it never exercises the
    production-facing source-set result.
- Impact: G4 could trust `is_demo=False` and externally deliver using a demo Genre package;
  Genre content can change without a Genre digest; empty or structurally unrelated inputs can
  be presented as a validated production source set.
- Violated contract: ADR-0002 D6, AC-2, AC-9A and §8.2/§8.4/§8.5/§8.8.
- Required acceptance:
  1. bind the Genre descriptor to a deterministic digest over the reviewed manifest and Genre
     records, and verify that digest through the registry/source-set boundary;
  2. compute demo status across both Genre descriptors and Album batches;
  3. reject empty/incomplete source sets and enforce the selected Genre-to-batch coverage
     needed by the 3×3 run;
  4. add negative tests for registered demo Genre + production Albums, empty assembly,
     tampered Genre data and missing/duplicate/unrelated Genre batches.

### [P1] G3-007-004 — CandidateBatch remains a concrete side API that the application Port bypasses

- Location: `src/omda/ports/album.py:10-17`;
  `src/omda/adapters/curated.py:60-99`, `:261-285`;
  `src/omda/orchestrator/run.py:381-392`;
  `tests/contract/test_ports.py:98-99`
- Evidence/reproduction:
  - The provider-neutral `AlbumSource` Port still returns only
    `list[AlbumCandidate]`. `CandidateBatch` is exposed only through the concrete
    `CuratedAlbumSource.batch_for_genre()` method.
  - `RunEngine` consumes `candidates_for_genre()` directly and therefore receives candidates
    before any registry or `ValidatedSourceSet` validation. The candidate adds no
    provider-neutral contract through which the trusted application boundary can require the
    batch evidence.
  - A cache hit is deserialized and returned without `verify_batch_integrity()`; the direct
    `candidates_for_genre()` path can therefore materialize cached records without even the
    digest check that later assembly would perform.
  - Existing Port contract tests explicitly lock `AlbumSource` to only
    `candidates_for_genre`, demonstrating that the accepted ADR's public source-envelope
    amendment was not implemented in G3-007.
- Impact: G4 would have to import the concrete adapter or keep the current validation bypass.
  Either choice breaks the accepted `Orchestrator → Ports ← Adapters` boundary and makes
  “validate after FETCH, before SELECT” unenforceable for all AlbumSource implementations.
- Violated contract: SPEC §3.1/§3.2; accepted IMPLEMENTATION_PLAN B.3/B.9; ADR-0002 D4/D6,
  §4 impact analysis and §8.4.
- Required acceptance:
  1. implement the ADR-authorized provider-neutral source-envelope Port contract in G3-007,
     with fake/contract parity; do not leave it as a concrete-only parallel API;
  2. make it impossible for the production path to reach selection without registry and
     digest validation; G4 may perform the final composition wiring only after this checkpoint
     is accepted;
  3. validate cached batches before returning them, or treat an invalid cached entry as a
     typed miss/failure; add tampered-cache tests that exercise the public Port path.

### [P1] G3-007-005 — The production manifests collapse the license layers rejected by ADR-0002

- Location: `data/albums/curated-omda/source.yaml:1-16`;
  `data/albums/curated-omda/README.md:3-14`;
  `data/genres/curated-omda/source.yaml:1-13`;
  `data/genres/curated-omda/README.md:3-11`;
  `data/sources/registry.jsonl:1-2`
- Evidence:
  - The Album package names a MusicBrainz search URL as origin while declaring the package
    `CC0-1.0`; its README describes all 20 candidates as CC0 curated facts.
  - The Genre package names Wikipedia as origin while also declaring the package's taxonomy
    CC0, without recording an independent-curation basis or the upstream text-license layer.
  - The same declarations are copied into the registry in the same candidate commit; that
    proves descriptor equality, not the human review, source derivation or license basis.
  - ADR-0002 was revised specifically to prohibit collapsing core facts, tag/search evidence,
    service terms and the derived package into one blanket CC0 claim. No legal conclusion is
    made here; the repository evidence simply does not satisfy that accepted provenance
    contract.
- Impact: the package may be externally delivered and later redistributed as production data
  under a license claim that the accepted ADR explicitly disallows. The absent MBIDs and
  per-record derivation evidence make the claimed origin harder to audit.
- Violated contract: SPEC §3.3; Master Plan §7; ADR-0002 D1/D2, AC-9A, the revised acceptance
  additions, and §8.11.
- Required acceptance:
  1. represent the four license/provenance layers required by ADR-0002 and use an accurate
     per-source/per-package license identifier instead of a blanket claim;
  2. document whether Genre membership and Album selection were independently curated or
     derived from upstream search/tag/index material, with reviewable record-level evidence;
  3. bind the exact reviewed dataset version/content to the registry and add fixtures that
     reject a package whose license/origin derivation does not match the reviewed policy.

### [P2] G3-007-006 — RuntimeCache does not implement its stated FIFO/TTL contract robustly

- Location: `src/omda/adapters/curated.py:299-347`;
  `tests/unit/test_runtime_cache.py:25-41`
- Evidence:
  - Eviction sorts sanitized filenames lexicographically and deletes the first name; it does
    not track insertion order. The `a`, `b`, `c` test passes only because alphabetic and
    insertion order happen to match.
  - `ttl_seconds` is not required to be a positive finite number. Negative values expire
    immediately and NaN disables the comparison in practice.
  - Sanitization maps distinct keys such as `a/b` and `a_b` to the same cache file.
- Impact: cache behavior is bounded in size but not the deterministic FIFO behavior claimed
  by the implementation/report; invalid configuration and key collisions can serve or evict
  the wrong record. This is lower severity than the source-integrity failures above.
- Required acceptance: validate positive finite TTL, use collision-resistant keys, implement
  insertion-time FIFO (or document/test another deterministic policy), and add nonalphabetic
  insertion/collision/invalid-TTL tests.

## Acceptance matrix

| G3-007 / ADR-0002 criterion | Status | Evidence |
|---|---|---|
| Focused G3 source-side scope; no new G4 implementation | **PASS** | `883b86f..07851eb` file/symbol inspection |
| Real, non-demo, Genre-relevant curated 3×3 source | **FAIL** | G3-007-001; identical all-Album batches |
| Canonical release-group identity and permanent-exclusion basis | **FAIL** | G3-007-002; MBID 0/20 |
| Genre + Album content-bound provenance and demo rejection | **FAIL** | G3-007-003 |
| Provider-neutral validation after FETCH and before SELECT | **FAIL** | G3-007-004 |
| License/provenance layer separation | **FAIL** | G3-007-005 |
| Explicit contribution flow; ordinary run does not write tracked data | **PASS** | contribution/cache code and tests |
| Bounded, TTL runtime cache | **PARTIAL** | hard entry cap works; G3-007-006 remains |
| No live tag-search source, RYM crawl, anti-bot behavior or Album Detail fan-out | **PASS** | focused diff and source inspection |
| Regression suite and lint | **PASS but insufficient** | 659 tests pass; missing semantic assertions above |
| Open P0/P1 findings | **FIVE P1** | G3-007-001 through G3-007-005 |

## Independent checks performed and limitations

- Verified both full SHAs, ancestry, merge-base, branch and clean starting worktree.
- Inspected the full original-base chain and all 27 files in the focused G3-007 increment;
  `git diff --check` passed.
- Independently ran the complete suite in a temporary Python 3.12 environment with cache
  disabled: **659 passed**.
- Independently ran Ruff with its cache disabled: **all checks passed**.
- Reproduced identical Ambient/Bebop batches, zero MBIDs, a registered demo Genre yielding
  `ValidatedSourceSet.is_demo == False`, and acceptance of an empty source set using local,
  read-only probes.
- No live MusicBrainz, Wikipedia, RYM or PushPlus request was made. License finding
  G3-007-005 is a contract/provenance audit, not legal advice.
- No production code, data package, merge, tag, push or external state was changed by the
  Reviewer.

## Required repair scope

The Executor should remain on the current branch and repair only G3-007 source/data scope:

- Genre-bound Album records and CandidateBatch/source-envelope contracts;
- canonical release-group MBIDs and their reviewable provenance;
- Genre digest/demo/source-set completeness validation;
- provider-neutral Port/contract tests and cache-integrity behavior;
- accurate data-license manifests/registry bindings;
- focused regression tests, repair report, test evidence and state update.

Do not begin G4 production composition, PushPlus wiring, v3 migration or runtime LLM work.
These findings can be closed within the already accepted ADR-0002 design. If the Executor
instead needs to remove canonical MBIDs from the curated-source contract, weaken the validated
source boundary or change the accepted license model, it must stop at `BLOCKED_ARCHITECTURE`
and submit an ADR rather than silently changing semantics.

## Verdict

**CHANGES_REQUESTED**

Candidate `07851eb4c8cb13a3bb2a06382c74e6cba7c3c27a` is not accepted. G3-007 remains
open, must not be merged or tagged as accepted, and G4 must not begin. The Executor may create
focused G3-007 repair commits and return a new full candidate for re-review.
