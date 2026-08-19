# Gate G0 Repair Report

> 作者：DeepSeek V4 Flash（Executor）
> 日期：2026-08-19
> 依据：`reviews/stage-00/REVIEW_VERDICT.md`（GPT-5.6 Sol，CHANGES_REQUESTED）
> 原始 Base：`8a2e82072afca8fe7217c9fc79288d99a94e01ce`
> 原始 Candidate：`488860b497f3a179a12ce38082d337b48dda6e2f`
> 修复后新 Candidate：提交后由 Executor 在最终聊天报告中给出精确 SHA（`PROJECT_STATE.json` 的 `candidate_commit` 保持 `null`，避免自引用提交）
> 本轮未写 production code，未进入 G1；`REVIEW_VERDICT.md` 未被修改。

## 修复摘要

| Finding | 严重度 | 状态 | 修改文件 |
|---|---|---|---|
| G0-001 Port 契约时序错误 | P1 | CLOSED | IMPLEMENTATION_PLAN.md |
| G0-002 Core 读存储 / var/ 可重置 | P1 | CLOSED | IMPLEMENTATION_PLAN.md |
| G0-003 .workbuddy/ 无仓库策略 | P2 | CLOSED | .gitignore、REPAIR_REPORT.md |
| G0-004 风险引用与优先级不一致 | P2 | CLOSED | IMPLEMENTATION_PLAN.md |
| G0-005 Open Decisions 治理过载 | P2 | CLOSED | IMPLEMENTATION_PLAN.md |

---

## G0-001 — Port contracts are scheduled after the Orchestrator that requires them（P1）

- **根因**：G2/T2.6 需实现完整状态机（含 GENERATE/DELIVER/journal/history），但六个 Port 契约与领域错误分类要到 G3/T3.1 才定义；G2 会出现直接依赖具体存储或自造临时接口的返工风险。
- **修改**：
  1. `B.3` 增加时序声明：最小 Port protocols 与领域错误分类在 G1 末尾（T1.6）定义，先于 Orchestrator；G3 不是应用边界首次出现点。
  2. `C.1` 新增 `T1.6 应用 Port protocols 与领域错误分类`（六 Port：GenreSource / AlbumSource-Enricher / CriticRatingSource / HistoryPort / LLM / Delivery；SPEC §8 错误分类；fake/in-memory 测试实现）。
  3. `C.2/T2.6` 明确：本任务全程针对 T1.6 契约使用 fake/in-memory 实现（fake LLM、fake Delivery、in-memory journal/history），覆盖 GENERATE、DELIVER、journal、history 迁移；具体外部 Adapter 在 G3/G4，不阻塞 G2。
  4. `C.3/T3.1` 改为「具体外部 Adapter 实现（基于 G1/T1.6 既有契约）」，不再首次定义接口。
  5. `B.9`/`D.5` 依赖方向与契约测试相应更新。
- **验收证据**：依赖图已无「G2 任务依赖 G3 才首次出现的契约」；T2.6 明示 fakes 测试路径（见修订后 C.2）。
- **状态**：**CLOSED**。

## G0-002 — The pure Recommendation Core is described as reading runtime history/storage（P1）

- **根因**：T2.4 依赖写成 `T1.4（history 读取）`，暗示 Core 读存储；T2.6 rollback 出现「`var/` 运行时数据可重置」，把真实历史当作可删数据。
- **修改**：
  1. `B.1`/`B.9` 强化 Core 纯净性：**Core 无任何 persistence import/call（不得导入/调用 SQLite、HistoryStore 或文件读写）**；历史 exclusion set 由 Orchestrator/History Port 读取后以不可变领域输入传入 Core。
  2. `T2.4` 依赖改为 `T1.6（HistoryPort 契约：Orchestrator 读取版本化历史快照/exclusion set 后作为领域输入传入）`；Deliverables/Tests 增加「以历史 exclusion set 作为参数输入的单元测试」。
  3. `T2.6` rollback 删除「var/ 可重置」，改为：真实运行时数据（官方 history、delivery/recovery 证据）受保护，回滚仅限备份、迁移、恢复或非破坏性补偿；**只有 disposable test database 可重建**。
  4. `B.5` 新增数据保护边界段落。
  5. `D.2` 增加 exclusion set 参数测试行；`D.5` 增加架构测试「Core 无 persistence import/call」。
- **验收证据**：Core 纯净性进入架构测试与单元测试要求；B.5/T2.6 已改受保护状态规则。**第一轮疏漏更正（Re-review 1 指出）**：当时声称「计划不再包含任何『真实运行时历史可删除/重置』表述」并不属实——**T1.4（存储抽象）的 rollback 仍残留 `var/ 可删可重建（非真源）`**，第一轮漏掉了该行。该行已在本轮（Second repair）真正删除并替换为受保护状态规则（见下方 Second repair 部分）。故第一轮对本 Finding 的结论应为 **PARTIAL，非 CLOSED**。
- **状态**：**PARTIAL（第一轮）→ CLOSED（第二轮，见下）**。

## G0-003 — Current handoff worktree is not clean and WorkBuddy memory has no repository policy（P2）

- **根因**：评审时 `git status --short` 显示 `?? .workbuddy/`（含 Executor 生成的 `memory/2026-08-19.md`），且仓库无该目录策略；最终 handoff 声称「干净」与实际状态不一致。
- **修改**：
  1. `.gitignore` 新增 `.workbuddy/`（第 4 行）。
  2. **未删除** `.workbuddy/` 目录（按评审要求，不以删除掩盖状态）；策略为当前本地工作流忽略该目录，除非 Owner 日后决定版本化部分 WorkBuddy 配置（届时走 ADR/显式决策）。
  3. 本报告披露被观察到的未跟踪文件。
- **验收证据**：`git check-ignore -v .workbuddy/memory/2026-08-19.md` → `.gitignore:4:.workbuddy/`；修复提交后 `git status --short` 为空（见提交后核验）。
- **状态**：**CLOSED**。

## G0-004 — Risk references and priorities are internally inconsistent（P2）

- **根因**：计划 E 摘要把 R-010 列为 P2，而 RISK_REGISTER 权威表为 P1；OD-4 引用 R-012（时区风险）承载 MusicBrainz 许可/限流问题。
- **修改**：
  1. 计划 E 中 R-010 优先级修正为 **P1**，并注明「与 RISK_REGISTER 一致」。
  2. OD-4 引用修正为 **R-006（许可）与 R-005（外部网络/限流行为）**，删除错误的 R-012 引用。
  3. RISK_REGISTER.md 无需改动（其本身已是权威且正确；逐项复核：R-001 P0、R-002 P0、R-003 P1、R-004 P1、R-005 P1、R-006 P1、R-007 P2、R-008 P1、R-009 P0、R-010 P1、R-011 P2、R-012 P2、R-013 P2）。
- **验收证据**：计划中出现的每个风险 ID（R-001…R-013）与 RISK_REGISTER 的优先级、主题一致。
- **状态**：**CLOSED**。

## G0-005 — The plan turns ordinary implementation defaults into ten Owner/ADR blockers（P2）

- **根因**：原规则「任一 OD 实现前提是 Owner 确认或 ADR 定案」，把 Python 版本、env 注入、dry-run 默认输出、统计技术等普通可逆工程选择也变成治理阻塞。
- **修改**：`G` 节重写为三分类：
  - **(a) Owner 产品决策**：OD-7（数据范围）、OD-8（许可证）、OD-5/OD-6 的语义部分。
  - **(b) 架构/契约决策（改变已接受契约才需 ADR）**：OD-4（canonical 来源）、OD-10（RYM 页面预算边界）。
  - **(c) 可逆工程选择（Executor 提出，Reviewer 在对应 Gate 评审，无需 Owner/ADR）**：OD-1（Python）、OD-2（LLM provider）、OD-3（token 注入）、OD-9（统计判据）、OD-5/OD-6 的工程部分。
  - 每项含「决策机制 / 最近决策 Gate」与建议默认。
- **验收证据**：普通可逆项不再自动要求 Owner 介入或 ADR；Owner 保留对许可、数据范围与产品语义的控制。
- **状态**：**CLOSED**。

---

## 实际运行检查

| 命令 | 结果 |
|---|---|
| `git branch --show-current` | `exec/g0-plan` |
| `git log --oneline -5` | `13c57f4 review(g0): request implementation plan changes`（HEAD 含 Reviewer commit）等 |
| `git rev-parse HEAD` | `13c57f433a3fdff626c3497d9ce5784f8490f358` |
| `git status --short`（修复前） | `?? .workbuddy/`（已披露） |
| `git check-ignore -v .workbuddy/memory/2026-08-19.md` | `.gitignore:4:.workbuddy/` |
| `git diff --check`（提交前） | 通过（无 whitespace 错误） |
| `git status --short`（提交后） | 空（干净，见提交后核验） |

## 修复范围声明

仅修改允许范围：`governance/IMPLEMENTATION_PLAN.md`、`governance/RISK_REGISTER.md`（复核后无需改动）、`governance/PROJECT_STATE.json`（仅 updated_at）、`reviews/stage-00/REPAIR_REPORT.md`（本文件）、`.gitignore`（.workbuddy/ 策略）。未修改/删除 `REVIEW_VERDICT.md`；未写 production code；未进入 G1。

## Executor Conclusion

**READY_FOR_REVIEW**（待 GPT-5.6 Sol 对修复后新 candidate SHA 复审；verdict 仅对新 SHA 有效）

---

# Second repair / Re-review 1（2026-08-19）

对应 Reviewer commit：`63f31fb5e47b3569ee4cdeb3d1e3efea42a50087`（`review(g0): request second plan repair`）
上一候选：`7bec77f3055c9afdad0f61593e985bb1eda8acfc`
本轮 Candidate：提交后由 Executor 在最终聊天报告中给出精确 SHA（`PROJECT_STATE.json` 的 `candidate_commit` 保持 `null`，避免自引用）

## Re-review 1 状态汇总

| Finding | 严重度 | Re-review 1 判定 | 本轮结果 |
|---|---|---|---|
| G0-001 | P1 | CLOSED（原缺陷） | 维持 CLOSED；编号引用随 G1 重排同步修正 |
| G0-002 | P1 | **OPEN**（T1.4 rollback 残留） | CLOSED（见下） |
| G0-003 | P2 | CLOSED | 维持 |
| G0-004 | P2 | CLOSED | 维持 |
| G0-005 | P2 | CLOSED | 维持 |
| G0-006 | P1 | **新发现** | CLOSED（见下） |

## G0-002 真正关闭（Re-review 1）

- **根因**：第一轮修复漏掉了 T1.4（存储抽象与 SQLite runtime 层）rollback 行的 `var/ 可删可重建（非真源）`；第一轮报告声称「不再包含任何删除/重置表述」不属实。`var/` 明确承载 official pick history、Album history、delivery receipt 与 run journal，「不是社区数据真源」并不使其可废弃。
- **修改**：G1 重排后该任务为 **T1.5（SQLite runtime Adapter）**，rollback 修正为受保护状态规则——真实官方 history、run journal、delivery receipt、recovery evidence 均为受保护用户状态，**不得删除/重置**；回滚只能使用备份、迁移、恢复或非破坏性补偿；只有明确创建为测试用途的 **disposable test database** 才能重建；「不是社区数据真源」不等于「可以删除」。
- **验收证据**：全文搜索 `可删可重建`、授权性 `可重置/可删除` 表述结果为零（仅剩否定性「不得删除/重置」与历史记录文本）。
- **状态**：**CLOSED**。

## G0-006 依赖方向与 Adapter 归属（Re-review 1 新发现，P1）

三个子问题及修复：

1. **依赖方向统一**：架构图与 B.9 统一为——`Orchestrator → Recommendation Core`（调用纯规则）且 `Orchestrator → Ports`（调用契约）；`Adapters → Ports`（实现契约）；**Core 不调用 GenreSource、HistoryPort、LLM、Delivery 或其他外部 Port**，只接收/返回领域值，零 persistence / vendor / network / 文件读写依赖（B.1/B.9/D.5 架构测试强制）。
2. **G1 先契约后实现**：G1 重新编号——**T1.4 应用 Port protocols 与领域错误分类**（先于任何具体实现）；**T1.5 SQLite runtime Adapter** 显式实现 History/Journal 相关 Port（依赖 T1.4，不允许先写具体 SQLite abstraction 再反向适配 Port）；T1.6 测试基建与 fixtures。全文档 T1.x 引用已同步修正（T2.1/T2.4/T2.6/T3.1/T4.1/T4.3 等，见 grep 验证）。
3. **G3/G4 Adapter 归属去重**：T3.1 只实现**数据/来源类**（文本数据集、MusicBrainz/community enrichment、critic 数据、Browser Companion/RYM，以及数据来源的缓存、provenance 与错误映射）；**LLM Provider、Markdown output、PushPlus Delivery 实现独占 G4**（T4.1–T4.3）。每个具体 Adapter 只有唯一实现 Gate；T3.1 已删除对 LLM/Markdown/PushPlus 的实现声称。

- **状态**：**CLOSED**。

## 第二轮实际运行检查

| 命令 | 结果 |
|---|---|
| `git branch --show-current` | `exec/g0-plan` |
| `git rev-parse HEAD`（开始时） | `63f31fb5e47b3569ee4cdeb3d1e3efea42a50087`（含 Reviewer commit） |
| `git status --short`（开始时） | 空（干净） |
| grep `可删可重建\|可重置\|可删除`（授权性表述） | 零命中（仅否定性与历史记录） |
| 全文档 T1.x/T2.x/T3.x/T4.x 引用核对 | 与新编号一致（见 IMPLEMENTATION_PLAN.md） |
| `git diff --check`（提交前） | 通过（无 whitespace 错误） |
| `git status --short`（提交后） | 空（干净） |

## 修复范围声明（第二轮）

仅修改允许范围：`governance/IMPLEMENTATION_PLAN.md`、`reviews/stage-00/REPAIR_REPORT.md`（本文件：新增本节 + 更正第一轮 G0-002 结论）、`governance/PROJECT_STATE.json`（仅 updated_at）。`RISK_REGISTER.md` 复核后无真实引用错误，未改动。未修改/删除 `REVIEW_VERDICT.md`；未写 production code；未进入 G1。

## Executor Conclusion（第二轮）

**READY_FOR_REVIEW**（待 GPT-5.6 Sol 对本轮新 candidate SHA 复审；verdict 仅对新 SHA 有效）
