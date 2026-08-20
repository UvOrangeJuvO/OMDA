# G2 Repair Report（Re-review 2：G2-007 ~ G2-010）

> Reviewer commit：`4953297a268a16696752ab3b3400734674dfbc19`（`review(g2): request unbiased and durable core repairs`）
> 被审 candidate：`284fea8e08370ffe0a31cc1ad5f661eaa6bf314d`（verdict: CHANGES_REQUESTED）
> 修复提交链：`673ed1e`（G2-007）→ `66fed46`（G2-008）→ `ddca821`（G2-009）→ `a8ae643`（G2-010）→ 最终 handoff
> 每项先加失败回归测试、再做最小修复；verdict 未修改；未弱化/删除/skip 既有测试。

## G2-007（P0）— 有界解前缀造成 Genre-ID 选择偏差 — CLOSED

- **根因**：DFS 按 genre_id 稳定排序后枚举，`len(solutions) >= 100_000` 时截断——只覆盖字典序靠前的解，后段 ID 失去首位置机会，词法 ID 变成隐式权重。
- **修复**（`673ed1e`）：替换为**计数 DP + unranking 无偏求解**——`_counts_cached` 对每个可达状态（已选集合、family/parent 计数）计算完整有效解数（输入级 lru 缓存）；`build_unbiased_sampler` 逐位置按"以该 genre 开头的解数"加权随机前进，每个有效解等概率，**永不截断解空间**；无约束+无 cooldown 场景走 `rng.sample` 快速路径（数学同分布）。修复过程中发现并修正两个实现缺陷：嵌套函数名 `count` 遮蔽参数导致递归永不终止；`fam_map` 误以限制值作初始计数导致 Regional 族全被跳过。
- **测试**：`test_big_pool_marginal_equality_unconstrained`（100 Genre、解空间 970k > 100k、50k 采样 ±10%）、`test_big_pool_positional_opportunity_unconstrained`（首位置 ±15%）、`test_renaming_genre_ids_does_not_change_opportunity`（同构池置换 ID 机会不变）、`test_large_pool_constrained_still_bounded_and_deterministic`。
- **关闭证据**：大池每 Genre 边际机会一致（无 5.8x 差异）；重命名不改变机会；约束可满足/不可满足仍有界确定。

## G2-008（P1）— journaled seed 不能跨进程重现已 run 2 — CLOSED

- **根因**：`RunEngine` 持有一个可变长驻 RNG 并在所有 run 间复用；journal 只记录同一 seed 字符串，run 2 的随机性依赖进程内存历史；`Config.seed` 未被构造默认绑定。
- **修复**（`66fed46`）：移除长驻 RNG；**每 run 从持久 provenance 派生专用 RNG** `make_rng(f"{base_seed}:{run_id}")`；`base_seed` 优先级 = 显式参数 > `Config.seed` > `"default"`；PLANNED journal 记录派生输入 `seed`（base）+ `run_id` + `input_version` + `config_version`，不消耗任何随机抽取。
- **测试**：`test_run2_reproducible_across_process_restart`（进程 A 长驻 run1+run2 与重启后的进程 B 的 run2 的 SELECTED digest 完全一致）、`test_config_seed_is_bound_to_rng_construction`、原 `test_fresh_process_reproduces_exact_plan_from_journal_evidence` 升级为同 seed+同 run_id 重现。
- **关闭证据**：run 2 输出只依赖 journaled base_seed + run_id + 输入状态，与进程生命周期无关。

## G2-009（P0）— 他 run/key 的 ok receipt 被接受并提交历史 — CLOSED

- **根因**：`_deliver_and_commit` 只检查 `receipt.status == "ok"`，未绑定 `run_id` / `idempotency_key` / `channel`；恢复路径同样只查状态。
- **修复**（`ddca821`）：新增 `_receipt_matches(receipt, run_id, key)`——必须同时满足 run_id == 当前 run、idempotency_key == 预期 key、channel == 配置 channel、status == "ok"，任一不匹配 → FAILED（含字段详情写入 journal），**不保存收据、不提交任何官方历史**；`_finish_after_delivery` 恢复路径对持久收据做同样绑定校验，不匹配 → RECOVERING fail closed。
- **测试**：`test_misbound_receipt_never_commits_history`（wrong run id / wrong key / wrong channel / failed status × fake + SQLite 参数化，断言 pick index=0、无收据、journal 尾 FAILED）、`test_exact_matching_receipt_still_succeeds`（正常路径不回归）、`test_misbound_receipt_on_recovery_fails_closed`（篡改持久收据后恢复不提交历史）。`FakeDelivery` 现返回与 key 绑定的 run_id/channel。
- **关闭证据**：4 种绑定错配注入（fake+SQLite 共 8 例）均不提交历史；精确匹配与幂等重放继续成功。

## G2-010（P1）— parent 多样性仅存在于 test-only Core 参数 — CLOSED

- **根因**：`GenreRef` 无 parents 字段、`GenreSource` 无法携带、Orchestrator 不传 `parents_by_genre`/`parent_limits` → parent 约束在正常 run 中不可达。
- **修复**（`a8ae643`）：`GenreRef` 增加 `parents: tuple[str, ...] = ()`（domain 值类型，向后兼容）；`GenreSource` 返回带 parents 的 `GenreRef`（Protocol 签名不变）；`Config.genre_parent_limits` + config schema 字段（`genre_parent_limits: object`，additional_fields=allow）+ `_from_dict` 解析；Orchestrator 收集 `parents_by_genre = {g.genre_id: g.parents}` 并传 `select_daily_genres(parent_limits=config.genre_parent_limits, parents_by_genre=...)`——parent 是集合约束，非评分。
- **测试**：`test_parent_diversity_enforced_through_orchestrated_run`（4 Genre 池中 2 个共享受限 parent；无约束时 g1+g2 同选概率 ~50%，30 次 run 必须从不同时选中——证明约束经 Port/Orchestrator 到达 Core）、`test_parent_unsatisfiable_fails_explicitly`（不可满足 → FAILED，历史零写入）。
- **关闭证据**：正常 run 中 parent 限制生效；不可满足显式失败；无 popularity/评分路径（Core 架构测试仍通过）。

## 修复后独立反例复核（对应 Verdict "Checks performed"）

| Verdict 反例 | 复核结果 |
|---|---|
| 50/100 Genre 池等权偏差 | `test_big_pool_marginal/positional_equality` PASS（50k 采样） |
| run2 长驻 vs 重启输出分歧 | `test_run2_reproducible_across_process_restart` PASS（digest 一致） |
| 他 run/key ok receipt 提交历史 | `test_misbound_receipt_never_commits_history` PASS（FAILED，零提交） |
| parent 无法经 GenreSource/RunEngine 传递 | `test_parent_diversity_enforced_through_orchestrated_run` PASS（约束生效） |

## 验证

| 命令 | 结果 |
|---|---|
| `pytest -q -p no:cacheprovider` | **225 passed, 0 failed, 0 skipped, 0 error** |
| `pytest -v`（TEST_RESULTS.txt） | 225 passed |
| `ruff check src tests` | All checks passed |
| `git diff --check` | clean |
| 既有测试未删除/弱化/skip | 确认（计数 206 → 225 单调增长） |
| 未 merge / 未 tag / 未进入 G3 / 未改 verdict | 确认 |

---

# G2 Re-review 3 Repair（2026-08-19）

对应 Reviewer commit：`266ccdc1c69b5b90d76366af125b3009f688c19d`（`review(g2): request bounded configuration and recovery repairs`）
上一 candidate：`c0bf31d974a85499082a2e3e6eeb24e66fea1ed9`
本轮修复 commits：`fd3340a`（G2-011）、`a39d351`（G2-012）、`e405898`（G2-013）

## G2-011（P1）— genre_parent_limits 绕过校验且可变破坏 provenance — CLOSED

- **根因**：schema 用 `additional_fields="allow"` 无值校验（接受 "one"/-1/0/1.5/true/嵌套）；畸形值到达 Core 抛未捕获 TypeError；`Config` frozen 但持可变 dict，引擎构造后 mutate 改变选择而 journal 指纹是旧的。
- **修复**（`fd3340a`）：
  1. validator 扩展：`additional_fields` 支持值 spec dict（`reject`/`allow`/值 spec 三态；schema 树无条件校验值 spec）；
  2. `config.schema.json`：`genre_parent_limits` 值 spec `{type: integer, min: 1, max: 10}`（0/负数会永久饿死 parent → 禁止；上限与 daily_genre_count 一致），schema_version 1→2；
  3. `Config.genre_parent_limits` 存 `MappingProxyType`（不可变）；`config_to_dict` 确定性序列化；`_from_dict` 冻结快照。
- **测试**：6 种畸形值在精确路径 `genre_parent_limits.electronic` 拒绝；合法值 round-trip；mutate 原 overrides 不影响 Config；直接改 Config 值抛 TypeError；journal fingerprint 恒等于 selection 用配置快照。
- **关闭证据**：畸形值在 PLANNED 前被 RecordValidationError 拒绝（精确 field path）；不可变快照保证 fingerprint 与实际生效约束一致。

## G2-012（P1）— 歧义成功投递被终态 FAILED — CLOSED

- **根因**：deliver 返回 ok 但 run/key/channel 错 → 拒绝 commit 后 append 终态 FAILED 并丢弃收据；外部可能已投递，歧义被隐藏。
- **修复**（`a39d351`）：拆分状态判定——`status != "ok"`（确认失败）→ 普通 FAILED；`ok` 但 misbound → **RECOVERING**（manual review），journal 持久化异常证据（receipt_run_id/key/channel/status），不 commit、不重投、不终态；恢复路径对持久收据同样校验。
- **测试**：`test_misbound_receipt_never_commits_history` 升级为 RECOVERING + anomaly 可审计断言；`test_ambiguous_delivery_records_one_effect_and_never_redelivers`（3 种 misbound × calls==1、重复 run 不二次投递、历史零写入）；`test_failed_receipt_run_fails_without_history` 保持确认失败 → FAILED。
- **关闭证据**：外部副作用发生一次后歧义进入 recovery 而非终态；重复 run 零额外投递；历史不变；异常可审计。

## G2-013（P1）— 无偏求解器组合内存增长且跨 run 保留 — CLOSED

- **根因**：`_counts_cached` 存全部可达状态（含全部终态三元组）；`build_unbiased_sampler` 总是先建 DP（快路径在 sampler 内，无法避免构建）；LRU 128 变体累积组合 memo（5 次不同 start → 388MB）。
- **修复**（`e405898`）：
  1. **快路径前置**：无 cooldown + 无 family/parent 限制 → 直接 `rng.sample`（数学等价），零 DP；
  2. **终态不 memoize**：depth==count 直接返回 1，sampler 对终态子分支直接取 1；
  3. **LRU maxsize 128 → 4**（`_counts_cached` 与 `_enumerate_cached`），跨 run 旧 memo 被逐出而非累积。
- **测试**：200 Genre 无约束 → 快路径且 `_counts_cached` currsize 不增；8 个不同 global start → 缓存 ≤ 4（有界）；30 Genre 有约束 → memo 大小 << C(30,3) 全组合（终态不存储）。既有 exact-count/等权/cooldown/parent/satisfiable/unsatisfiable 测试全部保留通过。
- **关闭证据**：无约束大池零组合构建；跨 run 缓存有界；约束路径仅保留非终态状态。

## 本轮验证

| 命令 | 结果 |
|---|---|
| `pytest -q -p no:cacheprovider` | **239 passed, 0 failed, 0 skipped, 0 error** |
| `pytest -v`（TEST_RESULTS.txt） | 239 passed |
| `ruff check src tests` | All checks passed |
| `git diff --check` | clean |
| 既有测试未删除/弱化/skip | 确认（225 → 239 单调增长；G2-009 misbound 测试按新验收语义升级为 RECOVERING，属修复而非弱化） |
| 未 merge / 未 tag / 未进入 G3 / 未改 verdict | 确认 |

---

# G2 Re-review 4 Repair（2026-08-20）

对应 Reviewer commit：`1c0265a8aaa35c4a7b4204016ea8760e56304c79`（`review(g2): keep boundary and recovery findings open`）
上一 candidate：`061e1d11fe703a4ee3036dc5d4bad5d847a2ef99`
本轮修复 commits：`3540c47`（G2-011）、`5b7326f`（G2-012）、`ac3fc60`（G2-013）

## G2-011 — 直接 Config(...) 构造仍可变 — CLOSED

- **根因**：`Config.genre_parent_limits` 用 `field(default_factory=dict)`，frozen dataclass 无 `__post_init__` 规范化；`Config()` 与 `Config(genre_parent_limits=caller_dict)` 暴露可变映射。
- **修复**（`3540c47`）：`Config.__post_init__` 在**每一条构造路径**（含直接 `Config(...)`）把 parent 映射做防御性复制并冻结为 `MappingProxyType`——caller dict 与暴露映射均无法改变生效约束；引擎构造后的 fingerprint 恒等于生效规则。
- **测试**：`test_direct_config_default_is_immutable`、`test_direct_config_with_caller_dict_is_immutable_and_detached`（mutate 原 dict 不影响 Config、改暴露映射抛 TypeError）、`test_direct_config_runengine_fingerprint_matches_selection_rules`（直接 Config 构造 RunEngine，构造后 mutate caller dict，fingerprint 仍等于生效规则）。
- **关闭证据**：直接构造路径的映射不可变；fingerprint/行为分歧不可复现。

## G2-012 — 收据分类顺序错误 + 恢复日志无界 — CLOSED

- **根因**：`_deliver_and_commit` 先查 `status != "ok"` 再查绑定 → misbound failed receipt（他 run 的确认失败）被误终结为 FAILED；冲突收据（外部调用后）也被终结 FAILED；相同证据的重复恢复不断追加 RECOVERING 条目。
- **修复**（`5b7326f`）：
  1. **先验证 run/key/channel 绑定，再解释 status**——绑定错误（无论 status）→ RECOVERING（外部可能已投递）；绑定正确 + failed → 确认失败 → FAILED；绑定正确 + ok → 正常路径；
  2. receipt 存储冲突（外部调用后）→ RECOVERING（歧义），原证据保留、零历史；
  3. 恢复幂等：`_finish_after_delivery` 对未变化证据（尾部已 RECOVERING）不再追加 journal 条目。
- **测试**：`test_bound_failed_receipt_is_ordinary_terminal_failure`（绑定正确 failed → FAILED）、`test_misbound_failed_receipt_enters_recovery`（他 run failed → RECOVERING）、`test_receipt_conflict_after_external_call_enters_recovery`（冲突 ok → RECOVERING、1 次投递、原证据保留）、`test_repeated_recovery_of_unchanged_evidence_is_bounded`（5 次相同 run() → 仅 1 条 RECOVERING、1 次投递、零历史）。
- **关闭证据**：仅正确绑定的 failed 终结为 FAILED；任何 misbound/conflict 进 RECOVERING；恢复日志有界。

## G2-013 — RunEngine 形状绕过快路径 — CLOSED

- **根因**：RunEngine 对每个 eligible genre 生成 cooldown key（首次 run 值全空）→ `not pick_history` False；默认 family limits 非空且池中无对应 family 时 DP 仍激活 → 100/200/300 Genre 首 run 0.47s/5.14s/19.2s。
- **修复**（`ac3fc60`）：`build_unbiased_sampler` 在快路径判定前做**语义规范化**——丢弃 cooldown 空值条目、丢弃对当前池不存在的 family/parent 限制（不改变有效解空间 → 等权保持）；规范化后无任何生效约束 → `rng.sample` 快路径零 DP；约束路径的 memo key 用 active 版本。快路径 count 超池时抛 `InsufficientCandidatesError`（保持有界显式失败语义）。
- **测试**：`test_runengine_shaped_empty_cooldown_map_uses_fast_path`（200 Genre + `{gid: ()}` 形状 + 默认 limits → 零 DP）、`test_orchestrated_first_run_large_pool_has_no_dp_construction`（真实 RunEngine 200 Genre 首次 run → COMPLETE 且 `_counts_cached` currsize 不增）、`test_active_constraint_upper_bound_stays_bounded`（Regional 激活 → DP 有界、确定性、family 限制生效）；既有缓存 ≤4 跨 starts 测试保留。
- **关闭证据**：正式 Orchestrator 输入形状零 DP；active 约束有界确定；无前缀截断、无概率性假不足。

## 本轮验证

| 命令 | 结果 |
|---|---|
| `pytest -q -p no:cacheprovider` | **248 passed, 0 failed, 0 skipped, 0 error** |
| `pytest -v`（TEST_RESULTS.txt） | 248 passed |
| `ruff check src tests` | All checks passed |
| `git diff --check` | clean |
| 既有测试未删除/弱化/skip | 确认（239 → 248 单调增长；G2-012 failed-receipt 测试按新验收语义升级为 bound/misbound 两例，属修复而非弱化） |
| 未 merge / 未 tag / 未进入 G3 / 未改 verdict | 确认 |

---

# G2 Re-review 5 Repair（2026-08-20）

对应 Reviewer commit：`3fd88ad71491353ac6228a01dc45f43b439587e1`（`review(g2): request exact boundary and normalization repairs`）
上一 candidate：`bf62ca658a1cbb10d5bbc8b2bae4f2b4a7c87305`
本轮修复 commits：`a3680a9`（G2-011）、`df6a22b`（G2-012）、`7f089d0`（G2-013/G2-010）

## G2-011 — 直接 Config(...) 非法值绕过校验 — CLOSED

- **根因**：`Config.__post_init__` 只冻结映射不校验值 → `Config(genre_parent_limits={"p": "one"})` 构造成功，RunEngine 接受后在 PLANNED 后抛未捕获 TypeError。
- **修复**（`a3680a9`）：`Config.__post_init__` 对**每一条构造路径**校验值——parent key 非空字符串、limit 为 int（非 bool）、1..10 安全范围；非法 → 受控 `ValueError`（带 `genre_parent_limits.<parent>` 精确路径），配置无法构造 → 任何 run 都不可能以未校验配置写 PLANNED。
- **测试**：直接 `Config(...)` 的 string/bool/float/zero/negative/out-of-range 六类值均受控拒绝；非法值无法构造 Config（引擎无从产生，PLANNED 不可能写入）。
- **关闭证据**：直接构造非法值在 PLANNED 前受控拒绝，无未捕获内建异常。

## G2-012 — 未知/畸形收据状态被当确认失败 — CLOSED

- **根因**：绑定通过后 `status != "ok"` 全判 FAILED → bound `"unknown"`/`"pending"`/`""` 被终结为确认失败。
- **修复**（`df6a22b`）：**严格三分**——`status == "ok"` 成功路径；绑定正确且 `status == "failed"` 确认失败 → FAILED；**其余所有状态**（unknown/pending/空/畸形）→ RECOVERING，journal 持久化 `receipt_status` 异常证据，零历史、不重投。
- **测试**：`test_bound_malformed_status_enters_recovery_not_terminal`（unknown/pending/empty × 1 次投递、RECOVERING、零历史、anomaly detail 保留 receipt_status）。
- **关闭证据**：仅恰好 "ok"/"failed" 被解释；任何其他状态进入 recovery 且证据可审计。

## G2-013/G2-010 — 规范化丢弃真实 parent 约束 + stale 历史仍建 DP — CLOSED

- **根因**：`pool_parents` 只从 GenreRef.parents 派生 → 显式 `parents_by_genre` 映射（GenreRef 无 parents）时 parent_limits 被丢弃进快路径，违反约束；cooldown 只丢弃空 tuple → `{gid:(1,)}` + 远端 start 仍建 DP（200 Genre 4s）；limit 只要池中有成员就保留（成员 ≤ limit 不可能 bind 也激活 DP）。
- **修复**（`7f089d0`）：
  1. **authoritative parents**：合并 `parents_by_genre` 与 GenreRef.parents 为 `effective_parents_by_genre`（显式映射永不被丢弃），约束路径与 DP 均用该映射；
  2. **stale cooldown**：条目仅当能阻断 next `count` 个全局位置之一时保留（对每个 `start+i` 用 `is_available` 判定）——全可用则丢弃；
  3. **不 bind 的 limit**：`min(成员数, count) > limit` 才保留 family/parent 限制。
- **测试**：`test_explicit_parents_by_genre_constraint_is_never_dropped`（4 Genre 显式映射 40 seeds 从不同选 + 不可满足显式失败）、`test_stale_nonempty_cooldown_history_uses_fast_path`（200 Genre `{gid:(1,)}` + start=1000 → 零 DP）、`test_limits_that_cannot_bind_are_dropped`（1 Regional/limit 1、2 成员/limit 2 → 快路径）。
- **关闭证据**：显式 parent 约束在公共 selector 生效（Reviewer seed-0 反例关闭）；stale 历史零 DP；不可能 bind 的限制被丢弃；等权与显式不足保持。

## 本轮验证

| 命令 | 结果 |
|---|---|
| `pytest -q -p no:cacheprovider` | **261 passed, 0 failed, 0 skipped, 0 error** |
| `pytest -v`（TEST_RESULTS.txt） | 261 passed |
| `ruff check src tests` | All checks passed |
| `git diff --check` | clean |
| 既有测试未删除/弱化/skip | 确认（248 → 261 单调增长） |
| 未 merge / 未 tag / 未进入 G3 / 未改 verdict | 确认 |
