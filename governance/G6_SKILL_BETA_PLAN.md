# G6 实施计划 — Skill Distribution Beta（Proposed）

> 状态：PROPOSED —— 待 GPT-5.6 Sol 评审；与 `docs/adr/0003-agent-skill-beta-and-personal-markdown-mode.md`
> （ADR-0003，Proposed）绑定，ADR 未接受前不得开始本计划任何实现任务。
> 作者：WorkBuddy Executor（实际模型：GLM-5.3-Flash）
> 日期：2026-09-18
> 基线：`docs/OMDA_AGENT_HANDOFF_SPEC.md`、`docs/OMDA_PROJECT_MASTER_PLAN_zh-CN.md`、
> 已接受 ADR-0001/0002、`AGENTS.md`、已接受的 `governance/IMPLEMENTATION_PLAN.md`
> 本文件不修改、不弱化任何高层规范与 G0–G5 已接受产物；如冲突，高层优先。

---

## A. Gate 目标与非目标

### A.1 目标

交付一个**可分发给朋友的 OMDA Skill Beta 分发包**（Personal Markdown Mode，
companion mode；架构定位见 ADR-0003 D1/D4）：

- 用户阅读中英使用说明 → 准备 `OMDA_PROFILE.md` 与 `OMDA_COLLECTION.md`
  → 交给支持 Skill 的 Agent → Agent 调用确定性脚本 `daily_pick.py`
  → 得到当天 1 张专辑推荐（同日幂等）。
- 本地默认、零网络、零第三方运行时依赖（ADR-0003 D15/D19）。

### A.2 非目标（与 ADR-0003 D20 一致，任何提前实现需新 ADR）

Web Beta、音乐平台账号、Spotify/Apple Music API、在线服务器、Agent API
接入、多用户、云同步、自动调度、评分/热度/AI 参与选择、Skill 与正式核心
历史互通、把自由文本清单自动转为社区 curated 贡献包。

### A.3 边界声明

- **不修改** `src/`、`tests/` 既有内容、`data/`、`var/`、G0–G5 已接受历史；
- Skill 源文件置于仓库 `skill/` 目录（ADR-0003 §9-6 待定案项）；
- Skill 与正式核心互不导入、互不读写（ADR-0003 D4/D10）。

---

## B. Atomic Tasks

每个任务按 OPH §8.2 固定循环执行：读状态 → 读相关规范 → 最小变更 →
自检 diff → commit。字段：Goal / 允许范围 / Deliverables / 验收（对应 §D
测试矩阵编号）/ Risks。

### T6.1 Skill 包结构与 SKILL.md

- Goal：建立 `skill/` 目录骨架与 Agent 入口说明。
- 允许范围：`skill/SKILL.md`、`skill/VERSION`、`skill/LICENSES.md`、目录骨架。
- Deliverables：SKILL.md 含 frontmatter（name、description，兼容 Codex/
  WorkBuddy skill 惯例）、安装步骤（native skill + 非 native 手动路径）、
  3×3 引擎 vs Skill Beta 对照表（ADR-0003 D4-3）、AI 权限清单（D14）、
  隐私声明（D15）。
- 验收：AC-10。
- Risks：harness frontmatter 格式差异——以最简通用字段为准，D17 手动路径兜底。

### T6.2 确定性脚本 `scripts/daily_pick.py`

- Goal：实现 ADR-0003 D6–D13、D19 的确定性选择与历史管理。唯一脚本、
  标准库零依赖、Python ≥ 3.9、零网络。
- 允许范围：`skill/scripts/daily_pick.py`（及同目录必要的 `__init__` 或
  单文件自包含实现；**不**在 `src/omda/` 下新增任何文件）。
- Deliverables（功能清单）：
  1. CLI：`--profile`、`--collection`（可多次，多清单合并）、`--history`、
     `--output-dir`、`--template-dir`、`--date`（仅测试注入）、`--lang`
     （zh/en 输出语言，默认 zh）；
  2. 表头别名解析（英/中/双语；AC-6）与行级校验（缺 Artist/Album 定位报错，
     fail-closed，AC-7）；
  3. Heard/Skip 排除、永久排除历史、规范化身份键纯函数（D10，AC-4）；
  4. 多清单合并去重与冲突规则：heard/skip 冲突取最严格；year/genre/rating/
     note 冲突取首现值并在输出附冲突记录；同键不同原文记录不静默（AC-5）；
  5. Genre 等机会抽样 → Genre 内等机会抽样（D8），seed =
     `SHA-256(day_key + collection_digest + consumed_pick_count)`，
     `random.Random(seed)`（AC-2/AC-3）；
  6. 同日幂等：day key 命中历史 → 重渲染同一结果，不重抽样（AC-3）；
  7. 输出渲染：固定 Beta 免责声明（D4-2）+ 选中条目事实 + rating/note
     展示区（不参与选择，AC-14 锁定）；
  8. 历史：版本化 JSON、临时文件 + `os.replace` 原子写、损坏 fail-closed
     保留副本（D12，AC-7）；
  9. 耗尽：显式信息 + 非零退出 + 不回退（D13，AC-15）；
  10. 错误信息英文、含定位；退出码区分校验失败/耗尽/历史损坏。
- 明确禁止：任何网络模块 import（AC-8 静态审计）；任何"指定结果/跳过选择"
  参数；读取 rating/note/profile 参与选择（AC-14）。
- 验收：AC-2、AC-3、AC-4、AC-5、AC-6、AC-7、AC-8、AC-14、AC-15。
- Risks：小清单边界情形（单一分组、单条目、全部同组）——测试矩阵逐项覆盖。

### T6.3 中英文模板资产

- Goal：交付 D5/D6 定义的两份输入模板（中英各一），即本计划 §C.1–§C.4
  草稿的定稿。
- 允许范围：`skill/templates/` 下 4 个模板文件。
- 验收：AC-6（表头可解析）、AC-1（随安装验证可用）。
- Risks：朋友手改表格破坏结构——模板内嵌"不要改表头行"提示；解析器对
  未知表头 fail-closed 报列名。

### T6.4 中英文使用说明（含 Codex 安装与非 native 兼容）

- Goal：`skill/README.md`（中英双语，分节）：准备文件 → 安装（native skill
  路径：Codex 导入步骤逐条；WorkBuddy 路径）→ 非 native Agent 手动路径
  （D17 逐条命令，Windows/macOS/Linux 差异）→ 每日使用流程 → 隐私边界 →
  备份（历史 JSON 是唯一需要备份的状态，D12）→ 故障排查（耗尽/损坏历史/
  表头错误）。
- 验收：AC-1、AC-12、AC-13。
- Risks：Codex skill 导入 UI 可能变化——README 标注"以平台当前文档为准"，
  手动路径始终可用。

### T6.5 AI 整理 Prompt（中英）

- Goal：交付 §C.5 草稿定稿（`skill/prompts/ORGANIZE_PROMPT.zh-CN.md` /
  `.en.md`）：用户把歌单/乐评/聆听记录交给自己的 AI，按模板整理成
  OMDA Markdown。
- 硬规则（写入 Prompt 正文）：不知道的字段留空；不得编造；不得替用户决定
  Heard/Skip（不确定就留空）；输出必须是合法模板表格；整理结果需交还用户
  确认后才投入使用。
- 验收：AC-10（结构齐备）；Prompt 效果由 Owner/朋友实测反馈（G6 记录）。

### T6.6 反馈模板

- Goal：`skill/FEEDBACK_TEMPLATE.md`（中英双语，§C.6 定稿）：朋友试用 7 天
  后填写；内容仅经用户自愿分享，默认不上传（D15）。

### T6.7 中英文项目前言（"为什么我想做 OMDA"修订版）

- Goal：按 Owner 要求，把卡尔维诺《为什么读经典》、偶然相遇与审美多元性
  自然整合进项目前言；英文与中文含义严格对应，不擅自扩大为宏大宣言。
- 允许范围：本计划 §C.7/§C.8 草稿定稿，随 G6 实现放入
  `skill/README.md` 开头（及未来主 README 修订时的对应段落——主 README
  修订不在本轮，届时单独 commit 送审）。
- 验收：中英对照评审（Reviewer 逐句核对语义对应）；AC-10。

### T6.8 测试矩阵执行与证据

- Goal：执行 §D 全部验证并保存真实输出（不得凭记忆撰写）。
- 允许范围：`skill/tests/`（脚本自测用例，独立于正式核心 `tests/`）、
  `reviews/stage-06/TEST_RESULTS.txt`（G6 报告阶段）。
- 验收：§D 矩阵全绿；每 skip 必须披露理由（SPEC §7）。

### T6.9 打包、扫描与分发验证

- Goal：构建分发 ZIP 并验证内容（AC-9/AC-11）；secret/隐私扫描零命中；
  manifest 与实际内容一致；确认排除项（用户数据、var/、.git、正式核心
  产物）不存在。
- 说明：**打包/分发动作本身仍需 Owner 在 G6 接受后明确授权**（AGENTS.md
  停止条件）；G6 阶段只验证"可打包"，在隔离临时目录构建并立即校验，
  不放入仓库、不发布。

### T6.10 G6 报告与状态更新

- Goal：`reviews/stage-06/EXECUTOR_REPORT.md`（OPH §10 模板）+
  PROJECT_STATE 更新为 READY_FOR_REVIEW；停止，等待 Reviewer。

---

## C. 模板与文档草稿（G6 实现时定稿；本节为交付物定义）

### C.1 `OMDA_PROFILE.template.zh-CN.md`

```markdown
# OMDA 音乐档案

> 这是你的个人音乐档案。所有字段都可以留空；不知道的不要编。
> OMDA 只在本地读取这个文件；除非你主动分享，任何内容都不会被上传。
> 档案只用来帮助 AI 向你解释推荐，不会影响每天选哪张专辑。

## 关于我
- 常住地区 / 常用语言：
- 一句话介绍你的听歌经历：

## 我喜欢的
- 喜欢的流派或风格：
- 喜欢的年代：
- 喜欢的艺人（几个即可）：
- 最近常听的专辑：

## 我的边界（可选）
- 不想被推荐的类型：
- 其他偏好或要求：

## 聆听目标（可选）
- （例如：今年想多听 2010 年以后的专辑 / 想补某个地区的老唱片）
```

### C.2 `OMDA_PROFILE.template.en.md`

```markdown
# OMDA Music Profile

> This is your personal music profile. Every field is optional — leave
> anything you don't know blank; never make it up.
> OMDA reads this file locally only. Nothing is uploaded unless you
> explicitly share it.
> The profile only helps the AI explain recommendations to you; it never
> influences which album gets picked each day.

## About me
- Where you live / languages you use:
- One sentence about your listening history:

## What I like
- Genres or styles I enjoy:
- Eras I enjoy:
- A few favorite artists:
- Albums I have been listening to lately:

## My boundaries (optional)
- Types of music I do NOT want recommended:
- Other preferences or requests:

## Listening goals (optional)
- (e.g., "this year I want to hear more post-2010 albums")
```

### C.3 `OMDA_COLLECTION.template.zh-CN.md`

```markdown
# OMDA 探索清单

> 清单来源：（朋友 / 乐评人 / 社群 / 自己整理，可写一句话）
> 每行一张专辑。Artist 和 Album 必填；其余字段不确定就留空，不要编造。
> 评分和备注只会展示，不会影响每天选哪张专辑。
> Heard（已听）= 你已经听过的；Skip（跳过）= 你明确不想被推荐的。
> 请不要修改表头那一行。

| Artist 艺人 | Album 专辑 | Year 年份 | Genre 流派 | Rating 评分 | Heard 已听 | Skip 跳过 | Note 备注 |
|---|---|---|---|---|---|---|---|
| （示例）坂本龙一 | async | 2017 | 环境音乐 | | | | 朋友强烈推荐 |
|  |  |  |  |  |  |  |  |
```

### C.4 `OMDA_COLLECTION.template.en.md`

```markdown
# OMDA Collection

> Source of this list: (a friend / a critic / a community / self-curated —
> one sentence is fine)
> One album per row. Artist and Album are required; leave anything you
> are not sure about blank — never make it up.
> Rating and Note are display-only; they never influence the daily pick.
> Heard = you have already heard it; Skip = you explicitly do not want it
> recommended.
> Do not modify the header row.

| Artist | Album | Year | Genre | Rating | Heard | Skip | Note |
|---|---|---|---|---|---|---|---|
| (example) Ryuichi Sakamoto | async | 2017 | ambient | | | | recommended by a friend |
|  |  |  |  |  |  |  |  |
```

### C.5 AI 整理 Prompt（`ORGANIZE_PROMPT.zh-CN.md` 定稿基础）

```markdown
请把我提供的音乐资料整理成 OMDA 探索清单（Markdown 表格）。

规则（必须遵守）：
1. 只使用我提供的资料里真实出现的信息；不知道的字段一律留空，不得编造、
   不得推测、不得用搜索结果填补（除非我明确要求并提供了来源）。
2. 输出格式：完整复制 OMDA_COLLECTION 模板的表头行，一行一张专辑。
   Artist 和 Album 必填；Year、Genre、Rating、Heard、Skip、Note 尽量填，
   不确定就留空。
3. Heard（已听）：仅当资料明确表明我听过这张专辑才填"是"；不确定留空。
   Skip（跳过）：仅当我明确表达过不想听才填"是"。
4. Rating：保留资料中的原始表述（如"9/10""年度最佳"），不要换算或打分。
5. Note：可摘录资料中的一句短评，注明出处（如"来自乐评人 X"）。
6. 整理完成后把结果交给我确认；未经我确认不要提交给任何工具或上传。

我的资料如下：
（在此粘贴歌单 / 乐评 / 聆听记录 / 聊天记录等）
```

英文版（`.en.md`）为上述规则的逐条对应翻译（G6 定稿时逐句核对语义一致，
不增删规则）。

### C.6 反馈模板（`FEEDBACK_TEMPLATE.md`，中英双语同文件分节）

```markdown
# OMDA Skill Beta 反馈（试用一周后填写）

- 使用了几天：
- 每天真的会看推荐吗：（是 / 大多数时候 / 经常忘记）
- 推荐里有几张你想真的去听：
- 最惊喜的一张：
- 最不想要的一类：
- 哪一步最麻烦：（准备档案 / 准备清单 / 让 Agent 运行 / 其他）
- 你愿意把清单继续用下去吗：
- 给作者的一句话：

（本反馈默认只保存在你本地或由你自愿发给作者；OMDA 不会自动收集。）

# OMDA Skill Beta Feedback (after one week of use)

- Days used:
- Did you actually check the daily pick: (yes / most days / often forgot)
- How many picks did you actually want to listen to:
- Most surprising pick:
- Least wanted kind of pick:
- Which step was most annoying: (profile / collection / running the agent / other)
- Will you keep using it:
- One sentence for the author:

(This feedback stays local or is sent to the author by you voluntarily;
OMDA never collects it automatically.)
```

### C.7 项目前言（中文定稿基础）

```markdown
## 为什么我想做 OMDA

卡尔维诺在《为什么读经典》里说，经典是"从未对读者说完它要说的话"的书，
读经典几乎等于重读——每一次相遇，你已经是另一个人。我喜欢的音乐也是
这样：一张专辑的价值不在于它排在哪个榜单，而在于它有没有机会在某一天
遇见此刻的你。

大多数推荐系统在做的，恰恰是把"遇见"的可能性收窄：它记住你的偏好，
然后一次又一次把你送回你已经喜欢的东西里。OMDA 想做的相反——它不猜你
喜欢什么，而是为偶然相遇留出位置：从你没听过的地方，每天认真地带来
一张专辑，附上一份你可以核查的说明。

我也想诚实地承认审美是多元的：没有任何一个评分、榜单或算法有资格替你
判定什么"更重要"。所以 OMDA 的规则刻意朴素——给每个流派同样的机会，
不因为小众而少给，也不因为热门而多给；选择交给确定性的规则，解释交给你
自己的耳朵。Skill Beta 是这件事最小的一个开始：一份你自己的清单，
一天一张专辑，其余的交给相遇。
```

### C.8 项目前言（英文定稿基础，与 C.7 逐句对应）

```markdown
## Why I want to build OMDA

In "Why Read the Classics?", Italo Calvino says a classic is a book that
has never finished saying what it has to say — and that reading a classic
is almost the same as rereading it, because on each encounter you are
already someone else. The music I love works the same way: the value of
an album is not where it ranks on a chart, but whether it gets the chance
to meet you on some particular day.

Most recommendation systems narrow exactly that chance: they remember
your preferences and keep sending you back to what you already like.
OMDA tries to do the opposite — it does not guess what you like; it
leaves room for chance encounters: every day it carefully brings one
album from somewhere you have not been, with an explanation you can check.

I also want to say honestly that taste is plural: no single rating,
chart, or algorithm has the standing to decide for you what "matters
more". So OMDA's rules are deliberately plain — every genre gets an
equal chance, neither penalized for being obscure nor boosted for being
popular; deterministic rules make the pick, and your own ears do the
interpreting. Skill Beta is the smallest possible start: a list of your
own, one album a day, and the rest left to the encounter.
```

---

## D. 测试矩阵（G6 验收标准）

| # | 验证项 | 方法 | 证据位置（G6 报告阶段） |
|---|---|---|---|
| V-1 | 安装验证 | 干净目录 + 干净 Python ≥ 3.9：解压、按 README 手动路径完成首次推荐 | TEST_RESULTS.txt §install |
| V-2 | 连续两天推荐 | day1/day2（`--date` 注入）各一张、不同、历史两条记录；day2 不依赖 day1 输出文件存在 | §two-day |
| V-3 | 同日幂等 | 同 day key 重复 ≥3 次：输出一致、历史不变、抽样仅一次（seed/日志断言） | §idempotency |
| V-4 | 已听排除 | Heard/Skip 条目不被选；改标志后次日行为按 D10；永久排除条目不再出现 | §exclusion |
| V-5 | 多清单去重与冲突 | 两个 collection 合并：重复去重、heard/skip 取最严格、字段冲突取首现并记录、规范化歧义记录 | §merge |
| V-6 | 中英表头 | 英/中/双语三种表头解析等价；未知表头报列名 fail-closed | §headers |
| V-7 | 缺字段与损坏历史 | 缺必填行定位报错；损坏历史 JSON → 保留副本、拒绝运行、零自动重建 | §malformed |
| V-8 | 零网络调用 | 静态 import 审计（禁 socket/urllib/http/http.client/requests）+ 断网运行 | §no-network |
| V-9 | Secret/隐私扫描 | 扫描分发包与输出：无 token/key/个人数据/本机路径泄漏 | §scan |
| V-10 | Skill 结构验证 | SKILL.md frontmatter、目录结构、双语模板/说明/反馈模板齐备 | §structure |
| V-11 | ZIP 内容验证 | manifest 比对；排除项（var/、用户数据、.git、src/omda、测试）逐一断言不存在 | §zip |
| V-12 | Codex 安装说明 | 按 SKILL.md/README 在 Codex 中可发现并执行（Owner/朋友实测，反馈记录在 G6 报告；不可实测时显式披露） | §codex |
| V-13 | 非 native 兼容 | D17 手动路径在无 skill 加载器环境逐条可执行 | §compat |
| V-14 | 选择不受评分影响 | 修改 rating/note/profile → 同输入同历史下选择不变（D9 契约锁定） | §no-rating-effect |
| V-15 | 耗尽行为 | 全排除 → 显式耗尽信息 + 非零退出 + 零回退 | §exhausted |
| V-16 | 原子写入与崩溃 | 写入中途中断（注入异常）→ 历史不出现半写状态；重试成功 | §atomic |

规则：失败测试不得删除/弱化/无理由跳过（SPEC §7）；live 网络一律不用
（fixtures + `--date` 注入 + 临时目录隔离历史）。

---

## E. 安装与分发验证要求（汇总自 Owner 指令）

1. **Codex 安装说明**（T6.4）：逐条截图级步骤 + "以平台当前文档为准"注记
   + 手动路径兜底；验证 = V-12。
2. **非 native Skill Agent 兼容说明**（T6.4/D17）：粘贴 SKILL.md 作为普通
   指令 + 手动 CLI 命令 + 三平台差异；验证 = V-13。
3. **可分发 ZIP 内容验证**（T6.9/ADR-0003 D18）：白名单 manifest；
   验证 = V-11。

## F. 回滚与停止条件

- G6 全部产物位于 `skill/`、`governance/G6_SKILL_BETA_PLAN.md`、
  `reviews/stage-06/`，`git revert` 可整体回退，不触碰正式核心。
- ADR-0003 未接受前不得开始 T6.1–T6.10 的实现；评审返回 REVISE 时仅修订
  文档再送审；分发动作需 Owner 在 G6 接受后明确授权。

## G. 风险登记（G6 新增）

| ID | 风险 | 级别 | 缓解 |
|---|---|---|---|
| R-6-1 | 朋友误认为 Skill = 完整 3×3 引擎 | P1 | ADR-0003 D4 免责声明 + 对照表（V-10） |
| R-6-2 | AI 越权替换确定性选择 | P1 | D14 禁令 + 脚本无指定结果参数 + 文档声明 |
| R-6-3 | 历史损坏破坏永久排除承诺 | P1 | 原子写 + fail-closed + 损坏副本（V-7/V-16） |
| R-6-4 | 规范化身份误合并 | P2 | 纯函数规范化 + 歧义记录（V-5） |
| R-6-5 | 用户数据进入分发包/Git | P0 | manifest 白名单 + 扫描（V-9/V-11） |
| R-6-6 | harness 遥测超出 OMDA 控制 | P2 | D15 说明文档提示用户注意平台隐私政策 |
| R-6-7 | Codex/WorkBuddy skill 机制变化 | P2 | 手动路径始终可用（V-13） |
