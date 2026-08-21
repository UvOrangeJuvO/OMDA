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
