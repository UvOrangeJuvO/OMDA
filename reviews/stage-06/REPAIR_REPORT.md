# G6 Repair Report — G6-001 ~ G6-007

> 角色：OMDA Executor（WorkBuddy；实际模型 GLM-5.3-Flash）
> 被审 candidate：`88324ae3a3a95d4372a6548da31d836a514ada3d`
> Reviewer checkpoint（本轮直接父提交）：`3c39aae24af2ef721422aafd947f782d0506d67c`
> Verdict：`reviews/stage-06/REVIEW_VERDICT.md`（CHANGES_REQUESTED）
> 修复原则：最小改动、逐条闭环、不删除/弱化/跳过既有测试；candidate
> `88324ae3` 与 Reviewer commit 保持不可变，全部修复位于其后。

## 逐项关闭对照

### G6-001 — seed 与 selection-pool digest 协议（P1）→ CLOSED

- `select()` 重写：**防重复规则先执行**，再从**最终实际可用**的候选构造
  selection canonical projection（规范化 identity + resolved Genre）；
  selection-pool digest 只对最终可用池计算。
- `seed_material_digest(day_key, pool_digest)` 精确只含
  `(day_key, algorithm_version, selection_pool_digest)`；
  `consumed_picks` 及其他一切额外输入已删除。
- 新增测试：`test_g6001_seed_independent_of_history_length`（签名断言
  `["day_key", "pool_digest"]` + 同 day/pool 结果一致）、
  `test_g6001_excluded_genre_mutation_invariant`（只改动被 cooldown 排除
  Genre 内的专辑 → pool digest / seed / 选择全部不变）。
- 固定选择向量 fixture 更新为新协议（AC-26）。

### G6-002 — 唯一 Genre 提示（P1）→ CLOSED

- 三个分支语义纠正：
  1. **真豁免**：唯一 admissible 分组 == 上一成功分组 → 允许重复，
     `forced_note` 显式标注"唯一可用流派…防重复规则在此豁免"；
  2. **cooldown 已执行**：多分组中排除上一分组后仅剩一个**不同**分组 →
     `cooldown_note` 明确"防重复规则已执行：冷却后仅剩一个不重复的可用
     流派"（不再是"waived"）；
  3. **普通多分组**：无任何 note。
- 两个 note 存入历史 `selected` 并渲染进每日输出。
- 新增测试：`test_g6002_true_waiver_unique_genre_note`、
  `test_g6002_cooldown_applied_single_remainder_note`、
  `test_g6002_normal_multi_group_no_notes`、端到端
  `test_g6002_end_to_end_cooldown_note` / `test_g6002_end_to_end_forced_unique_note`。

### G6-003 — 历史深度校验与同日提交语义（P1）→ CLOSED

- `_validate_history` 全面重写：根/天键/记录字段集（拒绝未知字段）、
  嵌套 `timezone_evidence`（含 utc_offset 格式）、`selected` 全字段
  （含 annotations 元素、order int、note 字段 null|string）、64-hex digest
  格式、`source_ids` 非空/唯一/**canonical 排序**、display names 与 digests
  的键集与 source_ids 一致、`selected.source_id`/annotations 归属、
  `identity_key` 与 artist/album 跨字段一致、`render_lang ∈ {zh,en}`、
  `record.day_key == 键`。任何 schema-shaped 损坏 → ValueError →
  load_history 走损坏副本 + **exit 3**，不再抛未捕获 KeyError。
- **语言锁定**：提交时记录 `render_lang`；同日重放以
  `record["render_lang"]` 渲染，`--lang` 变更不改变输出字节。
- **时钟回退守卫**：当前 day key 早于历史最新 day key → fail-closed
  （exit 2），禁止补写过去日期。
- 新增负向测试：`test_g6003_shaped_corrupt_history_exit3`（`selected: {}`
  形状损坏 → exit 3 + 损坏副本 + 历史字节不变）、
  `test_g6003_language_locked_for_same_day`、
  `test_g6003_clock_rollback_rejected`。

### G6-004 — canonical 审计证据（P1）→ CLOSED

- 新增 `_content_record_sort_key`（文档化稳定 tuple：规范化 identity 优先，
  其后各字段 NFC）；`compute_source_content_digest` 对排序后的完整记录
  计算 → **仅改变行序不改变 content digest**。
- 历史 `source_ids` 统一为 canonical（sorted）source_id 顺序；
  annotations 的 `order` 改为记录在 canonical 内容排序中的位置（不再泄漏
  文件行序）。
- 扩展测试：`test_g6004_content_digest_row_order_invariant`（新增）、
  AC-19 扩展为比较 content digests + `source_ids` + **完整历史记录相等**、
  AC-25 扩展 content-digest 不变量。

### G6-005 — Codex Skill 安装结构（P1）→ CLOSED

- `agents/openai.yaml` 改为受支持的 `interface:` 结构
  （display_name / short_description / default_prompt，全部字符串加引号，
  default_prompt 含 `$omda-daily-discovery`）；删除无效的顶层
  `name`/`description`/`version` 结构。
- SKILL.md 与 README 明确区分**已安装 Skill 根目录（`<skill-root>`）**与
  **用户 workspace**：Profile/Sources/History 留在用户 workspace；脚本与
  模板相对 `<skill-root>` 解析（`<skill-root>/scripts/daily_pick.py`、
  `<skill-root>/templates/`），不再假设用户 cwd 存在脚本。
- 新增 `test_g6005_openai_yaml_interface_structure`（结构断言 + 禁止旧
  顶层键）与 `test_g6005_install_simulation_separate_dirs`（Skill 安装目录
  与用户 workspace 完全分离，经已安装 skill root 的脚本完成首次推荐，
  且 skill root 未接收任何用户数据）。
- Validator：本机未找到 Codex `quick_validate.py`；按"可用时必须运行"
  的要求，改用 PyYAML（仅装入隔离 dev venv，**非 OMDA 运行时依赖**）对
  `openai.yaml` 做了解析与结构校验（见 TEST_RESULTS.txt [3.3]），
  结果 PASS。

### G6-006 — 完整中英文前言（P1）→ CLOSED（待 Owner/Reviewer 复核确认）

- 采用 Owner 原稿（附件 pasted-text.txt）为唯一来源，README 前言恢复：
  标题 `OMDA` → `Open Music Discovery Agent` → **`开放音乐探索 Agent`**
  （错误的全称"每日音乐探索代理"已从交付物中移除；治理计划 §C.7 草稿
  加注"已被 Owner 原稿取代"）→ 双语题记及《礼记·乐记》出处 → 中/英引言
  四段 → 三个完整的中英双语主题部分（天地之和 / 八音克谐 / 伯牙子期，
  含各自的内嵌引文与出处）→ 中英"为什么我想做 OMDA"。
- Owner 后续想法（卡尔维诺、偶然相遇、信任/陌生/随机/不同意的来源、
  审美由文化和经历塑造）以第一人称、克制语气整合进 Why 结尾，中英逐句
  对应，未上升为普适宣言。
- `PREFACE_CHECKLIST.md` 已完整填写（21 项逐句对照 + 约束自查）；
  最终 Owner/Reviewer 复核列保持未勾选——**AC-30 不由 Executor 宣称
  PASS**，状态为 EXECUTOR_FILLED — PENDING OWNER/REVIEWER CONFIRMATION。

### G6-007 — 第二个 Album 表静默丢弃（P2）→ CLOSED

- 选择"fail-closed"方案：`parse_album_table` 重构为 seek → table → done
  状态机；第一个表结束后，任何后续（围栏外）匹配 Album 表头的行 →
  以**精确行号**报错（含"合并表格或移入围栏代码块"的指引）。
- 新增测试：`test_g6007_second_live_table_fails_with_line_number`
  （断言错误信息含准确行号）、`test_g6007_fenced_second_table_allowed`
  （围栏内示例表不受影响）。

## Verification

| Command | Result |
|---|---|
| `python3.13 -m unittest test_daily_pick`（3.13.12） | **54 tests — OK**（0 fail / 0 skip） |
| `python3.9 -m unittest test_daily_pick`（3.9.6） | **54 tests — OK**（0 fail / 0 skip） |
| PyYAML（隔离 dev venv）解析 `openai.yaml` | interface 结构 PASS |
| T6.9 隔离 ZIP 构建/解压/功能验证 | whitelist 精确匹配 + exit 0 + tempdir 删除 |
| `git diff --check`（Base..HEAD） | 通过 |
| `git status`（提交后） | clean |

测试数：39 → **54**（新增 16 项，更新 3 项断言以匹配被接受的协议修正；
无删除、无弱化、无 skip）。完整输出：`reviews/stage-06/TEST_RESULTS.txt`。

## Deviations

1. 测试 `test_ac26_pinned_selection_vector` 的固定向量随协议修正更新
   （G6-001 要求删除 consumed_picks，旧向量按定义失效）——属跟随已接受
   修复的必要更新，非弱化。
2. `openai.yaml` validator 用 PyYAML 替代（本机无 Codex quick_validate.py）；
   PyYAML 仅存在于隔离 dev venv，未进入 OMDA 任何运行时路径。
3. 治理计划 §C.7 加注"草稿已被 Owner 原稿取代"（状态注记，不改变已批准
   计划的任务语义）。

## Residual Risks / Open Items

- **AC-30**：EXECUTOR_FILLED — PENDING OWNER/REVIEWER CONFIRMATION
  （第 20–21 行整合句为重点复核对象）。
- **AC-12**：Codex 实装实测仍需 Owner/朋友试用（元数据与路径结构已按
  G6-005 修正并通过模拟安装测试）。
- 无其他已知偏离。

## Executor Conclusion

**READY_FOR_REVIEW** — G6-001 ~ G6-007 逐条关闭；54 项测试在 Python
3.13.12 与 3.9.6 双双通过。Executor 停止，等待 GPT-5.6 Sol 复审；未合并、
未打标签、未 push、未发布、未保留分发包。

---

# Re-review 1 修复轮 — G6-R1-001 ~ G6-R1-003 + AC-30 措辞

> 被审 candidate：`64b805e6518462ed6346aa7a3fd8a87cac277cdd`
> Reviewer checkpoint（本轮直接父提交）：`ceeec1074966cfbe6865f05658607bae641fe5c0`
> Verdict：`reviews/stage-06/REVIEW_VERDICT.md` §Re-review 1（CHANGES_REQUESTED）
> 范围纪律：仅修复本轮指定问题；G6-001/002/005 已解决的实现未改动；
> 3×3 Core 未触碰；未顺便重构。

## G6-R1-001 — 规范化等价记录的顺序依赖 → CLOSED

- `merge_sources()` 改为按**文档化 canonical content 顺序**（每条记录的
  `canonical_order`，即 `_content_record_sort_key` 排序名次）迭代各来源
  记录——展示 Artist/Album 不再由文件行序或 `occs[0]` 的原始顺序决定。
- 新增 `test_r1001_canonical_equivalent_duplicates_permutation_invariant`：
  `A Ref | Alpha` 与 `a ref | Alpha.`（规范化同一身份）在两种排列下
  → 展示字段（断言为 canonical 的 "A Ref"/"Alpha"）、完整历史 JSON、
  输出字节完全一致。

## G6-R1-002 — 跨语言第二张表检测 → CLOSED

- `parse_album_table` 表内阶段：在把任何行当数据之前，先用
  `_header_matches(cells, required_fields)` 做**语义表头检查**（任一支持
  语言/别名形式）；第一张 live table 之后再次出现有效表头 → fail-closed
  并报精确行号，绝不作为 Album。
- 新增三个方向测试：`test_r1002_english_then_chinese_header_fail_closed`、
  `test_r1002_chinese_then_english_header_fail_closed`、
  `test_r1002_blank_line_only_separation_fail_closed`，均断言错误含
  准确行号（含两表之间仅空行的情形）。

## G6-R1-003 — 历史日期与时间的语义校验 → CLOSED

- 新增 `_parse_iso_date`（严格真实日历日期 + canonical YYYY-MM-DD 形式）、
  `_parse_aware_datetime`（必须带时区的可解析 datetime）、
  `_validate_history_semantics`（对每天记录校验：day key 真实日期；
  `local_iso`/`utc_iso`/`selected_at` 为 aware datetime；`utc_iso` 偏移
  为 0；`local_iso` 日期与 day key 一致；`utc_offset` 与 `local_iso` 实际
  偏移一致）。任何失败 → ValueError → 损坏副本保留 + **exit 3**
  （load_history 在 rollback 检查之前运行，语义损坏不再误报 exit 2）。
- 新增六个测试（`test_r1003_*`）：不可能月份/日期（复现 Reviewer 探针
  `2026-99-99` + `not-a-time`）、非法 timestamp、缺时区 timestamp、
  local 日期与 day key 不一致、`utc_offset` 与 `local_iso` 不一致、
  `utc_iso` 非 UTC；每个用例断言 exit 3、corrupt copy 字节精确等于
  磁盘上的损坏内容、运行不改写历史文件。

## AC-30 文案对应修正 → DONE（Owner 确认仍待定）

- 中文 `最近读了` → `读过……之后`；英文 `Recently, after rereading` →
  `After reading`（README 已改；T6.9 验证解压包内为新文案）。
- `PREFACE_CHECKLIST.md` 已加 Re-review 1 修正记录；第 20–21 行仍处
  **等待 Owner 最终确认**状态，Executor 未宣称 AC-30 PASS。

## Verification（本轮）

| Command | Result |
|---|---|
| `python3.13 -m unittest test_daily_pick`（3.13.12） | **64 tests — OK**（0 fail / 0 skip） |
| `python3.9 -m unittest test_daily_pick`（3.9.6） | **64 tests — OK**（0 fail / 0 skip） |
| T6.9 隔离 ZIP 复验（含新文案确认） | PASS；tempdir 已删除 |
| `git diff --check`（Base..HEAD） | 通过 |
| `git status`（提交后） | clean |

测试数：54 → **64**（+10：R1-001 ×1、R1-002 ×3、R1-003 ×6；无删除/
弱化/skip；G6-001/002/005 既有测试原样保留并通过）。

## Residual Risks / Open Items

- **AC-30**：EXECUTOR_FILLED — 等待 Owner 最终确认（第 20–21 行）。
- **AC-12**：Codex 实装实测仍需 Owner/朋友试用。
- 无其他已知偏离。

## Executor Conclusion

**READY_FOR_REVIEW** — Re-review 1 指定的 G6-R1-001~003 与 AC-30 措辞
修正全部完成；64 项测试双版本全绿。Executor 停止，等待 GPT-5.6 Sol 复审；
未合并、未打标签、未 push、未发布、未保留分发包。
