# ADR-0003 — Agent Skill Beta 与个人 Markdown 模式（Skill Distribution Beta）

- Status: **Proposed**（待 GPT-5.6 Sol 独立评审；Executor 不得自行改写为 Accepted）
- Date: 2026-09-18
- Gate: G6（Skill Distribution Beta）前置架构检查点
- 触发来源：Owner 产品决策（2026-09-18）——OMDA 暂不开发 Web Beta；第一轮朋友测试
  改为一个可分发给 Agent 使用的 OMDA Skill。Owner 设想的 Skill Beta 语义
  （"每天从用户明确提供的 Markdown 清单中发现一张专辑"）与现有正式核心
  （3 Genre × 3 Album、30-pick cooldown、curated 数据源 + SQLite 官方历史）
  不完全相同，因此按 SPEC §1.5 进入 **BLOCKED_ARCHITECTURE / ADR_PENDING**。
- 修改范围：本 ADR 只提出决策与建议，**不修改任何 production code、测试、
  模板资产或分发包**；G6 实施计划见 `governance/G6_SKILL_BETA_PLAN.md`
  （同属 Proposed，随本 ADR 一并评审）。

## 1. 背景与已核实事实

1. v0.1 正式核心已按 G0–G5 交付并接受（approved commit
   `3aa76ea5bb35e219550cf65328549de47c98269b`）：每次运行 3 个 Genre、
   每个 Genre 3 张 Album、Genre 30-pick cooldown、成功推荐 Album 永久排除、
   Genre 等机会选择、确定性引擎选择（ADR-0002 D8：deterministic/no-LLM
   runtime）、curated 数据源生产门禁（ADR-0002 D1/D6）、SQLite 官方历史。
2. Owner 决定：暂不开发 Web Beta；第一轮朋友测试改为分发一个 OMDA Skill。
   用户流程：阅读使用说明 → 准备个人音乐档案 Markdown → 提供一份探索清单
   Markdown（来自朋友/乐评人/社群/自己整理，或由 AI 按模板从既有歌单、乐评、
   聆听记录整理，未知信息必须留空）→ 交给支持 Skill 的 Agent → Agent 调用
   确定性脚本给出当天推荐。
3. Skill Beta 语义（一天一张、来自用户清单）与正式核心语义（一次 3×3、来自
   curated 数据包）不是同一产品语义。若直接修改 Recommendation Core 迎合
   Skill Beta，将违反 SPEC §1.4（不得静默重新解释契约）与 AGENTS.md
   不可协商规则；若把简化模式冒充完整 3×3 引擎，将违反"不得把简化模式
   冒充完整引擎"的架构边界。
4. 第一轮测试对象是朋友（非技术用户），分发物必须是"能快速打包、交给
   朋友试用"的文件集合；Web、音乐平台账号、Spotify/Apple Music API、
   在线服务器、Agent API 接入均不在本轮范围（Owner 明确排除）。
5. 仓库既有治理把 Executor 绑定为模型名 "DeepSeek V4 Flash"；
   该模型已不再可用，本轮实际执行环境为 WorkBuddy（见 §9 建议调整）。

## 2. 现有契约与冲突点

| 已接受契约 | 与 Skill Beta 的关系 |
|---|---|
| SPEC §2 产品常量（3/3/30/2010） | Skill Beta 是"一天一张"，不使用 3×3 常量；不得静默更改常量，也不得让 Skill 冒充 3×3 |
| SPEC §2.1 Genre 等机会、无 popularity 权重 | Skill Beta 必须继承"等机会、评分不加权"的精神（见 D8/D9） |
| SPEC §2.2 cooldown = 成功 pick 序号 ±30 | 该语义针对正式核心的 Genre 池；Skill Beta 的 Genre 池来自用户小清单，直接套用会使小清单在数日内全部进入 cooldown 而不可用（见 D8，属本 ADR 新定义，不改动正式核心） |
| SPEC §2.4 成功推荐 Album 永久排除、稳定 identity | Skill Beta 需要自己的永久排除历史（本地 JSON），与正式核心 SQLite 历史相互独立（D10） |
| SPEC §3.5 LLM 不决定 Genre/Album 集合 | Skill 中 Agent（LLM）只能整理资料与解释结果，不得替换确定性脚本的选择（D14） |
| SPEC §3.3 文本为真源、SQLite 仅 runtime | Skill Beta 的全部用户输入与历史均为本地文本/JSON，不引入 SQLite，不写入本仓库 tracked 数据 |
| AGENTS.md 角色分离 | Executor/Reviewer 职责不变；模型名绑定问题见 §9 建议 |

## 3. 方案比较

### 方案 A：Skill Beta 作为完整 3×3 Core 的包装器

- 让 Skill 调用 `omda.cli` / Recommendation Core，把用户清单适配成
  curated 数据源。
- 否决理由：①语义不符——用户要"一天一张"，核心产出 3×3；②数据契约不符——
  `CandidateBatch`/`GenreSourceDescriptor` 生产门禁（ADR-0002 D6）要求
  人工审核、许可 manifest、demo flag=false，用户随手整理的私人清单永远无法
  满足，导致 `--deliver` 永久 fail-closed；③隐私不符——用户私人档案会流入
  为开源社区设计的 curated 贡献路径；④需要修改 Core 或新增 ADR 级适配层，
  改动面最大，且把"个人模式"和"社区引擎"的历史/常量纠缠在一起。

### 方案 B：独立、清楚标记的 Skill Beta companion mode —— **推荐**

- 新建一个自包含的 Skill 分发包：确定性脚本 + 模板 + 说明，零第三方运行时
  依赖；不修改、不导入、不复用 Recommendation Core 与 SQLite 官方历史。
- 以固定命名与输出免责声明明确标记它是 "OMDA Skill Beta — Personal
  Markdown Mode"（companion mode），不是完整 3×3 引擎。
- 继承 OMDA 精神中与数据规模无关的部分：Genre 等机会、评分不影响选择、
  成功推荐永久排除、确定性可复现、AI 只解释不选择。
- 结论：**采用**。改动面最小、隐私边界清晰、不触碰已接受历史，且符合 Owner
  "第一版尽量简单、快速打包"的要求。

### 方案 C：维持现状，不做 Skill，等 Web Beta

- 与 Owner 决策直接冲突（Web Beta 暂停、先做朋友测试）。
- 结论：否决。

## 4. 决策

### D1 — Skill Beta 的定位：独立 companion mode

**决策：Skill Beta 是一个独立、清楚标记的 companion mode
（"OMDA Skill Beta — Personal Markdown Mode"），不是完整 OMDA 3×3 Core 的
包装器，也不是 3×3 引擎的简化配置。**

- 不修改 Recommendation Core、`src/omda/`、SQLite 官方历史或既有测试；
- 不共享 3×3 的常量、数据包、生产门禁与历史文件；
- 其输出必须带固定标记（见 D4），不得自称或被描述为"OMDA 3×3 推荐"。

### D2 — 为什么第一版选择 Skill 而不是 Web

- **分发成本**：Skill 是一组文件（Markdown + 一个脚本），可以 ZIP 直接发给
  朋友；Web 需要部署、域名、账号系统和在线服务器维护。
- **隐私边界**：Skill 天然本地运行（D15）；Web 第一天就要回答"数据放哪里"，
  与"本地使用默认"冲突。
- **零运行成本**：无服务器、无 API key、无平台账号（Spotify/Apple Music API
  均被 Owner 明确排除）。
- **借用用户已有的 Agent**：朋友已经在用支持 Skill 的 Agent（Codex、
  WorkBuddy 等）；Skill 把 OMDA 放进他们已有的日常入口。
- **可演进**：companion mode 的输入契约（两份 Markdown）未来可被 Web 或其他
  前端复用，不锁死路线。

### D3 — 第一版采用"一天一张专辑"

**决策：采用。** 每次调用最多产出 1 张 Album 推荐；推荐来源仅为用户提供的
`OMDA_COLLECTION.md` 清单；一天内重复调用返回同一结果（D11）。

### D4 — 如何明确说明它不等同于正式 3×3 引擎

1. **命名**：Skill 名称与所有文档统一使用
   `OMDA Skill Beta (Personal Markdown Mode)`；
   任何输出不得出现"OMDA 3×3 推荐"字样。
2. **固定免责声明**：每日输出的第一段固定为（中英双语或按用户语言）：

   > 本推荐来自 OMDA Skill Beta（个人 Markdown 模式）：一天一张、来自你自己
   > 提供的清单。它不是 OMDA 完整的 3 Genre × 3 Album 引擎，两者规则与历史
   > 互不通用。
   >
   > This recommendation comes from OMDA Skill Beta (Personal Markdown Mode):
   > one album per day, from a list you supplied. It is NOT the full OMDA
   > 3 Genre × 3 Album engine; the two share neither rules nor history.

3. **文档对照说明**：使用说明中包含一张对照表（3×3 引擎 vs Skill Beta：
   输出数量、数据来源、历史存储、cooldown 规则），防止误解。
4. **禁止混用**：Skill 脚本不得读写正式核心的 `var/omda.sqlite3`；
   正式核心不得读取 Skill 的历史文件。

### D5 — 两份 Markdown 输入的职责

| 文件 | 职责 | 所有者 |
|---|---|---|
| `OMDA_PROFILE.md` | 用户的音乐档案：地区/语言、喜欢的流派与年代、参考艺人、不想被推荐的类型、聆听目标等。**仅用于 AI 解释推荐时提供上下文，绝不参与选择算法**（脚本不读取它的任何字段来做筛选或加权）。 | 用户本人 |
| `OMDA_COLLECTION.md` | 音乐探索清单：一行（一表行）一张专辑，来自朋友、乐评人、社群或自己整理；是唯一的选择数据源。 | 用户提供 |

- 脚本对 `OMDA_PROFILE.md` 的唯一要求是"文件存在"（可全空）；
  选择算法只依赖 `OMDA_COLLECTION.md` 与本地历史文件。
- 这样设计的原因：档案是主观上下文，一旦进入选择路径就会变成隐蔽的
  popularity/偏好过滤器，违反等机会原则。

### D6 — 字段必填与可选

`OMDA_COLLECTION.md` 为 Markdown 表格，表头支持中英文或双语别名
（如 `Artist 艺人`、`Album 专辑`、`Year 年份`、`Genre 流派`、`Rating 评分`、
`Heard 已听`、`Skip 跳过`、`Note 备注`）。解析器接受英文表头、中文表头或
双语表头（别名映射表由 G6 实现时写入脚本并测试锁定）。

| 字段 | 必填 | 说明 |
|---|---|---|
| Artist | **必填** | 艺人名 |
| Album | **必填** | 专辑名 |
| Year | 可选 | 年份；缺失/未知留空，不得编造 |
| Genre | 可选 | 自由文本；为空归入"未分类（uncategorized）"分组；含分隔符时取第一个值作为分组键，展示保留原文 |
| Rating | 可选 | 任意文本；**仅展示，不参与选择**（D9） |
| Heard | 可选 | 是/否（接受 是/否、yes/no、true/false、x/空）；true = 已听过，排除（D10） |
| Skip | 可选 | 同上；true = 明确不想听，排除（D10） |
| Note | 可选 | 自由文本；**仅展示**（D9） |

`OMDA_PROFILE.md`：**无必填字段**（骨架模板全部可留空）。缺必填字段
（Artist 或 Album）的表行 → 校验失败并定位到行号，fail-closed，不猜测、
不编造、不跳过静默。

### D7 — 没有评分的清单完全有效

**决策：完全有效。** Rating 是可选字段；评分缺失不影响任何条目的资格、
机会或顺序。Skill Beta 的选择算法根本不读取评分（D9），因此"无评分清单"
与"有评分清单"在选择层面完全等价；评分只决定展示内容。

### D8 — Genre 先等机会选择，再在 Genre 内选择 Album

**决策：是。选择分两步，均为确定性：**

1. **Genre 等机会**：把清单条目按 Genre 分组键分组（含"未分类"组），对
   **有合格候选**的分组做等机会（均匀）抽样。分组出现与否、条目多少
   **不影响**分组的基础被选概率（同一分组不会因为专辑多而更容易被选中）。
2. **Genre 内选专辑**：在选中分组内，对合格条目（未听、未跳过、未在永久
   排除历史中）做等机会（均匀）确定性抽样，选出当天唯一一张。

**cooldown 处理（本 ADR 新定义，不改动正式核心）：**

- 正式核心的 30-pick cooldown 面向数千级 Genre 池；Skill Beta 的 Genre 池
  是朋友的小清单（可能只有 3–10 组）。若照搬"其后 30 个 pick 不可选"，
  小清单会在数日内全部进入 cooldown，模式直接不可用。
- **Skill Beta 采用自己的防重复规则：同一 Genre 分组不得在连续两个成功
  pick 中重复出现，除非它是唯一有合格候选的分组**（此时照常选择，并在
  输出中显式标注"唯一可用流派"）。
- 该差异是 companion mode 的显式设计，随 D4 的对照表向用户说明；
  **正式核心的 30-pick cooldown 语义一个字不改**。
- Genre 的长期机会均等仍由"等机会抽样 + 永久排除消耗"保证：清单耗尽是
  唯一的终点（D13）。

### D9 — 评分和备注只能展示，不得影响 Genre 机会

**决策：是。** Rating、Note、`OMDA_PROFILE.md` 全部字段：

- 不参与 Genre 分组的资格与机会；
- 不参与 Genre 内专辑的选择与排序；
- 不作为权重、过滤器或 tie-breaker；
- 仅出现在当日输出的展示区。

选择算法代码路径中不得出现对 rating/note/profile 字段的任何读取；
由 G6 测试矩阵以契约测试锁定（含"修改评分不改变选择结果"的回归测试）。

### D10 — 已听、跳过与历史推荐的排除

**决策：三类排除，全部确定性：**

1. **已听（Heard = true）**：从清单资格中排除；排除依据是清单文件本身的
   当前内容（用户改回 false 后次日可重新合格——这是用户对自己清单的主权，
   不是漏洞）。
2. **跳过（Skip = true）**：同上排除。
3. **历史推荐（永久排除）**：凡被 Skill Beta 成功推荐过（当日结果已写入
   本地历史，见 D12）的条目，按规范化身份键
   `normalize(artist) + "|" + normalize(album)`（NFC、小写、折叠空白、
   去首尾标点）永久排除。字符串规范化是本模式下唯一可用的身份方式
   （用户清单没有 MusicBrainz MBID）；规范化规则必须实现为纯函数并测试锁定；
   规范化歧义（同键不同原文）在输出中记录，不静默合并（见 D11 多清单冲突）。
- **与正式核心历史互不导入**：正式核心 SQLite 里已推荐的专辑**不**进入
  Skill Beta 排除集，反之亦然（两个模式历史独立，随 D4 说明）。
  该取舍是显式的：跨模式导入会引入用户无法核查的隐藏排除集。

### D11 — 同一天重复调用返回同一结果

**决策：**

- **day key = 本地日历日期**（`YYYY-MM-DD`）。选择"每天一张"的语义以用户
  本地日期为准（朋友语境）；历史记录同时保存带时区的 UTC ISO 8601 时间戳。
- 每次成功运行将当日结果写入本地历史（含 day key、选中条目的完整事实、
  分组键、seed、collection digest）并渲染当日输出文件
  `var/omda-skill/output/YYYY-MM-DD.md`。
- **同日重复调用：检测到历史中已有该 day key → 直接返回既有当日结果
  （重渲染同一文件），不重新抽样、不修改历史。** 用户当天修改清单或档案，
  变更从下一个 day key 生效（输出中提示）。
- **跨机器/跨 harness 的确定性**：抽样 seed 派生自
  `SHA-256(day_key + collection_digest + 已消耗 pick 数)`；相同输入文件 +
  相同历史进度必然得到相同选择，即使当日输出文件丢失也可从历史确定性
  重渲染。
- 同日语义不依赖"运行次数"，失败/中止的运行不消耗 day key（与"失败运行
  不污染历史"同构）。

### D12 — 历史文件：位置、格式、原子写入、损坏处理

- **位置**：默认 `<工作目录>/var/omda-skill/history.json`，可用
  `--history` 覆盖；`var/` 模式加入分发 ZIP 的说明（该目录不得进入任何
  Git 仓库或分享包）。
- **格式**：版本化 JSON：`{"schema_version": 1, "days": {...}}`，每天一条
  记录（day key、selected 事实、genre 分组键、seed、collection digest、
  selected_at UTC 时间戳）。schema 演进只能向前加版本，不删字段。
- **原子写入**：同目录写临时文件 + `os.replace()`；绝不就地覆写。
- **损坏处理：fail-closed**。解析失败、schema_version 未知或结构校验失败
  时：保留损坏副本（`history.corrupt-<timestamp>.json`）、拒绝运行并给出
  明确的人工恢复指引（从备份恢复或手工修复后重命名回来）。**绝不静默重置、
  绝不自动重建、绝不丢弃历史继续运行**——历史是永久排除承诺的唯一凭证。
- 每日输出文件丢失可从历史确定性重渲染（D11）；历史丢失则无法重渲染，
  因此历史是唯一需要备份的状态（说明文档写明）。

### D13 — 清单耗尽时的明确行为

**决策：显式报告，绝不回退。** 当不存在任何合格条目（全部已听/跳过/永久
排除）时：

- 输出明确信息："清单已耗尽：所有条目都已听过、跳过或已被推荐过。
  请向 OMDA_COLLECTION.md 添加新条目后明天再试。"（中英双语版本由模板固定）
- 脚本以非零退出码结束；Agent 只转述，不得自行补一张专辑、不得降低排除
  标准、不得从已听/已跳过条目中挑选。
- 部分耗尽（某些分组无合格条目）不触发整次失败：无合格候选的分组仅从
  当日 Genre 抽样池中排除（等机会定义在"有合格候选的分组"上，D8）。

### D14 — AI 在本流程中的权限

**允许：**

1. 按模板把用户提供的自由格式资料（歌单、乐评、聆听记录）整理成
   `OMDA_PROFILE.md` / `OMDA_COLLECTION.md`；**不知道的字段必须留空，
   不得编造**（整理 Prompt 由 G6 交付并包含此硬规则）；
2. 阅读脚本输出的确定性事实，结合 `OMDA_PROFILE.md` 解释/介绍当天推荐；
3. 协助用户安装、排障、修改清单格式。

**禁止：**

1. 替换、覆盖、重排或"优化"确定性脚本选出的 Album——**确定性脚本选择，
   AI 只解释**；
2. 绕过脚本直接从清单中"挑一张"充当推荐；
3. 编造清单中不存在的字段值（年份、评分、流派）；
4. 把评分/备注/档案变成选择依据（D9）；
5. 修改脚本的选择逻辑、历史文件或排除集；
6. 在未经用户明确操作下上传、公开发布或提交任何用户资料、清单、历史或输出
   （D15）。

AI 侧约束由分发说明（SKILL.md 与 README）声明；脚本侧由"AI 无法通过脚本
接口覆盖选择结果"保证（脚本无任何"指定结果"参数）。

### D15 — 本地隐私边界与公开贡献边界

- **默认全本地**：档案、清单、历史、输出只保存在用户本机；脚本零网络调用
  （D19、测试矩阵锁定）；分发包内不含任何用户数据。
- **本地使用 ≠ 同意公开贡献**：任何上传、公开分享、提交到 OMDA 开源仓库
  （如把清单整理成 curated 贡献包）都是**独立的、显式的用户动作**；
  Skill 与 AI 均不得默认执行，也不得在输出中暗示"会自动贡献"。
  说明文档明确写：*"如果你想把自己整理的清单贡献给 OMDA 社区数据包，
  那是一个单独的流程，需要你明确发起。"*（中英双语）
- **harness 提示**：Agent 平台自身可能上传对话上下文（遥测/云同步），这超出
  OMDA 控制范围；使用说明提醒用户注意其 Agent 平台的隐私政策，并给出
  "最小化档案内容"的建议。
- 不得把 `var/`、历史 JSON 或任何用户文件加入分发包或 Git。

### D16 — Skill 的可移植范围

**目标 harness：Codex、WorkBuddy，以及任何满足以下最小能力的 Agent
harness：**

1. 能读取并遵循 `SKILL.md` 指令（native skill 机制或人工粘贴均可）；
2. 能在工作目录读写文件（模板复制、脚本运行、输出读取）；
3. 能运行命令 `python3 scripts/daily_pick.py ...`（Python ≥ 3.9）。

- 脚本是**独立 CLI**，不依赖任何 harness 的 skill 加载机制、SDK 或
  网络服务；skill 机制只负责"把说明和脚本带到用户面前"。
- 所有文档与模板提供中英双语；脚本错误信息英文（便于跨环境排障），
  输出正文语言跟随模板/参数。

### D17 — 非 native Skill Agent 的兼容使用方法

**决策：脚本必须是可用 CLI，说明必须包含"无 Skill 机制"路径：**

1. 用户把分发 ZIP 解压到任意目录；
2. 用户把 `SKILL.md` 的内容**粘贴给 Agent 作为普通指令**（或自己阅读）；
3. 用户按 README 中的手动命令运行，例如：

   ```bash
   python3 scripts/daily_pick.py \
     --profile OMDA_PROFILE.md \
     --collection OMDA_COLLECTION.md \
     --history var/omda-skill/history.json \
     --output-dir var/omda-skill/output
   ```

4. Agent 读取输出 Markdown 并按其内容解释。

README 必须包含逐条的手动步骤（含 Windows/macOS/Linux 差异说明），
确保"没有 skill 加载器"不是使用障碍。

### D18 — 分发包应包含的文件

```text
omda-skill-beta/
├── SKILL.md                          # Agent 入口说明（中英双语）
├── README.md                         # 朋友使用说明（中英双语；含 D17 手动路径）
├── VERSION                           # 版本标识（如 0.1.0-beta.1）
├── LICENSES.md                       # 代码许可与第三方声明（Apache-2.0 沿用仓库决策）
├── scripts/
│   └── daily_pick.py                 # 唯一确定性脚本（标准库零依赖）
├── templates/
│   ├── OMDA_PROFILE.template.zh-CN.md
│   ├── OMDA_PROFILE.template.en.md
│   ├── OMDA_COLLECTION.template.zh-CN.md
│   └── OMDA_COLLECTION.template.en.md
├── prompts/
│   └── ORGANIZE_PROMPT.zh-CN.md / .en.md   # AI 整理资料用 Prompt（D14）
└── FEEDBACK_TEMPLATE.md              # 反馈模板（中英双语）
```

**明确排除**：任何用户数据、`var/`、历史 JSON、SQLite、`.git`、正式核心
代码、测试套件、node_modules/venv 等环境目录。ZIP 内容以 manifest 校验
（G6 测试矩阵锁定）。

### D19 — Python 标准库零运行时依赖

**决策：是。** `daily_pick.py` 只使用 Python 标准库
（`argparse`、`json`、`hashlib`、`random`、`pathlib`、`datetime`、
`tempfile`、`os`、`re`、`unicodedata`、`sys`）；不安装任何第三方包；
不使用任何网络模块（`socket`、`urllib`、`http` 等一律不得 import，
以静态检查 + 离线运行测试双重锁定）。目标 Python ≥ 3.9（覆盖朋友的常见
环境；避免 3.10+ 专属语法）。`random` 仅以 seed 派生的确定性用法使用
（`random.Random(seed)`），禁止全局随机状态。

### D20 — 明确推迟到后续版本

以下内容**不在本轮、也不在 Skill Beta v1 范围**（任何提前实现需新 ADR 或
Owner 决策）：

1. Web Beta、任何在线服务器与账号系统；
2. 音乐平台账号、Spotify / Apple Music / RYM API 接入；
3. Agent API 接入（把 OMDA 作为服务供其他 Agent 调用）；
4. 评分、热度、AI 判断参与任何选择/加权（永久禁止项，非"推迟"）；
5. Skill 与正式核心历史的互相导入；
6. 自动定时运行/调度（用户手动或由其 Agent 触发）；
7. 多语言扩展（超出中英）、多用户、云同步、协作清单；
8. 从 Skill 清单到社区 curated 贡献包的自动流水线（显式人工流程保留）；
9. MusicBrainz MBID 身份（用户清单无此数据；若未来清单模板支持 MBID，
   需修订本 ADR）；
10. 输出中调用外部 LLM 生成文案（解释由用户自己的 Agent 完成，脚本只出
    确定性事实）。

## 5. 角色定义调整建议（提出，不自行接受）

**以下为 Executor 提交给 Reviewer/Owner 的建议，未经接受前不修改
AGENTS.md / OPH / PROJECT_STATE schema 的既有语义：**

1. 执行角色绑定到 **`WorkBuddy Executor`**（角色标识），而不是永久绑定
   模型名 `deepseek-v4-flash`；DeepSeek V4 Flash 已不再可用。
2. **每一轮报告仍必须记录实际使用的模型**（本轮：GLM-5.3-Flash，
   经 WorkBuddy 执行）。
3. Reviewer 继续为独立的 **GPT-5.6 Sol**，不变。
4. **更换 Executor 模型不得改变架构权限与 Gate 规则**：EXECUTOR 仍然只能
   写到 `READY_FOR_REVIEW`，只有 Reviewer 可以置 `ACCEPTED`；权威顺序、
   反自引用规则、完成证据要求全部不变。
5. 若接受，落地动作是后续 commit 中对 `AGENTS.md` §Role separation、
   OPH §4.1、PROJECT_STATE `executor` 字段语义的文本修订（届时按正常
   Gate/ADR 流程提交，本轮不执行）。

本轮 PROJECT_STATE 中 `executor` 字段暂记为 `workbuddy-executor` 并新增
`executor_model` 字段记录实际模型——这是对现状的如实记录，不等同于
接受上述永久绑定调整；最终语义以本 ADR 评审结论为准。

## 6. 影响分析

- **正式核心**：零改动。`src/`、`tests/`、`data/`、`var/` 均不触碰；
  G0–G5 已接受历史与测试不受影响。
- **新增物（G6 实现阶段，均待本 ADR 接受后）**：`skill/` 目录（分发包内容，
  D18）、`governance/G6_SKILL_BETA_PLAN.md` 中的模板定稿、G6 测试矩阵。
  Skill 源文件建议置于仓库 `skill/`（或 `skill-beta/`）目录并在 G6 实现时
  确认，不放入 `src/omda/` 以免与正式核心混淆。
- **治理**：PROJECT_STATE 切换为 G6 / BLOCKED_ARCHITECTURE / ADR_PENDING；
  G6 实施计划为新增治理文档（Proposed）。
- **风险与缓解**：

| 风险 | 缓解 |
|---|---|
| 用户误以为拿到的是完整 3×3 引擎 | D4 固定免责声明 + 对照表 + 命名区分 |
| AI 越权替换选择 | D14 禁令 + 脚本无"指定结果"参数 + G6 测试（篡改输出 attempt 被检测） |
| 评分/档案变成隐蔽 popularity filter | D5/D9 脚本不读取这些字段 + 契约测试 |
| 历史损坏导致永久排除承诺失效 | D12 原子写 + fail-closed + 损坏副本保留 |
| 隐私外泄 | D15 本地默认 + 分发包 manifest 扫描 + 用户数据不入 ZIP/Git |
| 小清单被 cooldown 饿死 | D8 companion 专属防重复规则（显式偏离并标记） |
| 规范化身份误合并不同专辑 | D10 纯函数规范化 + 歧义记录 + 测试锁定 |

## 7. rollout / rollback

- **rollout**：① 本 ADR 与 G6 计划获接受 → ② G6 实现（skill/ 目录 + 脚本 +
  模板 + 说明 + 测试矩阵全绿）→ ③ G6 Reviewer checkpoint 接受 → ④ Owner
  授权后打包分发。ADR 接受不授权 merge/tag/分发。
- **rollback**：`git revert` G6 相关 commit 即可整体移除 Skill 分支产物；
  不触碰正式核心与既有历史；已分发副本由用户自行删除（本地文件，无服务端
  状态）。Skill 用户本地的 `var/omda-skill/` 数据属用户文件，任何清理由
  用户显式执行。
- **停止条件**：评审返回 REVISE / OWNER_DECISION_REQUIRED 时，Executor 仅
  修订文档并再次送审，不开始实现。

## 8. 验收测试设计（G6 实现，本 ADR 只定义）

对应 `governance/G6_SKILL_BETA_PLAN.md` 的完整测试矩阵，要点：

| # | 验收 | 设计 |
|---|---|---|
| AC-1 | 安装验证 | 干净目录解压 ZIP + 干净 Python ≥ 3.9 环境，按 README 手动路径完成首次推荐 |
| AC-2 | 连续两天推荐 | day 1 / day 2（伪造或 `--date` 注入第二天）各产出一张、互不相同且第二天不受前一天输出文件缺失影响 |
| AC-3 | 同日幂等 | 同一 day key 重复调用 N 次：结果字节级一致、历史记录数不变、无第二次抽样（seed 断言） |
| AC-4 | 已听/跳过排除 | Heard/Skip 条目永不被选；清单改标志后行为按 D10 变化 |
| AC-5 | 多清单去重与冲突 | 多个 `--collection` 合并：重复条目去重；heard/skip 冲突取最严格；字段冲突取首现并记录；规范化同键不同原文被记录不静默 |
| AC-6 | 中英表头 | 三种表头（英/中/双语）解析等价；未知表头 fail-closed 报列名 |
| AC-7 | 缺字段/损坏历史 | 缺 Artist/Album 的行定位报错；损坏历史保留副本 + 拒绝运行 + 零自动重建 |
| AC-8 | 零网络 | 静态 import 审计（禁 socket/urllib/http 等）+ 断网环境功能测试 |
| AC-9 | Secret/隐私扫描 | 分发包与输出中无 token/路径/个人数据；manifest 与目录清单一致 |
| AC-10 | Skill 结构 | SKILL.md frontmatter、目录结构、双语模板齐备 |
| AC-11 | ZIP 内容 | 仅含 D18 清单文件，排除项逐一断言不存在 |
| AC-12 | Codex 安装说明 | 按 SKILL.md 在 Codex 中可发现并执行（由 Owner/朋友实测并反馈，G6 记录证据） |
| AC-13 | 非 native 兼容 | D17 手动路径逐条可执行（无 skill 加载器环境验证） |
| AC-14 | 选择不受评分影响 | 修改 rating/note/profile 字段 → 同输入+同历史下选择结果不变（D9 回归锁定） |
| AC-15 | 耗尽行为 | 全部条目被排除 → 显式耗尽信息 + 非零退出 + 不回退 |

## 9. 需要 Reviewer / Owner 决定的问题

1. **D1 定位**：独立 companion mode 是否成立？（Executor 强烈推荐方案 B）
2. **D8 cooldown 偏离**：Skill Beta 用"连续 pick 防重复 + 唯一分组豁免"
   替代 30-pick cooldown，仅作用于 companion mode——是否接受？若不接受，
   备选是接受小清单数日不可用的后果，或由 Owner 给出其他规则。
3. **D11 同日语义**：本地日期作为 day key、当日锁定结果（清单修改次日生效）
   是否接受？
4. **D10 排除边界**：Heard/Skip 跟随清单当前内容（用户改回即恢复资格），
   而永久排除仅来自成功推荐——是否接受？
5. **§5 角色定义调整**：是否接受 Executor 绑定 `WorkBuddy Executor` 并逐轮
   记录实际模型？
6. **Skill 源目录位置**：`skill/` vs `skill-beta/`（Executor 建议
   `skill/`，G6 实现前定案即可）。

## 10. 引用

- Owner 决策记录（2026-09-18，本轮任务指令）。
- `docs/OMDA_AGENT_HANDOFF_SPEC.md` §1、§2、§3.5、§4、§9。
- `docs/OMDA_PROJECT_MASTER_PLAN_zh-CN.md` §3、§9。
- `docs/adr/0002-production-album-source-and-runtime-boundary.md` D6/D8
  （生产门禁与 no-LLM 边界——Skill Beta 不触碰、不绕过）。
- `governance/G6_SKILL_BETA_PLAN.md`（Proposed，随本 ADR 评审）。
- `governance/PROJECT_STATE.json`（本轮状态更新）。
- `reviews/adr/ADR_0003_EXECUTOR_HANDOFF.md`（Executor 交接报告）。
