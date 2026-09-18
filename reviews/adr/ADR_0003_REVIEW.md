# ADR-0003 Independent Review

## Reviewed object

- Reviewer: GPT-5.6 Sol in Codex
- Review date: 2026-09-18
- ADR: `docs/adr/0003-agent-skill-beta-and-personal-markdown-mode.md`
- Base: `c15fbbe63fb7409483bf092fe7df926868ef5dda`
- Proposal candidate: `d52d4b6f42557ae3fad72729eeed3b4147275a50`
- Branch observed: `exec/g6-skill-beta-adr`
- Repository state observed: `G6 / BLOCKED_ARCHITECTURE / ADR_PENDING`
- ADR status observed: `Proposed`
- Production-code/test changes: none

Git verification passed: the candidate is a single documentation-only descendant of the
declared Base, its merge-base is exactly the declared Base, the worktree was clean at review
start, and `git diff --check` passed for the full review range.

## Summary

The product direction is sound and should remain: pause the Web Beta; distribute a local,
portable Agent Skill; keep the accepted 3×3 runtime untouched; mark the one-Album personal-list
experience as a separate companion mode; let deterministic code select while the Agent only
organizes input and explains output; keep local use separate from public contribution.

ADR-0003 is not yet safe to accept. The largest issue is that it puts the user's `Heard` and
`Skip` state inside the shareable collection while declaring that the personal profile is never
read by the selector. A friend receiving another person's list would have to edit the source
list to add personal state, so reusable source data, personal data and provenance become mixed.
The deterministic contract is also incomplete: the canonical collection digest is undefined,
`random.Random` is treated as a cross-version protocol, and a public `--date` option would let an
Agent consume arbitrary future/past day keys. The proposed Skill source layout is not the normal
discoverable Skill directory, the standalone ZIP omits the full Apache license, and the active
table templates contain example/blank rows that conflict with the stated fail-closed parser.

The bilingual introduction also does not preserve the Owner's requested full structure or
voice. It replaces the supplied personal reflection with a direct Calvino quotation and a new
general claim about most recommendation systems. This needs revision, not more copywriting.

ADR-0003 must remain `Proposed`. No Skill implementation is authorized yet.

## Findings requiring revision

### ADR3-001 — Shareable collection data and personal listening state are assigned to the wrong files

- Location: ADR D5/D6/D9/D10; plan C.1-C.4, T6.2/T6.3, V-4/V-5.
- `OMDA_COLLECTION.md` is described as a list obtained from a friend, critic, community or
  curator. It should be reusable by multiple people without each recipient modifying the
  curator's source file.
- The proposal instead puts `Heard` and `Skip` in that collection, while `OMDA_PROFILE.md`
  contains personal boundaries and listening history but is deliberately ignored by the
  deterministic script. This creates three contradictions:
  1. personal state is mixed into shareable source data;
  2. the profile promises fields such as “types I do not want recommended” that cannot affect
     eligibility;
  3. the claim “profile input would violate equal opportunity” is too broad, because the same
     proposal already allows explicit Album-level `Skip` exclusions.
- Required revision:
  1. keep `OMDA_COLLECTION.md` as reusable source data (Artist, Album, optional Year/Genre/
     source Rating/source Note and source attribution); do not place recipient-specific
     `Heard`/`Skip` state in it;
  2. add a small machine-readable Album-status table to `OMDA_PROFILE.md` for explicit personal
     `heard`/`skip` decisions, keyed by Artist + Album under the same normalization contract;
  3. let the script read only that structured status table for deterministic eligibility;
     free-form tastes, cultural preferences and prose remain explanation-only and never become
     weights, rankings or implicit filters;
  4. either remove misleading free-text “boundaries” that the selector will ignore, or state
     directly beside them that only the structured Album-status table excludes an item;
  5. update merge/conflict rules and tests so a curator's collection can be shared unchanged
     among users with different profiles and histories.

This preserves Genre equal opportunity among the explicitly eligible collection after the
user's own Album-level exclusions; it does not create a popularity or AI quality filter.

### ADR3-002 — The cross-machine deterministic-selection contract is not fully specified

- Location: ADR D8/D10/D11/D19; plan T6.2 items 4-5; AC-2/AC-3/AC-5/AC-14.
- `collection_digest` has no canonical definition. The proposal does not say whether it hashes
  raw Markdown bytes, parsed rows, file paths, CLI order or merged records; nor does it specify
  stable encoding, record ordering, field inclusion or domain separators.
- “first conflicting value wins” makes results depend on `--collection` argument order while
  the ADR simultaneously claims cross-machine reproducibility. Selection-relevant conflicts
  such as two Genres for the same identity can change the candidate grouping.
- `random.Random(seed)` is an implementation detail, not an adequate versioned interchange
  protocol for a strong Python 3.9+ cross-version/cross-harness guarantee. The proposal also
  omits an algorithm version from the seed and history.
- Required revision:
  1. define a canonical parsed-record representation (Unicode normalization, UTF-8, exact
     fields, stable key order and stable record order) and compute the collection digest from
     that representation, never from absolute paths;
  2. fail closed on duplicate identities with conflicting selection-relevant facts (especially
     Genre), rather than resolving them by incidental file order; display-only conflicts may be
     retained as explicitly ordered source annotations if their canonical order is defined;
  3. add `algorithm_version`, input-schema version and canonical digest to every committed
     history row;
  4. define a versioned uniform-index procedure using domain-separated SHA-256 bytes and
     unbiased rejection/unranking, or narrow the portability guarantee to a precisely pinned
     algorithm/runtime. Do not rely on an unversioned `random.Random` call sequence as the
     portable protocol;
  5. add permutation tests proving that row order and collection-file order either intentionally
     do not change a result, or are explicitly part of the documented input contract.

### ADR3-003 — Public date override and two-file commit semantics can break the “one per day” promise

- Location: ADR D11/D12; plan T6.2 item 1; AC-2/AC-3/AC-16.
- The proposed distributed CLI exposes `--date` while calling it “test injection.” An Agent or
  user can invoke multiple past/future dates, consume candidates, bypass the daily experience
  and permanently contaminate history. D14's “no specified result” rule does not prevent this
  deterministic reroll channel.
- The ADR separately writes history and output but does not identify the commit point or the
  expected state when one succeeds and the other fails.
- Required revision:
  1. do not expose an unrestricted date override on the normal committing CLI. Inject a clock
     through an importable function/test seam, or make any diagnostic date override preview-only
     and incapable of writing history;
  2. define the local-day derivation and store its timezone/offset evidence with the day key;
  3. make the atomic history replacement the official commit point, then render/re-render the
     output from committed history; an output failure after commit must be recoverable without a
     new selection, and a history failure must never be reported as a successful recommendation;
  4. keep volatile timestamps out of the rendered same-day payload or store/reuse the committed
     timestamp so AC-3's byte-identical claim is actually testable;
  5. extend crash tests across both history and output boundaries, not only interrupted JSON
     replacement.

### ADR3-004 — The proposed source/ZIP layout is not a complete installable Skill package

- Location: ADR D16-D19 and §9-6; plan T6.1/T6.4/T6.9, V-10/V-12.
- `skill/` versus `skill-beta/` is the wrong decision axis. A discoverable Codex Skill should
  have a stable, valid skill name and live as its own folder, while the ZIP should preserve that
  same folder as its root.
- D18 includes `LICENSES.md` but not the actual Apache-2.0 `LICENSE` text. A standalone archive
  must carry the license, not only a summary/third-party notice.
- Required revision:
  1. use repository source path `skills/omda-daily-discovery/` and ZIP root
     `omda-daily-discovery/`;
  2. set SKILL frontmatter name to `omda-daily-discovery` and provide a discriminating
     description; add `agents/openai.yaml` with consistent display metadata/default prompt for
     Codex while keeping the manual CLI fallback vendor-neutral;
  3. include the complete `LICENSE` plus `LICENSES.md`, and define the Skill's version separately
     from the accepted OMDA core release target;
  4. validate the source Skill structure before packaging and validate the extracted archive,
     not only a hand-written manifest;
  5. keep tests/review evidence outside the distributable root or explicitly exclude them from
     the ZIP whitelist.

### ADR3-005 — The templates can recommend placeholder data or fail before first use

- Location: plan C.3/C.4 and T6.2 row validation.
- Both collection templates contain an active example Album row and a fully blank table row.
  The example can be selected if a friend forgets to delete it. The blank row conflicts with
  “missing Artist/Album fails closed,” so an untouched template can fail immediately.
- Required revision:
  1. keep examples outside the active input table (for example, in a fenced example block or
     explanatory prose) and ship an empty real table;
  2. explicitly ignore rows whose cells are all empty, but continue to fail closed on any
     partially populated row missing Artist or Album;
  3. add tests proving a fresh template validates without creating a fake candidate, and that
     placeholder/example markers can never become recommendations;
  4. add curator/source/sharing-permission fields outside the Album table. They are provenance
     and private-sharing context, not an automatic public-data license.

### ADR3-006 — The bilingual release front matter is incomplete and no longer reflects the Owner's voice

- Location: plan T6.7 and C.7/C.8.
- The required front matter was the complete bilingual introduction: OMDA title/full name,
  “乐者，天地之和也”, the three numbered sections, and the Owner's “Why I wanted to build
  OMDA” at the end. The plan delivers only a replacement “Why” section.
- The new text directly quotes Calvino and adds the broad assertion that most recommendation
  systems narrow discovery. The Owner asked for a lightly smoothed version of their own words:
  reading *Why Read the Classics?* led them to feel that a work that truly belongs to you may be
  encountered by chance, and OMDA can create more such chances. They also explicitly wanted the
  freedom to use lists from trusted, unfamiliar, randomly encountered, or even disagreed-with
  people, because taste is plural and shaped by culture, experience and preference.
- Required revision:
  1. restore the full requested front-matter structure and keep it separate from the short
     technical Skill comparison/limitations section;
  2. paraphrase the Calvino reflection in the Owner's first-person voice instead of inserting a
     direct quotation or a literary claim the Owner did not write;
  3. include trusted/unfamiliar/random/disagreed-with sources and the Owner's plural-aesthetics
     reasoning without turning it into a universal declaration that music has no value
     distinctions;
  4. make the English a sentence-level semantic counterpart of the revised Chinese, including
     uncertainty and modest scope; do not independently embellish either language;
  5. add an explicit bilingual review checklist rather than treating presence of two sections as
     sufficient evidence.

## Accepted direction and clarifications

The revision should retain these parts:

1. Web work is paused; Skill-first is the correct first friend-test interface.
2. The one-Album experience is a distinct companion mode and does not modify or masquerade as
   the accepted 3×3 core.
3. Formal 3×3 constants, 30-pick cooldown, source trust gates, SQLite history and tests remain
   untouched.
4. The companion mode may use “no immediately repeated Genre, unless only one admissible Genre
   remains,” provided the documentation calls this a separate Beta rule and defines equal
   opportunity only among the currently admissible groups. Do not claim unconditional or
   long-run equality after groups deplete.
5. Rating and source Note remain display-only. Free-form profile prose remains explanation-only.
6. Committed Album picks are permanently excluded within Skill history; exhaustion fails
   explicitly with no AI fallback.
7. Local use does not authorize upload, publication or community contribution; harness privacy
   limitations remain disclosed.
8. Standard-library-only, zero-network, manual CLI fallback and explicit Agent authority limits
   remain binding.
9. The Executor-role direction is accepted in principle: governance should bind authority to the
   WorkBuddy Executor role and record the actual model separately. The revision must specify the
   backward-compatible PROJECT_STATE field semantics, then update AGENTS/operations text only
   after ADR acceptance; changing models never changes Gate permissions.

## Required revised acceptance additions

In addition to the corrected proposal matrix:

1. One unchanged collection must work with two different profiles/histories and produce no
   writes to the collection.
2. Free-form profile preference changes must not change the pick; structured Album-status
   changes must change only eligibility as documented.
3. Canonical digest and selection-vector fixtures must produce the same result on supported
   Python versions/platforms; row/file permutations follow the documented rule.
4. The production committing path has no usable arbitrary-date override.
5. Crashes before/after history commit and before/after output replacement preserve the chosen
   state and never create two same-day picks.
6. A pristine template contains zero candidate Albums and cannot recommend sample text.
7. The extracted ZIP validates as a Skill, contains the complete license, and contains no test,
   history, user, repository or machine-path data.
8. The full Chinese and English introduction passes a sentence-level intent correspondence
   review against the Owner-provided draft.
9. Zero-network validation should use a narrow import allowlist (and reject process/browser
   escape modules such as `subprocess` and `webbrowser`), not only a partial network-module
   denylist.

## Scope and governance

- `G6 / BLOCKED_ARCHITECTURE / ADR_PENDING` remains correct.
- ADR-0003 remains `Proposed`; the Executor must not write `Accepted`.
- Revise only ADR-0003, G6 plan, state metadata if needed, and the Executor handoff/report.
- Do not create the Skill directory, script, templates, tests or ZIP before re-review acceptance.
- Do not modify `src/omda/`, existing tests/data, accepted ADRs or G0-G5 history.
- Do not merge, tag, push or publish.

## Decision

**REVISE**

The Skill-first companion-mode direction is accepted in principle, including a separate
one-Album daily experience. Revise the personal/source data boundary, deterministic protocol,
date/commit semantics, installable Skill package, first-use templates and bilingual front
matter. Return one new documentation-only candidate whose direct parent is this Reviewer commit;
do not begin G6 implementation before ADR-0003 is accepted.

---

# Re-review 1 — ADR-0003 v2

- Original base: `c15fbbe63fb7409483bf092fe7df926868ef5dda`
- Revised candidate: `8d7427c7ee6f54f7331f193533a5304afb5b8216`
- Direct parent: `8aecaf7c77dc233406d4284a241249fccd19a4d8` (the REVISE commit above)
- Scope: documentation/governance only; worktree clean at review start;
  `git diff --check` passed.

## Closure of prior findings

| Finding | Re-review result |
|---|---|
| ADR3-001 | Closed. Shareable Source files, private Profile state and runtime history are physically and semantically separated; Sources are read-only. |
| ADR3-002 | Closed with binding constraint C1. Multi-source deduplication, Genre-conflict fail-closed behavior, versioned uniform-index sampling and stable representations are defined. Audit content and selection projections must remain separate. |
| ADR3-003 | Closed. The public date override is removed; atomic history replacement is the commit point; same-day source/result locking and crash semantics are testable. |
| ADR3-004 | Closed. The installable Skill layout, independent version, complete license, archive root and extracted-package validation are defined. |
| ADR3-005 | Closed. Active tables ship empty; examples remain outside them; blank versus partially populated rows have distinct validation behavior. |
| ADR3-006 | Architecturally closed with binding constraint C3. The complete bilingual structure and sentence-level Owner review are explicit acceptance requirements; the current prose remains a draft. |

## Multi-source Owner decision

Accepted. One curator or community may maintain one Source Markdown; a user may select one or
more Sources without creating a global collection. The runtime merges them in memory, deduplicates
Albums without probability gain, preserves per-source opinions, and never writes personal state
back to a Source. Future Web/desktop interfaces must reuse this protocol.

## Binding acceptance constraints

1. Per-source content digests are audit evidence only. The selection seed may depend only on the
   admissible selection-pool digest (normalized identity plus resolved Genre after eligibility and
   cooldown). Display/audit-only changes must not change that digest or the pick.
2. Source metadata uses the restricted OMDA flat-frontmatter grammar, not general YAML. The
   standard-library parser rejects nesting, sequences, tags, anchors, aliases, duplicate keys and
   unknown keys.
3. Plan C.7/C.8 is a structural draft, not approved final copy. AC-30 must compare the complete
   three-part introduction and first-person voice against the Owner's text, with sentence-level
   Chinese/English intent correspondence.
4. This decision authorizes G6 implementation only. T6.9 may build, extract, validate and then
   discard an archive in an isolated temporary directory as a test; no distributable artifact may
   be retained. It does not accept the G6 Gate or authorize merge, tag, push, packaging for
   distribution, publication or release.

## Decision

**ACCEPT**

ADR-0003 v2 is accepted subject to the constraints above. `PROJECT_STATE` may move to
`G6 / READY / ADR_ACCEPTED`. The WorkBuddy Executor may implement the approved G6 plan and must
stop at `READY_FOR_REVIEW`; only the independent Reviewer may accept G6.
