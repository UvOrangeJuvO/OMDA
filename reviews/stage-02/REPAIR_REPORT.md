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
