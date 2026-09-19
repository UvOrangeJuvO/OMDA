# OMDA Skill 分发包声明

- **代码**：`scripts/daily_pick.py` 与整个 OMDA Skill Beta 分发包遵循
  **Apache-2.0**（完整文本见本包内 `LICENSE`；与 OMDA 主仓库许可一致）。
- **第三方运行时依赖**：无。脚本仅使用 Python 标准库（目标 Python ≥ 3.9）。
- **模板与文档**（`templates/`、`prompts/`、`README.md`、`SKILL.md`、
  `FEEDBACK_TEMPLATE.md`）：随分发包以 Apache-2.0 提供；你可以复制、修改
  模板供个人使用（Source 模板本来就是设计为可复制的）。
- **内置来源清单**（`assets/sources/OMDA_ONE_ALBUM_A_DAY.md`）：其整理、
  编排与文件文本由 OMDA 项目发起人随本包公开分享，并以 Apache-2.0 提供；
  Album、Artist 与 Genre 名称只作事实性标识，其相关权利仍归各自权利人。
  Genre 是项目在 Owner 授权下完成的原创宽口径人工分类；整理时曾查阅
  MusicBrainz 等公开音乐元数据与公开目录作核对，但本包不复制外部标签表、
  数据库记录或原文描述。
- **你的数据**：你的 `profile/`、`sources/`、`var/` 中的全部内容归你所有，
  不受本包许可影响。把他人整理的来源清单再分发时，请遵守该来源
  `sharing_note` 中的分享语境；它不是自动授予的公开再分发许可。
- **OMDA 商标/项目名**：本包是 OMDA 项目的 Skill Beta 分发物；修改后再
  分发时请勿声称其未修改。
