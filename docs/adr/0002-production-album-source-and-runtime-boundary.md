# ADR-0002 — v0.1 生产 Album 候选来源、运行时边界与持久化版本对齐（修订版 v2）

- Status: **Accepted**（GPT-5.6 Sol 独立复审接受修订版 v2；实现必须遵守
  §8 Reviewer acceptance constraints；ADR 接受不等于 G3-007 或 G4 Gate 接受）
- Date: 2026-08-22（修订 v2：2026-08-22）
- Gate: G3-007 corrective checkpoint → G4（ADR 已接受；两个实现 Gate 均未接受）
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
| ADR2-003 D4 与已接受的 Gate 独占归属矛盾 | **窄幅重开 G3 corrective task（G3-007）**实现默认 `CuratedAlbumSource` + source 契约/cache/provenance/错误映射测试（data/source adapter 完全归 G3，符合 IMPLEMENTATION_PLAN 已接受契约）；live `MusicBrainzAlbumSource` 仍受 ODP-1 约束。G3-007 独立评审后才回 G4 做生产组合与 delivery gating（§2 D4、§6、§8） |
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

以下 provider-query/pagination 条款仅在 ODP-1 接受 live tag-search 后启用；默认
curated path 读取版本化本地 package，不发 tag-search 请求。

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

**决策：实现默认 `CuratedAlbumSource`（及 source 契约/cache/provenance/错误映射
测试）作为**窄幅重开 G3 的 corrective task（G3-007）**；live
`MusicBrainzAlbumSource` 仅在 ODP-1 由 Owner 接受后另行加入。G4 保持其独占所有权
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

**条件决策：若 ODP-1 接受并加入 live `MusicBrainzAlbumSource`，必须使用单一
composition-owned MusicBrainz request coordinator，由 live source 与 enricher
共用；未启用第二个 live client 时不得为未来可能性先行扩大实现范围。**

- coordinator 持有一个可联系 UA、host allowlist（仅 `musicbrainz.org` 官方
  WS/2 主机/路径）、pacing（**整个 client 平均 ≤1 req/s**，跨成功与失败）、
  retry accounting（429/5xx 有界退避）与 **total attempt budget**。
- **每次 HTTP attempt 都计数**（成功、失败、重试、超时全部计入同一有限预算）；
  预算耗尽 → 显式失败（不无限重试）。
- **并发 run**：单 run 锁 + 共享 limiter；并发 run 的合并请求同样受同一 pacing
  与预算约束（不因并行翻倍突破 1 rps）。
- 所有网络行为可注入（transport/clock/sleeper），测试不触网。

### D6 — production-source gate 与统一 provenance 契约（修订：ADR2-006）

**决策：Album 候选统一为版本化 `CandidateBatch`/source envelope；生产 gate 同时
要求一个经过验证的非 demo `GenreSourceDescriptor`。两者共同组成可交付的
`ValidatedSourceSet`，任一为 sample/demo 或 provenance 不完整都不得外部推送。**

- `CandidateBatch` 结构（版本化 schema）：immutable **source descriptor**
  （source_id、origin_url/query、retrieved_at、query_policy_version、
  license identifier、demo flag、content digest）+ **per-candidate** 记录
  （MBID、title、artist、year、type、score 仅作相关性参考）。
- `GenreSourceDescriptor` 绑定当前 Genre package 的 source_id、origin、license、
  schema/package version、demo flag 与 content digest；现有 illustrative
  `rym-sample` 必须在 `--deliver` 下被拒绝，不能因为 Genre 名称真实就视为生产源。
- **trusted composition（`build_production_engine`）在 journal claim 与任何
  delivery 之前**校验 batch：schema 版本匹配、digest 自洽、license 齐全且允许、
  demo flag=false、来源在 allowlist；任一不符 → fail-closed（无外部调用、无历史
  变更）。
- 校验必须是**内容级**（batch 与其证据绑定），不是字符串比较——自标 allowlist
  字符串的畸形/伪造 batch 同样失败。
- `--deliver` 仅接受已通过校验的 `ValidatedSourceSet`；dry-run 可继续用 sample
  Genre/Album 数据（本地、history-neutral）。

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
  3. **任何无法证明 attempt 关联的 pre-v3 既有行**（包括 v1、
     v2-with-column 与 v2-without-column）保留 NULL 且继续不可变；不得猜测或
     合成 attempt id；新 v3 finalize 必须写入生成的 attempt id；
  4. 完成加列后 `PRAGMA user_version = 3`；
  5. `user_version > 3` 或未知 schema fingerprint → **fail-closed**（raise，不
     改库）。
- **回滚 = forward-fix（修复/重放）或迁移前备份恢复**，绝不删除 `attempt_id`
  列（它是 receipt↔attempt 证据绑定，删除将重开 ADR-0001 已关闭的歧义）。旧
  二进制若因 `user_version=3` 拒绝打开属于安全的 fail-closed 行为；不得为了让
  旧二进制继续写入而降低版本号或删列。
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

- 新增：`CuratedAlbumSource`（G3-007）、
  `data/schemas/candidate_batch.schema.json`、curated package 目录
  （`data/albums/<source_id>/`，贡献流程产物）、runtime cache（`var/` 边界）；
- 条件新增（仅 ODP-1 明确接受后）：live `MusicBrainzAlbumSource` 与跨 live clients
  共享的 `MusicBrainzRequestCoordinator`；未定案前不得借 ADR Accepted 实现；
- 修改：`cli.py`（production-source gate、token 三态）、`production.py`
  （docstring 分类表）、`sqlite_history.py`（begin/receipt 绑定 + v3 fingerprint
  迁移，G4-002C/G4-002D）、`config.py`（`llm.mode` 仅 deterministic、
  `album.*` 预算项）、MP/IP 文档。

**测试影响（设计见 §5）**：新增 CandidateBatch/curated package 校验、gate 正/负、
贡献导入/导出、v3 四布局迁移矩阵、token 三态、docstring 一致、deterministic
marker；若 ODP-1 后加入 live path，再强制 coordinator 共享预算、查询转义/类型
过滤/分页/映射缺失矩阵。既有 630 项不删除不弱化。

**风险与缓解**：

| 风险 | 缓解 |
|---|---|
| 许可边界（supplementary/mixed/非商业） | 许可四层分离 + per-source manifest + ODP-1 Owner 决策；未定案 fail-closed（D1/D2） |
| curated package 覆盖不足/陈旧 | 贡献流程 + 显式版本/retrieved_at；不足时显式失败不填充（D3） |
| 限流/暂时封禁（仅获批 live path） | coordinator 共享 pacing（≤1 rps）+ 总尝试预算 + 缓存命中优先（D5） |
| live 候选池被永久历史耗尽（仅获批 live path） | 有界 offset/limit 分页 + query-version 失效（D3/§8-6） |
| 畸形/伪造来源自标生产 | CandidateBatch 内容级校验（digest/license/demo/allowlist）fail-closed（D6） |
| 迁移破坏证据 | fingerprint 检查 + 幂等加列 + 无删列降级 + 备份恢复（D7） |

## 5. 验收测试设计（本 ADR 只设计，不实现）

映射 G4 Re-review 4 与 ADR-0002 首轮评审的 Required acceptance：

- **AC-1（G4-007B 正 / ADR2-006）**：经公共 `cli.main` + 注入 fake 网络边界，使用
  已校验的非 demo Genre package + `CandidateBatch`（生产 provenance）→ 断言
  选中 Genre、outbound Album 事实与 committed
  官方历史中的 Album 标识**逐条**来自该 batch（batch digest 绑定：committed
  identity 与 outbound fact 都属于同一 validated batch），外部调用恰一次、官方
  历史原子提交。
- **AC-2（G4-007B 负 / ADR2-006）**：sample/demo Genre package、sample/demo
  CandidateBatch、**missing provenance、自相矛盾的 provenance、伪造来源（自标
  allowlist 字符串但 digest/license 不符）** 全部 → `--deliver` 拒绝：非零退出、
  `transport.calls == 0`、官方历史零变更。
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
  attempt_id 在无法证明既有绑定时保留 NULL；`user_version > 3` 或未知 fingerprint
  fail-closed（不改库）；**无删列降级路径**。
- **AC-8（G4-009 / ADR2-008）**：`llm.mode=deterministic` 全链路不调用外部 LLM，
  交付物为确定性事实报告，narrative 存档为 typed deterministic marker；
  `llm.mode=provider` 在 config validation 即 fail-closed（run/journal/network
  副作用前）。
- **AC-9A（D1/D2/D6，G3-007 必需）**：curated Genre/Album packages 的
  manifest/schema/digest/registry binding、显式 import/export、普通 run 不写
  tracked Git、缺失/过期/候选不足失败，以及至少一组经审核的非 demo Genre + Album
  packages（足以完成真实 3×3）全部通过；永久历史排除后，本地数据按确定性顺序继续
  提供尚未推荐的记录，耗尽时显式失败。
- **AC-9B（D1/D3/D5，仅 ODP-1 接受并实现 live path 时启用）**：MusicBrainz
  相关注入 transport 全表——200 正常 / 429
  退避 / 5xx / 畸形体 / 超时 / 预算耗尽显式失败；**Lucene 保留字符与多词 Genre
  name 不改变查询结构**；release-group 类型过滤（Single/EP 剔除）；**no-mapping
  与 insufficient-candidates 可观测**；**分页越过已入历史的第一页**且不无界爬取；
  **source 与 enricher 共享 coordinator：每次 HTTP attempt（含失败/重试）都计入
  同一预算，合并调用时间戳满足 ≤1 rps**；search score 仅相关性、不作为
  popularity filter。

**ADR2 新增验收（Required revised acceptance additions）映射**：①许可/provenance
fixtures 区分 CC0 core facts 与 supplementary tag/search evidence，生成的 package
无有效依据不得整体标 CC0（AC-9A/AC-1）；②普通 run 查询只写 Git 忽略缓存，显式
export/import 是唯一产生可审 Git 数据的路径（AC-9A/AC-1）；③保留字符/多词 Genre
不能改查询结构，映射缺失与无关类型明确失败（条件 AC-9B）；④首页候选入永久历史
后有界分页可发现后续页，耗尽/不稳定显式失败且无 sample 替代、无历史污染（条件
AC-9B/AC-2）；⑤source+enricher 共享 coordinator，每次尝试计入预算、时间戳满足
pacing（条件 AC-9B）；
⑥provenance schema 不一致、digest/origin/license 缺失、伪造生产状态都在 PushPlus
前与官方历史变更前失败（AC-2/AC-1）；⑦v2-with-column / v2-without-column /
future-version 库按修订后安全 v3 迁移/fail-closed 规则且不删交付证据（AC-7）。

## 6. 阶段状态与 Gate 流程

- **当前**：ADR 修订 v2 已由 Reviewer 接受；项目转为 `G3 / READY`，只授权下一
  个窄幅 checkpoint，不代表实现或 Gate 已接受。
- **下一步**：先进入窄幅重开的 G3-007，只实现并验证 §8 中适用于 source/data 的
  工作；生成独立 G3-007 报告与 candidate 后停止，等待
  Reviewer checkpoint。只有 G3-007 被接受后，才恢复 G4 的 production-source
  gate、`--deliver` 接线、G4-002C/G4-007C/G4-002E、v3 forward migration 与
  MP/IP 修订。
- ADR 接受不授权 merge/tag/G5；G3-007 与随后完整 G4 candidate 仍须分别评审。

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

## 8. Reviewer acceptance constraints（接受约束）

以下约束是本次 Accepted 决策的一部分，优先消除正文仍可能产生的实现歧义；
Executor 不得自行弱化：

1. **默认来源与 ODP-1 分离**：本次接受的 v0.1 默认生产来源是经过审核的
   `CuratedAlbumSource`/curated package。ODP-1 仍未由 Owner 定案，因此本次接受
   **不授权实现或启用 live MusicBrainz tag-search AlbumSource**；它只能在 Owner
   将 ODP-1 的决定和许可影响写入治理记录后另行实现。既有 MusicBrainz canonical
   enrichment 不因本条被移除。
2. **不能用“安全拒绝一切”冒充完成**：G3-007/G4 最终验收必须包含至少一组
   非 demo、人工审核、许可与 provenance 完整、足以完成一次真实 3×3 推荐的 curated
   Genre + Album packages。现有 `rym-sample` Genre package 也是 demo，生产 gate
   必须拒绝。没有真实数据时 `--deliver` 必须 fail-closed，但仅证明 fail-closed
   不足以关闭 G4-007B。
3. **G3-007 单独过 Gate**：G3-007 只实现 source-side 工作：
   `CuratedAlbumSource`、`CandidateBatch` 与 `GenreSourceDescriptor` 契约/校验、
   curated import/export 贡献流程、Git-ignored runtime cache，以及这些边界的
   fixtures/许可/provenance 测试。
   Executor 必须生成独立 G3-007 review package，置为 `READY_FOR_REVIEW` 后停止。
   Reviewer 接受该 checkpoint 前，不得开始 G4 production composition、PushPlus
   接线或把 G3/G4 改动混成一个不可分审计包。
4. **source-set 校验位置与 Core 边界**：`build_production_engine` 只能在组装时
   校验 source registry/config；运行期 `GenreSourceDescriptor` 与
   `CandidateBatch` 必须在 FETCH/source adapter 返回后、进入选择与任何 delivery
   claim 之前，由可信 application boundary 组成并校验为 `ValidatedSourceSet`。
   Core 仍只处理候选事实与确定性选择，不承担许可、网络或 provenance 策略。
5. **digest 是完整性，不是身份认证**：content digest 只能证明 batch 内容未在校验
   后改变，不能证明 source_id/license 声明真实。可信度来自显式安装且经审核的
   source registry：registry 将 Genre/Album source_id 绑定到预期 origin、license、
   schema 和 demo policy；manifest/descriptor/batch 与 registry 任一不一致即
   fail-closed。不得声称可抵抗已获本地仓库写权限的恶意代码/数据修改，除非未来
   另有签名信任 ADR。
6. **查询/分页仅属于获批 live 路径**：curated package 使用确定性、版本化本地记录，
   不伪造 provider cursor。若 ODP-1 后启用 MusicBrainz search，只能使用其实际
   `offset`/`limit` 能力；page size、max pages、总 attempts 都必须是有硬上限的正
   整数。query/page/order/policy version 纳入 cache key；跨页重复、结果漂移或耗尽
   必须显式失败。Lucene escaping、primary type=Album 和无 popularity weighting
   约束保持不变。
7. **限速必须跨进程有效**：若 live MusicBrainz 路径未来获批，单-run lock 和
   request pacing 不能只是两个 adapter 各自的内存对象。v0.1 必须通过同一
   process-independent 本地锁/协调状态阻止并发进程突破限制；source 与 enricher
   的每个 HTTP attempt 共用预算与至少一秒的请求间隔。
8. **provenance 必须可追溯到运行证据**：在 FETCH/SELECT journal 中记录经过验证的
   Genre source_id/digest、Album source_id/CandidateBatch digest、schema/
   query-policy version 与检索/包版本；outbound payload 的选中 Genre/Album 事实和
   最终提交的 MBID 必须能回溯到同一 `ValidatedSourceSet`。不得把 delivery payload
   digest 当作 candidate-source digest 的替代品。
9. **v3 不合成、不降级**：任何 pre-v3、无法证明 attempt 关联的 receipt（不只 v1）
   保持 NULL 且不可变；future/unknown schema fail-closed。旧二进制拒绝 v3 是允许的
   安全结果，绝不得降低 `user_version`、删列或合成 attempt id 来换取兼容。
10. **deterministic 就是真正零 LLM**：v0.1 config 只接受 deterministic；不得构造
    `_LocalEchoTransport`、不得保存伪 narrative。未来 provider mode 仍需独立实现、
    版本化配置与 Gate 接受。
11. **验收矩阵不可缩减**：§5 AC-1～AC-8、AC-9A 和首轮 Reviewer 中适用于 curated
    默认路径的验收全部是当前关闭条件；AC-9B 仅在 ODP-1 接受且 live path 被实现时
    同步成为关闭条件。测试不得以空数据、全 fail-closed 或仅 fake “production”
    标签替代一次真实、非 demo Genre + Album curated 3×3 端到端事实来源证明。
