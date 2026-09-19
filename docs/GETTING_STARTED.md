# OMDA Skill Beta：下载与使用指南

English instructions follow the Chinese guide.

当前公开测试版：**v0.1.0-beta.3**

## 立即下载

- **[直接下载可用的 OMDA Skill ZIP](https://github.com/UvOrangeJuvO/OMDA/releases/download/v0.1.0-beta.3/omda-daily-discovery-0.1.0-beta.3.zip)**
- [查看 v0.1.0-beta.3 Release 页面](https://github.com/UvOrangeJuvO/OMDA/releases/tag/v0.1.0-beta.3)
- [下载 SHA-256 校验文件](https://github.com/UvOrangeJuvO/OMDA/releases/download/v0.1.0-beta.3/SHA256SUMS)

请下载 `omda-daily-discovery-0.1.0-beta.3.zip`。不要下载 GitHub 自动生成的
“Source code (zip)”或“Source code (tar.gz)”；它们是仓库源码快照，不是已经整理好
的 Skill 包。

## OMDA Skill Beta 是什么？

这是 OMDA 的轻量、本地优先测试版本。它每天从你明确选择的一个或多个 Markdown
音乐清单中，确定性地选出一张尚未推荐过的专辑。

- 每位分享者可以保留一份独立的 Source Markdown；不需要把所有人的清单合并成一个文件。
- 同一天可以选择一个或多个来源。
- 同一张专辑出现在多个来源时只算一个候选，不会因此增加被选中的概率。
- 评分与备注只用于展示，不影响选择。
- OMDA 脚本本身不会联网，也不会自动上传你的 Profile、来源或历史。
- Beta 每天推荐一张专辑；它与仓库中的完整版 3 × 3 Core 使用不同的历史。

## 最简单的使用方法

### 第一步：下载并解压

1. 点击上方“直接下载”链接。
2. 解压 ZIP；你会得到一个 `omda-daily-discovery` 文件夹。
3. 不要直接修改 Skill 文件夹中的脚本和内置来源。

文件夹内最重要的内容：

| 文件 | 用途 |
|---|---|
| `SKILL.md` | 给 AI Agent 阅读的操作规则 |
| `README.md` | 包内的完整中英文说明 |
| `templates/` | 私人 Profile 与音乐来源模板 |
| `assets/sources/OMDA_ONE_ALBUM_A_DAY.md` | 内置的 205 张《一天一专辑》来源 |
| `scripts/daily_pick.py` | 执行每日确定性选择的本地脚本 |
| `FEEDBACK_TEMPLATE.md` | 可选的 Beta 反馈模板 |

### 第二步：把文件夹交给 Agent

你不需要自己输入 Python 命令。打开能够读取本地文件的 Codex、WorkBuddy 或其他
Agent，把下面的话发给它，并把路径换成你电脑上的实际解压路径：

> 请阅读 `<解压路径>/omda-daily-discovery/SKILL.md` 和 README.md。不要修改 Skill
> 本体。请在我的文档目录中新建一个私人的 `OMDA-My-Music` workspace，按中文模板
> 建立 `profile/`、`sources/` 和 `var/`。第一次先使用包内的
> `OMDA_ONE_ALBUM_A_DAY.md` 作为唯一来源，运行今天的推荐，并用中文解释结果。
> 未经我明确同意，不要上传或公开任何文件，也不要替换脚本选出的专辑。

Agent 应为你建立类似下面的私人目录：

```text
OMDA-My-Music/
├── profile/
│   └── MY_PROFILE.md
├── sources/
│   └── （你自己或别人分享的来源清单）
└── var/
    └── omda-skill/
        ├── history.json
        └── output/
```

请备份 `history.json`；它记录已经推荐过的专辑，帮助 OMDA 避免重复推荐。

### 第三步：每天使用

每天告诉 Agent：

> 用 OMDA Daily Discovery，从我今天选择的来源里给我一张专辑，并解释结果；不要
> 改变脚本的选择。

当天第一次成功运行后，结果、来源集合和语言会锁定。同一天再次运行会返回相同结果，
不会不断重抽；第二天才会产生新的选择。

## 使用自己的清单

复制 `templates/OMDA_SOURCE.template.zh-CN.md` 到私人 workspace 的 `sources/`
目录，然后填写 Artist 与 Album。Year、Genre、Rating 和 Note 可以留空；评分若填写，
使用 1–10 的整数，并且永远不会影响选择概率。

也可以把你已有的歌单、乐评、表格或笔记交给 Agent，同时让它阅读
`prompts/ORGANIZE_PROMPT.zh-CN.md`。要求它不知道的内容留空，不得编造专辑、年份、
Genre 或评分。

每位分享者使用独立的 Source Markdown。你可以在某一天选择多个文件共同生成候选池，
不需要把所有人的内容复制进同一个文件。

## 隐私说明

- OMDA Skill 脚本本身零网络调用。
- Profile、来源、历史和输出默认只保存在你指定的本地 workspace。
- 你所使用的 Agent 平台可能有自己的云端处理或遥测；这不由 OMDA 控制。
- 不要在 Profile 或来源中写入密码、Token、身份证号、住址等敏感信息。
- 本地使用不代表同意公开贡献。上传清单前必须由你另外明确决定。
- 分享反馈前，请删除本机路径、用户名、私人 Profile 和不想公开的收听历史。

## 提交反馈

使用几天后，可以复制包内的 `FEEDBACK_TEMPLATE.md`。你可以通过 GitHub Issue 或你
选择的其他方式反馈安装困难、说明不清楚、重复推荐或多来源行为问题。请勿直接上传
`history.json` 或私人 Profile。

---

# OMDA Skill Beta: Download and Use

Current public beta: **v0.1.0-beta.3**

## Download now

- **[Download the ready-to-use OMDA Skill ZIP](https://github.com/UvOrangeJuvO/OMDA/releases/download/v0.1.0-beta.3/omda-daily-discovery-0.1.0-beta.3.zip)**
- [View the v0.1.0-beta.3 release](https://github.com/UvOrangeJuvO/OMDA/releases/tag/v0.1.0-beta.3)
- [Download SHA256SUMS](https://github.com/UvOrangeJuvO/OMDA/releases/download/v0.1.0-beta.3/SHA256SUMS)

Download `omda-daily-discovery-0.1.0-beta.3.zip`. Do not download GitHub's
automatically generated “Source code” archives; those are repository snapshots,
not the ready-to-use Skill package.

## What is the Skill Beta?

The Skill Beta is a lightweight, local-first OMDA mode. Each day it
deterministically selects one album you have not previously been recommended
from one or more Markdown music sources that you explicitly choose.

- Keep one Source Markdown per curator and select one or several sources each day.
- Duplicate albums across sources remain one candidate and gain no probability.
- Ratings and notes are display-only and never affect selection.
- The OMDA script makes no network calls and uploads nothing automatically.
- This one-album-per-day Beta keeps separate history from the repository's 3 × 3 Core.

## Easiest setup

1. Download and extract the Skill ZIP.
2. Open Codex, WorkBuddy, or another agent that can read local files.
3. Send the following instruction after replacing the path:

> Read `<extracted-path>/omda-daily-discovery/SKILL.md` and README.md. Do not
> modify the Skill itself. Create a private `OMDA-My-Music` workspace with
> `profile/`, `sources/`, and `var/`. For the first run, use the bundled
> `OMDA_ONE_ALBUM_A_DAY.md` as the only source and give me today's deterministic
> album. Do not upload any file or replace the script's selection without my
> explicit permission.

Back up `var/omda-skill/history.json`; it prevents repeat recommendations.

For your own list, copy `templates/OMDA_SOURCE.template.en.md` into your private
`sources/` directory, or ask the agent to follow `prompts/ORGANIZE_PROMPT.en.md`.
Unknown information must remain blank. Optional ratings are integers from 1 to
10 and never affect selection.

The first successful pick locks the result, selected sources, and language for
that local day. Re-running returns the same result; a new choice becomes
available the next day.

## Privacy and feedback

OMDA's script makes zero network calls, but your agent platform may have its own
cloud processing or telemetry. Do not include passwords, tokens, government IDs,
addresses, or other sensitive information in your files. Local use is not
consent to public contribution.

After testing, copy `FEEDBACK_TEMPLATE.md` and report unclear setup steps,
unexpected repeats, or source-merging problems. Remove local paths, usernames,
private profiles, and listening history before sharing feedback.
