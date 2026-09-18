# G6 实施计划 — Skill Distribution Beta（Approved v2）

> 状态：APPROVED FOR IMPLEMENTATION —— 与
> `docs/adr/0003-agent-skill-beta-and-personal-markdown-mode.md`（ADR-0003 v2，
> Accepted）绑定，并必须遵守其 §10 Reviewer acceptance constraints。此状态
> 不等于 G6 Gate 接受，也不授权 merge、tag、push、保留对外分发包或发布；
> T6.9 的隔离临时归档构建/解压仅作为测试执行并立即清理。
> 作者：WorkBuddy Executor（实际模型：GLM-5.3-Flash）
> 日期：2026-09-18（v2：同日，响应 Reviewer REVISE ADR3-001~006 与 Owner
> 多来源一等公民补充决定）
> 基线：`docs/OMDA_AGENT_HANDOFF_SPEC.md`、`docs/OMDA_PROJECT_MASTER_PLAN_zh-CN.md`、
> 已接受 ADR-0001/0002、`AGENTS.md`、已接受的 `governance/IMPLEMENTATION_PLAN.md`
> 本文件不修改、不弱化任何高层规范与 G0–G5 已接受产物；如冲突，高层优先。

---

## A. Gate 目标与非目标

### A.1 目标

交付一个**可分发给朋友的 OMDA Skill Beta 分发包**（Personal Markdown Mode，
companion mode；架构定位见 ADR-0003 D1/D4）：

- 用户准备 `profile/MY_PROFILE.md`（私人档案 + 结构化已听/跳过状态表）；
- 从 `sources/` 中每日选择一个或多个 **OMDA Source Markdown**（每位贡献者
  一份、可分享、只读）；
- Agent 调用确定性脚本 `daily_pick.py` → 得到当天 1 张专辑推荐
  （同日幂等、来源集合锁定）；
- 本地默认、零网络、零第三方运行时依赖（ADR-0003 D15/D19）。

### A.2 非目标（与 ADR-0003 D20 一致，任何提前实现需新 ADR）

Web Beta、音乐平台账号、Spotify/Apple Music API、在线服务器、Agent API
接入、多用户、云同步、自动调度、评分/热度/AI 参与选择、多来源评分组合
算法（仅预留格式与边界，D25）、Skill 与正式核心历史互通、把自由文本清单
自动转为社区 curated 贡献包。

### A.3 边界声明

- **不修改** `src/`、`tests/` 既有内容、`data/`、`var/`、G0–G5 已接受历史；
- Skill 源文件置于仓库 **`skills/omda-daily-discovery/`**（ADR-0003 D16，
  ADR3-004-1）；
- Skill 与正式核心互不导入、互不读写（ADR-0003 D4/D10）；
- 来源文件运行时**只读**；个人状态**永不写回来源**（ADR-0003 D5/D10/D21）。

---

## B. Atomic Tasks

每个任务按 OPH §8.2 固定循环执行：读状态 → 读相关规范 → 最小变更 →
自检 diff → commit。字段：Goal / 允许范围 / Deliverables / 验收（对应 §D
测试矩阵编号）/ Risks。

### T6.1 Skill 包结构与 SKILL.md

- Goal：建立 `skills/omda-daily-discovery/` 目录骨架与 Agent 入口说明。
- 允许范围：`SKILL.md`（frontmatter `name: omda-daily-discovery` + 有区分度
  description）、`agents/openai.yaml`（Codex 元数据/默认提示）、`VERSION`
  （Skill 独立版本 `0.1.0-beta.1`）、`LICENSE`（**完整 Apache-2.0 文本**）、
  `LICENSES.md`、目录骨架。
- Deliverables：SKILL.md 含安装步骤（native skill + 非 native 手动路径）、
  3×3 引擎 vs Skill Beta 对照表（D4-3）、多来源使用模型说明（D5/D21）、
  AI 权限清单（D14）、隐私与 sharing note 边界声明（D15）。
- 验收：AC-10、AC-28。
- Risks：harness frontmatter 格式差异——以最简通用字段为准，D17 手动路径兜底。

### T6.2 确定性脚本 `scripts/daily_pick.py`

- Goal：实现 ADR-0003 D6–D13、D19、D21–D25 的确定性选择、多来源融合与
  历史管理。唯一脚本、标准库零依赖、Python ≥ 3.9、零网络。
- 允许范围：`skills/omda-daily-discovery/scripts/daily_pick.py`（单文件
  自包含实现；**不**在 `src/omda/` 下新增任何文件）。
- Deliverables（功能清单）：
  1. **CLI**：`--profile profile/MY_PROFILE.md`、`--source sources/x.md`
     （**可重复**，至少一个；同一文件或同 `source_id` 重复 → fail-closed）、
     `--history`、`--output-dir`、`--template-dir`、`--lang`；
     **无 `--date` 或任何日期覆盖参数**——时钟经可导入 clock seam 注入，
     仅测试可达（AC-27）；
  2. **来源解析**：受限 OMDA flat frontmatter（每行一个标量 `key: value`；
     拒绝嵌套/序列/tag/anchor/alias/重复或未知字段；不是通用 YAML；字段为
     `source_id`/`display_name`/`curator`/
     `provenance`/`sharing_note`/可选 `rating_scale`/`format_version`，D22）；
     Album 表英/中/双语表头别名；全空行忽略、部分填充缺必填 fail-closed
     定位行号（AC-6/AC-7）；
  3. **两层资格模型**：个人 heard/skip 只读 profile 结构化 Album-status 表
     （同规范化契约）；永久排除读历史；来源文件只读（AC-4/AC-23）；
  4. **多来源内存融合（D21/D23）**：按规范化身份键去重（重复条目一个候选、
     概率不增，AC-20）；per-source rating/note/attribution 分别保留、按
     canonical 顺序并列展示（AC-21）；**selection-relevant 冲突（Genre）
     fail-closed**：报告身份键/来源/各自值，要求确认（AC-22）；合并池按
     规范化身份键稳定排序；
  5. **确定性协议（D19-3/§10 C1）**：source-content canonical
     representation（完整审计内容）→ per-source content digest；selection
     canonical projection（仅规范化 identity + 已解决 Genre，经资格/cooldown
     过滤）→ admissible selection-pool digest，且只有后者进入 seed；两种表示
     均为 NFC/UTF-8/稳定键序与记录序、无绝对路径；**版本化 uniform-index**
     （domain-separated SHA-256 +
     无偏 rejection/unranking，含 `algorithm_version`）；排列不变性
     （AC-19/AC-26）；
  6. **Genre 等机会 → Genre 内等机会**（D8），仅作用于当前 admissible 分组；
     连续 pick 防重复 + 唯一分组豁免（AC-2）；
  7. **提交点与同日语义（D11/D12）**：原子历史替换（temp + `os.replace`）
     = 官方 commit point；输出从已提交历史渲染/重渲染；同日重复调用与
     更换 `--source` → 返回已提交结果 + 原来源集合说明，零重抽（AC-3/AC-5）；
  8. **历史记录**：source_id 集合、per-source content digest（仅审计）、
     admissible selection-pool digest（seed 证据）、`algorithm_version`/schema version、day key +
     timezone/offset 证据、提交时间戳（渲染复用，无易变时间戳）（AC-25）；
  9. **损坏 fail-closed**：保留副本、拒绝运行、零自动重建（AC-7）；
  10. **耗尽**：显式信息 + 非零退出 + 不回退（AC-15）；
  11. 输出渲染：固定 Beta 免责声明（D4-2）+ 事实 + 多来源注记展示区
      （不参与选择，AC-14）；
  12. 错误信息英文含定位；退出码区分校验失败/冲突/耗尽/历史损坏。
- 明确禁止：白名单外任何 import（含 socket/urllib/http/subprocess/
  webbrowser，AC-8）；"指定结果"参数；读取 rating/note/profile 自由文本
  参与选择（AC-14）；任何来源文件写入（AC-23）。
- 验收：AC-2…AC-8、AC-14…AC-27。
- Risks：小清单/单来源/单条目边界——测试矩阵逐项覆盖。

### T6.3 模板资产（v2：Source 模板 + Profile 结构化状态表）

- Goal：交付 D5/D6/D22 定义的模板（即 §C.1–C.4 定稿基础）。
- 允许范围：`templates/` 下 4 个模板：
  `OMDA_SOURCE.template.zh-CN.md` / `.en.md`（含元数据头 + curator/sharing
  字段 + **表格外的 fenced 示例块** + **空的真实表格**）、
  `OMDA_PROFILE.template.zh-CN.md` / `.en.md`（自由文本区 + 结构化
  Album-status 表 + "只有状态表会真正排除"标注）。
- 规则：示例文本永不出现在活动表格（AC-29）；用户复制 Source 模板创建
  任意数量来源文件（D21-7）。
- 验收：AC-6、AC-29、AC-1。
- Risks：朋友手改表头——解析器对未知表头 fail-closed 报列名。

### T6.4 中英文使用说明（含 Codex 安装与非 native 兼容）

- Goal：`README.md`（双语分节）：目录结构（profile/sources/var）→ 准备
  文件 → 安装（Codex native skill 路径逐条 + WorkBuddy 路径）→ 非 native
  手动路径（D17 逐条命令，含多来源示例；Windows/macOS/Linux 差异）→ 每日
  使用流程 → 同日锁定行为说明 → 隐私边界与 sharing note 说明 → 备份
  （历史 JSON 是唯一需要备份的状态）→ 故障排查（耗尽/冲突 fail-closed/
  损坏历史/表头错误）。
- 验收：AC-1、AC-12、AC-13。
- Risks：Codex skill 导入 UI 可能变化——标注"以平台当前文档为准"。

### T6.5 AI 整理 Prompt（中英）

- Goal：交付 §C.5 定稿（`prompts/ORGANIZE_PROMPT.zh-CN.md` / `.en.md`）：
  用户把歌单/乐评/聆听记录交给自己的 AI，按模板整理成 **OMDA Source
  Markdown**（含元数据头，`source_id`/`provenance` 等由用户口述提供）。
- 硬规则（写入 Prompt 正文）：不知道的字段留空；不得编造；不替用户决定
  个人 heard/skip（那是 profile 的事，不属于来源文件）；输出须交用户确认
  后才投入使用；一次整理只产出一份来源文件，不合并多人内容。
- 验收：AC-10（结构齐备）；Prompt 效果由 Owner/朋友实测反馈（G6 记录）。

### T6.6 反馈模板

- Goal：`FEEDBACK_TEMPLATE.md`（双语，§C.6 定稿）：试用 7 天后填写；
  默认只存本地或由用户自愿发送（D15）。

### T6.7 中英文项目前言（v2：恢复完整结构 + Owner 语气）

- Goal：按 ADR3-006 恢复**完整前言结构**：OMDA 标题/全名 → "乐者，天地之
  和也" → 三个编号小节 → 结尾"为什么我想做 OMDA"；§C.7/C.8 为定稿基础。
- 硬要求：卡尔维诺感悟以 Owner 第一人称**转述**（不直接引用、不做
  "大多数推荐系统"式普适断言）；包含"信任的/陌生的/偶然遇到的/甚至不同意的"
  来源自由与审美多元论证（不上升为"音乐无高下"的普适宣言）；英文与中文
  **逐句语义对应**，不擅自扩大；技术性 Skill 对照/限制说明放在前言之外的
  独立小节（T6.1 对照表），不与前言混排。
- 附：**双语逐句意图对照 checklist**（§C.9），AC-30 的评审留痕格式。
- 验收：AC-30（对照 Owner 原稿逐句校订——Executor 无原稿全文，定稿需
  Owner 参与）。

### T6.8 测试矩阵执行与证据

- Goal：执行 §D 全部验证并保存真实输出（不得凭记忆撰写）。
- 允许范围：`skills/omda-daily-discovery/tests/`（脚本自测；位于分发包
  白名单之外）、`reviews/stage-06/TEST_RESULTS.txt`。
- 验收：§D 矩阵全绿；每 skip 必须披露理由（SPEC §7）。

### T6.9 打包、扫描与分发验证

- Goal：构建分发 ZIP（根 `omda-daily-discovery/`）并验证（AC-9/AC-11/
  AC-28）：**打包前验证源 Skill 结构；打包后验证解压产物**（manifest 由
  验证产生，非手写清单）；完整 LICENSE 在包内；secret/隐私扫描零命中；
  排除项（tests/、评审证据、用户数据、var/、.git、src/omda、环境目录）
  逐一断言不存在。
- 说明：**打包/分发动作仍需 Owner 在 G6 接受后明确授权**；G6 阶段只在
  隔离临时目录构建并立即校验，不放入仓库、不发布。

### T6.10 G6 报告与状态更新

- Goal：`reviews/stage-06/EXECUTOR_REPORT.md`（OPH §10 模板）+
  PROJECT_STATE 更新为 READY_FOR_REVIEW；停止，等待 Reviewer。

---

## C. 模板与文档草稿（G6 实现时定稿；本节为交付物定义）

### C.1 `OMDA_PROFILE.template.zh-CN.md`

```markdown
# 我的 OMDA 档案

> 这是你的私人档案。除"已听 / 跳过记录"外，全部字段都可以留空；不知道的
> 不要编。档案只保存在你本地；除非你主动分享，任何内容都不会被上传。

## 关于我
- 常住地区 / 常用语言：
- 一句话介绍你的听歌经历：

## 我喜欢的（只帮 AI 向你解释，不影响选择）
- 喜欢的流派或风格：
- 喜欢的年代：
- 喜欢的艺人（几个即可）：
- 最近常听的专辑：

## 我的边界（可选）
- 不想被推荐的类型：
- ⚠️ 注意：这一段只是给 AI 的解释上下文。**只有下面"已听 / 跳过记录"
  表格里的条目会被真正排除出选择。** 想排除某张专辑，请在下表加一行。

## 已听 / 跳过记录（OMDA 唯一会读取的表格）
> Status 填 heard（已听）或 skip（明确不想被推荐）。Artist 和 Album 必填。

| Artist 艺人 | Album 专辑 | Status 状态 | Note 备注 |
|---|---|---|---|
```

### C.2 `OMDA_PROFILE.template.en.md`

```markdown
# My OMDA Profile

> This is your private profile. Every field outside the "Heard / Skip log"
> is optional — leave anything you don't know blank; never make it up.
> The profile stays on your machine; nothing is uploaded unless you
> explicitly share it.

## About me
- Where you live / languages you use:
- One sentence about your listening history:

## What I like (explanation context only — it never influences the pick)
- Genres or styles I enjoy:
- Eras I enjoy:
- A few favorite artists:
- Albums I have been listening to lately:

## My boundaries (optional)
- Types of music I do NOT want recommended:
- ⚠️ Note: this section is context for the AI's explanations only. **Only
  rows in the "Heard / Skip log" table below are actually excluded from
  the pick.** To exclude an album, add a row to that table.

## Heard / Skip log (the only table OMDA reads)
> Status is `heard` or `skip`. Artist and Album are required.

| Artist | Album | Status | Note |
|---|---|---|---|
```

### C.3 `OMDA_SOURCE.template.zh-CN.md`（用户可复制任意份）

```markdown
---
format_version: 1
source_id: alice
display_name: Alice 的私藏清单
curator: Alice
provenance: 朋友手写推荐（2026-06）
sharing_note: 仅限私人分享，请勿公开转载
rating_scale: 10-point
---

# Alice 的私藏清单

> 这是"OMDA 来源清单"：每行一张专辑，可原样分享给任何 OMDA 用户；系统
> 运行时只读，不会改写本文件。你的"已听/跳过"属于你自己的 Profile，
> 不要写在这里。
> Artist 和 Album 必填；其余不确定就留空，不要编造。
> 评分和备注只会展示（并注明来自本清单），不会影响每天选哪张专辑。
> 请不要修改表头行；全空行会被忽略。

| Artist 艺人 | Album 专辑 | Year 年份 | Genre 流派 | Rating 评分 | Note 备注 |
|---|---|---|---|---|---|

<details>
<summary>示例（仅供参考，不要放进上面的表格）</summary>

| Artist 艺人 | Album 专辑 | Year 年份 | Genre 流派 | Rating 评分 | Note 备注 |
|---|---|---|---|---|---|
| 坂本龙一 | async | 2017 | 环境音乐 | 9 | 适合深夜 |

</details>
```

### C.4 `OMDA_SOURCE.template.en.md`（copy freely, one per source）

```markdown
---
format_version: 1
source_id: alice
display_name: Alice's picks
curator: Alice
provenance: handwritten friend recommendations (2026-06)
sharing_note: private sharing only; do not republish
rating_scale: 10-point
---

# Alice's picks

> This is an "OMDA Source Markdown": one album per row, shareable as-is
> with any OMDA user. The system reads it at runtime and never rewrites it.
> Your personal heard/skip state belongs to YOUR profile — do not add it
> here.
> Artist and Album are required; leave anything you are not sure about
> blank — never make it up.
> Rating and Note are display-only (attributed to this source) and never
> influence the daily pick.
> Do not modify the header row; fully blank rows are ignored.

| Artist | Album | Year | Genre | Rating | Note |
|---|---|---|---|---|---|

<details>
<summary>Example (for reference only — do NOT put it in the table above)</summary>

| Artist | Album | Year | Genre | Rating | Note |
|---|---|---|---|---|---|
| Ryuichi Sakamoto | async | 2017 | ambient | 9 | great at night |

</details>
```

### C.5 AI 整理 Prompt（`ORGANIZE_PROMPT.zh-CN.md` 定稿基础）

```markdown
请把我提供的音乐资料整理成一份 OMDA 来源清单（OMDA Source Markdown）。

规则（必须遵守）：
1. 一次只整理**一位**整理者/来源的资料，产出**一份**来源文件；不要把多个
   人的内容合并进一份清单。
2. 只使用我提供的资料里真实出现的信息；不知道的字段一律留空，不得编造、
   不得推测（除非我明确要求并提供了来源）。
3. 先按模板填写受限 OMDA flat frontmatter：source_id（我指定的唯一短标识）、
   display_name、curator、provenance、sharing_note 由我口述提供；
   rating_scale 只有该来源确有评分时才填。
4. Album 表：完整复制模板表头行，一行一张专辑。Artist 和 Album 必填；
   Year、Genre、Rating、Note 尽量填，不确定就留空。
5. **不要**写任何"已听/跳过"个人状态——那属于我自己的 Profile 文件，
   不属于来源清单。
6. Rating 保留来源资料的原始表述，不要换算或打分；Note 可摘录一句短评并
   注明出处。
7. 整理完成后交给我确认；未经我确认不要提交给任何工具或上传。

我的资料如下：
（在此粘贴某一位朋友/乐评人/社群/自己的歌单、乐评、聆听记录等）
```

英文版（`.en.md`）为上述规则的逐条对应翻译（G6 定稿时逐句核对，不增删）。

### C.6 反馈模板（`FEEDBACK_TEMPLATE.md`，双语同文件分节）

```markdown
# OMDA Skill Beta 反馈（试用一周后填写）

- 使用了几天：
- 用了哪几个来源清单：
- 每天真的会看推荐吗：（是 / 大多数时候 / 经常忘记）
- 推荐里有几张你想真的去听：
- 最惊喜的一张：
- 最不想要的一类：
- 哪一步最麻烦：（准备档案 / 准备来源清单 / 让 Agent 运行 / 其他）
- 你愿意继续用吗：
- 给作者的一句话：

（本反馈默认只保存在你本地或由你自愿发给作者；OMDA 不会自动收集。）

# OMDA Skill Beta Feedback (after one week of use)

- Days used:
- Which source lists did you use:
- Did you actually check the daily pick: (yes / most days / often forgot)
- How many picks did you actually want to listen to:
- Most surprising pick:
- Least wanted kind of pick:
- Which step was most annoying: (profile / source lists / running the agent / other)
- Will you keep using it:
- One sentence for the author:

(This feedback stays local or is sent to the author by you voluntarily;
OMDA never collects it automatically.)
```

### C.7 项目前言（中文定稿基础；v2 恢复完整结构）

```markdown
# OMDA — Open Music Discovery Agent（每日音乐探索代理）

"乐者，天地之和也。"

1. OMDA 帮你每天遇见一张值得认真听的专辑。它不猜你喜欢什么，而是从你自己
   选择的来源清单里，用确定性的规则做出当天的选择，并附上一份你可以核查
   的说明。
2. 它的规则刻意朴素：每个流派有同样的机会；评分和热闹程度不决定什么
   更重要；推荐过的专辑不再重复；失败的运行不会弄脏任何记录。
3. 它默认一切都发生在你的电脑上：档案、来源清单和历史只保存在本地；
   除非你明确分享，什么都不会上传。

## 为什么我想做 OMDA

读了卡尔维诺的《为什么读经典》之后，我有一种说不清但很确定的感觉：一件
作品真正属于你，往往不是因为你去找了它，而是它在某个具体的时刻偶然遇上
了此刻的你。我想让 OMDA 做的，就是多创造一点这样的偶遇。

我也想保留使用清单的自由：它可以从我信任的朋友那里来，也可以来自陌生的
人、偶然碰到的社群，甚至来自我并不完全同意的乐评人——审美本来就是多元
的，它由文化、经历和偏好共同塑造，没有谁的清单有资格替我划线。OMDA 不替
我判断什么音乐"更好"；它只是每天认真地把一张专辑带到我面前，剩下的交给
我自己的耳朵。

Skill Beta 是这件事最小的一个开始：你自己的档案、几份你选择的来源清单、
一天一张专辑，其余的交给相遇。
```

### C.8 项目前言（英文定稿基础；与 C.7 逐句对应）

```markdown
# OMDA — Open Music Discovery Agent

"As music, so the harmony of heaven and earth."（乐者，天地之和也。）

1. OMDA helps you encounter one album worth serious listening every day.
   It does not guess what you like; it applies deterministic rules to the
   source lists you have chosen, makes the day's pick, and gives you an
   explanation you can check.
2. Its rules are deliberately plain: every genre gets an equal chance;
   ratings and popularity do not decide what matters more; recommended
   albums never repeat; failed runs never contaminate any record.
3. By default everything happens on your computer: your profile, source
   lists, and history stay local; unless you explicitly share them,
   nothing is uploaded.

## Why I wanted to build OMDA

After reading Italo Calvino's *Why Read the Classics?*, I was left with a
feeling I cannot fully explain but am sure of: a work truly becomes yours
not because you went looking for it, but because it happened to meet you,
at that particular moment, as the person you were. What I want OMDA to do
is create a little more of that kind of encounter.

I also want to keep the freedom to choose whose lists I use: they can come
from friends I trust, from strangers, from communities I stumbled upon, or
even from critics I do not fully agree with — taste is plural, shaped by
culture, experience, and preference, and no one's list has the standing to
draw the line for me. OMDA does not judge for me which music is "better";
it simply brings one album to me, carefully, each day, and leaves the rest
to my own ears.

Skill Beta is the smallest possible start: your own profile, a few source
lists you chose, one album a day — and the rest left to the encounter.
```

### C.9 双语逐句意图对照 checklist（AC-30 留痕格式）

```markdown
| # | 中文句（摘要） | 英文句（摘要） | 意图一致 | 备注 |
|---|---|---|---|---|
| 1 | 标题/全名 | Title/full name | ☐ | |
| 2 | 乐者天地之和也 | rendered epigraph | ☐ | 保留原典出处说明 |
| 3-5 | 编号小节 1/2/3 | numbered sections 1/2/3 | ☐ | 逐句核对 |
| 6-9 | 为什么我想做 OMDA 各句 | Why-section sentences | ☐ | Owner 原稿为准 |
```

> 定稿要求：以 Owner 原稿逐句校订后勾选；Executor 起草稿不视为通过 AC-30。

---

## D. 测试矩阵（G6 验收标准；编号对应 ADR-0003 §8 AC-1…AC-30）

| # | 验证项 | 方法 | 证据位置（G6 报告阶段） |
|---|---|---|---|
| V-1/AC-1 | 安装验证 | 干净目录 + 干净 Python ≥ 3.9：解压、按 README 手动路径（多来源）完成首次推荐 | §install |
| V-2/AC-2 | 连续两天推荐 | day1/day2（clock seam）各一张、不同；day2 不依赖 day1 输出文件 | §two-day |
| V-3/AC-3 | 同日幂等 | 同 day key 重复 ≥3 次：字节级一致、历史不变、抽样一次 | §idempotency |
| V-4/AC-4 | 个人状态排除 | profile 状态表 heard/skip 不被选；变更只改资格 | §exclusion |
| V-5/AC-5 | 同日来源集合锁定 | 提交后换 `--source` → 返回已提交结果 + 原来源集合；零重抽零历史变更 | §source-lock |
| V-6/AC-6 | 中英表头与元数据 | 三种表头解析等价；缺元数据/format_version 未知 fail-closed 定位 | §headers |
| V-7/AC-7 | 缺字段/损坏历史 | 部分填充行定位报错、全空行忽略；损坏历史保留副本 + 拒绝 + 零重建 | §malformed |
| V-8/AC-8 | 零网络（import 白名单） | 白名单审计（禁 socket/urllib/http/subprocess/webbrowser 等）+ 断网运行 | §no-network |
| V-9/AC-9 | Secret/隐私扫描 | 扫描分发包与输出：无 token/key/个人数据/本机路径 | §scan |
| V-10/AC-10 | Skill 结构 | frontmatter name、agents/openai.yaml、目录、双语模板齐备 | §structure |
| V-11/AC-11 | ZIP 内容 | 白名单 + 解压产物自动验证；排除项逐一断言不存在 | §zip |
| V-12/AC-12 | Codex 安装说明 | 按 SKILL.md/openai.yaml 在 Codex 可发现并执行（实测或显式披露） | §codex |
| V-13/AC-13 | 非 native 兼容 | D17 手动路径（多来源）逐条可执行 | §compat |
| V-14/AC-14 | 展示/审计字段不影响选择 | 修改 rating/note/year/display 元数据/profile 自由文本 → content digest 可变，但 selection-pool digest 与选择不变；状态表变更只改资格 | §no-rating-effect |
| V-15/AC-15 | 耗尽行为 | 全排除 → 显式信息 + 非零退出 + 零回退 | §exhausted |
| V-16/AC-16 | 崩溃矩阵（扩展） | 历史提交前/后、输出替换前/后四类崩溃点：不产生两张当日推荐；历史失败不报成功 | §crash |
| V-17/AC-17 | 单来源 | 单一 `--source` 全流程可用 | §single-source |
| V-18/AC-18 | 多来源 | 多 `--source` 合并池可用；输出按来源标注归属 | §multi-source |
| V-19/AC-19 | 来源顺序确定性 | `--source` 顺序与文件行序排列 → digest 与选择不变 | §permutation |
| V-20/AC-20 | 重复 Album 不增概率 | 同 Album 多来源出现 → 候选去重为一；添加只含重复条目的来源不改变 selection-pool digest 与选择 | §dedup-prob |
| V-21/AC-21 | 来源意见分别保留 | 同 Album 多来源 rating/note/attribution 并列展示、无平均/覆盖 | §opinions |
| V-22/AC-22 | Genre 冲突 fail-closed | 同身份键不同 Genre → 失败、报告冲突详情、零选择零历史变更 | §genre-conflict |
| V-23/AC-23 | 来源只读与多用户共享 | 同组来源 + 两个不同 profile/历史 → 来源文件字节不变；共享无需修改 | §sources-readonly |
| V-24/AC-24 | 无评分来源完全有效 | 全来源无评分 → 与有评分流程等价 | §no-rating-valid |
| V-25/AC-25 | 历史来源证据 | 记录含 source_id 集合/per-source content digest/selection-pool digest/版本/timezone；content digest 不进 seed | §history-evidence |
| V-26/AC-26 | 跨版本/平台复现 | digest 与选择向量 fixtures 跨受支持 Python 版本/平台一致；排列遵循文档规则 | §cross-version |
| V-27/AC-27 | 无任意日期覆盖 | 公共 CLI 无日期参数；clock seam 仅测试可达 | §no-date-override |
| V-28/AC-28 | 许可完整 | ZIP 含完整 Apache-2.0 LICENSE + LICENSES.md；Skill 版本独立 | §license |
| V-29/AC-29 | 纯净模板零候选 | 全新模板通过校验、零候选；示例块文本永不能成为推荐 | §pristine-template |
| V-30/AC-30 | 双语前言逐句对照 | 按 §C.9 checklist 对照 Owner 原稿逐句校订并留痕 | §preface-review |

规则：失败测试不得删除/弱化/无理由跳过（SPEC §7）；live 网络一律不用；
测试位于分发包白名单之外（ADR3-004-5）。

---

## E. 安装与分发验证要求（汇总）

1. **Codex 安装说明**（T6.4）：逐条步骤 + "以平台当前文档为准"注记 + 手动
   路径兜底；验证 = V-12。
2. **非 native Skill Agent 兼容说明**（T6.4/D17）：粘贴 SKILL.md + 手动 CLI
   命令（含多来源）+ 三平台差异；验证 = V-13。
3. **可分发 ZIP 内容验证**（T6.9/D18）：打包前验证源结构 + 打包后验证解压
   产物；完整 LICENSE；验证 = V-11/V-28。

## F. 回滚与停止条件

- G6 全部产物位于 `skills/omda-daily-discovery/`、本计划、
  `reviews/stage-06/`，`git revert` 可整体回退，不触碰正式核心。
- ADR-0003 已接受，允许开始 T6.1–T6.10；实现必须遵守 ADR §10，完成后只写
  READY_FOR_REVIEW 并停止；分发动作需 Owner 在 G6 接受后明确授权。

## G. 风险登记（G6，v2 更新）

| ID | 风险 | 级别 | 缓解 |
|---|---|---|---|
| R-6-1 | 朋友误认为 Skill = 完整 3×3 引擎 | P1 | D4 免责声明 + 对照表（V-10） |
| R-6-2 | AI 越权替换选择/改写来源 | P1 | D14 禁令 + 无指定结果参数 + 来源只读（V-23） |
| R-6-3 | 历史损坏破坏永久排除承诺 | P1 | 原子写 + fail-closed + 损坏副本（V-7/V-16） |
| R-6-4 | 规范化身份误合并 / 跨来源冲突静默任选 | P1 | 纯函数规范化 + Genre 冲突 fail-closed（V-21/V-22） |
| R-6-5 | 用户数据进入分发包/Git | P0 | 白名单 + 打包后解压验证 + 扫描（V-9/V-11） |
| R-6-6 | harness 遥测超出 OMDA 控制 | P2 | D15 说明文档提示用户注意平台隐私政策 |
| R-6-7 | Codex/WorkBuddy skill 机制变化 | P2 | 手动路径始终可用（V-13） |
| R-6-8 | 跨 Python 版本/平台不可复现 | P1 | 版本化 uniform-index + canonical 表示 + fixtures（V-19/V-26） |
| R-6-9 | 同日通过换来源重抽（reroll 通道） | P1 | 同日来源集合锁定 + 无日期覆盖（V-5/V-27） |
| R-6-10 | 前言偏离 Owner 语气/结构 | P2 | 完整结构恢复 + §C.9 逐句 checklist + Owner 校订（V-30） |
