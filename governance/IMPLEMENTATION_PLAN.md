# OMDA Implementation Plan（G0 提案稿）

> 状态：PROPOSED —— 待 GPT-5.6 Sol 独立评审
> 作者：DeepSeek V4 Flash（Executor）
> 日期：2026-08-19
> 基线：`docs/OMDA_AGENT_HANDOFF_SPEC.md`（v0.1）、`docs/OMDA_PROJECT_MASTER_PLAN_zh-CN.md`（v0.1）、`docs/OMDA_DUAL_MODEL_OPERATIONS_HANDBOOK_zh-CN.md`（v1.0）
> 本文件在权威顺序中位于「已批准 IMPLEMENTATION_PLAN」层级；本稿未获批准前不具约束力，仅作为 G0 评审对象。本稿**不修改、不弱化、不重新解释**任何高层规范条款；如与高层冲突，高层优先。

---

## A. 产品理解（Executor 用自己的语言复述）

### A.1 项目目标

OMDA（Open Music Discovery Agent）是一个本地优先、可审计的每日音乐探索工具。它的使命是**长期发现而非热门复刻**：每天产出一份 3×3 的推荐清单——3 个 Genre、每个 Genre 3 张 Album、共 9 张——每张 Album 都从未被系统成功推荐过，且整个选择过程可解释、可复现、可被社区审查。

它首先服务单个用户（Owner）的日常探索；同时因为采用可 diff 的文本数据、版本化 Schema、明确的 Adapter 边界和双模型审计流程，具备开源社区贡献的可行性。

### A.2 MVP 与每日数据流

一次「每日运行（run）」从用户启动开始，逻辑流程固定为：

```text
PLAN → FETCH → SELECT → GENERATE → VALIDATE → DELIVER → COMMIT HISTORY
```

逐环节的职责（用自然语言描述）：

1. **PLAN**：读取合法 Genre 文本数据、配置和成功历史；确定本次运行的 pick 语义（3 个 Genre，含内部确定性的 pick 顺序）、注入 seed、记录输入数据版本。
2. **FETCH**：为每个被选 Genre 获取候选 Album 并补全必要信息；数据可来自本地文本数据、社区/权威来源（如 MusicBrainz）以及 RYM 浏览器会话的**按需** enrichment；全部网络访问有界、可缓存、可失败。
3. **SELECT**：确定性规则在候选池上完成选择——排除冷却中 Genre、满足 family/parent 多样性、排除历史已推荐与本次已选的 Album、满足年份约束、按可配置权重组合评分并确定性破平。
4. **GENERATE**：LLM 只拿到一份经过验证的「事实包（fact packet）」，为最终清单撰写介绍性文案；LLM 无任何选择权。
5. **VALIDATE**：对 LLM 输出做结构、长度、引用事实校验；任何校验失败都不进入交付。
6. **DELIVER**：通过输出适配器（默认本地 Markdown 文件，可替换为 PushPlus）投递；投递带稳定的幂等键。
7. **COMMIT HISTORY**：**仅当**校验通过且交付成功之后，才把 3 个 Genre pick 写入官方 cooldown 历史、把 9 张 Album 写入官方推荐历史。

失败语义：FETCH 到 DELIVER 任一步失败，官方历史一律不得写入；失败运行不消耗任何官方 pick 序号。「已交付但本地 history commit 失败」的窗口由 run journal + 幂等键 + 显式恢复状态处理，**不宣称**外部推送与本地 SQLite 之间存在绝对原子性。

### A.3 产品不变量（逐条复述，附规范出处）

| # | 不变量（Executor 语言） | 出处 |
|---|---|---|
| I-1 | 合法且未被冷却的 Genre 一律等权；任何 popularity 过滤、人为 Tier 概率、LLM「质量分」都不得影响基础资格或权重。 | SPEC §2.1；MP §3.1 |
| I-2 | cooldown 以**成功提交的全局 pick 序号**计：第 p 次成功提交后，p+1..p+30 不可再选，p+31 起可恢复；失败/放弃运行不消耗序号；多次选择同一 run 内 pick 顺序确定且可测。 | SPEC §2.2；MP §3.1 |
| I-3 | family/parent 多样性是**集合约束**（避免当日 3 个 Genre 过度同族），不是评分手段；不得借此永久饿死某族；受限 family（地域/传统类）默认每 run 至多 1 个；约束不可满足时必须给出有界、显式的结果并保证终止。 | SPEC §2.3；MP §3.1 |
| I-4 | 每 run 内 9 张 Album 两两不同；任何成功推荐的 Album 永久排除，优先用稳定 canonical identity（如 MusicBrainz release-group）；字符串降级必须可预期规范化、记录歧义，禁止基于不可审查的模糊猜测做破坏性永久封禁。 | SPEC §2.4；MP §3.2 |
| I-5 | 每 Genre 默认 3 张；存在合适候选时至少 1 张 year ≥ 2010，正常情况至多 2 张更老；缺现代候选时不得硬塞无关 Album，必须走明确的可观测失败/降级路径。 | SPEC §2.5；MP §3.2 |
| I-6 | RYM / critic / community / personal rating 是相互独立的维度；权重与缺失值策略是**配置**而非代码常量；新增 critic 来源原则上不动 Recommendation Core。 | SPEC §2.6；MP §3.3 |
| I-7 | 确定性 Core 做全部选择与约束；LLM 只基于给定事实解释；网页/外部文本均为不可信数据，不得作为指令执行。 | SPEC §3.1/3.5；MP §3.6 |
| I-8 | RYM 只走合法用户会话 + 薄 Browser Companion + 按需 enrichment + 本地缓存；禁止 Cloudflare 绕过、验证码自动化、隐身对抗、全站预抓、默认 Album Detail fan-out。 | SPEC §3.4；MP §3.4 |
| I-9 | 社区数据真源是可 diff 文本（YAML/CSV/JSON/JSONL），带版本化 Schema；SQLite 只做 runtime state / cache / index，永不作社区真源。 | SPEC §3.3；MP §3.5 |
| I-10 | 只有 PLAN→FETCH→SELECT→GENERATE→VALIDATE→DELIVER 全部成功才 COMMIT HISTORY；delivered-but-not-committed 有 journal/幂等恢复，不虚假宣称跨系统原子性。 | SPEC §4；MP §3.7 |

补充固定语义（SPEC §2）：`daily_genre_count=3`、`albums_per_genre=3`、`genre_cooldown_picks=30`、`modern_album_year=2010`；默认值可配置，但改变产品语义/默认值需要 ADR。

---

## B. 最小架构与模块职责

目标：Core 纯净、边界显式、依赖单向、平台无关。所有模块按「依赖箭头永远朝内指向 Core」组织。

```text
                        ┌─────────────────────────────┐
                        │  CLI / Scheduler（G5 之前仅 CLI） │
                        └──────────────┬──────────────┘
                                       ▼
                        ┌─────────────────────────────┐
                        │  Application Orchestrator     │◄── Run Journal（状态机）
                        │  编排一次 run、错误分类、重试、  │
                        │  验证门、交付门、history commit │
                        └──────────────┬──────────────┘
                                       ▼
                        ┌─────────────────────────────┐
                        │  Recommendation Core（纯/确定性）│◄── Config / Domain Models
                        │  资格 · cooldown · diversity ·  │
                        │  去重 · 年份 · 评分组合 · 选择     │
                        └──────────────┬──────────────┘
                                       ▼
                        ┌─────────────────────────────┐
                        │  Ports（接口，无实现）            │
                        │  Genre / Album / Critic /     │
                        │  History / LLM / Delivery     │
                        └──────────────┬──────────────┘
                                       ▼
                        ┌─────────────────────────────┐
                        │  Adapters                     │
                        │  文本数据集 · MusicBrainz ·    │
                        │  Browser Companion · SQLite · │
                        │  LLM Provider · Markdown ·    │
                        │  PushPlus                     │
                        └─────────────────────────────┘
```

### B.1 Recommendation Core（核心）

- 职责：领域模型 + 纯确定性规则。包括：Genre 资格与等权选择、cooldown 推进、family/parent 集合约束求解、Album canonical 去重与永久排除、年份约束、评分组合（权重/缺失策略/确定性破平）、选择结果生成。
- 硬约束：**零导入**具体浏览器、RYM DOM、PushPlus、LLM vendor、数据库驱动；只操作领域值与 Ports。
- 确定性：接受可注入的随机源或 seed；禁止依赖 set/dict 迭代序做排序依据。

### B.2 Application Orchestrator（应用编排）

- 职责：一次 run 的状态机推进（PLAN→FETCH→SELECT→GENERATE→VALIDATE→DELIVER→COMMIT HISTORY + FAILED/ABANDONED/recovery 状态）、错误分类、有界重试、journal 读写、验证门、交付门、history commit。
- 它调用 Core 做纯计算，调用 Adapters 做副作用；自身不含推荐规则。

### B.3 Ports（端口，接口契约）

- 最小接口集：`GenreSource`、`AlbumSource/Enricher`、`CriticRatingSource`、`HistoryPort`、`LLM`、`Delivery`。
- 每个 Port 定义领域级错误类型（SPEC §8 错误分类），不泄漏供应商控制流。
- **时序（G0-001 修复）**：G2 Orchestrator 所需的最小 Port protocols 与领域错误分类在 **G1 末尾（T1.6）定义**，先于任何 Orchestrator 工作；G2 全程基于 fake/in-memory 测试实现运行。具体外部 Adapter（RYM/MusicBrainz/PushPlus/LLM vendor 等）在 G3/G4 实现，可经正常 Gate 评审细化 source-specific 契约，但**不是**应用边界的首次出现点。

### B.4 Adapters（适配器，位于边缘）

- 文本数据集 Adapter：读取 `data/` 下 YAML/CSV/JSON(L)，过 Schema 校验，返回领域值。
- MusicBrainz / 社区来源 Adapter：按需 enrichment，bounded timeout/retry/backoff，带缓存与 provenance。
- Browser Companion Adapter：RYM 薄会话提取（见 B.6）。
- SQLite Adapter：runtime state（journal、history、cache、idempotency），事务化写。
- LLM Provider Adapter：vendor SDK 只存在于此处；输出先过校验。
- Markdown / PushPlus Delivery Adapter：幂等投递、重试边界、收据记录。

### B.5 Storage（存储）

- **社区真源**：`data/` 下的可 diff 文本（genres/、critics/、schemas/），Git 提交，版本化 Schema。
- **运行时**：`var/`（SQLite、缓存、临时输出），`.gitignore` 已排除；迁移可检测、可备份、可回滚或提供恢复说明。
- **数据保护边界（G0-002 修复）**：真实运行时数据（官方 history、delivery/recovery 证据）受保护，**不得被删除或重置**；恢复只允许备份、迁移、非破坏性补偿。只有 **disposable test database**（测试隔离的临时库）可自由重建。
- 密钥：仅环境变量 / 本地 secret store；cookie/profile 永入 Git、日志、Prompt。

### B.6 Browser Companion（浏览器伴生）

- 形态：独立薄进程/脚本（Playwright/CDP 可选实现，**不**作为 Core 依赖），连接用户**合法登录会话**，人工可介入。
- 行为：只提取当前 run 所需最小页面数据；按需 enrichment；本地缓存带 provenance 与时间戳；会话失效/验证出现时暂停并请求人工处理；不绕过 Cloudflare、不自动解验证码、不预爬全站、Album Detail 逐页 fan-out 不是默认路径。
- 边界：cookie/profile 只在本机，被 Git 忽略，不进日志与模型 Prompt。

### B.7 LLM（语言模型）

- 输入：由 Orchestrator 构造的**有界、已验证事实包**（run id、Genre、Album 事实、规则证据）。
- 输出：叙述性文案。校验通过前不得交付；任何外部文本中的指令都只是数据。

### B.8 Output（输出）

- 默认：本地 Markdown 文件（dry-run 与日常可用）；可替换：PushPlus（微信）。两者都走同一 Delivery Port，幂等键由 run id 派生。

### B.9 依赖方向与禁止项（架构约束）

- 依赖方向：CLI → Orchestrator → Core；Core → Ports ← Adapters；Storage 只被 Adapters/Orchestrator 用。
- **Core 纯净性（G0-002 修复，架构测试强制）**：Core 无任何 persistence import/call——不得导入或调用 SQLite、`HistoryStore` 或文件读写；历史 exclusion set 由 Orchestrator/History Port 读取后以**不可变领域输入**传入 Core。
- 禁止（无 ADR 不得引入）：Core 内出现 vendor SDK 或 persistence 导入；社区数据以 SQLite 为真源；历史在交付成功前写入；无界重试/搜索；秘密/cookie/profile 进入仓库工件；Cloudflare 对抗、全量预爬、默认 fan-out；LLM 参与选择。

---

## C. G1–G5 Milestones 与 Atomic Tasks

每个 Gate 以 `exec/gN-*` 分支交付，基于上一被接受 SHA；完成标准是「测试全绿 + 不变量测试 + 送审包 + READY_FOR_REVIEW」。任务字段统一：Goal / Inputs / 允许范围 / Deliverables / Tests / Acceptance Criteria / Dependencies / Rollback / Risks。

### C.1 G1 Foundation（对应 SPEC §10：schemas、config、validation、storage boundary、test infra）

**Milestone 目标**：仓库骨架、版本化 Schema 全集、分层配置、SQLite runtime 边界与迁移、测试基建与 fixtures 全部就位；**不含任何推荐逻辑**。

#### T1.1 仓库骨架与工程基线
- Goal：可安装、可测试、可 lint 的最小工程。
- Inputs：Master Plan §4 目录建议、`.gitignore`、AGENTS.md。
- 允许范围：`pyproject.toml`、包布局 `src/omda/`、`tests/` 目录、`var/.gitkeep`、lint/format 配置（ruff）。
- Deliverables：可 `pip install -e .`；`pytest` 空跑通过；`.gitignore` 复核无缺口。
- Tests：CI 冒烟（import、collect）。
- Acceptance：从干净 venv 可安装并收集测试；无未忽略的 secrets 模式。
- Dependencies：无第三方运行时依赖（测试工具除外）。
- Rollback：本 Gate 全部为新增文件，`git revert` 可整体回退。
- Risks：低。

#### T1.2 版本化 Schema 定义与校验器
- Goal：SPEC §5 所列 9 类记录的 Schema 全部版本化、可机器校验、报错定位到记录。
- Inputs：SPEC §5；MP §5。
- 允许范围：`data/schemas/` 下 Schema 定义（JSON Schema 或等价声明式校验）、校验器、fixtures。
- Deliverables：Genre、Album identity、critic source/rating、plan/fact packet、run journal、official Genre pick history、official Album history、delivery receipt/idempotency、application config 的 Schema；每类含合法样例 + 畸形样例。
- Tests：Schema 接受/精确拒绝测试（SPEC §7-1）；错误信息含记录定位。
- Acceptance：每类记录通过校验或报出具体字段/行；schema 版本号随迁移递增。
- Dependencies：T1.1。
- Rollback：新增文件为主，`git revert` 可回退。
- Risks：Schema 形状过早固化——应对：以 SPEC §5 为唯一依据，超出项列入 Open Decisions。

#### T1.3 分层配置系统
- Goal：默认值 + 用户覆盖 + 运行时覆盖；约束校验；确定性 seed 通道。
- Inputs：SPEC §2（四个默认常量）、§6（seed）。
- 允许范围：`omda/config.py` 与配置 Schema、示例配置、校验。
- Deliverables：配置加载/合并/校验；`daily_genre_count=3`、`albums_per_genre=3`、`genre_cooldown_picks=30`、`modern_album_year=2010` 为默认且可覆盖。
- Tests：默认值、覆盖优先级、非法值拒绝。
- Acceptance：改变产品语义的配置被 Schema 显式标注「需 ADR」。
- Dependencies：T1.2。
- Rollback：配置纯文本，回退易。
- Risks：把「可配置」误解为「可改语义」——Schema 注释与测试双重约束。

#### T1.4 存储抽象与 SQLite runtime 层
- Goal：runtime 状态落库边界；事务、迁移、journal 表骨架。
- Inputs：SPEC §3.3、§4、§5；MP §5。
- 允许范围：`omda/storage/` 抽象 + SQLite 实现（append-friendly journal、pick history、album history、cache、idempotency、迁移元数据）。
- Deliverables：表结构与迁移 v1；事务化读写；schema_version 记录。
- Tests：事务回滚、迁移幂等、并发/重入基本行为。
- Acceptance：写入可审计；迁移可检测可备份；社区真源不落 SQLite。
- Dependencies：T1.2。
- Rollback：`var/` 可删可重建（非真源）；代码回退用 `git revert`。
- Risks：把 SQLite 当社区真源——架构约束测试（§D）把关。

#### T1.5 测试基建与 fixtures
- Goal：fixtures 目录、确定性 seed 工具、property 测试骨架、统计检验骨架。
- Inputs：SPEC §6、§7；OPH §12。
- 允许范围：`tests/fixtures/`、`tests/unit|integration|contract/` 骨架、conftest。
- Deliverables：可复现 seed；Genre/Album/critic fixtures；统计测试基础设施。
- Tests：fixture 本身过 Schema。
- Acceptance：任何测试可用 `--seed` 复现；live 网络非必需。
- Dependencies：T1.2。
- Rollback：新增测试文件，易回退。
- Risks：fixture 与真实数据脱节——fixture 附带 provenance 与生成说明。

#### T1.6 应用 Port protocols 与领域错误分类（G0-001 修复：前置至 G1）
- Goal：在任何 Orchestrator 工作开始前，定义 G2 所需的最小应用边界。
- Inputs：SPEC §3.1/§3.2/§8；MP §4。
- 允许范围：`omda/ports/`（接口与领域错误类型，**无实现**）。
- Deliverables：`GenreSource`、`AlbumSource/Enricher`、`CriticRatingSource`、`HistoryPort`、`LLM`、`Delivery` 六个最小 Port protocol；SPEC §8 领域错误分类（invalid input / unavailable / insufficient candidates / invariant / generation / validation / delivery / state commit）。
- Tests：契约测试骨架（接口形状、错误分类映射）；**fake/in-memory 测试实现**（供 G2 使用：fake LLM、fake Delivery、in-memory journal/history）。
- Acceptance：G2 无任何任务依赖 G3 才首次出现的契约；错误分类不泄漏供应商细节。
- Dependencies：T1.2。
- Rollback：纯接口层，可 revert。
- Risks：接口过度设计——按 G2 Orchestrator 实际需要的最小集收敛。

### C.2 G2 Recommendation Core（SPEC §10 最高风险 Gate）

**Milestone 目标**：纯推荐规则 + 可恢复事务模型全部实现并经受最强测试；Core 零外部依赖。

#### T2.1 领域模型与 Genre 等权选择器
- Goal：Genre 领域对象、资格判定、确定性等权选择（可注入 seed）。
- Inputs：SPEC §2.1、§6；MP §3.1。
- 允许范围：`omda/core/` 纯逻辑。
- Deliverables：`eligible()`、等权抽样（无 popularity 输入）、内部 pick 顺序确定性。
- Tests：等权 property/统计测试（SPEC §7-2）；同一 input+config+seed 可复现（§7 一般要求）。
- Acceptance：统计上无明显偏差且无 flaky 阈值；随机源可注入。
- Dependencies：T1.3（配置）、T1.5（seed 工具）。
- Rollback：Core 纯函数，可 revert；不触历史数据。
- Risks：R-003 等权被悄悄替代——Core 契约测试禁止 popularity 字段进入选择路径。

#### T2.2 Cooldown 引擎
- Goal：按成功提交 pick 序号的 30/31 边界。
- Inputs：SPEC §2.2；MP §3.1。
- 允许范围：`omda/core/cooldown.py`。
- Deliverables：`p+1..p+30` 不可选、`p+31` 可恢复；仅成功提交推进。
- Tests：边界 30/31（SPEC §7-3）；失败/放弃不消耗序号。
- Acceptance：多 Genre 内部 pick 顺序确定性可测。
- Dependencies：T2.1。
- Rollback：纯逻辑。
- Risks：把 cooldown 错写成天数/运行次数——测试锁定语义。

#### T2.3 family/parent 多样性约束求解
- Goal：集合约束、有界、可终止；受限 family 每 run 至多 1 个（默认）。
- Inputs：SPEC §2.3；MP §3.1。
- 允许范围：`omda/core/diversity.py`。
- Deliverables：约束求解；不可满足时的有界显式结果（放弃该组合并重新规划，有限步）。
- Tests：多 pick 顺序与多样性（SPEC §7-4）；不可满足终止（§7-5）；不永久饿死某族（property）。
- Acceptance：多样性不进入评分；循环必然终止。
- Dependencies：T2.1、T2.2。
- Rollback：纯逻辑。
- Risks：diversity 变相 popularity filter——代码审查 + 测试断言「约束前后候选池集合不被改写」。

#### T2.4 Album 候选过滤与 canonical 去重
- Goal：run 内去重 + 历史永久排除；canonical identity 优先，字符串降级带置信度。
- Inputs：SPEC §2.4；MP §3.2。
- 允许范围：`omda/core/album.py`、identity 规范化。
- Deliverables：`canonical_id` 匹配；run 内 dedup；历史排除（基于**传入的不可变 exclusion set**）；模糊匹配记录歧义且不静默永久封禁。
- Tests：同名不同发行不误并、同发行不同名仍判重（SPEC §7-6）；跨 Genre 候选重叠不重复选；**以历史 exclusion set 作为参数输入的单元测试**（Core 不读取任何存储）。
- Acceptance：破坏性永久排除只基于可审查 identity；Core 不读取 SQLite/HistoryStore/文件。
- Dependencies：T2.1、T1.6（HistoryPort 契约：Orchestrator 读取版本化历史快照/exclusion set 后作为领域输入传入 Core）。
- Rollback：纯逻辑。
- Risks：R-004 canonical 错配——fixtures 覆盖混淆场景。

#### T2.5 年份约束与评分组合
- Goal：2010+ 至少一张（候选允许时）；至多 2 张旧；评分多维度、权重/缺失可配置、确定性破平。
- Inputs：SPEC §2.5、§2.6；MP §3.2/§3.3。
- 允许范围：`omda/core/year.py`、`omda/core/rating.py`。
- Deliverables：年份选择策略（含缺年份/缺现代候选路径）；评分组合与 tie-breaking。
- Tests：有/无/未知年份三种情形（SPEC §7-7）；多来源、缺评分、权重、确定性 tie（§7-8）。
- Acceptance：缺现代候选时走明确降级且被观测报告；rating 维度为数据维度而非代码常量。
- Dependencies：T2.4。
- Rollback：纯逻辑。
- Risks：写死单一评分源——配置 Schema 强制维度化。

#### T2.6 Run 事务状态机与恢复
- Goal：SPEC §4 状态机 + FAILED/ABANDONED/recovery；journal 幂等恢复。
- Inputs：SPEC §4、§8；MP §3.7。
- 允许范围：`omda/orchestrator/`（状态机）、journal 写入协议。
- Deliverables：状态机推进；每步失败落 FAILED 且历史不变（SPEC §7-9）；delivered-but-not-committed 恢复（§7-10）；崩溃重跑（§7-11）。
- Tests：**本任务全程针对 T1.6 定义的 Port 契约运行，使用 fake/in-memory 测试实现**——fake LLM（返回预置文本）、fake Delivery（记录投递收据）、in-memory journal/history；覆盖 GENERATE、DELIVER、journal 与 history 各状态迁移；失败注入（fetch/generate/validate/deliver 各失败）；交付成功但 commit 失败的恢复；每个持久转变点崩溃重放。具体 LLM/PushPlus/RYM 等外部 Adapter 在 G3/G4 实现，不阻塞本任务。
- Acceptance：官方 history 仅在 DELIVERED 后写；幂等键稳定；恢复查询持久证据而非记忆。
- Dependencies：T2.1–T2.5、T1.4（存储实现）、T1.6（Port 契约）。
- Rollback（G0-002 修复）：状态机逻辑 revert；**真实运行时数据（官方 history、delivery/recovery 证据）受保护，回滚仅限备份、迁移、恢复或非破坏性补偿，不得删除/重置**；只有 disposable test database 可重建。
- Risks：R-001/R-009——本 Gate 核心风险，测试矩阵专门覆盖。

### C.3 G3 Data & Adapters（SPEC §10：数据与 adapter 契约、provenance、缓存、Browser Companion 边界）

**Milestone 目标**：Port 契约定型；文本数据、MusicBrainz、critic、Browser Companion 各 adapter 以 fixtures 为主可测；live RYM 非必需。

#### T3.1 具体外部 Adapter 实现（基于 G1/T1.6 既有 Port 契约）
- Goal：为 G1/T1.6 已定义的六个 Port 契约提供具体外部实现；**Port 接口的首次定义不在本任务**。
- Inputs：SPEC §3.1/§3.2/§8；MP §4；T1.6 契约。
- 允许范围：`omda/adapters/` 实现类（文本数据集、MusicBrainz、Browser Companion、LLM Provider、Markdown/PushPlus；SQLite 存储实现已在 T1.4）。
- Deliverables：各 Adapter 实现 + 错误分类映射；source-specific 契约细化（如有）必须经正常 Gate 评审，不得改变 T1.6 已定应用边界。
- Tests：契约测试（§D.5）；每个 Adapter 的 fixtures 测试（SPEC §7-12）。
- Acceptance：Core 只见领域错误，不见供应商细节；Port 接口形状不因 Adapter 实现而返工。
- Dependencies：G2 全部、T1.6。
- Rollback：Adapter 可独立回退。
- Risks：接口过度设计——按最小集收敛，任何多余抽象需自证。

#### T3.2 文本数据集 Adapter
- Goal：`data/` 文本→领域值；Schema 校验；provenance。
- Inputs：SPEC §3.3；MP §5。
- 允许范围：`omda/adapters/datasets.py`、`data/genres/`、`data/critics/` 骨架。
- Deliverables：Genre 数据集（genre_id/name/url/family/parents/eligible/source）；critic 贡献形状（source.yaml + ratings.csv）；每来源 license/抓取日期/边界。
- Tests：畸形记录精确拒绝（SPEC §7-1）。
- Acceptance：新增 critic 源不触发 Core 修改（SPEC §2.6）。
- Dependencies：T3.1、T1.2。
- Rollback：数据与代码都可 revert；社区文本是 Git 内容。
- Risks：R-006 许可——每个来源必填 provenance 字段。

#### T3.3 MusicBrainz / 社区 enrichment Adapter
- Goal：按需补全 canonical identity 与基础事实；有界网络行为；缓存。
- Inputs：SPEC §3.2；MP §5。
- 允许范围：`omda/adapters/musicbrainz.py`、缓存层。
- Deliverables：release-group 查询、限流/超时/退避、缓存带时间戳。
- Tests：超时/畸形响应/空结果/过期缓存（SPEC §7-12）。
- Acceptance：live 网络非必需（fixtures 覆盖）；失败降级清晰。
- Dependencies：T3.1。
- Rollback：adapter 可独立回退。
- Risks：限流/条款风险——bounded 行为是契约测试内容。

#### T3.4 Browser Companion contract（RYM）
- Goal：合法会话薄伴生、按需提取、缓存、人工介入；合规边界可测。
- Inputs：SPEC §3.4；MP §3.4。
- 允许范围：`browser-companion/`、RYM enrichment contract、缓存与 provenance。
- Deliverables：最小页面提取；会话失效/验证码出现→暂停并请求人工；cookie 隔离；无 Cloudflare 对抗/无预爬/无默认 fan-out。
- Tests：DOM 变化/空页/限流/超时受控（SPEC §7-12）；无保存 cookie 断言。
- Acceptance：contract 测试证明「live RYM 非核心套件必需」且无对抗行为。
- Dependencies：T3.1、T3.3。
- Rollback：伴生独立进程，可停用；不影响 Core。
- Risks：R-005 页面/会话变化——fixtures + 人工介入路径兜底。

#### T3.5 Critic 数据源贡献包
- Goal：社区可只加文本就新增 critic 源。
- Inputs：SPEC §3.3；MP §5；data/critics/README。
- 允许范围：`data/critics/<source>/`（source.yaml + ratings.csv）+ 示例。
- Deliverables：至少 1 个示例贡献包通过全部校验。
- Tests：Schema + 贡献流程演练。
- Acceptance：贡献指南可让新贡献者不写代码完成添加。
- Dependencies：T3.2。
- Rollback：文本贡献可 revert。
- Risks：贡献摩擦——错误信息定位到行。

### C.4 G4 Agent & Delivery（SPEC §10：受控生成、Markdown 校验、交付与恢复）

**Milestone 目标**：LLM 只解释、输出必校验、交付幂等、恢复完备；先 dry-run，不自动推送。

#### T4.1 LLM Provider Adapter 与受控 Prompt
- Goal：vendor 隔离 + 有界事实包 + untrusted content 隔离。
- Inputs：SPEC §3.5；MP §3.6。
- 允许范围：`omda/adapters/llm.py`、Prompt 模板（仓库内）。
- Deliverables：事实包构造；系统指令不可被外部文本覆盖；供应商 SDK 仅在此处。
- Tests：prompt-injection 隔离（SPEC §7-13）。
- Acceptance：LLM 输出不改变任何选择结果。
- Dependencies：T3.1、G2。
- Rollback：adapter 可替换。
- Risks：R-008 注入——测试固化「外部文本只作数据」。

#### T4.2 Markdown 生成与校验
- Goal：结构化、长度受限、引用事实验证。
- Inputs：SPEC §3.5、§8。
- 允许范围：`omda/output/markdown.py`。
- Deliverables：模板渲染；结构/长度/事实引用校验。
- Tests：畸形/超长/编造事实输出被拒。
- Acceptance：校验失败不交付。
- Dependencies：T4.1。
- Rollback：输出层独立。
- Risks：低。

#### T4.3 Delivery Adapter（Markdown / PushPlus）
- Goal：幂等投递、有界重试、收据记录。
- Inputs：SPEC §4；MP §3.7。
- 允许范围：`omda/adapters/delivery.py`。
- Deliverables：幂等键（由 run id 派生）；投递收据写入 runtime 存储；重试边界。
- Tests：重复投递防护；PushPlus 长度/转义（OPH §12）。
- Acceptance：同一 run 重放不产生第二次外部投递。
- Dependencies：T1.4、T4.2。
- Rollback：不投递即回滚；已投递走补偿协议。
- Risks：R-001 重复投递——幂等测试为 Gate 阻断项。

#### T4.4 delivered-but-not-committed 恢复路径
- Goal：SPEC §4「交付成功但本地 commit 失败」的显式恢复。
- Inputs：SPEC §4；MP §6。
- 允许范围：`omda/orchestrator/recovery.py`。
- Deliverables：recovery 状态；重跑前先查询/确认交付结果；补偿/幂等协议文档。
- Tests：deliver 成功后强制模拟 commit 失败→恢复→不盲重复投递（SPEC §7-10）。
- Acceptance：任何路径都不声称跨系统绝对原子。
- Dependencies：T2.6、T4.3。
- Rollback：纯状态机逻辑。
- Risks：R-009——本任务即缓解。

#### T4.5 dry-run 与人工批准门
- Goal：默认 dry-run；自动推送需显式开关。
- Inputs：OPH §14-8。
- 允许范围：CLI 开关、输出目录约定。
- Deliverables：`--dry-run` 默认路径；推送需 `--deliver` 或配置显式开启。
- Tests：dry-run 不产生任何外部调用。
- Acceptance：Owner 可先观察 7 次 dry-run 无历史污染。
- Dependencies：T4.3。
- Rollback：无副作用路径。
- Risks：误自动推送——默认关闭即为防护。

### C.5 G5 Release Audit（SPEC §10：E2E、安装、安全、许可、备份/回滚、RC）

**Milestone 目标**：全链路审计通过 → 建议 `v0.1.0-rc1`（打 tag 由 Reviewer 接受后执行）。

#### T5.1 安装与干净环境验证
- Goal：文档可从零安装并运行 dry-run。
- Inputs：README、pyproject、OPH §14。
- 允许范围：文档、依赖锁定、`.env.example`。
- Deliverables：安装步骤、dry-run 命令、故障排查。
- Tests：全新 venv 安装 + dry-run 冒烟。
- Acceptance：空白环境不依赖 Owner 手工环境。
- Dependencies：全部前置 Gate。
- Rollback：文档回退。
- Risks：低。

#### T5.2 E2E 与失败注入全矩阵
- Goal：SPEC §10 G5 + Prompt 10 七类故障模拟。
- Inputs：SPEC §7；OPH Prompt 10。
- 允许范围：`tests/e2e/`、故障注入工具。
- Deliverables：数据源失败、无现代候选、重复 Album、LLM 失败、推送失败、commit 失败、崩溃重跑的全矩阵证据。
- Tests：历史不变性断言贯穿每项注入。
- Acceptance：任一注入下官方历史零污染。
- Dependencies：G4 全部。
- Rollback：注入工具独立。
- Risks：测试被弱化——「每 skip 必须披露」（SPEC §7）。

#### T5.3 安全/秘密扫描与许可证清单
- Goal：secrets/cookie/profile 零入库；依赖与数据许可清单。
- Inputs：SPEC §7-14；MP §7；OPH §13。
- 允许范围：扫描脚本、`LICENSES.md`。
- Deliverables：secret 扫描（CI 可跑）；依赖许可表；数据源许可表。
- Tests：仓库工件不含 secrets 断言（SPEC §7-14）。
- Acceptance：扫描零命中。
- Dependencies：T5.1。
- Rollback：新增文件。
- Risks：R-002/R-006——扫描即缓解。

#### T5.4 备份/回滚与贡献文档
- Goal：备份恢复演练 + 社区贡献指南。
- Inputs：MP §4/§11；OPH §7.5。
- 允许范围：`docs/`、备份说明、CONTRIBUTING 要点。
- Deliverables：备份/恢复步骤；新增 Genre/critic 源的贡献流程。
- Tests：备份→恢复演练。
- Acceptance：新贡献者可仅凭文本文件贡献并通过校验（MP §11）。
- Dependencies：T5.1。
- Rollback：文档为主。
- Risks：贡献摩擦——指南配合 T3.5 演练。

#### T5.5 连续观察与 RC 建议
- Goal：≥7 次 dry-run/手动运行无历史污染后建议 RC。
- Inputs：MP §11；OPH §14-9。
- 允许范围：观察记录、release notes 草稿、tag 建议命令。
- Deliverables：观察证据；RC 建议。
- Tests：历史污染零次断言。
- Acceptance：只有 Reviewer 的 RELEASE_CANDIDATE_ACCEPTED 后才打 tag。
- Dependencies：T5.2–T5.4。
- Rollback：不适用（无破坏）。
- Risks：观察不足即 RC——由 Reviewer 把关。

---

## D. 测试策略

总体原则：测试即契约证据；live 网络非必需；失败测试不得删除/弱化/无理由跳过；每 skip 必须披露。

| 策略 | 目的 | 位置 | 代表用例 |
|---|---|---|---|
| D.1 Schema tests | 记录级校验的接受/精确拒绝 | `tests/unit/test_schemas.py` + fixtures | 每类记录合法通过、畸形报字段/行（SPEC §7-1） |
| D.2 Unit tests | 每个纯规则的确定性行为 | `tests/unit/` | cooldown 30/31、年份三态、去重、评分 tie；**历史 exclusion set 作为参数输入**（Core 不读取任何存储） |
| D.3 Property/统计 tests | 等权与约束满足的统计学证据 | `tests/property/`（hypothesis 或手写） | 等权无偏差（SPEC §7-2）、diversity 不饿死家族；非 flaky 阈值设计 |
| D.4 Integration tests | 模块协同（Orchestrator+Core+Adapter fakes） | `tests/integration/` | PLAN→…→DELIVER 全链路用 fakes 跑通 |
| D.5 Contract tests | Port/Adapter 边界与合规约束 | `tests/contract/` | **架构测试：Core 无 persistence import/call（无 SQLite/HistoryStore/文件读写导入或调用）**；Core 无 vendor 导入；adapter 错误分类；RYM 无对抗行为；社区真源非 SQLite |
| D.6 Failure-injection tests | 各类失败的受控注入 | `tests/integration/` + 注入工具 | fetch/generate/validate/deliver 各失败→历史不变（SPEC §7-9） |
| D.7 Crash-recovery tests | 每个持久转变点崩溃/重放 | `tests/integration/` | 崩溃重跑无半提交；delivered-but-not-committed 恢复（§7-10/11） |
| D.8 E2E tests | 干净环境真实（fixture）端到端 | `tests/e2e/` | 3×3 生成、重复率=0、cooldown 违规=0 |
| D.9 Security/license tests | 秘密与许可门禁 | CI 脚本 + `tests/security/` | 仓库工件 secrets 扫描；依赖/数据许可清单检查 |

辅助：确定性（seed 注入 + 记录）、日志脱敏（run id + transition，无 secrets）、错误分类映射表测试。

---

## E. P0/P1/P2 风险登记与缓解

完整登记表见 `governance/RISK_REGISTER.md`（本计划引用并受其约束）。摘要：

- **P0**：R-001 交付歧义污染/重复历史（缓解：journal + 幂等 + T2.6/T4.4）；R-002 凭据/cookie/profile 入 Git（缓解：ignore + secret 扫描 + 脱敏日志）；R-009 虚假原子性声明（缓解：补偿/幂等协议显式文档 + T4.4）。
- **P1**：R-003 Genre 等权被 popularity 替代（Core 契约 + property 测试）；R-004 canonical Album 错配（稳定 ID + 置信度降级 + fixtures）；R-005 RYM 布局/会话变化（薄 adapter + fixtures + 人工介入）；R-006 外部数据许可（provenance + license audit）；R-008 LLM 注入/越权（受控 fact packet + 输出校验）；**R-010 不可复现（seed + 输入版本入 journal）——P1，与 RISK_REGISTER 一致（G0-004 修复）**。
- **P2**：R-007 角色坍塌（exact-SHA + verdict 分离）；R-011 统计测试 flaky（非阈值化设计）；R-012 时区/每日边界（UTC ISO 8601 + 显式 daily window 配置）；R-013 社区贡献摩擦（版本化 Schema + 行级错误信息 + 贡献指南）。

每风险带 Owner（默认 Executor，重大项升级 Owner/Reviewer）与缓解验证点（Gate 验收矩阵条目）。

---

## F. v0.1 Explicit Non-goals（防 scope creep）

1. 不训练推荐模型、不建立社交推荐平台。
2. 不做 RYM 全站镜像、不做 Cloudflare/反爬对抗、不自动化验证码。
3. 不做大规模 Album Detail fan-out 作为默认架构。
4. 不让 LLM 主导 Genre/Album 选择。
5. 不做多用户云服务、复杂权限系统、分布式队列。
6. 不架设在大而全的音乐管理框架之上。
7. v0.1 不支持所有浏览器、所有推送渠道、所有 critic 来源——每个适配器只有 1 个参考实现。
8. 不引入 ORM/事件总线/全套 DDD 等重型抽象；Core 保持纯函数集合。
9. 不在 G5 接受前接入自动每日调度；先 dry-run 与手动运行。
10. 不宣称「外部推送与本地 SQLite 绝对原子」，只提供补偿/幂等协议。

超出本清单的任何新增能力必须走 ADR。

---

## G. 决策待确认项（G0-005 修复：三分类，避免治理过载）

原则：**规范已确定的事项（§A.3 十条不变量、四个默认常量、Gate 顺序、权威顺序、双模型分工）不在此列，一律不重新开放**。待确认项按决策机制分三类：

- **(a) Owner 产品决策**：涉及产品语义、数据范围或许可，必须由 Owner 定案；未定案前对应 Gate 不实现该部分。
- **(b) 架构/契约决策**：仅在**改变已接受契约**（公开 Schema、持久化结构、Port 契约、RYM 访问策略、历史提交时机）时才需要 ADR；不改变契约的选型在对应 Gate 由 Reviewer 正常评审。
- **(c) 可逆工程选择**：Executor 在对应 Gate 提出并实现，Reviewer 在该 Gate 评审中审查；**不自动要求 Owner 介入或 ADR**。

| ID | 待确认项 | 分类 | 决策机制 / 最近决策 Gate | 建议默认 |
|---|---|---|---|---|
| OD-1 | Python 版本基线 | (c) | G1 评审 | 3.12（pyproject 声明） |
| OD-2 | LLM provider 具体选型与模型标识 | (c) | G4 评审（涉及外部账户/成本时 Owner 知晓） | DeepSeek API，Provider 可替换 |
| OD-3 | PushPlus token 注入方式 | (c) | G4 评审 | 环境变量 + `.env.example` |
| OD-4 | canonical identity 默认来源 | (b) | G3 评审；若偏离 MP 建议（MusicBrainz）或改变身份契约则 ADR。许可风险见 R-006，外部网络/限流行为见 R-005 | MusicBrainz release-group |
| OD-5 | 「每日」运行窗口与触发方式 | (a)+(c) | 窗口语义 → Owner；触发机制（本地 cron/手动）属 (c) G5 后 | UTC 日界可配置；先手动/dry-run |
| OD-6 | v0.1 默认交付通道 | (a)+(c) | 真实推送默认目标 → Owner；dry-run 默认本地 Markdown 属 (c) G4 评审 | dry-run 本地文件；推送显式开启 |
| OD-7 | 初始 Genre 数据集范围 | (a) | Owner（数据范围与许可，R-006） | 以 Owner 既有 RYM 目录为种子，经 Schema 与许可审查后入库 |
| OD-8 | 项目与数据许可证 | (a) | Owner | 代码 OSI 许可 + 数据单独许可声明 |
| OD-9 | 统计「明显偏差」判据 | (c) | G2 评审（verdict 确认可按可评审实现选择） | 固定 seed 基准 + 非阈值化分布检验 |
| OD-10 | RYM 每 run 页面预算 | (b) | G3 评审；若突破 SPEC §3.4 最小化边界则 ADR | 每 run 有界预算，可配置 |

规则：任何 (b) 类项若在 Gate 执行中发现必须改变已接受契约，立即进入 BLOCKED_ARCHITECTURE 并提出 ADR，不在执行中擅自选择。(c) 类项默认由 Executor 提出、Reviewer 评审闭环，无需 Owner 审批，除非其实际后果超出普通可逆范围。

---

## H. SELF_CRITIQUE（先修订后交付）

| 检查点 | 发现 | 本稿修订 |
|---|---|---|
| 过度设计 | 初稿曾拟引入 Port 超集（7 个以上接口）+ 事件总线；Core 会因接口膨胀而难测 | 收敛到 6 个最小 Port；禁止事件总线/ORM；G2 全部为纯函数，无框架 |
| 无必要依赖 | 初稿考虑用 ORM 管理 SQLite、引入第三方注入框架 | 改为标准库 sqlite3 + 薄封装；依赖新增必须逐项在 Gate 报告披露（OPH §13） |
| 平台耦合 | WorkBuddy/Codex 是运行环境，不应进入代码契约 | 一切以 Git + CLI 为准；报告/状态文件与执行环境无关；CLI 为唯一入口直至 G5 后调度 |
| RYM 实时依赖 | 若默认测试依赖 live RYM，CI 与 Reviewer 都无法复现 | fixtures 优先；live RYM 明确非核心套件必需（T3.4 contract 测试固化） |
| 历史污染 | 失败 run 若写入任何官方记录，将永久扭曲 cooldown 与排除集 | 状态机把「官方写入」唯一挂在 DELIVERED 之后（T2.6）；失败注入矩阵逐项断言历史不变（SPEC §7-9） |
| 幂等窗口 | delivered-but-not-committed 若只靠「重新投递」会重复推送 | 独立 recovery 状态 + 持久收据查询 + 幂等键（T4.3/T4.4）；明确不宣称跨系统原子（SPEC §4） |
| 社区贡献难度 | Schema 无版本、错误信息模糊会劝退贡献者 | 版本化 Schema、行/字段级错误、贡献指南 + 演练（T3.5/T5.4）；模糊匹配歧义必须记录 |
| 用户操作复杂度 | 多步终端命令 + 自动推送会让 Owner 日常使用复杂 | 默认 dry-run、一键 CLI、dry-run 与手动运行先行（T4.5/T5.5）；人工介入路径文档化 |

自批判结论：本稿已在上述八点上完成修订；未发现需触发 BLOCKED_ARCHITECTURE 或 ADR 的高层冲突（详见报告 §5 规范理解矩阵——全部一致）。

> G0 独立评审修复记录（2026-08-19，详见 `reviews/stage-00/REPAIR_REPORT.md`）：
> - G0-001：Port protocols 与领域错误分类前置至 G1/T1.6；G2 全程 fake/in-memory 测试；G3 只实现具体外部 Adapter。
> - G0-002：Core 零 persistence（架构测试强制）；历史 exclusion set 作为参数输入；真实运行时数据受保护（不再出现「var/ 可重置」表述）。
> - G0-003：`.workbuddy/` 加入 `.gitignore`（不删除目录）。
> - G0-004：R-010 优先级修正为 P1（与 RISK_REGISTER 一致）；OD-4 引用修正为 R-006/R-005。
> - G0-005：Open Decisions 分为 Owner 产品决策 / 架构-ADR 决策 / 可逆工程选择 三类。

---

## 附：一致性声明

本计划与 HANDOFF_SPEC、MASTER_PLAN、OPERATIONS_HANDBOOK 逐条核对，无冲突、无重新开放已确定项、无超出 G0 允许范围的实现承诺。本稿待 GPT-5.6 Sol 评审；任何修订以评审意见为准。
