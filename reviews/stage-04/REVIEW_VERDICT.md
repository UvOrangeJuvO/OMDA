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
