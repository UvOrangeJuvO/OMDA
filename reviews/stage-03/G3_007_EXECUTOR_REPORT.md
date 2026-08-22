# G3-007 Executor Report — Curated Album Source & Source Registry（2026-08-22）

- ADR：`docs/adr/0002-production-album-source-and-runtime-boundary.md`（Accepted，
  Reviewer commit `883b86ffb3cb4cdda0216786b91ea163ae4cfce3`，§8 为绑定约束）
- 本轮单位：**G3-007 only**（窄幅重开 G3 corrective task，ADR-0002 §8.3/§8.4）
- Base：`68e3d453c7b803d2090cb1318f48e58eb18d6390`
- Reviewer checkpoint：本报告提交后置 `READY_FOR_REVIEW`，**G4 不开始**

## 范围（G3-007 source-side）

实现并测试（每项先加失败测试复现、再实现）：

| ADR §8 约束 | 交付 |
|---|---|
| §8.4 契约/校验位置 | `CandidateBatch`/`GenreSourceDescriptor`/`SourceDescriptor`/`ValidatedSourceSet`（`src/omda/ports/source.py`）；`assemble_validated_source_set` 在 FETCH 后、选择/delivery claim 前由可信边界组装校验 |
| §8.5 信任锚 = reviewed registry | `SourceRegistry`（`src/omda/sources/registry.py`）+ `data/sources/registry.jsonl`：source_id→origin/license/schema/demo/records_file；descriptor/batch 与 registry 任一不一致 fail-closed；digest 只证完整性不证真实性（self-asserted production 标签拒绝） |
| §8.2 真实非 demo 数据 | `data/genres/curated-omda/`（5 个真实 Genre）+ `data/albums/curated-omda/`（20 张真实 Album，4/genre，足够一次 3×3；MBID 留空由运行期 MusicBrainzEnricher 补全，无虚构 ID）；`rym-sample` 明确标记 `demo: true`（生产 gate 必须拒绝） |
| §8.6 curated import/export + runtime cache | `export_curated_package`/`import_curated_package`（`src/omda/adapters/contribution.py`，显式 target、demo 需 review 确认、registry 校验）；`RuntimeCache`（`src/omda/adapters/curated.py`，`var/cache/` Git-ignored、有界 FIFO、TTL、版本 keyed、可删） |
| demo-policy | album_source schema 含 `demo`；genre_source schema v2 增加可选 `demo`/`schema_version`；registry 权威 demo 判定，descriptor.demo ≠ registry.demo → fail-closed |
| provenance/license/digest | batch 内容级 SHA-256 digest（内容/来源字段敏感）；per-source license/origin/retrieved_at；`album_source`/`album_candidate`/`candidate_batch`/`source_registry` schema v1 |

## 明确禁止项核验

- **未实现/未启用 live MusicBrainz tag-search AlbumSource**（ODP-1 未定，§8.1）；
- **未开始 production PushPlus composition**；未改 G4 delivery gate / token /
  SQLite v3 / LLM runtime（`git diff -- src/omda/cli.py production.py orchestrator/
  storage/sqlite_history.py adapters/delivery.py adapters/llm.py config.py` 为空）；
- 未把 rym-sample 或虚构 Album 标记 production（rym-sample 显式 demo:true）；
- 未用空数据/全 fail-closed 冒充完成（真实 curated 数据 3×3 端到端证明存在）。

## 验证

| 命令 | 结果 |
|---|---|
| `pytest -q -p no:cacheprovider` | **659 passed, 0 failed**（630→659，+29 全为 G3-007 新增） |
| `pytest -v`（G3_007_TEST_RESULTS.txt） | 659 passed |
| `ruff check src tests browser_companion` | All checks passed |
| `git diff --check` | clean |
| tracked 敏感文件 | 无 |
| 未 merge / 未 tag / 未进入 G5 | 确认 |

## 残余风险（诚实披露）

1. **curated-omda MBID 为空**：canonical identity 依赖运行期 MusicBrainzEnricher
   强匹配补全（G3 已交付，G4 接线）；若 enrich 匹配不到，identity 保持 None（显式
   失败路径，由 G4 recovery 决策）——不虚构任何 ID。
2. **ValidatedSourceSet 的 run.py 接线（FETCH/SELECT journal 记录 §8.8）未做**：
   属于 G4 production composition，G3-007 只提供证据字段（source_id/digest/
   version）与测试；G4 接线前不可用于交付。
3. **genre_source schema v2**（新增可选 demo/schema_version）：外部硬编码 v1 的
   消费者需更新；仓库内无（659 passed）。
4. **live MusicBrainz 路径（ODP-1）未实现**：符合 §8.1 与 Owner 决策状态；批准后
   需独立实现 + coordinator/跨进程限速验收（§8.6/§8.7）。

## 下一步

- 请 GPT-5.6 Sol 对 G3-007 checkpoint（本报告 + candidate SHA）复审；
- **Reviewer 接受前不得开始 G4**（ADR-0002 §8.3）。
