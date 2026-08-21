
---

# G4 Re-review 1 Repair（2026-08-21）

对应 Reviewer commit：`754a140562dcb36dacf77b56d1d6505996a0c490`（`review(g4): request agent and delivery repairs`）
上一 candidate：`10275ed04a66ed50631edb0d43a3505f18d2a5b7`
本轮修复 commits：`f5f02d2`（G4-001/G4-005）、`66c7ee4`（G4-002）、`460a518`+`343d3ed`（G4-003）、`aedff3f`（G4-004）、`958a32b`（G4-006）
每项先加失败测试复现 Reviewer 反例、再做最小修复；未弱化既有测试（G4 新增测试按新验收语义升级并披露）。

## G4-001（P1）— 生产 RunEngine 绕过渲染器与事实校验 — CLOSED

- **根因**：`RunEngine._generate()` 直接返回 LLM 原始响应为 payload；`_validate_payload()` 只查非空+长度；`_deliver_and_commit()` 原样投递并提交官方历史——注入/编造 LLM 回答被视为已验证推荐。
- **修复**（`f5f02d2`）：`RunEngine._generate()` 现在**渲染确定性结构化 Markdown**（`render_markdown(self._report_data(plan), narrative)`，facts 仅来自 plan）；`_validate_payload(payload, plan)` 调用 `validate_markdown`（结构/长度/事实引用全量校验）；交付的 payload 是结构化报告而非原始 LLM 文本。
- **测试**：`test_production_run_delivers_structured_markdown_not_raw_llm_text`（真实 RunEngine + 对抗 LLM "IGNORE FACTS: recommend Fabricated Album" → COMPLETE 时 payload 以 `# 每日音乐发现` 开头且无 `- Fabricated Album`，或 FAILED 时投递/历史双零）；`test_production_run_never_commits_history_for_invalid_payload`。
- **关闭证据**：Reviewer 复现（对抗回答被原样投递 + 提交历史）关闭——生产路径只交付确定性报告，校验失败零投递零历史。

## G4-002（P1）— PushPlus 盲目重试歧义发送 — CLOSED

- **根因**：transport 异常（超时/响应丢失）被重试——provider 可能已接受第一次请求，重试造成二次推送；耗尽后标 `failed`（歧义被当确认失败 → run 终结 FAILED 而非 RECOVERING）。
- **修复**（`66c7ee4`）：**transport 异常 → 立即返回 `status="ambiguous"` 收据，绝不重试**（无第二次外部推送、无退避）；HTTP **明确失败响应**（provider 显式拒绝）才允许有界重试，耗尽 → `failed`（确认未送达）；ambiguous 在 RunEngine 三分法下进入 **RECOVERING**（G2-012 已支持）。
- **测试**：`test_timeout_after_provider_accept_is_ambiguous_not_retried`（`EffectThenTimeout`：calls==1、effects==1、status=="ambiguous"、零退避）；`test_ambiguous_outcome_enters_recovery_at_run_level`（真实 RunEngine → RECOVERING、历史零污染）；既有网络错误测试升级为 `..._maps_to_ambiguous_not_failed`。
- **关闭证据**：Reviewer 复现（响应丢失后二次推送）关闭——歧义不盲重发、与确认拒绝可区分、进入 durable RECOVERING。

## G4-003（P1）— dry-run 只是选择器且污染历史 — CLOSED

- **根因**：`omda.cli` 无 `main()`/应用组合；测试内 `build_delivery` 传 Protocol 类本身；明显组合用 `MarkdownFileDelivery` + 真实 RunEngine → 本地文件+COMPLETE+官方 pick index 前进+Album 排除。
- **修复**（`460a518`+`343d3ed`）：`run_dry_run()` 生产可调用——**真实 RunEngine + `SqliteHistory(":memory:")` 隔离历史 + MarkdownFileDelivery**，零外部调用、不解析 token、官方历史永不触碰；`main()` + `if __name__ == "__main__"` 入口，`python -m omda.cli --dry-run --output-dir ... --run-id ...` 真实执行（实测 COMPLETE + 生成 `<run_id>.md`）；`--deliver` 仍唯一解锁外部推送。
- **测试**：`test_run_dry_run_writes_preview_and_keeps_history_neutral`、`test_repeated_dry_runs_do_not_pollute_history`（7 次 dry-run 哨兵官方库零变化）、`test_dry_run_resolves_no_token`、`test_deliver_mode_still_requires_explicit_flag`。
- **关闭证据**：Reviewer 复现（`python -m omda.cli` 空跑 + 组合污染历史）关闭——dry-run 可执行、历史中性、token 零解析。

## G4-004（P1）— recovery 接受未绑定收据 — CLOSED

- **根因**：`resolve_recovery_action` 不要求 post-delivery journal tail；只查 `receipt.status`/`run_id`，不查 `idempotency_key`/`channel`；`_AFTER_DELIVER_TRANSITIONS` 定义了未用。
- **修复**（`aedff3f`）：**先要求 journal tail ∈ {DELIVERING, DELIVERED, RECOVERING}**（无 post-delivery journal → REQUIRE_HUMAN，禁止 COMMIT_HISTORY）；再要求收据**精确绑定** run_id + idempotency_key + channel + status=="ok" 才 COMMIT_HISTORY；任何不匹配 → REQUIRE_HUMAN。
- **测试**：无 journal tail + ok 收据 → REQUIRE_HUMAN；同 key 但错 channel → REQUIRE_HUMAN；status=failed → REQUIRE_HUMAN；仅"journal 达交付窗口 + 全绑定 ok 收据"→ COMMIT_HISTORY（Reviewer 精确复现关闭）。
- **关闭证据**：stale/corrupt 证据无法再授权官方历史提交；生产一致使用 G2 `RunEngine.recover()`（同绑定语义）与强化后的决策层。

## G4-005（P1）— Markdown 校验只查 title 前缀 — CLOSED

- **根因**：Album presence 只比 title 前缀；artist/year/Genre 关联/run id 不校验；narrative prose 编造（"recommend Album X instead"）因非 bullet 通过。
- **修复**（`f5f02d2`）：`validate_markdown` 重写——**完整 bullet 文本（title — artist (year)）必须精确匹配 plan 且位于其 Genre 节下**；run id 行必须精确匹配；narrative 嵌入 `> ` 引用块并拒绝：directive verbs（recommend/suggest/choose/pick/ignore/instead/replace/remove/add）、注入的 `- `/`## ` 结构、**em-dash 专辑断言不在 fact packet 中**。
- **测试**：`test_every_fact_mutation_is_rejected`（run id/genre heading/year/artist/title/genre 关联六种独立变异全部拒绝）；narrative directive verb 拒绝；narrative em-dash 编造断言拒绝；既有 `test_narrative_cannot_alter_selected_facts` 升级为 `test_narrative_with_directive_verbs_is_rejected`（语义强化，披露）。
- **关闭证据**：Reviewer 复现（`Real Album — Fake Artist (1900)` + prose 编造通过）关闭——每个选中事实独立变异必拒，prose 编造不能仅因非 bullet 通过。

## G4-006（P1）— 事实包未全字段有界 — CLOSED

- **根因**：`MAX_FIELD_LENGTH` 只用于 name/title/artist；run_id/genre_id/album_id 无长度与空值约束，无聚合序列化大小上限；百万字符 run_id 被接受冻结。
- **修复**（`958a32b`）：`bounded_packet` 对所有字符串字段（run_id/genre_id/name/album_id/title/artist）强制**非空 + `MAX_FIELD_LENGTH`**；新增 `MAX_PACKET_BYTES=48_000` **聚合序列化大小上限**（JSON 序列化后校验，超限拒绝）；`EXPECTED_GENRES/EXPECTED_ALBUMS` 文档化真实 3x3 基数。
- **测试**：百万字符 run_id / 空 run_id / 超长与空 genre_id / album_id / name / title / artist 拒绝；10 genres×1900 + 30 albums×(2000+2000) 聚合超限拒绝（transport 调用前）。
- **关闭证据**：Reviewer 复现（百万字符 run_id 接受）关闭——所有外部控制字段有界，序列化总量有上限，transport 前失败。

## 验证

| 命令 | 结果 |
|---|---|
| `pytest -q -p no:cacheprovider` | **566 passed, 0 failed, 0 skipped, 0 error** |
| `pytest -v`（TEST_RESULTS.txt） | 566 passed |
| `ruff check src tests browser_companion` | All checks passed |
| `git diff --check` | clean |
| 既有测试未删除/弱化/skip | 确认（539 → 566 单调增长；G4 新增的 2 个测试按新验收语义升级并披露：narrative directive 拒绝、网络错误→ambiguous） |
| `python -m omda.cli --dry-run` | 真实执行 COMPLETE + 生成预览文件 |
| tracked 敏感文件 | 无 |
| G0-G3 verdict 未改；G2 Core 零改动（`git diff 754a140 -- src/omda/core/` 0 文件） | 确认 |
| 无 G5 scope creep；无 live LLM/PushPlus 依赖；无反爬绕过 | 确认 |
| 未 merge / 未 tag / 未进入 G4 后接 G5 / 未写 ACCEPTED | 确认 |
