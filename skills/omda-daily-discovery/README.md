# OMDA Daily Discovery — Skill Beta（个人 Markdown 模式）使用说明

<!--
前言状态说明（AC-30 / ADR-0003 §10 C3）：以下"关于 OMDA"前言为结构草稿，
最终文案必须由 Owner 提供原稿逐句校订中英文含义后定稿。在 Owner 校订前，
本前言以草稿状态随包发布。
-->

## 关于 OMDA

**OMDA — Open Music Discovery Agent（每日音乐探索代理）**

"乐者，天地之和也。"

1. OMDA 帮你每天遇见一张值得认真听的专辑。它不猜你喜欢什么，而是从你自己
   选择的来源清单里，用确定性的规则做出当天的选择，并附上一份你可以核查
   的说明。
2. 它的规则刻意朴素：每个流派有同样的机会；评分和热闹程度不决定什么
   更重要；推荐过的专辑不再重复；失败的运行不会弄脏任何记录。
3. 它默认一切都发生在你的电脑上：档案、来源清单和历史只保存在本地；
   除非你明确分享，什么都不会上传。

### Why I wanted to build OMDA

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

---

## 这是什么 / What this is

**中文**：OMDA Skill Beta 是 OMDA 的 companion mode——**每天一张专辑**，
从你自己选择的来源清单中由确定性脚本选出。它**不是** OMDA 完整的
3 Genre × 3 Album 引擎，两者规则与历史互不通用。全本地、零网络、不需要
任何账号。

**English**: OMDA Skill Beta is OMDA's companion mode — **one album a day**,
picked deterministically from source lists you choose. It is **not** the
full OMDA 3 Genre × 3 Album engine; the two share neither rules nor history.
Fully local, zero network, no accounts.

### 两种模式对照 / Two modes at a glance

| | OMDA 正式引擎（3×3） | OMDA Skill Beta（本包） |
|---|---|---|
| 输出 Output | 每天 3 Genre × 3 Album = 9 张 | **每天 1 张** |
| 数据来源 Data | 人工审核的 curated 数据包 | 你自己选择的来源 Markdown |
| 历史 History | SQLite 官方历史 | 本地 JSON（`var/`） |
| Genre 规则 | 30-pick cooldown | 等机会 + 连续 pick 防重复 |
| 评分 Ratings | 独立维度、可配置权重 | **仅展示，永不影响选择** |

---

## 目录结构 / Directory layout

```text
<你的工作目录>/
├── profile/
│   └── MY_PROFILE.md        # 你的私人档案 + 已听/跳过状态表（私人，勿分享）
├── sources/                 # 每位贡献者一份来源清单（可分享、只读）
│   ├── alice.md
│   ├── critic-zhang.md
│   └── ...
└── var/                     # 私人历史与输出（勿分享、勿提交 Git）
```

- `sources/` 里的每个文件来自一位朋友/乐评人/社群/你自己整理；把它们原样
  放进来即可，**不需要也不会被修改**。
- 复制 `templates/OMDA_SOURCE.template.*.md` 即可创建新的来源文件
  （每份的 `source_id` 必须不同）。

---

## 快速开始（三条路）/ Quick start

### A. Codex（native Skill）

1. 把本 `omda-daily-discovery/` 文件夹放入你的 Codex skills 目录
   （以 Codex 当前的 Skill 文档为准）。
2. 新开对话，让 Agent：*"Use the OMDA Daily Discovery skill to set me up
   and give me today's album."*
3. Agent 会引导你从模板创建 `profile/MY_PROFILE.md` 与来源文件，然后运行
   脚本并解释结果。

### B. WorkBuddy / 其他支持 Skill 的 Agent

把本文件夹交给 Agent 并让它阅读 `SKILL.md`，按其中步骤操作。

### C. 没有 Skill 机制？手动也能用（vendor-neutral）

```bash
# 1. 准备文件：从 templates/ 复制并填写
#    profile/MY_PROFILE.md 与 sources/<name>.md（每份改一个 source_id）

# 2. 运行（--source 可重复，想用几个来源就写几个）：
python3 scripts/daily_pick.py \
  --profile profile/MY_PROFILE.md \
  --source sources/alice.md \
  --source sources/critic-zhang.md \
  --history var/omda-skill/history.json \
  --output-dir var/omda-skill/output

# 3. 打开 var/omda-skill/output/<今天日期>.md 查看当天推荐。
#    英文输出加 --lang en。
```

要求：Python ≥ 3.9（标准库，无需安装任何包）。

---

## 每天怎么用 / Daily flow

1. 告诉你的 Agent 用哪几个来源（或者手动修改 `--source` 参数）。
2. 运行（或让 Agent 运行）上面的命令。
3. 阅读当天输出；Agent 可以结合你的档案解释这张专辑。

**同日锁定**：当天第一次成功运行后，结果与使用的来源集合即被锁定；同一天
再运行（即使换了 `--source`）只会返回同一个结果并说明原始来源集合。修改
来源或档案从明天生效。

**已听 / 跳过**：想排除某张专辑，在你自己的 `profile/MY_PROFILE.md` 的
"已听 / 跳过记录"表里加一行（`heard` 或 `skip`）。来源文件永远不会被
修改。

**清单耗尽**：当所有条目都被听过/跳过/推荐过，脚本会明确提示"清单已耗尽"
并停止——它绝不会自动降低标准或重复推荐。添加新条目后明天再试。

---

## 隐私与分享 / Privacy & sharing

- 档案、来源、历史、输出全部只保存在你的电脑上；脚本**零网络调用**。
- **本地使用 ≠ 同意公开贡献**。任何上传、公开发布或提交到 OMDA 社区都是
  需要你明确发起的独立动作。
- 来源文件里的 `sharing_note` 只描述私下分享的语境，**不是**公开再分发
  许可。
- 注意：你使用的 Agent 平台自身的遥测/云同步不在 OMDA 控制范围内，请留意
  其隐私政策；必要时尽量精简档案内容。

## 备份 / Backup

只有 `var/omda-skill/history.json` 需要备份（它承载"永久排除已推荐专辑"
的承诺）。档案和来源文件你自己就有；输出可随时从历史重新渲染。

## 故障排查 / Troubleshooting

| 现象 | 处理 |
|---|---|
| `selection-relevant Genre conflict ...` | 同一张专辑在不同来源里的流派不一致。选择一个为准，修改对应来源文件后重试（脚本没有做任何选择）。 |
| `source frontmatter ... rejected` | 来源文件的元数据头不符合受限格式（必须每行一个 `key: value`，不能缩进/嵌套/重复/未知字段）。对照模板修正。 |
| `table row at line N is missing required field(s)` | 表格某行缺 Artist 或 Album。填上或删掉整行（全空行没问题）。 |
| `history file ... is corrupt ... refusing to run` | 历史 JSON 损坏。脚本已保留损坏副本；从备份恢复或手工修复，**不要删除后重建**。 |
| `The collection is exhausted / 清单已耗尽` | 所有条目都已被排除。向来源清单添加新专辑。 |
| 想要英文输出 | 加 `--lang en`。 |

## 反馈

试用一周后，欢迎按 `FEEDBACK_TEMPLATE.md` 填写反馈（自愿，默认只保存在
本地）。
