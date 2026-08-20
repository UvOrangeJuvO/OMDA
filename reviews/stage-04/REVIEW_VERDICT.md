# Gate G4 Independent Review Verdict

## Reviewed object

- Reviewer: GPT-5.6 Sol in Codex
- Review date: 2026-08-21
- Gate: G4 — Agent & Delivery
- Exact base SHA: `68e3d453c7b803d2090cb1318f48e58eb18d6390`
- Exact candidate SHA: `10275ed04a66ed50631edb0d43a3505f18d2a5b7`
- Candidate branch observed: `exec/g4-agent-delivery`
- Executor report: `reviews/stage-04/EXECUTOR_REPORT.md`
- Executor test evidence: `reviews/stage-04/TEST_RESULTS.txt`

The exact candidate is a clean descendant of the exact accepted G3/main base, and the
merge-base is the supplied base. The worktree was clean at review start. The complete
base-to-candidate diff and G4 production/test files were inspected. There are no accepted
ADRs changing the G4 contracts.

The ordinary suite and lint are green, but independent negative probes found six open P1
failures. Most importantly, the production `RunEngine` never calls the new Markdown renderer
or validator: it delivers the raw LLM response and then commits official history. PushPlus
also retries an ambiguous request without provider-side idempotency, so one logical delivery
can produce two pushes. Therefore the candidate does not yet satisfy the G4 Gate.

## Findings

### [P1] G4-001 — The production run path bypasses the G4 renderer and fact validator

- Location: `src/omda/orchestrator/run.py:454-469`, `:484-558`;
  `src/omda/output/markdown.py:45-126`; `tests/integration/test_g4_pipeline.py:56-100`
- Evidence:
  - `_generate()` returns the LLM response as the final payload. `_validate_payload()` checks
    only non-emptiness and total length. `_deliver_and_commit()` sends that same string
    directly to the Delivery Port and commits official history after an `ok` receipt.
  - No production module imports or invokes `render_markdown()` or `validate_markdown()`.
    `test_g4_pipeline.py` manually assembles a second, test-only pipeline and therefore does
    not exercise `RunEngine`.
  - Independent reproduction used the real `RunEngine` with a selected real Album and an LLM
    response `IGNORE FACTS: recommend Fabricated Album by Fake Artist`. The run returned
    `COMPLETE`, the exact fabricated sentence was the delivered payload, and one official
    Album was committed.
- Impact: an injected, malformed or fabricated LLM answer is treated as a successfully
  validated recommendation. The user can receive content with no selected Genre/Album
  structure while official cooldown and permanent Album history still advance.
- Violated contract: SPEC §3.5 and §4; Master Plan §3.6; IMPLEMENTATION_PLAN T4.2
  “generated output MUST be validated before delivery” and “validation failure does not
  deliver”.
- Required acceptance test: run the actual application/`RunEngine` composition with an
  adversarial LLM response. It must either deliver a deterministic structured Markdown report
  whose facts come only from the selected plan, or fail validation. On failure, delivery calls
  and official Genre/Album history must both remain zero. A manually assembled test-only
  pipeline is not sufficient.

### [P1] G4-002 — PushPlus retries ambiguous sends and does not implement idempotent replay

- Location: `src/omda/adapters/delivery.py:132-177`, especially `:150-157`;
  `tests/unit/test_delivery_adapters.py:202-228`; `src/omda/ports/delivery.py:13-23`
- Evidence:
  - The outbound PushPlus body contains token/title/content/template but not the stable
    idempotency key. Every transport exception is retried, even though a timeout can occur
    after PushPlus accepted the first request.
  - Independent reproduction used a transport that recorded an external effect and then
    raised `TimeoutError` on the first call; the retry succeeded. One `deliver()` call made
    two outbound calls/two simulated effects and returned `status="ok"`.
  - On exhausted transport exceptions the adapter returns `status="failed"`, incorrectly
    treating an ambiguous outcome as a confirmed non-delivery. `RunEngine` then terminates the
    run as `FAILED` rather than preserving it for human-safe recovery.
  - The claimed replay test calls `deliver()` only once. Its second half merely checks a fake
    HistoryPort and executes `pass`; it never replays the adapter or tests concurrent/ambiguous
    delivery.
- Impact: the user can receive duplicate notifications. A response-loss window can also leave
  a delivered recommendation with no official history, permitting later recommendations to
  repeat its Albums.
- Violated contract: Delivery Port `deliver()` idempotency contract; SPEC §4; T4.3 blocking
  acceptance; R-001.
- Required acceptance test: simulate “provider accepted request, response was lost” and prove
  there is no automatic second external push. Ambiguous outcomes must remain distinguishable
  from confirmed rejection and enter durable `RECOVERING`/human review. Replay and concurrent
  use of the same key must not cause a second effect. If the accepted Port cannot represent an
  ambiguous outcome, stop and submit an ADR rather than labelling ambiguity `failed`.

### [P1] G4-003 — Dry-run is only an argument selector and pollutes official history when composed

- Location: `src/omda/cli.py:27-64`; `pyproject.toml:1-18`;
  `tests/unit/test_dry_run_gate.py:33-87`; `src/omda/orchestrator/run.py:536-569`
- Evidence:
  - `omda.cli` has no `main()`, application composition or console-script entry point. Running
    `python -m omda.cli` exits successfully without doing a dry-run or producing a report.
  - The only `build_delivery()` function exists inside the test file. Its deliver branch passes
    the `HttpTransport` Protocol class itself as a transport, so it is not a usable production
    factory.
  - The implied dry-run composition uses `MarkdownFileDelivery`. With the real `RunEngine`, an
    independent probe wrote the local Markdown file, returned `COMPLETE`, advanced the official
    pick index to 1 and added one permanent Album exclusion.
- Impact: the Owner cannot execute the promised safe observation mode, and wiring the supplied
  pieces in the obvious way consumes official cooldown/permanent-history state during a
  rehearsal. Seven dry-runs would not be history-neutral.
- Violated contract: IMPLEMENTATION_PLAN T4.5, especially “Owner can observe 7 dry-runs
  without history pollution”; handbook §14-8; candidate CLI docstring.
- Required acceptance test: expose one production callable/entry point for a full dry-run and
  execute it against persistent/in-memory history. It must create the intended local preview,
  make zero external calls, resolve no PushPlus token, and leave all official Genre/Album
  history unchanged across repeated dry-runs. `--deliver` must remain the only route that can
  enable external push and official commit.

### [P1] G4-004 — Recovery accepts unbound receipts without any post-delivery journal evidence

- Location: `src/omda/orchestrator/recovery.py:35`, `:48-81`
- Evidence:
  - `_AFTER_DELIVER_TRANSITIONS` is defined but never used. `resolve_recovery_action()` does
    not require a `DELIVERING`, `DELIVERED` or `RECOVERING` journal tail before returning
    `COMMIT_HISTORY`.
  - It looks up the expected key but validates only `receipt.status` and `receipt.run_id`; it
    never checks `receipt.idempotency_key` or `receipt.channel`, despite its own contract text.
  - Independent reproduction supplied no journal entries and a returned receipt with the
    correct run id but `idempotency_key="wrong:key"` and `channel="pushplus"` while the
    requested/default key was `probe:markdown`. The function returned `COMMIT_HISTORY`.
  - The mismatched-receipt test stores a receipt under a different lookup key, so the function
    merely receives `None`; it does not exercise a corrupt/mismatched returned receipt.
- Impact: stale or corrupt delivery evidence can authorize an official history commit for a
  run/channel that was never durably shown to reach delivery.
- Violated contract: SPEC §4; T4.4 requirement to recover only from bound durable evidence and
  require human review for missing/mismatched evidence.
- Required acceptance test: with no post-delivery journal tail, or with any run/key/channel/
  status mismatch, recovery must return `REQUIRE_HUMAN` and perform no commit/redelivery.
  Only an exact bound `ok` receipt plus an allowed durable journal state may authorize
  `COMMIT_HISTORY`. The production application must use one consistent recovery path rather
  than leaving a weaker parallel resolver unused.

### [P1] G4-005 — Markdown “fact validation” accepts fabricated artist/year and narrative claims

- Location: `src/omda/output/markdown.py:84-126`;
  `tests/unit/test_markdown_output.py:99-124`
- Evidence:
  - Album presence/allow-list checks compare only the title prefix. Artist, year, Genre-to-Album
    association, run id and complete bullet text are not checked against `ReportData`.
  - Independent reproduction rendered `Real Album — Real Artist (2020)`, changed the bullet to
    `Real Album — Fake Artist (1900)`, and added prose recommending a fabricated Album. The
    validator returned successfully.
  - The candidate's own `test_narrative_cannot_alter_selected_facts` intentionally accepts the
    narrative `recommend Album X instead`; it checks only that the phrase is not formatted as
    an Album bullet. The false recommendation remains visible in the delivered report.
- Impact: the validator's PASS does not mean that delivered claims are grounded in the fact
  packet. This defeats the principal control intended to make untrusted LLM output safe.
- Violated contract: SPEC §3.5; Master Plan §3.6; T4.2 structure/length/fact-reference
  validation and “fabricated facts are rejected”.
- Required acceptance test: mutate every selected fact independently (run id, Genre, Album
  title, artist, year and Genre association) and prove rejection. LLM-authored content must be
  constrained to a machine-validatable structure/reference scheme so mentions or
  recommendations outside the selected fact packet cannot pass merely because they are prose.

### [P1] G4-006 — The fact packet is not bounded across all externally controlled fields

- Location: `src/omda/adapters/llm.py:38-42`, `:93-143`;
  `src/omda/orchestrator/run.py:621-629`
- Evidence:
  - `MAX_FIELD_LENGTH` is applied only to Genre name, Album title and artist. `run_id`,
    `genre_id` and `album_id` have no length bound or aggregate serialized-size bound, and empty
    identifier/name strings are accepted.
  - Independent reproduction passed a one-million-character `run_id` with empty Genre/Album
    lists; `bounded_packet()` accepted and froze it. The same unbounded identifier slots are
    populated from run/source data in the real Orchestrator packet.
- Impact: untrusted/local input can create an unexpectedly large provider request, cost/latency
  spike or provider rejection despite the adapter claiming a bounded prompt boundary.
- Violated contract: T4.1 bounded fact packet; R-008 input containment.
- Required acceptance test: apply non-empty and length constraints to every string field,
  enforce expected Genre/Album cardinality for a real plan, and cap the final serialized packet
  size. Boundary and one-over-limit tests must fail before the transport is called.

## Acceptance matrix

| G4 criterion | Status | Evidence |
|---|---|---|
| T4.1 vendor isolation and prompt slot separation | **PARTIAL** | fixed system/user slots work; packet bounds fail in G4-006 |
| LLM cannot alter the selected Genre/Album plan | **PASS for selection** | deterministic Core is unchanged |
| LLM output is safe, structured and fact-validated before delivery | **FAIL** | G4-001 and G4-005 |
| T4.3 stable idempotent Markdown/PushPlus delivery | **FAIL** | ambiguous retry/replay gap in G4-002 |
| Delivery receipt and history ordering | **PARTIAL** | normal success ordering works; ambiguous delivery is misclassified |
| T4.4 delivered-but-not-committed recovery | **FAIL** | weaker resolver accepts unbound/no-journal evidence in G4-004 |
| T4.5 default executable dry-run with zero external calls/history pollution | **FAIL** | selector only; obvious composition commits history in G4-003 |
| Ordinary tests use only fakes/fixtures, no live LLM/PushPlus | **PASS** | test/source inspection and full suite |
| Secrets/cookies/profiles absent from candidate | **PASS** | tracked-file scan; token values appear only as test placeholders |
| G0-G3 accepted recommendation/data invariants unchanged | **PASS** | no Core/source-adapter behavior changes in the candidate |
| Open P0/P1 findings | **SIX P1** | G4-001 through G4-006 |

## Independent checks performed

- Verified full base/candidate SHAs, current branch, clean starting worktree, ancestry,
  merge-base, commit chain, state file, accepted Gate chain and absence of accepted ADRs.
- Inspected the complete 15-file base-to-candidate delta and all related G2 production paths,
  Port contracts and G4 tests; `git diff --check` passed.
- Ran the complete suite independently: **539 passed**, with one non-functional pytest-cache
  write warning caused by the review sandbox.
- Ran Ruff over the repository: **all checks passed**.
- Reproduced raw fabricated LLM delivery plus official history commit, dry-run history
  pollution, ambiguous double push, unbound/no-journal recovery acceptance, false Markdown
  fact validation and the unbounded fact packet using only local fakes/temp storage.
- Ran a tracked-text secret keyword scan; no credential value, cookie, browser profile, local
  database, live LLM call or live PushPlus request was used.
- No production code, merge, tag, push or external service was modified.

## Required repair scope

The Executor should stay on `exec/g4-agent-delivery`, read this verdict, reproduce every
finding and add focused repair commits. Allowed scope:

- wire one real application pipeline so `RunEngine`/application composition renders and
  validates deterministic Markdown before any Delivery call;
- harden Markdown validation and the bounded fact-packet contract;
- redesign ambiguous PushPlus outcome/retry handling and real same-key idempotency;
- make the production dry-run executable and history-neutral;
- bind the recovery resolver to exact journal/run/key/channel/status evidence, or remove the
  weaker duplicate path in favour of one tested production recovery path;
- add negative unit/integration/state-machine tests and update the G4 repair report/evidence.

Do not enter G5, merge the Gate, enable automatic push, weaken existing tests, alter
Recommendation Core semantics or claim PushPlus/server-side idempotency without executable
evidence. If safely representing ambiguous external delivery requires changing an accepted
Port/domain contract, stop at `BLOCKED_ARCHITECTURE` and submit an ADR.

## Verdict

**CHANGES_REQUESTED**

Open blocking findings: G4-001 through G4-006 (all P1). Candidate
`10275ed04a66ed50631edb0d43a3505f18d2a5b7` must not be merged,
`gate-g4-accepted` must not be created, and G5 must not begin.
