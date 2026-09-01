# OMDA — Open Music Discovery Agent

OMDA 是一个本地优先、可审计的每日音乐探索 Agent：每次运行选择 3 个 Genre，为每个 Genre 推荐 3 张从未成功推荐过的 Album，生成确定性事实报告，并通过可替换的输出适配器交付。

- **v0.1 是 deterministic/no-LLM runtime**（ADR-0002 D8）：不调用任何外部 LLM，交付物是经过验证的结构化事实报告。
- **零第三方运行时依赖**：仅使用 Python 标准库。
- **外部交付受控**：默认 dry-run（零外部调用）；只有显式 `--deliver` 才会推送 PushPlus。

---

## 快速开始

### 安装（推荐：wheel）

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install omda-0.1.0-py3-none-any.whl     # 或 pip install .（从源码构建）
```

### 运行一次本地预览（dry-run，零外部调用）

```bash
python -m omda.cli --dry-run --output-dir var/output --run-id my-first-run
```

输出：

```
dry-run my-first-run: COMPLETE
preview: var/output/my-first-run.md
```

dry-run 写入本地 Markdown 预览，**不调用任何外部服务、不写官方历史**，可反复执行。

### 显式外部交付（需要 PushPlus token）

```bash
export OMDA_PP_TOKEN='your-token-here'
python -m omda.cli --deliver \
  --config config.json \
  --run-id my-delivery \
  --history var/omda.sqlite3
```

`--deliver` 只接受已评审的 curated 数据源（demo/示例数据会被拒绝），并在外部推送后把官方历史写入 `--history` 指定的 SQLite 运行时库。

---

## 配置

配置文件为 JSON（schema 见 `data/schemas/config.schema.json`）：

```json
{
  "daily_genre_count": 3,
  "albums_per_genre": 3,
  "delivery": {
    "channel": "pushplus",
    "pushplus_token_env": "OMDA_PP_TOKEN"
  }
}
```

- `delivery.channel`：`markdown`（本地文件）或 `pushplus`（外部推送）。
- `delivery.pushplus_token_env`：存放 token 的**环境变量名**（不写 token 本身）。
- `llm.mode`：仅允许 `deterministic`（v0.1 无外部 LLM；配置 `provider` 会在校验阶段 fail-closed）。
- token 覆盖规则：CLI `--token-env` 显式给出时覆盖配置值；省略时使用配置值；两者都缺 → 推送前明确失败（零网络调用）。

## 数据与历史位置

| 项 | 位置 | 说明 |
|---|---|---|
| 数据真源（Git reviewable） | `data/` | schemas、curated 数据包、registry |
| 已安装数据（wheel） | `<sys.prefix>/omda/data/` | 随 wheel 打包 |
| 运行时官方历史（SQLite） | 源码运行：`<repo>/var/omda.sqlite3`；wheel 运行：`<cwd>/var/omda.sqlite3` | 可用 `--history` 覆盖 |
| dry-run 预览 | `--output-dir`（默认 `var/output`） | 不写官方历史 |

`OMDA_DATA_DIR` 环境变量可显式指定数据目录（优先于所有默认解析）。

## 备份与恢复（用户步骤）

运行时官方历史（SQLite）是唯一需要备份的状态。

```bash
# 1. 停止写入者：确保没有 OMDA 进程正在运行。
# 2. 一致备份（推荐用 sqlite3 工具，需 sqlite3 CLI）：
sqlite3 var/omda.sqlite3 ".backup 'var/omda.backup.sqlite3'"
#    或直接复制（仅当已完全停止写入）：
cp var/omda.sqlite3 var/omda.backup.sqlite3

# 3. 校验备份可打开：
python -c "from omda.storage import SqliteHistory; s=SqliteHistory('var/omda.backup.sqlite3'); print('backup ok, schema', s.schema_version()); s.close()"
```

恢复：

```bash
# 1. 停止写入者。
# 2. 保留损坏副本（证据不覆盖）：
cp var/omda.sqlite3 var/omda.corrupt.sqlite3
# 3. 原子替换（先写临时文件再 rename）：
cp var/omda.backup.sqlite3 var/omda.sqlite3.tmp && mv var/omda.sqlite3.tmp var/omda.sqlite3
# 4. 校验恢复后的库：
python -c "
from omda.storage import SqliteHistory
s = SqliteHistory('var/omda.sqlite3')
print('schema', s.schema_version(), '| picks', s.latest_pick_index())
s.close()"
```

可复现的自动化演练（备份 → 模拟损坏 → 拒绝 → 保留 → 原子恢复 → 校验）：

```bash
python tools/release_audit/backup_restore.py
```

损坏的库必须被拒绝（打开失败或完整性检查失败）；如果未检测到损坏，演练会以非零退出失败。

## 故障排查

| 症状 | 原因与处理 |
|---|---|
| `omda: run failed: ... missing source.yaml` | 数据目录未解析到。确认已安装 wheel（含 `omda/data`），或显式设置 `OMDA_DATA_DIR`。 |
| `--deliver` 报 token-missing | 未提供 token 环境变量。设置 `OMDA_PP_TOKEN` 或 `--token-env`。 |
| `--deliver` 拒绝 demo/sample 数据 | 外部交付只接受已评审 curated 数据（`demo-omda` 是演示包，被生产门禁拒绝）。 |
| dry-run 输出非 COMPLETE | 检查 `--output-dir` 可写、数据包完整。dry-run 不调用外部服务，失败通常来自数据/校验。 |
| SQLite 打开失败（SourceUnavailableError） | 库可能损坏或版本过新。按"备份与恢复"一节恢复，或联系维护者。 |
| 推送结果非 200 | 全部按 ambiguous 保守处理（ADR-0001 §9），进入 RECOVERING，需要人工确认；绝不自动重推。 |

## 开发治理

- Executor：WorkBuddy 中的 DeepSeek V4 Flash；Reviewer：Codex 中的 GPT-5.6 Sol。
- 真源：本地 Git、规范文件、状态文件、测试和阶段报告。
- 当前阶段：**G5 Release Audit / READY_FOR_REVIEW**（尚未打 RC/发布标签）。
- 完整规范：`docs/OMDA_AGENT_HANDOFF_SPEC.md`、`docs/OMDA_PROJECT_MASTER_PLAN_zh-CN.md`、`docs/OMDA_DUAL_MODEL_OPERATIONS_HANDBOOK_zh-CN.md`、`AGENTS.md`。

## 许可

- 代码：**Apache-2.0**（见 `LICENSE`；Owner 决策 2026-08-29）。
- 数据与依赖许可：见 `LICENSES.md`。
- 社区贡献：见 `CONTRIBUTING.md`。
