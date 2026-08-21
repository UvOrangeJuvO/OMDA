# G4 Executor Report — Agent & Delivery

- **Gate**：G4 Agent & Delivery（SPEC §10；MP §10；IMPLEMENTATION_PLAN C.4）
- **Executor**：DeepSeek V4 Flash
- **Branch**：`exec/g4-agent-delivery`
- **Base 完整 SHA**：`68e3d453c7b803d2090cb1318f48e58eb18d6390`（main == gate-g3-accepted）
- **启动 HEAD**：`3fb74b5fb29256f5f884cf3ba3a0c318a68b8d6d`（核对通过）
- **Candidate 完整 SHA**：见 handoff commit（`docs(g4): propose agent and delivery review package`）

## 1. 开始前只读核对

| 项 | 结果 |
|---|---|
| 仓库路径 | `<REPO_ROOT>` |
| 当前分支 | `exec/g4-agent-delivery`（符合） |
| 启动 HEAD == `3fb74b5f...` | YES |
| G4 base == main == gate-g3-accepted == `68e3d453...` | 全部一致 |
| `git status --short` | 空（干净） |
| PROJECT_STATE | G4 / IN_PROGRESS，base_commit = `68e3d453...` |
| G3 最终 verdict | **ACCEPTED**（candidate `d201c164...`） |
| AGENTS.md + 两份最高规范 + IMPLEMENTATION_PLAN C.4 + ADR（无 Accepted 正文） | 已完整阅读 |
| G3 基线测试 | 497 passed + Ruff 全绿 |

## 2. Atomic Tasks 与提交

| Task | 提交 | 内容与验收 |
|---|---|---|
| 治理 | `4e95543` | stage-04 骨架；PROJECT_STATE 保持 G4/IN_PROGRESS |
| T4.1 | `2c5ebed` | `omda/adapters/llm.py`：LLMAdapter（实现既有 LLM Port，transport 可注入）+ `bounded_packet`（字段长度/数量有界、递归冻结）+ 固定 `DEFAULT_SYSTEM_PROMPT`（外部文本显式标记不可信）。验收：prompt-injection 隔离（system 恒定、恶意字段只进 user 数据槽）、transport 失败映射 GenerationFailureError、**LLM 输出不改变选择结果**（流水线组合测试证明） |
| T4.2 | `2902280` | `omda/output/markdown.py`：确定性模板渲染 + `validate_markdown`（结构/长度/事实引用）。验收：空/超长/缺标题/缺 Genre 节/缺 Album 条目/编造 Genre/编造 Album 全部拒绝；**校验失败不投递**（组合测试） |
| T4.3 | `611132a` | `omda/adapters/delivery.py`：MarkdownFileDelivery（run id 派生文件名、防逃逸）+ PushPlusDelivery（token_provider 注入、有界整数 retries + 指数退避、超长拒发、收据）。验收：同一幂等键不产生第二次外部投递（receipt 权威 + calls==1 断言） |
| T4.4 | `36b7b2f` | `omda/orchestrator/recovery.py`：纯决策层（COMPLETE_ALREADY / COMMIT_HISTORY / REQUIRE_HUMAN），补偿/幂等协议文档（不虚构跨系统原子）。验收：deliver 成功 + commit 失败 → 恢复提交历史且**不盲重复投递**；证据缺失/不匹配 → 人工 |
| T4.5 | `82dbf8d` | `omda/cli.py`：`--dry-run` 默认、`--deliver` 显式开启、显式 `--dry-run` 优先。验收：**dry-run 零外部调用**（不构造 transport、不解析 token） |
| 组合测试 | `88c69d9` | LLM→render→validate→Markdown 落盘端到端；编造报告永不投递 |

## 3. 不可违反项对照

| 规则 | 证据 |
|---|---|
| LLM 只能解释，不能选择/更改 Genre/Album | T4.1 注入隔离 + `test_narrative_cannot_alter_selected_facts` + 流水线测试（narrative 含 "pick Album X" 仍不影响 plan 事实） |
| 外部数据不可信、不能覆盖系统指令 | `DEFAULT_SYSTEM_PROMPT` 恒定，packet 全部进 user 数据槽；`bounded_packet` 防超大字段注入 |
| 输出校验失败不得投递 | T4.2 全部负向测试 + `test_fabricated_report_is_never_delivered`（文件不存在） |
| 投递失败不得提交成功历史 | 继承 G2：delivery failed → FAILED，`commit_history` 仅在收据 ok 后调用（G2 已接受语义未改） |
| 同一幂等键不得产生第二次外部投递 | T4.3 `test_same_idempotency_key_does_not_cause_second_push`（calls==1）+ T4.4 恢复不重投 |
| dry-run 不得调用任何外部服务 | T4.5：dry-run 不构造 transport、不解析 token、无网络路径 |
| 不得使用/提交真实 key/token/cookie/浏览器资料 | 敏感扫描零命中；token 仅经 `token_provider`/环境变量注入，从不入日志/Git |
| 普通测试全 fake/fixture，零 live LLM/PushPlus | 全部测试用 ScriptedTransport / 临时目录；无真实外部调用 |
| 不修改已接受 Port/Schema/事务状态机/产品语义 | G0-G3 代码零改动（core/orchestrator-run.py/ports/storage/config/schemas 相对 base 0 文件）；`recovery.py` 为纯新增决策层 |

## 4. 验证

| 命令 | 结果 |
|---|---|
| `pytest -q -p no:cacheprovider` | **539 passed, 0 failed, 0 skipped, 0 error** |
| `pytest -v`（TEST_RESULTS.txt） | 539 passed |
| `ruff check src tests browser_companion` | All checks passed |
| `git diff --check` | clean |
| tracked 敏感文件（cookie/profile/sqlite/.env/secret/token/key/pem/pyc/cache） | 无 |
| G2/G3 verdict 未改（相对 base 0 行） | 确认 |
| G0-G3 实现代码零改动 | 确认 |
| skip/xfail | 0（无隐藏失败） |

## 5. 偏差与残余风险

- **无偏差**：五个 T4.x 均在 IMPLEMENTATION_PLAN C.4 允许范围内；未进入 G5；未写 ACCEPTED；未合并/打标签/push。
- **残余风险**：
  - R-008（注入）：已由固定 system prompt + 有界 packet + 校验缓解；真实 LLM vendor 的 transport 具体实现（HTTP/SDK）留待 G5 运行时组合，本 Gate 未引入网络依赖。
  - R-001（重复投递）：幂等由 durable receipt 权威 + adapter 有界重试缓解；PushPlus 服务端幂等键对齐属 G5 审计项。
  - R-009（虚假原子性）：T4.4 协议文档明确"外部推送与本地 SQLite 非跨系统原子"，恢复仅基于持久化证据。

## 6. Executor Conclusion

**READY_FOR_REVIEW**（待 GPT-5.6 Sol 对本 candidate SHA 复审；verdict 仅对新 SHA 有效）

---

# G4 Re-review 1 Repair（2026-08-21）

对应 Reviewer commit：`754a140562dcb36dacf77b56d1d6505996a0c490`
上一 candidate：`10275ed04a66ed50631edb0d43a3505f18d2a5b7`
本轮修复 commits：`f5f02d2`、`66c7ee4`、`460a518`、`aedff3f`、`958a32b`、`343d3ed`
详细逐项修复记录见 `reviews/stage-04/REPAIR_REPORT.md`。

## Re-review 1 finding 修复对照

| Finding | 严重度 | 修复 commit | 状态 |
|---|---|---|---|
| G4-001 生产 RunEngine 绕过渲染器与事实校验 | P1 | `f5f02d2` | CLOSED |
| G4-002 PushPlus 盲目重试歧义发送 | P1 | `66c7ee4` | CLOSED |
| G4-003 dry-run 只是选择器且污染历史 | P1 | `460a518`+`343d3ed` | CLOSED |
| G4-004 recovery 接受未绑定收据 | P1 | `aedff3f` | CLOSED |
| G4-005 Markdown 校验只查 title 前缀 | P1 | `f5f02d2` | CLOSED |
| G4-006 事实包未全字段有界 | P1 | `958a32b` | CLOSED |

## 本轮验证

| 命令 | 结果 |
|---|---|
| `pytest -q -p no:cacheprovider` | **566 passed, 0 failed, 0 skipped, 0 error** |
| `pytest -v`（TEST_RESULTS.txt） | 566 passed |
| `ruff check src tests browser_companion` | All checks passed |
| `git diff --check` | clean |
| `python -m omda.cli --dry-run` | COMPLETE + 生成预览 |
| 既有测试未删除/弱化/skip | 确认（539 → 566；2 个 G4 新增测试按新验收语义升级并披露） |
| 未 merge / 未 tag / 未进入 G5 / 未改 verdict / 未写 ACCEPTED | 确认 |

## Executor Conclusion（G4 Re-review 1 repair）

**READY_FOR_REVIEW**（待 GPT-5.6 Sol 对本轮新 candidate SHA 复审；verdict 仅对新 SHA 有效）

---

# G4 Re-review 2 — BLOCKED_ARCHITECTURE（2026-08-21）

对应 Reviewer commit：`3977d62198750df8177452330b6c55986785229b`
被审 candidate：`13a659d741e70df5e7b3faa561ffc822dd4efb5c`

## 触发

Reviewer 判定 G4-002（P1）仍开放，且明确指出：`ambiguous` 状态违反已接受的
Delivery Port / `DeliveryReceipt` / `delivery_receipt.schema.json` v1 契约；
同 key 直接重放产生第二次外部推送；provider 非成功响应被一律当"明确拒绝"
重试；并要求"stop and submit an ADR"（若现有 Port 无法安全表达交付歧义）。
Executor 按用户指令进入 **BLOCKED_ARCHITECTURE**，暂不修改 production code。

## 已提交

- **Proposed ADR**：`docs/adr/0001-delivery-receipt-ambiguity-and-idempotency.md`
  （首个正式 ADR 文件），完整覆盖 8 个设计点：
  1. attempt / confirmed failure / ambiguous / receipt 概念区分；
  2. Port 与版本化 Schema（v1→v2 enum 增项 + attempt_id）及迁移兼容方案；
  3. 同 key 直接重放 / 进程重启 / 并发调用防二次推送
     （durable intent outbox + UNIQUE 键 reserve-before-send）；
  4. provider 非成功响应分类表（仅可证明"未接受"才是明确拒绝；
     5xx/超时/响应丢失/未文档化业务码一律歧义）；
  5. durable intent / receipt 写入顺序与崩溃窗口表；
  6. 明确不宣称 PushPlus 与 SQLite 跨系统原子；
  7. rollout / rollback / 恢复语义 / 验收测试矩阵；
  8. 三方案比较（A 保持 ok/failed；B 版本化增加 ambiguous/attempt —— 推荐；
     C 无安全保证时禁用真实 PushPlus），并给出推荐理由与备选触发条件。
- **PROJECT_STATE.json**：`status=BLOCKED_ARCHITECTURE`，
  `adr_status=ADR_PENDING`，`blocking_adr` 指向 ADR 文件。

## 明确声明

- 本轮**未修改任何 production code**（`git diff 3977d62 -- src/ tests/`
  为空；仅新增 ADR + 状态 + 报告）。
- **未修复** G4-005 / G4-007（按用户指令等待 ADR 评审后统一处理）。
- 未 merge、未打 tag、**未进入 G5**、未写 ACCEPTED。
- 下一步：等待 GPT-5.6 Sol 评审本 Proposed ADR；评审通过后按 ADR 实现
  G4-002 修复（T4.3/T4.4），随后处理 G4-005/G4-007。

---

# G4 Re-review 3 — ADR-0001 REVISE → 修订 v2（2026-08-21）

对应 Reviewer commit：`a699a4955e2e925641ee979a7dd8f26b74beef5f`
评审文件：`reviews/stage-04/ADR_0001_REVIEW.md`（结论 **REVISE**，ADR-001~005）
ADR：`docs/adr/0001-delivery-receipt-ambiguity-and-idempotency.md`（保持 **Proposed**）

## 修订对照（ADR-001 ~ ADR-005）

| Finding | 修订 v2 方案 |
|---|---|
| ADR-001 REGISTERED→SENT 并发双发窗口 | **删除可恢复 REGISTERED**；外部调用前原子创建 operation 于 `IN_FLIGHT_OR_MAY_HAVE_SENT`（与 DELIVERING journal 同事务、ON CONFLICT 仅一方成功）；既有行阻止一切自动调用方；claim 后调用前崩溃 = 假歧义 → 人工（显式 availability 取舍）；不采用 lease/fencing（§4） |
| ADR-002 不可变 failed 与同 key 重试矛盾 | **DeliveryOperation（每 key 一行）与 DeliveryAttempt（append-only 不可变）分离**；failed 为 operation terminal（不覆盖不可变收据、不自动重试）；人工确认未投递后以新 generation key（`<run>:<channel>:<gen>`）开新 operation 并绑定原 run（§5） |
| ADR-003 ambiguous 无人工 resolution | 新增 **append-only `delivery_resolution`**（run/operation/key/attempt/actor/time/reason），outcome ∈ {CONFIRMED_DELIVERED → 提交历史不重推；CONFIRMED_NOT_DELIVERED → abandon/新操作；STILL_UNKNOWN → 保持阻塞}（§6） |
| ADR-004 持久化 API/事务边界未指定 | 语义级原子 Port 方法：`begin_delivery_operation`（journal+operation 同事务、网络前 commit）/ `finalize_delivery_attempt`（CAS 期望 state+version）/ `record_delivery_resolution`；payload digest=SHA-256，同 key 异 digest 网络前 fail-closed；SQLite v1→v2 DDL 草案（operation/attempt/resolution 三表 + CHECK/UNIQUE/FK 约束）、两独立连接并发行为（BEGIN IMMEDIATE + ON CONFLICT）、迁移/回滚（§7/§8） |
| ADR-005 4xx 全重试无依据 | **取消笼统 4xx 重试**；类型化 transport（ProviderSuccess / ProviderDefinitiveRejection / `NoBytesSentError` / AmbiguousFailure）；唯一自动重试类别 = `NoBytesSentError`（可证明未发送任何字节，有界）；未知响应/5xx/解析失败/写后异常/未知业务码 → ambiguous no-retry；认证/参数拒绝 = CONFIRMED_FAILED terminal 非重试循环（§9） |

## 保证边界（§10）

- OMDA 保证 **每个 delivery operation 至多一次自动外部请求**（原子 claim +
  无歧义自动重试）。
- **不宣称** provider 端 exactly-once（PushPlus 无服务端幂等键）。
- 不宣称 PushPlus 与 SQLite 跨系统原子（SPEC §4）。

## 验收（§12）

纳入 Reviewer 全部 10 项验收测试（两连接并发 race / claim-send 窗口 /
两类崩溃 / 异 digest fail-closed / 既有证据永不重发 / failed 终态基数 /
人工裁决三结果 / schema v2 + 迁移 v2 兼容 v1 / 类型化 provider 响应全表）。

## 明确声明

- 本轮**未修改任何 production code**；ADR 保持 **Proposed**（未改 Accepted）；
- 未处理 G4-005 / G4-007；未 merge、未打 tag、**未进入 G5**。
- 下一步：等待 GPT-5.6 Sol 复审修订 v2。

---

# G4 Re-review 2 Repair（2026-08-21，ADR-0001 Accepted 后恢复实现）

对应 Reviewer commit：`3977d62198750df8177452330b6c55986785229b`
ADR-0001 接受 commit：`1349a0fd53116335d372c89684d83f1d556b63ac`
上一 candidate：`13a659d741e70df5e7b3faa561ffc822dd4efb5c`
本轮修复 commits：`701c203`、`606c859`、`4db6803`、`01f4506`、`c40d619`、`694a443`
详细逐项修复记录见 `reviews/stage-04/REPAIR_REPORT.md`。

## Re-review 2 finding 修复对照

| Finding | 严重度 | 修复 commits | 状态 |
|---|---|---|---|
| G4-002 幂等/歧义/契约（ADR-0001 §15 六条） | P1 | `701c203`+`606c859`+`4db6803` | CLOSED |
| G4-005 narrative 黑名单被绕过 | P1 | `01f4506` | CLOSED（机械契约） |
| G4-007 无生产 Agent/PushPlus 组合 | P1 | `c40d619` | CLOSED |
| G4-003 P2 CLI 路径/文件名/退出码 | P2 | `c40d619` | CLOSED |
| G4-006 P2 UTF-8 byte cap / cardinality | P2 | `694a443` | CLOSED |

## 本轮验证

| 命令 | 结果 |
|---|---|
| `pytest -q -p no:cacheprovider` | **617 passed, 0 failed, 0 skipped, 0 error** |
| `pytest -v`（TEST_RESULTS.txt） | 617 passed |
| `ruff check src tests browser_companion` | All checks passed |
| `git diff --check` | clean |
| ADR §12 十项验收 | 全部通过（含两独立连接并发） |
| 既有测试未删除/弱化/skip | 确认（566 → 617；2 处语义演进已披露） |
| 未 merge / 未 tag / 未进入 G5 / 未改 verdict / 未写 ACCEPTED | 确认 |

## Executor Conclusion（G4 Re-review 2 repair）

**READY_FOR_REVIEW**（待 GPT-5.6 Sol 对本轮新 candidate SHA 复审；verdict 仅对新 SHA 有效）

---

# G4 Re-review 3 Repair（2026-08-21，candidate 1a197d9）

对应 Reviewer commit：`50ce635ede960265dc60927e6bc09e0ffd9745bf`
上一 candidate：`1a197d9ceb95acd4e8214a28cd52c8172a4a02a0`
本轮修复 commits：`f60f225`、`0437aa9`、`cbe8a23`、`a8c2a4c`、`ab6c23e`
详细逐项修复记录见 `reviews/stage-04/REPAIR_REPORT.md`。

## Re-review 3 finding 修复对照

| Finding | 严重度 | 修复 commit | 状态 |
|---|---|---|---|
| G4-002A 全部 HTTP 4xx 被当 definitive | P1 | `f60f225` | CLOSED |
| G4-002B §15-5 绑定 + receipt-attempt 关联 | P1 | `0437aa9` | CLOSED |
| G4-004R 人工 confirmed-delivered 未接入真实恢复 | P1 | `cbe8a23` | CLOSED |
| G4-007 公共 --deliver 死路 | P1 | `a8c2a4c` | CLOSED |
| G4-008 LLM 输出被丢弃 | P2 | `ab6c23e` | CLOSED |

## 本轮验证

| 命令 | 结果 |
|---|---|
| `pytest -q -p no:cacheprovider` | **630 passed, 0 failed, 0 skipped, 0 error** |
| `pytest -v`（TEST_RESULTS.txt） | 630 passed |
| `ruff check src tests browser_companion` | All checks passed |
| `git diff --check` | clean |
| 既有测试未删除/弱化/skip | 确认（617 → 630；2 处按新语义披露） |
| 未 merge / 未 tag / 未进入 G5 / 未改 verdict / 未写 ACCEPTED | 确认 |

## Executor Conclusion（G4 Re-review 3 repair）

**READY_FOR_REVIEW**（待 GPT-5.6 Sol 对本轮新 candidate SHA 复审；verdict 仅对新 SHA 有效）
