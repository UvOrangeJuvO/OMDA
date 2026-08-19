# OMDA 双模型开发与独立评审操作手册

> 版本：v1.0（2026-08-18）  
> 适用项目：Open Music Discovery Agent（OMDA）  
> 执行模型：DeepSeek V4 Flash  
> 独立 Reviewer：Codex 中的 GPT-5.6 Sol（高推理档）  
> 推荐执行环境：腾讯云 WorkBuddy；DeepSeek Harness 作为后续可替换/试验性方案  
> 状态与交接真源：本地 Git + 仓库内 Markdown/JSON 文件，而不是聊天记录

---

## 0. 先看这一页：最简单的使用方法

你只需要记住六件事：

1. 把两份既有项目规范放进仓库：`docs/OMDA_PROJECT_MASTER_PLAN_zh-CN.md` 和 `docs/OMDA_AGENT_HANDOFF_SPEC.md`。
2. 用 WorkBuddy 打开仓库，固定选择 `deepseek-v4-flash`，把本手册的「Prompt 1」交给它；第一次只让它做实施计划，不写代码。
3. DeepSeek 提交一个本地 Git commit，并生成阶段报告；不要让它直接进入下一阶段。
4. 在 Codex 中让 GPT-5.6 Sol 用「Prompt 5」审查同一个仓库和指定 commit。
5. Reviewer 只可返回 `ACCEPTED`、`CHANGES_REQUESTED` 或 `BLOCKED_ARCHITECTURE`。不通过时，把评审文件交回 DeepSeek，用「Prompt 6」修复。
6. 六个 Gate 全部通过后才打 `v0.1.0-rc1` 标签。聊天里说“完成了”不算完成；Git、测试证据和状态文件才算。

一句话流程：

```text
规范 → DeepSeek 计划/实现 → 自测 → commit → 阶段报告
     → Sol 独立审查 → 接受或退修 → 下一阶段 → 最终验收
```

---

## 1. 用户原始表述的工程化校对

本手册把口述中的名称和职责统一如下：

| 原始/可能的口述 | 本手册统一写法 | 说明 |
|---|---|---|
| DeepSea V4 Flash | DeepSeek V4 Flash / `deepseek-v4-flash` | 后者是官方 API 模型标识 |
| 五点座 Sol | GPT-5.6 Sol | 在 Codex 中作为独立 Reviewer |
| WorkBody / WorkBuddy | 腾讯云 WorkBuddy | 本项目语境指腾讯云桌面 Agent，不是同名 Obsidian 项目 |
| DeepSeek harness | DeepSeek Harness / `dsh` | 必须核对发行者与版本；网上有多个同名第三方仓库 |
| RM | RYM（Rate Your Music） | 项目的可选数据增强来源 |
| 双重评审 | Executor–Reviewer 双模型闭环 | 不是两个模型都随意写代码 |

### 不可混淆的产品

- 腾讯云 WorkBuddy 是支持本机操作、多模型切换和腾讯生态连接的桌面 Agent；腾讯云页面已明确列出对 DeepSeek V4 Flash 的支持。
- `work-buddy.ai` 是另一个基于 Claude Code 与 Obsidian 的 local-first 项目，不是本手册所说的腾讯云 WorkBuddy。
- GitHub 上存在多个名为 `deepseek-harness` 的第三方仓库。安装前必须检查组织、包名、版本、发布日期与文档，不能仅凭项目名判断“官方”。

---

## 2. 公开资料核实结果与选型

### 2.1 已确认事实

截至 2026-08-18：

- DeepSeek 官方 API 文档列出 `deepseek-v4-flash` 和 `deepseek-v4-pro`；Flash 支持思考/非思考模式、工具调用，官方称其更快、更经济，在简单 Agent 任务上接近 Pro，并提供 1M 上下文。[DeepSeek V4 发布说明](https://api-docs.deepseek.com/news/news260424/)；[Chat Completions API](https://api-docs.deepseek.com/api/create-chat-completion/)
- 腾讯云 WorkBuddy 官方活动页已列出对 DeepSeek V4 Flash 的支持；腾讯云文档把 WorkBuddy描述为支持本机操作和多模型切换的桌面 Agent。[腾讯云 WorkBuddy](https://cloud.tencent.com/act/pro/workbuddy)；[腾讯云 WorkBuddy 文档](https://intl.cloud.tencent.com/document/product/1300/80640)
- DeepSeek V4 的多轮工具链需要正确保留模型协议字段。若采用自建或第三方客户端，必须做版本与协议兼容验证，不能假设任意 OpenAI-compatible 客户端都完全正确。
- 一个公开的第三方 `deepseek-harness` 项目主要解决 V4 协议适配、消息验证、流式工具调用与缓存等问题；它并不天然等于完整的、适合普通用户的代码工作台。[第三方协议适配项目](https://github.com/HenryZ838978/deepseek-harness)

### 2.2 选型结论

**v0.1 首选腾讯云 WorkBuddy，固定 DeepSeek V4 Flash，使用 Craft/可写代码模式执行；Codex + GPT-5.6 Sol 单独评审。**

原因：

| 维度 | 腾讯云 WorkBuddy | DeepSeek Harness / dsh 类工具 |
|---|---|---|
| 上手难度 | 低，图形界面，适合逐步操作 | 中到高，偏命令行/框架配置 |
| V4 Flash 可用性 | 官方页面明确支持 | 取决于具体发行版和适配器 |
| 本地文件与命令 | 面向桌面 Agent 工作流 | 通常更可控，但需要自行搭建 |
| Git 使用 | 可让 Agent 调用本地 Git | 很适合脚本化、CI 和可复现运行 |
| 长任务可观察性 | 对非专业用户更友好 | 日志和控制能力通常更强 |
| 供应链风险 | 商业产品与积分/版本依赖 | 同名项目多，包来源需严格核验 |
| 适合本项目当前阶段 | **最佳** | 适合第二阶段 A/B 试验或高级用户 |

选择 WorkBuddy 不是把项目绑定到 WorkBuddy。所有规范、状态、报告和代码均保存在 Git 仓库，因此以后可以换成官方 `dsh`、OpenCode 或其他执行器而不改变治理协议。

### 2.3 何时改用 Harness

只有同时满足下列条件才切换：

- 能明确验证安装包的发布者、版本、校验来源和许可证；
- 能稳定完成读文件、改文件、运行测试、查看 diff、提交 Git；
- 连续完成至少 3 个沙盒任务，没有丢失消息、工具调用或写错工作目录；
- 相比 WorkBuddy 有可测量收益，例如失败率、成本、速度或审计日志明显改善；
- 通过一份 ADR，由 Reviewer 批准。

不要在 OMDA 正式开发中直接试用一个来源不明的同名 Harness。

---

## 3. OMDA 项目：给非技术用户的整体结构

OMDA 每次运行做的事是：从合法 Genre 池中选择 3 个流派，为每个流派选 3 张未推荐过的专辑，生成介绍并推送；仅在完整成功后写入历史。

```text
Genre 文本数据 + 已推荐历史 + 配置
                 ↓
          推荐核心（确定性规则）
                 ↓
      数据适配器按需补全 Album 信息
                 ↓
       LLM 只负责解释，不负责改规则
                 ↓
        Markdown 输出 / PushPlus
                 ↓
       成功后事务式提交推荐历史
```

### 核心产品规则（不得静默修改）

1. 合法 Genre 原则上等权；不得引入 popularity filter、LLM Genre quality score 或人为 Tier 概率。
2. 一个 Genre 被选后，在后续 30 个 Genre picks 内不得再次出现；单位不是天。
3. 同一日的 family/parent 多样性约束只避免三个 Genre 过度相似，不用于淘汰小众 Genre。
4. 已成功推荐的 Album 永久排除，优先使用稳定 canonical/release-group identity。
5. 每个 Genre 默认 3 张 Album；数据允许时至少一张为 2010 年或以后，通常最多两张旧专辑。
6. 评分维度相互独立、权重可配置；增加 critic 数据源不应修改 Core。
7. RYM 采用正常浏览器会话、人工可介入的 Browser Companion、按需抓取、渐进缓存；禁止 Cloudflare 绕过和全站预抓。
8. 社区数据以 YAML/CSV/JSON(L) 等可 diff 文本为真源；SQLite 只做本地状态、缓存或编译索引。
9. LLM 负责解释与文案，确定性代码负责筛选和约束。
10. 只有 `PLAN → FETCH → SELECT → GENERATE → VALIDATE → DELIVER` 全部成功，才 `COMMIT HISTORY`。失败运行不得污染历史。

### 推荐仓库目录

```text
omda/
├── AGENTS.md
├── README.md
├── pyproject.toml
├── .gitignore
├── docs/
│   ├── OMDA_PROJECT_MASTER_PLAN_zh-CN.md
│   ├── OMDA_AGENT_HANDOFF_SPEC.md
│   ├── OPERATIONS_HANDBOOK.md
│   └── adr/
├── governance/
│   ├── PROJECT_STATE.json
│   ├── IMPLEMENTATION_PLAN.md
│   ├── REVIEW_LOG.md
│   └── RISK_REGISTER.md
├── reviews/
│   ├── stage-00/
│   └── final/
├── data/
│   ├── genres/
│   ├── critics/
│   └── schemas/
├── src/omda/
│   ├── core/
│   ├── models/
│   ├── storage/
│   ├── adapters/
│   ├── output/
│   └── cli.py
├── browser-companion/
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── contract/
│   └── fixtures/
└── var/                 # 本地缓存、SQLite、临时输出；通常不提交
```

Core 不得导入某个具体平台、RYM DOM、PushPlus 或具体 LLM SDK；这些都放在边缘 adapter 中。

---

## 4. 双模型的权限分离

### 4.1 DeepSeek V4 Flash：Executor

可以：

- 阅读规范和已批准 ADR；
- 拆分任务、实现代码、测试、修复；
- 在指定分支创建本地 commit；
- 生成真实、可核验的阶段报告。

不可以：

- 自行改变产品规则、架构边界、Schema 兼容性或历史事务语义；
- 自己批准自己的阶段；
- 删除/弱化失败测试来“通过”；
- 在 Gate 未接受时进入下一阶段；
- 将 API key、Cookie、浏览器 Profile 或个人数据提交到 Git。

### 4.2 GPT-5.6 Sol：Reviewer

可以：

- 读取规范、commit、diff、测试与报告；
- 独立运行只读检查和测试；
- 发现架构漂移、安全、许可、状态损坏或可维护性问题；
- 输出有优先级、文件位置、复现与验收方法的修改要求；
- 批准 ADR 或要求用户决策。

默认不可以：

- 为了省事直接接管整个实现；
- 在审查时顺手大改代码，使“作者”和“审查者”变成同一角色；
- 仅凭阶段报告断言通过，不看 diff 和证据；
- 把个人偏好升级成阻断项。

若用户明确要求 Reviewer 修复，可另开一次“Reviewer-assisted repair”，但修复后的 commit 必须再做一次独立复核。

### 4.3 用户：Owner

- 决定产品语义和重大取舍；
- 批准 P0 级 ADR、破坏性迁移、范围扩张与发布；
- 保管密钥、处理浏览器人工验证；
- 在 Reviewer 和 Executor 意见冲突时裁决。

---

## 5. 状态机与仓库状态文件

### 5.1 任务状态

```text
BACKLOG → READY → IN_PROGRESS → SELF_VERIFIED
        → READY_FOR_REVIEW → ACCEPTED

READY_FOR_REVIEW → CHANGES_REQUESTED → IN_PROGRESS
任意状态 → BLOCKED_ARCHITECTURE → ADR_PENDING → READY
```

只有 Reviewer 可以把 Gate 置为 `ACCEPTED`。Executor 只能写到 `READY_FOR_REVIEW`。

### 5.2 `governance/PROJECT_STATE.json` 模板

```json
{
  "schema_version": 1,
  "project": "OMDA",
  "release_target": "0.1.0",
  "active_gate": "G0",
  "status": "READY_FOR_REVIEW",
  "executor": "deepseek-v4-flash",
  "reviewer": "gpt-5.6-sol",
  "base_commit": "<40-char-sha>",
  "candidate_commit": "<40-char-sha>",
  "approved_commit": null,
  "open_review": "reviews/stage-00/EXECUTOR_REPORT.md",
  "blocking_adr": null,
  "updated_at": "2026-08-18T00:00:00Z"
}
```

规则：

- SHA 必须是完整 commit id，不写 `latest`。
- 状态更新和对应报告必须放在同一 commit。
- Reviewer 接受后，将 verdict 和 `approved_commit` 写入 Review 文件；不要让 Executor 伪造 Reviewer 结论。
- JSON 只能保存机器状态；理由写入 Markdown 报告。

### 5.3 每个 Gate 的审计包

```text
reviews/stage-0N/
├── EXECUTOR_REPORT.md
├── TEST_RESULTS.txt
├── REVIEW_VERDICT.md
└── REPAIR_REPORT.md       # 仅退修时存在
```

`TEST_RESULTS.txt` 必须是实际测试输出的保存件或可复现摘要，不能由模型凭空撰写。

---

## 6. 六个阶段 Gate

| Gate | 阶段 | Executor 交付物 | Reviewer 阻断重点 |
|---|---|---|---|
| G0 | 计划与基线 | 需求复述、模块边界、任务拆解、测试计划、非目标 | 误解产品规则、过度工程、偷偷扩范围 |
| G1 | Foundation | 仓库骨架、配置、Schema、验证、状态抽象、基础测试 | 数据真源错误、Core 与平台耦合、密钥风险 |
| G2 | Recommendation Core | Genre 等权、30-pick cooldown、多样性、Album 去重、年份/评分规则、事务状态机 | 随机偏差、边界条件、失败污染历史；**最高强度评审** |
| G3 | Data & Adapters | MusicBrainz/社区/critic 接口、RYM contract、Browser Companion、缓存 | 单一来源污染 Core、Cloudflare 对抗、全量预爬、许可问题 |
| G4 | Agent & Delivery | LLM provider、受控 Prompt、Markdown、PushPlus、错误恢复 | LLM 越权选择、秘密泄漏、输出后提交次序错误 |
| G5 | Release Audit | E2E、文档、安装、迁移/恢复、许可证、安全、RC | 回归、不可复现、未记录风险、贡献体验差 |

### 强制立即评审的触发器

不等到阶段结束，Executor 必须停止并进入 `BLOCKED_ARCHITECTURE`，如果它准备：

- 改产品不变量或推荐语义；
- 改公开 Schema、持久化结构或 plugin contract；
- 引入新数据库、框架、大型运行时或浏览器自动化依赖；
- 改历史提交时机；
- 访问策略涉及绕过反爬/验证；
- 新增未明确许可的数据集；
- 做不可逆迁移或删除用户数据。

---

## 7. 本地 Git 工作流

### 7.1 一次性初始化

```bash
git init
git branch -M main
git add .
git commit -m "chore: establish OMDA architecture baseline"
git tag architecture-v0.1
```

先确认 `.gitignore` 至少排除：

```gitignore
.env
*.key
var/
browser-profile/
cookies*.json
*.sqlite3
__pycache__/
.pytest_cache/
```

### 7.2 分支约定

- `main`：只接收 Reviewer 已接受的 Gate。
- `exec/g0-plan`、`exec/g1-foundation`：Executor 阶段分支。
- `fix/g2-review-01`：退修分支（也可继续使用原阶段分支，但必须新 commit）。
- `adr/0001-title`：重大决策文档分支。

如果只有一台机器，本地分支已经足够，不需要先上 GitHub。

### 7.3 每阶段固定命令顺序

```bash
git status --short
git switch main
git switch -c exec/g1-foundation
# DeepSeek 实现并测试
git diff --check
git status --short
git add <明确文件列表>
git commit -m "feat(g1): establish schemas and local state boundary"
git rev-parse HEAD
```

禁止 `git add .` 作为 Agent 的日常默认动作；它应先查看状态并显式添加文件，避免提交密钥或用户的无关文件。

### 7.4 评审与合并

Reviewer 审查 `main..candidate_sha`。通过后：

```bash
git switch main
git merge --no-ff exec/g1-foundation -m "merge: accept gate G1 foundation"
git tag gate-g1-accepted
```

不通过：禁止合并；Executor 依据 verdict 新增修复 commit，Reviewer 重新审查完整范围和增量修复。

### 7.5 Git 安全规则

- 不允许 Agent 使用 `git reset --hard`、强推、重写已接受历史或清除未知文件。
- 回滚优先 `git revert <sha>`，保留审计链。
- 每次评审前工作区应干净；若不干净，报告所有未提交文件。
- 绝不把 API key 放进 Prompt、报告、测试快照或 Git。
- Reviewer 的接受只适用于精确 SHA；之后修改一行代码也要重新评审相关范围。

---

## 8. 每个角色的傻瓜式操作指南

### 8.1 用户每天怎么做

1. 打开 WorkBuddy，选择 OMDA 文件夹。
2. 模型固定为 DeepSeek V4 Flash；实现阶段使用可读写文件和运行命令的模式。
3. 粘贴本阶段对应 Prompt。
4. 等它停止后，检查它是否给出完整 SHA、测试结果和阶段报告路径。
5. 若没有完整 SHA 或测试失败，让它补齐，不送审。
6. 打开 Codex 的同一仓库，选择 GPT-5.6 Sol 高推理档，粘贴 Reviewer Prompt。
7. 若 `ACCEPTED`，合并到 main 并开始下一 Gate；若 `CHANGES_REQUESTED`，把 verdict 路径交回 WorkBuddy。
8. 若 `BLOCKED_ARCHITECTURE`，先处理 ADR，不让 DeepSeek继续猜。

### 8.2 Executor 每个 Atomic Task 的固定循环

```text
读状态 → 读相关规范 → 写最小变更 → 写/更新测试
→ 跑相关测试 → 查看 diff → 自检不变量 → commit
```

每个 Atomic Task 不必找 Reviewer；一个 Gate 完成或触发架构敏感变更时才送审。

### 8.3 Reviewer 的固定循环

```text
确认 base/candidate SHA → 工作区检查 → 读规范和阶段目标
→ 查看完整 diff → 运行测试 → 对照不变量和验收矩阵
→ 按严重度记录发现 → 给唯一 verdict
```

严重度：

- P0：数据损坏、安全/秘密泄漏、违法/许可重大风险、核心语义错误；绝对阻断。
- P1：可复现功能错误、关键测试缺失、架构违约；阻断。
- P2：可维护性、文档或较小风险；可按数量和影响决定是否阻断。
- P3：非阻断建议；不能伪装成必须修改的个人偏好。

---

## 9. 完整 Prompt 套件

使用方法：把尖括号字段替换为真实值。不要一次把所有 Prompt 粘给模型；按当前步骤只用一个。

### Prompt 1：Executor 首次启动（只做计划）

```text
你是 OMDA 项目的 Implementation Executor，模型固定为 DeepSeek V4 Flash。

权威顺序：
1. docs/OMDA_AGENT_HANDOFF_SPEC.md
2. docs/OMDA_PROJECT_MASTER_PLAN_zh-CN.md
3. 已批准 ADR
4. 本操作手册
5. 已批准 IMPLEMENTATION_PLAN
6. 当前任务
7. 你的工程判断

冲突时必须遵守更高层。你不能批准自己的工作，也不能静默改变产品或架构。

现在先执行只读检查：确认仓库状态、列出规范文件、阅读上述文件。不得写 production code。

创建或更新 governance/IMPLEMENTATION_PLAN.md，内容必须包括：
- 用自己的语言复述目标、MVP、十条产品不变量和非目标；
- 最小模块边界及数据流，区分 Core 与 Adapter；
- G1–G5 的 Atomic Tasks、依赖、交付物和验收标准；
- schema、unit、property/边界、integration、contract、E2E 测试策略；
- P0/P1/P2 风险登记；
- 回滚和失败恢复；
- 自我批判：过度设计、平台耦合、RYM 实时依赖、历史污染、社区贡献难度。

重点确认：Genre 等权；cooldown 是后续 30 个 genre picks；Album 成功推荐后永久排除；LLM 不做确定性选择；失败 run 不提交 history；禁止 Cloudflare 绕过和大规模预爬；文本是社区数据真源。

更新 governance/PROJECT_STATE.json 到 G0/READY_FOR_REVIEW，生成 reviews/stage-00/EXECUTOR_REPORT.md。提交一个本地 Git commit，报告 base SHA、candidate 完整 SHA、文件、实际检查命令、已知风险。然后停止。不得进入 G1。
```

### Prompt 2：Executor 开始一个已批准 Gate

```text
你是 OMDA Executor。开始 Gate <GATE_ID>: <GATE_NAME>。
批准基线 SHA：<APPROVED_SHA>
本阶段分支：<BRANCH>

先核对当前 HEAD、工作区、PROJECT_STATE、已批准计划和所有相关 ADR。若不一致，停止并报告，不要猜。

只实现 governance/IMPLEMENTATION_PLAN.md 中本 Gate 的已批准范围。按 Atomic Task 循环：最小变更、测试、diff 自检、commit。不得进入下一 Gate。

任何产品不变量、公共 Schema、持久化、adapter contract、依赖、许可、历史事务或 RYM 访问策略变更，立即进入 BLOCKED_ARCHITECTURE 并使用 ADR 请求格式。

完成后执行本阶段全部验证；失败测试不得隐藏、跳过或改弱。生成 reviews/stage-<NN>/EXECUTOR_REPORT.md 与真实测试结果摘要，更新 PROJECT_STATE 为 READY_FOR_REVIEW，提交最终 handoff commit，并输出 base SHA、candidate 完整 SHA、提交列表、测试统计、偏差、残余风险。然后停止。
```

### Prompt 3：Executor Atomic Task

```text
执行 Atomic Task <ID>: <TITLE>。
允许范围：<FILES_OR_MODULES>
验收标准：<CRITERIA>
关联规范：<SECTIONS>

开始前确认工作区与父 commit。先写或确认失败测试，再做满足标准的最小实现。运行相关测试与静态检查，检查 git diff 和秘密泄漏。不要顺手重构无关代码，不要修改更高层规范。

完成后输出：修改、原因、命令和结果、验收证据、风险、commit SHA。若遇架构敏感问题，停止并生成 ADR 请求，不得自行选择。
```

### Prompt 4：阶段报告生成

```text
为 Gate <ID> 生成 reviews/stage-<NN>/EXECUTOR_REPORT.md。所有陈述必须可由仓库和命令验证，不得凭记忆美化。

必须包含：
1. Gate、base SHA、candidate SHA、分支、工作区状态；
2. 计划范围、实际范围、明确非目标；
3. 每个 commit 与重要文件变更及原因；
4. 架构影响：Core/Schema/plugin/history/migration/兼容性；
5. 十条产品不变量逐项 PASS/FAIL/N/A 与证据；
6. 实际运行命令、总数/通过/失败/跳过；
7. 验收标准矩阵（标准、状态、证据位置）；
8. 与规范/计划的所有偏差；
9. 新增依赖及许可证；
10. 失败恢复：网络、空数据、重复、畸形输入、LLM/推送失败、进程崩溃；
11. P0/P1/P2 技术债和已知限制；
12. READY_FOR_REVIEW 或 NOT_READY 的结论。

只要有核心测试失败、未解释偏差或工作区含未提交相关更改，结论必须是 NOT_READY。
```

### Prompt 5：GPT-5.6 Sol 独立阶段评审

```text
你是 OMDA 的独立 Reviewer（GPT-5.6 Sol）。只做审查，不默认接管实现。

Gate：<GATE_ID>
Base commit：<BASE_40_CHAR_SHA>
Candidate commit：<CANDIDATE_40_CHAR_SHA>
Executor report：<REPORT_PATH>

先验证两个 SHA、工作区和报告是否一致。读取：
- docs/OMDA_AGENT_HANDOFF_SPEC.md
- docs/OMDA_PROJECT_MASTER_PLAN_zh-CN.md
- governance/IMPLEMENTATION_PLAN.md
- 已批准 ADR
- PROJECT_STATE 与阶段报告

审查完整 base..candidate diff，不只看报告。按风险运行相关测试或只读检查。重点检查：Genre 等权和随机偏差；30-pick cooldown 边界；family diversity 不变成 popularity filter；Album canonical 永久去重；2010 年约束及候选不足行为；评分缺失与权重；失败 run 的原子性；Core/Adapter 边界；RYM 合规访问；秘密、依赖和许可证；确定性与可复现测试。

把结果写入 reviews/stage-<NN>/REVIEW_VERDICT.md：
- 精确 base/candidate SHA；
- Findings 按 P0/P1/P2/P3，给出文件/行或符号、复现、影响、所违反的规则、最小验收方法；
- 验收矩阵；
- 实际检查和限制；
- 唯一 verdict：ACCEPTED / CHANGES_REQUESTED / BLOCKED_ARCHITECTURE。

规则：任何 P0/P1 未解决不得 ACCEPTED；没有发现问题时明确写“无阻断发现”，不要虚构问题。接受只对 candidate SHA 有效。不要修改 production code。
```

### Prompt 6：Executor 根据评审修复

```text
你是 OMDA Executor。评审结论为 CHANGES_REQUESTED。
被审 candidate：<OLD_SHA>
Verdict：<VERDICT_PATH>

逐条读取 Finding，先复现，再以最小改动修复。不得借修复扩大范围，不得删除/弱化测试，不得把 Reviewer 的建议误当作产品变更。

对每个 Finding 记录：ID、根因、修复文件、回归测试、结果。若某项实际需要改变产品/架构，停止并转 ADR，不要擅自修复。

运行原 Gate 的完整测试和新增回归测试，生成 REPAIR_REPORT.md，更新 PROJECT_STATE 为 READY_FOR_REVIEW，提交新的 commit。输出旧 SHA、新完整 SHA、逐项关闭证据和残余风险，然后停止等待复审。
```

### Prompt 7：Reviewer 复审

```text
复审 OMDA Gate <ID>。
原 candidate：<OLD_SHA>
新 candidate：<NEW_SHA>
原 verdict：<VERDICT_PATH>
修复报告：<REPAIR_REPORT_PATH>

先验证每个阻断 Finding 的复现与关闭证据；再审查 OLD_SHA..NEW_SHA 增量，最后对 BASE_SHA..NEW_SHA 做必要回归。检查是否引入范围漂移或弱化测试。

更新 REVIEW_VERDICT.md，保留原 Finding 及 Closed/Open 状态，输出唯一 verdict。接受仅对 NEW_SHA 有效。
```

### Prompt 8：架构问题 / ADR 请求（Executor）

```text
进入 BLOCKED_ARCHITECTURE。停止 production code。

创建 docs/adr/NNNN-<slug>.md，状态 Proposed，包含：
- Context：可复现事实和当前阻塞；
- Existing contract：相关规范与不能满足之处；
- Options：至少“维持现状”及可行替代；
- 每个方案的收益、复杂度、数据迁移、兼容性、安全/许可、测试影响；
- 推荐方案及为何；
- 明确不做什么；
- rollout、rollback、acceptance tests；
- 需要 Owner 决定的问题。

更新 PROJECT_STATE 为 BLOCKED_ARCHITECTURE/ADR_PENDING。只提交 ADR 和状态，不实现任何方案。
```

### Prompt 9：ADR 评审（Sol）

```text
评审 ADR：<ADR_PATH>。你是架构守门人，不因“更先进”而自动批准复杂方案。

核对事实、现有契约、替代方案、范围、迁移、回滚、测试、安全、许可和长期维护成本。特别检查是否重新引入 popularity filter、LLM selection、大规模预爬、Cloudflare 对抗、Album detail fan-out 或平台锁定。

输出：ACCEPT / REVISE / OWNER_DECISION_REQUIRED；给出理由、必要修订、被修改的规范章节和验收测试。若接受，将 ADR 状态改为 Accepted，但不要实现代码。
```

### Prompt 10：最终发布验收（Sol）

```text
对 OMDA v0.1.0-rc1 候选 <SHA> 做最终独立审计。

审计从 architecture baseline 到候选的完整变更，并验证 G0–G4 的 accepted SHA、ADR、状态链和报告。运行或核验：全测试、E2E dry-run、失败注入、历史原子性、重复与冷却边界、安装说明、空白环境启动、配置校验、秘密扫描、依赖/许可证、数据来源许可、备份/恢复和 Browser Companion 人工介入路径。

必须特别模拟：
1. RYM/数据源失败；
2. 某 Genre 无现代候选；
3. 9 张中出现已推荐 Album；
4. LLM 失败；
5. PushPlus 失败；
6. deliver 后 history commit 失败；
7. 进程中途崩溃并重跑。

生成 reviews/final/RELEASE_AUDIT.md，列 Findings、证据、已知限制、回滚说明和唯一 verdict：RELEASE_CANDIDATE_ACCEPTED / CHANGES_REQUESTED / NO_GO。没有接受前不得建议打正式标签。
```

### Prompt 11：Executor 最终打包（只在最终接受后）

```text
最终审计已对 SHA <ACCEPTED_SHA> 返回 RELEASE_CANDIDATE_ACCEPTED。

确认 HEAD 精确等于该 SHA、工作区干净、所有 Gate 与 ADR 状态一致。只做不改变 production 内容的发布元数据整理；若任何文件需要变化，创建新 commit 并重新送最终审计。

输出建议的 tag 命令、release notes 草稿、安装/升级/回滚摘要和已知限制。不要推送远程，不要发布外部服务，除非 Owner 另行明确授权。
```

### Prompt 12：紧急回滚

```text
OMDA 发布候选 <SHA> 出现问题：<SYMPTOM>。

先停止自动运行，保护 var/ 和历史数据库的副本，记录最后成功 run id。只读诊断影响范围，找出最后已知良好 tag。优先使用 git revert 保留审计历史，不使用 reset --hard，不删除用户数据。

提出回滚计划、数据恢复验证、重复推送防护和验收步骤。未经 Owner 明确批准，不执行不可逆数据操作。
```

---

## 10. 阶段报告标准模板

```markdown
# Gate G2 Executor Report

## Identity
- Base SHA:
- Candidate SHA:
- Branch:
- Worktree clean: yes/no

## Scope / Non-goals

## Commits and Changes

## Architecture Impact

## Product Invariant Matrix
| Invariant | PASS/FAIL/N/A | Evidence |
|---|---|---|

## Acceptance Matrix
| Criterion | PASS/FAIL | Evidence |
|---|---|---|

## Verification
| Command | Result | Counts |
|---|---|---|

## Failure and Recovery

## Deviations / Dependencies / Licenses

## Risks and Technical Debt

## Executor Conclusion
READY_FOR_REVIEW / NOT_READY
```

## 11. Reviewer Verdict 标准模板

```markdown
# Gate G2 Review Verdict

## Reviewed Object
- Base SHA:
- Candidate SHA:
- Report:
- Reviewer:

## Findings
### [P1] G2-001 — 标题
- Location:
- Evidence/reproduction:
- Impact:
- Violated contract:
- Required acceptance test:

## Acceptance Matrix

## Checks Performed and Limitations

## Verdict
ACCEPTED / CHANGES_REQUESTED / BLOCKED_ARCHITECTURE
```

---

## 12. 推荐核心的最低测试清单

### Genre

- 每个合法 Genre 在固定候选集下具有等权机会；用统计/property test 检查明显偏差。
- 第 1–30 个后续 pick 不能复现，第 31 个符合条件时可复现。
- 一次日运行选择 3 个 Genre 时，pick 序号递增语义明确。
- family/Regional 限制不会永久饿死某类 Genre。
- 候选不足时产生明确失败或降级，不死循环。

### Album

- canonical ID 相同但名称不同仍判重；名称相同但不同发行不被错误合并。
- 已成功推荐 Album 永久排除。
- 三张中尽可能至少一张 `year >= 2010`；无现代候选时行为符合规范且被说明。
- 缺年份、缺评分、多个 critic 缺失时不崩溃且排名规则可解释。
- 同一日不同 Genre 重叠候选不会选出同一 Album 两次。

### 事务与恢复

- fetch、generate、validate、deliver 任一失败，正式 history 不变化。
- deliver 成功但 history commit 失败时不会无声重复推送；必须有 run journal/idempotency 设计。
- 进程崩溃重跑不会得到半提交状态。
- SQLite 事务与外部推送无法做真正分布式原子事务，因此要用 run journal、幂等键和可恢复状态，而不是声称“绝对原子”。

### Adapter 与安全

- DOM 变化、空页面、验证码、限流、网络超时均有受控错误。
- Browser Companion 不保存/提交 Cookie；正常会话失败时请求人工介入。
- critic/community 文件通过 Schema 校验并报告具体行。
- Prompt injection 风格的网页文本只作为数据，不可覆盖系统规则或调用工具。
- 输出转义、PushPlus 长度与重复投递有测试。

---

## 13. 质量仪表盘与停止规则

每个 Gate 最少记录：

- 测试通过/失败/跳过数；
- 新增和变更依赖数；
- P0/P1/P2/P3 Finding 数；
- 从送审到接受的修复轮次；
- 与计划的偏差数；
- 未解决风险及 Owner 接受记录。

建议停止并人工检查的信号：

- 同一 Finding 修复三次仍失败；
- Executor 修改超过本 Gate 预计范围约 2 倍；
- 测试“通过”但跳过数突然增加；
- candidate SHA 与报告不一致；
- Agent 要求删除未知文件、重写 Git 历史或绕过网页验证；
- Reviewer 开始大量实现而不是审查；
- 为满足测试而改变产品规则。

---

## 14. 第一次真正开工的推荐顺序

1. 创建本地仓库和 `.gitignore`。
2. 放入两份既有规范与本手册，做 architecture baseline commit/tag。
3. WorkBuddy 固定 V4 Flash，运行 Prompt 1。
4. Codex/Sol 用 Prompt 5 审 G0；只审计划。
5. G0 接受后，DeepSeek 用 Prompt 2 做 G1。
6. G1 接受后做 G2；给 G2 最多审查时间。
7. G3 先实现 adapter contract 和 fixtures，再接真实 RYM Browser Companion。
8. G4 最后接 LLM 和 PushPlus，先 dry-run，不立即每天自动推送。
9. 至少连续 7 次 dry-run 或手动运行无历史污染，再做 G5。
10. G5 接受后打 `v0.1.0-rc1`；观察期后再决定 `v0.1.0`。

---

## 15. 最终建议

这套体系的核心不是“让两个最强模型互相聊天”，而是让它们通过可验证工件合作：

```text
DeepSeek 负责产生候选变更
Git 负责冻结候选对象
测试负责提供可重复证据
Sol 负责独立判定是否满足契约
用户负责产品与高风险决策
```

当前最佳落地组合是：**腾讯云 WorkBuddy + DeepSeek V4 Flash 做 Executor，本地 Git 做控制面，Codex + GPT-5.6 Sol 做 Gate Reviewer。** Harness 保留为替换层，而不是在项目第一天同时引入第二套执行环境。这样最少操作、最容易审计，也不会把 OMDA 锁死在某个 Agent 产品里。

---

## 附录 A：开工前 60 秒检查表

- [ ] 当前模型确实是 DeepSeek V4 Flash（Executor）或 GPT-5.6 Sol（Reviewer）
- [ ] 当前仓库路径正确
- [ ] 当前 Gate 与分支正确
- [ ] 工作区状态已看过
- [ ] base SHA 与 candidate SHA 是完整值
- [ ] API key/Cookie 不在仓库
- [ ] 本轮 Prompt 只要求一个明确角色
- [ ] 测试结果来自实际运行
- [ ] Gate 未接受前不会进入下一 Gate
- [ ] 架构问题会转 ADR，不由 Executor 猜答案

## 附录 B：资料可靠性说明

本手册优先引用 DeepSeek 官方 API 文档和腾讯云 WorkBuddy 官方页面。第三方 Harness 仓库只用于说明同名与协议适配风险，不把其自述性能视为官方保证。工具版本变化较快，正式安装前应再次核对发布组织、包名、版本与变更日志。
