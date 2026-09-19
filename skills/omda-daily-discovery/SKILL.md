---
name: omda-daily-discovery
description: "OMDA Skill Beta (Personal Markdown Mode): deterministically pick ONE album per day from the user's own OMDA Source Markdown lists. Local-only, zero network, ratings/notes never influence the pick. / OMDA Skill Beta（个人 Markdown 模式）：每天从用户自己选择的 OMDA 来源清单中确定性地选出一张专辑。仅本地、零网络，评分与备注不影响选择。"
---

# OMDA Skill Beta — Daily Discovery (Personal Markdown Mode)

**重要边界（Agent 必读）**：本 Skill 是 OMDA 的 companion mode（一天一张、
来自用户自己选择的来源清单），**不是** OMDA 完整的 3 Genre × 3 Album 引擎；
两者规则与历史互不通用。所有输出必须保留 D4 固定免责声明。

**AI 权限边界**：

1. 你可以：帮用户准备/整理 `OMDA_SOURCE` 与 `OMDA_PROFILE` 文件（按模板，
   不知道的字段留空，**不得编造**）；运行下面的脚本；阅读脚本输出并向用户
   解释当天推荐（可结合 Profile 的自由文本区）。
2. 你不得：替换、覆盖、重排或"优化"脚本选出的专辑；绕过脚本直接从清单里
   "挑一张"；把评分、备注或档案自由文本当作选择依据；改写任何来源文件；
   把个人状态写回来源文件；未经用户明确操作上传或公开任何用户数据。
3. 脚本没有"指定结果"参数。确定性脚本选择，AI 只解释。

## 两个目录，别混（G6-005）

| 目录 | 内容 | 说明 |
|---|---|---|
| **已安装 Skill 根目录**（下文记作 `<skill-root>`） | `SKILL.md`、`scripts/daily_pick.py`、`templates/`、`assets/sources/`、`README.md` 等 | Codex 安装目录（或解压后的分发包目录）；只读使用 |
| **用户 workspace** | `profile/MY_PROFILE.md`、`sources/*.md`、`var/` | 用户的私人数据；Profile/Sources/History **必须**留在这里 |

- 脚本与模板**始终相对于 `<skill-root>` 解析**（例如
  `<skill-root>/scripts/daily_pick.py`、`<skill-root>/templates/`）；
  **不要**假设用户当前工作目录里存在 `scripts/daily_pick.py`。
- 所有输出（每日推荐 Markdown）与历史 JSON 写入用户 workspace 的 `var/`。

## 每日运行（Agent 操作）

先确定两个路径：`<skill-root>`（本文件所在目录）与用户的
`<workspace>`（存放 `profile/`、`sources/`、`var/` 的目录），然后：

```bash
python3 <skill-root>/scripts/daily_pick.py \
  --profile <workspace>/profile/MY_PROFILE.md \
  --source <workspace>/sources/alice.md \
  --source <workspace>/sources/critic-zhang.md \
  --history <workspace>/var/omda-skill/history.json \
  --output-dir <workspace>/var/omda-skill/output
```

- `--source` 可重复：用户当天想用几个来源就传几个（至少一个）。
- OMDA 原生清单默认评分规范为 `10-point-integer`：Rating 可留空，填写时
  只能是 1–10 的整数。评分仍然只展示，绝不影响选择；旧版 `10-point`
  元数据写法继续兼容。
- 包内提供可选来源
  `<skill-root>/assets/sources/OMDA_ONE_ALBUM_A_DAY.md`（OMDA 发起人分享的
  205 张《一天一专辑》清单；全部条目都有人工复核的宽口径 Genre，
  较难判断的条目由 Owner 逐条确认）。可以在用户明确选择后直接作为一个
  `--source` 使用，或复制到用户 workspace；**不得静默自动启用**。
- `--template-dir <skill-root>/templates` 可选：让脚本校验模板齐备，
  便于为用户复制新的来源模板。
- 运行成功后阅读 `<workspace>/var/omda-skill/output/<当天日期>.md`，
  按其中内容向用户解释。
- **同日锁定**：当天第一次成功运行后，结果、来源集合与输出语言即锁定。
  同日再次运行（即使换了 `--source` 或 `--lang`）只会返回已提交结果
  （字节不变）并说明原始来源集合，不会重抽。
- 退出码：`0` 成功；`2` 输入/校验失败（含来源间 Genre 冲突、时钟回退）；
  `3` 历史文件损坏（fail-closed，脚本会保留损坏副本，请勿自动重建）；
  `4` 清单耗尽（请提示用户向来源添加新条目，不得自行补充专辑）。

## 安装

- **Codex**：将本目录作为 Skill 安装（元数据见 `agents/openai.yaml`，
  使用 `interface:` 结构与 `$omda-daily-discovery` 默认提示）。
- **其他 Agent / 无 Skill 机制**：解压后把本 SKILL.md 内容作为普通指令
  粘贴给 Agent，或由用户按 `README.md` 中的手动命令自行运行
  （此时 `<skill-root>` 即解压目录）。
- 详细的中英文使用说明、模板复制方法与故障排查见 `README.md`。

## 隐私

档案、来源、历史、输出全部只保存在用户本机（用户 workspace）；脚本零
网络调用。本地使用**不等于**同意公开贡献；任何上传/公开/提交都需要用户
明确的独立动作。来源文件中的 `sharing_note` 只是私下分享语境，不是公开
再分发许可。
