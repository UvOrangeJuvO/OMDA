# OMDA 项目主计划

> 状态：Architecture Baseline v0.1  
> 日期：2026-08-19  
> 说明：原会话生成文件没有保存在当前本机。本文件依据该会话中可恢复的项目规则重新建立为本仓库的规范基线；进入 G1 前应由 GPT-5.6 Sol 在 G0 评审中校核。

## 1. 项目愿景

OMDA（Open Music Discovery Agent）每天提供一份可解释、有多样性且不会重复 Album 的音乐探索清单：3 个 Genre，每个 Genre 3 张 Album，共 9 张。系统追求长期探索，而不是热门榜单复刻。

它首先是一个可长期维护的个人 Agent，同时采用适合开源贡献的文本数据、Schema、Adapter 边界和审计流程。

## 2. MVP 用户故事

用户启动一次推荐运行后，系统：

1. 读取合法 Genre 文本数据、配置及成功历史；
2. 选择 3 个未处于 cooldown 的 Genre；
3. 遵守 family/parent 多样性限制，地域/传统类等受限 family 每日最多一个；
4. 为每个 Genre 获取候选 Album 并补全必要信息；
5. 永久排除成功推荐过的 Album，也排除本次运行已经选中的 Album；
6. 每个 Genre 选择 3 张 Album，数据允许时至少一张发行于 2010 年或以后；
7. v0.1 由确定性运行时生成结构化事实报告（ADR-0002 D8：narrative 仅存档
   typed deterministic marker，不调用任何外部 LLM；未来 provider 模式需独立
   implemented adapter、版本化配置与 Gate 接受，不在 v0.1 激活）；
8. 验证 Markdown 输出并通过 PushPlus 或本地文件交付；
9. 只有完整交付成功后才正式写 Genre cooldown 和 Album history；
10. 失败时给出可恢复状态，不制造无声重复推送。

## 3. 产品不变量

### 3.1 Genre

- 合法 Genre 原则上等权。
- 不得因小众、microgenre、关注量、评分数量或 popularity 较低而减少其被选择概率。
- 不得建立 60/30/10 等人为 Genre tier 抽样比例。
- LLM 不给 Genre 打“质量分”，也不参与确定性抽样。
- 一个 Genre 成功推荐后，在其后的 30 个 Genre picks 内不可再次选择；第 31 个后续 pick 起可重新获得资格。
- cooldown 以成功提交的 Genre pick 序号计算，不是天数，也不是运行次数。
- family/parent constraint 用于同一份推荐内的多样性，不得借此形成 popularity filter 或永久饿死某类 Genre。

### 3.2 Album

- 一个 Album 成功推荐后永久排除。
- identity 优先采用 MusicBrainz release-group 等稳定 canonical ID；字符串规范化只能作为降级匹配。
- 同一次运行的 9 张 Album 也不得重复。
- 每个 Genre 默认选择 3 张 Album。
- 数据允许且质量门槛可满足时，至少 1 张应为 2010 年或以后作品，通常最多 2 张更老作品。
- 候选不足时必须按明确策略失败或降级并报告，不得用明显不相关的 Album 硬凑。

### 3.3 Rating

- RYM、critic、community、personal rating 是独立维度。
- 权重可配置，缺失值行为明确并可测试。
- 不把任何单一评分源写死为核心唯一标准。
- 新增 critic source 原则上只增加数据贡献包或 Adapter，不修改推荐 Core。

### 3.4 RYM 与浏览器

- 不实施 Cloudflare bypass、隐身对抗或验证码自动绕过。
- 不默认全站预抓、逐一访问所有 Album Detail 或持续高频抓取。
- 默认采用用户正常浏览器会话、人工可介入的薄 Browser Companion、DOM 提取、按需 enrichment 和本地缓存。
- 会话失效、页面变化或验证出现时暂停并请求人工处理。
- Playwright/CDP 可以是可选实现，但不得未经 ADR 成为 Core 强依赖。

### 3.5 数据与开源贡献

- Genre、critic 和 community contribution 以 YAML/CSV/JSON/JSONL 等可 diff 文本为真源。
- 每类贡献必须有机器可验证 Schema、具体错误信息和测试 fixture。
- SQLite 仅用作本地 history、cache、run journal 或编译索引，不作为社区数据的主要 Git 真源。
- 每个外部数据源记录来源、许可证、抓取/导入日期和使用边界。

### 3.6 LLM

- v0.1 是 deterministic/no-LLM runtime（ADR-0002 D8）：config 只接受
  `llm.mode=deterministic`，任何 provider 值在 config validation 阶段
  fail-closed（任何 run/journal/network 副作用之前）；交付物 = 确定性事实
  报告，narrative 存档为 typed deterministic marker，不保存任何伪造句子，
  不构造本地 echo transport 冒充生产 Agent。
- 确定性代码负责候选过滤、选择、去重、cooldown 和事务。
- 未来 provider 模式加入需独立 implemented adapter、schema/版本变更、
  cost/secret 控制与 Gate acceptance；不在 v0.1 激活。
- LLM（如未来启用）只基于提供的事实写解释与文案，输出必须经过结构、长度和
  引用事实验证；外部网页和数据内的指令均是不可信数据。

### 3.7 Run 事务

逻辑流程固定为：

```text
PLAN → FETCH → SELECT → GENERATE → VALIDATE → DELIVER → COMMIT HISTORY
```

FETCH 到 DELIVER 任一步失败，不得写正式推荐历史。由于外部推送与本地数据库无法形成真正分布式事务，系统必须采用 run id、journal、幂等键和恢复状态处理“已交付但本地 commit 失败”的窗口，不能虚假宣称绝对原子。

## 4. 目标架构

```text
CLI / Scheduler
      ↓
Application Orchestrator ───────────── Run Journal
      ↓
Recommendation Core ← Config / Domain Models
      ↓
Ports: Genre / Album / Critic / History / LLM / Delivery
      ↓
Adapters: text datasets, MusicBrainz, Browser Companion,
          local SQLite, LLM providers, Markdown, PushPlus
```

### Core

Core 只包含领域模型和纯/确定性规则：资格、cooldown、多样性、Album 排除、年份约束、评分组合和选择。Core 不导入 RYM DOM、PushPlus、具体 LLM SDK、浏览器 SDK 或数据库驱动。

### Application orchestration

协调一次 run 的状态机、错误分类、重试边界、journal、验证、交付和 history commit。

### Ports and adapters

每个外部来源和目的地通过小接口接入。Adapter 失败必须转换成领域可理解的错误，不泄露供应商细节到 Core。

### Storage

社区源数据保存在 `data/`。本地 SQLite 和缓存保存在被 Git 忽略的 `var/`。迁移必须可检测、可备份、可回滚或至少提供恢复说明。

## 5. 数据建议

### Genre source

至少包含：`genre_id`、`name`、`url`、`family`、`parents`、`eligible`、`source`。是否 eligible 只表示数据是否合法/有效，不是 popularity 评价。

### Album canonical identity

优先级建议：MusicBrainz release-group ID → 其他稳定来源 ID 映射 → 规范化 artist/title/year 复合键并记录置信度。模糊匹配不得静默永久封禁错误 Album。

### Critic contribution

一个来源采用 `source.yaml + ratings.csv`，包含 source id、显示名、许可/来源、评分量表、抓取日期和 canonical Album 映射。

### Runtime state

包含 append-friendly run journal、成功 Genre pick 序号、Album recommendation history、delivery idempotency key、schema version 和迁移元数据。

## 6. 失败与降级原则

- 数据源不可用：使用未过期缓存或清晰失败；不可用陈旧数据时标注来源时间。
- 候选不足：按规范决定该 Genre 不可完成并重新规划，不能无界重试。
- LLM 失败：保留选择计划但不提交 history；允许以后以同一 run id 重试生成。
- 推送失败：不提交成功历史；可用幂等键安全重试。
- 推送成功、history commit 失败：journal 进入需要恢复的明确状态，重跑前先查询/确认交付结果。
- 进程崩溃：从 journal 恢复或安全中止，不猜测是否成功。

## 7. 安全、隐私与许可

- 密钥仅通过环境变量或本地 secret store 注入。
- Cookie 和 browser profile 永不进入 Git、日志、Prompt 或报告。
- 日志做字段化脱敏，不记录完整页面会话数据。
- 网络访问使用超时、限速、退避和清晰 user-agent/合法会话策略。
- 不构建反爬对抗；遵守网站条款、机器人规则和适用法律，由 Owner 对数据使用做最终确认。
- 开源发布前生成依赖与数据许可证清单。

## 8. 推荐质量与可观测性

最低可观测字段：run id、版本、seed、输入数据版本、候选数量、每步状态、选择理由（规则证据）、外部调用摘要、delivery 状态和 history commit 状态。

质量评价包括：重复率必须为零、cooldown 违规必须为零、约束满足率、运行成功率、恢复成功率、数据陈旧度和用户反馈。不要把“越热门”当作默认质量。

## 9. MVP 非目标

- 训练推荐模型或建立社交推荐平台；
- RYM 全站镜像或 Cloudflare 对抗；
- 大规模 Album Detail fan-out；
- LLM 主导的 Genre/Album 选择；
- 多用户云服务、复杂权限系统和分布式队列；
- 把 OMDA 架在大型音乐管理框架之上；
- 在 v0.1 同时支持所有浏览器、所有推送和所有 critic 来源。

## 10. Gate 路线

- G0：实施计划和架构基线审查。
- G1：仓库、配置、Schema、验证、状态抽象与测试基础。
- G2：推荐 Core 和事务状态机。
- G3：数据与 Adapter，包括 Browser Companion contract。
- G4：LLM、Markdown、PushPlus 与错误恢复。
- G5：端到端、安装、许可、安全、备份恢复与发布审计。

每个 Gate 的精确 SHA 必须由独立 Reviewer 接受后才能进入下一阶段。

## 11. MVP 完成定义

- 从干净环境可按照文档安装并执行 dry-run；
- 所有核心不变量均有自动测试；
- 真实/fixture 数据可以完整生成 3×3 推荐；
- 失败注入证明正式 history 不被污染；
- 推送幂等与 crash recovery 有证据；
- secrets、依赖和数据许可检查通过；
- 新贡献者能仅通过文本文件添加 Genre/critic 数据并通过验证；
- G0–G5 均有可追溯的 accepted SHA 和 Reviewer verdict。

