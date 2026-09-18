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

## 目录约定（用户工作目录）

```text
<workspace>/
├── profile/
│   └── MY_PROFILE.md          # 用户私人档案 + 结构化已听/跳过状态表
├── sources/                   # 每位贡献者一份 OMDA Source Markdown（可分享、只读）
│   ├── alice.md
│   ├── critic-zhang.md
│   └── ...
└── var/                       # 私人历史与输出（勿分享、勿提交 Git）
```

## 每日运行（Agent 操作）

```bash
python3 scripts/daily_pick.py \
  --profile profile/MY_PROFILE.md \
  --source sources/alice.md \
  --source sources/critic-zhang.md \
  --history var/omda-skill/history.json \
  --output-dir var/omda-skill/output
```

- `--source` 可重复：用户当天想用几个来源就传几个（至少一个）。
- 运行成功后阅读 `--output-dir/<当天日期>.md`，按其中内容向用户解释。
- **同日锁定**：当天第一次成功运行后，结果与来源集合即锁定。同日再次运行
  （即使换了 `--source`）只会返回已提交结果并说明原始来源集合，不会重抽。
- 退出码：`0` 成功；`2` 输入/校验失败（含来源间 Genre 冲突）；`3` 历史文件
  损坏（fail-closed，脚本会保留损坏副本，请勿自动重建）；`4` 清单耗尽
  （请提示用户向来源添加新条目，不得自行补充专辑）。

## 安装

- **Codex**：将本目录作为 Skill 安装（见 `agents/openai.yaml` 元数据），
  然后按上面的"每日运行"操作。
- **其他 Agent / 无 Skill 机制**：解压后把本 SKILL.md 内容作为普通指令
  粘贴给 Agent，或由用户按 `README.md` 中的手动命令自行运行。
- 详细的中英文使用说明、模板复制方法与故障排查见 `README.md`。

## 隐私

档案、来源、历史、输出全部只保存在用户本机；脚本零网络调用。本地使用
**不等于**同意公开贡献；任何上传/公开/提交都需要用户明确的独立动作。
来源文件中的 `sharing_note` 只是私下分享语境，不是公开再分发许可。
