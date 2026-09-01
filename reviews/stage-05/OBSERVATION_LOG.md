# G5 T5.5 — Controlled Observation Log

> Re-audited: 2026-08-29 (G5-006). Reproducible via:
> `python tools/release_audit/observation_run.py`
>
> Observations 1–7 are SEVEN invocations of the PUBLIC `omda.cli --dry-run`
> entry point (same-day, automated rehearsals — explicitly NOT presented as
> elapsed operational stability). Each records timestamp, candidate SHA,
> command/mode, packaged data version, zero live calls (an exploding PushPlus
> transport factory proves no transport is even constructed), the preview
> digest, and before/after official-history state.
>
> Observation 8 replaces the previous (invalid) exhaustion observation with the
> targeted Album-exclusion evidence required by G5-002.

## Observations (raw JSON emitted by the script)

```
{"observation": 1, "mode": "public dry-run (CLI main entry)", "state": "COMPLETE", "live_calls": 0, "exit_code": 0, "official_history_before": "absent", "official_history_after": "absent", "same_day_automated": true}
{"observation": 2, "mode": "public dry-run (CLI main entry)", "state": "COMPLETE", "live_calls": 0, "exit_code": 0, "official_history_before": "absent", "official_history_after": "absent", "same_day_automated": true}
{"observation": 3, "mode": "public dry-run (CLI main entry)", "state": "COMPLETE", "live_calls": 0, "exit_code": 0, "official_history_before": "absent", "official_history_after": "absent", "same_day_automated": true}
{"observation": 4, "mode": "public dry-run (CLI main entry)", "state": "COMPLETE", "live_calls": 0, "exit_code": 0, "official_history_before": "absent", "official_history_after": "absent", "same_day_automated": true}
{"observation": 5, "mode": "public dry-run (CLI main entry)", "state": "COMPLETE", "live_calls": 0, "exit_code": 0, "official_history_before": "absent", "official_history_after": "absent", "same_day_automated": true}
{"observation": 6, "mode": "public dry-run (CLI main entry)", "state": "COMPLETE", "live_calls": 0, "exit_code": 0, "official_history_before": "absent", "official_history_after": "absent", "same_day_automated": true}
{"observation": 7, "mode": "public dry-run (CLI main entry)", "state": "COMPLETE", "live_calls": 0, "exit_code": 0, "official_history_before": "absent", "official_history_after": "absent", "same_day_automated": true}
{"observation": 8, "mode": "Album-exclusion evidence (G5-002 replacement)", "state": "COMPLETE", "selected_albums": 9, "committed_identity_rejected": true, "no_repeat_within_run": true}
```

Every observation additionally records `timestamp` (UTC), `candidate_sha` and
`preview_digest_sha256`; the full JSON lines are emitted by the script and
captured verbatim in `reviews/stage-05/` during the release rehearsal.

## Analysis

- **Observations 1–7** (public dry-run): all exit 0, state COMPLETE, preview
  file produced with a recorded SHA-256 digest, zero live calls (no PushPlus
  transport constructed), and the official runtime store stays `absent`
  before and after every run — dry-run is history-neutral by construction and
  measured, not assumed.
- **Observation 8** (G5-002 Album-exclusion evidence): a controlled fixture
  keeps Genre eligibility/cooldown satisfiable (40 Genres) and plants one
  already-committed canonical identity inside every selectable Genre pool. The
  full engine run completes with exactly 9 NEW real Albums, the committed
  identity is rejected, and no identity repeats within the run — permanent
  Album exclusion is proven inside the real selection path, not by a
  Genre-planning failure.
- All runs are deterministic fact-only output (no LLM narrative;
  `narrative_mode=deterministic` per ADR-0002 D8).

## Conclusion

≥ 7 honest public dry-runs plus the targeted Album-exclusion observation
completed with zero live calls, zero official-history mutation and zero
repeats.

**Note**: no RC/release tag is created by this log; the final release audit
and `RELEASE_CANDIDATE_ACCEPTED` belong exclusively to the Reviewer.
