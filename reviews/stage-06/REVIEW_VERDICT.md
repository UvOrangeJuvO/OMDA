# Gate G6 Independent Review Verdict

## Reviewed object

- Reviewer: GPT-5.6 Sol in Codex
- Review date: 2026-09-18
- Gate: G6 — Skill Distribution Beta
- Original base: `c15fbbe63fb7409483bf092fe7df926868ef5dda`
- ADR-0003 acceptance checkpoint: `608b4d25cbd12abda767bf1a2559a092145c630a`
- Candidate: `88324ae3a3a95d4372a6548da31d836a514ada3d`
- Candidate branch observed: `exec/g6-skill-beta-adr`
- Executor report: `reviews/stage-06/EXECUTOR_REPORT.md`

The candidate is a clean direct child of the accepted ADR checkpoint and the merge-base with
the supplied original base is exact. The worktree was clean at review start. The 19-file scope
is confined to the G6 Skill, G6 evidence and project state; the accepted 3x3 Core is untouched.

The multi-source product model is implemented in the intended shape: one read-only Source file
per curator, repeatable `--source`, in-memory deduplication, per-source annotations, private
Profile state and a separate local history. However, independent negative probes found six
blocking contract failures that the green suite does not exercise. G6 is not yet acceptable.

## Findings

### [P1] G6-001 — The seed and selection-pool digest do not implement the accepted protocol

- Location: `skills/omda-daily-discovery/scripts/daily_pick.py:613-675`
- Evidence:
  - `seed_material_digest()` adds `consumed_picks` to the seed. ADR-0003 D11 and §10 C1 bind
    the seed to exactly the day key, algorithm version and admissible selection-pool digest.
  - `select()` computes the pool digest before removing the immediately previous Genre. Thus
    an Album that cannot be selected today because its Genre is under the anti-repeat rule can
    still change the digest, seed and choice among the actually usable Genres.
  - Independent probes showed different seeds for the same day/pool with consumed counts 0/1,
    and different pool digests after adding an Album only to the excluded previous Genre.
- Impact: identical accepted selection projections can produce different picks, and ineligible
  data can influence the result. The history evidence no longer proves the pool actually used.
- Required repair:
  1. apply the anti-repeat/cooldown rule before constructing the canonical selection projection;
  2. hash only that final usable pool;
  3. derive the seed from exactly `(day_key, algorithm_version, selection_pool_digest)`;
  4. add negative fixtures for changed history length with the same projection and mutations
     confined to the excluded Genre.

### [P1] G6-002 — The unique-Genre exception is reported backwards and sometimes not reported

- Location: `skills/omda-daily-discovery/scripts/daily_pick.py:647-675`
- Evidence:
  - When several groups exist and removing the prior group leaves one group, the implementation
    says the anti-repeat rule was “waived”; it was actually applied.
  - When the only admissible group is the same as the previous successful group, repetition is
    necessarily allowed but `forced_note` is `None`. ADR-0003 D8 requires this case to be
    explicitly marked as the unique available Genre.
- Impact: user-visible audit text states the opposite rule in one branch and omits the required
  exception disclosure in the real waiver branch.
- Required repair: emit the exception note only when a sole available group forces repetition;
  use a separate truthful message if the cooldown leaves exactly one non-repeating group. Add
  tests for both branches and for the ordinary multi-group branch.

### [P1] G6-003 — History is only shallowly validated and same-day output is not byte-idempotent

- Location: `skills/omda-daily-discovery/scripts/daily_pick.py:492-559`, `:682-732`,
  `:787-849`
- Evidence:
  - `_validate_history()` checks only top-level record value types. A schema-shaped record with
    `selected: {}` passes validation; same-day replay then raises an uncaught `KeyError` instead
    of preserving a corrupt copy and failing closed with exit code 3.
  - A first run with `--lang zh` followed by same-day replay with `--lang en` rewrites the daily
    output to different bytes, contradicting the byte-identical replay contract.
  - If history already contains `2026-09-18` and the local clock reports `2026-09-17`, the code
    commits a new earlier day. D11 permits the clock seam to advance to today, not to backfill
    arbitrary earlier day keys.
- Impact: malformed history can crash outside the documented recovery path, same-day output can
  change after commitment, and clock rollback can mutate official history out of order.
- Required repair: deeply validate all nested history fields and cross-field invariants before
  use; lock the committed render language/payload so later CLI language changes cannot rewrite
  it; reject a day key earlier than the latest committed day. Add exact negative tests for all
  three probes.

### [P1] G6-004 — The audit content representation is not canonical

- Location: `skills/omda-daily-discovery/scripts/daily_pick.py:334-349`, `:817-885`
- Evidence:
  - `compute_source_content_digest()` hashes records in file order. Reversing two unchanged
    Album rows changes the per-source content digest, despite ADR-0003 D19 requiring stable
    record ordering for both canonical representations.
  - `source_ids` is persisted in CLI argument order rather than as the canonical selected set.
    Therefore equivalent `--source` permutations produce different history/render evidence even
    when selection is unchanged.
- Impact: an audit digest signals a content change when only presentation order changed, and
  equivalent source sets do not have canonical history evidence.
- Required repair: sort the complete source-content records by a documented stable tuple before
  hashing; store source IDs and corresponding display/digest evidence in canonical source-id
  order. Extend AC-19/AC-25 to compare both audit evidence and selection results.

### [P1] G6-005 — The packaged Codex Skill metadata and execution path are not installable as written

- Location: `skills/omda-daily-discovery/agents/openai.yaml:1-15`,
  `skills/omda-daily-discovery/SKILL.md:22-59`,
  `skills/omda-daily-discovery/README.md:68-121`
- Evidence:
  - Current Codex Skill metadata requires UI fields under `interface`, quoted string values and
    a `default_prompt` that explicitly mentions `$omda-daily-discovery`. The candidate instead
    places `name`, `display_name`, `description`, `default_prompt` and `version` at the top level;
    its prompt does not mention the `$skill-name` invocation.
  - Both instructions run `python3 scripts/daily_pick.py` while describing Profile/Sources as a
    separate user workspace. Once the Skill is installed under the Codex skills directory and
    the Agent is operating in the user's workspace, that relative script path does not exist.
  - AC-10 only checks for file presence/string fragments and cannot detect either defect. AC-12
    is disclosed rather than exercised.
- Impact: the primary “native Skill” path can fail before OMDA runs, even though the manual
  in-repository test passes.
- Required repair: use the supported `interface:` metadata shape and a `$omda-daily-discovery`
  default prompt; explicitly resolve the script/templates relative to the installed Skill root
  while keeping Profile/Sources/History in a separate user workspace. Add an installation
  simulation with separate Skill and workspace directories. Validate with the current Skill
  validator where available.

### [P1] G6-006 — AC-30 is failed, not merely waiting for unavailable Owner input

- Location: `skills/omda-daily-discovery/README.md:3-40`,
  `reviews/stage-06/PREFACE_CHECKLIST.md:1-28`
- Evidence:
  - Owner source text is available at the previously supplied attachment
    `<OWNER_PREFACE_SOURCE>`
    and in the project conversation; new Owner input is not required to begin correction.
  - The README changes the explicit Chinese full name from “开放音乐探索 Agent” to
    “每日音乐探索代理”.
  - It has three short Chinese product-rule bullets with no English counterparts, then an
    English-only Why section with no Chinese counterpart. It omits the Owner's three thematic
    bilingual sections, the English epigraph/source attribution and the complete Chinese Why.
- Impact: the friend-facing introduction is neither the Owner's requested text nor bilingual,
  and the candidate explicitly ships an unfinished draft in the distributable package.
- Required repair: use the Owner attachment as the source of truth, preserve “开放音乐探索
  Agent”, restore the complete title/epigraph/three bilingual thematic sections/Owner Why
  structure, then integrate the later Calvino and plural-aesthetics additions without replacing
  the Owner's first-person voice. Complete the sentence-level checklist and have the Owner review
  the resulting wording before claiming AC-30 PASS.

### [P2] G6-007 — Additional live Album tables are silently ignored

- Location: `skills/omda-daily-discovery/scripts/daily_pick.py:247-311`
- Evidence: `parse_album_table()` intentionally parses only the first matching table. A second
  unfenced Album table is silently omitted rather than parsed or rejected. The Executor reports
  this as low-risk technical debt, but the product targets non-technical contributors and
  otherwise promises fail-closed validation.
- Impact: a curator can believe Albums were added while OMDA silently never considers them.
- Required repair: either parse every live matching table under a deterministic documented rule,
  or fail closed with the second table's line number. Add a fixture proving no live Album table
  can be silently dropped.

## Independent verification

- Verified exact branch, parent, ancestry, merge-base, 19-file scope and clean starting tree.
- Inspected the complete production script, tests, templates, Skill entrypoint, metadata,
  README, evidence and state.
- Ran all 39 Skill tests independently on system Python 3.9.6: **39 passed**.
- Ran all 39 Skill tests independently on bundled Python 3.12.14: **39 passed**.
- `git diff --check` is clean and `PROJECT_STATE.json` parses.
- Reproduced locally, without network or external services: extra seed input, pre-cooldown pool
  hashing, missing/mislabelled unique-Genre note, row-order-dependent content digest, shallow
  history crash, same-day language rewrite and backward-day commit.
- Compared `agents/openai.yaml` with the locally installed Codex Skill metadata specification.
  The bundled `quick_validate.py` could not run because its local Python environments lack
  PyYAML; the schema defect above is directly visible and does not depend on that validator.
- No production implementation, merge, tag, push, package publication or user data was changed.

## Required repair scope

Remain on `exec/g6-skill-beta-adr` and keep candidate `88324ae3...` plus this Reviewer commit
immutable in history. Repair G6-001 through G6-007 with focused tests. Do not alter the accepted
3x3 Core, weaken/delete existing tests, merge, tag, push, publish, retain a distributable ZIP or
enter another Gate. Temporary archive validation remains allowed under ADR-0003 §10 C4.

Return one new complete candidate whose direct history includes this Reviewer checkpoint. Update
the G6 repair report, real test evidence and `PROJECT_STATE` to `G6 / READY_FOR_REVIEW`, then stop.

## Verdict

**CHANGES_REQUESTED**

Candidate `88324ae3a3a95d4372a6548da31d836a514ada3d` must not be merged or distributed.
Open blocking findings: G6-001 through G6-006. G6-007 is also required for this friend-facing
Beta because silently dropping user source data conflicts with its fail-closed contract.

---

## Re-review 1 — candidate `64b805e6518462ed6346aa7a3fd8a87cac277cdd`

### Identity and verification

- Direct parent: Reviewer checkpoint `3c39aae24af2ef721422aafd947f782d0506d67c`
- Original base and merge-base: `c15fbbe63fb7409483bf092fe7df926868ef5dda`
- Candidate scope: 10 files, limited to the G6 Skill, G6 plan/state and G6 evidence
- Worktree at review start: clean
- Independent suite: **54/54 passed** on Python 3.9.6 and **54/54 passed** on
  bundled Python 3.12.14; `git diff --check` passed

### Prior finding status

| Finding | Re-review result |
|---|---|
| G6-001 seed/final selection projection | **RESOLVED** — cooldown now precedes projection; seed inputs match ADR D11/C1 exactly; excluded-Genre mutation fixture passes. |
| G6-002 unique-Genre disclosure | **RESOLVED** — true waiver and applied-cooldown branches are distinct and covered end to end. |
| G6-003 history/language/clock | **PARTIAL** — the reported probes are repaired, but semantic date/time corruption remains open as G6-R1-003. |
| G6-004 canonical audit evidence | **PARTIAL** — content digest and source-set evidence are stable, but display/history still depend on row order for canonical-equivalent duplicate identities (G6-R1-001). |
| G6-005 Codex Skill installation | **RESOLVED** — `interface:` metadata is valid in shape, `$omda-daily-discovery` is present, and separate Skill/workspace simulation passes. |
| G6-006 bilingual Owner preface | **CONTENT RESTORED / OWNER CONFIRMATION PENDING** — the complete source structure is present; one wording mismatch remains noted below. |
| G6-007 second live table | **PARTIAL** — identical headers are rejected, but a second equivalent header using another supported language is parsed as Album data (G6-R1-002). |

### [P1] G6-R1-001 — Canonical-equivalent duplicate rows still make output depend on file order

- Location: `skills/omda-daily-discovery/scripts/daily_pick.py:380-398`, `:478-510`
- Evidence: the content digest sorts records canonically, but `merge_sources()` still iterates
  `source.records` in file order and chooses `occs[0]` as the displayed Artist/Album. Two rows
  `A Ref | Alpha` and `a ref | Alpha.` normalize to the same identity and have the same Genre.
  Reversing those rows preserves the content digest and selection-pool digest but changes the
  committed/displayed Artist and Album text.
- Impact: equivalent file permutations can produce different history and daily output, contrary
  to D19/D23 and the candidate's claim that full history is permutation invariant.
- Required repair: order records/occurrences by the documented canonical content tuple before
  selecting display facts and annotations. Add a permutation fixture containing two distinct raw
  spellings that normalize to one identity and require identical full history/output bytes.

### [P1] G6-R1-002 — A second live table with another supported header language becomes a fake Album

- Location: `skills/omda-daily-discovery/scripts/daily_pick.py:247-327`
- Evidence: while `phase == "table"`, the parser detects a second table only when
  `cells == header`. An English first header followed (after a blank line) by a Chinese header is
  not equal to the first header, so the Chinese header is accepted as a data row. Independent
  reproduction returned Albums `A/Alpha`, `艺人/专辑`, and `B/Beta` instead of failing closed.
- Impact: a header marker can become a recommendable fake Album and the second live table is not
  rejected, so G6-007 remains open.
- Required repair: before interpreting any in-table row as data, test whether it matches the
  required semantic header fields under any supported alias set. Treat every later matching
  header as a second live table regardless of language or exact spelling. Add English→Chinese and
  Chinese→English fixtures (including blank-only separation) and assert exact line-number errors.

### [P1] G6-R1-003 — “Deep” history validation accepts impossible dates and non-time timestamps

- Location: `skills/omda-daily-discovery/scripts/daily_pick.py:582-669`, `:964-973`
- Evidence: day keys are checked only by `\d{4}-\d{2}-\d{2}` and the ISO timestamp fields only
  for non-empty strings. A real committed record mutated to day `2026-99-99` with
  `local_iso`, `utc_iso`, and `selected_at` set to `not-a-time` passes `_validate_history()`.
  Runtime then misclassifies it as clock rollback (exit 2), creates no corrupt copy, and does not
  use the history-corruption exit 3 path.
- Impact: schema-shaped history corruption can bypass the documented preservation/recovery path
  and influence latest-day/cooldown logic.
- Required repair: semantically parse day keys and all ISO timestamps; require valid aware
  datetimes, `utc_iso` in UTC, `local_iso` calendar date equal to the day key, and offset evidence
  consistent with `local_iso`. Invalid values must preserve a corrupt copy and exit 3. Add focused
  cases for impossible day/month, malformed timestamps and offset/date mismatch.

### AC-30 wording status

The restored preface is materially faithful, but the added Calvino pair is not yet a strict
sentence-level counterpart of the Owner's words: Chinese says `最近读了` while English says
`after rereading`; the Owner said `读过`/reading, not “recently” or “rereading”. Remove those two
new qualifications (for example, `读过…之后` / `After reading…`) unless the Owner explicitly
chooses them. After that edit, the Owner must still confirm checklist rows 20–21 before AC-30 can
be marked PASS.

### Re-review 1 verdict

**CHANGES_REQUESTED**

The repair is close, and the multi-source/Skill architecture remains accepted. Candidate
`64b805e6518462ed6346aa7a3fd8a87cac277cdd` must not be merged or distributed. Repair only
G6-R1-001 through G6-R1-003 plus the two-word AC-30 correspondence correction, rerun the complete
matrix, return `G6 / READY_FOR_REVIEW`, and stop. Do not reopen resolved findings or alter the
accepted 3x3 Core.

---

## Re-review 2 — candidate `9ddab49a314b22fac8f686159ac45aeed44afb80`

### Identity and independent verification

- Direct parent: Reviewer checkpoint `ceeec1074966cfbe6865f05658607bae641fe5c0`
- Original base and merge-base: `c15fbbe63fb7409483bf092fe7df926868ef5dda`
- Candidate scope: 7 files and one focused commit; no accepted 3x3 Core file changed
- Worktree at review start: clean; `git diff --check` passed
- Independent suite: **64/64 passed** on Python 3.9.6 and **64/64 passed** on
  Python 3.12.14
- The prior English/Chinese second-table probes and malformed date/time probes now fail closed as
  required. The case/punctuation permutation fixture is also repaired.
- The bundled Skill `quick_validate.py` was attempted under both interpreters but its local
  environment lacks PyYAML; metadata shape was therefore checked directly against the installed
  Skill specification, as in the prior review.

### Re-review 1 finding status

| Finding | Re-review result |
|---|---|
| G6-R1-001 canonical-equivalent duplicate ordering | **PARTIAL** — case/punctuation variants are stable, but canonically equivalent Unicode spellings still tie in the canonical sort and retain input order (G6-R2-001). |
| G6-R1-002 cross-language second live table | **RESOLVED** — semantic header detection runs before data-row parsing and both language directions fail closed with exact line evidence. |
| G6-R1-003 semantic history validation | **RESOLVED** — real dates and aware timestamps are parsed; the required UTC/date/offset checks use the corrupt-history exit-3 path and preserve the original bytes. |
| AC-30 correspondence correction | **IMPLEMENTED / OWNER CONFIRMATION PENDING** — `读过…之后` and `After reading…` remove the unsupported qualifications. Checklist rows 20–21 still correctly await Owner confirmation. |

### [P1] G6-R2-001 — NFC-equivalent raw spellings still break permutation invariance

- Location: `skills/omda-daily-discovery/scripts/daily_pick.py:355-418`, `:478-519`
- Evidence: `_content_record_sort_key()` normalizes fields to NFC. Therefore two distinct raw
  spellings such as precomposed `Caf\u00e9` and decomposed `Cafe\u0301` have the same canonical
  sort key. Python's stable sort then preserves their file order; `canonical_order` and
  `occs[0]["artist"]` inherit that order. Reversing those two otherwise identical rows keeps the
  per-source content digest equal but changes the displayed Artist and merged/history payload.
- Independent reproduction on candidate `9ddab49...`: `digest_equal=True`, while the first
  merged Artist changed from `Caf\u00e9` to `Cafe\u0301` and `merged_equal=False`.
- Impact: D19 explicitly defines the source-content canonical representation as Unicode NFC and
  requires stable record order independent of file row order. Two canonically identical source
  representations can still produce different output bytes and history evidence.
- Required repair: normalize source metadata and all parsed record/display fields to NFC at the
  canonicalization boundary (or define an equivalent total canonical representation that cannot
  tie on different retained raw bytes). The value used for display, annotations, digest and
  history must come from that same canonical representation. Add a regression fixture using
  precomposed/decomposed Unicode rows in both orders and require equal content digest, merged
  payload, full history JSON and output bytes. Do not change identity normalization, seed inputs
  or the accepted selection algorithm.

### Re-review 2 verdict

**CHANGES_REQUESTED**

Candidate `9ddab49a314b22fac8f686159ac45aeed44afb80` must not be merged or distributed.
Repair only G6-R2-001, rerun the complete dual-version matrix, return `G6 / READY_FOR_REVIEW`,
and stop. The code repair is narrow. AC-30 remains a separate Owner confirmation step and must
not be self-approved by the Executor.
