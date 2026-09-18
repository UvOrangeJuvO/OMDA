# ADR-0003 — Agent Skill Beta 与个人 Markdown 模式（修订版 v2：多来源一等公民模型）

- Status: **Accepted**（GPT-5.6 Sol 独立复审接受修订版 v2；实现必须遵守
  §10 Reviewer acceptance constraints。ADR 接受只授权进入 G6 实现，不等于
  G6 Gate 接受、合并、打包、push 或发布）
- Date: 2026-09-18（v1：2026-09-18；v2 同日）
- Gate: G6（Skill Distribution Beta）前置架构检查点
- v1 触发来源：Owner 产品决策（2026-09-18）——OMDA 暂不开发 Web Beta；第一轮
  朋友测试改为一个可分发给 Agent 使用的 OMDA Skill。
- v2 触发来源：①`reviews/adr/ADR_0003_REVIEW.md`（Reviewer commit `8aecaf7`，
  结论 REVISE）；②Owner 补充架构决定——Collection 重定义为一等公民的多来源
  文件系统。
- 修改范围：本轮仍**只修改 ADR、G6 计划、治理状态和交接报告**，不编写任何
  production code、脚本、测试、模板资产或分发包。

## 0. 修订记录（v2）

| 来源 | 本修订的解决方案 |
|---|---|
| Owner 多来源决定 | Collection 重命名为 **OMDA Source Markdown**（每位贡献者一份，`sources/`）；个人状态归 `profile/MY_PROFILE.md`；`--source` 可重复参数；来源元数据头（D22）；内存融合、来源只读（D21）；同 Album 跨来源去重不增概率、意见分别保留、Genre 冲突 fail-closed（D23）；同日锁定来源集合与结果（D24）；未来多来源评分组合能力预留且永不影响 Genre 基础机会（D25）；历史记录来源集合/digest/版本（D12 v2）；未来 Web/桌面复用同一多文件协议（D21）；分发包提供一个可复制的 Source 模板（D18 v2）；新增 9 项测试（§8 AC-17~AC-25） |
| ADR3-001 可分享数据与个人状态混放 | **两层文件模型**：来源文件不再承载 Heard/Skip 等接收者个人状态，只含可分享的候选事实与来源注记；个人 heard/skip 移入 `profile/MY_PROFILE.md` 的**结构化 Album-status 表**（键 = 同一规范化契约的 Artist+Album），脚本只为资格读取该表；自由文本偏好仅解释；档案中"不想被推荐"等自由字段旁明确标注"只有结构化状态表会真正排除条目"；合并/冲突规则与测试改为"同一来源可被多个不同 Profile 用户共享且零写入"（AC-17/AC-23） |
| ADR3-002 跨机确定性协议不完整 | 定义相互隔离的 **source-content canonical representation** 与 **selection canonical projection**（D19-3/§10 C1）；**selection-relevant 冲突 fail-closed**（尤其 Genre，D23）；历史携带版本与两类 digest；抽样采用版本化 uniform-index：domain-separated SHA-256 字节流 + 无偏 rejection/unranking，不依赖 `random.Random`；新增排列不变性测试（AC-19、AC-26） |
| ADR3-003 公开日期覆盖与双文件提交语义 | **提交路径移除 `--date`**：时钟经可导入的 clock seam 注入（仅测试）；day key 记录 timezone/offset 证据；**原子历史替换 = 官方 commit point**，输出从已提交历史渲染/重渲染；输出失败可恢复且无需新选择，历史失败绝不报成功；当日 payload 不含易变时间戳（复用提交时记录值）；崩溃测试覆盖历史提交前后与输出替换前后（D11 v2/D12 v2、AC-5/AC-15/AC-16/AC-27） |
| ADR3-004 Skill 目录/ZIP/许可不完整 | 仓库源路径 **`skills/omda-daily-discovery/`**、ZIP 根 `omda-daily-discovery/`；SKILL frontmatter name = `omda-daily-discovery` + 有区分度描述；新增 `agents/openai.yaml`（Codex 元数据，手动 CLI 兜底保持 vendor-neutral）；ZIP 含**完整 Apache-2.0 LICENSE** + LICENSES.md；Skill 版本独立于 OMDA 核心发布目标；打包前验证源结构、打包后**验证解压产物**（manifest 由验证产生，非手写）；测试/评审证据在分发包白名单之外（D16–D18 v2、AC-11/AC-28） |
| ADR3-005 模板含占位数据/首次即失败 | 示例行移到表格**外的 fenced 示例块**；真实表格为空；**全空行忽略、部分填充缺 Artist/Album fail-closed**；新增测试：纯净模板零候选、占位文本永不成为推荐；来源表格外加 curator/source/sharing-permission 字段（provenance 与私下分享语境，非自动公开许可）（计划 §C.3/C.4、AC-7/AC-29） |
| ADR3-006 前言结构与语气偏离 Owner | 恢复**完整前言结构**：OMDA 标题/全名 →"乐者，天地之和也"→ 三个编号小节 → 结尾"为什么我想做 OMDA"；卡尔维诺感悟以 Owner 第一人称**转述**（不直接引用、不做"大多数推荐系统"式普适断言）；纳入"信任的/陌生的/偶然遇到的/甚至不同意的"来源自由与审美多元论证（不上升为"音乐无高下"的普适宣言）；英文逐句对应；新增**双语逐句意图对照 checklist**（计划 §C.7/C.8、AC-30） |
| §5 角色定义（Reviewer 原则接受） | 固化**向后兼容**的 PROJECT_STATE 字段语义：`executor` = 角色标识 `workbuddy-executor`；`executor_model` = 每轮实际模型字符串；旧读取器把 executor 当普通字符串即兼容；AGENTS/OPH 文本修订在 ADR 接受后单独 commit 执行 |

## 1. 背景与已核实事实

1. v0.1 正式核心已按 G0–G5 交付并接受（approved commit
   `3aa76ea5bb35e219550cf65328549de47c98269b`）：每次运行 3 个 Genre、
   每个 Genre 3 张 Album、Genre 30-pick cooldown、成功推荐 Album 永久排除、
   Genre 等机会选择、确定性引擎选择（ADR-0002 D8：deterministic/no-LLM
   runtime）、curated 数据源生产门禁（ADR-0002 D1/D6）、SQLite 官方历史。
2. Owner 决定（v1）：暂不开发 Web Beta；第一轮朋友测试改为分发一个 OMDA
   Skill。用户流程：阅读使用说明 → 准备个人音乐档案 → 提供探索清单 → 交给
   支持 Skill 的 Agent → Agent 调用确定性脚本给出当天推荐。
3. Owner 补充决定（v2）：**OMDA 不维护汇总所有人内容的全局 Collection**。
   每位朋友、乐评人、社群或资料整理者拥有独立的 Source Markdown；用户每天
   选择一个或多个来源，系统在运行时构造**临时、只读的虚拟候选池**，不物理
   合并、不改写原始来源；个人状态（已听、跳过、个人记录）另行保存在用户
   自己的 profile，**绝不写回任何来源文件**。
4. Skill Beta 语义（一天一张、来自用户清单）与正式核心语义（一次 3×3、来自
   curated 数据包）不是同一产品语义；直接修改 Recommendation Core 迎合
   Skill Beta、或把简化模式冒充完整 3×3 引擎均违反既有契约。
5. 第一轮测试对象是朋友（非技术用户）；Web、音乐平台账号、Spotify/Apple
   Music API、在线服务器、Agent API 接入均不在本轮范围（Owner 明确排除）。
6. 仓库既有治理把 Executor 绑定为模型名 "DeepSeek V4 Flash"；该模型已不再
   可用。Reviewer 已原则接受"角色绑定 WorkBuddy Executor、模型单独记录"
   的方向（ADR_0003_REVIEW.md §Accepted direction-9），本 v2 固化字段语义。

## 2. 现有契约与冲突点

| 已接受契约 | 与 Skill Beta 的关系 |
|---|---|
| SPEC §2 产品常量（3/3/30/2010） | Skill Beta 是"一天一张"，不使用 3×3 常量；不得静默更改常量，也不得让 Skill 冒充 3×3 |
| SPEC §2.1 Genre 等机会、无 popularity 权重 | Skill Beta 继承"等机会、评分不加权"精神（D8/D9/D25） |
| SPEC §2.2 cooldown = 成功 pick 序号 ±30 | 该语义针对正式核心 Genre 池；Skill Beta 用自己的防重复规则（D8），正式核心一字不改 |
| SPEC §2.4 成功推荐 Album 永久排除、稳定 identity | Skill Beta 有自己的永久排除历史（本地 JSON），与正式核心 SQLite 历史相互独立（D10） |
| SPEC §3.5 LLM 不决定 Genre/Album 集合 | Agent 只整理资料与解释结果，不得替换确定性脚本的选择（D14） |
| SPEC §3.3 文本为真源、SQLite 仅 runtime | Skill Beta 全部用户输入与历史均为本地文本/JSON，不引入 SQLite，不写入本仓库 tracked 数据 |
| AGENTS.md 角色分离 | 职责不变；字段语义见 §5（v2 固化） |

## 3. 方案比较

### 方案 A：Skill Beta 作为完整 3×3 Core 的包装器

- 否决（沿 v1）：语义不符（一天一张 vs 3×3）；用户清单永远无法满足
  `CandidateBatch`/`GenreSourceDescriptor` 生产门禁（ADR-0002 D6）；私人
  档案流入为开源社区设计的贡献路径；改动面最大。

### 方案 B：独立、清楚标记的 Skill Beta companion mode —— **推荐**

- 自包含 Skill 分发包：确定性脚本 + 模板 + 说明，零第三方运行时依赖；
  不修改、不导入、不复用 Recommendation Core 与 SQLite 官方历史。
- v2 增强：数据模型升级为**多来源一等公民文件系统**（D21–D25），个人状态
  与可分享来源严格分离（ADR3-001），确定性协议完整版本化（ADR3-002）。
- 结论：**采用**。

### 方案 C：维持现状，不做 Skill，等 Web Beta

- 与 Owner 决策直接冲突。否决。

## 4. 决策

### D1 — Skill Beta 的定位：独立 companion mode

**决策：Skill Beta 是一个独立、清楚标记的 companion mode
（"OMDA Skill Beta — Personal Markdown Mode"），不是完整 OMDA 3×3 Core 的
包装器，也不是 3×3 引擎的简化配置。**

- 不修改 Recommendation Core、`src/omda/`、SQLite 官方历史或既有测试；
- 不共享 3×3 的常量、数据包、生产门禁与历史文件；
- 其输出必须带固定标记（D4），不得自称或被描述为"OMDA 3×3 推荐"。

### D2 — 为什么第一版选择 Skill 而不是 Web

- **分发成本**：Skill 是一组文件（Markdown + 一个脚本），ZIP 直接发给朋友；
  Web 需要部署、域名、账号系统和在线服务器维护。
- **隐私边界**：Skill 天然本地运行（D15）；Web 第一天就要回答"数据放哪里"。
- **零运行成本**：无服务器、无 API key、无平台账号。
- **借用用户已有的 Agent**：朋友已经在用支持 Skill 的 Agent；Skill 把 OMDA
  放进他们已有的日常入口。
- **可演进**：v2 的多文件协议（profile + sources）就是未来 Web/桌面端的
  数据协议（D21-6），不锁死路线。

### D3 — 第一版采用"一天一张专辑"

**决策：采用。** 每次调用最多产出 1 张 Album 推荐；推荐来源仅为用户当日
选择的 Source Markdown 集合 + 其个人 profile 状态；一天内重复调用返回同一
结果（D11）。

### D4 — 如何明确说明它不等同于正式 3×3 引擎

1. **命名**：Skill 名称与所有文档统一使用
   `OMDA Skill Beta (Personal Markdown Mode)`；
   任何输出不得出现"OMDA 3×3 推荐"字样。
2. **固定免责声明**：每日输出第一段固定为（双语或按用户语言）：

   > 本推荐来自 OMDA Skill Beta（个人 Markdown 模式）：一天一张、来自你自己
   > 选择的来源清单。它不是 OMDA 完整的 3 Genre × 3 Album 引擎，两者规则与
   > 历史互不通用。
   >
   > This recommendation comes from OMDA Skill Beta (Personal Markdown Mode):
   > one album per day, from source lists you selected. It is NOT the full
   > OMDA 3 Genre × 3 Album engine; the two share neither rules nor history.

3. **文档对照说明**：使用说明含对照表（3×3 引擎 vs Skill Beta：输出数量、
   数据来源、历史存储、cooldown 规则）。
4. **禁止混用**：Skill 脚本不得读写正式核心的 `var/omda.sqlite3`；
   正式核心不得读取 Skill 的历史文件。

### D5 — 两层数据模型（v2：多来源一等公民）

**决策：数据模型分为"可分享来源"与"个人状态"两层，物理目录分离：**

```text
<用户工作目录>/
├── profile/
│   └── MY_PROFILE.md            # 当前用户私人档案 + 结构化已听/跳过状态表
├── sources/                     # 每位贡献者一份 OMDA Source Markdown
│   ├── alice.md
│   ├── critic-zhang.md
│   ├── music-club.md
│   └── my-old-reviews.md
└── var/                         # 私人历史与输出（Git 忽略；永不分享）
    └── omda-skill/
```

| 层 | 文件 | 内容 | 可分享性 |
|---|---|---|---|
| 来源层 | `sources/*.md` | 每位贡献者的候选专辑清单 + 来源元数据（D22）；**不含任何接收者的个人状态** | 可在用户间原样传递；**运行时只读，永不改写** |
| 个人层 | `profile/MY_PROFILE.md` | 用户自由文本档案（仅解释用）+ **结构化 Album-status 表**（个人 heard/skip，唯一资格排除依据之一） | 私人；永不写回任何来源文件 |
| 运行层 | `var/` | 历史 JSON、每日输出 | 私人；历史是唯一需要备份的状态 |

- **OMDA_COLLECTION.md 概念废止**：v1 的单一汇总 Collection 不再存在；
  原职责由多个 OMDA Source Markdown 承担。文档与模板统一改名
  （模板：`OMDA_SOURCE.template.*.md`）。
- **个人状态永不写回来源**：脚本对 `sources/` 只读；heard/skip 只存在于
  profile 结构化状态表与 `var/` 历史。
- **profile 双区结构**：
  1. 自由文本区（口味、年代、偏好、目标）：**仅用于 Agent 解释推荐**，
     脚本完全不读取；
  2. 结构化 Album-status 表：唯一被脚本读取的 profile 内容，字段
     `Artist | Album | Status(heard/skip) | Note`，键 = 与来源相同的规范化
     身份契约（D10）。自由文本区"不想被推荐"等字段旁必须标注：
     *"只有下面的结构化状态表会真正把专辑排除出选择；这段文字只帮 AI 向
     你解释。"*（英文对应句由模板固定）——消除 ADR3-001 指出的误导。

### D6 — 字段必填与可选（v2）

**来源文件（OMDA Source Markdown）** 由两部分组成：

1. **元数据头**（受限 OMDA flat frontmatter，机器可读，见 D22）；
2. **Album 表**（Markdown 表格），表头支持英/中/双语别名
   （`Artist 艺人`、`Album 专辑`、`Year 年份`、`Genre 流派`、`Rating 评分`、
   `Note 备注`）。别名映射表由 G6 实现写入脚本并测试锁定。

| 字段 | 必填 | 说明 |
|---|---|---|
| Artist | **必填** | 艺人名 |
| Album | **必填** | 专辑名 |
| Year | 可选 | 留空不得编造 |
| Genre | 可选 | 自由文本；为空归入"未分类（uncategorized）"分组；含分隔符时取第一个值作为分组键，展示保留原文 |
| Rating | 可选 | 来源自己的评分；**当前 Beta 仅展示**（D9）；配合 D22 的可选 rating_scale |
| Note | 可选 | 来源自己的备注；**仅展示**（D9） |

- **无评分来源完全有效**：Rating 缺失不影响资格、机会或顺序（D7）。
- 行校验：**全空行忽略**；**部分填充但缺 Artist/Album 的行 → fail-closed**
  并定位行号，不猜测、不编造、不静默跳过。
- **Profile 结构化状态表**：`Artist | Album | Status | Note`；
  Status 接受 `heard/skip`（含中文别名"已听/跳过"）；Artist/Album 必填，
  同样全空行忽略、部分填充 fail-closed。

### D7 — 没有评分的清单完全有效

**决策：完全有效。** 评分是来源文件的可选字段；评分缺失不影响任何条目的
资格、机会或顺序；选择算法不读取评分（D9）。多来源场景下，"全部来源均无
评分"与"部分/全部有评分"在选择层面完全等价。

### D8 — Genre 先等机会选择，再在 Genre 内选择 Album（v2 措辞收紧）

**决策：选择分两步，均为确定性：**

1. **Genre 等机会**：把**当前 admissible**（有合格候选、未被防重复规则
   排除）的分组做等机会（均匀）抽样。**分组内条目数量、来源数量、评分
   均不影响分组的基础被选概率。**
2. **Genre 内选专辑**：在选中分组内，对合格条目做等机会（均匀）确定性
   抽样，选出当天唯一一张。

**cooldown 处理（companion 专属，正式核心不改）：**

- 防重复规则：同一 Genre 分组不得在连续两个成功 pick 中重复出现，除非它是
  唯一 admissible 分组（此时照常选择并显式标注"唯一可用流派"）。
- **等机会仅定义在"当前 admissible 分组"之上**；分组耗尽后不宣称无条件或
  长期均等（按 Reviewer 接受方向 #4 措辞）。长期多样性由"等机会抽样 +
  永久排除消耗 + 清单耗尽终点"保证。

### D9 — 评分和备注只能展示，不得影响选择

**决策：是。** 各来源的 Rating、Note、profile 自由文本区：

- 不参与 Genre 分组的资格与机会；
- 不参与 Genre 内专辑的选择与排序；
- 不作为权重、过滤器或 tie-breaker；
- 仅出现在当日输出的展示区，且**按来源分别标注归属**（哪个来源给的评分/
  备注，见 D23-3）。

契约测试锁定：修改 rating/note/profile 自由文本 → 同输入同历史下选择不变。

### D10 — 已听、跳过与历史推荐的排除（v2）

**决策：三类排除，全部确定性：**

1. **个人已听/跳过**：仅来自 `profile/MY_PROFILE.md` 的**结构化状态表**
   （heard/skip）。用户编辑自己的 profile 即改变资格；**来源文件永不承载
   该状态**（ADR3-001）。
2. **历史推荐（永久排除）**：凡被 Skill Beta 成功推荐（当日结果已原子提交
   入本地历史，D12）的条目，按规范化身份键永久排除。
3. **规范化身份键**：`normalize(artist) + "|" + normalize(album)`；
   normalize = NFC → 小写 → 折叠空白 → 去首尾标点，纯函数实现并测试锁定。
   同键不同原文的歧义记录不静默（D23）。
- **与正式核心历史互不导入**（沿 v1）。
- 来源文件中的 Album 在"当前用户"视角下是否听过，**只由用户自己的 profile
  状态表决定**——同一来源文件在不同用户处产生不同的 admissible 集合，
  这是设计意图而非缺陷（AC-23 锁定"来源零写入"）。

### D11 — 同一天重复调用返回同一结果（v2：来源集合锁定 + 提交点）

**决策：**

- **day key = 本地日历日期**（`YYYY-MM-DD`）；历史记录同时保存
  **day key 的 timezone/offset 证据**（如 `UTC+08:00` 及生成时的 UTC
  时间戳）。
- **官方 commit point = 原子历史替换**（同目录临时文件 + `os.replace()`）。
  历史替换成功即视为当日推荐正式提交；输出文件随后**从已提交历史渲染**。
  - 输出文件写入失败/丢失：从已提交历史**确定性重渲染**，不需要也不允许
    新的选择；
  - 历史替换失败：**绝不报告为成功推荐**，历史保持不变，用户重试。
- **同日重复调用**：历史中已有该 day key → 直接返回已提交结果（重渲染），
  **不重新抽样**。
- **同日来源集合锁定（Owner 决定 11）**：第一次正式推荐成功后，本次使用的
  `source_id` 集合与结果一并锁定；同日随后更换 `--source` 参数**不得产生
  第二张当日推荐**——只返回已提交结果，并**说明当日使用的原来源集合**
  （来源 display name 列表）。
- 用户当天修改来源/profile：变更从下一个 day key 生效（输出中提示）。
- **无公开日期覆盖（ADR3-003）**：提交路径**不提供 `--date`** 或任何诊断性
  日期参数；时钟通过可导入的 clock seam 函数注入，仅测试使用。day key 只
  能前进到"今天"。
- **当日 payload 不含易变时间戳**：渲染使用提交时记录的固定时间戳，
  保证 AC-5 的字节级一致可测。
- **确定性跨机可复现**：选择材料只派生自
  `SHA-256(domain-separated: day_key, algorithm_version,
  admissible_selection_pool_digest)`。选择投影仅包含经 profile 状态、永久
  历史与 cooldown 过滤后的规范化 Album identity 与已解决 Genre 分组键。
  Rating、Note、Year、display name、provenance、sharing note、profile 自由
  文本与完整来源内容 digest 均不得进入 seed；它们变化时不得改变选择。

### D12 — 历史文件：位置、格式、原子写入、损坏处理（v2：来源证据）

- **位置**：默认 `var/omda-skill/history.json`，可用 `--history` 覆盖；
  `var/` 永不入 Git、永不分享。
- **格式**：版本化 JSON `{"schema_version": 2, "days": {...}}`；每条成功
  记录必须保存（Owner 决定 10 + ADR3-002）：
  - day key + timezone/offset 证据；
  - 选中条目完整事实（artist、album、year、genre 分组键、**来源出处**）；
  - **被选择的 `source_id` 集合**；
  - **每个所选来源的 content digest**（覆盖来源元数据、候选事实与展示注记，
    只作审计证据，不进入选择 seed）；
  - **admissible selection-pool digest**（只对规范化 identity + 已解决 Genre
    的选择投影计算，作为选择 seed 证据，D19-3/D23-5）；
  - **`algorithm_version` 与 schema version**；
  - 提交时间戳（UTC ISO 8601，带 offset；渲染复用此值）。
- **原子写入**：临时文件 + `os.replace()`；**这是官方 commit point**（D11）。
- **损坏处理 fail-closed**：解析失败/版本未知/结构校验失败 → 保留损坏副本
  （`history.corrupt-<timestamp>.json`）、拒绝运行、给出人工恢复指引；
  **绝不静默重置、绝不自动重建、绝不丢弃历史继续运行**。
- schema 演进只能向前加版本，不删字段（v1 草案未发布，直接以 v2 命名）。

### D13 — 清单耗尽时的明确行为

**决策：显式报告，绝不回退。** 当不存在任何合格条目（全部已被个人
heard/skip 或永久排除）时：输出明确耗尽信息（双语固定文案），脚本非零
退出；Agent 只转述，不得自行补一张、不得降低排除标准。部分耗尽（某分组无
合格候选）不触发整次失败：该分组仅从当日 admissible 池排除。

### D14 — AI 在本流程中的权限

**允许：**

1. 按模板把自由格式资料整理成 **OMDA Source Markdown**（含元数据头）或
   profile；**不知道的字段必须留空，不得编造**（整理 Prompt 由 G6 交付并
   包含此硬规则）；
2. 阅读脚本输出的确定性事实，结合 profile 自由文本区解释/介绍当天推荐；
3. 协助安装、排障、格式修改。

**禁止：**

1. 替换、覆盖、重排或"优化"确定性脚本选出的 Album——**确定性脚本选择，
   AI 只解释**；
2. 绕过脚本直接从候选中"挑一张"充当推荐；
3. 编造字段值；
4. 把评分/备注/自由文本偏好变成选择依据（D9）；
5. 修改脚本的选择逻辑、历史文件或排除集；
6. **改写任何来源文件**（D21-3）；把个人状态写回来源文件；
7. 未经用户明确操作上传、公开或提交任何用户数据（D15）。

脚本侧保证：无"指定结果"参数；来源路径以只读方式打开。

### D15 — 本地隐私边界与公开贡献边界

- **默认全本地**：profile、sources、历史、输出只保存在用户本机；脚本零
  网络调用（D19 v2：import 白名单）；分发包不含任何用户数据。
- **本地使用 ≠ 同意公开贡献**：任何上传、公开分享、提交到 OMDA 开源仓库
  都是独立的、显式的用户动作；说明文档明确写双语提示。
- **sharing note ≠ 公开许可（ADR3-005-4）**：来源元数据头的
  sharing/license note 记录的是"curator 愿意让这份清单被怎样私下分享"
  的语境；它**不是**自动赋予的公开再分发许可；公开使用仍需按 note 与
  curator 确认。
- **harness 提示**：Agent 平台自身遥测超出 OMDA 控制；说明文档提醒用户
  注意其平台隐私政策并最小化档案内容。

### D16 — Skill 的可移植范围（v2：标准 Skill 目录）

**目标 harness：Codex、WorkBuddy，以及任何满足最小能力的 Agent harness：**
（1）能读取并遵循 SKILL.md；（2）能读写工作目录文件；（3）能运行
`python3 scripts/daily_pick.py ...`（Python ≥ 3.9）。

- 仓库源路径：**`skills/omda-daily-discovery/`**（ADR3-004-1）；
  分发 ZIP 以 `omda-daily-discovery/` 为根目录，保持同一结构。
- SKILL.md frontmatter：`name: omda-daily-discovery`（稳定、有效的 skill
  名）+ 有区分度的 description；新增 `agents/openai.yaml` 提供一致的
  Codex 展示元数据/默认提示；手动 CLI 兜底保持 vendor-neutral。
- 脚本是独立 CLI，不依赖任何 harness skill 机制。

### D17 — 非 native Skill Agent 的兼容使用方法

**决策：脚本必须可用 CLI，说明必须包含"无 Skill 机制"路径**（沿 v1）：

1. 解压分发 ZIP 到任意目录；
2. 把 SKILL.md 内容粘贴给 Agent 作为普通指令（或自己阅读）；
3. 手动运行（多来源示例，见 D21-4）：

   ```bash
   python3 scripts/daily_pick.py \
     --profile profile/MY_PROFILE.md \
     --source sources/alice.md \
     --source sources/critic-zhang.md \
     --history var/omda-skill/history.json \
     --output-dir var/omda-skill/output
   ```

4. Agent 读取输出 Markdown 并解释。

README 含逐条手动步骤（Windows/macOS/Linux 差异）。

### D18 — 分发包应包含的文件（v2）

```text
omda-daily-discovery/                # ZIP 根 = 仓库 skills/omda-daily-discovery/
├── SKILL.md                         # frontmatter name: omda-daily-discovery（双语正文）
├── agents/
│   └── openai.yaml                  # Codex 展示元数据/默认提示（ADR3-004-2）
├── README.md                        # 朋友使用说明（双语；含多来源用法与 D17 手动路径）
├── VERSION                          # Skill 版本（0.1.0-beta.1；独立于 OMDA 核心 0.1.0）
├── LICENSE                          # 完整 Apache-2.0 文本（ADR3-004-3）
├── LICENSES.md                      # 第三方/数据声明
├── scripts/
│   └── daily_pick.py                # 唯一确定性脚本（标准库零依赖）
├── templates/
│   ├── OMDA_SOURCE.template.zh-CN.md    # Source 模板（用户可复制任意份，D21-7）
│   ├── OMDA_SOURCE.template.en.md
│   ├── OMDA_PROFILE.template.zh-CN.md   # 含结构化 Album-status 表
│   └── OMDA_PROFILE.template.en.md
├── prompts/
│   ├── ORGANIZE_PROMPT.zh-CN.md     # AI 整理资料 → Source Markdown（D14）
│   └── ORGANIZE_PROMPT.en.md
└── FEEDBACK_TEMPLATE.md             # 反馈模板（双语）
```

**明确排除**：任何用户数据、`var/`、历史 JSON、SQLite、`.git`、
`tests/`、评审证据、`src/omda/`、环境目录。ZIP 内容由**打包后对解压产物
的自动验证**确认（manifest 由验证产生，非手写清单；AC-11/AC-28）。

### D19 — 零依赖、零网络与确定性协议（v2）

1. **标准库零运行时依赖**：只使用 Python 标准库；不安装第三方包；
   目标 Python ≥ 3.9（避免 3.10+ 专属语法）。
2. **零网络（收窄为 import 白名单，ADR3-006 要求 9）**：脚本 import 集合
   必须属于显式白名单（`argparse/json/hashlib/pathlib/datetime/tempfile/os/
   re/unicodedata/sys` 等）；**拒绝一切其他 import，包括 `socket`、
   `urllib`、`http`、`subprocess`、`webbrowser` 等网络/进程/浏览器逃逸
   模块**；静态审计 + 断网运行双重锁定。
3. **确定性协议（ADR3-002）**：
   - **source-content canonical representation**：覆盖来源元数据、候选事实、
     rating/note/attribution 等完整可审计内容；Unicode NFC、UTF-8、稳定字段
     键序与记录序。由此计算 per-source content digest，**仅作审计证据**。
   - **selection canonical projection**：完成多来源去重与 Genre 冲突解决后，
     每条记录只保留规范化 identity 与 Genre 分组键；再应用 profile 状态、
     永久历史与 cooldown 得到 admissible selection pool。只对该投影计算
     selection-pool digest，且**只有它可进入选择 seed**。Year、rating、note、
     来源展示元数据、profile 自由文本及 content digest 一律隔离在选择之外。
   - 两种表示均不得包含绝对路径或 CLI 参数顺序；稳定排序消除文件内行序与
     `--source` 顺序的影响。
   - **uniform-index 抽样**：版本化协议——从 domain-separated SHA-256
     字节流派生无偏均匀索引（unbiased rejection sampling / unranking），
     材料含 `algorithm_version`；**不得以 `random.Random` 的实现或调用序列
     作为可移植协议**。
   - **排列不变性**：来源文件内行序、`--source` 参数顺序**不影响选择**
     （canonical 记录序消除顺序依赖）；展示性注记的展示顺序按明确文档化
     的 canonical 顺序（source_id 字典序 + 文件内出现序）排列。
   - 每条历史记录携带 `algorithm_version`；协议变更必须递增版本并写入
     ADR/治理记录。

### D20 — 明确推迟到后续版本

沿 v1 清单（Web Beta、平台 API、服务器、Agent API、自动调度、多语言扩展、
跨模式历史导入、MBID 身份、脚本内调外部 LLM 等），另加：

11. **多来源评分组合（加权）算法本身**——本版只预留格式与边界（D25），
    不实现任何组合；
12. 来源级发现/订阅机制（自动拉取他人的 sources）。

### D21 — 多来源一等公民文件系统（v2 新增，Owner 核心决定）

1. **无全局汇总 Collection**：OMDA 不维护、不生成、不要求任何"汇总所有人
   内容"的全局 Markdown。每位贡献者（朋友/乐评人/社群/资料整理者）拥有
   独立的 OMDA Source Markdown。
2. **推荐目录结构**（D5）：`profile/`（当前用户私人档案与状态）、
   `sources/`（多个可选择、可分享的来源文件）、`var/`（私人历史与输出）。
3. **运行时融合只在内存**：用户每次运行通过可重复参数选择来源子集；脚本
   把被选来源构造成**临时、只读的虚拟候选池**——不物理合并成新的总
   Markdown，**不改写任何原始来源文件**（来源文件以只读语义打开；测试
   锁定运行前后字节不变，AC-23）。
4. **CLI 可重复参数**：`--source sources/alice.md --source
   sources/critic-zhang.md`（每出现一次添加一个来源）；至少一个
   `--source` 必须提供；同一文件重复传入 → fail-closed 报错；两个来源
   `source_id` 相同 → fail-closed 报错。
5. **来源可选、可分享**：来源文件可以在朋友之间原样传递；接收者不需要
   （也不得）为使用它而修改它。
6. **未来前端复用同一协议**：将来 Web/桌面端通过"来源复选框"调用**同一个
   多文件协议**（同一来源文件格式、同一元数据、同一合并/冲突规则），不再
   设计另一套数据模型。
7. **分发包提供一个 Source 模板**；用户复制该模板即可创建任意数量的来源
   文件（每份需自行填写元数据头，`source_id` 不得重复）。

### D22 — 来源文件元数据（v2 新增）

每个 OMDA Source Markdown 必须携带机器可读的 **OMDA flat frontmatter**：
位于首尾 `---` 之间，每行只能是一个标量 `key: value`。它不是通用 YAML；
禁止嵌套、序列、tag、anchor、alias、重复字段与未知字段，并由标准库受限解析器
读取，不引入第三方 YAML 依赖。

| 字段 | 必填 | 说明 |
|---|---|---|
| `source_id` | **必填** | 稳定且唯一（同一用户机器上）；建议 slug（如 `alice`、`critic-zhang`）；进入历史记录与输出归属 |
| `display_name` | **必填** | 展示名（如"Alice 的私藏清单"） |
| `curator` | **必填** | 整理者/作者 |
| `provenance` | **必填** | 来源说明（如"朋友手写推荐""乐评人专栏 2026-06"） |
| `sharing_note` | **必填** | 分享/许可语境说明（私下分享语境，非自动公开许可，D15） |
| `rating_scale` | 可选 | 该来源评分的量表描述（如 `10-point`、"星级 1-5"、`文字短评`）；无评分可省略 |
| `format_version` | **必填** | 来源格式/Schema 版本（从 1 起） |

- 缺失必填元数据 / `format_version` 未知 / 同次运行 `source_id` 冲突 →
  fail-closed，定位到文件。
- 元数据头与 Album 表进入 source-content canonical representation（D19-3）；
  `source_id` 是展示归属与 per-source content digest 的键。只有 identity 与
  已解决 Genre 的 selection projection 可进入选择 digest。

### D23 — 多来源融合、去重与冲突（v2 新增，Owner 决定 7）

1. **去重不增概率**：同一规范化身份键的 Album 在多个来源出现时，合并为
   **一个候选**；出现次数/来源数**不得增加**其被选概率（候选池按身份键
   去重后再抽样；测试锁定）。
2. **意见分别保留**：每个来源的 rating、note、attribution（来源
   display_name/source_id）**分别保留**，在输出展示区按来源并列呈现；
   **不得破坏性平均、加权或相互覆盖**。
3. **selection-relevant 冲突 fail-closed（ADR3-002-2）**：同一身份键的不同
   来源对 **selection-relevant 事实**（当前 = Genre 分组键；未来若扩充
   selection-relevant 字段需修订本 ADR）给出不一致值时，**运行 fail-closed**：
   报告冲突的身份键、涉及的来源与各自的值，要求用户确认/修正来源文件；
   **绝不按文件顺序或参数顺序任选一个**。展示性字段（rating/note）不一致
   不失败——按 D19-4 的 canonical 顺序并列展示。
4. **同键不同原文的规范化歧义**：规范化身份键相同但原文不同的记录（如
   大小写/标点差异）不静默合并展示文本；以首个 canonical 顺序来源的原文为
   展示文本，其余作为注记保留。
5. **双表示与稳定记录序**：
   - source-content 表示保存完整元数据、候选事实、rating/note/attribution，
     生成只作审计的 per-source content digest；
   - selection projection 只保存规范化 identity 与已解决 Genre；应用个人
     状态、历史和 cooldown 后形成 admissible pool，只有其 digest 进入 seed；
   - 两者均按稳定键排序。参数顺序、文件内行序，以及只改展示字段的变更，
     不得影响 selection-pool digest 与选择（AC-14/AC-19/AC-26）。
6. **当前 Beta：多来源评分与备注只用于展示**，不参与 Genre 机会或 Album
   抽样（与 D9 一致，显式重申）。

### D24 — 同日来源集合锁定（v2 新增，Owner 决定 11）

见 D11-4。要点：第一次正式推荐（原子历史提交）成功后，当日结果与
`source_id` 集合锁定；随后任何 `--source` 组合变更只返回已提交结果并说明
原来源集合；不产生第二次抽样、不修改历史。

### D25 — 未来多来源评分组合能力预留（v2 新增，Owner 决定 9）

1. **格式预留**：来源文件已按来源携带 `rating` + `rating_scale` +
   attribution；历史记录已按来源保存 per-source content digest 与注记——未来任何
   组合算法可以追溯证据。
2. **边界固化（即使未来引入权重）**：多来源评分组合**只能影响 Genre 内
   Album 的排列/排序**，**永远不得影响 Genre 的基础选择机会**（不得改变
   admissible 分组池、不得给分组加权、不得复活任何 popularity filter）。
   该边界是本 ADR 的永久约束；突破需新 ADR + Reviewer 接受。
3. 本版不实现任何组合算法（D20-11）。

## 5. 角色定义字段语义（v2：固化向后兼容语义）

Reviewer 已原则接受该方向（ADR_0003_REVIEW.md §Accepted direction-9）。
本 ADR v2 固化**向后兼容**的 PROJECT_STATE 字段语义；AGENTS/OPH 文本修订
在 ADR 正式接受后以单独 commit 执行：

1. `executor` 字段语义 = **角色标识**，固定取值 `workbuddy-executor`；
   不再承载模型名。旧读取器把它当普通字符串即可，无 schema 破坏。
2. 新增 `executor_model` 字段 = 该轮**实际使用的模型**字符串（本轮：
   `glm-5.3-flash (WorkBuddy)`）。字段可空（未知时如实填 `unknown`）。
3. `reviewer` 字段不变：`gpt-5.6-sol`。
4. **更换 Executor 模型不改变架构权限与 Gate 规则**：Executor 只能写到
   `READY_FOR_REVIEW`；只有 Reviewer 可以置 `ACCEPTED`；权威顺序、反自
   引用规则、完成证据要求全部不变。
5. 接受后的落地文本修订（届时执行，不在本轮）：`AGENTS.md` §Role
   separation、OPH §4.1/§0 的模型名表述、README §开发治理。

## 6. 影响分析

- **正式核心**：零改动。`src/`、`tests/`、`data/`、`var/` 均不触碰。
- **新增物（G6 实现阶段，待本 ADR 接受后）**：`skills/omda-daily-discovery/`
  目录（D18）、G6 计划模板定稿、G6 测试矩阵。Skill 源文件不放 `src/omda/`。
- **治理**：PROJECT_STATE 转为 G6 / READY / ADR_ACCEPTED；G6 计划获准执行，
  但 Gate 尚未接受。
- **风险与缓解**：

| 风险 | 缓解 |
|---|---|
| 用户误以为拿到的是完整 3×3 引擎 | D4 免责声明 + 对照表 + 命名区分 |
| AI 越权替换选择 / 改写来源 | D14 禁令 + 脚本无指定结果参数 + 来源只读（AC-23） |
| 个人状态混入可分享来源 | D5/D10 两层模型 + profile 结构化状态表（ADR3-001） |
| 评分/自由文本变成隐蔽 filter | D5/D9/D23-6 脚本不读取 + 契约测试（AC-14） |
| 跨来源重复条目获得概率优势 | D23-1 去重 + 测试（AC-20） |
| Genre 冲突被静默任选 | D23-3 fail-closed（AC-22） |
| 历史损坏破坏永久排除承诺 | D12 原子写 + fail-closed + 损坏副本（AC-7/AC-16/AC-27） |
| 隐私外泄 | D15 本地默认 + 分发包扫描 + 用户数据不入 ZIP/Git |
| 跨机/跨版本不可复现 | D19-3 canonical 表示 + 版本化 uniform-index + permutation 测试（AC-19/AC-26） |
| 小清单被 cooldown 饿死 | D8 companion 防重复规则（显式偏离并标记） |
| 模板占位文本成为推荐 | 计划 §C.3/C.4 示例外置 + 空行忽略 + AC-29 |

## 7. rollout / rollback

- **rollout**：① 本 ADR v2 与 G6 计划复审获接受 → ② G6 实现（skill 目录 +
  脚本 + 模板 + 说明 + 测试矩阵全绿）→ ③ G6 Reviewer checkpoint 接受 →
  ④ Owner 授权后打包分发。ADR 接受不授权 merge/tag/分发。
- **rollback**：`git revert` G6 相关 commit 整体移除 Skill 产物；不触碰
  正式核心与既有历史；用户本地 `var/`、`profile/`、`sources/` 属用户文件，
  清理由用户显式执行。
- **停止条件**：复审返回 REVISE / OWNER_DECISION_REQUIRED 时，Executor 仅
  修订文档并再次送审，不开始实现。

## 8. 验收测试设计（G6 实现，本 ADR 只定义）

| # | 验收 | 设计 |
|---|---|---|
| AC-1 | 安装验证 | 干净目录解压 ZIP + 干净 Python ≥ 3.9 环境，按 README 手动路径（多来源）完成首次推荐 |
| AC-2 | 连续两天推荐 | day1/day2（clock seam 注入第二天）各产出一张、互不相同；day2 不依赖 day1 输出文件存在 |
| AC-3 | 同日幂等 | 同 day key 重复 ≥3 次：结果字节级一致、历史不变、无第二次抽样 |
| AC-4 | 个人状态排除 | profile 状态表 heard/skip 条目不被选；状态变更只改资格（ADR3-001） |
| AC-5 | 同日来源集合锁定 | 首次成功提交后更换 `--source` → 返回已提交结果 + 原来源集合说明；零重抽、零历史变更（AC-3 扩展） |
| AC-6 | 中英表头/元数据 | 三种表头与元数据头解析等价；未知表头/缺元数据/format_version 未知 fail-closed 报定位 |
| AC-7 | 缺字段/损坏历史/模板 | 部分填充行定位报错、全空行忽略；损坏历史保留副本 + 拒绝运行 + 零自动重建 |
| AC-8 | 零网络（import 白名单） | 白名单审计（禁 socket/urllib/http/subprocess/webbrowser 等）+ 断网功能测试 |
| AC-9 | Secret/隐私扫描 | 分发包与输出无 token/key/个人数据/本机路径泄漏 |
| AC-10 | Skill 结构 | SKILL frontmatter（name=omda-daily-discovery）、agents/openai.yaml、目录结构、双语模板齐备 |
| AC-11 | ZIP 内容 | 白名单 + **解压产物自动验证**；排除项（tests/证据/用户数据/var//.git/src/omda）逐一断言不存在 |
| AC-12 | Codex 安装说明 | 按 SKILL.md/openai.yaml 在 Codex 中可发现并执行（Owner/朋友实测，不可实测时显式披露） |
| AC-13 | 非 native 兼容 | D17 手动路径（多来源）逐条可执行 |
| AC-14 | 展示/审计字段不影响选择 | 修改 rating/note/year/display 元数据/profile 自由文本 → content digest 可变，但 selection-pool digest 与选择不变；**结构化状态表变更只改资格** |
| AC-15 | 耗尽行为 | 全排除 → 显式信息 + 非零退出 + 零回退 |
| AC-16 | 原子写入与崩溃（扩展） | 历史提交前/后、输出替换前/后四类崩溃点：状态保持已选择结果、**永不产生两张当日推荐**；历史失败不报成功 |
| AC-17 | 单来源 | 单一 `--source` 全流程可用 |
| AC-18 | 多来源 | 多 `--source` 合并池推荐可用；输出按来源标注归属 |
| AC-19 | 来源顺序确定性 | 任意 `--source` 顺序与文件内行序排列 → digest 与选择不变（permutation fixtures） |
| AC-20 | 重复 Album 不增概率 | 同一 Album 出现在多个来源 → 候选数去重为一；添加只含重复条目的来源不得改变 selection-pool digest 与选择 |
| AC-21 | 来源意见分别保留 | 同一 Album 多来源 rating/note/attribution 并列展示、无平均/覆盖 |
| AC-22 | Genre 冲突 fail-closed | 同一身份键不同来源 Genre 不一致 → 运行失败、报告冲突详情、要求确认；零选择、零历史变更 |
| AC-23 | 来源只读与多用户共享 | 同一组来源 + 两个不同 profile/历史 → 两次运行后**来源文件字节不变**；同一来源可被多用户共享无需修改 |
| AC-24 | 无评分来源完全有效 | 全部来源无 rating_scale/rating → 推荐流程与有评分来源等价 |
| AC-25 | 历史来源证据 | 每条成功记录含 source_id 集合、per-source content digest、admissible selection-pool digest、algorithm/schema version、timezone 证据；content digest 不进入 seed |
| AC-26 | 跨版本/跨平台复现 | canonical digest 与 uniform-index 选择向量 fixtures 在受支持 Python 版本/平台产出相同结果 |
| AC-27 | 无任意日期覆盖 | 公共 CLI 无任何可用日期参数；clock seam 仅测试可达 |
| AC-28 | 许可完整 | ZIP 含完整 Apache-2.0 LICENSE 文本 + LICENSES.md；Skill 版本独立于核心版本 |
| AC-29 | 纯净模板零候选 | 全新模板通过校验、零候选、不产生推荐；示例块文本永不可能成为推荐 |
| AC-30 | 双语前言逐句对照 | 中英前言逐句意图对应评审（对照 Owner 原稿，checklist 留痕） |

## 9. 需要 Reviewer / Owner 复审确认的问题

1. **D5/D10/D23**：两层模型（个人状态入 profile 结构化表、来源只读、
   Genre 冲突 fail-closed）是否完整落实 ADR3-001/002 与 Owner 多来源决定？
2. **D11/D12**：原子历史替换为唯一 commit point、无公开日期覆盖、同日来源
   集合锁定——是否接受？
3. **D19-3**：版本化 uniform-index + canonical 表示作为可移植确定性协议，
   是否满足 ADR3-002-4？
4. **D22**：来源元数据字段集（7 项）是否齐备、有无需增删？
5. **D25**：未来权重"只能影响 Genre 内排列、永不影响 Genre 基础机会"的
   永久边界表述是否足够严格？
6. **计划 §C.7/C.8**：恢复后的完整前言结构与 Owner 原稿逐句对照——
   Executor 无 Owner 原稿全文，定稿需 Owner 逐句校订（AC-30）。

## 10. Reviewer acceptance constraints

本 ADR 的 Accepted 状态受以下约束；G6 实现与验收必须逐项满足：

1. **C1 — digest 职责分离**：per-source content digest 只作审计；选择 seed
   只能使用 admissible selection-pool digest。任何仅展示/审计字段的变化都
   不得改变 selection digest 或推荐结果。
2. **C2 — 受限 frontmatter**：D22 的 flat frontmatter 是 OMDA 自有受限格式，
   不是通用 YAML。标准库解析器必须拒绝嵌套、序列、tag、anchor、alias、
   重复字段与未知字段。
3. **C3 — Owner 文案仍须定稿**：计划 C.7/C.8 只是结构草稿，不代表 Reviewer
   接受其具体措辞。AC-30 必须用 Owner 原稿核对完整三段结构、第一人称语气与
   中英逐句意图；未完成该核对时 G6 不得判定通过。
4. **C4 — 授权边界**：接受 ADR 仅解除架构阻塞并允许执行 G6 计划；计划
   T6.9 所需的隔离临时归档构建/解压验证属于测试且允许执行，但不得留下对外
   分发包。除此之外，不代表 G6 Gate 接受，也不授权 merge、tag、push、
   对外打包、公开分发或发布。

## 11. 引用

- Owner 决策记录（2026-09-18 v1 + 同日多来源补充决定）。
- `reviews/adr/ADR_0003_REVIEW.md`（Reviewer commit `8aecaf7`，REVISE，
  ADR3-001 ~ ADR3-006 + Required revised acceptance additions 1–9）。
- `docs/OMDA_AGENT_HANDOFF_SPEC.md` §1、§2、§3.5、§4、§9。
- `docs/OMDA_PROJECT_MASTER_PLAN_zh-CN.md` §3、§9。
- `docs/adr/0002-production-album-source-and-runtime-boundary.md` D6/D8。
- `governance/G6_SKILL_BETA_PLAN.md`（Approved v2，受本节约束）。
- `governance/PROJECT_STATE.json`、`reviews/adr/ADR_0003_EXECUTOR_HANDOFF.md`。
