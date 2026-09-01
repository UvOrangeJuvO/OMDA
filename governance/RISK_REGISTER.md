# OMDA Risk Register

> 维护者：Executor（DeepSeek V4 Flash）；重大风险须升级 Owner/Reviewer。
> 更新：2026-08-29（G5 Release Audit 修复轮）。优先级含义：P0 数据损坏/安全/核心
> 语义错误，绝对阻断；P1 可复现功能错误/架构违约，阻断；P2 可维护性/小风险
> （OPH §8.3）。
> 每项状态均以精确 test/report/ADR 引用为证据（G5-008 核对）。

| ID | 优先级 | 风险 | 证据与状态 | 状态 |
|---|---|---|---|---|
| R-001 | P0 | 失败/歧义交付污染或重复官方历史 | **已缓解**：ADR-0001（接受的 at-most-one 补偿协议）；`test_ac3_begin_rejects_mismatched_binding`/`test_ac4_save_receipt_rejects_unbound_attempt`（G4-002C/002F 绑定）；`test_g5_class7_crash_matrix_real_sqlite`（G5-003，9 个崩溃窗口全在真实 SQLite 上断言 0-or-3/0-or-9 与零重推）；`test_g5_class6_commit_failure_recovers_without_redelivery` | **CLOSED** |
| R-002 | P0 | 凭据、cookie 或浏览器 profile 进入 Git/模型上下文 | **已缓解**：`.gitignore`（G1）；G5-004 强化扫描器——tracked-path denylist（cookie jar/browser profile/runtime DB/.env/keys/netrc/credential 文件）+ 文本 content patterns + 二进制安全 + 脱敏输出；`tests/unit/test_scan_secrets.py` 正负 fixtures（含 Reviewer 复现的 force-add 场景）；仓库扫描 **0 命中** | **CLOSED** |
| R-009 | P0 | 虚假声明「外部推送与本地 SQLite 绝对原子」 | **已缓解**：ADR-0001 §4 接受 at-most-one 协议 + delivered-but-not-committed 恢复；禁止「绝对原子」表述写入 recovery 文档 | **CLOSED** |
| R-003 | P1 | Genre 等权被 popularity/LLM 质量分/Tier 概率替代 | **已缓解**：`test_core_genre.py::test_selection_without_popularity_signal_is_equal_opportunity_smoke`、`test_sort_genres_is_stable_by_genre_id`（G2 D.3）；选择路径无 popularity 输入（HANDOFF §2） | **CLOSED** |
| R-004 | P1 | canonical Album 错配导致重复推荐或错误永久排除 | **已缓解**：`test_core_album.py`（canonical 命名空间、ambiguous 永不破坏性排除、不同 release 不合并，G2 T2.4）；G5-002 在真实选择路径证明永久排除生效（`test_g5_class3_album_exclusion_operates_in_selection_path`/`test_g5_class3_album_shortage_is_explicitly_caused_by_exclusion`） | **CLOSED** |
| R-005 | P1 | RYM 布局/会话变化破坏 enrichment | **已缓解为限制**：v0.1 无 live RYM 调用（ODP-1 未定案未实现，ADR-0002 §8-1）；原 RYM 派生 demo 包已重写为独立创作 fixture（`data/genres/demo-omda`，G5-005），运行时不再依赖 RYM | **CLOSED（v0.1 范围）** |
| R-006 | P1 | 外部数据（MusicBrainz/上游）许可或条款风险 | **已缓解**：G5-005 Owner 决策 **Apache-2.0**（`LICENSE` + SPDX）；demo 包 re-author 消除无依据的 RYM CC0 声明；MusicBrainz 声明与官方数据许可/服务条款一致（RELEASE_AUDIT §3 确认）；`LICENSES.md` 完整四层 provenance + build/dev/transitive 版本化清单 | **CLOSED** |
| R-008 | P1 | LLM 越权选择或外部文本注入被当作指令 | **已缓解**：ADR-0002 D8——v0.1 为 deterministic/no-LLM runtime（`test_deterministic_runtime_never_invokes_llm`、`test_ac8_deterministic_full_pipeline_no_llm_and_marker`）；config `llm.mode` 仅允许 `deterministic`（provider 值 config 校验 fail-closed）；未来 provider 需独立 adapter + 新 Gate | **CLOSED（v0.1 范围）** |
| R-010 | P1 | seed 或输入数据版本未记录导致选择不可复现 | **已缓解**：run journal 记录 seed + config fingerprint + 输入版本（G2-006/G2-008）；FETCHED journal 记录 source_evidence（source_id/digest/schema/query-policy/package version，ADR-0002 §8.8，`test_ac1_...`）；`test_same_seed_reproduces_selection` | **CLOSED** |
| R-007 | P2 | Executor 与 Reviewer 角色坍塌 | **持续控制**：exact-SHA Gate 协议、独立 verdict 工件、Executor 永不写 ACCEPTED（G0–G5 全程执行；本轮同样只写 READY_FOR_REVIEW） | **MITIGATED（持续）** |
| R-011 | P2 | 等权统计测试因 flaky 阈值误报 | **已缓解**：非阈值化分布检验 + 固定 seed 基准（G2 D.3） | **CLOSED** |
| R-012 | P2 | 时区/「每日」边界含糊导致跨日语义错误 | **已缓解**：时间戳一律 UTC ISO 8601（T1.2 schema format + T1.5 存储 + G4 运行层） | **CLOSED** |
| R-013 | P2 | 社区贡献摩擦 | **已缓解**：版本化 schema、行/字段级错误信息、`CONTRIBUTING.md`（G5-007）、贡献演练 | **CLOSED** |

## 已知非阻塞限制（下一 release-audit 候选跟踪，不阻断 G5 修复轮）

1. curated 数据包规模有限（5 Genre × 4 Album）：真实 3×3 可完成，但连续多日运行
   会快速耗尽（显式失败路径已测：`test_g5_class3_album_shortage_...`、
   `test_ac9a_second_run_excludes_committed_mbids_without_repeat`）；扩充属 G5 后
   贡献流程。
2. v0.1 交付物无 LLM narrative——ADR-0002 D8 的有意取舍；未来 provider 模式需
   独立实现 + 版本化配置 + Gate 接受。
3. ODP-1（live MusicBrainz tag-search）仍未定案未实现（ADR-0002 §8-1）；AC-9B
   条件未启用。
4. PushPlus 无文档化 definitive 类别：全部非 200 均按 ambiguous 保守处理
   （ADR-0001 §9/§15-3）。
5. `pyproject` 代码许可已于 2026-08-29 由 Owner 决策为 Apache-2.0（R-006 关闭）。

## 风险升级规则

- 触发 BLOCKED_ARCHITECTURE 的信号（OPH §6）：改产品不变量/推荐语义、改公开
  Schema/持久化/plugin contract、引入新数据库/框架/大型运行时/浏览器自动化依赖、
  改历史提交时机、访问策略涉及反爬绕过、新增未明确许可的数据集、不可逆迁移或删
  用户数据。
- 任一 P0/P1 未缓解则对应 Gate 不得 ACCEPTED（SPEC §10）。截至本更新，所有
  P0/P1 均已关闭或显式升级为 v0.1 范围限制；G5 评审状态 **READY_FOR_REVIEW**。
