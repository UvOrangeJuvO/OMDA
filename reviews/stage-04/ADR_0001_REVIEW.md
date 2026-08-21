# ADR-0001 Independent Review

## Reviewed object

- Reviewer: GPT-5.6 Sol in Codex
- Review date: 2026-08-21
- ADR: `docs/adr/0001-delivery-receipt-ambiguity-and-idempotency.md`
- ADR proposal commit: `dc18498dd7f644a87c271b70ef47edee9db51c70`
- Parent Reviewer commit: `3977d62198750df8177452330b6c55986785229b`
- Repository state observed: `BLOCKED_ARCHITECTURE / ADR_PENDING`
- ADR status observed: `Proposed`
- Production-code changes in the ADR proposal: none

## Summary

The recommended direction is sound: persist a local delivery claim before the external call,
model ambiguity explicitly, never blind-retry an outcome that may have produced a push, keep
receipts immutable, and do not claim distributed atomicity between PushPlus and SQLite.

The ADR is not yet implementable as written. Its `REGISTERED -> SENT` protocol has a
concurrency window that can still send twice; its immutable one-receipt-per-key model cannot
represent the later success retry that the same ADR permits after `failed`; and it has no
durable human-resolution protocol for an `ambiguous` receipt. These are central state-machine
issues, not editorial details. The ADR must remain `Proposed` and be revised before any G4-002
production work resumes.

## Findings requiring revision

### ADR-001 — `REGISTERED` recovery reopens the exact concurrency race the ledger is meant to close

- Location: ADR §4 and §5, especially the rules “intent REGISTERED without SENT -> allow one
  resend” and “set SENT immediately before the provider call”.
- Counterexample:
  1. process A inserts and commits `REGISTERED`;
  2. before A changes the row to `SENT`, process B observes `REGISTERED`;
  3. §4/§5 authorizes B to resume and send once;
  4. A then writes `SENT` and sends as well.
- A UNIQUE key prevents two inserts, but it does not give the winner exclusive ownership of
  the transition from `REGISTERED` to the external call. A lease alone also cannot guarantee
  at-most-one send unless it has a complete fencing/ownership protocol and the old owner is
  prevented from sending after losing the lease.
- Required revision: choose and document an executable atomic claim protocol. The safest
  minimal protocol is to transactionally create the operation directly in a conservative
  `MAY_HAVE_SENT`/`IN_FLIGHT` state before the external call; every existing row blocks every
  other automatic caller. A crash after that commit but before the call becomes a false
  ambiguity requiring human action, which is an explicit availability tradeoff for at-most-one
  outbound request. If recoverable `REGISTERED` is retained, define owner token, atomic
  compare-and-set, fencing and takeover semantics that prove the original owner cannot later
  send.

### ADR-002 — immutable receipts and “retry failed with the same key” are contradictory

- Location: ADR §2, §4, §6, §7 and §8.
- Evidence:
  - the ADR keeps G1-002: one immutable receipt per idempotency key;
  - §7 says a bound `failed` receipt may safely retry with a new attempt using the same key;
  - §8 expects repeated confirmed failures, each as a new attempt under the same key;
  - a later success cannot replace the immutable `failed` receipt, while a second receipt
    conflicts with the unique key.
- The data model also says one `delivery_intent` row has one `attempt_id`, but bounded retries
  create multiple attempts. One row cannot simultaneously be the operation and the immutable
  attempt ledger.
- Required revision: separate the stable **delivery operation** (keyed by idempotency key) from
  zero/one-or-more immutable **attempt records** (keyed by attempt id), or prohibit automatic
  retry entirely once an outbound attempt exists. Define whether `failed` is terminal. If a
  corrected retry is allowed, specify its new operation/generation key and how it remains tied
  to the original run without weakening same-run replay protection. Do not overwrite an
  immutable receipt.

### ADR-003 — ambiguous outcomes have no durable human-resolution path

- Location: ADR §7 and §8.
- Evidence: `ambiguous` always returns `REQUIRE_HUMAN`, but the ADR does not define how the
  human records one of these outcomes:
  - confirmed delivered -> authorize official history commit;
  - confirmed not delivered -> explicitly abandon or authorize a new operation;
  - still unknown -> remain blocked.
- Because the ambiguous receipt is immutable, simply changing it to `ok` or `failed` would
  violate the chosen evidence contract. Without a separate resolution record, the run stays
  in `RECOVERING` forever even after the Owner establishes the outcome.
- Required revision: define an append-only `delivery_resolution`/operator-decision record (or
  equivalent journal evidence) bound to run/key/receipt/actor/time/reason. Define allowed
  resolution transitions and exact recovery actions. A human-confirmed delivery may commit
  history without re-push; a confirmed non-delivery must not silently reuse the blocked
  operation key; unresolved ambiguity remains no-send/no-commit.

### ADR-004 — the persistence API and transaction boundary are underspecified

- Location: ADR §5 and §9.
- Evidence:
  - §5 requires `REGISTERED -> SENT -> RECEIPTED` state changes, but §9 adds only
    `register_delivery_intent` and `find_delivery_intent`; no atomic transition/compare-and-set
    methods exist.
  - “journal DELIVERING” and operation reservation are listed as separate writes. A crash or
    concurrent process between them produces states whose ownership/recovery behavior is not
    completely specified.
  - current SQLite uses `PRAGMA user_version=1`, one immutable receipt table, and a single
    connection per `SqliteHistory`. The ADR does not specify the v2 DDL, constraints, indexes,
    transition guards, payload binding or a concurrency test using independent connections.
- Required revision:
  - define the Port at semantic-operation level, for example an atomic
    `begin_delivery_operation(...) -> created/existing snapshot`, finalization methods guarded
    by expected state/version, and append-only resolution methods;
  - include payload digest, run id, channel, timestamps and schema/operation version so the same
    key cannot be replayed with different content;
  - state which journal/operation writes share one SQLite transaction and which must commit
    before the network call;
  - specify SQLite migration v1 -> v2 and verify old rows, backup/rollback, two independent
    connections, crash points and conflicting payloads.

### ADR-005 — blanket HTTP 4xx retry is neither justified nor useful

- Location: ADR §6 and §8.
- Evidence: the ADR classifies every HTTP 4xx as proof the provider did not accept a push and
  then retries authentication/parameter failures. It supplies no exact PushPlus response-code
  contract proving this for every 4xx/business-code combination. Authentication and malformed
  request failures also cannot become successful without changing input/configuration.
- The current transport returns only a decoded mapping, so the proposed implementation cannot
  even distinguish HTTP status, business code and parse failure without a new typed transport
  result.
- Required revision: pin the classification table to specific documented PushPlus HTTP and
  business codes. Default every unrecognized response, 5xx, parse failure and post-write
  transport exception to ambiguous/no-retry. Prefer no automatic external retry unless the
  transport can prove no request bytes were sent or the provider supplies a real idempotency
  guarantee. Treat configuration/auth/parameter rejection as terminal for that operation,
  not as an automatic retry loop.

## Required state model in the revised ADR

The revision does not have to use these exact names, but it must distinguish at least:

```text
DeliveryOperation (one per stable key)
  NEW/absent
    -> IN_FLIGHT_OR_MAY_HAVE_SENT   # durable claim committed before network
        -> SUCCEEDED                # bound immutable success evidence
        -> CONFIRMED_FAILED         # bound immutable rejection evidence
        -> AMBIGUOUS                # no automatic retry
        -> RESOLVED_DELIVERED       # append-only human/provider confirmation
        -> RESOLVED_NOT_DELIVERED   # append-only abandonment/new-op decision
```

It must explicitly choose the guarantee:

- OMDA can guarantee **at most one automatic outbound request per delivery operation** when it
  persists the conservative claim before the call and never auto-retries ambiguity.
- Without provider-side idempotency, it cannot guarantee exactly-once remote delivery.
- A stronger availability guarantee (automatically retrying a crash before the call) conflicts
  with strict at-most-once behavior unless an enforceable ownership/fencing mechanism exists.

## Acceptance tests required by the revised ADR

1. Two independent SQLite connections race on the same absent key: only one receives authority
   to call the transport; outbound calls `<= 1`.
2. A second caller arrives while the first is between reservation and send: it never calls the
   transport.
3. Crash after durable claim but before call: restart does not auto-send; state is explicitly
   ambiguous/manual under the conservative protocol.
4. Crash after call but before final evidence: restart does not auto-send.
5. Same key with a different payload digest fails closed before network.
6. Existing `ok`, `ambiguous`/in-flight and resolved-delivered evidence never re-sends.
7. `failed` behavior matches the chosen finality rule and never conflicts with immutable
   evidence; if retries exist, attempt/operation cardinality is tested.
8. Human-confirmed delivered commits history without push; confirmed-not-delivered follows the
   documented abandon/new-operation path; unresolved stays blocked.
9. JSON schema v2 and SQLite migration v2 both accept old v1 rows, validate every new state and
   preserve data on downgrade/fail-closed rollback.
10. Typed provider response tests cover exact documented definitive codes plus unknown 4xx,
    5xx, malformed body, timeout, connection reset and response loss.

## Scope and governance

- The current `BLOCKED_ARCHITECTURE / ADR_PENDING` state is correct and must remain.
- The ADR must remain `Proposed`; the Executor must not mark it `Accepted`.
- No G4-002 production implementation may resume until the revised ADR is accepted by the
  Reviewer.
- G4-005/G4-007 remain separate open review findings; revising this ADR does not close them.
- The revised ADR should keep the useful existing material: three-option comparison, no
  cross-system atomicity claim, versioned migration/rollback intent and local fake-based tests.

## Decision

**REVISE**

The recommended option B may remain the preferred direction, but its operation/attempt/
receipt/resolution model and atomic claim semantics must be corrected before acceptance.
