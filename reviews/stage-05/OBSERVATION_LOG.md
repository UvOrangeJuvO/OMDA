# G5 T5.5 — Controlled Observation Log (verbatim script output)

> **G5-R1-003**: this file contains the observation script's ACTUAL output,
> committed verbatim. It replaces the earlier hand-summarized table that omitted
> the promised fields (timestamp, candidate_sha, command, data_version, preview
> digest, official history before/after).
>
> - Script: `python tools/release_audit/observation_run.py`
> - Executed against revision `781d52b54693cf81258949c3e14b08195a978bdc`
>   (the G5-R1 repair commit; every record carries that `candidate_sha`).
> - Local date 2026-09-11 (UTC timestamps are inside each record).
> - Exit code 0 — 8 observations recorded, all invariants satisfied.
>
> **Evidence-commit split.** The repair content was committed first
> (`781d52b`), then this script was executed against that exact revision and its
> output committed as the immediately following evidence commit. That evidence
> commit adds only evidence files, so the code revision under test and the final
> candidate are identical — verify with
> `git diff 781d52b54693cf81258949c3e14b08195a978bdc..HEAD --stat`.
>
> Observations 1–7 are invocations of the PUBLIC `omda.cli --dry-run` entry
> point (same-day automated rehearsals, explicitly NOT presented as elapsed
> operational stability). Observation 8 is the targeted Album-exclusion
> evidence required by G5-002.

## Verbatim output

```text
dry-run g5-obs-1: COMPLETE
preview: /var/folders/4g/nst7qw9x28gg7f5dmxnz13j80000gn/T/tmp02bn2nt7/previews/g5-obs-1.md
dry-run g5-obs-2: COMPLETE
preview: /var/folders/4g/nst7qw9x28gg7f5dmxnz13j80000gn/T/tmphdd1yhos/previews/g5-obs-2.md
dry-run g5-obs-3: COMPLETE
preview: /var/folders/4g/nst7qw9x28gg7f5dmxnz13j80000gn/T/tmpwu0gce40/previews/g5-obs-3.md
dry-run g5-obs-4: COMPLETE
preview: /var/folders/4g/nst7qw9x28gg7f5dmxnz13j80000gn/T/tmpiggmjb6u/previews/g5-obs-4.md
dry-run g5-obs-5: COMPLETE
preview: /var/folders/4g/nst7qw9x28gg7f5dmxnz13j80000gn/T/tmp9yg1m4uy/previews/g5-obs-5.md
dry-run g5-obs-6: COMPLETE
preview: /var/folders/4g/nst7qw9x28gg7f5dmxnz13j80000gn/T/tmpst3u97i2/previews/g5-obs-6.md
dry-run g5-obs-7: COMPLETE
preview: /var/folders/4g/nst7qw9x28gg7f5dmxnz13j80000gn/T/tmpsgj0p85r/previews/g5-obs-7.md
{"candidate_sha": "781d52b54693cf81258949c3e14b08195a978bdc", "command": "omda.cli --dry-run --output-dir <tmp> --run-id g5-obs-1", "config": "defaults (llm.mode=deterministic)", "data_version": "2026-08-27", "exit_code": 0, "live_calls": 0, "mode": "public dry-run (CLI main entry)", "note": "not elapsed operational stability; rehearsals only", "observation": 1, "official_history_after": "absent", "official_history_before": "absent", "preview_digest_sha256": "02dac95fbb529cb0caa5f9751676141d8daf7ccfbeea142c4df2b2f15bfcfe7f", "same_day_automated": true, "state": "COMPLETE", "timestamp": "2026-09-12T16:16:46.864876Z"}
{"candidate_sha": "781d52b54693cf81258949c3e14b08195a978bdc", "command": "omda.cli --dry-run --output-dir <tmp> --run-id g5-obs-2", "config": "defaults (llm.mode=deterministic)", "data_version": "2026-08-27", "exit_code": 0, "live_calls": 0, "mode": "public dry-run (CLI main entry)", "note": "not elapsed operational stability; rehearsals only", "observation": 2, "official_history_after": "absent", "official_history_before": "absent", "preview_digest_sha256": "7078fe2af8ccecaca813f9898bcc7eaadd0b370f7022a37e0a1f4aa89227e77a", "same_day_automated": true, "state": "COMPLETE", "timestamp": "2026-09-12T16:16:46.883778Z"}
{"candidate_sha": "781d52b54693cf81258949c3e14b08195a978bdc", "command": "omda.cli --dry-run --output-dir <tmp> --run-id g5-obs-3", "config": "defaults (llm.mode=deterministic)", "data_version": "2026-08-27", "exit_code": 0, "live_calls": 0, "mode": "public dry-run (CLI main entry)", "note": "not elapsed operational stability; rehearsals only", "observation": 3, "official_history_after": "absent", "official_history_before": "absent", "preview_digest_sha256": "907a741258c41227714fd0623f0f38eb83355fe31f61ca7c7fa2dd03b44b3c40", "same_day_automated": true, "state": "COMPLETE", "timestamp": "2026-09-12T16:16:46.896853Z"}
{"candidate_sha": "781d52b54693cf81258949c3e14b08195a978bdc", "command": "omda.cli --dry-run --output-dir <tmp> --run-id g5-obs-4", "config": "defaults (llm.mode=deterministic)", "data_version": "2026-08-27", "exit_code": 0, "live_calls": 0, "mode": "public dry-run (CLI main entry)", "note": "not elapsed operational stability; rehearsals only", "observation": 4, "official_history_after": "absent", "official_history_before": "absent", "preview_digest_sha256": "e0bbf2ced428613e6375b588ac743330ca6ee41194211c7945296381a899419c", "same_day_automated": true, "state": "COMPLETE", "timestamp": "2026-09-12T16:16:46.908826Z"}
{"candidate_sha": "781d52b54693cf81258949c3e14b08195a978bdc", "command": "omda.cli --dry-run --output-dir <tmp> --run-id g5-obs-5", "config": "defaults (llm.mode=deterministic)", "data_version": "2026-08-27", "exit_code": 0, "live_calls": 0, "mode": "public dry-run (CLI main entry)", "note": "not elapsed operational stability; rehearsals only", "observation": 5, "official_history_after": "absent", "official_history_before": "absent", "preview_digest_sha256": "067ec79c0e8d7467fc096ea6bf69fe0b1597ebd8954ee2f8ff80553a7d673f96", "same_day_automated": true, "state": "COMPLETE", "timestamp": "2026-09-12T16:16:46.920786Z"}
{"candidate_sha": "781d52b54693cf81258949c3e14b08195a978bdc", "command": "omda.cli --dry-run --output-dir <tmp> --run-id g5-obs-6", "config": "defaults (llm.mode=deterministic)", "data_version": "2026-08-27", "exit_code": 0, "live_calls": 0, "mode": "public dry-run (CLI main entry)", "note": "not elapsed operational stability; rehearsals only", "observation": 6, "official_history_after": "absent", "official_history_before": "absent", "preview_digest_sha256": "2a60e1ec212fc52e17c1725248960f425fd8e19b9a2d73c701182e5bf1129ef7", "same_day_automated": true, "state": "COMPLETE", "timestamp": "2026-09-12T16:16:46.933179Z"}
{"candidate_sha": "781d52b54693cf81258949c3e14b08195a978bdc", "command": "omda.cli --dry-run --output-dir <tmp> --run-id g5-obs-7", "config": "defaults (llm.mode=deterministic)", "data_version": "2026-08-27", "exit_code": 0, "live_calls": 0, "mode": "public dry-run (CLI main entry)", "note": "not elapsed operational stability; rehearsals only", "observation": 7, "official_history_after": "absent", "official_history_before": "absent", "preview_digest_sha256": "ddd648a861b61b8043559bf92a421c1a7032f79fd85e24bdc9af7a2b52f39594", "same_day_automated": true, "state": "COMPLETE", "timestamp": "2026-09-12T16:16:46.946366Z"}
{"candidate_sha": "781d52b54693cf81258949c3e14b08195a978bdc", "committed_identity_rejected": true, "mode": "Album-exclusion evidence (G5-002 replacement)", "no_repeat_within_run": true, "observation": 8, "official_history_picks_after": 6, "selected_albums": 9, "state": "COMPLETE", "timestamp": "2026-09-12T16:16:46.969024Z"}
OBSERVATIONS: 8 recorded, all invariants satisfied
```

## What each record contains

- **Observations 1–7** (public dry-run): `observation`, `timestamp` (UTC),
  `candidate_sha`, `command`, `mode`, `data_version`, `config`, `live_calls`,
  `exit_code`, `state`, `preview_digest_sha256`, `official_history_before`,
  `official_history_after`, `same_day_automated`, `note`.
- **Observation 8** (Album-exclusion evidence): `observation`, `timestamp`,
  `candidate_sha`, `mode`, `state`, `selected_albums`,
  `committed_identity_rejected`, `no_repeat_within_run`,
  `official_history_picks_after`.

## Analysis

- **Observations 1–7**: every run exits 0 with state COMPLETE, records a real
  preview SHA-256, reports **zero live calls** (an exploding PushPlus transport
  factory is installed, so any attempt to construct a transport would fail the
  observation), and the official runtime store is `absent` both before AND after
  each run — dry-run is history-neutral by measurement, not by assumption.
- **Observation 8**: with 40 selectable Genres (cooldown satisfiable) and an
  already-committed canonical identity planted inside every candidate pool, the
  full engine run completes with exactly 9 NEW real Albums, the committed
  identity is rejected, and no identity repeats within the run — permanent Album
  exclusion is proven inside the real selection path.
- All runs are deterministic fact-only output (no LLM narrative;
  `narrative_mode=deterministic` per ADR-0002 D8).

## Conclusion

Seven honest public dry-runs plus the targeted Album-exclusion observation
completed with zero live calls, zero official-history mutation and zero repeats.
This log creates no RC/release tag; the final release audit and
`RELEASE_CANDIDATE_ACCEPTED` belong exclusively to the Reviewer.
