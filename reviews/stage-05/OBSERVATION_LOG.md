# G5 T5.5 — Controlled Observation Log

> Date: 2026-08-26. Reproducible via:
> `python tools/release_audit/observation_run.py`
> All runs use the REVIEWED curated source set + SourceRegistry with a FAKE
> PushPlus transport (zero live calls, no real PushPlus/LLM/RYM).

## Observations

| # | run_id | state | transport calls | albums | within-run repeats | committed picks | mode |
|---|---|---|---|---|---|---|---|
| 1 | g5-obs-1 | COMPLETE | 1 | 9 | 0 | 3 | isolated history |
| 2 | g5-obs-2 | COMPLETE | 1 | 9 | 0 | 3 | isolated history |
| 3 | g5-obs-3 | COMPLETE | 1 | 9 | 0 | 3 | isolated history |
| 4 | g5-obs-4 | COMPLETE | 1 | 9 | 0 | 3 | isolated history |
| 5 | g5-obs-5 | COMPLETE | 1 | 9 | 0 | 3 | isolated history |
| 6 | g5-obs-6 | COMPLETE | 1 | 9 | 0 | 3 | isolated history |
| 7 | g5-obs-7 | COMPLETE | 1 | 9 | 0 | 3 | isolated history |
| 8 | g5-obs-shared-1/2 | COMPLETE → FAILED | 1 | 9 / 0 | 0 | 3 | shared durable history |

## Analysis

- **Observations 1–7** (isolated history, dry-run semantics): every run
  completes with exactly 9 distinct Albums, exactly 3 committed Genre picks in
  its own isolated history, and exactly one external (fake) call — no
  within-run repeats, no cross-run pollution of any shared store.
- **Observation 8** (shared durable history): the first run commits 9 Albums
  (3 picks); the second run on the SAME store permanently excludes those
  identities — with the 4-per-Genre curated pool it exhausts and **fails
  explicitly** (never repeats an identity, never substitutes sample data, and
  the shared history stays at 3 picks / 9 identities). This is the documented
  AC-9A exhaustion behavior.
- Deterministic fact-only output confirmed across all observations (no LLM
  narrative; `narrative_mode=deterministic` marker in the GENERATED journal).

## Conclusion

≥ 7 controlled observations completed with zero history pollution, zero
repeats and zero unexplained side effects. The runtime is stable and
deterministic for a v0.1 release candidate evaluation.

**Note**: no RC/release tag is created by this log; the final release audit
and `RELEASE_CANDIDATE_ACCEPTED` belong exclusively to the Reviewer.
