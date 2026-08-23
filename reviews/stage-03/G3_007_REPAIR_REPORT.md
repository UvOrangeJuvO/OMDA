# G3-007 Repair — CHANGES_REQUESTED → 修复（2026-08-22）

- Reviewer commit：`f42ce3a5e64e9443616406daa973ace488a6b081`（`G3_007_REVIEW_VERDICT.md`，
  结论 **CHANGES_REQUESTED**，G3-007-001 ~ G3-007-006）
- 被审 candidate：`07851eb4c8cb13a3bb2a06382c74e6cba7c3c27a`
- 本轮修复范围：仅 G3-007 source/data 契约；**未动 G4 production composition、
  PushPlus、SQLite v3 migration、LLM runtime**（相对 reviewer commit 的
  `cli.py/production.py/orchestrator/storage/delivery/llm/config.py` diff = 0）
- 每项先复现 Reviewer 反例、再做最小修复、加回归测试；未删除/弱化既有测试。

## 逐项关闭证据

### G3-007-001（P1）Album 批次未绑定 Genre — CLOSED
- **复现**：20 条记录无 genre 字段；`_build_batch` 忽略 genre 使 Ambient/Bebop 批次
  完全相等；`candidates_for_genre` 重贴 genres 标签。
- **修复**：`album_candidate.schema.json` v2 增加必填 `genre_id`；`CandidateBatch`
  增加 `genre_id`；`_build_batch` 按**精确 reviewed genre_id 过滤**，空覆盖显式
  `InvalidInputError`（绝不重贴标签）；`candidates_for_genre` 返回记录的真实
  genre_id；digest 覆盖 genre 绑定；`assemble` 校验 batch 内记录 genre 一致性
  （unrelated batch 拒绝）与每个选中 genre 的批次覆盖。
- **回归测试**：`test_batch_is_filtered_to_the_requested_genre_only`（跨 genre
  负向）、`test_unknown_genre_coverage_fails_clearly`、checkpoint
  `test_no_cross_genre_record_enters_a_requested_batch`、
  `test_real_curated_packages_support_one_3x3_run`（五个真实批次 digest 互不相同）、
  `test_deterministic_3x3_selection_with_permanent_exclusion_and_shortage`
  （真实 3×3 确定性选择 + 永久排除 + 显式耗尽）。

### G3-007-002（P1）无 canonical release-group identity — CLOSED
- **复现**：20 条记录 MBID 0/20；`_identity_for` 恒 None；"证据名"测试只断言字符串
  非空。
- **修复**：**真实填充 20 个 verified MusicBrainz release-group MBID**（官方
  WS/2 API 数据准备工具 `tools/curate_mbids.py`：可联系 UA + 1.1s pacing +
  严格匹配 primary-type=Album + title/artist 规范化相等 + year 佐证 + score≥90，
  全部人工审核后提交；year 对齐 MB first-release-date）；生产记录 mbid 必填
  （schema optional + 代码层对非 demo 包强制）、duplicate mbid 拒绝；digest 覆盖
  mbid；export 拒绝缺 mbid 的生产包；source.yaml/README 记录 MBID 获取 provenance。
- **回归测试**：`test_production_record_without_mbid_is_rejected`、
  `test_duplicate_canonical_mbid_is_rejected`、`test_export_refuses_production_package_without_mbid`、
  checkpoint `test_production_records_have_unique_valid_mbid_from_validated_batch`
  （20/20 MBID 非空、唯一、identity 来自同一 validated batch）。

### G3-007-003（P1）Genre provenance/demo 未内容绑定 — CLOSED
- **复现**：Genre descriptor 无内容 digest；`is_demo` 只看 Album；空 assembly 被
  接受（is_demo=False）；registered demo Genre + production Albums → is_demo=False。
- **修复**：`GenreSourceDescriptor.content_digest`（SHA-256 over 已审 Genre 记录，
  `digest_genre_records`）；registry 记录审核时 content_digest，descriptor 不一致
  fail-closed（篡改 Genre 数据被拒）；`ValidatedSourceSet.is_demo` **跨 Genre
  descriptors 与 Album batches**；`assemble` 拒绝空/不完整 source set 并强制
  `selected_genre_ids` 逐 genre 覆盖 ≥ `required_candidates_per_genre`（3×3）。
- **回归测试**：`test_genre_content_digest_is_bound_by_registry`、
  `test_demo_status_covers_genre_descriptors_too`（assemble 层 is_demo=True）、
  `test_assemble_rejects_empty_and_incomplete_source_sets`、
  checkpoint `test_demo_genre_with_production_albums_yields_demo_source_set`（真实
  rym-sample demo Genre + production Albums → is_demo=True）、
  `test_tampered_genre_data_fails_closed_via_content_digest`（真实篡改 genres.jsonl
  → digest 不匹配拒绝）。

### G3-007-004（P1）CandidateBatch 只是 concrete side API — CLOSED
- **复现**：`AlbumSource` Port 只有 `candidates_for_genre`；`batch_for_genre` 仅
  具体 adapter 有；cache hit 未验 digest；contract 测试锁定旧方法集。
- **修复**：`AlbumSource` Port 增加 **provider-neutral `source_batch(genre) ->
  CandidateBatch`**（ADR 授权的 source-envelope 契约），`CuratedAlbumSource` 与
  `FakeAlbumSource`（contract parity）都实现；contract 测试断言方法集含
  source_batch；cache hit 返回前 `verify_batch_integrity`，无效条目删为 typed
  miss 并重建。
- **回归测试**：`tests/contract/test_ports.py`（方法集 + fake parity）、checkpoint
  `test_tampered_cache_is_a_typed_miss_on_public_port_path`（篡改缓存后经公开
  source_batch 路径返回正确数据）。

### G3-007-005（P1）生产 manifests 折叠许可层 — CLOSED（provenance 审计）
- **复现**：Album/Genre 包 blanket CC0 + MusicBrainz search URL 作 origin；
  README 全量 CC0 声明。
- **修复**：`album_source` v2 / `genre_source` v3 schema 增加 `data_derivation`
  （independently_curated | derived_from_upstream）、`upstream_license` 与四层
  `license_core_facts` / `license_supplementary_used` / `license_service_terms` /
  `license_derived_package`；数据包 manifest/README/registry 全部按四层记录
  （MusicBrainz 仅采纳 CC0 core facts；search index/tags 明确 NOT incorporated；
  web service 非商业条款声明；Wikipedia 只作验证不复制文本）；registry 绑定
  derivation/upstream_license，不一致 fail-closed。
- **回归测试**：`test_registry_verify_descriptor_mismatch_fails_closed` 新增
  derivation/upstream_license 不匹配用例；checkpoint 全链路使用真实 registry
  验证通过。

### G3-007-006（P2）RuntimeCache FIFO/TTL 不健壮 — CLOSED
- **复现**：按文件名排序淘汰（非插入序）；TTL 未校验正有限（负值立即过期、NaN
  禁用比较）；`a/b` 与 `a_b` 同文件。
- **修复**：插入序 FIFO（manifest.json 记录顺序，淘汰最先插入）；TTL 构造时强制
  正有限数；key 用 SHA-256 命名（碰撞安全）。
- **回归测试**：`test_cache_ttl_must_be_positive_finite`（0/-1/NaN/Inf/str/bool
  全部拒绝）、`test_cache_bounded_fifo_eviction_in_insertion_order`（z→a→m 淘汰 z
  非 a）、`test_cache_keys_are_collision_resistant`（a/b vs a_b 独立）。

## 验证

| 命令 | 结果 |
|---|---|
| `pytest -q -p no:cacheprovider` | **671 passed, 0 failed**（659→671；重写/合并的测试语义增强，无弱化） |
| `pytest -v`（G3_007_TEST_RESULTS.txt） | 671 passed |
| `ruff check src tests tools browser_companion` | All checks passed |
| `git diff --check` | clean |
| G4 层零改动（相对 f42ce3a，cli/production/orchestrator/storage/delivery/llm/config） | 0 文件 |
| tracked 敏感文件 | 无 |
| 未 merge / 未 tag / 未进入 G5 | 确认 |
| live 网络依赖 | 无（MBID 为一次性数据准备，`tools/curate_mbids.py` 是人工工具，非运行时 source；测试不触网） |

## 残余风险（诚实披露）

1. `tools/curate_mbids.py` 是**一次性人工数据准备工具**（贡献流程），非运行时
   组件；20 个 MBID 已于 2026-08-22 经官方 API 获取并人工审核，但 upstream
   MusicBrainz 数据随时间演进的再验证属 G5 数据许可审计范畴。
2. `assemble_validated_source_set` 的 run.py 接线（FETCH/SELECT journal 记录
   §8.8）仍属 G4 production composition；G3-007 提供证据字段与契约。
3. live MusicBrainz 路径（ODP-1）仍未定案未实现（§8.1 不变）。

---

# G3-007 Re-review 1 Repair（2026-08-23，candidate 2be8ee1）

对应 Reviewer commit：`09187426ca3f4f05eca27292fc448cc5f3ce470a`（G3_007_REVIEW_VERDICT.md
Re-review 1，结论 **CHANGES_REQUESTED**，G3-007-003/005 保持 OPEN + 新增
G3-007-007/008/009）
被审 candidate：`2be8ee110fabe9d6979f5d23a374e06bae146294`
本轮修复范围：仅 G3-007 source/data 契约；**未实施任何 G4 功能**（相对 reviewer
commit 的 cli/production/orchestrator/storage/delivery/llm/config diff = 0）。
未自行写 ACCEPTED；无需新 ADR（均在已接受 ADR-0002 内修复）。

## 逐项关闭证据

### G3-007-003（P1，保持 OPEN）selected Genre ID 未绑定 reviewed Genre 内容 — CLOSED
- **复现**：`selected_genre_ids=("phantom",)` + 自洽 batch + 真实注册 Genre
  descriptor 通过校验（phantom 不在 reviewed Genre 包中）。
- **修复**：`GenreSourceDescriptor.eligible_genre_ids`（由 GenreDatasetAdapter 从
  同一批 reviewed records 派生，eligible 记录的去重 genre_id；该 records 集即
  content_digest 覆盖的对象）；`assemble_validated_source_set` 校验
  `selected ⊆ 所有 descriptor.eligible_genre_ids 的并集`，任何 selected ID 不在
  其中即 `InvalidInputError`——调用方无法用自洽标签证明来源来自 reviewed Genre
  内容。
- **回归测试**：`test_selected_phantom_genre_is_rejected`（unit）、checkpoint
  `test_real_curated_packages_support_one_3x3_run`（selected 全部来自真实 eligible
  集）。

### G3-007-005（P1，保持 OPEN）license/provenance 层 self-asserted — CLOSED
- **复现**：改四层 license 字段或 `retrieved_at` 为伪造值 → batch digest 不变、
  registry 校验通过（这些字段既不在 digest 也不在 registry 契约）。
- **修复**：
  1. `_source_digest_fields` 扩展为**全部 immutable 字段**（display_name、
     license、origin_url、retrieved_at、dataset_version、schema_version、
     data_scope、records_file、demo、data_derivation、upstream_license、四层
     license_*）→ 任一字段变化都改变 batch/Genre digest（integrity 校验覆盖）；
  2. `RegistryEntry` 绑定**全部** immutable 字段（含 display_name/retrieved_at/
     dataset_version/data_scope/四层 license_*），`verify_descriptor` 逐字段
     比对，任何不一致 fail-closed（registry 为信任锚）；
  3. `source_registry.schema.json` v3 声明全字段。
- **回归测试**：`test_registry_verify_descriptor_mismatch_fails_closed` 参数化
  **15 个字段**逐一伪造 → 全部拒绝（unit）；digest 敏感性扩展（license 层与
  derivation 变化改变 digest）。

### G3-007-007（P1，新增）tracked machine schemas 与 runtime 契约不一致 — CLOSED
- **证据**：candidate_batch schema v1（无 genre_id/source）vs runtime v2；
  genre_source schema v3 vs 数据包/registry 声明 v1。
- **修复**：
  1. `candidate_batch.schema.json` **v2 完整**（schema_version enum ["2"]、
     genre_id、source object 全字段、candidates 条件可选字段）；
  2. `CuratedAlbumSource._batch_to_json` 序列化**先按 tracked schema 校验**
     （cache/export 边界与发布 schema 不可能漂移）；`_record_to_json` 省略
     None 可选字段使 JSON 满足 schema；
  3. Genre 包/registry 的 schema_version 统一为 **"3"**（与 genre_source schema
     一致）；album 包 schema_version="2" 与 album_source schema 一致。
- **回归测试**：`tests/unit/test_schema_version_alignment.py`——candidate_batch
  schema 版本 == BATCH_SCHEMA_VERSION、genre/album 包声明版本 == tracked schema
  版本、registry 版本一致、序列化 round-trip 过 tracked schema（版本漂移即失败）。

### G3-007-008（P1，新增）curation 工具占位 User-Agent — CLOSED
- **证据**：`tools/curate_mbids.py` 硬编码 `mailto:omda-curation@example.invalid`
  （.invalid 不可联系）。
- **修复**：工具改为从 `OMDA_MUSICBRAINZ_USER_AGENT` 环境变量读取 owner 提供的
  UA；`_validate_user_agent` 拒绝缺失、非可联系形状与占位标记（`.invalid`、
  `example.com/.org/.net`、`@example.`、localhost）；`_fetch` 接受可注入 transport
  （urllib 默认），UA 随请求头发送；仓库不再硬编码任何个人联系方式。
- **回归测试**：`tests/unit/test_curate_tool.py`——缺失/占位/非法 UA 全拒、
  owner 值通过、注入 fake transport 验证请求头携带 owner UA（**无网络**）。

### G3-007-009（P2，新增）两个集成测试不安全 — CLOSED
- **证据**：Genre tamper 测试原地修改 tracked genres.jsonl（finally 恢复）；
  cache tamper 测试复用同一 adapter（`_batch_cache` 内存命中，从不读被篡改的
  磁盘条目）。
- **修复**：Genre tamper 改为 `shutil.copytree` 到 tmp_path 再篡改**副本**；
  cache tamper 先写入/篡改磁盘缓存，再用**fresh adapter**（无内存缓存）走公开
  source_batch 路径读取被篡改条目 → 验 digest 失败 → typed miss 重建。
- **回归测试**：两个测试重写（见 checkpoint）。

## 验证

| 命令 | 结果 |
|---|---|
| `pytest -q -p no:cacheprovider` | **693 passed, 0 failed**（671→693，全部为新增/增强，无删除/弱化） |
| `pytest -v`（G3_007_TEST_RESULTS.txt） | 693 passed |
| `ruff check src tests tools browser_companion` | All checks passed |
| `git diff --check` | clean |
| G4 层零改动（相对 0918742） | 0 文件 |
| tracked 敏感文件 | 无 |
| 未 merge / 未 tag / 未进入 G5 / 未写 ACCEPTED | 确认 |
| live 网络依赖 | 无（curation 工具测试用注入 transport；工具本身需 owner 提供 UA） |

## 残余风险（诚实披露）

1. `tools/curate_mbids.py` 运行需 owner 设置 `OMDA_MUSICBRAINZ_USER_AGENT`；20 个
   已提交 MBID 的 upstream 再验证属 G5 数据许可审计。
2. `assemble_validated_source_set` 的 run.py 接线（§8.8 journal）仍属 G4。
3. ODP-1（live MusicBrainz 路径）未定案未实现（§8.1 不变）。

---

# G3-007 Re-review 2 Repair（2026-08-23，candidate c4ae191）

对应 Reviewer commit：`600305bd66b7a8f39d23f16ffcac31a321afcdb2`（G3_007_REVIEW_VERDICT.md
Re-review 2，结论 **CHANGES_REQUESTED**，G3-007-003/007 保持 OPEN + 新增
G3-007-010/011）
被审 candidate：`c4ae1911c3f0092806da804da929f9e0d3045f93`
本轮修复范围：仅 G3-007 source/data 契约；**未实施任何 G4 功能**（相对 reviewer
commit 的 cli/production/orchestrator/storage/delivery/llm/config diff = 0）。
未自行写 ACCEPTED；无需新 ADR（均在已接受 ADR-0002 内修复）。

## 逐项关闭证据

### G3-007-003（P1，保持 OPEN）eligible Genre 集仍可伪造 — CLOSED
- **复现**：向真实注册 descriptor 的 `eligible_genre_ids` 追加 `phantom` + 自洽
  重贴 batch + 重算 batch digest → assemble 接受。
- **修复**：eligible 集绑定**确定性摘要**——`GenreSourceDescriptor.eligible_digest`
  = SHA-256 over canonical JSON of sorted eligible IDs（`digest_genre_ids`）；
  `GenreDatasetAdapter.descriptor()` 从同一批 reviewed records 派生 eligible 集并
  计算 digest；`registry` genre entry 记录**审核时的 eligible_digest**，
  `verify_descriptor` 比对（伪造 eligible 集 → 自洽 digest 不匹配 或 registry
  不匹配 → fail-closed）；`assemble` 额外校验 descriptor 自洽
  （`digest_genre_ids(eligible) == eligible_digest`）。
- **回归测试**：`test_forged_eligible_genre_ids_are_rejected`（伪造 tuple + 伪造
  digest 两条路径均拒绝）、`test_genuine_descriptor_still_validates`。

### G3-007-007（P1，保持 OPEN）反序列化绕过 tracked schema — CLOSED
- **复现**：未知顶层字段的 batch 被解析并通过；cache 中 schema_version `999`
  （digest 重算）被 `source_batch()` 返回。
- **修复**：`_batch_from_json` 构造对象**前**先 `_validate_record("candidate_batch",
  payload)`（additional_fields 默认 reject → 未知字段拒绝；schema_version enum
  ["2"] → `999` 拒绝；嵌套 source/candidates 结构错误拒绝）；`verify_batch_integrity`
  额外要求 `schema_version == BATCH_SCHEMA_VERSION`（运行时拒绝不支持的版本）。
- **回归测试**：public cache-hit 路径——未知顶层字段 / schema_version `999` /
  malformed nested source / malformed candidates → 全部 typed miss（重建，不返回
  非法条目）；`test_verify_rejects_unsupported_schema_version`。

### G3-007-010（P1，新增）digest 编码歧义 — CLOSED
- **复现**：`|`/`\x1f` 拼接使 `(title="A|B", artist="C")` 与 `(title="A",
  artist="B|C")` 同 digest（Genre name/family 同理）。
- **修复**：**canonical JSON 编码**替代分隔符拼接——`_canonical_json`
  （`json.dumps(sort_keys=True, separators=(",",":"), ensure_ascii=False).encode("utf-8")`）；
  `digest_batch` = SHA-256 over canonical JSON object（schema/query-policy/genre/
  source 字段数组/records 数组）；`digest_genre_records` = canonical JSON array；
  `digest_genre_ids` = canonical JSON array。任意分隔符字符在 free-text 字段中
  都不可能再与结构边界混淆。
- **回归测试**：`test_digest_batch_collision_for_separator_in_free_text` 与
  `test_digest_genre_records_collision_for_separator_in_free_text`（`|` 与 `\x1f`
  两组碰撞对，均不同 digest）。

### G3-007-011（P1，新增）Album batch 可声称 Genre source — CLOSED
- **复现**：真实 Ambient batch 的 source 换为真实注册 Genre descriptor + 重算
  digest → assemble 接受。
- **修复**：三层拒绝——①`candidate_batch.schema.json` `source.kind` enum 收窄为
  `["album"]`（schema 层）；②`verify_batch_integrity` 要求
  `source.kind == "album"`（领域层）；③`assemble` 在 registry lookup 前经
  verify 拒绝（assembly 层）。
- **回归测试**：`test_genre_kind_batch_is_rejected_by_domain_and_assembly`、
  `test_schema_rejects_genre_kind_source`。

## 验证

| 命令 | 结果 |
|---|---|
| `pytest -q -p no:cacheprovider` | **704 passed, 0 failed**（693→704，全部新增/增强，无删除/弱化） |
| `pytest -v`（G3_007_TEST_RESULTS.txt） | 704 passed |
| `ruff check src tests tools browser_companion` | All checks passed |
| `git diff --check` | clean |
| 独立碰撞测试（010） | 2 passed（分隔符字符字段碰撞对） |
| G4 层零改动（相对 600305b） | 0 文件 |
| tracked 敏感文件 | 无 |
| 未 merge / 未 tag / 未进入 G5 / 未写 ACCEPTED | 确认 |

## 残余风险（诚实披露）

1. 新编码（canonical JSON）改变了既有 digest 值——registry 已同步更新（content/
   eligible digests）；任何外部消费者按旧 `|` 编码校验将失效（仓库内无）。
2. `assemble_validated_source_set` 的 run.py 接线（§8.8 journal）仍属 G4。
3. ODP-1（live MusicBrainz 路径）未定案未实现（§8.1 不变）。
