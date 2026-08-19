# Gate G1 Repair Report

> 作者：DeepSeek V4 Flash（Executor）
> 日期：2026-08-19
> 依据：`reviews/stage-01/REVIEW_VERDICT.md`（GPT-5.6 Sol，CHANGES_REQUESTED，commit `4bce3d3d1a4ddaaba1bab5e783ee239cefdf870a`）
> G1 Base：`5361b64d544c3134be9ba2b25a041ff146da613a`
> 原 G1 Candidate：`4830c53ba163631220a83d985cd1a385362ee17d`
> 修复后新 Candidate：提交后由 Executor 在最终聊天报告中给出精确 SHA（`PROJECT_STATE.json` 的 `candidate_commit` 保持 `null`，避免自引用）
> 本轮未实现 Recommendation Core / RYM / MusicBrainz / LLM / PushPlus；未修改 `REVIEW_VERDICT.md`。

## 修复摘要

| Finding | 严重度 | 状态 | 修复 commit |
|---|---|---|---|
| G1-001 官方 3×3 历史无法原子提交 | P0 | CLOSED | `79d2be5` |
| G1-002 成功交付证据可被覆盖 | P0 | CLOSED | `79d2be5` |
| G1-003 Schema 静默接受拼错字段 | P1 | CLOSED | `6f6f0b5` |
| G1-004 不可变声明强于实际类型 | P2 | CLOSED | `79d2be5` + `6f6f0b5` |

---

## G1-001 — Official 3×3 history cannot be committed atomically（P0，CLOSED）

- **根因**：`HistoryPort` 只有逐行 `record_genre_pick()`/`record_album()`，各自独立事务；Orchestrator 无法一次性提交 3 个 Genre picks + 9 个 Album + `HISTORY_COMMITTED`；中途失败会留下部分官方历史（cooldown 被消耗、部分 Album 被永久排除）。
- **修改**（commit `79d2be5`）：
  1. `ports/history.py`：新增唯一官方历史写路径 **`commit_history(run_id, genre_picks, album_identities, committed_at)`**；逐行 `record_genre_pick`/`record_album` **移出 Port**（不再公开），防止 Orchestrator 走逐条提交。
  2. `ports/domain.py`：新增不可变 `GenrePickRecord(pick_index, genre_id)`。
  3. `storage/sqlite_history.py`：`commit_history` 在**单个 `with self._conn` 事务**内写入全部 picks + 全部 albums + `HISTORY_COMMITTED` journal；任一步失败整体回滚，三类记录全部保持原状。
  4. `tests/fakes/InMemoryHistory`：先全量预检冲突（重复 pick_index / 重复 album_id）再一次性变更，实现相同的 all-or-nothing 语义。
- **验收证据（新测试）**：
  - `test_commit_history_writes_all_three_areas_atomically`：成功路径三区齐写。
  - `test_commit_history_failure_leaves_all_areas_unchanged`：预置冲突 album 后中途失败 → `latest_pick_index==0`、无新排除、无 `HISTORY_COMMITTED`（SQLite 失败注入）。
  - `test_commit_history_mid_batch_duplicate_pick_rolls_back`：pick 冲突同样整体回滚。
  - `test_inmemory_history_commit_is_all_or_nothing`：fake 侧冲突预检后零变更。
  - `test_no_public_per_row_history_write_methods`：公开 API 不再暴露逐行写。
- **状态**：**CLOSED**。

## G1-002 — A later write can overwrite immutable successful delivery evidence（P0，CLOSED）

- **根因**：`save_delivery_receipt` 使用 `INSERT OR REPLACE`（SQLite REPLACE = 删除重建），fake 直接字典赋值；冲突写入可把已成功的 `ok` 收据覆盖为 `failed`，导致恢复逻辑误判并重复推送。
- **修改**（commit `79d2be5`）：
  1. 删除 `INSERT OR REPLACE`；`save_delivery_receipt` 改为：键不存在 → 插入并返回；**精确重放（字段全等）→ no-op 返回原记录**；**冲突 → 抛 `InvariantFailureError`，原记录不变**（fail closed）。
  2. 返回类型改为 `DeliveryReceipt`（权威存储记录）；成功证据永不被 failed/不同 run 覆盖；失败尝试走 journal（G4 落实），不落收据覆盖路径。
  3. SQLite 与 `InMemoryHistory` 语义逐字对齐（同一套冲突规则与异常类型）。
- **验收证据（新测试）**：
  - `test_delivery_receipt_exact_replay_is_noop`：精确重放返回原记录。
  - `test_delivery_receipt_conflict_fails_closed`：不同 run 冲突、success→failed 覆盖尝试均抛 `InvariantFailureError`，原 `ok` 收据逐字节不变。
  - `test_inmemory_receipts_immutable_exact_replay_and_conflict`：fake 侧同语义（契约测试）。
- **状态**：**CLOSED**。

## G1-003 — Schema validation silently accepts misspelled fields（P1，CLOSED）

- **根因**：`_validate_fields` 只校验声明字段，未知键一律放行；`validate_record` 文档明确"forward-compatible"；`genre_cooldown_pick`、`canoncial_id`、`delivery.chanel` 均可静默通过。
- **修改**（commit `6f6f0b5`）：
  1. Schema 显式声明 unknown-field policy：顶层与嵌套 object 均支持 `"additional_fields": "reject" | "allow"`，**默认 `reject`**（严格拒绝未知字段，报完整字段路径 + 记录位置）；需要前向扩展时显式 opt-in `"allow"`（版本化、可审查）。
  2. 非法 policy 值抛 `SchemaError`。
  3. 删除旧测试 `test_unknown_extra_fields_are_forward_compatible`（"所有 unknown 都通过"）。
- **验收证据（新测试）**：
  - `test_unknown_extra_fields_are_rejected_with_full_path`（genre `famliy`，含 location）
  - `test_album_misspelled_canonical_field_is_rejected`（`canoncial_id`）
  - `test_config_misspelled_semantic_field_is_rejected`（`genre_cooldown_pick`）
  - `test_nested_misspelled_field_is_rejected_with_path`（`delivery.chanel`）
  - `test_nested_plan_item_misspelled_field_is_rejected`（`genres[0].famly`）
  - `test_opt_in_additional_fields_allow_passes_extension`（显式扩展机制通过）
  - `test_invalid_additional_fields_policy_is_schema_error`
- **状态**：**CLOSED**。

## G1-004 — Immutability claims are stronger than the actual domain types（P2，CLOSED）

- **根因**：frozen `JournalEntry.detail` 内是可变 dict；`excluded_album_identities()` 返回可变 set 却自称不可变。
- **修改**：
  1. `JournalEntry.detail` 构造时转为 `MappingProxyType`（只读映射），类型标注 `Mapping[str, Any] | None`；SQLite 存储前 `json.dumps(dict(detail))` 适配（commit `79d2be5`）。
  2. `excluded_album_identities()` 返回 **`frozenset[AlbumIdentity]`**，SQLite 与 fake 签名一致（commit `79d2be5`）。
  3. 类型签名同步（`domain.py`、`history.py`、`fakes`、`sqlite_history.py`）。
- **验收证据**：`test_journal_detail_is_immutable_mapping`（外部 dict 突变不影响快照；`detail[...]=` 抛 TypeError）；各 `excluded_album_identities` 断言改为 `frozenset(...)`。
- **状态**：**CLOSED**。

---

## 新增测试清单（共 12 项新增，68 项全绿）

Batch A（G1-001/G1-002）：`test_commit_history_writes_all_three_areas_atomically`、`test_commit_history_failure_leaves_all_areas_unchanged`、`test_commit_history_mid_batch_duplicate_pick_rolls_back`、`test_no_public_per_row_history_write_methods`、`test_delivery_receipt_exact_replay_is_noop`、`test_delivery_receipt_conflict_fails_closed`、`test_inmemory_history_commit_is_all_or_nothing`、`test_inmemory_receipts_immutable_exact_replay_and_conflict`、`test_journal_detail_is_immutable_mapping`
Batch B（G1-003/G1-004）：`test_unknown_extra_fields_are_rejected_with_full_path`、`test_album_misspelled_canonical_field_is_rejected`、`test_config_misspelled_semantic_field_is_rejected`、`test_nested_misspelled_field_is_rejected_with_path`、`test_nested_plan_item_misspelled_field_is_rejected`、`test_opt_in_additional_fields_allow_passes_extension`、`test_invalid_additional_fields_policy_is_schema_error`

## 实际运行检查

| 命令 | 结果 |
|---|---|
| `git branch --show-current` | `exec/g1-foundation` |
| `git rev-parse HEAD`（开始时） | `4bce3d3d1a4ddaaba1bab5e783ee239cefdf870a`（含 Reviewer commit） |
| `git status --short`（开始时） | 空（干净） |
| `pytest -v`（保存至 TEST_RESULTS.txt） | **68 passed, 0 failed, 0 skipped, 0 error** |
| `ruff check src tests` | All checks passed |
| `git diff --check` | clean |
| `git status --short`（修复提交后） | 空（干净） |

## 修复范围声明

仅修改：History/domain Port 契约与 fakes、SQLite history adapter、schema validator 与相关测试、测试证据、治理状态。未实现 Recommendation Core / RYM / MusicBrainz / LLM Provider / PushPlus；未修改或删除 `REVIEW_VERDICT.md`；未进入 G2。

## Executor Conclusion

**READY_FOR_REVIEW**（待 GPT-5.6 Sol 对修复后新 candidate SHA 复审；verdict 仅对新 SHA 有效）
