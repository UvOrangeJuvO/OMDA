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

---

# G2 Re-review 1 Repair（2026-08-19）

对应 Reviewer commit：`d07237ee243d556ed7f82c2c54277b9d0c454acb`（`review(g2): request core invariant repairs`）
上一 candidate：`5ae45fe436cffa000cc0684f6768f0afb504edb6`
本轮修复 commits：`a85a3a4`（Batch A）、`67717e3`（Batch B）、`f13bda9`（Batch C）
本轮 Candidate：提交后由 Executor 在最终聊天报告给出精确 SHA（`candidate_commit` 保持 null）

## Re-review 1 finding 修复对照

| Finding | 严重度 | 修复 commit | 状态 |
|---|---|---|---|
| G2-001 Plan 每次从 1 重启全局 pick index | P0 | `a85a3a4` | CLOSED |
| G2-002 cooldown 首位置过滤 + 200 次碰运气 | P1 | `a85a3a4` | CLOSED |
| G2-003 Album identity 匹配可重复推荐/误封 | P0 | `67717e3` | CLOSED |
| G2-004 年份 fallback 不可观测 + max_older 绕过 | P1 | `67717e3` | CLOSED |
| G2-005 crash harness 无效 + 幂等缺失 | P1 | `f13bda9` | CLOSED |
| G2-006 journal 记录的不是 seed | P1 | `a85a3a4` + `f13bda9` | CLOSED |

## Batch A — G2-001 + G2-002（commit `a85a3a4`）

- **G2-001**：`Plan` 现携带精确有序 `pick_records`（全局 index 由 `HistoryPort.latest_pick_index()+1` 给出，传入 `select_daily_genres(global_start_index=...)`）；`digest()/from_digest()` 原样持久化/恢复精确 index，恢复不再重新生成 1–3；`_run_once` 在 SELECT 后、DELIVER 前校验计划 index 不与已提交历史冲突（冲突绝不首现于外部投递后）；全局序号不再从当前可见 GenreSource 推断。
- **G2-002**：cooldown 在每个精确全局位置评估（`is_available(history, global_start+i)`）；以**有界完备求解**（回溯枚举有效有序序列，上限 `MAX_ENUMERATED_SOLUTIONS`，参数化 lru 缓存）替代 200 次随机重试——可满足池永不被误报不足；family/parent 集合约束（`parent_ok` + `parents_by_genre`）；等权 = 从有效解空间均匀采样。
- 测试：连续三次运行提交 1-3/4-6/7-9（fake+SQLite）、历史最新 pick 属于不可见 Genre 仍推进全局序号、失败 run 不消耗 index、位置内 30/31 边界、100 Regional 倾斜池多 seed 全成功、真不可满足显式终止、parent 重叠约束、确定性重放保留有序 picks。性能修复：解空间索引采样（property 20k 采样 <0.1s，无 flaky 阈值）。

## Batch B — G2-003 + G2-004（commit `67717e3`）

- **G2-003**：`album_id` 精确匹配独立于嵌套 identity（`identity=None` 也排除）；canonical 按 `(canonical_source, canonical_id)` 命名空间匹配，source 缺失任一侧即不匹配（防误封）；破坏性 canonical 匹配要求**双端**非 ambiguous；`normalized_text` Unicode-aware（NFD + 仅拉丁基底剥离组合标记 + casefold），保留日文浊点/非拉丁脚本，杜绝 ASCII 删除导致的跨脚本碰撞。
- **G2-004**：`select_albums_for_genre` 返回结构化 `AlbumSelectionResult`（albums + status/reason/modern/older/unknown/candidates）；`status` 三态（normal / fallback_no_modern / fallback_insufficient_era）；final fill 绝不静默突破 `max_older`（cap 不满 → 显式 `fallback_insufficient_era`）；`Plan.selection_results` + journal `album_selection` 持久化每 Genre 约束状态（端到端测试断言 SELECTED detail 含 fallback 证据）。
- 测试：无 identity 精确排除、跨 source 同 id 不判等、ambiguous 双端保护、非拉丁/重音 distinct、跨 run 永久排除；年份 normal/no-modern/unknown/insufficient-era/cap 不绕过。

## Batch C — G2-005 + G2-006（commit `f13bda9`）

- **G2-005**：`run(run_id)` 先查持久 journal——已有 run 只返回终态或 `recover()`，绝不重新规划（同一 run id 幂等重放，`COMPLETE` 恰一次）；recover 遇 `HISTORY_COMMITTED` 尾部**持久追加** `COMPLETE`（`_complete_durably`，重复调用不重复追加）；真实 crash harness `CrashPointHistory`——**先持久化转换再模拟进程死亡**（`SimulatedCrash`），表驱动覆盖 10 个持久窗口（PLANNED→COMPLETE + receipt-saved + history-committed）；missing/failed/conflicting receipt 针对同一已投递 run fail closed（不重投、证据不变、历史不写）；`FakeDelivery.calls`（deliver 调用数）与 `delivered`（外部副作用数）分离，恢复零额外调用；注入 receipt-save/journal-write/history-commit 失败。
- **G2-006**：RNG 绑定显式 `seed`（构造参数替代裸 rng）；PLANNED journal 记录真实 seed + `input_version` + `config_version`（配置 sha1 指纹）——**不消耗 RNG**；恢复/新进程仅凭 journal 证据重建完全相同的有序 Genre/Album plan（端到端重现测试）。

## 本轮验证

| 命令 | 结果 |
|---|---|
| `pytest -v`（TEST_RESULTS.txt） | **206 passed, 0 failed, 0 skipped, 0 error** |
| `ruff check src tests` | All checks passed |
| `git diff --check` | clean |
| `git status --short`（每次提交后） | 干净 |
| 敏感文件跟踪检查 | 无 |
| 未删除/skip/弱化既有测试 | 确认（test_count 56→206 单调增长；旧 crash/missing-receipt 测试以等价更强的表驱动测试替换） |
| 未 merge / 未 tag / 未进入 G3 / 未改 verdict | 确认 |

## Executor Conclusion（G2 Re-review 1 repair）

**READY_FOR_REVIEW**（待 GPT-5.6 Sol 对本轮新 candidate SHA 复审；verdict 仅对新 SHA 有效）

---

# G2 Re-review 2 Repair（2026-08-19）

对应 Reviewer commit：`4953297a268a16696752ab3b3400734674dfbc19`（`review(g2): request unbiased and durable core repairs`）
上一 candidate：`284fea8e08370ffe0a31cc1ad5f661eaa6bf314d`
本轮修复 commits：`673ed1e`（G2-007）、`66fed46`（G2-008）、`ddca821`（G2-009）、`a8ae643`（G2-010）
详细逐项修复记录见 `reviews/stage-02/REPAIR_REPORT.md`（verdict 要求的 handbook 命名文件）。

## Re-review 2 finding 修复对照

| Finding | 严重度 | 修复 commit | 状态 |
|---|---|---|---|
| G2-007 有界解前缀造成 Genre-ID 选择偏差 | P0 | `673ed1e` | CLOSED |
| G2-008 journaled seed 不能跨进程重现已 run 2 | P1 | `66fed46` | CLOSED |
| G2-009 他 run/key 的 ok receipt 被接受并提交历史 | P0 | `ddca821` | CLOSED |
| G2-010 parent 多样性仅存在于 test-only Core 参数 | P1 | `a8ae643` | CLOSED |

## 本轮验证

| 命令 | 结果 |
|---|---|
| `pytest -q -p no:cacheprovider` | **225 passed, 0 failed, 0 skipped, 0 error** |
| `pytest -v`（TEST_RESULTS.txt） | 225 passed |
| `ruff check src tests` | All checks passed |
| `git diff --check` | clean |
| 既有测试未删除/弱化/skip | 确认（206 → 225 单调增长） |
| 未 merge / 未 tag / 未进入 G3 / 未改 verdict | 确认 |

## Executor Conclusion（G2 Re-review 2 repair）

**READY_FOR_REVIEW**（待 GPT-5.6 Sol 对本轮新 candidate SHA 复审；verdict 仅对新 SHA 有效）

---

# G2 Re-review 3 Repair（2026-08-19）

对应 Reviewer commit：`266ccdc1c69b5b90d76366af125b3009f688c19d`（`review(g2): request bounded configuration and recovery repairs`）
上一 candidate：`c0bf31d974a85499082a2e3e6eeb24e66fea1ed9`
本轮修复 commits：`fd3340a`（G2-011）、`a39d351`（G2-012）、`e405898`（G2-013）
详细逐项修复记录见 `reviews/stage-02/REPAIR_REPORT.md`。

## Re-review 3 finding 修复对照

| Finding | 严重度 | 修复 commit | 状态 |
|---|---|---|---|
| G2-011 genre_parent_limits 绕过校验且可变 | P1 | `fd3340a` | CLOSED |
| G2-012 歧义成功投递被终态 FAILED | P1 | `a39d351` | CLOSED |
| G2-013 无偏求解器组合内存增长 | P1 | `e405898` | CLOSED |

## 本轮验证

| 命令 | 结果 |
|---|---|
| `pytest -q -p no:cacheprovider` | **239 passed, 0 failed, 0 skipped, 0 error** |
| `pytest -v`（TEST_RESULTS.txt） | 239 passed |
| `ruff check src tests` | All checks passed |
| `git diff --check` | clean |
| 既有测试未删除/弱化/skip | 确认（225 → 239 单调增长） |
| 未 merge / 未 tag / 未进入 G3 / 未改 verdict | 确认 |

## Executor Conclusion（G2 Re-review 3 repair）

**READY_FOR_REVIEW**（待 GPT-5.6 Sol 对本轮新 candidate SHA 复审；verdict 仅对新 SHA 有效）

---

# G2 Re-review 4 Repair（2026-08-20）

对应 Reviewer commit：`1c0265a8aaa35c4a7b4204016ea8760e56304c79`（`review(g2): keep boundary and recovery findings open`）
上一 candidate：`061e1d11fe703a4ee3036dc5d4bad5d847a2ef99`
本轮修复 commits：`3540c47`（G2-011）、`5b7326f`（G2-012）、`ac3fc60`（G2-013）
详细逐项修复记录见 `reviews/stage-02/REPAIR_REPORT.md`。

## Re-review 4 finding 修复对照

| Finding | 严重度 | 修复 commit | 状态 |
|---|---|---|---|
| G2-011 直接 Config(...) 构造仍可变 | P1 | `3540c47` | CLOSED |
| G2-012 收据分类顺序错误 + 恢复日志无界 | P1 | `5b7326f` | CLOSED |
| G2-013 RunEngine 形状绕过求解器快路径 | P1 | `ac3fc60` | CLOSED |

## 本轮验证

| 命令 | 结果 |
|---|---|
| `pytest -q -p no:cacheprovider` | **248 passed, 0 failed, 0 skipped, 0 error** |
| `pytest -v`（TEST_RESULTS.txt） | 248 passed |
| `ruff check src tests` | All checks passed |
| `git diff --check` | clean |
| 既有测试未删除/弱化/skip | 确认（239 → 248 单调增长） |
| 未 merge / 未 tag / 未进入 G3 / 未改 verdict | 确认 |

## Executor Conclusion（G2 Re-review 4 repair）

**READY_FOR_REVIEW**（待 GPT-5.6 Sol 对本轮新 candidate SHA 复审；verdict 仅对新 SHA 有效）

---

# G2 Re-review 5 Repair（2026-08-20）

对应 Reviewer commit：`3fd88ad71491353ac6228a01dc45f43b439587e1`（`review(g2): request exact boundary and normalization repairs`）
上一 candidate：`bf62ca658a1cbb10d5bbc8b2bae4f2b4a7c87305`
本轮修复 commits：`a3680a9`（G2-011）、`df6a22b`（G2-012）、`7f089d0`（G2-013/G2-010）
详细逐项修复记录见 `reviews/stage-02/REPAIR_REPORT.md`。

## Re-review 5 finding 修复对照

| Finding | 严重度 | 修复 commit | 状态 |
|---|---|---|---|
| G2-011 直接 Config(...) 非法值绕过校验 | P1 | `a3680a9` | CLOSED |
| G2-012 未知/畸形收据状态被当确认失败 | P1 | `df6a22b` | CLOSED |
| G2-013/G2-010 规范化丢弃真实 parent 约束 + stale 历史仍建 DP | P1 | `7f089d0` | CLOSED |

## 本轮验证

| 命令 | 结果 |
|---|---|
| `pytest -q -p no:cacheprovider` | **261 passed, 0 failed, 0 skipped, 0 error** |
| `pytest -v`（TEST_RESULTS.txt） | 261 passed |
| `ruff check src tests` | All checks passed |
| `git diff --check` | clean |
| 既有测试未删除/弱化/skip | 确认（248 → 261 单调增长） |
| 未 merge / 未 tag / 未进入 G3 / 未改 verdict | 确认 |

## Executor Conclusion（G2 Re-review 5 repair）

**READY_FOR_REVIEW**（待 GPT-5.6 Sol 对本轮新 candidate SHA 复审；verdict 仅对新 SHA 有效）

---

# G2 Re-review 6 Repair（2026-08-20）

对应 Reviewer commit：`169e3eedd69710053e055c7a1b069c85c0dc0a85`（`review(g2): require complete config and solver bounds`）
上一 candidate：`0594b2774a3a5f07f15086dc1474af9d8ef5bce6`
本轮修复 commits：`d733fa7`（G2-011）、`af7e51b`（G2-013）
详细逐项修复记录见 `reviews/stage-02/REPAIR_REPORT.md`。

## Re-review 6 finding 修复对照

| Finding | 严重度 | 修复 commit | 状态 |
|---|---|---|---|
| G2-011 直接 Config 校验仅覆盖 genre_parent_limits | P1 | `d733fa7` | CLOSED |
| G2-013 真激活约束资源边界未定义 | P1 | `af7e51b` | CLOSED |

## 本轮验证

| 命令 | 结果 |
|---|---|
| `pytest -q -p no:cacheprovider` | **274 passed, 0 failed, 0 skipped, 0 error** |
| `pytest -v`（TEST_RESULTS.txt） | 274 passed |
| `ruff check src tests` | All checks passed |
| `git diff --check` | clean |
| 既有测试未删除/弱化/skip | 确认（261 → 274 单调增长） |
| 未 merge / 未 tag / 未 push / 未进入 G3 / 未改 verdict | 确认 |

## Executor Conclusion（G2 Re-review 6 repair）

**READY_FOR_REVIEW**（待 GPT-5.6 Sol 对本轮新 candidate SHA 复审；verdict 仅对新 SHA 有效）

---

# G2 Re-review 7 Repair（2026-08-20）

对应 Reviewer commit：`d50722ac8b393b653b8d753831588d1b96a2f153`（`review(g2): require exact config null validation`）
上一 candidate：`a9136bb25cd487f81255561a440fb5da1f424ad4`
本轮修复 commit：`028b4ba`（G2-011）
详细逐项修复记录见 `reviews/stage-02/REPAIR_REPORT.md`。

## Re-review 7 finding 修复对照

| Finding | 严重度 | 修复 commit | 状态 |
|---|---|---|---|
| G2-011 `_normalise` 隐藏无效 null + 嵌套类型绕过受控校验 | P1 | `028b4ba` | CLOSED |

## 本轮验证

| 命令 | 结果 |
|---|---|
| `pytest -q -p no:cacheprovider` | **283 passed, 0 failed, 0 skipped, 0 error** |
| `pytest -v`（TEST_RESULTS.txt） | 283 passed |
| `ruff check src tests` | All checks passed |
| `git diff --check` | clean |
| 未修改求解器/推荐规则/收据逻辑 | 确认 |
| 既有测试未删除/弱化/skip | 确认（274 → 283 单调增长） |
| 未 merge / 未 tag / 未 push / 未进入 G3 / 未改 verdict | 确认 |

## Executor Conclusion（G2 Re-review 7 repair）

**READY_FOR_REVIEW**（待 GPT-5.6 Sol 对本轮新 candidate SHA 复审；verdict 仅对新 SHA 有效）
