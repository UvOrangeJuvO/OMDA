# Gate G3 — Data & Adapters — Executor Report

> Executor：DeepSeek V4 Flash
> Date：2026-08-20
> Branch：`exec/g3-adapters`
> Base SHA：`f69c540ee8d98741b9a90f2175fdde012ea81c45`（G2 merge/main 基线，gate-g2-accepted 指向）
> Candidate SHA：提交后由本报告 commit 的 SHA 为准（`candidate_commit` 保持 null 避免自引用）
> 状态：**READY_FOR_REVIEW**（等待 GPT-5.6 Sol 独立复审；Executor 不写 ACCEPTED）

## 1. 开始前只读核对（全部通过）

- 仓库绝对路径：`<REPO_ROOT>`
- 分支 `exec/g3-adapters` ✓；HEAD = `f69c540e...` ✓；`git status --short` 空 ✓
- `gate-g2-accepted` → `f69c540e...` ✓
- `PROJECT_STATE.json`：G2 / ACCEPTED，approved_commit=`4d67c10e...` ✓
- `REVIEW_LOG.md`：G2 ACCEPTED（`4d67c10e...`，2026-08-20）✓
- `reviews/stage-02/REVIEW_VERDICT.md`：最终 **ACCEPTED** ✓
- 权威文档已按顺序阅读：HANDOFF_SPEC、MASTER_PLAN、ADR 目录（仅 README，无 Accepted ADR）、DUAL_MODEL_HANDBOOK、IMPLEMENTATION_PLAN（C.3/D/E/F/G/H）、RISK_REGISTER
- 既有 Ports/领域值/Schema/SQLite 边界/G2 Core/Orchestrator/fakes 已阅读；G2 基线 `pytest -q -p no:cacheprovider` **283 passed** + Ruff 全绿

## 2. 本轮交付（三个 Batch，5 个 Atomic 提交）

| Commit | Task | 内容 |
|---|---|---|
| `7f82965` | 治理 | `PROJECT_STATE` → G3/IN_PROGRESS；`reviews/stage-03/` 骨架；`chore(g3): begin data and adapters gate` |
| `676dfee` | T3.1/T3.2 | `src/omda/adapters/`（datasets.py：GenreDatasetAdapter/CriticDatasetAdapter + `_miniyaml.py` 极简平面 YAML 解析器）；`data/schemas/genre_source.schema.json`；示例数据包 `data/genres/rym-sample/`、`data/critics/example-source/`；单元+集成测试 |
| `6ca5a27` | T3.5 | 贡献指南（`data/critics/README.md` 更新、`data/genres/README.md` 重写）：`feat(g3): add critic contribution package contract` |
| `8e669f4` | T3.3 | `src/omda/adapters/musicbrainz.py`（MusicBrainzEnricher 实现 AlbumEnricher）+ 缓存/重试/退避 + 测试：`feat(g3): implement bounded MusicBrainz enrichment adapter` |
| `65ca091` | T3.4 | `browser_companion/`（parser/contract/source 薄契约）+ `data/schemas/rym_page.schema.json` + RYM HTML fixtures + 单元/合规测试：`feat(g3): establish compliant browser companion contract` |

## 3. Adapter → Port 唯一映射表（无重复/平行接口）

| 既有 Port（T1.4 已接受） | 唯一 G3 Adapter | 输入 → 输出 | typed error | provenance/cache |
|---|---|---|---|---|
| `GenreSource` | `GenreDatasetAdapter` | `data/genres/<source>/`（source.yaml + genres.jsonl）→ `list[GenreRef]` | `InvalidInputError`（文件:行:字段） | `DatasetProvenance`（license/origin_url/retrieved_at/version/scope/records_file） |
| `CriticRatingSource` | `CriticDatasetAdapter` | `data/critics/<source>/`（source.yaml + ratings.csv）→ `list[CriticRatingRow]` | `InvalidInputError`（文件:行:字段） | `DatasetProvenance` |
| `AlbumEnricher` | `MusicBrainzEnricher` | `AlbumCandidate` → enriched `AlbumCandidate`（canonical identity） | `SourceUnavailableError`（timeout/5xx/429/畸形/缺字段）；空/歧义 → 不设 identity（非错误） | `EnrichmentEntry`（canonical/source/fetched_at/query_version）+ fresh/stale/refresh-failure 显式降级 |
| （Browser Companion 提供 RYM 页面源，作为 AlbumSource 类数据源的前置；不注册为默认） | `RymGenrePageSource` | page_url + HTML → schema-validated `rym_page` 记录 | `SourceUnavailableError`（`detail.kind="human-action-required"`） | `PageCacheEntry`（page_url/fetched_at）+ provenance/timestamp |

未新增任何"看起来更通用"的重复接口；`omda/adapters/__init__.py` 空。LLM/Markdown/PushPlus 明确不实现（G4 独占）。

## 4. 数据边界与合规说明

### 4.1 文本数据集（T3.2）
- 社区文本为 Git 真源（SPEC §3.3）；`GenreDatasetAdapter`/`CriticDatasetAdapter` 逐记录过版本化 schema（`genre`/`critic_source`/`critic_rating`/`genre_source`），错误定位到文件、记录/行与字段（SPEC §7-1）。
- 每个来源声明 license、origin_url、retrieved_at/scrape_date、dataset_version 与 data_scope（R-006）。
- 极简平面 YAML 解析器（`_miniyaml.py`）保持项目零运行时依赖（PyYAML 不引入）；不支持嵌套结构时显式报错。
- 新增 critic 源只加文本包，不修改 Recommendation Core（`compose_rating` 只消费 `CriticRatingRow` 值类型；架构测试强制 Core 不 import `omda.adapters`）。

### 4.2 MusicBrainz enrichment（T3.3）
- 只按当前 run 的单个候选按需查询（`enrich(candidate)`），无全库/批量 enrichment；测试断言"一个候选一次查询"。
- 可注入 `transport`/`clock`/`sleeper`；普通测试全部使用 scripted fake transport + fixture 响应，**零 live 网络**（SPEC §3.2/§7-12）。
- 有界 connect/read timeout（默认 5s/10s）；有界重试（默认 3 次）；429/5xx/网络中断分类并指数退避（base 2^n，max_backoff 封顶）；只读操作幂等可安全重试。
- malformed JSON / 缺 `release-groups` 字段 → `SourceUnavailableError`；空结果 / 多结果歧义 → 不设 canonical identity（**歧义绝不静默抹平**，SPEC §2.4）。
- cache 条目含 canonical_id/canonical_source/fetched_at/query_version/source；fresh 短路、stale 刷新、刷新失败显式降级（stale 标记或抛错）；User-Agent 可配置且无秘密。

### 4.3 Browser Companion / RYM（T3.4）
- 极薄、可停用、人工可介入；仅标准库 `html.parser`，无 bs4/浏览器 SDK/socket。
- 页面分类：ok / login_required / captcha_challenge / rate_limited / session_invalid / unknown_page；任何非 ok 状态 → typed `SourceUnavailableError`（`detail.kind="human-action-required"`）——**暂停并请求人工，绝不自动规避**（SPEC §3.4）。
- 只提取当前 run 所需最小字段（title + 有界正文样本 + genre 元数据），输出进 schema-validated `rym_page` 记录（含 provenance/extracted_at），再交给 Adapter；不默认 Album Detail fan-out、不全量预爬。
- cookie/profile/session material 永不读取/写入（合规测试按 ast 检查代码标识符）；`browser_companion/` 独立包，停用时 Core/Orchestrator 用 fakes 照常工作（合规测试证明）。

## 5. 跨 Gate 验收矩阵（十二项）

| # | 验收项 | 证据 |
|---|---|---|
| 1 | 每个具体数据 Adapter 只实现一个既有 Port，无重复/平行 Core 接口 | §3 映射表；`test_adapter_implements_existing_ports_structural` |
| 2 | 社区 Genre/critic 文本是 Git 真源；runtime cache 可删除重建 | `data/genres/rym-sample/`、`data/critics/example-source/` 提交入库；cache 全部内存/可重建（EnrichmentCache/PageCache），var/ 仅 .gitkeep |
| 3 | 每个来源具有 license、source、provenance 与时间信息 | source.yaml（license/origin_url/retrieved_at/dataset_version/data_scope）+ `DatasetProvenance` 测试 |
| 4 | 畸形文本错误定位到文件、记录/行和字段 | 20 个 dataset 测试断言 `genres.jsonl:1` / `ratings.csv:2` + 字段名 |
| 5 | 新增 critic 源不修改 Core | `tests/integration/test_critic_contribution.py`；Core 架构测试无 adapters import |
| 6 | MusicBrainz timeout/retry/backoff 有界，429/5xx/空/畸形/歧义响应受控 | `test_musicbrainz_enricher.py` 19 例（calls 计数、sleeper 退避、SourceUnavailableError 分类） |
| 7 | cache fresh/stale/refresh-failure 行为明确且可复现 | fresh 短路（transport.calls==0）、stale 刷新、stale+刷新失败显式降级、provenance 断言 |
| 8 | 普通 CI 零 live network；所有外部响应来自 fixtures/fakes | ScriptedTransport/FixtureFetcher；合规测试断言 companion 无 network import |
| 9 | Browser Companion 遇登录/CAPTCHA/挑战页停止并请求人工，不做绕过 | 6 场景 typed error + `detail.kind=="human-action-required"`；合规测试禁止 stealth/captcha/cloudflare 词 |
| 10 | 无全量 RYM 预爬、无默认 Album Detail fan-out | 合规测试禁止 mass_crawl/pre_crawl/album_detail/fan_out 词；source 每次仅一页 |
| 11 | cookie/profile/token/个人数据不进入 Git、日志、报告或测试快照 | `git ls-files` 检查（无 cookie/profile/.sqlite/.db/.env/secret/token/key）；companion 代码无 cookie/profile 标识符 |
| 12 | G2 的 283 项及新增完整测试全部回归通过；Core 等权、cooldown、历史事务语义不变 | 全套 **350 passed / 0 failed / 0 skip / 0 xfail**；`src/omda/core|orchestrator|ports|storage|config.py` 与既有 schema 零改动（git diff 核对） |

## 6. 验证命令与结果

| 命令 | 结果 |
|---|---|
| `pytest -q -p no:cacheprovider` | **350 passed**（含 no-cacheprovider 独立运行） |
| `pytest -v`（reviews/stage-03/TEST_RESULTS.txt） | 350 passed |
| `ruff check src tests browser_companion` | All checks passed |
| `git diff --check` | clean |
| skip/xfail | 0（无任何跳过/隐藏失败） |
| tracked 敏感文件检查 | 无（cookie/profile/sqlite/db/env/secret/token/key/pem/pyc/cache 均零命中） |
| 工作区 | 干净（提交后 `git status --short` 空） |

## 7. 偏差、已知限制与残余风险

- **偏差**：无已接受计划范围内的偏差。source.yaml 用自研极简平面解析器（非通用 YAML 引擎）——为保持项目零运行时依赖的可逆工程选择（分类 (c)），在 G3 评审中接受审查。
- **已知限制**：`GenreDatasetAdapter`/`CriticDatasetAdapter` 为内存解析（数据集规模当前为示例级）；MusicBrainz cache 默认内存后端（持久化 JSON 后端可按需扩展，不改变契约）；Browser Companion 未接入真实浏览器（契约与解析层已就位，真实会话连接属 G5 安装/运行层面）。
- **残余风险**：R-005（RYM 布局/会话变化）——fixtures + 人工介入路径 + unknown_page 分类兜底；R-006（外部数据许可）——每来源 license 已声明，发布前 G5 审计；R-002（秘密入库）——本轮零敏感文件，G5 CI 扫描化。
- **范围确认**：未实现 LLM Provider/Prompt/Markdown/PushPlus（G4）；未做 popularity filter/Genre tier/质量评分；未做 RYM 全量预爬/Album Detail fan-out/Cloudflare 对抗/CAPTCHA 自动化；未用 SQLite 取代社区真源；未改产品不变量与已接受事务语义。

## 8. Executor Conclusion

**READY_FOR_REVIEW**（等待 GPT-5.6 Sol 对本 candidate SHA 独立复审并出具唯一 verdict；Executor 未写 ACCEPTED、未合并、未打 gate-g3-accepted 标签、未进入 G4）。

---

# G3 Re-review 1 Repair（2026-08-20）

对应 Reviewer commit：`9178f145ed7c0210f5dd94af4c49b1d7a659f515`
上一 candidate：`eaeacb7a6bb77e87cb3af62b41a053a3d60270fc`
本轮修复 commits：`de30dd7`（G3-001/G3-002）、`ab3e1b8`（G3-003/G3-004）、`df989cd`（G3-005/G3-006）、`ad26c2f`（合规判据修正）
详细逐项修复记录见 `reviews/stage-03/REPAIR_REPORT.md`。

## Re-review 1 finding 修复对照

| Finding | 严重度 | 修复 commit | 状态 |
|---|---|---|---|
| G3-001 Genre 包 eligibility/provenance 边界 | P1 | `de30dd7` | CLOSED |
| G3-002 critic scale 一致性 | P1 | `de30dd7` | CLOSED |
| G3-003 MB 匹配验证（exact 需强证据） | P1 | `ab3e1b8` | CLOSED |
| G3-004 stale evidence 可观察（fail-clearly + AlbumEvidence，未改已接受契约） | P1 | `ab3e1b8` | CLOSED |
| G3-005 外部访问边界（pacing/timeout/budget/URL） | P1 | `df989cd` | CLOSED |
| G3-006 缓存有界与快照安全 | P2 | `df989cd` | CLOSED |

## 本轮验证

| 命令 | 结果 |
|---|---|
| `pytest -q -p no:cacheprovider` | **382 passed, 0 failed, 0 skipped, 0 error** |
| `pytest -v`（TEST_RESULTS.txt） | 382 passed |
| `ruff check src tests browser_companion` | All checks passed |
| `git diff --check` | clean |
| 既有测试未删除/弱化/skip | 确认（350 → 382；G3-004 一处按新验收升级并披露） |
| 未 merge / 未 tag / 未进入 G4 / 未改 verdict | 确认 |

## Executor Conclusion（G3 Re-review 1 repair）

**READY_FOR_REVIEW**（待 GPT-5.6 Sol 对本轮新 candidate SHA 复审；verdict 仅对新 SHA 有效）

---

# G3 Re-review 2 Repair（2026-08-20）

对应 Reviewer commit：`443638e0c3807d49b1726060413d6c0cd985cacc`
上一 candidate：`120eedd9c14b0b5014cc50a61c7e123abb4721db`
本轮修复 commits：`981deab`（G3-003/G3-004）、`10a1ef7`（G3-005/G3-007/G3-008）
详细逐项修复记录见 `reviews/stage-03/REPAIR_REPORT.md`。

## Re-review 2 finding 修复对照

| Finding | 严重度 | 修复 commit | 状态 |
|---|---|---|---|
| G3-003 缺 year/score 仍装 exact | P1 | `981deab` | CLOSED |
| G3-004 平行 enrichment API | P1 | `981deab` | CLOSED（最小方案：删除平行接口，未改已接受契约） |
| G3-005 边界可禁用/URL 可绕过 | P1 | `10a1ef7` | CLOSED |
| G3-007 预算 ledger 无生命周期边界 | P2 | `10a1ef7` | CLOSED |
| G3-008 critic 文档/运行时分歧 | P2 | `10a1ef7` | CLOSED |

## 本轮验证

| 命令 | 结果 |
|---|---|
| `pytest -q -p no:cacheprovider` | **411 passed, 0 failed, 0 skipped, 0 error** |
| `pytest -v`（TEST_RESULTS.txt） | 411 passed |
| `ruff check src tests browser_companion` | All checks passed |
| `git diff --check` | clean |
| 既有测试未删除/弱化/skip | 确认（382 → 411；G3-004 平行-API 测试删除属修复，已披露） |
| 未 merge / 未 tag / 未进入 G4 / 未改 verdict | 确认 |

## Executor Conclusion（G3 Re-review 2 repair）

**READY_FOR_REVIEW**（待 GPT-5.6 Sol 对本轮新 candidate SHA 复审；verdict 仅对新 SHA 有效）

---

# G3 Re-review 3 Repair（2026-08-20）

对应 Reviewer commit：`033e599468ff8677b262d1714c67a6a7bcc6eacb`
上一 candidate：`e8baf77787d552b086489f78850e71e1e363f0be`
本轮修复 commit：`ce67bd3`（G3-003/G3-005/G3-006/G3-007/G3-008/G3-009）
详细逐项修复记录见 `reviews/stage-03/REPAIR_REPORT.md`。

## Re-review 3 finding 修复对照

| Finding | 严重度 | 修复 commit | 状态 |
|---|---|---|---|
| G3-003 provider 字符串 score 被拒 + 低/非有限 score 装 exact | P1 | `ce67bd3` | CLOSED |
| G3-005 计数非整数可禁用边界 + URL 反斜杠/双重编码绕过 + 占位 UA | P1 | `ce67bd3` | CLOSED |
| G3-007 FIFO 驱逐让活跃 run 重置并超限 | P1 | `ce67bd3` | CLOSED |
| G3-006 cache max_entries 非整数禁用容量上限 | P2 | `ce67bd3` | CLOSED |
| G3-008 README 空分母示例不是可工作 CSV 行 | P2 | `ce67bd3` | CLOSED |
| G3-009 模块 docstring 仍描述已删除的 stale fallback | P2 | `ce67bd3` | CLOSED |

## 本轮验证

| 命令 | 结果 |
|---|---|
| `pytest -q -p no:cacheprovider` | **463 passed, 0 failed, 0 skipped, 0 error** |
| `pytest -v`（TEST_RESULTS.txt） | 463 passed |
| `ruff check src tests browser_companion` | All checks passed |
| `git diff --check` | clean |
| 既有测试未删除/弱化/skip | 确认（411 → 463 单调增长；G3-007 一个固化错误行为的测试按新验收语义改造并披露） |
| 未 merge / 未 tag / 未进入 G4 / 未改 verdict | 确认 |

## Executor Conclusion（G3 Re-review 3 repair）

**READY_FOR_REVIEW**（待 GPT-5.6 Sol 对本轮新 candidate SHA 复审；verdict 仅对新 SHA 有效）
