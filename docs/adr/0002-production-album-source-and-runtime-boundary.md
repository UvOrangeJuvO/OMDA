# ADR-0002 — v0.1 生产 Album 候选来源、运行时边界与持久化版本对齐

- Status: **Proposed**（提交 GPT-5.6 Sol 评审；本 ADR Accepted 前不实施任何
  production code 变更）
- Date: 2026-08-22
- Gate: G4（Agent & Delivery）— 架构阻断（BLOCKED_ARCHITECTURE / ADR_REQUIRED）
- 触发 Reviewer finding：G4 Re-review 4（Reviewer commit
  `790f36f99a859da3b2578462d76e6b2cac4051ad`，verdict **BLOCKED_ARCHITECTURE /
  ADR_REQUIRED**）：
  - **G4-007B（P1，架构）** — `--deliver` 推送编造 Sample Album 并提交官方历史；
    生产 `AlbumSource` 缺失，来源选择跨越已接受的 G3/G4 边界；
  - G4-002C（P1）— 存储层绑定（begin/receipt）未按 ADR-0001 §15-5 强制；
  - G4-007C（P2）— 配置的 token 变量在省略 `--token-env` 时被忽略；
  - G4-002D（P2，治理）— SQLite `user_version=3` 与 Accepted ADR-0001 v2 边界分歧；
  - G4-002E（P2）— 生产 transport 模块文档仍把 HTTP 4xx 描述为 definitive；
  - G4-009（P2，架构）— `--deliver` 用 `_LocalEchoTransport` 冒充生产 Agent
    组合；G5 无 runtime-provider 实现任务，OD-2 属 G4。
- 触发流程：按 verdict 明确要求"stop feature implementation and submit the
  production-source/runtime ADR"——**本轮只提交本 ADR（含影响分析与验收测试设计），
  不实现 ADR、不改 Accepted 状态、不 merge、不进 G5**。

## 1. 背景与已核实事实

Reviewer 独立探针复现（`reviews/stage-04/REVIEW_VERDICT.md` Re-review 4）：

1. **G4-007B**：公共 `cli.main()` + PushPlus config + 临时官方 SQLite 存储 + 注入
   fake 网络 transport → run 返回 COMPLETE、恰一次外部调用，outbound Markdown 含
   `tuareg Sample 1 — Sample Artist (2015)`；官方历史随后含九个 ID
   （`ambient-1`、`bebop-2`、`tuareg-3`）。`src/omda/cli.py:263-272`
   `_sample_album_source` 为每个 Genre 硬编码三条编造记录；`data/genres/README.md`
   明确 `rym-sample` 是"illustrative 4-record subset, not a full RYM mirror"；
   仓库无任何生产 `AlbumSource` 实现。
2. **G4-002C**：`begin_delivery_operation` 对既有 key 返回既有行时不校验
   run_id/channel 绑定（复现：`run-a/shared/markdown/digest-a` 后
   `run-b/shared/pushplus/digest-a` 被接受为 created=False）；`save_delivery_receipt`
   接受任意 caller 提供的非空 attempt_id（复现：`shared-key#999` 无对应 attempt 仍
   存储成功）。
3. **G4-002D**：实现 `_SCHEMA_VERSION = 3`，而 Accepted ADR-0001 §8 以
   `user_version=2`（含 nullable `attempt_id` 列）定义 G4 边界；测试/注释仍写 v2
   契约，fresh 库却建到 v3。
4. **G4-002E**：`src/omda/production.py` 模块级文档仍写"HTTP 4xx 为 definitive
   rejection"，与已修复的代码行为（全 4xx → ambiguous）相反。
5. **G4-009**：`--deliver` 使用 `_LocalEchoTransport`（恒返回一句本地常量），修复
   报告把真实 LLM 客户端推迟到 G5，但 G5 是 release-audit Gate（安装/E2E/安全/许可/
   发布），无 runtime-provider 实现任务；OD-2 明确"LLM provider 具体选型 (c) G4
   评审"。

已核实事实（本 ADR 的决策依据）：

- `AlbumSource` Port 存在（`src/omda/ports/album.py`：
  `candidates_for_genre(genre, limit) -> list[AlbumCandidate]`），但**无生产实现**；
  唯一实现是 CLI 的 `_sample_album_source`。
- `AlbumEnricher` **生产实现已交付**（`src/omda/adapters/musicbrainz.py`，G3 T3.3）：
  per-candidate、有界重试、fresh TTL 缓存、强制可联系 User-Agent、1 rps pacing、
  歧义不坍缩（多结果不给 canonical id）、弱匹配不安装 canonical id（≥90 分）。
- canonical identity 默认来源已由 OD-4（(b) G3 评审）定为 **MusicBrainz
  release-group**；MP §5 同文；G3-005 修复范围已要求"across successful MusicBrainz
  calls"的 pacing，即 MusicBrainz 已在授权架构内。
- MusicBrainz 官方开放 API（`https://musicbrainz.org/ws/2/`）；数据库内容以
  **CC0 1.0** 授权；服务要求有意义的可联系 User-Agent 与约 1 req/s 限速
  （G3-005 已实现并测试）。
- SPEC §3.3：community data MUST 以 YAML/CSV/JSON/JSONL 为 Git source of truth；
  SPEC §3.2/§7-12：按需抓取最少量页面数据并缓存（带 provenance/时间戳）、网络行为
  有界可注入。
- G3 Browser Companion（G3-005）只提取**有界 Genre 元数据**，明确禁止默认
  Album Detail fan-out、反爬/验证码绕过、无界预抓取——该边界**不可变**，本 ADR 不
  触及。
- MP 步骤 4-9：为每个 Genre 获取候选 Album 并补全必要信息 → 永久排除已推荐 →
  每 Genre 选 3 张 → LLM 生成介绍（不改变选择）→ 验证交付 → 成功后写 cooldown 与
  Album history；MP §6：数据缺失/失败必须显式失败/报告，不得用无关 Album 填充；
  MP §9 MVP 非目标需审计。
- OD-6：v0.1 默认 dry-run 本地 Markdown；推送显式开启（`--deliver`）。

## 2. 决策

### D1 — v0.1 真实 Album 候选来源（对应评审问题 1）

**决策：v0.1 生产 AlbumSource = MusicBrainz Release-Group 搜索 API（官方 WS/2，
CC0），作为新增 G4 补充任务（G4-010）实现 `MusicBrainzAlbumSource`（实现既有
`AlbumSource` Port）。**

- 获取方式：`GET /ws/2/release-group?query=tag:<genre>&fmt=json&limit=N`，按当前
  run 选中的 Genre 触发；返回有界候选（默认 `limit=10`，上限 25）。
- 依据：与已接受架构一致——OD-4/MP §5 已定 canonical identity = MusicBrainz
  release-group；G3 已交付同一 provider 的 Enricher（UA/pacing/缓存/分类基础设施
  直接复用）；官方开放 API，无 RYM 爬虫、无 album-detail fan-out、无反爬绕过；
  CC0 许可明确可审计。
- **明确排除**（维持已拒绝架构约束）：以任何 RYM 页面/HTML 抓取获取 Album 候选；
  Album Detail fan-out；验证码/反爬绕过；无界/全量抓取；任何未在基线与本 ADR 授权
  的新抓取架构。

### D2 — 来源、许可、provenance 与 canonical identity（对应评审问题 2）

- **来源**：`musicbrainz.org` 官方 WS/2 API（release-group search）。
- **许可**：MusicBrainz 数据库内容 **CC0 1.0**；请求必须携带有意义的可联系
  User-Agent（复用 `musicbrainz.py` 的强制 UA 校验）并遵守约 1 req/s pacing
  （G3-005 已实现）。
- **provenance**：`AlbumCandidate` 增加 provenance 字段（`source` / `query` /
  `fetched_at` / `query_version` / `license`）——公开 Port 契约变化，由本 ADR
  授权；候选快照**缓存为 Git JSONL 数据包**（复用 genre 包模式：`source.yaml` +
  `albums.jsonl`，满足 SPEC §3.3"Git source of truth"与 MP §5 的
  source.yaml + 数据文件模式），fresh TTL 内缓存命中优先。
- **canonical identity**：MusicBrainz release-group **MBID**（OD-4 既定）；enrich
  路径复用已交付 `MusicBrainzEnricher`（≥90 分强匹配、年份佐证、歧义不坍缩）；
  字符串规范化仅作降级匹配，永远不把弱匹配安装为 exact。

### D3 — 按需获取策略与禁令（对应评审问题 3）

- **按需**：仅对当前 run 选中的 Genre 触发；缓存优先（fresh TTL 内不重查）；缓存
  不足才发 API；每 Genre 候选数有界（`limit` 参数）；整个 run 的 MusicBrainz
  成功请求设运行预算（复用 OD-10/G3-005 模式，默认每 run ≤ 50 次，超出显式失败
  而非无限重试）；所有网络行为可注入（transport/clock/sleeper）、有界超时、有界
  重试（429/5xx 退避）、强制 UA、成功调用 pacing。
- **禁令**（本 ADR 固化，任何实现不得突破）：不抓取 RYM 页面获取 Album；不做
  Album Detail fan-out；不绕过验证码/反爬；不做无界/全量抓取；不使用 sample/demo
  数据冒充生产来源（D5）。

### D4 — 归属：重开 G3 还是 G4 补充任务（对应评审问题 4）

**决策：作为 G4 补充任务（G4-010；IMPLEMENTATION_PLAN C.4 增补 T4.5），不重开
G3，不改任何 G3 已接受边界。**

- 理由：`AlbumSource` Port 由 G3 交付；生产实现属于 G4"Agent & Delivery"组合层
  （`run.py` 消费 `candidates_for_genre`）；`MusicBrainzEnricher` 基础设施已在 G3
  就绪；本 ADR 不触碰 Browser Companion 边界（G3-005 约束继续有效）。

### D5 — sample/demo 数据下的 `--deliver` fail-closed（对应评审问题 5）

**决策：生产组合引入 `production-source gate`——`--deliver` 在做出任何外部调用
之前校验 AlbumSource 的真实性；仅当全部候选的 provenance 满足生产策略（source
非 demo/sample、license/origin_url/retrieved_at 齐全、来源在允许列表内）才放行；
否则立即拒绝（非零退出，`transport.calls == 0`，官方历史零变更，无 journal 污染）。**

- dry-run 保持不变（仍允许 sample；本地、history-neutral，Re-review 4 已 PASS）。
- 机制：`AlbumSource` 暴露 provenance；`build_production_engine` 校验（demo 标记
  或 provenance 缺失即拒绝）；负向测试锁定（见 §5 AC-1/AC-2）。

### D6 — v0.1 的 LLM 运行时边界（对应评审问题 6）

**决策：正式定义 v0.1 为 deterministic/no-LLM runtime；保留可替换 `LLM` Port
接口与 `llm.mode` 配置（`"deterministic" | "provider"`），v0.1 默认
`deterministic`。**

- `deterministic`：交付物 = 确定性事实报告（G4-005 机械契约不变）；narrative
  存档为空或模板句（G4-008 存档字段保留）；**不**调用任何外部 LLM。
- `provider`：v0.2+ 启用（候选：DeepSeek API，OD-2 建议默认；涉及外部账户/成本时
  按 OD-2 规则 Owner 知晓），Provider 可替换；本 ADR 不实现。
- 连带修订：MP 步骤 7 改写为"生成确定性结构化报告；narrative 为可选存档
  （provider 模式），不改变选择、不进交付物"；IMPLEMENTATION_PLAN 同步。
- 理由：评审二选一；消除 v0.1 的外部账户/成本/网络依赖（务实、fail-closed）；
  G4-008 已证明 narrative 不进交付物，no-LLM 不影响交付正确性；杜绝
  `_LocalEchoTransport` 冒充生产组合的诚实性问题。

### D7 — SQLite `user_version` 2/3 正式迁移决策（对应评审问题 7）

**决策：正式批准 v3 rollout（作为对 ADR-0001 的 amendment，记录于本 ADR；本
ADR Accepted 后同步更新 ADR-0001 §8/§12 文本）。**

- 事实：Accepted ADR-0001 §8 的 v2 定义含 nullable `attempt_id` 列；实现 v2 漏
  列、以 `_SCHEMA_VERSION=3` 补充；G4-002D 指出文档（v2）与实现（v3）分歧。
- 规则：
  - `user_version >= 2` 均为合法边界；fresh 库直接建到 **3**；
  - v2→v3 迁移 = 唯一 additive `ALTER TABLE delivery_receipt ADD COLUMN
    attempt_id TEXT`（幂等、向后兼容；v1/v2 旧行 `attempt_id` 保持 NULL）；
  - 回滚 v3→v2 = 删除该列，v2 读取器不受影响（只读不依赖该列的既有路径）；
  - 文档/注释/测试统一为 v3（fresh=v3、v1→v3 保留旧行、v2→v3 幂等）。
- 否决项：回退到 v2 重做（破坏既有库与 630 项基线，无收益）；不决策、静默保持
  v3（违反已接受边界治理，评审明确禁止）。

### D8 — 其余 open finding 的处置方案（本 ADR 一并记录，Accepted 后实施）

- **G4-002C（P1）**：`begin_delivery_operation` 对既有 key 同事务校验
  run_id/channel/payload_digest 与既有行一致，不一致即 `InvariantFailureError`
  （任何外部调用之前，SQLite + InMemory parity）；`save_delivery_receipt` 对非空
  attempt_id 同事务校验其属于匹配 operation（operation/key/run/channel/attempt
  绑定），并定义 **v1 legacy null-attempt 兼容规则**：旧行（attempt_id NULL）不
  校验 attempt 关联，保持可读、不可被改写。
- **G4-007C（P2）**：`--token-env` 区分"省略"与"显式覆盖"——省略时使用
  config 的 `pushplus_token_env`；显式传入才覆盖；config-only / CLI-override /
  missing-token 三态经公共入口测试，secret 永不落日志。
- **G4-002E（P2）**：`production.py` 模块文档的分类表与代码/测试完全一致
  （唯一自动重试类 `NoBytesSentError`；所有非 200 状态含全 4xx → ambiguous
  no-retry；无文档化 definitive 类别）。

## 3. 方案比较摘要

| 决策点 | 选定 | 备选（否决） | 否决理由 |
|---|---|---|---|
| Album 来源（D1） | MusicBrainz WS/2 release-group 搜索 | 人工维护 Git 数据包（无自动更新）；G3 browser extraction 扩展（fan-out） | 数据包缺自动按需获取；后者违反 G3-005 边界/反爬禁令 |
| 归属（D4） | G4 补充任务 G4-010 | 重开 G3 | Port 在 G3 已交付；边界无变化，无需重开 |
| 生产 gate（D5） | provenance 校验 fail-closed | 运行时过滤/填充无关专辑 | 填充违反 MP §6；运行时过滤仍可能推送劣质数据 |
| LLM（D6） | v0.1 deterministic/no-LLM + Port 保留 | v0.1 接入 DeepSeek | 外部账户/成本依赖；评审允许 defer；G4-008 已隔离 narrative |
| Schema（D7） | 批准 v3（amend ADR-0001） | 回退 v2；静默保持 v3 | 回退破坏基线；静默违反治理 |

## 4. 影响分析

**契约影响（需本 ADR 授权）**：

- `AlbumSource` Port：新增 provenance 暴露（`AlbumSource` 增加
  `provenance()` 或 `AlbumCandidate` 增加 provenance 字段）——公开契约变化；
- `AlbumEnricher` / `AlbumIdentity` 不变（MBID 语义沿用 OD-4）；
- `DeliveryReceipt` / `delivery_receipt.schema.json` v2 不变；
- ADR-0001 §8/§12：v3 rollout 文本对齐（D7，Accepted 后执行）；
- MP 步骤 7（narrative 语义）与 IMPLEMENTATION_PLAN（增补 T4.5/G4-010、OD-2
  措辞）修订（D6/D4）。

**代码影响（Accepted 后实施，不在本轮）**：

- 新增：`src/omda/adapters/musicbrainz_source.py`（或并入 musicbrainz.py 的
  `MusicBrainzAlbumSource`）、候选快照 JSONL 数据包目录（`data/albums/`）、
  `data/schemas/album_source*.schema.json`；
- 修改：`cli.py`（生产 gate、token 三态）、`production.py`（docstring 分类表）、
  `sqlite_history.py`（begin/receipt 绑定，G4-002C）、`config.py`
  （`llm.mode`、`album.limit`、`album.run_request_budget`）、MP/IP 文档。

**测试影响（设计见 §5）**：新增 production-source gate 负向、MusicBrainzAlbumSource
分类全表、begin/receipt 绑定负向（SQLite+InMemory parity）、token 三态、docstring
与代码一致、v3 迁移矩阵；既有 630 项不删除不弱化。

**风险与缓解**：

| 风险 | 缓解 |
|---|---|
| MusicBrainz tag 覆盖率不足导致候选不足 | MP §6：显式失败/报告，不填充（D5 gate 复用） |
| 限流/暂时封禁 | 强制 UA + 1 rps pacing + 有界重试退避 + 缓存命中优先 + run 预算（D3） |
| 许可/来源审计 | CC0 记录于 provenance 与 LICENSES；快照 Git 数据包带 source.yaml |
| 对既有已交付 Enricher 的影响 | G4-010 仅新增 AlbumSource，不修改 Enricher 语义 |

## 5. 验收测试设计（本 ADR 只设计，不实现）

映射 Reviewer 各 finding 的 Required acceptance：

- **AC-1（G4-007B 正）**：经公共 `cli.main` + 注入 fake 网络边界，使用带完整
  provenance 的生产 AlbumSource → 断言 outbound 事实与 committed 官方历史中的
  Album 标识**逐条**来自该生产来源（可审计 provenance：source/query/fetched_at/
  license），外部调用恰一次、官方历史原子提交。
- **AC-2（G4-007B 负）**：sample/demo AlbumSource（`_sample_album_source` 或
  provenance 标记 demo）→ `--deliver` 拒绝：非零退出、`transport.calls == 0`、
  官方历史（Album history / cooldown / pick index）**零变更**。
- **AC-3（G4-002C begin）**：SQLite 与 InMemory parity——对既有 key 以不匹配的
  run/channel/digest 调 `begin_delivery_operation` → `InvariantFailureError`，
  且发生在任何外部调用之前；匹配绑定则照常返回既有行快照。
- **AC-4（G4-002C receipt）**：`save_delivery_receipt` 带非空 attempt_id 时同事务
  校验 attempt 属于匹配 operation（operation/key/run/channel/attempt）——不匹配
  即失败；v1 null-attempt 旧行保持可读且不可改写（兼容规则测试）。
- **AC-5（G4-007C）**：config-only（省略 `--token-env`，config 指定变量）/ 显式
  `--token-env` 覆盖 / missing-token 三态经公共入口；secret 不出现在任何输出/日志。
- **AC-6（G4-002D）**：fresh 库 `user_version == 3`；v1→v3 迁移保留旧 receipt 行
  （attempt_id NULL）；v2→v3 幂等（重复打开不重复加列）；文档/注释与实现一致。
- **AC-7（G4-002E）**：`production.py` 文档分类表与代码/测试一致——全 4xx/5xx/
  未知 → ambiguous no-retry；仅 `NoBytesSentError` 有界重试。
- **AC-8（G4-009 / D6）**：`llm.mode=deterministic` 下 `--deliver` 全链路不调用任何
  外部 LLM，交付物为确定性事实报告，narrative 存档为空/模板；`llm.mode=provider`
  仅作为 v0.2 配置路径存在（不在 v0.1 激活）。
- **AC-9（D3）**：MusicBrainzAlbumSource 注入 transport 全表——200 正常 /
  429 退避重试 / 5xx / 畸形体 / 多结果歧义（不坍缩）/ 404 空结果 / 超时 /
  budget 超限显式失败；pacing 与 UA 强制；每 Genre limit 与 run 预算生效。

## 6. 阶段状态与 Gate 流程

- **当前（本轮）**：`BLOCKED_ARCHITECTURE / ADR_PENDING`——只提交本 Proposed
  ADR 与阶段状态更新；无 production code 变更；ADR 不标 Accepted。
- **Reviewer 接受本 ADR 后**：Executor 按 D1-D8 实施（G4-010 AlbumSource +
  production-source gate、G4-002C/G4-007C/G4-002E、v3 amend 文本对齐、MP/IP 修订），
  完成 §5 全部验收测试，提交一个新的完整 candidate（相对同一 base
  `68e3d453…`）返回 Reviewer 复审。
- 本 ADR 未被接受前：不实施、不 merge、不打 tag、不进入 G5。

## 7. 引用

- Reviewer：`reviews/stage-04/REVIEW_VERDICT.md` §G4 Re-review 4（commit
  `790f36f99a859da3b2578462d76e6b2cac4051ad`）；候选 `8b1f7c9…`。
- ADR-0001 §8（v2 DDL / user_version 边界）、§9（provider 分类）、§15（acceptance
  constraints）。
- G3 verdict：G3-003（search score ≥90）、G3-004（stale-refresh 显式失败）、
  G3-005（UA/pacing/budget/URL 边界）、G3-006（缓存有界）。
- SPEC §2.4（canonical identity）、§3.2（按需最小抓取）、§3.3（Git source of
  truth）、§7-12（网络有界）、§7-13（prompt 隔离）、§7-14（secrets）。
- MP §5（数据建议/MusicBrainz canonical 映射）、§6（失败降级不填充）、§7（许可）、
  §9（MVP 非目标）；步骤 4-9。
- IMPLEMENTATION_PLAN C.4（G4 任务）、C.5（G5 范围）、OD-2 / OD-4 / OD-6 / OD-10。
