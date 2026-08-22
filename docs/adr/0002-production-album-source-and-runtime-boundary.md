# ADR-0002 — v0.1 生产 Album 候选来源、运行时边界与持久化版本对齐（修订版 v2）

- Status: **Proposed**（修订版 v2，响应 ADR2-001 ~ ADR2-008；提交 GPT-5.6 Sol
  复审；本 ADR Accepted 前不实施任何 production code 变更）
- Date: 2026-08-22（修订 v2：2026-08-22）
- Gate: G4（Agent & Delivery）— 架构阻断（BLOCKED_ARCHITECTURE / ADR_PENDING）
- 触发 Reviewer finding：G4 Re-review 4（Reviewer commit
  `790f36f99a859da3b2578462d76e6b2cac4051ad`，verdict **BLOCKED_ARCHITECTURE /
  ADR_REQUIRED**）：G4-007B（P1 架构）、G4-002C（P1）、G4-007C（P2）、G4-002D
  （P2）、G4-002E（P2）、G4-009（P2）。
- 修订触发：`reviews/stage-04/ADR_0002_REVIEW.md`（Reviewer commit
  `443f90a04951e6d360a69fa4446b4e3b34946589`，结论 **REVISE**），finding
  ADR2-001 ~ ADR2-008。本修订逐条解决；**仍不修改 production code/tests**。

## 0. 修订记录（ADR2-001 ~ ADR2-008 响应）

| Reviewer finding | 本修订 v2 的解决方案 |
|---|---|
| ADR2-001 所选 tag-search 来源不是无保留 CC0 数据集 | **许可四层分离**：①release-group core facts（title/artist/MBID/year，CC0）；②user tags/genre associations 与 search index（**supplementary data，CC BY-NC-SA 3.0**）；③web service 访问条款（免费仅限**非商业**，商业需 plan/contact）；④OMDA 派生候选包按"curated package + per-source license manifest"管理，**绝不整体标 CC0**。**候选发现 v0.1 首选 curated community Genre→release-group-MBID package**（Git source of truth、人工审核）；live tag-search 发现仅在 **Owner 明确决策（ODP-1）**接受非商业条款后作为可选补充，默认关闭；无合法兼容来源 → fail-closed（§2 D1/D2、§3） |
| ADR2-002 runtime cache 与 Git community source of truth 混淆 | **两条独立路径**：①**runtime cache**——有界、本地、Git 忽略（`var/` 边界）、TTL/provenance aware、可安全删除，普通 run **永不写入 tracked 数据**；②**curated community package**——仅由**显式 export/import 贡献流程**产生：schema 校验 + 人工审核后才 commit，自带 license/source manifest。runtime cache hit 不得描述为 Git source of truth（§2 D2、§4） |
| ADR2-003 D4 与已接受的 Gate 独占归属矛盾 | **窄幅重开 G3 corrective task（G3-007）**实现 `MusicBrainzAlbumSource` + source 契约/cache/provenance/错误映射测试（data/source adapter 完全归 G3，符合 IMPLEMENTATION_PLAN 已接受契约）；完成后**回到仍被阻断的 G4** 做生产组合与 delivery gating。本 ADR 不再声称"不改 G3 边界"，而是显式记录该窄幅重开（§2 D4、§4、§6） |
| ADR2-004 tag 查询未定义安全/相关/可持续的 Album 池 | 补全：**escaped/quoted query 构造**（Lucene 保留字符转义 + 双引号包裹，hostile/special-char Genre name 测试）；**release-group 类型过滤**（允许 primary Album，排除 Single/EP 等，定义必填字段）；**versioned Genre→MusicBrainz query/tag 映射**（含"no mapping"/"insufficient candidates"可观测结果）；**有界分页/cursor 与 cache-key/query-version 失效**，永久历史可越过第一页而无无界爬取；**search score/tag evidence 仅用于相关性**，绝不成为 popularity filter 或改变 Genre 等权重（§2 D3、§5 AC-4/AC-9） |
| ADR2-005 请求预算与 pacing 未跨 MusicBrainz clients 共享 | 定义 **composition-owned MusicBrainz request coordinator**：source 与 enricher **共用**——单一可联系 UA、host allowlist、pacing（整个 client 平均 ≤1 req/s）、retry accounting、**总尝试预算（每次 HTTP attempt 都计数，含失败与重试，不只成功）**；并发 run 行为：**单 run 锁 + 共享 limiter**（§2 D5、§5 AC-5/AC-9） |
| ADR2-006 无单一可强制 provenance 契约 | 统一为**版本化 `CandidateBatch`/source envelope**：immutable source descriptor（origin_url/query、retrieved_at、query policy version、license identifier、demo flag、content digest）+ per-candidate MBID/事实；明确定义 **trusted composition 在 journal claim 与 delivery 之前**校验 batch；AC-1 证明 committed identity 与 outbound fact 都属该 validated batch；AC-2 覆盖 missing/contradictory/**forged** provenance（非仅 "sample" 字面标签）（§2 D6、§5 AC-1/AC-2/AC-6） |
| ADR2-007 破坏性 v3→v2 降级销毁交付证据 | **删除破坏性降级方案**。v3 为 forward migration（事务内：schema fingerprint 检查 + 幂等加列 + 仅真实 legacy 行保留 NULL + set v3）；支持并测试 v1 / v2-with-column / v2-without-column / v3 四种物理布局；`user_version > 3` 或未知 fingerprint **fail-closed**（不改库）；回滚 = **forward-fix（修复/重放）或备份恢复**，绝不删除 attempt 证据列；文档化 old-binary 兼容性而非声称无害降级（§2 D7、§5 AC-7） |
| ADR2-008 v0.1 config 不应宣传未激活的 provider | v0.1 `llm.mode` **只允许 `deterministic`**；`provider` 值在 **config validation 阶段 fail-closed**（明确 "not supported in v0.1"，在任何 run/journal/network 副作用之前）；narrative 存档 = **typed deterministic report-mode marker**，不存档任何伪造句子；provider 模式加入需独立 implemented adapter + schema/version 变更 + cost/secret 控制 + Gate acceptance（§2 D8、§5 AC-8） |

## 1. 背景与已核实事实

Reviewer 独立探针复现（`reviews/stage-04/REVIEW_VERDICT.md` Re-review 4）与
ADR-0002 首轮评审（`reviews/stage-04/ADR_0002_REVIEW.md`）：

1. **G4-007B**：公共 `cli.main()` + PushPlus config + 临时官方 SQLite 存储 + 注入
   fake 网络 transport → run 返回 COMPLETE、恰一次外部调用，outbound Markdown 含
   `tuareg Sample 1 — Sample Artist (2015)`；官方历史随后含九个编造 ID
   （`ambient-1`、`bebop-2`、`tuareg-3`）。`src/omda/cli.py:263-272`
   `_sample_album_source` 为每个 Genre 硬编码三条编造记录；`data/genres/README.md`
   明确 `rym-sample` 是"illustrative 4-record subset, not a full RYM mirror"；
   仓库无任何生产 `AlbumSource` 实现。
2. **G4-002C**：`begin_delivery_operation` 对既有 key 不校验 run_id/channel 绑定；
   `save_delivery_receipt` 接受任意 caller 提供的非空 attempt_id（`shared-key#999`
   无对应 attempt 仍存储成功）。
3. **G4-002D**：实现 `_SCHEMA_VERSION = 3`，而 Accepted ADR-0001 §8 以
   `user_version=2`（含 nullable `attempt_id` 列）定义 G4 边界；测试/注释仍写 v2
   契约，fresh 库却建到 v3。
4. **G4-002E**：`src/omda/production.py` 模块级文档仍写"HTTP 4xx 为 definitive
   rejection"，与已修复代码行为（全 4xx → ambiguous）相反。
5. **G4-009**：`--deliver` 使用 `_LocalEchoTransport`（恒返回一句本地常量）冒充
   生产 Agent 组合；G5 是 release-audit Gate，无 runtime-provider 实现任务；
   OD-2 明确"LLM provider 具体选型 (c) G4 评审"。

ADR2-001 补充核实的官方事实（许可边界）：

- MusicBrainz 官方数据库拆分（`/doc/MusicBrainz_Database`）：
  - **CC0 core data**：artist/release-group/release 等核心元数据；
  - **CC BY-NC-SA 3.0 supplementary data**：**user-submitted tags（含 genre
    associations）与 search indexes**。
- 数据许可页（`/doc/About/Data_License`）与 API 文档（`/doc/MusicBrainz_API`）：
  web service **免费仅限非商业使用**；商业使用指向商业 plan/contact。
- 因此：D1 若用 `query=tag:<genre>` 做候选发现，其 Genre→release-group **候选
  关系**与经其筛选的快照至少是 **mixed/derived data**，不能整体标 CC0；"开源
  代码"本身不能替代服务使用条款或再分发数据的许可结论。

其余已核实事实（沿用 ADR-0002 v1，未变）：

- `AlbumSource` Port 存在（`src/omda/ports/album.py`：
  `candidates_for_genre(genre, limit)`），无生产实现；唯一实现是 CLI 的
  `_sample_album_source`。
- `AlbumEnricher` 生产实现已交付（`src/omda/adapters/musicbrainz.py`，G3 T3.3）：
  per-candidate、有界重试、fresh TTL 缓存、强制可联系 UA、pacing、歧义不坍缩、
  弱匹配不安装 canonical id（≥90 分）。
- canonical identity 默认来源已由 OD-4（(b) G3 评审）定为 **MusicBrainz
  release-group MBID**；MP §5 同文；G3-005 已要求跨成功 MusicBrainz 调用的 pacing。
- SPEC §3.3：community data MUST 以 YAML/CSV/JSON/JSONL 为 Git source of truth；
  SPEC §3.2/§7-12：按需抓取最少量页面数据并缓存（带 provenance/时间戳）、网络
  行为有界可注入。
- G3 Browser Companion（G3-005）只提取有界 Genre 元数据，禁止 Album Detail
  fan-out、反爬/验证码绕过、无界预抓取——该边界不可变。
- MP 步骤 4-9、MP §6（失败显式报告、不填充）、MP §7（许可清单）、MP §9（MVP
  非目标）；OD-6（v0.1 默认 dry-run，推送显式开启）。

## 2. 决策

### D1 — v0.1 真实 Album 候选来源（修订：许可分层 + curated 首选）

**决策：v0.1 生产 AlbumSource 的候选发现首选 curated community
Genre→release-group-MBID 数据包**（Git source of truth、per-source license
manifest、人工审核贡献流程，与 SPEC §3.3/ADR2-002 curated 路径一致）；live
MusicBrainz **tag-search 发现仅在 Owner 决策（ODP-1）明确接受非商业条款后**作为
可选补充，默认关闭；**无任何合法兼容来源安装时，外部交付 fail-closed**（D6 gate
复用）。

- **许可四层分离**（本 ADR 固化，任何实现/数据包不得合并）：
  1. release-group **core facts**（title/artist/MBID/first-release-date）——CC0；
  2. user tags / genre associations 与 **search index**——**supplementary data，
     CC BY-NC-SA 3.0**，非商业；
  3. **web service 访问条款**——免费仅限非商业，商业需 plan/contact；
  4. **OMDA 派生候选包**——per-source license manifest（逐源记录来源/许可/派生
     声明），**绝不整体标 CC0**；attribution/share-alike/non-commercial 影响在
     数据包 README 与 LICENSES 中显式声明；**数据许可与代码许可分开记录**。
- **ODP-1（Owner 产品决策，待定案）**：v0.1 是否接受"非商业-only live
  MusicBrainz tag-search 发现"作为运行时来源。**未定案前**：live tag-search 发现
  关闭，仅 curated package 生效；若 curated package 也未安装 → fail-closed。
- **明确排除**（维持已拒绝架构约束）：RYM 页面/HTML 抓取获取 Album；Album Detail
  fan-out；验证码/反爬绕过；无界/全量抓取；把 sample/demo 或 mixed-license 数据
  冒充 CC0 生产来源。

### D2 — 来源、许可、provenance 与 canonical identity（修订：cache/package 分离）

- **两条独立路径**（ADR2-002）：
  - **runtime cache**：有界（条目上限 + TTL）、**本地且 Git 忽略**（`var/`
    边界，SQLite 或等价本地缓存）、携带 provenance（source/fetched_at/query
    version）、**可安全删除**；普通推荐 run **永不写入 tracked 仓库数据**；cache
    hit **不是** Git source of truth。
  - **curated community package**：仅由**显式 export/import 贡献流程**产生——
    schema 校验 + **人工审核**后才 commit 到 `data/albums/<source_id>/`
    （`source.yaml` + `albums.jsonl`，含 per-source license/origin/retrieved_at
    manifest）；每次自动查询**不得**静默提升进 Git。
- **canonical identity**：MusicBrainz release-group **MBID**（OD-4 既定）；
  enrich 路径复用已交付 `MusicBrainzEnricher`（≥90 分强匹配、年份佐证、歧义不
  坍缩）；**tag associations 不参与 canonical 判定**；字符串规范化仅作降级匹配。

### D3 — 按需获取、查询契约与禁令（修订：补全 ADR2-004）

- **查询构造**：Genre→MusicBrainz 查询使用**版本化映射**（query-policy version，
  随匹配语义演进递增，cache-key 与 invalidate 同版本）；Genre name 必须经
  **Lucene 保留字符转义 + 双引号包裹**后嵌入 `tag:"<escaped>"`；hostile/
  special-char（引号、冒号、斜杠、多词）Genre name 不能改变查询结构——注入
  测试锁定；映射缺失 → 可观测 **"no mapping"** 结果；候选不足 → 可观测
  **"insufficient candidates"**，二者都 fail/report，不填充。
- **Album 类型**：候选池仅接受 release-group **primary type = Album**（允许的
  secondary type 与必填字段在实现中枚举；Single/EP/其他 primary type 过滤）。
- **分页/历史耗尽协议**：per-genre 候选获取有界分页（页面大小与页数上限、cursor
  稳定化）；**已进入永久历史的候选永久排除后，可从后续页继续发现**；页面耗尽或
  结果不稳定 → 显式失败，**绝不 sample 替代、绝不污染历史**。
- **相关性规则**：search score / tag evidence **仅用于相关性排序**，绝不作为
  popularity filter，绝不改变 Genre 等权重（MP §2.1 不变）。
- **禁令**（固化）：无 RYM 抓取、无 Album Detail fan-out、无反爬绕过、无无界/
  全量抓取、无 sample/demo 冒充生产、无 popularity 权重、无 tag 参与 canonical。

### D4 — 归属：窄幅重开 G3，而非 G4 补充（修订：ADR2-003）

**决策：实现 `MusicBrainzAlbumSource`（及 source 契约/cache/provenance/错误映射
测试）作为**窄幅重开 G3 的 corrective task（G3-007）**；G4 保持其独占所有权
（LLM/Markdown/delivery），负责生产组合（production-source gate、`--deliver`
接线、delivery 测试）。**

- 依据：已接受计划把 data/source-class adapter（含 MusicBrainz/community
  sources、cache、provenance、error mapping）**独占归 G3**；从 `run.py` 消费
  `AlbumSource` 不改变该所有权。
- 流程：G3-007 完成后回到**仍被阻断的 G4**（G4 只做组合与 gate），再返回完整
  candidate 复审；本 ADR 不再主张"不改 G3 边界"——而是**显式记录该窄幅重开**
  及其理由（AlbumSource 是 data/source adapter，不属 delivery 层）。
- IMPLEMENTATION_PLAN：C.3（G3）增补 G3-007，C.4（G4）相应引用修订（文档变更，
  Accepted 后执行）。

### D5 — 请求协调与预算（修订：ADR2-005 跨 client 共享）

**决策：单一 composition-owned MusicBrainz request coordinator，source 与
enricher 共用。**

- coordinator 持有一个可联系 UA、host allowlist（仅 `musicbrainz.org` 官方
  WS/2 主机/路径）、pacing（**整个 client 平均 ≤1 req/s**，跨成功与失败）、
  retry accounting（429/5xx 有界退避）与 **total attempt budget**。
- **每次 HTTP attempt 都计数**（成功、失败、重试、超时全部计入同一有限预算）；
  预算耗尽 → 显式失败（不无限重试）。
- **并发 run**：单 run 锁 + 共享 limiter；并发 run 的合并请求同样受同一 pacing
  与预算约束（不因并行翻倍突破 1 rps）。
- 所有网络行为可注入（transport/clock/sleeper），测试不触网。

### D6 — production-source gate 与统一 provenance 契约（修订：ADR2-006）

**决策：统一为版本化 `CandidateBatch`/source envelope，作为唯一可强制来源契约。**

- `CandidateBatch` 结构（版本化 schema）：immutable **source descriptor**
  （source_id、origin_url/query、retrieved_at、query_policy_version、
  license identifier、demo flag、content digest）+ **per-candidate** 记录
  （MBID、title、artist、year、type、score 仅作相关性参考）。
- **trusted composition（`build_production_engine`）在 journal claim 与任何
  delivery 之前**校验 batch：schema 版本匹配、digest 自洽、license 齐全且允许、
  demo flag=false、来源在 allowlist；任一不符 → fail-closed（无外部调用、无历史
  变更）。
- 校验必须是**内容级**（batch 与其证据绑定），不是字符串比较——自标 allowlist
  字符串的畸形/伪造 batch 同样失败。
- `--deliver` 仅接受已通过校验的 `CandidateBatch`；dry-run 可继续用 sample
  （本地、history-neutral）。

### D7 — SQLite `user_version` 2/3 正式迁移决策（修订：ADR2-007 非破坏性）

**决策：正式批准 v3 为 forward migration（amend ADR-0001）；删除破坏性 v3→v2
降级方案。**

- 事实：Accepted ADR-0001 §8 的 v2 定义含 nullable `attempt_id` 列；实现 v2
  漏列、以 `_SCHEMA_VERSION=3` 补充；G4-002D 指出文档（v2）与实现（v3）分歧。
- 迁移规则（**单个事务**内完成，幂等）：
  1. 读取 `user_version` 并检查 `delivery_receipt` **schema fingerprint**（是否
     含 `attempt_id` 列）——**版本号本身不是充分迁移前提**；
  2. 支持并测试四种物理布局：v1（旧四表，receipt 无新列）→ 建三新表 + 幂等加列；
     v2-with-column（intended 布局）→ 直接进 v3；v2-without-column（buggy
     布局）→ 幂等加列 → v3；v3 → no-op；
  3. **仅真实 legacy 行（v1 迁移而来）保留 NULL `attempt_id`**；新 finalize 写
     入生成的 attempt id；
  4. 完成加列后 `PRAGMA user_version = 3`；
  5. `user_version > 3` 或未知 schema fingerprint → **fail-closed**（raise，不
     改库）。
- **回滚 = forward-fix（修复/重放）或备份恢复**，绝不删除 `attempt_id` 列
  （它是 receipt↔attempt 证据绑定，删除将重开 ADR-0001 已关闭的歧义）；
  文档化 old-binary 兼容性（旧二进制读取器忽略新列），而非声称无害降级。
- 文档/注释/测试统一为 v3（fresh=v3、v1→v3 保留旧行、v2 两布局→v3、>3
  fail-closed）。
- 否决项：回退 v2 重做（破坏既有库与基线）；破坏性降级（销毁证据）；不决策
  静默保持 v3（违反治理）。

### D8 — v0.1 的 LLM 运行时边界（修订：ADR2-008 config fail-closed）

**决策：v0.1 正式定义为 deterministic/no-LLM runtime；v0.1 config schema 的
`llm.mode` 只允许 `deterministic`。**

- `llm.mode=deterministic`：交付物 = 确定性事实报告（G4-005 机械契约不变）；
  narrative 存档 = **typed deterministic report-mode marker**（如
  `{"mode": "deterministic"}`），**不存档任何伪造句子**；不调用任何外部 LLM。
- config validation 对 `llm.mode=provider`（或任何未知值）**fail-closed**：
  明确 "not supported in v0.1"，在任何 run/journal/network 副作用之前拒绝。
- 未来加入 provider 模式（候选：DeepSeek，OD-2）需要：独立 implemented
  adapter、schema/version 变更、cost/secret 控制、Gate acceptance——本 ADR
  不在 v0.1 激活。
- 连带修订：MP 步骤 7（确定性结构化报告；narrative 仅 deterministic marker，
  provider 留待后续）与 IMPLEMENTATION_PLAN（C.4 增补说明，不新建 G5 任务）。

### D9 — 其余 open finding 的处置方案（沿用 v1，Accepted 后实施）

- **G4-002C（P1）**：`begin_delivery_operation` 对既有 key 同事务校验
  run_id/channel/payload_digest 与既有行一致，不一致即 `InvariantFailureError`
  （任何外部调用之前，SQLite + InMemory parity）；`save_delivery_receipt` 对非空
  attempt_id 同事务校验其属于匹配 operation（operation/key/run/channel/attempt
  绑定），并定义 **v1 legacy null-attempt 兼容规则**：旧行（attempt_id NULL）不
  校验 attempt 关联，保持可读、不可改写。
- **G4-007C（P2）**：`--token-env` 区分"省略"与"显式覆盖"——省略时使用
  config 的 `pushplus_token_env`；显式传入才覆盖；config-only / CLI-override /
  missing-token 三态经公共入口测试，secret 永不落日志。
- **G4-002E（P2）**：`production.py` 模块文档分类表与代码/测试完全一致
  （唯一自动重试类 `NoBytesSentError`；所有非 200 状态含全 4xx → ambiguous
  no-retry；无文档化 definitive 类别）。

## 3. 方案比较摘要

| 决策点 | 选定 | 备选（否决） | 否决理由 |
|---|---|---|---|
| Album 候选来源（D1） | **curated community Genre→release-group-MBID package**（首选，per-source licensing）；live tag-search 仅 ODP-1 同意后可选 | 直接 live tag-search 为唯一来源 | 候选关系经 supplementary tag/search index（CC BY-NC-SA、非商业条款），无 Owner 决策不可整体 CC0 |
| 无合法来源时（D1/D6） | **fail-closed**（拒绝外部交付） | 运行时填充/过滤无关专辑 | 填充违反 MP §6；过滤仍可能推送劣质数据 |
| 缓存路径（D2） | runtime cache（Git 忽略）与 curated package（人工审核贡献流程）**分离** | 自动查询结果写入 tracked Git | 绕过贡献/许可审核；违反 SPEC §3.3 操作性语义 |
| 归属（D4） | **窄幅重开 G3 corrective task（G3-007）** | 在 G4 新增 adapter；重开完整 G3 | 已接受计划把 data/source adapter 独占归 G3；G4 只做组合 |
| LLM（D8） | v0.1 deterministic/no-LLM，`llm.mode` 仅允许 deterministic（provider fail-closed） | v0.1 接入 DeepSeek；config 保留未激活 provider 值 | 外部账户/成本依赖；未激活的 public surface 误导 |
| Schema（D7） | v3 forward migration（fingerprint 检查 + 幂等加列 + >3 fail-closed）；**无破坏性降级** | 回退 v2；v3→v2 删列降级；静默保持 v3 | 回退破坏基线；删列销毁交付证据；静默违反治理 |

## 4. 影响分析

**契约影响（需本 ADR 授权）**：

- `AlbumSource` Port：新增 `CandidateBatch`（版本化 source envelope）契约
  （公开契约变化，本 ADR 授权）；`AlbumEnricher` / `AlbumIdentity` 不变；
- `DeliveryReceipt` / `delivery_receipt.schema.json` v2 不变；
- ADR-0001 §8/§12：v3 forward-migration 文本对齐（D7，Accepted 后执行）；
- MP 步骤 7 与 IMPLEMENTATION_PLAN（G3-007 增补、G4 引用修订、OD-2 措辞）修订
  （D4/D8，Accepted 后执行）。

**代码影响（Accepted 后实施，不在本轮）**：

- 新增：`src/omda/adapters/musicbrainz_source.py`（或并入 musicbrainz.py 的
  `MusicBrainzAlbumSource`，G3-007）、`MusicBrainzRequestCoordinator`、
  `data/schemas/candidate_batch.schema.json`、curated package 目录
  （`data/albums/<source_id>/`，贡献流程产物）、runtime cache（`var/` 边界）；
- 修改：`cli.py`（production-source gate、token 三态）、`production.py`
  （docstring 分类表）、`sqlite_history.py`（begin/receipt 绑定 + v3 fingerprint
  迁移，G4-002C/G4-002D）、`config.py`（`llm.mode` 仅 deterministic、
  `album.*` 预算项）、MP/IP 文档。

**测试影响（设计见 §5）**：新增 CandidateBatch 校验、gate 正/负、coordinator
共享预算、查询转义/类型过滤/分页/映射缺失、v3 四布局迁移矩阵、token 三态、
docstring 一致、deterministic marker；既有 630 项不删除不弱化。

**风险与缓解**：

| 风险 | 缓解 |
|---|---|
| 许可边界（supplementary/mixed/非商业） | 许可四层分离 + per-source manifest + ODP-1 Owner 决策；未定案 fail-closed（D1/D2） |
| curated package 覆盖不足/陈旧 | 贡献流程 + 显式版本/retrieved_at；不足时显式失败不填充（D3） |
| 限流/暂时封禁 | coordinator 共享 pacing（≤1 rps）+ 总尝试预算 + 缓存命中优先（D5） |
| 候选池被永久历史耗尽 | 有界分页/cursor + 稳定化 + query-version 失效（D3） |
| 畸形/伪造来源自标生产 | CandidateBatch 内容级校验（digest/license/demo/allowlist）fail-closed（D6） |
| 迁移破坏证据 | fingerprint 检查 + 幂等加列 + 无删列降级 + 备份恢复（D7） |

## 5. 验收测试设计（本 ADR 只设计，不实现）

映射 G4 Re-review 4 与 ADR-0002 首轮评审的 Required acceptance：

- **AC-1（G4-007B 正 / ADR2-006）**：经公共 `cli.main` + 注入 fake 网络边界，使用
  已校验的 `CandidateBatch`（生产 provenance）→ 断言 outbound 事实与 committed
  官方历史中的 Album 标识**逐条**来自该 batch（batch digest 绑定：committed
  identity 与 outbound fact 都属于同一 validated batch），外部调用恰一次、官方
  历史原子提交。
- **AC-2（G4-007B 负 / ADR2-006）**：sample/demo batch、**missing
  provenance、自相矛盾的 provenance、伪造来源（自标 allowlist 字符串但 digest/
  license 不符）** 全部 → `--deliver` 拒绝：非零退出、`transport.calls == 0`、
  官方历史零变更。
- **AC-3（G4-002C begin）**：SQLite 与 InMemory parity——对既有 key 以不匹配的
  run/channel/digest 调 `begin_delivery_operation` → `InvariantFailureError`，
  且发生在任何外部调用之前。
- **AC-4（G4-002C receipt）**：`save_delivery_receipt` 带非空 attempt_id 时同事务
  校验 attempt 属于匹配 operation——不匹配即失败；v1 null-attempt 旧行可读且
  不可改写。
- **AC-5（G4-007C）**：config-only / CLI-override / missing-token 三态经公共
  入口；secret 不出现在任何输出/日志。
- **AC-6（G4-002E / ADR2-006）**：`production.py` 文档分类表与代码/测试一致
  （全 4xx/5xx/未知 → ambiguous no-retry；仅 `NoBytesSentError` 有界重试）。
- **AC-7（G4-002D / ADR2-007）**：fresh=v3；**v1、v2-with-column、
  v2-without-column、v3 四布局**在一个事务性迁移中正确且幂等收敛到 v3，旧行
  attempt_id 仅真实 legacy 行保留 NULL；`user_version > 3` 或未知 fingerprint
  fail-closed（不改库）；**无删列降级路径**。
- **AC-8（G4-009 / ADR2-008）**：`llm.mode=deterministic` 全链路不调用外部 LLM，
  交付物为确定性事实报告，narrative 存档为 typed deterministic marker；
  `llm.mode=provider` 在 config validation 即 fail-closed（run/journal/network
  副作用前）。
- **AC-9（D1/D3/D5）**：MusicBrainz 相关注入 transport 全表——200 正常 / 429
  退避 / 5xx / 畸形体 / 超时 / 预算耗尽显式失败；**Lucene 保留字符与多词 Genre
  name 不改变查询结构**；release-group 类型过滤（Single/EP 剔除）；**no-mapping
  与 insufficient-candidates 可观测**；**分页越过已入历史的第一页**且不无界爬取；
  **source 与 enricher 共享 coordinator：每次 HTTP attempt（含失败/重试）都计入
  同一预算，合并调用时间戳满足 ≤1 rps**；search score 仅相关性、不作为
  popularity filter。

**ADR2 新增验收（Required revised acceptance additions）映射**：①许可/provenance
fixtures 区分 CC0 core facts 与 supplementary tag/search evidence，生成的 package
无有效依据不得整体标 CC0（AC-9/AC-1）；②普通 run 查询只写 Git 忽略缓存，显式
export/import 是唯一产生可审 Git 数据的路径（AC-9/AC-1）；③保留字符/多词 Genre
不能改查询结构，映射缺失与无关类型明确失败（AC-9）；④首页候选入永久历史后有界
分页可发现后续页，耗尽/不稳定显式失败且无 sample 替代、无历史污染（AC-9/AC-2）；
⑤source+enricher 共享 coordinator，每次尝试计入预算、时间戳满足 pacing（AC-9）；
⑥provenance schema 不一致、digest/origin/license 缺失、伪造生产状态都在 PushPlus
前与官方历史变更前失败（AC-2/AC-1）；⑦v2-with-column / v2-without-column /
future-version 库按修订后安全 v3 迁移/fail-closed 规则且不删交付证据（AC-7）。

## 6. 阶段状态与 Gate 流程

- **当前（本轮）**：`BLOCKED_ARCHITECTURE / ADR_PENDING`——只提交本 Proposed
  ADR（修订 v2）与阶段状态更新；无 production code / tests 变更；ADR 不标
  Accepted。
- **Reviewer 接受本 ADR 后**：Executor 按 D1-D9 实施——先窄幅重开 G3-007
  （MusicBrainzAlbumSource + coordinator + CandidateBatch + 贡献流程），再回到
  G4 做 production-source gate 与 `--deliver` 接线，并修复 G4-002C/G4-007C/
  G4-002E、执行 v3 forward migration 对齐与 MP/IP 修订；完成 §5 全部验收测试后，
  提交新的完整 candidate（相对同一 base `68e3d453…`）返回 Reviewer 复审。
- 本 ADR 未被接受前：不实施、不 merge、不打 tag、不进入 G5。

## 7. 引用

- Reviewer：`reviews/stage-04/REVIEW_VERDICT.md` §G4 Re-review 4（commit
  `790f36f…`）；`reviews/stage-04/ADR_0002_REVIEW.md`（commit `443f90a…`，
  结论 REVISE）；候选 `702d1d3…`。
- MusicBrainz 官方：`https://musicbrainz.org/doc/About/Data_License`、
  `https://musicbrainz.org/doc/MusicBrainz_Database`、
  `https://musicbrainz.org/doc/MusicBrainz_API`、
  `https://musicbrainz.org/doc/MusicBrainz_API/Rate_Limiting`、
  `https://musicbrainz.org/doc/MusicBrainz_API/Search`。
- ADR-0001 §8（v2 DDL / user_version 边界）、§9（provider 分类）、§15（acceptance
  constraints）。
- G3 verdict：G3-003 / G3-004 / G3-005 / G3-006。
- SPEC §2.4、§3.2、§3.3、§7-12、§7-13、§7-14。
- MP §5 / §6 / §7 / §9；步骤 4-9。
- IMPLEMENTATION_PLAN C.3（G3，增补 G3-007）、C.4（G4）、C.5（G5 范围）、
  OD-2 / OD-4 / OD-6 / OD-10。
