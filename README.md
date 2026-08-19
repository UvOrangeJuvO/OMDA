# OMDA — Open Music Discovery Agent

OMDA 是一个本地优先、可审计的每日音乐探索 Agent：每天选择 3 个 Genre，为每个 Genre 推荐 3 张从未成功推荐过的 Album，生成介绍并通过可替换的输出适配器交付。

## 开发治理

- Executor：WorkBuddy 中的 DeepSeek V4 Flash
- Reviewer：Codex 中的 GPT-5.6 Sol
- 真源：本地 Git、规范文件、状态文件、测试和阶段报告
- 当前阶段：G0（只制定实施计划，不写 production code）

## 首先阅读

1. `docs/OMDA_AGENT_HANDOFF_SPEC.md`
2. `docs/OMDA_PROJECT_MASTER_PLAN_zh-CN.md`
3. `docs/OMDA_DUAL_MODEL_OPERATIONS_HANDBOOK_zh-CN.md`
4. `AGENTS.md`

## 当前操作

用 WorkBuddy 打开本目录，固定选择 `deepseek-v4-flash`，粘贴根目录的 `WORKBUDDY_FIRST_PROMPT.md`。模型完成 G0 并提交本地 commit 后必须停止，等待独立 Reviewer。

