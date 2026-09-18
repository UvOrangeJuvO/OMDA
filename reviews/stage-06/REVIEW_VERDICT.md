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
