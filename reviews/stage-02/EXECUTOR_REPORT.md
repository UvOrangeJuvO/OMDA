# Gate G2 Executor Report — Recommendation Core

> 作者：DeepSeek V4 Flash（Executor）
> 日期：2026-08-19
> 依据：`.workbuddy/G2_START_PROMPT.md`；已批准 `governance/IMPLEMENTATION_PLAN.md` C.2（T2.1–T2.6）
> G2 Base（唯一）：`731e0498fecdb0a28c84cf57d55c89569895a5bf`（merge: accept gate G1 foundation，tag `gate-g1-accepted`）
> 分支：`exec/g2-core`（从合并后 main 创建）

## 1. Identity 与开始前核对

| 项 | 值 |
|---|---|
| 仓库 | `<REPO_ROOT>` |
| 分支 | `exec/g2-core` |
| G1 accepted candidate | `d280e7879fad7a4714a83c1add1e3ae60a06484c` |
| G1 verdict commit | `9f8f9446699054909b49ccdbef5891d90a9c182c` |
| G2 base（merge/main） | `731e0498fecdb0a28c84cf57d55c89569895a5bf` |
| tag `gate-g1-accepted` → | `731e0498fecdb0a28c84cf57d55c89569895a5bf` ✓ |
| PROJECT_STATE（开始前） | G1 / ACCEPTED（approved=d280e78…）✓ |
| REVIEW_LOG | G1 ACCEPTED 已记录 ✓ |
| 开始工作区 | 干净 ✓ |
| 基线测试 | 110 passed + Ruff All checks passed ✓ |
| G2 candidate | 提交后由 Executor 在最终聊天报告给出精确 SHA（`candidate_commit` 保持 null） |

已按权威顺序阅读：AGENTS.md、HANDOFF_SPEC、MASTER_PLAN、Accepted ADRs（无）、OPERATIONS_HANDBOOK、IMPLEMENTATION_PLAN（重点 C.2/D/E/F/G/H）、RISK_REGISTER、REVIEW_VERDICT 最终 ACCEPTED 部分；并复核既有 ports/config/seed/storage/fakes 与 G1 contract tests 边界。

## 2. Scope / Non-goals

**实现**：纯 Recommendation Core（`omda/core/`）、Application Orchestrator 状态机与恢复（`omda/orchestrator/`）、对应 unit/property/contract/failure-injection/crash-recovery tests、G2 领域值（Plan/FactPacket 等）。

**明确未实现**：RYM / Browser Companion / MusicBrainz / 任何真实网络抓取、LLM provider、Markdown/PushPlus 真实交付、G3/G4 数据与外部 Adapter、popularity filter / Genre tier / LLM quality score、全量预爬 / fan-out / 反爬对抗、UI / 部署 / 定时任务 / packaging。

## 3. Commits 与 Atomic Task 对照

| Commit | Message | Task / 验收 |
|---|---|---|
| `2521d93` | chore(g2): begin recommendation core gate | PROJECT_STATE→G2/IN_PROGRESS；stage-02 骨架 |
| `8bc8c9f` | feat(g2): implement equal-opportunity genre core with cooldown and diversity (T2.1-T2.3) | T2.1/T2.2/T2.3：等权选择（可注入 seed、稳定排序）、cooldown 30/31、family 多样性有界终止 |
| `036e5cf` | feat(g2): implement album identity filtering and deduplication (T2.4) | T2.4：canonical 优先去重、run 内 dedup、永久排除（仅 exact/可审查 identity；ambiguous 不永久封禁）、Core 不读存储 |
| `52d9d31` | feat(g2): implement album year constraints and rating composition (T2.5) | T2.5：≥1 modern（有候选时）、≤2 旧、不足/无现代候选明确降级或失败、评分维度 source-specific、权重/缺失策略可配置、确定性 tie |
| `25f8cef` | feat(g2): implement recoverable run state machine (T2.6) | T2.6：状态机 + FAILED/ABANDONED/RECOVERING、逐点 journal、幂等投递、delivered-but-not-committed 恢复不重复投递、失败不污染历史、崩溃重放、有界终止；架构边界测试 |

**偏差披露**：T2.1–T2.3 合为一个 commit——`select_daily_genres` 组合函数横跨三个任务（cooldown 过滤 + 等权抽样 + family 约束），拆开会使中间 commit 不可运行；保持每个 commit 可独立运行优先（计划 H 自批判精神）。T2.6 中 Orchestrator 不做自动 replan（`_replan_worthwhile` 恒 False），候选不足直接 FAILED（有界、可观测），避免隐性重试。

## 4. 变更文件与架构影响

- 新增 `src/omda/core/`：`genre.py`（等权选择器 + 每日计划）、`cooldown.py`、`diversity.py`、`album.py`（identity/dedup/exclusion）、`rating.py`（多维评分）、`year.py`（年份约束）——**零外部依赖**（架构测试 AST 断言：不 import storage/sqlite3/network/browser/vendor/Port Protocol/storage/orchestrator）。
- 新增 `src/omda/orchestrator/`：`run.py`（RunEngine 状态机 + recover）、`__init__.py`。
- 新增测试：`tests/unit/test_core_genre.py`、`tests/property/test_genre_equality.py`、`tests/unit/test_core_album.py`、`tests/unit/test_core_year_rating.py`、`tests/integration/test_run_engine.py`、`tests/contract/test_core_architecture.py`。
- 依赖方向：Orchestrator → Core（选择）+ Ports（副作用）；Core 永不调用 Port Protocol（历史快照由 Orchestrator 以参数传入）；G1 的 Port/存储契约零改动。

## 5. 十二项跨 Gate 验收矩阵

| # | 验收项 | 状态 | 证据 |
|---|---|---|---|
| 1 | Core 不导入 storage/sqlite3/network/browser/vendor；不调用 HistoryPort/Delivery/LLM | PASS | `test_core_has_no_forbidden_imports`（AST 扫描全部 core 模块）、`test_core_package_imports_without_side_effects` |
| 2 | Equal-opportunity 统计测试：无 popularity/tier/quality 输入路径 | PASS | `tests/property/test_genre_equality.py`（20k 采样 ±10% 容差、固定 seed 非 flaky） |
| 3 | Cooldown 30/31 精确边界 | PASS | `test_cooldown_boundary_30_and_31`（p+1 不可、p+30 不可、p+31 恢复） |
| 4 | Diversity 不可满足有界终止 | PASS | `test_diversity_unsatisfiable_terminates_bounded`、`MAX_SAMPLING_ATTEMPTS` 上限 |
| 5 | Album canonical dedup 与歧义保护 | PASS | `test_canonical_same_release_different_name_is_excluded`、`test_ambiguous_exclusion_never_permanently_blocks`、`test_dedup_key_same_name_different_year_not_merged` |
| 6 | Year constraint 正常/降级/不足候选 | PASS | `test_select_at_least_one_modern`、`test_no_modern_candidates_degrades_observably`、`test_candidate_shortage_raises_bounded` |
| 7 | Rating 多来源/缺失/权重/确定性 tie | PASS | `test_compose_rating_multi_source_weighted`、`test_missing_policy_skip/zero`、`test_rank_candidates_deterministic_ties` |
| 8 | 所有失败路径不污染 official history | PASS | `test_{fetch,generation,validation,delivery}_failure_does_not_pollute_history`、`test_candidate_shortage_fails_without_history_write`（picks=0、exclusions 空、无 HISTORY_COMMITTED） |
| 9 | delivered-but-not-committed 恢复不重复投递 | PASS | `test_delivered_but_not_committed_recovers_without_redelivery`（RECOVERING→COMPLETE，FakeDelivery 仅 1 次外部投递） |
| 10 | Fake/SQLite 关键状态机契约一致 | PASS | `test_successful_run_commits_history_and_completes[in-memory/sqlite]` 等参数化 |
| 11 | 同一输入/配置/seed 可复现 | PASS | `test_same_seed_reproduces_selection`、`test_rank_candidates_deterministic_ties` |
| 12 | 普通 CI 无 live network | PASS | 全部测试零网络调用（仅本地 fixtures/fakes/SQLite） |

## 6. Verification

| 命令 | 结果 |
|---|---|
| `pytest -v`（TEST_RESULTS.txt） | **179 passed, 0 failed, 0 skipped, 0 error** |
| `ruff check src tests` | All checks passed |
| `git diff --check` | clean |
| `git status --short`（每次提交后） | 干净 |
| secret/数据库/缓存/browser profile 跟踪检查 | 无（仅 `var/.gitkeep` G1 占位） |
| G3/G4 scope creep 检查 | 无 adapter/browser/网络代码 |

## 7. Seed / 确定性证据

- `omda.seed.make_rng(seed)` 注入所有随机源；同 seed 复现（`test_same_seed_reproduces_selection`）。
- 稳定排序（genre_id / album tie key）保证集合遍历顺序不影响选择。
- property 测试固定 seed + ±10% 容差（非 flaky，R-011 缓解）。

## 8. 失败恢复证据

- 每步失败 → journal FAILED 且官方 history 完全不变（picks/exclusions/HISTORY_COMMITTED 全空）。
- deliver 成功但 commit 失败 → RECOVERING；recover() 仅依据持久 journal + 不可变 receipt 补 commit，绝不重新外部投递（`delivery.delivered` 计数恒 1）。
- crash-replay：在 PLANNED/FETCHED/SELECTED/GENERATED/VALIDATED/DELIVERED 每个持久点注入崩溃 → recover 有界收敛（COMPLETE/FAILED/RECOVERING），无重复投递、无崩溃循环。
- 收据缺失 → fail closed（RECOVERING 待人工），不盲重复投递。

## 9. 偏差、已知限制、残余风险

- 偏差：T2.1–T2.3 单 commit（见 §3）；T2.6 不做自动 replan（有界、显式 FAILED）。
- 已知限制：`Plan.digest()` 以 journal detail 持久化 plan（恢复依赖 journal 完整性）；恢复窗口内（DELIVERING 后、DELIVERED 前）若收据已存但 journal 未写 DELIVERED，recover 通过 receipt 判定已投递并补 commit（covered by crash-replay 测试）；fuzzy 字符串身份匹配仅作 run 内 dedup，不做跨 run 永久排除（防误封，SPEC §2.4）。
- 残余风险：RISK_REGISTER R-001/R-009 缓解（本 Gate 核心，见 §8）；R-003 等权（架构测试 + property 测试锁定）；R-004 canonical 错配（fixtures 混淆场景覆盖）；R-010 seed 可复现（§7）。

## 10. Executor Conclusion

**READY_FOR_REVIEW**（待 GPT-5.6 Sol 对 G2 candidate 出具唯一 verdict；接受前不合并、不进入 G3）
