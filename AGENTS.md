# OMDA Agent Rules

## Authority order

1. `docs/OMDA_AGENT_HANDOFF_SPEC.md`
2. `docs/OMDA_PROJECT_MASTER_PLAN_zh-CN.md`
3. Accepted ADRs under `docs/adr/`
4. `docs/OMDA_DUAL_MODEL_OPERATIONS_HANDBOOK_zh-CN.md`
5. Approved `governance/IMPLEMENTATION_PLAN.md`
6. Current atomic task

Lower authority must not override higher authority. If a required change conflicts with a higher-level rule, stop, set `BLOCKED_ARCHITECTURE`, and propose an ADR. Do not silently redesign the project.

## Current gate

The repository begins at G0. During G0, do not write production code. Produce only the implementation plan, risk register, stage-00 report, and state updates.

## Role separation

- DeepSeek V4 Flash is the Executor. It plans, implements, tests, commits, and reports.
- GPT-5.6 Sol is the independent Reviewer. It reviews exact commits and does not normally implement.
- Only the Reviewer may mark a Gate `ACCEPTED`.

## Non-negotiable rules

- Preserve equal opportunity among valid Genres. No popularity filter, tier probability, or LLM Genre quality score.
- Genre cooldown is the next 30 Genre picks, not 30 days or 30 runs.
- Successfully recommended Albums are permanently excluded using stable identity where possible.
- The deterministic engine selects; the LLM explains.
- Failed runs must not contaminate official Genre or Album history.
- Do not bypass Cloudflare, mass-crawl RYM, or make Album Detail fan-out a default design.
- Git-reviewable text is the community source of truth; SQLite is runtime state/cache/index only.
- Never commit credentials, cookies, browser profiles, personal data, or generated local databases.
- Do not use destructive Git commands or rewrite accepted history.

## Completion evidence

Chat statements are not evidence. A review handoff requires an exact base SHA, exact candidate SHA, clean-worktree disclosure, real test output, acceptance matrix, deviations, and an Executor report committed with the candidate.

