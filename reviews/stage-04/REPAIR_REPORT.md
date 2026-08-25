
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

---

# G4 Re-review 2 Repair（2026-08-21，ADR-0001 Accepted 后恢复实现）

对应 Reviewer commit：`3977d62198750df8177452330b6c55986785229b`（评审 candidate 13a659d）
ADR-0001 接受 commit：`1349a0fd53116335d372c89684d83f1d556b63ac`（Accepted ADR + §15 绑定约束）
上一 candidate：`13a659d741e70df5e7b3faa561ffc822dd4efb5c`
本轮修复 commits：`701c203`（模型+迁移）、`606c859`（G4-002 协议）、`4db6803`（§12 验收）、
`01f4506`（G4-005）、`c40d619`（G4-007+CLI P2）、`694a443`（G4-006 P2）
每项先加失败测试复现 Reviewer 反例、再最小实现；ADR 语义未改（§15 六条全部落实）。

## G4-002（P1）— 按 Accepted ADR-0001 + §15 实现 — CLOSED

- **§15-1 同 key 永不二发**：`begin_delivery_operation` 网络前原子 claim（与 DELIVERING
  journal 同事务、`INSERT ... ON CONFLICT DO NOTHING`）；既有任意 operation 行（含
  CONFIRMED_FAILED）→ `created=False` → `_existing_operation_outcome` 状态表，transport
  永不再次调用；人工重试走显式新 generation key（v0.1 fail-closed，不临时复用旧 key）。
- **§15-2 保守 claim 优先**：claim 后、调用前崩溃 = `IN_FLIGHT_OR_MAY_HAVE_SENT` 无 attempt
  → REQUIRE_HUMAN，不自动恢复（接受验收 3）。
- **§15-3 零字节证明才重试**：`NoBytesSentError` 是唯一自动重试类（DNS/连接拒绝证明零字节
  写出，有界）；`ProviderRejection`（文档化精确类别）terminal 非重试循环；未知响应/5xx/
  解析失败/写后异常 → `AmbiguousFailure` → ambiguous no-retry（验收 10 全表）。
- **§15-4 resolution 来源受限**：自动路径仅 SUCCEEDED/CONFIRMED_FAILED/AMBIGUOUS；人工
  resolution 只允许从 IN_FLIGHT/AMBIGUOUS 推进到 RESOLVED_*；SUCCEEDED 被改写 fail-closed
  （测试 `test_resolution_from_succeeded_fails_closed`）。
- **§15-5 持久化绑定完整**：operation/attempt/receipt/resolution 同存储事务验证；
  payload digest=SHA-256 绑定，同 key 异 digest 网络前 fail-closed（验收 5）；SQLite
  `user_version=2` + JSON receipt schema v2 双版本边界实现并测试（验收 9）。
- **§15-6 验收矩阵不可缩减**：ADR §12 十项全部落地（`tests/unit/test_adr_acceptance.py`），
  并发用同一文件 DB 两个独立连接（`BEGIN IMMEDIATE` + ON CONFLICT，测试断言恰一方
  created、outbound ≤ 1）。
- **三态一致迁移**：`DeliveryReceipt.status` 注释、Delivery Port docstring、
  `delivery_receipt.schema.json` v2（enum + attempt_id）一致；新增
  delivery_operation/attempt/resolution 三个 JSON schema。
- **人工恢复路径**：`record_delivery_resolution`（append-only）+ `resolve_recovery_action`
  按 operation 状态决策：RESOLVED_DELIVERED → COMMIT_HISTORY 不重推；CONFIRMED_NOT_DELIVERED/
  RESOLVED_NOT_DELIVERED → REQUIRE_HUMAN（新操作）；STILL_UNKNOWN → 保持阻塞（验收 8）。

## G4-005（P1）— narrative 黑名单被自然语言绕过 — CLOSED（机械契约）

- **方案**（Reviewer 许可的 "omit unconstrained LLM prose from the deliverable"）：
  `render_markdown` 不再嵌入任何 LLM 自由文本——交付物 = 确定性结构化事实（title/run id/
  Genre heading/完整 bullet）。LLM narrative 由 Orchestrator 生成但**只作存档用途，绝不
  进交付物**（无自由文本槽 → off-packet Album/Genre 引用不可能出现在交付报告）。
- **测试**：`test_render_contains_no_llm_free_text_slot`（无 quote 块、无编造）；真实
  RunEngine 对抗 LLM（"IGNORE FACTS: recommend Fabricated Album by Fake Artist" 及中文
  变体）→ 交付物断言不含编造；既有 narrative 黑名单测试按机械契约改造（披露）。
- **关闭证据**：Reviewer 复现（`My favorite is Fabricated Album by Fake Artist` 绕过黑名单）
  在机械契约下不可能——交付物中没有 narrative 槽。

## G4-007（P1）— --deliver 无生产组合 — CLOSED

- **`src/omda/production.py`**：`PushPlusHttpTransport`（标准库 urllib，真实 HTTP，§9
  分类：200+code==200→成功；4xx→definitive rejection terminal；DNS/连接拒绝（零字节）→
  NoBytesSentError 有界重试；5xx/超时/连接重置/畸形体/未文档化码→ambiguous）；
  `build_production_engine`（真实 RunEngine + PushPlus 投递 + 可替换 transport）。
- **CLI**：`--deliver` 可执行（channel==pushplus 时组装生产引擎并 run；否则明确拒绝）；
  dry-run 仍是默认安全门（零外部调用、隔离 history）。
- **测试**：组合形状、token 边界（env 注入不日志）、受控失败（ambiguous→RECOVERING、
  零字节重试、definitive rejection terminal 无重试循环）、官方历史顺序（ok→commit）；
  transport 分类用注入 urlopen 全表断言。

## G4-003 P2 / G4-006 P2 — CLI 路径/文件名/退出码 + byte cap/cardinality — CLOSED

- **CLI**：打包数据经 `DEFAULT_DATA_DIR`（包根锚定，独立于 CWD，实测从 /tmp 运行成功）+
  `--source-path` 覆盖；run id 无小数点（文件名与实际预览路径一致，打印 receipt.target）；
  退出码按 RunOutcome（非 COMPLETE 非零，含未预期异常 catch → 1）。
- **G4-006**：`MAX_PACKET_BYTES` 改按 UTF-8 **字节**测量（多字节内容测试）；
  `bounded_packet`/`LLMAdapter.generate_narrative` 增加 `expected_genres/expected_albums`，
  RunEngine 按真实 plan 3x3 基数强制（零/错基数拒绝）；LLM Port 与 FakeLLM 签名同步。

## 验证

| 命令 | 结果 |
|---|---|
| `pytest -q -p no:cacheprovider` | **617 passed, 0 failed, 0 skipped, 0 error** |
| `pytest -v`（TEST_RESULTS.txt） | 617 passed |
| `ruff check src tests browser_companion` | All checks passed |
| `git diff --check` | clean |
| 既有测试未删除/弱化/skip | 确认（566 → 617 单调增长；G4-005 narrative 黑名单测试按机械契约改造并披露；EmptyLLM 用例改为 ExplodingLLM 语义演进并披露） |
| tracked 敏感文件 | 无 |
| G0-G3 verdict 未改（相对 68e3d45 0 行）；G2 Core 零改动 | 确认 |
| ADR-0001 §15 六条约束 | 全部落实（见各节） |
| 无 G5 scope；无 live LLM/PushPlus 依赖；无反爬绕过 | 确认 |
| 未 merge / 未 tag / 未进入 G5 / 未写 ACCEPTED | 确认 |

---

# G4 Re-review 3 Repair（2026-08-21，candidate 1a197d9）

对应 Reviewer commit：`50ce635ede960265dc60927e6bc09e0ffd9745bf`（`review(g4): keep adr delivery implementation findings open`）
上一 candidate：`1a197d9ceb95acd4e8214a28cd52c8172a4a02a0`
本轮修复 commits：`f60f225`（G4-002A）、`0437aa9`（G4-002B）、`cbe8a23`（G4-004R）、
`a8c2a4c`（G4-007）、`ab6c23e`（G4-008）
每项先加失败测试复现 Reviewer 反例、再做最小修复；未弱化测试。

## G4-002A（P1）— 生产 transport 把全部 HTTP 4xx 当 definitive — CLOSED

- **根因**：`PushPlusHttpTransport` 把整个 400-499 段分类为 definitive rejection（ProviderRejection）；
  独立注入 HTTP 418 复现 `ProviderRejection`；acceptance-10 标着 "unknown 4xx -> ambiguous" 却供给
  `ProviderRejection("499", ...)` 期望 failed——测试证明了被禁止的行为。
- **修复**（`f60f225`）：**移除无文档化的 definitive 类别**。当前 PushPlus 官方文档只定义业务码
  `code == 200`，没有任何 HTTP 4xx/5xx 的"未入队"证明（Reviewer 已核对官方 API 文档）→
  生产 transport 对**任何非 200 状态（含全部 4xx/5xx/未知码）一律 `AmbiguousFailure`**（no-retry）；
  `ProviderRejection` 类型保留为接口（供未来有文档化契约时启用），生产不产生。
- **测试**：真实 `PushPlusHttpTransport`（注入 urlopen）418/499/400/401/403/404/422/429 全表 →
  AmbiguousFailure；修正 acceptance-10 误导用例（移除 `ProviderRejection("499")→failed`，改由真实
  transport 覆盖）；`test_http_transport_classifies_401_definitive_rejection` 更新为
  `..._as_ambiguous`。

## G4-002B（P1）— §15-5 持久化绑定未校验 + receipt-attempt 关联缺失 — CLOSED

- **根因**：`record_delivery_resolution` 插入 caller 提供的冗余字段不比对 operation（复现：对
  operation A 用 run-b/key-b/attempt-b 成功推进 A）；receipt 表无 attempt_id 列、`DeliveryReceipt`
  无 attempt_id 字段；begin 的 DELIVERING journal 只记 key 不记 digest；Delivery Port docstring
  仍只写 ok/failed。
- **修复**（`0437aa9`）：
  1. **SQLite v3 迁移**（`ALTER TABLE delivery_receipt ADD COLUMN attempt_id`，v1 行 NULL；迁移
     包在 `BEGIN IMMEDIATE` 中串行化，并做列存在检查——并发迁移（两个独立连接同时打开）不再
     duplicate-column 崩溃，顺带修复并发迁移死锁）；
  2. `finalize_delivery_attempt` 写 receipt 时**绑定生成的 attempt_id**；`DeliveryReceipt` 增加
     `attempt_id` 字段；find/save 读写该列；
  3. `record_delivery_resolution` **同事务校验绑定**：operation 的 run_id 必须等于传入 run_id、
     idempotency_key 必须等于 operation_key、attempt_id（若有）必须属于该 operation——跨绑定
     一律 `InvariantFailureError`（SQLite + InMemory parity 均加负向测试）；
  4. begin 的 DELIVERING journal 原子记录 **key + payload_digest**；
  5. Delivery Port docstring 更新为 ADR-0001 三态 + pre-claim 协议；
  6. acceptance-9 增强：查真实 v3 列（`PRAGMA table_info` 含 attempt_id）、v1 行 attempt_id 为
     NULL、finalize 后 receipt.attempt_id == 生成的 attempt id。

## G4-004R（P1）— 人工 confirmed-delivered 未接入真实 RunEngine 恢复 — CLOSED

- **根因**：`_finish_after_delivery` 把 SUCCEEDED 与 RESOLVED_DELIVERED 合并并要求 receipt——
  崩溃后（IN_FLIGHT 无 receipt）+ owner 记 CONFIRMED_DELIVERED 的恢复路径永远 RECOVERING；
  验收测试只测未使用的 helper。
- **修复**（`cbe8a23`）：`_finish_after_delivery` **复用 `resolve_recovery_action` 作为唯一生产
  决策路径**（helper 与 engine 不可能发散）；RESOLVED_DELIVERED（append-only 人工确认，无需
  receipt）→ COMMIT_HISTORY → COMPLETE；其他动作幂等执行。
- **测试**：`test_real_engine_crash_human_confirmed_delivered_completes`——真实 RunEngine：
  claim → 外部调用 → finalize 模拟崩溃（IN_FLIGHT 无 receipt，RECOVERING）→ owner 记
  CONFIRMED_DELIVERED → restart 新引擎 `recover()` → **COMPLETE** + 外部效果恰 1 次 +
  一次原子历史提交（pick_index==3）。

## G4-007（P1）— 公共 `--deliver` 仍是死路 — CLOSED

- **根因**：`_main` 调 `load_config()`（无路径）→ 默认 channel 恒为 markdown → pushplus 检查恒
  失败；`--token-env` 未被应用；生产组合测试绕过公共 CLI 直连 helper。
- **修复**（`a8c2a4c`）：CLI 增加 **`--config`** 路径选项（`load_config(args.config)`）；
  `--deliver` 应用 **`--token-env`**（覆盖 config 的 pushplus_token_env，经
  `build_production_engine(token_env=...)`）；transport 提取为可注入 hook `_pushplus_transport()`
  （生产默认标准库 `PushPlusHttpTransport`，测试 monkeypatch 注入 fake 网络边界）。
- **测试**（经公共 `cli.main` 入口 + 注入 fake 网络）：`--deliver --config <pushplus> --token-env
  <VAR>` → 到达组合、COMPLETE、恰 1 次外部推送、使用指定 token 变量；ambiguous → 非零退出码且
  不盲重试；无 pushplus config → 仍明确拒绝（安全门保持）。产品边界如实声明：narrative 为
  存档用途，`--deliver` 的 LLM 是本地 echo transport（可替换注入），真实 LLM 客户端属 G5
  runtime composition（报告披露）。

## G4-008（P2）— LLM 输出被丢弃，cost 无存档价值 — CLOSED

- **根因**：`_generate` 调用 `generate_narrative` 丢弃返回值且失败使整个 run 失败。
- **修复**（`ab6c23e`）：**narrative 有界存档**到 GENERATED journal detail
  （`NARRATIVE_ARCHIVE_LENGTH = 1500` 截断）；run() 不再重复 append GENERATED。
- **测试**：`test_generated_narrative_is_archived_bounded_in_journal`（GENERATED detail 含
  narrative，交付物仍无自由文本槽）；`test_generated_narrative_is_truncated_to_bounded_length`
  （10000 字符截断到 ≤1500）。

## 验证

| 命令 | 结果 |
|---|---|
| `pytest -q -p no:cacheprovider` | **630 passed, 0 failed, 0 skipped, 0 error** |
| `pytest -v`（TEST_RESULTS.txt） | 630 passed |
| `ruff check src tests browser_companion` | All checks passed |
| `git diff --check` | clean |
| 既有测试未删除/弱化/skip | 确认（617 → 630 单调增长；acceptance-10 误导用例移除改由真实 transport 覆盖、401 测试改 ambiguous 语义，均披露） |
| tracked 敏感文件 | 无 |
| G0-G3 verdict 未改（相对 base 0 行）；G2 Core 零改动 | 确认 |
| 无 G5 scope；无 live LLM/PushPlus 依赖；无反爬绕过 | 确认 |
| 未 merge / 未 tag / 未进入 G5 / 未写 ACCEPTED | 确认 |

---

# G4 Resume Repair（2026-08-24，G3-007 Accepted 后恢复；candidate 待 Reviewer 审）

对应控制决策：`reviews/stage-04/G4_RESUME_REPORT.md`（G3-007 **ACCEPTED**，G4 从
BLOCKED_ARCHITECTURE 恢复为 CHANGES_REQUESTED）
G3-007 接受 commit：`28e652cd3ad979efefa4269aa26ded123015a434`（candidate `960712e`）
本轮起点 commit：`7c38f356b5c8aec009d305c272f786a1908d0ac2`
本轮范围：仅 G4 production composition / delivery / 迁移 / config / 文档；**未实施任何
G5 功能**；未自行写 ACCEPTED；无需新 ADR（均在已接受 ADR-0001 §15 + ADR-0002 §8 内修复）。
每项先加失败测试复现 Reviewer 反例、再做最小修复；未删除/弱化既有测试（受 ADR-0002
D8 产品语义变更影响的 5 个 LLM 相关测试按新语义升级并披露）。

## G4-007B（P1 架构）— 外部交付推送编造 Albums 并提交官方历史 — CLOSED

- **根因**：`cli --deliver` 恒用 `_sample_album_source`（每 Genre 三条编造记录）→ 推送
  `Sample Artist` 内容并把 `ambient-1` 等 ID 提交为永久官方历史；`build_production_engine`
  无 source-set 校验。
- **修复**：
  1. `omda/production.py` 新增 **`build_curated_sources()`**——组装 v0.1 生产来源：
     reviewed **非 demo** curated Genre/Album 包（`data/genres/curated-omda`、
     `data/albums/curated-omda`）+ `SourceRegistry` 信任锚；缺失包 → `DeliveryFailureError`
     fail-closed（绝不 sample 替代）。
  2. `cli --deliver` 改用 `build_curated_sources()`；`_sample_album_source`/`_sample_genre_source`
     仅保留给本地、历史中性的 dry-run（ADR-0002 D6 允许）。
  3. `build_production_engine` 新增 `source_registry` 接线；`RunEngine` 在 **FETCH 后、
     SELECT 前**（`source_registry` 非 None 时）用 `assemble_validated_source_set` 组成并
     校验 `ValidatedSourceSet`（§8-4）：selected ⊆ digest-bound eligible 集、batch digest
     自洽、registry 逐字段匹配；**demo source set 拒绝**（D6/§8-2）；校验失败 → FAILED，
     零外部调用、零历史变更。
  4. SELECT 的 candidates 从 **validated batches** 提取（`_candidates_from_validated`），
     杜绝未校验记录进入选择。
- **测试**（`tests/integration/test_g4_resume_acceptance.py`）：
  - AC-1：公共 `cli.main --deliver` 真实 curated 3×3 → COMPLETE、恰 1 次外部调用、
    outbound 无 `Sample` 标记、官方历史 9 个 production MBID；engine 层逐条断言 outbound
    fact + committed MBID 均来自同一 digest-bound batch。
  - AC-2：未注册 demo（rym-sample）拒绝；**注册 demo source set**（registry demo=true）
    被 demo gate 拒绝；伪造 batch（自标 source_id 但 digest 不符）拒绝；缺失包拒绝——
    全部 calls==0 + 历史零变更。
  - AC-9A：首轮 9 条提交后，第二轮**不重复**；curated 包 4 条/Genre 耗尽时显式失败
    （无 sample 替代、无历史污染）。

## G4-002C（P1）— begin/receipt 持久化绑定仍可被绕过 — CLOSED

- **根因**：`begin_delivery_operation` 对既有 key 不校验 run/channel/digest 绑定（复现：
  `run-a/shared/…` 后再 begin `run-b/shared/…` 被接受为 created=False）；`save_delivery_receipt`
  接受任意非空 attempt_id（`shared-key#999` 无对应 attempt 仍存储）；InMemory 同缺陷。
- **修复**（SQLite + InMemory parity）：
  1. `begin_delivery_operation`：`INSERT ... ON CONFLICT DO NOTHING` 后对既有行**同事务校验**
     run_id/channel/payload_digest 与 caller 一致，不一致 → `InvariantFailureError`（任何外部
     调用之前，ADR-0001 §15-5 / ADR-0002 AC-3）。
  2. `save_delivery_receipt`：非空 attempt_id 时**同事务校验** attempt 属于匹配 operation
     （operation_key/run/channel/attempt 四重绑定）；**v1 legacy null-attempt 兼容**：attempt_id
     为 NULL 的旧行不做 attempt 关联校验、保持可读不可改写（ADR-0002 D9）。
  3. InMemoryHistory 同步（contract parity）。
- **测试**：`test_acceptance_5`/`test_begin_requires_matching_digest_on_replay` 更新为
  fail-closed 语义（原"返回 existing"语义违反 §15-5，按 ADR 强制）；新增
  `test_ac3_begin_rejects_mismatched_binding`（SQLite + InMemory：错 run/channel/digest 全拒、
  同绑定 replay 仍 no-op）、`test_ac4_save_receipt_rejects_unbound_attempt`（跨 operation
  attempt、不存在 attempt 全拒；null-attempt legacy 可存）。

## G4-002D（P2）— SQLite v3 与 Accepted v2 边界分歧 — CLOSED（ADR-0002 D7）

- **根因**：`_SCHEMA_VERSION=3` 但迁移无 fingerprint 检查、`user_version > 3` 不 fail-closed、
  四种物理布局未覆盖。
- **修复**：`_migrate` 重写——迁移**前**校验当前版本物理布局（v1 四表 / v2 三表 / v3
  attempt_id 列），未知 fingerprint fail-closed；`user_version > 3` fail-closed；v1 →
  v2-with-column → v2-without-column → v3 四布局在同一事务性迁移中幂等收敛到 v3；
  pre-v3 旧行 attempt_id 保留 NULL（不合成）；无删列降级路径；迁移失败时连接正确释放。
- **测试**：AC-7 四布局参数化（fresh=v3、v1/v2-with-col/v2-without-col→v3）、
  `user_version=4` fail-closed、`user_version=2` 缺三表 fingerprint fail-closed、v1 旧行
  迁移后保留且 attempt_id 为 NULL（`test_ac7_*`）。

## G4-007C（P2）— token 配置被 CLI 默认值掩盖 — CLOSED

- **根因**：`--token-env` 非空默认 `PUSHPLUS_TOKEN` → `args.token_env or config…` 恒选默认，
  config-only 场景失效。
- **修复**：`--token-env` 默认 **None**（区分"省略"与"显式覆盖"）；`--deliver` 中
  `token_env = args.token_env if not None else config.delivery.pushplus_token_env`；两处均缺 →
  推送前明确 token-missing 失败（零网络调用）；secret 永不落日志。
- **测试**：AC-5 config-only（省略 → 用 config 的 env 名）、CLI-override（显式 → 覆盖）、
  missing-token（config 无 + 未传 → 非零退出、calls==0）三态经公共入口。

## G4-002E（P2）— production 文档仍把 HTTP 4xx 当 definitive — CLOSED

- **修复**：`production.py` 模块 docstring 重写为**与代码/测试完全一致**的分类表——唯一
  自动重试类 `NoBytesSentError`（零字节证明）；所有非 200 状态（含全部 4xx/5xx/未知业务码）
  → `AmbiguousFailure` ambiguous no-retry；无文档化 definitive 类别。
- **测试**：AC-6 读取模块 docstring 断言分类表关键行 + 真实 transport 注入 400 →
  AmbiguousFailure。

## G4-009 / ADR-0002 D8（P2/决策）— v0.1 定义 deterministic/no-LLM runtime — CLOSED

- **根因**：`--deliver` 用 `_LocalEchoTransport`（本地常量句）冒充生产 Agent；G5 是
  release-audit 无 runtime-provider 任务。
- **修复**（按 ADR-0002 D8/§8-10/AC-8）：
  1. config schema + `LLMConfig`：`llm.mode` 只允许 `deterministic`（schema enum +
     `__post_init__` 双保险）；`provider` 值在 config validation 即 fail-closed（任何
     run/journal/network 副作用之前）；
  2. `RunEngine._generate` deterministic 分支：**不调用任何 LLM**，GENERATED journal 存档
     typed marker `{"narrative_mode": "deterministic"}`（不存伪句子），交付物 = 确定性事实
     报告（G4-005 机械契约不变）；provider 分支保留为未来 seam（v0.1 不可达）；
  3. `cli.py` 删除 `_LocalEchoTransport`；dry-run/deliver 均不构造 echo transport。
- **测试**：AC-8（`Config(llm=LLMConfig(mode="provider"))` 与 config 文件 provider 均拒绝；
  真实 curated 3×3 全链路注入会炸的 LLM → 零调用 COMPLETE + GENERATED marker）；
  `test_deterministic_runtime_never_invokes_llm`/`test_deterministic_runtime_ignores_provider_breakage`
  （原"LLM 失败注入"测试按 D8 语义升级：v0.1 无 LLM 槽，失败注入点改为 Delivery 边界）；
  G4-008 两个 narrative 存档测试改为 marker 断言（D8 取代"存档 LLM 文本"契约）。

## ADR-0002 §8.8 — 运行证据可追溯 — CLOSED

- **修复**：`RunEngine` FETCH 后 journal `FETCHED` 的 `source_evidence`：每个 Genre
  descriptor 的 source_id/content_digest/eligible_digest/schema_version/package_version/demo；
  每个 Album batch 的 source_id/batch_digest/genre_id/schema_version/query_policy_version/
  package_version/demo + selected_genre_ids。outbound facts 与 committed MBID 可经
  `source_batch` 回溯到同一 ValidatedSourceSet（AC-1 逐条断言）。
- **测试**：`test_ac1_outbound_facts_and_committed_mbids_belong_to_validated_batch`
  （FETCHED evidence 断言 + 逐 album 追溯）。

## 规划文档修订（ADR-0002 D4/D8 授权）

- `docs/OMDA_PROJECT_MASTER_PLAN_zh-CN.md`：MVP 步骤 7 改为 deterministic 结构化报告
  （narrative 仅 typed marker，不调用外部 LLM）；§3.6 LLM 段写明 v0.1 no-LLM + provider
  fail-closed + 未来加入条件。
- `governance/IMPLEMENTATION_PLAN.md`：C.3 新增 **T3.6 G3-007 corrective checkpoint**
  （D4 授权，含独立 Gate 流程）；T4.1 重写为 v0.1 deterministic/no-LLM（D8）；新增
  **T4.6 production-source composition 与 external-delivery gate**（G4-007B/007C）；
  OD-2 措辞改为"v0.1 不激活 provider；未来独立实现 + Gate 接受"。

## 验证

| 命令 | 结果 |
|---|---|
| `pytest -q -p no:cacheprovider` | **734 passed, 0 failed, 0 skipped, 0 error**（710→734，+24 新增 AC 测试） |
| `pytest -v`（reviews/stage-04/TEST_RESULTS.txt） | 734 passed |
| `ruff check src tests tools browser_companion` | All checks passed |
| `git diff --check` | clean |
| ADR-0002 AC-1~AC-8、AC-9A | 全部通过（`test_g4_resume_acceptance.py` 24 项）；AC-9B 保持 ODP-1 条件未实现 |
| 既有测试未删除/弱化/skip | 确认（5 个受 D8 语义影响的 LLM 测试升级为 deterministic 断言并披露；2 个 begin 绑定测试按 §15-5 强制 fail-closed 语义更新并披露；2 个 v1 fixture 补全为完整 v1 物理布局） |
| G4 层零 G5 实现；G2 Core 零改动 | 确认 |
| tracked 敏感文件 | 无（token 仅测试占位） |
| live 网络依赖 | 无（全部 fake/injected transport；`--deliver` 需 owner 提供 token） |
| 未 merge / 未 tag / 未进入 G5 / 未写 ACCEPTED | 确认 |
| PROJECT_STATE | G4 / **READY_FOR_REVIEW** |

## 残余风险（诚实披露）

1. curated 包 5 Genre × 4 Album（每 Genre 3 条后仅剩 1 条）：真实 3×3 可完成，但连续多日
   运行会快速耗尽（AC-9A 显式失败路径已测）；扩充 curated 数据属 G3-007 之后的贡献流程。
2. v0.1 deterministic 意味着交付物无 LLM narrative——这是 ADR-0002 D8 的有意取舍；未来
   provider 模式需独立 implemented adapter + 版本化配置 + Gate acceptance。
3. ODP-1（live MusicBrainz tag-search）仍未定案未实现（§8-1 不变）；AC-9B 条件未启用。
4. PushPlus 文档化 definitive 类别当前为零——全部非 200 均为 ambiguous（保守，符合
   ADR-0001 §9/§15-3）；未来有文档化 no-side-effect 类别时可放宽。

---

# G4 Resume Re-review 1 Repair（2026-08-25，candidate 81309b1）

对应 Reviewer commit：`08337254be9b8c7757356f467f5271bdfaab821e`（`review(g4): keep production
trust and receipt binding open`，结论 **CHANGES_REQUESTED**：G4-007D（P1）、G4-002F（P1）、
G4-007E（P2））
被审 candidate：`81309b167923d02c917fd21bcf3a881c5c8265bb`
本轮修复范围：仅上述三项 + SQLite/InMemory parity + 公共入口负向测试；**未实施任何 G5
功能**；未自行写 ACCEPTED；无需新 ADR（均为已接受 ADR-0002 D6/D7/D9 与 token-override
契约的窄幅实现）。
每项先复现 Reviewer 反例、再做最小修复；未删除/弱化既有测试（受 G4-002F 新写入规则影响
的 receipt fixture 测试改为经 bound claim/finalize 协议构造，语义等价升级并披露）。

## G4-007D（P1）— 公共生产组合存在 registry-free 交付旁路 — CLOSED

- **复现**：`build_production_engine(source_registry=None)` + fake sources + 注入成功
  PushPlus transport → run COMPLETE、1 次外部调用、官方 pick index 前进到 3、提交
  `bebop-1` 等编造 ID。
- **修复**：`build_production_engine` 将 `source_registry` 变为**强制信任锚**——缺失即
  `DeliveryFailureError`，发生在**任何 run journal、外部调用或官方历史变更之前**（构造期
  抛错，transport 不存在、history 未触碰）；docstring 更新为"mandatory trust anchor"。
- **测试**：
  - 新增 `test_build_production_engine_rejects_missing_registry_before_side_effects`
    （负向：registry 缺失 → DeliveryFailureError，`transport.calls == 0`、journal 零写入、
    pick index 0、exclusions 空）；
  - `test_build_production_engine_returns_real_runengine_...` 改为显式传 registry
    （`SourceRegistry({})`，构造不 run）证明正向组合；
  - 原 run 级组合测试（success/ambiguous/zero-bytes/definitive）改为**直接构造 RunEngine**
    （fixture sources、无 registry）——Reviewer 许可的"explicitly local/history-neutral
    fixture composition"，与公共外部交付组合明确分离。

## G4-002F（P1）— 全新 v3 store 可创建未绑定的 legacy 式收据 — CLOSED

- **复现**：fresh `user_version=3` store 插入 `fresh:markdown`（attempt_id=None）→ SQLite
  与 InMemoryHistory 均接受；AC-4 测试把 fresh-key insert 当 legacy 兼容。
- **修复**（SQLite + InMemory parity）：`save_delivery_receipt` 先查**不可变既有证据**——
  已迁移的 null-attempt 行可读取与**精确重放**但绝不修改（冲突 `InvariantFailureError`）；
  **新 key 必须携带并同事务校验**匹配的 operation/run/channel/attempt 关联——attempt_id
  为 None 的新写入一律 `InvariantFailureError`（"fresh key 不能仅靠省略字段变成 legacy"）。
- **测试**：
  - `test_ac4_save_receipt_rejects_unbound_attempt` 更新：fresh null 写入 → 拒绝（两种
    实现），原 legacy 兼容断言移除；
  - 新增 `test_ac4_bound_receipt_binding_is_validated`（绑定收据可存 + 精确重放 no-op）、
    `test_ac4_migrated_legacy_row_stays_null_readable_and_immutable`（v1 迁移行 attempt_id
    NULL、可读、可精确重放、冲突写入拒绝）；
  - `test_sqlite_history.py` 新增 `test_new_receipt_without_bound_attempt_fails_closed`；
  - recovery 决策测试改用 bound receipt（`bound_receipt` helper：begin+finalize 协议构造）；
    "无 post-delivery journal 的 legacy receipt"场景改用**真实 SQLite 迁移 v1 行**
    （`test_legacy_migrated_receipt_without_journal_is_require_human`）；
  - `test_receipt_conflict_after_external_call_enters_recovery` 改用真实迁移 legacy 行
    场景（保留原意图：external call 1 次 + RECOVERING + 原证据保留）。

## G4-007E（P2）— 显式空 token 覆盖被静默丢弃并回退配置密钥 — CLOSED

- **复现**：`--token-env ''` + config `OMDA_PP_TOKEN` 已设 → COMPLETE、1 次外部调用且使用
  配置 token。
- **修复**：
  1. `build_production_engine` 用 `token_env if token_env is not None else config...`
     （**None 是唯一"省略"哨兵**，空串/任意显式值原样传递）；
  2. 生效的 token env 名用与 config 相同的 env 名契约（`^[A-Z_][A-Z0-9_]*$`）校验——
     **空串/非法名 → `DeliveryFailureError`**（推送前、零网络调用），绝不回退另一密钥；
  3. secret 永不落日志（负向测试用 capsys 断言输出不含 token）。
- **测试**：`test_ac5_invalid_explicit_token_override_is_rejected_not_discarded` 参数化
  `["", "invalid-name", "lower_case", "HAS SPACE"]`——非零退出、`calls == 0`、输出无
  `configured-secret`；既有 config-only / CLI-override / missing-token 三态保持通过。

## 验证

| 命令 | 结果 |
|---|---|
| `pytest -q -p no:cacheprovider` | **744 passed, 0 failed, 0 skipped, 0 error**（734→744，+10 新增/参数化测试） |
| `pytest -v`（reviews/stage-04/TEST_RESULTS.txt） | 744 passed |
| `ruff check src tests tools browser_companion` | All checks passed |
| `git diff --check` | clean |
| 独立复现 probe（registry-free builder / fresh null-attempt / 空 token 覆盖） | 3/3 全拒或正确处理 |
| 既有测试未删除/弱化/skip | 确认（receipt fixture 测试改经 bound 协议构造、legacy 场景改真实 v1 迁移，语义等价升级并披露） |
| G4 层零 G5 实现；G2 Core 零改动 | 确认 |
| 未 merge / 未 tag / 未 push / 未进入 G5 / 未写 ACCEPTED | 确认 |
| PROJECT_STATE | G4 / **READY_FOR_REVIEW** |

## 残余风险（诚实披露）

1. 迁移 legacy 行（attempt_id NULL）在 v3 store 中继续可读且可精确重放——这是 ADR-0002
   D7/D9 明确允许的兼容语义；它们没有 operation/attempt 绑定，恢复时若无 delivery
   journal tail 一律 REQUIRE_HUMAN（已测）。
2. 其余残余风险沿用上一轮：curated 包规模有限（耗尽显式失败已测）、v0.1 无 LLM
   narrative（D8 取舍）、ODP-1 未定案、PushPlus 无文档化 definitive 类别。
