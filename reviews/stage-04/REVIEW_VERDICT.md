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

---

## Re-review 1 — candidate `13a659d741e70df5e7b3faa561ffc822dd4efb5c`

### Re-review identity and checks

- Original G4 base: `68e3d453c7b803d2090cb1318f48e58eb18d6390`
- Original G4 candidate: `10275ed04a66ed50631edb0d43a3505f18d2a5b7`
- Original Reviewer commit: `754a140562dcb36dacf77b56d1d6505996a0c490`
- Repair candidate: `13a659d741e70df5e7b3faa561ffc822dd4efb5c`
- Candidate branch observed: `exec/g4-agent-delivery`
- Worktree at review start: clean
- Merge-base with the supplied base: exact supplied base
- Repair commits inspected: `f5f02d2`, `66c7ee4`, `460a518`, `aedff3f`,
  `958a32b`, `343d3ed`; review-package commit `13a659d`
- Independent full suite: **566 passed**
- Ruff: **passed**
- `git diff --check`: **passed**

The repair materially wires the Markdown renderer/validator into the real `RunEngine`, makes
the local dry-run history-neutral, and binds the recovery helper to journal/run/key/channel
evidence. Those are substantive closures. However, two original P1 controls remain open and
the new executable composition exposes a third P1 completeness gap. The ordinary suite does
not cover these counterexamples.

### Original finding status

| Finding | Re-review status | Evidence |
|---|---|---|
| G4-001 production path bypass | **CLOSED** | `RunEngine` now renders and validates structured Markdown before Delivery; raw LLM output is no longer the whole payload. |
| G4-002 ambiguous/idempotent PushPlus | **PARTIAL / OPEN P1** | timeout is no longer retried, but direct same-key replay still sends twice and the new status violates the accepted Port/Schema. |
| G4-003 executable, history-neutral dry-run | **CLOSED for history neutrality; P2 limitations remain** | the real callable uses isolated history and writes a preview; CLI is CWD-dependent and reports the wrong default filename. |
| G4-004 bound recovery evidence | **CLOSED** | allowed journal tail plus exact run/key/channel/`ok` receipt is now required. |
| G4-005 complete fact validation | **PARTIAL / OPEN P1** | deterministic bullets are fully checked, but unconstrained fabricated narrative still passes a small keyword/format blacklist. |
| G4-006 bounded fact packet | **PARTIAL / P2** | all named fields have character bounds, but the declared byte cap is not measured in bytes and expected cardinality is not enforced. |

### [P1] G4-002 remains open — replay is not idempotent and `ambiguous` breaks the accepted receipt contract

- Location: `src/omda/adapters/delivery.py:132-188`;
  `src/omda/ports/delivery.py:13-23`; `src/omda/ports/domain.py:117-130`;
  `data/schemas/delivery_receipt.schema.json:5-10`;
  `tests/unit/test_delivery_adapters.py:202-228`
- Positive closure: a transport exception now stops after one call and is no longer blindly
  retried as a confirmed failure. The exact “accepted then response lost” two-call
  counterexample from the first review is closed.
- Remaining evidence:
  - `PushPlusDelivery` is still stateless. Calling `deliver()` twice with the same stable key
    makes two external calls and returns two `ok` receipts. Independent reproduction produced
    `external_calls=2` for two invocations of key `same:pushplus`.
  - The existing test named `test_same_idempotency_key_does_not_cause_second_push` still calls
    the adapter only once. Its replay branch checks a fake history and executes `pass`; it does
    not test the Delivery Port's direct replay contract, process restart or concurrency.
  - The repair returns `DeliveryReceipt(status="ambiguous")`, but the accepted Delivery Port,
    domain comment and versioned receipt schema permit only `ok` or `failed`. Independent
    schema validation rejected the adapter's receipt with `value 'ambiguous' not in enum
    ['ok', 'failed']`.
  - The original verdict explicitly required an ADR if the accepted Port could not represent
    ambiguity. No ADR was submitted; the adapter silently extended an accepted cross-layer
    contract instead.
  - Any non-200 response is assumed to prove non-delivery and is retried. The current transport
    shape supplies no evidence that every provider error response means the push was not
    queued; an internal/provider error can remain ambiguous.
- Impact: same-run replay/concurrency can still duplicate a user notification, and an adapter
  receipt cannot pass the project's own schema/Port contract. Recovery semantics now depend on
  an undocumented fourth state.
- Required acceptance:
  - stop and submit an ADR that defines the durable delivery-attempt/ambiguity model and any
    versioned Port/Schema migration, unless the repair can stay inside the existing contract;
  - prove direct replay, restart replay and concurrent attempts for the same key cannot produce
    a second external effect within the explicitly documented guarantee;
  - distinguish only demonstrably definitive provider rejection from ambiguous outcome; do
    not infer non-delivery from an arbitrary non-success response;
  - replace the vacuous replay test with an executable counter that would fail on the current
    two-call reproduction.

### [P1] G4-005 remains open — natural-language fabrication bypasses the blacklist

- Location: `src/omda/output/markdown.py:200-222`;
  `tests/unit/test_markdown_output.py:114-141`;
  `tests/integration/test_run_engine_g4.py:68-107`
- Positive closure: run id, Genre headings and complete Album bullet facts (title, artist, year
  and Genre association) are now checked against `ReportData`; deterministic structure
  mutation is rejected.
- Remaining evidence:
  - Narrative safety is implemented as a short English directive-verb regex plus one em-dash
    pattern. It is not a machine-validatable fact-reference scheme.
  - Independent production reproduction used the real `RunEngine` with narrative
    `My favorite is Fabricated Album by Fake Artist.`. It contains no blacklisted verb or
    em-dash, so the run returned `COMPLETE`, delivered the fabricated Album claim and committed
    official history. Equivalent Chinese prose such as `我最喜欢虚构专辑` also bypasses the
    English-only filter.
  - The repaired integration test uses the old exact phrase containing `IGNORE` and
    `recommend`, so it only proves that the blacklist catches its own keywords. It allows
    either `COMPLETE` or `FAILED` and does not assert that arbitrary off-packet mentions are
    absent from the complete delivered payload.
  - The test helper returns a different new `FakeDelivery` when no delivery is supplied, so
    its zero-delivery assertions do not observe the adapter attached to the engine.
- Impact: untrusted LLM prose can still add or endorse an Album/Genre outside the deterministic
  plan while the output is labelled validated and official history advances. This is the same
  product-boundary failure as the original finding, with only one phrasing blocked.
- Required acceptance: replace semantic keyword guessing with an output shape whose references
  are mechanically bound to selected IDs/facts (or omit unconstrained LLM prose from the
  deliverable). Add adversarial multilingual/paraphrase tests that inspect the exact payload
  delivered by the actual engine and prove off-packet Album/Genre references cannot pass.

### [P1] G4-007 — the executable application has no real Agent/PushPlus delivery composition

- Location: `src/omda/cli.py:122-176`; `src/omda/adapters/llm.py:48-91`;
  `src/omda/adapters/delivery.py:40-45`; `governance/IMPLEMENTATION_PLAN.md:351-408`,
  `:410-430`
- Evidence:
  - `python -m omda.cli --deliver` always exits with “production PushPlus wiring not composed”.
    Thus the explicit approval flag cannot enable delivery; it is a dead end.
  - The only executable dry-run uses `_LocalEchoTransport` and generated sample Albums. There
    is no concrete provider transport for the LLM or PushPlus in production code; both exposed
    transport types are Protocols that require a caller to invent the missing runtime layer.
  - The Executor report defers real vendor/runtime composition to G5. The approved G5 plan is a
    release audit: its production scopes are documentation/dependency locking, E2E tests,
    scans, backup/contribution docs and observation. It does not contain a task authorizing the
    missing Agent/Delivery implementation.
- Impact: accepting G4 would enter the release-audit Gate with no executable way to perform the
  feature G4 is meant to establish. The application can only generate a local sample preview;
  it cannot run the real Agent or send an explicitly approved PushPlus recommendation.
- Violated contract: G4 milestone “Agent & Delivery”, T4.1 Provider Adapter, T4.3 PushPlus
  Delivery, and T4.5 explicit manual-approval path.
- Required acceptance: provide a production composition boundary with replaceable concrete
  transports/configuration and an executable `--deliver` route that remains off by default.
  Use fake transports in ordinary tests, but test the real composition shape, token boundary,
  controlled failures and official-history ordering. Do not silently move production feature
  implementation into the G5 audit; if the Gate ownership must change, use an ADR/plan update.

### [P2] G4-006 remains partial — “byte” limit and plan cardinality claims are not implemented

- Location: `src/omda/adapters/llm.py:98-166`;
  `tests/unit/test_llm_adapter.py:201-225`
- Evidence:
  - `MAX_PACKET_BYTES` is checked with `len(json_string)`, not
    `len(json_string.encode("utf-8"))`. Independent reproduction passed a packet whose UTF-8
    encoding was 95,209 bytes under the declared 48,000-byte cap.
  - `EXPECTED_GENRES` and `EXPECTED_ALBUMS` are unused. Empty Genre/Album lists are still
    accepted. The test named `test_bounded_packet_enforces_real_plan_cardinality` checks only
    `MAX_GENRES + 1`; it does not enforce the documented 3/9 cardinality or reject zero.
- Impact: provider cost/request size can exceed the declared bound and malformed empty plan
  packets reach the transport. Per-field/count caps mean the packet is no longer truly
  unbounded, so this residual is P2 rather than the original P1.
- Required acceptance: measure the serialized UTF-8 byte length, define cardinality relative
  to validated plan/config semantics, and make test names/repair claims match executable
  behavior.

### [P2] G4-003 residual CLI defects

- Location: `src/omda/cli.py:122-154`; `src/omda/adapters/delivery.py:66-75`
- Evidence:
  - The CLI loads `data/genres/rym-sample` relative to the current working directory. The same
    module command that succeeds at the repository root fails from `/tmp` with “missing
    source.yaml”, so it is not yet an installed-location-independent entry point.
  - The generated run id contains a decimal point. `MarkdownFileDelivery` removes that point
    from the actual filename, while `main()` prints the unsanitized filename. Independent run
    printed `dry-...040917.094119.md` but created `dry-...040917094119.md`.
  - `main()` returns exit code 0 regardless of the `RunOutcome` state.
- Impact: the Owner can be told to open a file that does not exist and automation cannot trust
  CLI success. Clean-environment portability is also currently absent, though G5/T5.1 will
  audit installation.
- Required acceptance: derive/report the actual receipt target, return nonzero for non-complete
  runs, and resolve packaged data independently of the caller's working directory (or require
  an explicit source path).

### Re-review acceptance matrix

| G4 criterion | Status | Re-review evidence |
|---|---|---|
| Production render/validate before Delivery | **PASS** | G4-001 closed |
| Structured run/Genre/Album facts match selected plan | **PASS** | full deterministic bullet checks |
| Untrusted LLM narrative cannot add off-packet recommendations | **FAIL** | G4-005 paraphrase/multilingual bypass |
| Ambiguous send is not automatically retried | **PASS for transport exception** | exact lost-response probe closed |
| Same-key delivery is idempotent and receipt contract is versioned | **FAIL** | G4-002 direct replay and invalid status |
| Delivered-but-not-committed recovery uses bound durable evidence | **PASS** | G4-004 closed |
| Executable history-neutral dry-run | **PASS with P2 usability limits** | seven isolated runs do not mutate official history |
| Executable explicitly approved real Agent/PushPlus route | **FAIL** | G4-007 |
| Bounded fact packet | **PARTIAL** | per-field/count bounds pass; byte/cardinality residual G4-006 |
| Full regression suite/lint/diff check | **PASS** | 566 passed; Ruff and diff check clean |
| Open blocking findings | **THREE P1** | G4-002, G4-005 and G4-007 |

### Re-review verdict

**CHANGES_REQUESTED**

Candidate `13a659d741e70df5e7b3faa561ffc822dd4efb5c` must not be merged or marked
`ACCEPTED`. G5 must not begin. The Executor should first resolve G4-002 and its accepted
Port/Schema decision (ADR if required), replace the narrative blacklist with a mechanically
grounded output contract, and provide the missing production Agent/PushPlus composition.

---

## Re-review 3 — ADR-0001 implementation candidate

### Reviewed range and repository state

- Gate: **G4 — Agent & Delivery**
- Base: `68e3d453c7b803d2090cb1318f48e58eb18d6390`
- Candidate: `1a197d9ceb95acd4e8214a28cd52c8172a4a02a0`
- Branch at review start: `exec/g4-agent-delivery`
- HEAD at review start: exact candidate
- Merge-base: exact supplied base
- Worktree at review start: clean
- Accepted architecture in the reviewed chain: ADR-0001 revision v2, accepted by
  `1349a0fd53116335d372c89684d83f1d556b63ac`; its section 15 constraints are binding.
- Candidate state/report: G4 / `READY_FOR_REVIEW`; `candidate_commit=null` follows the
  repository's documented anti-self-reference convention.

The complete 38-file base-to-candidate delta, the prior findings, the Accepted ADR, the
Executor/repair reports, the ten claimed ADR acceptance tests, production composition,
storage implementation and recovery path were inspected. The full ordinary suite is green,
but independent counterexamples show that several binding assertions are not actually tested.

### Prior finding status

| Finding | Re-review 3 status | Evidence |
|---|---|---|
| G4-001 production render/validate path | **CLOSED** | Real `RunEngine` renders and validates deterministic Markdown before Delivery. |
| G4-002 delivery ambiguity/idempotency | **OPEN P1** | ADR classification and persistence-binding constraints are not fully implemented; see G4-002A/B. |
| G4-003 dry-run and CLI usability | **CLOSED except G4-007 deliver route** | Dry-run is isolated, CWD-independent and returns outcome-sensitive status. |
| G4-004 bound recovery | **REOPENED P1** | Human-confirmed delivery without a receipt cannot complete in the real `RunEngine`; see G4-004R. |
| G4-005 unconstrained LLM prose | **CLOSED for delivery safety** | No LLM free-text slot exists in the delivered Markdown. |
| G4-006 packet byte/cardinality bounds | **CLOSED** | UTF-8 bytes and actual plan cardinality are enforced. |
| G4-007 executable Agent/PushPlus route | **OPEN P1** | `--deliver` still deterministically exits before composition. |

### [P1] G4-002A — production classifies every HTTP 4xx as definitive despite the Accepted ADR

- Location: `src/omda/production.py:81-117`;
  `tests/unit/test_adr_acceptance.py:498-543`.
- Reproduction: inject an HTTP 418 response into the concrete
  `PushPlusHttpTransport`. It raises `ProviderRejection`, not `AmbiguousFailure`:

  ```text
  UNKNOWN_418_CLASS= ProviderRejection
  ```

- The test labelled `unknown 4xx (undocumented) -> ambiguous` has the opposite executable
  assertion: it supplies `ProviderRejection("499", ...)` and expects `failed`. It therefore
  makes the binding acceptance matrix green while proving the forbidden behavior.
- Accepted ADR-0001 §9 and §15-3 require exact documented no-side-effect categories; unknown
  4xx must be ambiguous/no-retry. The current concrete transport has no allow-list of exact
  PushPlus categories and turns the entire 400-499 range into confirmed failure.
- Current official PushPlus message documentation describes business `code == 200` as the
  server having received the asynchronous request; it does not document a blanket HTTP-4xx
  guarantee that no message was queued:
  <https://www.pushplus.plus/doc/guide/api.html>.
- Impact: uncertain provider outcomes become terminal `CONFIRMED_FAILED`. A later human
  generation retry can duplicate a notification that the system incorrectly declared absent,
  and the audit trail overstates its evidence.
- Required acceptance:
  - unknown 4xx, 5xx, malformed response and undocumented business codes all produce
    `AmbiguousFailure` and exactly one transport call;
  - any definitive-rejection allow-list cites an exact provider contract proving no side
    effect; otherwise omit the category;
  - correct the `unknown-4xx` acceptance test so it would fail on the current implementation,
    and exercise the concrete `PushPlusHttpTransport`, not only a preclassified fake exception.

### [P1] G4-002B — receipt/resolution persistence does not validate the binding required by §15-5

- Location: `src/omda/storage/sqlite_history.py:90-153`, `:477-527`, `:540-698`;
  `src/omda/ports/domain.py:117-130`; `data/schemas/delivery_receipt.schema.json:1-13`;
  `src/omda/ports/delivery.py:13-23`.
- Independent reproduction created two ambiguous operations and then recorded a resolution
  against operation A while supplying run/key/attempt fields belonging to operation B. The
  real SQLite adapter accepted it and advanced operation A:

  ```text
  CROSS_BOUND_RESOLUTION_ACCEPTED= RESOLVED_DELIVERED
  ('run-a:pushplus', 'run-b', 'run-b:pushplus', 'run-b:pushplus#1')
  ```

- `record_delivery_resolution` inserts caller-supplied redundant fields without comparing
  them to `delivery_operation`; `attempt_id` has no foreign key and is not checked to belong
  to that operation. This directly violates ADR-0001 §15-5.
- JSON receipt schema v2 declares `attempt_id`, but the migrated SQLite
  `delivery_receipt` table still has only the v1 columns and `DeliveryReceipt` has no
  `attempt_id`. `finalize_delivery_attempt` creates an attempt id but cannot bind it to the
  receipt. The claimed dual JSON/SQLite v2 boundary is therefore incomplete.
- `begin_delivery_operation` is required to journal key **and payload digest** atomically; its
  `DELIVERING` detail records only the key. The Delivery Port docstring also still advertises
  only `ok|failed` and places replay prevention on the adapter, rather than documenting the
  accepted three-state/pre-claim protocol.
- Impact: a malformed or operator-supplied resolution can authorize history for the wrong
  run/evidence, and an auditor cannot prove which immutable attempt a receipt represents.
- Required acceptance:
  - migrate the SQLite receipt association promised by ADR-0001 (old v1 rows may remain null;
    new finalized receipts bind their generated attempt id) and expose the association through
    the domain/Port consistently;
  - in the same resolution transaction, fail closed unless operation key, run id,
    idempotency key and optional attempt all refer to the same operation; add cross-binding
    negative tests to both SQLite and the parity fake;
  - journal key + payload digest atomically and update the Delivery Port contract to the
    Accepted ADR semantics;
  - make the ADR acceptance-9 test inspect the real v2 columns/relations, not merely
    `PRAGMA user_version` and an ambiguous status value.

### [P1] G4-004R — human-confirmed delivered evidence is not wired into real recovery

- Location: `src/omda/orchestrator/run.py:700-757`;
  `src/omda/orchestrator/recovery.py:56-155`;
  `tests/unit/test_adr_acceptance.py:302-405`.
- The pure `resolve_recovery_action` helper correctly treats
  `RESOLVED_DELIVERED` as authoritative without requiring an automatic receipt. The real
  `RunEngine._finish_after_delivery`, however, groups `SUCCEEDED` and
  `RESOLVED_DELIVERED` together and requires a receipt for both.
- Independent crash probe:
  1. run reaches a durable claim and the simulated process dies after the external-call point
     but before attempt/receipt finalization;
  2. operation has `IN_FLIGHT_OR_MAY_HAVE_SENT`, no receipt;
  3. owner records `CONFIRMED_DELIVERED`;
  4. restarting the real engine returns `RECOVERING`, leaves history index at zero and never
     completes.

  ```text
  AFTER_CRASH= IN_FLIGHT_OR_MAY_HAVE_SENT receipt= None
  AFTER_HUMAN_CONFIRMED= RECOVERING history_index= 0 tail= RECOVERING
  ```

- ADR-0001 §6/§11 and binding acceptance item 8 require human-confirmed delivery to commit
  official history without a second push. The acceptance test calls only the unused decision
  helper; production code never calls that helper, so the test does not prove the required
  path.
- Impact: the principal manual recovery for the crash-after-call/before-evidence window is a
  permanent dead end. The owner cannot safely finish the run despite having supplied the exact
  decision the ADR defines.
- Required acceptance: drive the real `RunEngine` through claim -> crash/no receipt ->
  `CONFIRMED_DELIVERED` -> restart and assert `COMPLETE`, one external effect and one atomic
  history commit. Use one production recovery decision path so helper and engine cannot diverge.

### [P1] G4-007 remains open — `--deliver` is still an unreachable route

- Location: `src/omda/cli.py:35-74`, `:138-190`; `src/omda/config.py:208-235`;
  `tests/integration/test_production_composition.py:84-156`.
- Reproduction from the exact candidate:

  ```text
  python -m omda.cli --deliver --run-id reviewer-probe
  --deliver requires delivery.channel == 'pushplus' in config ...
  exit=1
  ```

- `_main` calls `load_config()` with no config path or overrides. Its default delivery channel
  is always `markdown`, while the CLI exposes no `--config` option. The subsequent pushplus
  check therefore always fails. Parsed `--token-env` is also never applied. The production
  composition tests call `build_production_engine` directly with a hand-built pushplus Config,
  so none exercises the public CLI route that the repair claims to close.
- The route also supplies `_LocalEchoTransport` as its LLM transport. This may be acceptable
  for a no-narrative local mode, but it is not the concrete configurable LLM provider implied
  by the repair claim; the implementation/report must state the intended product boundary
  accurately.
- Impact: the Owner still cannot explicitly approve and execute a PushPlus recommendation.
  G5 remains a release audit and has no authorized milestone for implementing this missing G4
  feature.
- Required acceptance: execute the public CLI in a subprocess with injected fake network
  boundaries and prove that explicit `--deliver` reaches composition, uses the chosen token
  variable, remains off by default, and preserves controlled failure/history ordering. Provide
  a usable config/override path and a truthful LLM/runtime composition boundary.

### [P2] G4-008 — discarded LLM output creates cost/availability with no archived or delivered value

- Location: `src/omda/orchestrator/run.py:464-481`;
  `src/omda/output/markdown.py:1-24`.
- `_generate` invokes `generate_narrative`, discards its return value, and fails the whole run
  if that unused provider call fails. The Markdown module says the narrative is for archival
  purposes, but no archive or journal field stores it.
- Impact: once a real provider is configured, OMDA can spend tokens and lose availability
  without producing any user-visible or durable explanation. This does not permit fabricated
  facts, so it is P2 rather than P1.
- Required acceptance: either remove/bypass narrative generation while the mechanical
  no-free-text deliverable is the selected policy, or persist a bounded purpose for the result.
  Any reintroduction into the delivered payload must remain mechanically fact-bound and may
  require an ADR rather than a keyword filter.

### Acceptance matrix

| G4 criterion | Status | Evidence |
|---|---|---|
| Deterministic selection remains outside LLM | **PASS** | Core unchanged; LLM does not alter plan. |
| Render and complete fact validation before delivery | **PASS** | G4-001/G4-005 deterministic payload path. |
| Unconstrained LLM prose cannot add recommendations | **PASS for delivered payload** | No free-text slot; G4-008 remains an efficiency/semantics issue. |
| Atomic pre-network operation claim; same operation does not automatically re-send | **PASS for tested automatic path** | Two-connection claim and replay probes pass. |
| Provider ambiguity classification matches Accepted ADR | **FAIL** | All HTTP 4xx become definitive; acceptance test asserts the inverse of its comment. |
| Operation/attempt/receipt/resolution binding is complete | **FAIL** | Cross-bound resolution accepted; receipt has no attempt association; journal lacks digest. |
| Human-confirmed delivery completes without re-push | **FAIL** | Real engine remains RECOVERING when receipt is absent. |
| JSON schema v2 + SQLite migration v2 | **PARTIAL** | Version/tables exist, but promised receipt-attempt association is missing. |
| Default dry-run is isolated and external delivery needs explicit approval | **PASS for safety** | Default remains local and history-neutral. |
| Explicitly approved PushPlus route is executable | **FAIL** | Public `--deliver` always exits before composition. |
| UTF-8 packet bounds and plan cardinality | **PASS** | G4-006 closure inspected and tested. |
| No live calls/secrets/new runtime dependencies in ordinary tests | **PASS** | No live service used; secret scan empty; runtime dependencies remain empty. |
| Full regression/lint/diff checks | **PASS** | 617 tests, Ruff and diff check all pass. |
| Open blocking findings | **FOUR P1** | G4-002A, G4-002B, G4-004R, G4-007. |

### Checks performed and limits

- `git rev-parse`, exact merge-base, branch and clean-worktree verification: passed.
- Complete `base..candidate` name/status/stat and relevant source/test/schema review.
- Full suite: **617 passed in 3.49s**, 0 failed, 0 skipped.
- `ruff check src tests browser_companion`: passed.
- `git diff --check base..candidate`: passed.
- Targeted independent probes: unknown HTTP 418 classification, cross-operation resolution
  binding, receipt table columns, immediate-close migration durability, public CLI delivery,
  and real-engine crash -> human-confirmed-delivery recovery.
- Tracked secret/private-key pattern scan: no match.
- Latest official PushPlus message documentation was read; no live PushPlus or LLM request was
  made. No production code, merge, tag or push was performed.

### Re-review 3 verdict

**CHANGES_REQUESTED**

Candidate `1a197d9ceb95acd4e8214a28cd52c8172a4a02a0` must not be merged or marked
`ACCEPTED`, and G5 must not begin. Repair the four P1 findings with tests that exercise the
real concrete transport, SQLite bindings, real `RunEngine` recovery and public CLI route.
The Accepted ADR is sufficient for these repairs; a new ADR is needed only if the Executor
proposes changing its binding semantics rather than implementing them.

---

# G4 Re-review 4 — Production-boundary audit (2026-08-22)

## Reviewed object

- Reviewer: GPT-5.6 Sol in Codex
- Gate: G4 — Agent & Delivery
- Exact original base SHA: `68e3d453c7b803d2090cb1318f48e58eb18d6390`
- Exact candidate SHA: `8b1f7c9ad73f60b3288cd1f4fff941cc37e38f51`
- Previous reviewer commit: `50ce635ede960265dc60927e6bc09e0ffd9745bf`
- Candidate branch observed: `exec/g4-agent-delivery`
- Executor repair report: `reviews/stage-04/REPAIR_REPORT.md`

The candidate was a clean descendant of the supplied original base, with the exact supplied
candidate checked out and a clean worktree at review start. This review inspected both the
repair delta after the previous reviewer commit and the complete base-to-candidate behavior.

The four concrete counterexamples from re-review 3 are substantially repaired: unknown HTTP
4xx responses now become ambiguous, cross-bound resolutions are rejected, the real
`RunEngine` consumes the human-confirmed-delivered decision, and the public `--deliver` route
can now reach an injected PushPlus boundary. The bounded narrative archive also closes the
specific discarded-value finding.

The candidate nevertheless cannot be accepted. An independent public-entrypoint probe showed
that the newly reachable external-delivery route sends fabricated illustrative Album records
(`Sample Artist`, `<genre> Sample 1/2/3`) and then commits those identifiers to permanent
official history. No production `AlbumSource` implementation exists in `src/`; the only Album
source reachable from the CLI is `_sample_album_source`. Choosing where real Album candidates
come from crosses the already accepted G3/G4 boundary and is not specified by an open task.
This is an architecture blocker, not a reason for the Executor to improvise another scraper.

## Previous findings disposition

| Previous finding | Re-review 4 status | Evidence |
|---|---|---|
| G4-002A unknown HTTP 4xx | **CLOSED** | Concrete unknown 418/499 outcomes are ambiguous and are not retried. |
| G4-002B resolution/receipt binding | **PARTIAL** | Resolution and finalized receipts are bound, but begin/replay and the public legacy receipt write still accept unbound fields; see G4-002C. |
| G4-004R human-confirmed recovery | **CLOSED** | Real engine claim/crash/confirm/recover reaches COMPLETE without a second external call. |
| G4-007 unreachable public route | **CLOSED only for reachability** | `--config` reaches an injected PushPlus transport, but the reached route is not a valid production recommendation route; see G4-007B. |
| G4-008 discarded narrative | **CLOSED mechanically** | Generated text is stored in a bounded journal field and is excluded from the delivered fact-only report. |

## Blocking findings

### [P1] G4-007B — `--deliver` pushes illustrative Albums and commits them as official history

- Location: `src/omda/cli.py:165-198`, especially `:178-193`;
  `src/omda/cli.py:245-275`; `data/genres/README.md:41-42`.
- The public route always constructs `_sample_album_source(genres)`. That source hard-codes
  three invented records for every selected Genre:

  ```text
  <genre>-1 / <genre> Sample 1 / Sample Artist / 2015
  <genre>-2 / <genre> Sample 2 / Sample Artist / 2000
  <genre>-3 / <genre> Sample 3 / Sample Artist / 1990
  ```

- Independent probe called public `cli.main()` with a PushPlus config, temporary official
  SQLite store, runtime token and injected fake network transport. The run returned COMPLETE,
  made exactly one external call, and its outbound Markdown contained entries such as
  `tuareg Sample 1 — Sample Artist (2015)`. The official history then contained nine IDs such
  as `ambient-1`, `bebop-2` and `tuareg-3`.
- The packaged Genre directory is itself documented as an illustrative four-record subset,
  not a full source. Repository search found no concrete production `AlbumSource`; G3's
  Browser Companion extracts bounded Genre metadata, not Album candidates.
- Impact: a user who deliberately unlocks the supposedly real PushPlus route receives fake
  recommendations. Because delivery succeeds, fake Album identifiers are permanently excluded
  and Genre cooldown advances. This is a direct product-data corruption path, not a cosmetic
  demo limitation.
- Violated contract: Master Plan MVP steps 4-9 and Album invariants; the G4-007 claim of a
  production Agent/PushPlus composition; the rule that insufficient or unavailable real
  candidates must fail/report rather than be filled with unrelated Albums.
- Required disposition: the external route MUST fail closed while only sample/demo Album data
  is available. To complete G4, first submit an ADR/plan amendment that selects the v0.1
  production Album-candidate source, its provenance/licensing boundary, on-demand access
  policy, canonical identity/enrichment path, and whether the missing work belongs to reopened
  G3 or G4. Do not silently add broad RYM crawling, Album-detail fan-out, anti-bot bypass or
  another architecture not authorized by the baseline.
- Required acceptance: drive the public CLI through an injected network boundary and assert
  exact outbound facts and exact committed identities originate from a production source with
  auditable provenance. Add a negative test proving sample/demo sources cannot be used with
  external delivery and leave official history unchanged.

### [P1] G4-002C — Accepted ADR's full storage binding is still not enforced

- Location: `src/omda/storage/sqlite_history.py:436-480`, `:510-576`;
  Accepted ADR-0001 §15-5 (`docs/adr/0001-delivery-receipt-ambiguity-and-idempotency.md:371-374`).
- `begin_delivery_operation()` returns an existing row for the same operation key without
  verifying that the caller's `run_id` and `channel` match that row. Independent probe began
  `run-a/shared/markdown/digest-a`, then began `run-b/shared/pushplus/digest-a`; the second call
  was accepted as `created=False` and returned the first operation.
- `save_delivery_receipt()` still inserts any caller-supplied non-null `attempt_id` without
  checking that the attempt exists or belongs to the matching operation. Independent probe
  stored `shared-key#999` successfully despite there being no such attempt.
- Digest replay protection in the orchestrator and the repaired resolution method do not
  satisfy the ADR's storage-level requirement that operation, attempt, receipt and resolution
  run/key/channel/digest/attempt associations fail closed in the same storage transaction.
- Impact: malformed, stale or cross-run evidence can enter the durable authority boundary.
  Correctness currently depends on every caller pre-validating fields that the Accepted ADR
  explicitly assigns to persistence.
- Required acceptance: both SQLite and in-memory parity tests must reject an existing-key
  begin with any mismatched run/channel/digest binding, before any external call. Receipt writes
  with a non-null attempt must verify operation/key/run/channel/attempt in one transaction;
  define and test the narrow compatibility rule for legacy v1 null-attempt receipts.

## Non-blocking but required findings

### [P2] G4-007C — Configured token variable is ignored unless the CLI override is repeated

- Location: `src/omda/cli.py:35-80`, `:184-193`.
- `--token-env` has a non-null default (`PUSHPLUS_TOKEN`), so
  `args.token_env or config.delivery.pushplus_token_env` always chooses the parser default.
- Independent probe configured `pushplus_token_env=OMDA_PP_TOKEN`, set only that environment
  variable, and omitted `--token-env`; the route exited non-zero before the fake transport was
  called.
- Required acceptance: distinguish “CLI option omitted” from an explicit override, honor the
  config value first when omitted, and test config-only, CLI-override and missing-token cases
  through the public entrypoint without logging the secret.

### [P2] G4-002D — SQLite version 3 silently diverges from the Accepted version-2 boundary

- Location: `src/omda/storage/sqlite_history.py:50-54`; Accepted ADR-0001
  `:207-250`, `:296`, `:371-374`.
- Candidate now sets `_SCHEMA_VERSION = 3` so a receipt-attempt column omitted from its earlier
  v2 implementation can be added in a later migration. The Accepted ADR explicitly defines
  `user_version=2`, including that nullable column, as the G4 boundary. Tests and module
  comments still describe the v2 contract while fresh databases end at v3.
- Required disposition: either implement the Accepted v2 layout faithfully for the supported
  base migration, or amend the ADR with an explicit, backward-compatible v3 rollout and tests.
  Do not silently change an Accepted persistent version boundary inside a repair commit.

### [P2] G4-002E — Production transport documentation still classifies every HTTP 4xx as definitive

- Location: `src/omda/production.py:1-14`.
- The implementation was correctly repaired to make undocumented 4xx ambiguous, but the
  module-level production contract still says “HTTP 4xx” is terminal rejection.
- Required acceptance: document the same exact provider classification table that code and
  tests enforce; stale safety documentation must not instruct a future adapter to restore the
  rejected behavior.

### [P2] G4-009 — Real LLM runtime composition has no owned milestone

- Location: `src/omda/cli.py:184-193`, `:256-260`;
  `reviews/stage-04/REPAIR_REPORT.md:211-223`;
  `governance/IMPLEMENTATION_PLAN.md:351-364`, `:410-445`, `:530-532`.
- The external route uses `_LocalEchoTransport`, which always returns one constant local
  sentence. The repair report defers a real LLM client to G5, but G5 is a release-audit Gate
  containing installation, E2E/failure injection, security/licensing and release work—there is
  no runtime-provider implementation task. OD-2 assigns replaceable provider selection to G4.
- This does not authorize embedding unconstrained prose in delivery; the existing mechanical
  fact-only payload remains the safer boundary. The unresolved issue is that a demo echo is
  being called the production Agent composition.
- Required disposition in the same architecture decision: either select/configure a concrete
  replaceable v0.1 provider in G4, or explicitly define v0.1 as deterministic/no-LLM runtime
  and amend the MVP/plan accordingly. Do not defer implementation to a nonexistent G5 task.

## Acceptance matrix

| G4 criterion | Re-review 4 status |
|---|---|
| Deterministic selection remains outside LLM | **PASS** |
| Fact-only Markdown prevents LLM from changing recommendations | **PASS** |
| Unknown provider outcomes are ambiguous/no blind retry | **PASS** |
| Human-confirmed delivery recovers without re-push | **PASS** |
| Public explicit-delivery route is technically reachable | **PASS** |
| Public route delivers real, provenance-bearing Album candidates | **FAIL — P1 / architecture** |
| Official history contains only genuine selected Album identities | **FAIL — P1** |
| Full operation/attempt/receipt/resolution persistence binding | **FAIL — P1** |
| Config-only PushPlus token selection | **FAIL — P2** |
| Accepted persistent schema version boundary | **FAIL — P2 / governance** |
| G4 owns a truthful LLM/runtime boundary | **FAIL — P2 / architecture** |
| Default dry-run remains local and history-neutral | **PASS** |
| Full regression, lint and whitespace checks | **PASS** |

## Checks performed and limits

- Exact SHA, merge-base, branch, clean-worktree and complete repair-delta inspection: passed.
- Full suite: **630 passed in 4.31s**, 0 failed, 0 skipped.
- `ruff check src tests browser_companion`: passed.
- `git diff --check` for the supplied base-to-candidate range: passed.
- Independent probes: public external route with captured payload/official history, config-only
  token selection, cross-bound existing-operation begin, and unbound receipt attempt write.
- Previous probes were rerun/inspected for unknown 4xx classification, human-confirmed real
  engine recovery and resolution binding.
- Tracked secret/private-key pattern scan: no match.
- No live PushPlus, LLM, RYM or other network request was made. No production code, merge, tag
  or push was performed.

## Re-review 4 verdict

**BLOCKED_ARCHITECTURE / ADR_REQUIRED**

Candidate `8b1f7c9ad73f60b3288cd1f4fff941cc37e38f51` MUST NOT be merged, marked
`ACCEPTED`, or used to begin G5. The Executor must stop feature implementation and submit the
production-source/runtime ADR described in G4-007B/G4-009. The ADR must preserve all rejected
architecture constraints and make external delivery fail closed until genuine candidates are
available. After Reviewer acceptance of that decision, implement it and repair G4-002C plus
the P2 findings, then return one new cumulative candidate against the same original base.
