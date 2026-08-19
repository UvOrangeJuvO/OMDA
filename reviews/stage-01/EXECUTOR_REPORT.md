# Gate G1 Executor Report — Foundation

> 作者：DeepSeek V4 Flash（Executor）
> 日期：2026-08-19
> 依据：已批准 `governance/IMPLEMENTATION_PLAN.md`（G0 ACCEPTED，candidate `4ba0d34ceb474513292edf4217d8ba58814a303c`）；Re-review 2 中披露的 P2 follow-up G0-007 已在本 Gate 处理。

## 1. Identity

| 项 | 值 |
|---|---|
| Gate | G1 Foundation（SPEC §10：schemas、config、validation、storage boundary、test infra） |
| 仓库 | `<REPO_ROOT>` |
| G0 merge commit | `5361b64d544c3134be9ba2b25a041ff146da613a`（`merge: accept gate G0 implementation plan`，parents `8a2e8207…` + `570d01a…`） |
| G0 tag | `gate-g0-accepted` |
| G1 base SHA（完整） | `5361b64d544c3134be9ba2b25a041ff146da613a`（合并后的 main） |
| G1 candidate SHA（完整） | 提交后由 Executor 在最终聊天报告给出精确值；`PROJECT_STATE.json` 的 `candidate_commit` 置 `null` 避免自引用（延续 G0 已授权处理） |
| 分支 | `exec/g1-foundation`（从合并后 main 创建） |
| 开始工作区状态 | clean（`git status --short` 空输出） |
| 结束工作区状态 | clean（提交后核验） |

## 2. Scope / Non-goals

**实际范围**（已批准计划 G1 六任务）：
- T1.1 仓库骨架与工程基线（pyproject、包布局、ruff/pytest 配置）
- T1.2 版本化 Schema 与校验器（10 类记录 schema + 纯标准库校验器）
- T1.3 分层配置（默认 < 文件 < 运行时覆盖，schema 校验，语义字段 ADR 标记）
- T1.4 最小 Port protocols 与领域错误分类（6 Port + SPEC §8 八类领域错误 + fakes）
- T1.5 SQLite runtime Adapter（实现 HistoryPort，含 journal；事务、迁移 v1、append-only）
- T1.6 测试基建与 fixtures（确定性 seed 工具、fixtures 数据集、conftest、property 骨架）

**明确 Non-goals**：G1 未实现 Recommendation Core 选择逻辑、真实 RYM/MusicBrainz/LLM/PushPlus 适配器（属 G3/G4）；未引入第三方运行时依赖；SQLite 仅 runtime state，未承载任何社区数据。

## 3. Commits and Changes

| Commit | Message | 内容 |
|---|---|---|
| `521201b…` | chore(g1): begin G1, apply accepted P2 follow-up G0-007 | PROJECT_STATE→G1/IN_PROGRESS；计划 T2.6 引用 T1.6→T1.4；T1.4 明确 journal 归属决策 |
| `ed2715a…` | feat(g1): establish repository skeleton and tooling (T1.1) | pyproject.toml、src/omda 包布局、冒烟测试 |
| `717f86d…` | feat(g1): add versioned schemas and validator (T1.2) | data/schemas/*.schema.json ×10、validator.py、schema 测试 |
| `e61b657…` | feat(g1): add layered configuration system (T1.3) | config.py、config 测试 |
| `fe75a00…` | feat(g1): define port protocols and domain errors (T1.4) | ports/（6 Port + 领域值 + 错误分类）、fakes、契约测试 |
| `ab10dcd…` | feat(g1): add sqlite runtime adapter implementing HistoryPort (T1.5) | sqlite_history.py、SQLite 测试 |
| `461400a…` | feat(g1): add seed tooling, fixtures and test scaffolding (T1.6) | seed.py、conftest、fixtures、property 骨架 |
| handoff | docs(g1): propose foundation review package | 本报告 + TEST_RESULTS + RISK_REGISTER 状态 + PROJECT_STATE |

## 4. Architecture Impact

- **依赖方向**：Orchestrator（尚未实现）→ Core/Ports；Adapters 实现 Ports。T1.5 的 `SqliteHistory` 显式实现 `HistoryPort`（契约在前，实现在后，T1.4 先于 T1.5）。
- **Core 纯净性**：G1 未创建 Core 模块；ports/domain.py 的值类型为不可变 dataclass，供 G2 使用；无任何 vendor/persistence/network 依赖进入领域层。
- **契约边界**：六 Port 形状由 `tests/contract/test_ports.py` 锁定（方法集断言），G3/G4 实现与 G2 Core 均不得漂移。
- **数据保护**：`SqliteHistory` 为 append/read-only，测试断言无 delete/drop/clear/reset 方法（SPEC §4/§9）。
- **真源**：Schema 定义位于 `data/schemas/`（Git 可 diff 文本）；SQLite 仅 runtime。

## 5. Product Invariant Matrix

| 不变量 | 状态 | 证据 |
|---|---|---|
| Genre 等权（无 popularity/tier/LLM 分） | N/A（G2 实现） | 计划 A.3 I-1；G1 无选择逻辑 |
| cooldown = 30 picks（p+31 恢复） | N/A（G2） | 计划 A.3 I-2 |
| family diversity 是集合约束 | N/A（G2） | 计划 A.3 I-3 |
| Album 永久排除 + run 内去重 | PARTIAL | `HistoryPort.excluded_album_identities()` 与 `SqliteHistory` 已提供排除集存储（T2.4 消费）；匹配逻辑属 G2 |
| 每 Genre 3 张 / ≥1 张 ≥2010 | N/A（G2） | 计划 A.3 I-5 |
| rating 维度独立、权重/缺失可配置 | N/A（G2） | 计划 A.3 I-6 |
| LLM 只解释，确定性 Core 选择 | N/A（G2/G4） | LLM Port 仅 `generate_narrative`（解释性） |
| RYM 正常会话 + 薄 Companion | N/A（G3） | 计划 A.3 I-8 |
| 文本真源，SQLite 仅 runtime | **PASS** | schema 在 `data/schemas/`；`SqliteHistory` 只落 `var/` 类路径；测试验证迁移/表结构 |
| DELIVER 成功后才 COMMIT HISTORY | N/A（G2/G4） | journal/history/receipt 表已就绪（T2.6 消费） |

## 6. G1 Acceptance Matrix（对照已批准计划 G1 任务验收标准）

| 任务验收标准 | 状态 | 证据 |
|---|---|---|
| T1.1：干净 venv 可安装并收集测试；无未忽略 secrets 模式 | PASS | `pip install -e .` 成功；pytest 收集 56 项；`.gitignore` 含 `.workbuddy/`、`var/*`、`*.sqlite3` 等 |
| T1.2：每类记录校验通过/报具体字段行；schema 版本号随迁移递增 | PASS | 19 项 schema 测试；畸形样例报字段+location；`schema_version` 整数且 ≥1 |
| T1.3：默认值、覆盖优先级、非法值拒绝 | PASS | 7 项 config 测试；`semantic_overrides()` 标记 ADR 敏感字段 |
| T1.4：G2 无任务依赖 G3 首现契约；错误分类不泄漏供应商细节 | PASS | 契约测试断言 6 Port 方法集 + 八类领域错误；fakes 供 G2 |
| T1.5：写入可审计；迁移可检测可备份；社区真源不落 SQLite；实现依附契约 | PASS | 10 项 SQLite 测试；迁移 v1 幂等；append-only 断言；`user_version` 可检测 |
| T1.6：任何测试可用 `--seed` 复现；live 网络非必需 | PASS | seed 确定性测试 5 项；全测试无网络调用 |

## 7. Verification

| 命令 | 结果 |
|---|---|
| `pytest -v`（保存至 TEST_RESULTS.txt） | **56 passed, 0 failed, 0 skipped, 0 error**（0.18s） |
| `ruff check src tests` | All checks passed |
| `git diff --check` | clean |
| `git status --short`（提交前/后） | 仅本 Gate 声明的文件 / 空 |
| `pip install -e .` | 成功（无第三方运行时依赖） |

## 8. Failure and Recovery

G1 无交付链路；聚焦存储层恢复语义（G2/G4 消费）：
- 事务原子性：重复主键写入失败时整体回滚，无部分写入（`test_transaction_rolls_back_on_constraint_violation`）。
- 迁移：新库一步到位 v1；重复打开幂等。
- 数据保护：无删除/重置 API；真实 history/receipt 不可被当作缓存重建。
- 崩溃恢复：journal 按 journal_id 单调追加，`journal_after()` 支持断点续读（G2 T2.6 崩溃重放基础）。

## 9. P2 follow-up（G0-007）处理证据

1. **T2.6 过期引用**：已从 `T1.6 定义的 Port 契约` 修正为 `T1.4 定义的 Port 契约`（commit `521201b`，plan §C.2/T2.6）。
2. **journal 归属决策**：**run-journal 操作纳入 `HistoryPort`**，不设独立 `RunJournalPort`。理由：journal 与官方 history 在同一 SQLite runtime 存储与事务边界内（T1.5）；crash-recovery contract test 需在同一抽象内原子核对 journal 状态与 history 写入（delivered-but-not-committed 窗口）；独立 Port 无独立消费者，违背最小接口原则。实现证据：`ports/history.py` 的 `append_journal/journal_after` 与 `record_genre_pick/record_album` 同属一个 Protocol，`SqliteHistory` 在同一事务连接内实现二者。该决策未改变已接受契约的 Port 集合，仅明确内部边界（plan §T1.4 已记录，G0-007 明确允许两种选择）。

## 10. Deviations / Dependencies / Licenses

**偏差**：
1. `candidate_commit` 在 PROJECT_STATE 中为 `null`（自引用规避，延续 G0 授权；精确 SHA 见聊天报告）。
2. YAML 配置解析未在 G1 实现（`config.py` 仅支持 JSON 文件）——计划未要求 G1 支持 YAML；作为可逆工程选择记录，G5 前如需 YAML 再评估（不影响契约）。
3. Schema 采用自研声明式 JSON schema + 纯标准库校验器，而非引入 `jsonschema` 依赖——遵循计划 H「无必要依赖」自批判；错误信息含字段与 location，满足 SPEC §3.3。

**依赖**：运行时依赖 0 个；开发依赖仅 `pytest`、`ruff`（MIT 许可）。
**许可证**：项目 `pyproject.toml` 声明 `UNLICENSED`（OD-8 待 Owner 定案，G5 处理）；fixtures 数据为虚构示例，无外部数据许可问题。

## 11. Risks and Technical Debt

- RISK_REGISTER 状态更新见 `governance/RISK_REGISTER.md`（G1 相关条目 R-002 缓解进展：secret 扫描尚未 CI 化，G5 完成；新增观测：YAML 配置缺失为已知限制）。
- 技术债：无选择逻辑（G2 交付）；无迁移降级测试（G5 备份/恢复演练覆盖）；`SqliteHistory` 单连接模型在多进程场景需复核（v0.1 单进程运行，可接受）。

## 12. Executor Conclusion

**READY_FOR_REVIEW**

G1 六任务全部完成并各自提交；56 项测试全绿、lint 全绿、diff --check 干净；G0-007 P2 follow-up 已处理并有实现证据；未写 G2 内容、未实现真实外部适配器；SQLite 未承载社区真源；真实历史数据保护已由 append-only 设计与测试固化。待 GPT-5.6 Sol 对精确 candidate SHA 出具唯一 verdict。
