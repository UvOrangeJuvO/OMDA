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

---

## Re-review 1 — candidate `2be8ee110fabe9d6979f5d23a374e06bae146294`

### Reviewed object

- Re-review date: 2026-08-23
- Exact original base SHA: `68e3d453c7b803d2090cb1318f48e58eb18d6390`
- Previous rejected candidate: `07851eb4c8cb13a3bb2a06382c74e6cba7c3c27a`
- Previous Reviewer commit: `f42ce3a5e64e9443616406daa973ace488a6b081`
- Exact repair candidate SHA: `2be8ee110fabe9d6979f5d23a374e06bae146294`
- Executor repair report: `reviews/stage-03/G3_007_REPAIR_REPORT.md`

The repair candidate has the correct merge-base, is a descendant of the previous Reviewer
commit, and contains one focused repair commit after it. The worktree was clean. No incremental
G4 implementation was introduced. The repaired implementation now supplies distinct
Genre-bound batches, 20 unique release-group MBIDs, a provider-neutral `source_batch` port,
Genre content digests and stronger cache limits. Those are material improvements.

The complete suite nevertheless cannot establish acceptance. Independent checks found that
unreviewed license statements and a Genre ID absent from the reviewed Genre package can still
cross the supposedly validated source boundary. The tracked machine schemas also disagree
with the runtime contract. These are source-trust failures within G3-007, not reasons to begin
G4.

### Previous-finding closure status

| Previous finding | Status | Re-review result |
|---|---|---|
| G3-007-001 Genre-bound batches | **CLOSED** | Records and batches carry `genre_id`; exact filtering and cross-Genre tests exist. |
| G3-007-002 canonical MBIDs | **CLOSED for package content** | 20 unique UUID-shaped release-group MBIDs are present and required for non-demo records. The curation tool compliance issue is recorded separately below. |
| G3-007-003 Genre provenance/completeness | **PARTIAL / OPEN** | Content digest, demo and coverage checks improved, but selected IDs are not proven to belong to the reviewed Genre content. |
| G3-007-004 provider-neutral boundary | **CLOSED** | `AlbumSource.source_batch()` supplies a concrete provider-neutral batch; curated and fake adapters implement it. |
| G3-007-005 license/provenance layers | **PARTIAL / OPEN** | Four fields exist but are not bound to the registry or integrity digest. |
| G3-007-006 cache robustness | **CLOSED with P2 test debt** | TTL/key/manifest behavior materially improved; the tamper test does not actually read the tampered disk entry. |

### [P1] G3-007-003 remains open — selected Genre IDs are not bound to reviewed Genre records

- Location: `src/omda/ports/source.py:71-80,118-142` and source-set assembly validation;
  `data/genres/curated-omda/genres.jsonl`
- Evidence: `GenreSourceDescriptor` binds only an opaque content digest. Source-set assembly
  verifies that each batch matches the caller-provided selected ID, but it receives neither
  the canonical Genre records nor a digest-bound eligible-ID set.
- Independent reproduction: a real Ambient batch was consistently relabelled to `phantom`,
  its self-digest recomputed, and then assembled with the real registered curated Genre
  descriptor and `selected_genre_ids=("phantom",)`. Validation accepted the source set even
  though `phantom` is absent from the reviewed Genre package.
- Impact: the source boundary proves internal consistency of caller-controlled labels, not
  that selection came from the reviewed Genre source. This breaks the required Genre-to-Album
  provenance chain.
- Required acceptance: bind the eligible Genre IDs to the registered Genre content—either by
  validating against canonical Genre records at assembly time or by carrying a registry- and
  digest-bound eligible-ID set—and add a negative `phantom`-ID test.

### [P1] G3-007-005 remains open — license/provenance layers are self-asserted

- Location: `src/omda/ports/source.py:43-68,145-158`;
  `src/omda/sources/registry.py:124-159`; `data/schemas/source_registry.schema.json`
- Evidence: the four new fields `license_core_facts`, `license_supplementary_used`,
  `license_service_terms` and `license_derived_package` are omitted from the canonical batch
  digest and from the registry entry/verification contract. `retrieved_at`, `data_scope` and
  `dataset_version` are also not fully registry-bound.
- Independent reproduction: changing each license layer to a forged value and changing
  `retrieved_at` to 2099 left the batch digest unchanged; both batch integrity verification
  and full source-set assembly still passed.
- Impact: a package can present unreviewed licensing or provenance statements while retaining
  a valid reviewed identity. The four-layer representation is therefore descriptive text,
  not an enforced trust boundary.
- Required acceptance: make every immutable delivery/governance field part of the reviewed
  registry contract or bind a complete descriptor digest; include it in batch/Genre integrity
  validation; add one negative mismatch test for every bound field.

### [P1] G3-007-007 — tracked machine schemas disagree with the runtime source contract

- Location: `src/omda/ports/source.py:33,101-115`;
  `data/schemas/candidate_batch.schema.json`;
  `data/schemas/genre_source.schema.json`;
  `data/genres/curated-omda/source.yaml`;
  `data/genres/rym-sample/source.yaml`
- Evidence:
  - runtime declares CandidateBatch schema version `2` and requires `genre_id` plus a source
    descriptor, while the tracked CandidateBatch schema remains version `1`, contains neither
    field, and is not used to validate the serialized/cache/import boundary;
  - the tracked Genre schema declares version `3`, while both Genre package manifests and
    corresponding registry entries declare schema version `1`.
- Impact: a consumer following the published schema cannot construct the runtime object, and
  repository review cannot determine which version actually governs accepted packages.
- Required acceptance: publish and exercise the complete v2 CandidateBatch envelope, make
  Genre package/schema version semantics consistent, validate serialized boundaries against
  the tracked schema, and add tests that fail on version drift.

### [P1] G3-007-008 — the MusicBrainz curation tool does not use a contactable User-Agent

- Location: `tools/curate_mbids.py:2-7,23-25`
- Evidence: the tool claims a contactable User-Agent but hardcodes
  `mailto:omda-curation@example.invalid`. The reserved `.invalid` address cannot contact a
  maintainer. The shipped tool performs live requests and was cited as evidence for the
  committed identities.
- Impact: the documented curation flow is not safely reproducible under the upstream service's
  identification requirement, weakening both external-service compliance and provenance.
- Required acceptance: require an owner-supplied meaningful User-Agent/contact value, reject
  missing or placeholder values (including `.invalid`), and test this without network access
  using an injected transport. Do not hardcode a contributor's personal contact in the repo.

### [P2] G3-007-009 — two integration tests do not safely prove their stated behavior

- Location: `tests/integration/test_g3_007_checkpoint.py:189-232`;
  `src/omda/adapters/curated.py:122-140`
- Evidence:
  - the Genre tamper test edits the tracked production `genres.jsonl` in place and restores it
    in `finally`; interruption or parallel execution can leave or observe corrupted source;
  - the cache tamper test reuses the same adapter after warming `_batch_cache`, so the second
    call returns the in-memory batch and never reads the tampered disk entry. The disk repair
    branch may be correct, but this test does not exercise it.
- Required acceptance: copy the package to `tmp_path` before tampering and construct a fresh
  adapter over the same runtime cache after disk corruption.

### Re-review acceptance matrix

| G3-007 / ADR-0002 criterion | Status |
|---|---|
| Focused G3 repair; G4 remains frozen | **PASS** |
| Distinct Genre-bound production candidates | **PASS** |
| Canonical release-group identity present | **PASS** |
| Selected Genre belongs to reviewed Genre content | **FAIL — G3-007-003** |
| Provider-neutral CandidateBatch port | **PASS** |
| Review-bound four-layer license/provenance | **FAIL — G3-007-005** |
| Versioned machine schema matches runtime contract | **FAIL — G3-007-007** |
| Reproducible, compliant MBID curation flow | **FAIL — G3-007-008** |
| Safe/effective tamper regression tests | **PARTIAL — G3-007-009** |
| Open P0/P1 findings | **FOUR P1** |

### Independent checks and limitations

- Verified the exact SHA, branch ancestry, exact original merge-base, focused repair commit,
  clean worktree and `git diff --check`.
- Ran the complete suite from an isolated archive initialized as a temporary Git repository:
  **671 passed**. Ruff also passed. This shows regression stability, but does not close the
  semantic trust failures above.
- Reproduced forged-license acceptance and unregistered `phantom` Genre acceptance with local
  probes against the real registry and package contracts.
- Spot-checked multiple committed release-group MBIDs against official MusicBrainz entity
  pages. Not all 20 were independently live-confirmed because of upstream rate limiting and
  browser verification. No live request was made with the candidate's invalid User-Agent.
- No production code/data, merge, tag, push or G4 work was performed by the Reviewer.

### Re-review verdict

**CHANGES_REQUESTED**

Candidate `2be8ee110fabe9d6979f5d23a374e06bae146294` is not accepted. G3-007 remains
open and G4 must not begin. The four P1 findings can be repaired within accepted ADR-0002;
another ADR is not presently required. Return a new full candidate after focused repair and
full regression evidence.

---

## Re-review 2 — candidate `c4ae1911c3f0092806da804da929f9e0d3045f93`

### Reviewed object

- Re-review date: 2026-08-23
- Exact original base SHA: `68e3d453c7b803d2090cb1318f48e58eb18d6390`
- Previous candidate: `2be8ee110fabe9d6979f5d23a374e06bae146294`
- Previous Reviewer commit: `09187426ca3f4f05eca27292fc448cc5f3ce470a`
- Exact repair candidate SHA: `c4ae1911c3f0092806da804da929f9e0d3045f93`
- Executor repair report: `reviews/stage-03/G3_007_REPAIR_REPORT.md`

The exact SHA, ancestry and original merge-base are correct. The candidate contains one focused
G3-007 repair commit after the previous Reviewer commit, the starting worktree was clean, and
no incremental G4 implementation was found. The full suite and lint are green. Registry binding
of the four license layers, owner-supplied MusicBrainz User-Agent handling and both test-isolation
repairs are now implemented correctly.

Acceptance is still blocked at the source-integrity boundary. The new
`eligible_genre_ids` tuple is caller-controlled rather than registry/content bound; cache input
does not actually pass through the tracked CandidateBatch schema; and the digest serialization
is ambiguous for valid text fields. Independent probes reproduced each failure below.

### Previous-finding closure status

| Previous finding | Status | Re-review result |
|---|---|---|
| G3-007-003 selected Genre provenance | **OPEN** | The new eligible-ID tuple can itself be forged without changing the registered Genre content digest. |
| G3-007-005 immutable license/provenance binding | **CLOSED** | All descriptor fields are now registry-bound and included in the source digest fields; field-by-field negative tests exist. |
| G3-007-007 machine schema/runtime alignment | **PARTIAL / OPEN** | Tracked files and write serialization align, but cache deserialization bypasses the schema and accepts unsupported versions. |
| G3-007-008 curation User-Agent | **CLOSED** | Owner-supplied value is required; placeholder values are rejected; transport test is network-free. |
| G3-007-009 tamper-test safety/effectiveness | **CLOSED** | Genre data is copied to temporary storage and a fresh adapter exercises disk-cache corruption. |

### [P1] G3-007-003 remains open — eligible Genre membership is still self-asserted

- Location: `src/omda/ports/source.py:71-87,277-292`;
  `src/omda/adapters/datasets.py:136-177`;
  `src/omda/sources/registry.py:140-195`
- Evidence: `GenreDatasetAdapter` normally derives `eligible_genre_ids` from the same records,
  but the trusted assembly boundary receives only a dataclass descriptor. Neither the registry
  nor `content_digest` binds the tuple, and `verify_descriptor()` does not compare it.
- Independent reproduction: append `phantom` to a real registered descriptor's
  `eligible_genre_ids`, consistently relabel a real batch and its records to `phantom`, and
  recompute the batch's self-digest. `assemble_validated_source_set()` accepts the result even
  though `phantom` is absent from the reviewed Genre records.
- Impact: the repair moves the untrusted assertion from `selected_genre_ids` into another
  untrusted field; it still does not prove membership in reviewed Genre content.
- Required acceptance: either bind the canonical eligible-ID set (or its deterministic digest)
  in the reviewed registry and verify it, or pass validated canonical Genre records into
  assembly and derive membership there. Add a negative test that forges the descriptor tuple,
  not merely the caller's selected tuple.

### [P1] G3-007-007 remains open — CandidateBatch schema is enforced only on writes

- Location: `src/omda/adapters/curated.py:115-143,313-375`;
  `data/schemas/candidate_batch.schema.json`
- Evidence: `_batch_to_json()` validates output, but `_batch_from_json()` directly constructs
  objects without `_validate_record()`. `verify_batch_integrity()` checks only a self-computed
  digest and does not require `schema_version == BATCH_SCHEMA_VERSION`.
- Independent reproduction:
  - a serialized batch with an unknown top-level field was parsed and passed integrity checks;
  - a cache batch changed to schema version `999`, with its digest recomputed, was returned by
    the public `source_batch()` path as schema `999` even though the tracked schema permits only
    version `2`.
- Impact: the published machine contract cannot reject unsupported or structurally drifting
  cache/import data, which was the central acceptance requirement for this finding.
- Required acceptance: validate the raw payload against the tracked schema before constructing
  any object; reject unsupported runtime/query-policy versions explicitly; add public cache-hit
  tests for unknown fields, version `999`, malformed nested source and malformed candidates.

### [P1] G3-007-010 — digest canonicalization is ambiguous for valid record values

- Location: `src/omda/ports/source.py:152-227`
- Evidence: source, Album and Genre fields are concatenated with literal `|` and record separator
  characters without length-prefixing or escaping. Album title/artist and Genre name/family
  schemas permit `|`.
- Independent reproduction:
  - Album facts `(title="A|B", artist="C")` and `(title="A", artist="B|C")` produce the same
    `digest_batch()` value;
  - otherwise identical valid Genre facts with `(name="A|B", family="C")` and
    `(name="A", family="B|C")` produce the same `digest_genre_records()` value.
- Impact: changing reviewed facts can preserve the declared SHA-256 digest without breaking
  SHA-256; the ambiguity is in the preimage encoding. Content integrity therefore is not
  actually guaranteed for the allowed data domain.
- Required acceptance: use a canonical unambiguous encoding, preferably deterministic JSON
  arrays/objects with UTF-8 and fixed separators/sorted keys, or length-prefix every field.
  Add collision-regression tests covering separator characters in every free-text field.

### [P1] G3-007-011 — an Album CandidateBatch may claim a Genre source

- Location: `data/schemas/candidate_batch.schema.json:10-12`;
  `src/omda/ports/source.py:101-122,295-317`
- Evidence: CandidateBatch's schema permits source kind `genre` or `album`, and assembly never
  requires `batch.source.kind == "album"`.
- Independent reproduction: replace a real Ambient batch's Album source descriptor with the
  real registered Genre descriptor, recompute the batch digest, and assemble it with the real
  registry. Validation accepts the CandidateBatch with `source.kind == "genre"`.
- Impact: the validated boundary does not prove that Album candidates came from a reviewed
  Album source; source-role provenance can be confused while all checks pass.
- Required acceptance: restrict CandidateBatch source kind to `album` in both schema and domain
  validation, reject the wrong kind before registry lookup, and add a negative assembly test.

### Re-review 2 acceptance matrix

| Criterion | Status |
|---|---|
| Focused G3 repair; no G4 implementation | **PASS** |
| License/provenance fields bound to reviewed registry | **PASS** |
| Owner-supplied, non-placeholder MusicBrainz User-Agent | **PASS** |
| Tamper tests isolated and exercising disk path | **PASS** |
| Selected Genre membership bound to reviewed content | **FAIL — G3-007-003** |
| Read and write boundaries enforce CandidateBatch v2 schema | **FAIL — G3-007-007** |
| Digests unambiguously bind allowed fact values | **FAIL — G3-007-010** |
| CandidateBatch proves an Album-source role | **FAIL — G3-007-011** |
| Open P0/P1 findings | **FOUR P1** |

### Independent checks

- Verified exact SHA, branch, ancestry, original merge-base, focused increment, clean starting
  worktree and `git diff --check`.
- Ran the complete suite from an isolated archive initialized as a temporary Git repository:
  **693 passed in 5.93 seconds**. Ruff reported **all checks passed**.
- Reproduced forged eligible membership, public cache serving schema `999`, acceptance of a
  Genre-kind Album batch and two delimiter-based digest collisions using local read-only probes.
- No production code/data, merge, tag, push, network request or G4 work was performed by the
  Reviewer.

### Re-review 2 verdict

**CHANGES_REQUESTED**

Candidate `c4ae1911c3f0092806da804da929f9e0d3045f93` is not accepted. G3-007 remains
open; do not merge and do not begin G4. These findings are implementation-level corrections
inside accepted ADR-0002, so another ADR is not currently required. Return a new full candidate
after focused repair and full regression evidence.
