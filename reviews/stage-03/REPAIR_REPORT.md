# G3 Repair Report（Re-review 1）

对应 Reviewer commit：`9178f145ed7c0210f5dd94af4c49b1d7a659f515`（`review(g3): request adapter contract repairs`）
上一 candidate：`eaeacb7a6bb77e87cb3af62b41a053a3d60270fc`
本轮修复 commits：`de30dd7`（G3-001/G3-002）、`ab3e1b8`（G3-003/G3-004）、`df989cd`（G3-005/G3-006）、`ad26c2f`（合规测试修正：允许惰性 urllib.parse）
每项先加失败测试复现 Reviewer 反例、再做最小修复；既有测试未删除/弱化（详见各节）。

## G3-001（P1）— Genre 包不强制 eligibility 与 provenance 边界 — CLOSED

- **根因**：`list_eligible_genres()` 返回全部记录（含 eligible:false）；`records_file` 直接 join 允许 `../../` 逃逸；记录 `source` 与 source_id、source_id 与目录名均未校验。
- **修复**（`de30dd7`）：
  1. 仅返回 `eligible: true` 记录（记录存在但全部 ineligible → 合法空列表；记录文件缺失/为空 → 包损坏错误）；
  2. `source.yaml.source_id == 包目录名` 校验；
  3. 每条记录 `source == source_id` 校验；
  4. `_records_path()` 拒绝绝对路径与目录逃逸（resolve 后必须位于包目录内，防符号链接逃逸）。
- **测试**：5 个负向（ineligible 不返回、ineligible 永不被选（Orchestrator 级）、source_id≠目录名、记录 source≠source_id、records_file 逃逸）。

## G3-002（P1）— critic row scale 可绕过声明 scale — CLOSED

- **根因**：rating_max 空白/0/负数/不相关均可接受；Core 按 row.rating_max truthy 归一化 → `rating=4` 空白 max 被当作已归一化 4.0。
- **修复**（`de30dd7`）：唯一归一化规则——空白 denominator 从 `source.yaml.rating_scale_max` 填充；提供的 `rating_max` 必须等于声明 scale_max（否则拒绝）；`rating_scale_min < rating_scale_max` 且 scale_max 为正（正分母）。
- **测试**：空白 max → 填充 5.0 且 compose=0.8；不匹配/0/负数 max 拒绝；scale_min>=scale_max 拒绝；rating 越有效 scale 拒绝；adapter→`compose_rating` 集成断言。

## G3-003（P1）— 单个无关 MusicBrainz 结果标 exact — CLOSED

- **根因**：只按列表数量选结果；不校验 title/artist/year → unrelated single → WRONG + exact。
- **修复**（`ab3e1b8`）：
  1. 每个 item 形状校验（id/title/artist-credit；畸形 → `SourceUnavailableError`）；
  2. **强匹配**：normalized title + 完整 artist-credit 均相等才候选；first-release-year 作为可复核佐证——与候选年份冲突 → 拒绝 exact；
  3. 0 匹配 → 显式 no-match（不装 canonical）；>1 匹配 → 显式 ambiguous（不装）。
- **测试**：unrelated single、同 title 异 artist、同 title/artist 年份冲突、畸形 item、多 plausible 歧义、真 exact（fixture 增强含 artist-credit）。

## G3-004（P1）— stale 缓存回退无可观察 marker — CLOSED（未触发 BLOCKED）

- **根因**：`cache_status="stale"` 传入 `_apply` 但未暴露；Port 返回值无法携带。
- **契约判断**：让 stale 可见**不修改已接受 Port/domain 契约**——选择 Reviewer 的两个允许分支：
  1. **fail clearly**：`enrich()`（Port 签名不变）在 stale 刷新失败时抛出 `SourceUnavailableError`，detail 携带 `cache_status/source/fetched_at/query_version`（不再静默返回未标注旧数据）；
  2. **新增纯领域值 `AlbumEvidence`**（cache_status/source/fetched_at/query_version）与 adapter 级 `enrich_with_evidence()` → `(AlbumCandidate, AlbumEvidence)`，使 fresh/stale-success/stale-failure 的 freshness 全程可观察；`AlbumEvidence` 是**纯新增类型**（domain.py 仅新增 dataclass，不改任何既有类型/Port 签名），未触发 BLOCKED_ARCHITECTURE。
- **测试升级（披露）**：原 `test_stale_cache_refresh_failure_degrades_explicitly`（断言静默返回旧值）按新验收语义升级为 `test_stale_cache_refresh_failure_fails_clearly_with_evidence`（断言 `SourceUnavailableError` + detail 证据）——属修复性升级而非弱化；新增 4 个 `enrich_with_evidence` 可观察性测试（fresh/缓存 fresh/stale 刷新成功/stale 刷新失败）。

## G3-005（P1）— 外部访问边界不完整（MB + RYM）— CLOSED

- **根因**：MB 连续成功调用无 pacing；RYM fetch 无 timeout/deadline、无 per-run 预算、接受任意 http(s) URL。
- **修复**（`df989cd`）：
  1. MB：`pacing_seconds`（默认 1.0s，符合 MusicBrainz ≤1 req/s 指引）——每次成功调用后 `_pace()`；可配置禁用；User-Agent 保持可配置（无秘密）；
  2. RYM：`PageFetcher.fetch(url, timeout)` 契约化；source 配置 `fetch_timeout` 并传入；fetcher 异常 → `SourceUnavailableError`；
  3. RYM：`max_pages_per_run`（默认 10）+ 按 run_id 独立预算，超限显式 `SourceUnavailableError`；
  4. RYM：URL 限制为 `https://rateyourmusic.com/genre/...`（scheme/host/path 校验）。
- **测试**：连续成功 pacing（sleeper 记录）、pacing 可禁用、timeout 传递、fetcher 异常映射、URL scheme/host/path 拒绝、per-run 预算耗尽与跨 run 独立。

## G3-006（P2）— 缓存无界 + 快照可变 — CLOSED

- **根因**：EnrichmentCache/PageCache 无限增长；PageCacheEntry 持可变 dict，get 返回缓存对象本身。
- **修复**（`df989cd`）：两缓存加 `max_entries` 容量上限 + 确定性 FIFO 驱逐；PageCache 存 `freeze_json` 不可变快照，`get` 返回 `thaw_json` 防御副本（调用者变异不影响缓存）。
- **测试**：两缓存驱逐（最旧条目被逐出）、缓存命中变异不损坏快照。

## 合规测试修正（提交 `ad26c2f`，披露）

Browser Companion URL 校验使用标准库 `urllib.parse`（惰性 URL 解析，不联网）；合规测试原将整个 `urllib` 列为网络 import 而误报。修正为仅禁止 `urllib.request/error`（socket 组件），`urllib.parse` 允许。这是对合规测试判据的修正，不弱化原有"无网络/浏览器 SDK import"保证（socket/requests/httpx/selenium/playwright/bs4 仍禁止）。

## 验证

| 命令 | 结果 |
|---|---|
| `pytest -q -p no:cacheprovider` | **382 passed, 0 failed, 0 skipped, 0 error** |
| `pytest -v`（TEST_RESULTS.txt） | 382 passed |
| `ruff check src tests browser_companion` | All checks passed |
| `git diff --check` | clean |
| 既有测试未删除/弱化/skip | 确认（350 → 382 单调增长；G3-004 一处测试按新验收语义升级，已披露；MB/companion fixtures 增强以携带完整证据） |
| tracked 敏感文件 | 无 |
| G2 verdict 未改；G2 Core/Orchestrator/Ports（除 domain.py 纯新增 AlbumEvidence）/storage/config 未改 | 确认 |
| 无 G4 scope creep；无 live RYM 依赖；无反爬绕过 | 确认 |
| 未 merge / 未 tag / 未进入 G4 | 确认 |

---

# G3 Re-review 2 Repair（2026-08-20）

对应 Reviewer commit：`443638e0c3807d49b1726060413d6c0cd985cacc`（`review(g3): keep adapter boundary findings open`）
上一 candidate：`120eedd9c14b0b5014cc50a61c7e123abb4721db`
本轮修复 commits：`981deab`（G3-003/G3-004）、`10a1ef7`（G3-005/G3-007/G3-008）
每项先加失败测试复现 Reviewer 反例、再做最小修复；未弱化既有测试（详见各节）。

## G3-003（P1，仍开放）— 缺 year/score 仍装 exact — CLOSED

- **根因**：`_year_conflict` 在任一年份缺失时返回 False；score 未校验/未用——自名专辑同 title/artist、无 year、score 缺失/0 → exact。
- **修复**（`981deab`）：`_sufficient_evidence` 取代 `_year_conflict`——
  1. 候选 year 已知时，必须存在**有效兼容** first-release year（缺失/畸形 "unknown" 视为证据不足，不是中性）；
  2. score 形状校验（畸形 → `SourceUnavailableError`）；score 缺失/<=0 → 证据不足，不装 destructive canonical ID；
  3. title/artist 单匹配不再仅凭"唯一返回项"即 exact。
- **测试**：缺 year、畸形 year、缺 score、score=0、畸形 score（6 类）+ 完全佐证自名专辑 exact（fixture 增强含 score）。

## G3-004（P1，仍开放）— 平行 adapter API — CLOSED（最小方案，未改 Port）

- **根因**：上一修复在具体 adapter 上新增 `enrich_with_evidence()`/`AlbumEvidence`，绕过已接受 one-adapter-one-Port 映射。
- **修复**（`981deab`）：按 Reviewer 指定最小方案——**删除 `enrich_with_evidence()`/`AlbumEvidence`**（domain.py 完全回退到已接受 G2 状态）；`enrich()`（Port 签名不变）保留 stale 刷新失败 fail-clearly（detail 携带 stale 证据）；docstrings 更新。**未修改任何已接受 Port/domain 契约 → 未触发 BLOCKED_ARCHITECTURE**。
- **测试**：删除 4 个 `enrich_with_evidence` 测试（属修复）；保留 fail-clearly 断言测试。

## G3-005（P1，仍开放）— 边界可禁用/URL 可绕过 — CLOSED

- **根因**：timeout/pacing 接受 0/负/inf/nan/None；PageFetcher 默认 None timeout；`_check_url` 只查原始 path 前缀（dot-segment/编码/userinfo/port 可逃逸）；UA 占位符。
- **修复**（`10a1ef7`）：
  1. MB 构造校验 connect/read timeout、base_delay、max_backoff、fresh_ttl、pacing 全为**有限正数**（拒绝 0/负/inf/nan/None/字符串/bool）；UA 非空字符串；
  2. `PageFetcher.fetch(url, timeout)` timeout **必填**（无 None 默认）；companion `fetch_timeout`/`fresh_ttl` 有限正数校验；
  3. `_check_url` 规范化：拒绝 userinfo（@）、端口（:）、dot-segments（原始与 `unquote` 解码后）、编码分隔符；解码后 path 必须仍以 `/genre/` 开头；
  4. UA：构造时校验非空（live 联系 UA 由运行层提供，文档注明）。
- **测试**：MB pacing 0/-1/inf/nan/None/string 拒绝、timeout 非有限拒绝；companion fetch_timeout 非有限拒绝、6 种 URL 绕过拒绝（dot-segment/编码 ../%2e%2e/userinfo/port/编码斜杠）、规范 URL 仍接受。

## G3-007（P2）— per-run 预算 ledger 无生命周期边界 — CLOSED

- **根因**：`_budget_used` 对每个 run id 永久保留条目。
- **修复**（`10a1ef7`）：ledger 容量上限 `max_tracked_runs`（默认 64）+ FIFO 驱逐最旧 run；新增 `finish_run(run_id)` 显式 run 完成清理（per-run，非全局重置，活跃 run 不会因此绕过限额）。
- **测试**：ledger 超容量驱逐最旧 run；`finish_run` 释放条目且新 run 正常计数。

## G3-008（P2）— critic 文档与运行时检查分歧 — CLOSED

- **根因**：指南承诺 source_id==目录名但 adapter 未校验；归一化/校验规则未文档化。
- **修复**（`10a1ef7`）：`CriticDatasetAdapter._source_meta` 强制 `source_id == 包目录名`；`data/critics/README.md` 更新——目录/source 不变量、blank `rating_max` 继承 `rating_scale_max`、提供须等于声明 scale、scale 严格递增且分母为正、blank-denominator 示例。
- **测试**：critic source_id≠目录名拒绝。

## 验证

| 命令 | 结果 |
|---|---|
| `pytest -q -p no:cacheprovider` | **411 passed, 0 failed, 0 skipped, 0 error** |
| `pytest -v`（TEST_RESULTS.txt） | 411 passed |
| `ruff check src tests browser_companion` | All checks passed |
| `git diff --check` | clean |
| 既有测试未删除/弱化/skip | 确认（382 → 411 单调增长；G3-004 的 4 个平行-API 测试删除属修复；pacing 禁用测试改造为断言拒绝） |
| tracked 敏感文件 | 无 |
| G2 verdict 未改；G2 Core/Orchestrator/Ports/storage/config 未改（domain.py 完全回退） | 确认 |
| 无 G4 scope creep；无 live RYM 依赖；无反爬绕过 | 确认 |
| 未 merge / 未 tag / 未进入 G4 | 确认 |

---

# G3 Re-review 3 Repair（2026-08-20）

对应 Reviewer commit：`033e599468ff8677b262d1714c67a6a7bcc6eacb`（`review(g3): keep live adapter and budget findings open`）
上一 candidate：`e8baf77787d552b086489f78850e71e1e363f0be`
本轮修复 commit：`ce67bd3`（G3-003/G3-005/G3-006/G3-007/G3-008/G3-009）
每项先加失败测试复现 Reviewer 反例、再做最小修复；未弱化既有测试（详见各节）。

## G3-003（P1）— provider 字符串 score 被拒 + 低/非有限 score 装 exact — CLOSED

- **根因**：`_parse_item` 只接受 int/float score → 官方 API 的字符串 `"100"` 被判畸形；`_sufficient_evidence` 用 `score <= 0` 作正数检查 → `NaN <= 0` 为 False、`0.01`/`Infinity` 都通过 → 装 destructive exact。
- **修复**（`ce67bd3`）：
  1. `_parse_score()`：接受 provider 文档化的**十进制字符串**（`"100"`）与 JSON number，解析为单一有限数值域 `[0, 100]`；拒绝 bool、非有限（NaN/±Inf）、畸形字符串、超范围（负/101+）→ typed `SourceUnavailableError`；
  2. 命名保守阈值 `MIN_EXACT_SCORE = 90.0`（`__all__` 导出、模块常量文档化）——低于阈值的弱匹配**永不**装 destructive canonical ID；
  3. `_sufficient_evidence` 改为 `score >= MIN_EXACT_SCORE`。
- **测试**：provider 形状 `"100"` 正常 enrichment；字符串 `"10"`/数值 `0.01`/`89` 不装 exact；boundary 恰好阈值接受；NaN/±Inf、bool、`"high"`/`"1O0"`/`"-5"`/`"101"`/list 受控拒绝（14 项新测试）。
- **关闭证据**：Reviewer 反例（`"100"`→失败、`0.01`/`NaN`/`Infinity`→exact）全部关闭；只有 title+完整 artist credit+必需 year+阈值 score 才装 canonical ID。

## G3-005（P1）— 计数非整数可禁用边界 + URL 反斜杠/双重编码绕过 + 占位 UA — CLOSED

- **根因**：`max_pages_per_run`/`max_tracked_runs` 只查 `<= 0`（NaN/Infinity/分数/bool 通过，NaN/Inf 使预算永不耗尽）；`max_retries` 无整数校验（1.5/NaN/Inf 后期 range() 抛裸 TypeError、字符串裸比较）；`_check_url` 只查原始 path 前缀（`..\` 反斜杠、双重编码 `%252e%252e` 可逃逸）；`DEFAULT_USER_AGENT` 是未验证联系点的占位符。
- **修复**（`ce67bd3`）：
  1. `_is_positive_int()`（int 非 bool 且 >0）应用于 `max_pages_per_run`/`max_tracked_runs`；`max_retries` 校验非负整数（int 非 bool 且 >=0）→ 构造时确定性失败；
  2. `_check_url`：拒绝反斜杠（原始与编码 `%5c`）；`_has_residual_encoding()` 拒绝任何残留/双重百分号编码（`%252e`/`%2f` 等）；最多 3 层 unquote 后仍须以 `/genre/` 开头且无点段——所有非规范目标在 PageFetcher 边界前被拒（`fetcher.calls == 0` 断言）；
  3. **User-Agent 必填**：移除占位默认（`DEFAULT_USER_AGENT = None`），构造时必须显式提供 contactable UA 字符串，否则受控 `ValueError`——不提供无法 live 构造。
- **测试**：companion 计数 bool/1.5/NaN/Inf 拒绝；MB retries bool/1.5/NaN/Inf/-1/string 拒绝；5 种非规范 URL（反斜杠、编码反斜杠、双重 `..`、双重 `/`、编码点段）拒绝且不达 fetcher；`user_agent=None` 拒绝；规范 URL 仍接受。
- **关闭证据**：Reviewer 反例全部关闭；计数类型与上限可强制执行；URL 在 fetcher 前规范化；live 请求必须有联系 UA。

## G3-007（P1）— FIFO 驱逐让活跃 run 重置并超限 — CLOSED

- **根因**：`_consume_budget` 容量满时静默驱逐最旧 ledger（可能活跃）→ 交错 run 可轮换 ID 绕过页面上限；既有测试固化了 reset 行为（`budget_used("r1") == 0`）。
- **修复**（`ce67bd3`）：**移除静默驱逐**——新 run ID 在满容量时 fail-closed 拒绝（明确 `SourceUnavailableError`，含 finish 提示）；活跃 run 的计数器永不被其他 run 到达重置；容量释放**只**通过显式 `finish_run(run_id)` 生命周期操作；`finish_run` 后标识符可复用为新 run。
- **测试**：Reviewer 精确 `r1 → r2 → r1` 交错（`max_pages=1, max_tracked=2`：r1 抓 A、r2 抓 B、r1 再抓 C 被拒且 `fetcher.calls == 2`、r1/r2 计数保持）；满容量新 run fail-closed；`finish_run` 释放后标识符复用（新 run 重新计数、超限仍拒）；原 `test_budget_ledger_is_bounded_by_tracked_runs` 改为 `test_budget_ledger_capacity_is_fail_closed`（语义修复，非弱化）。
- **关闭证据**：第三次请求未达 fetcher；活跃 run 预算为硬边界；ledger 有界且可释放。

## G3-006（P2）— cache max_entries 非整数禁用容量上限 — CLOSED

- **根因**：`EnrichmentCache`/`PageCache` 构造只查 `<= 0` → `max_entries=NaN/Infinity` 使 `len >= max` 永不成立（缓存无界），1.5/bool 也被接受。
- **修复**（`ce67bd3`）：两个 cache 的 `max_entries` 均校验为**正整数（int 非 bool 且 >0）**，构造时受控拒绝。
- **测试**：两 cache 各 6 类（bool/1.5/NaN/Inf/0/-1）拒绝。

## G3-008（P2）— README 空分母示例不是可工作 CSV 行 — CLOSED

- **根因**：示例行 `my-source,album-b,3,,            # blank...` 第五个 cell 是字面注释 → 被当 `review_url` 解析 → 非 HTTP(S) 拒绝。
- **修复**（`ce67bd3`）：示例行改为第五 cell 真空白（`my-source,album-b,3,,https://example.org/reviews/b`），解释放行外；注明 CSV 无行内注释。
- **测试**：`test_readme_blank_denominator_example_is_parseable`——从 README 提取示例代码块、构造真实包、经 adapter 解析：album-b `rating_max == 5.0`（继承 scale_max）、`rating == 3.0`。

## G3-009（P2）— 模块 docstring 仍描述已删除的 stale fallback — CLOSED

- **根因**：`musicbrainz.py` 模块 docstring 说刷新失败"falls back to the stale value"，与实现的 fail-closed（raise typed error 且不返回 stale identity）矛盾。
- **修复**（`ce67bd3`）：docstring 更新为精确契约——刷新失败是**带 stale provenance 的 typed `SourceUnavailableError`**（detail 含 cache_status/source/fetched_at/query_version），stale identity 永不 serve。

## 验证

| 命令 | 结果 |
|---|---|
| `pytest -q -p no:cacheprovider` | **463 passed, 0 failed, 0 skipped, 0 error** |
| `pytest -v`（TEST_RESULTS.txt） | 463 passed |
| `ruff check src tests browser_companion` | All checks passed |
| `git diff --check` | clean |
| 既有测试未删除/弱化/skip | 确认（411 → 463 单调增长；G3-007 一个固化错误行为的测试按新验收语义改造并披露） |
| tracked 敏感文件 | 无 |
| G2 verdict 未改；G2 Core/Orchestrator/Ports/storage/config 零改动 | 确认（`git diff 033e599` 该目录树 0 文件） |
| 无 G4 scope creep；无 live RYM 依赖；无反爬绕过 | 确认 |
| 未 merge / 未 tag / 未进入 G4 | 确认 |

---

# G3 Re-review 4 Repair（2026-08-20）

对应 Reviewer commit：`068b49df50ed5d7cf3bfbd931b43507a21b7ee8e`（`review(g3): require cache policy invalidation`）
上一 candidate：`98b13b892787caf0dd52e511a2e8913d53e380e9`
本轮修复 commit：`fd925e8`（G3-003/G3-005/G3-008）
每项先加失败测试复现 Reviewer 反例、再做最小修复；未弱化既有测试。

## G3-003（P1）— 旧 v1 canonical 缓存绕过新阈值 — CLOSED

- **根因**：上一轮收紧匹配语义（`MIN_EXACT_SCORE=90`）但 `QUERY_VERSION` 仍是 `"v1"`——旧规则（任何正 score）写入的 `v1` 缓存条目在 fresh hit 时被直接 `_apply` 为 exact，绕过新策略；缓存条目不含 score，无法重估。
- **修复**（`fd925e8`）：
  1. `QUERY_VERSION` 升级 `"v1" → "v2"`（模块常量文档化：匹配/接受语义改变时须升版本，旧命名空间条目永不作为当前 exact serve）；
  2. `enrich()` fresh-hit 增加**双保险**：`cached.query_version == QUERY_VERSION` 才直接 serve，同 key 但旧 query_version 的条目（如持久化 backend 注入）也视为 stale-by-policy，强制当前查询；
  3. 既有测试的"当前 key"硬编码 `v1|...` 改为动态 `f"{QUERY_VERSION}|..."`；反例测试保留 `v1|` 前缀。
- **测试**：`test_old_version_cache_entry_does_not_bypass_threshold`（seed 旧 `v1` 弱规则条目 → 不 serve，发起当前查询 `mb-current`，`transport.calls == 1`）；`test_old_version_cache_entry_is_never_served_directly`（当前查询失败时旧条目也绝不成为 exact，raise typed error）；`test_same_key_old_query_version_entry_is_not_served`（同 key 旧版本字段防御）。
- **关闭证据**：Reviewer 反例关闭——pre-threshold 条目在任何情况下都不再作为 exact 身份被 serve。

## G3-005（P2）— "contactable UA"只验证非空 — CLOSED

- **根因**：构造只要求显式字符串，`"x"`/`"omda/0.1"`/`"not contactable"` 均通过；只有 None 被拒绝，未证明联系要求。
- **修复**（`fd925e8`）：新增 `_is_contactable_user_agent()`——校验文档化的 `Application/version (contact URL or email)` 形状：应用名 token 打头 + 括号内 `(+https://`/`(+http://`/`(+mailto:`/`(mailto:` 联系 URL，或尖括号 `<user@example.org>` email 联系；其余一律受控 `ValueError`（无匿名/非联系串可静默替换）。
- **测试**：`"x"`/`"omda/0.1"`/`"not contactable"`/`"anonymous/1.0"`/`"app/1.0 (no contact)"` 拒绝；URL/mailto/尖括号 email 三种合法形状接受。
- **关闭证据**：运行时组合无法再传入非联系 UA；匿名标识符在 adapter 边界被拒。

## G3-008（P2）— README 列号/存储值/Core 归一化说明矛盾 — CLOSED

- **根因**：指南说"keep the fifth cell empty"（空白分母是**第四**列 `rating_max`，第五列 `review_url` 有值）；又说 album-b "stored as 3/5 (not 3.0)"——而 adapter 实际存 `CriticRatingRow(rating=3.0, rating_max=5.0)`，Core 组合时才算 `3.0/5.0`。
- **修复**（`fd925e8`）：`data/critics/README.md` 措辞修正——第四 `rating_max` 列可留空；adapter 填充并存 `rating_max=5.0` + 原始 `rating=3.0`；Core 在组合时归一化为 `3/5 = 0.6`；示例行保持有效 CSV。
- **测试**：既有 README smoke test 扩展——`compose_rating(adapter.ratings_for(album-b), {"my-source": 1.0}) == 3.0/5.0`（从 README 提取代码块构造真实包、经 adapter 解析、再经 Core 组合的端到端断言）。
- **关闭证据**：README 契约与实际存储/归一化行为完全一致；示例对贡献者可执行。

## 验证

| 命令 | 结果 |
|---|---|
| `pytest -q -p no:cacheprovider` | **474 passed, 0 failed, 0 skipped, 0 error** |
| `pytest -v`（TEST_RESULTS.txt） | 474 passed |
| `ruff check src tests browser_companion` | All checks passed |
| `git diff --check` | clean |
| 既有测试未删除/弱化/skip | 确认（463 → 474 单调增长；既有 cache key 硬编码改为动态版本，属修复同步非弱化） |
| tracked 敏感文件 | 无 |
| G2 verdict 未改；G2 Core/Orchestrator/Ports/storage/config 零改动 | 确认（`git diff 068b49d` 该目录树 0 文件） |
| 无 G4 scope creep；无 live RYM 依赖；无反爬绕过 | 确认 |
| 未 merge / 未 tag / 未进入 G4 | 确认 |

---

# G3 Re-review 5 Repair（2026-08-20）

对应 Reviewer commit：`f4cf1999fed91f6601efd7f878c778c1fa4c15d7`（`review(g3): require complete contact validation`）
上一 candidate：`f4ca34f168899d98f83fd23d2b081836e1cbd7f5`
本轮修复 commit：`cf59cf1`（G3-005）
先加失败测试复现 Reviewer 五个精确反例、再做最小修复；未弱化既有测试。

## G3-005（P2）— UA 校验器接受空/匿名/控制字符联系 — CLOSED

- **根因**：`_is_contactable_user_agent` 只查首字符字母数字 + 少量 marker 子串——`x(+https://)`（无 app/version 分隔、空 URL）、`x <@>`（空 local/domain）、`anonymous/1.0 (+https://)`、`app (+mailto:)`（无版本空邮箱）、`app/1 (+https://example.org)\r\nX-Test: injected`（尾随 CRLF）全部构造成功；控制字符可在 adapter 配置边界外逃逸为传输失败或不安全 header。
- **修复**（`cf59cf1`）：`_is_contactable_user_agent` 重写为**完整值校验**：
  1. 整个值无 ASCII 控制字符（`[\x00-\x1f\x7f]`，含 CR/LF → 拒绝 header 注入）；
  2. 必须 `Application/version`——`^[A-Za-z0-9][\w._-]*/\d[\w.+-]*$`（真实 app token + `/version`，缺一不可）；
  3. `anonymous`/`anon`/`bot`/`app` 不得作为应用标识；
  4. contact 严格三选一且**全串匹配**（无尾随内容）：`(+http(s)://...` 用 `urlparse` 验证非空 hostname；`(+mailto:local@domain)` / `(mailto:...)` 与 `<local@domain>` 由正则强制非空 local/domain。
- **测试**：verdict 五个精确反例 + 扩展 6 类（LF/CRLF 前移、https 无 host、mailto/尖括号空 local/domain）共 11 项拒绝；既有 3 类合法形状（URL/mailto/尖括号 email）接受（TEST_USER_AGENT 同步为严格合法格式）。
- **关闭证据**：Reviewer 反例全部关闭——空、匿名、无版本、控制字符、尾随内容 UA 一律在配置边界受控 `ValueError` 拒绝；合法联系形状可构造。

## 验证

| 命令 | 结果 |
|---|---|
| `pytest -q -p no:cacheprovider` | **485 passed, 0 failed, 0 skipped, 0 error** |
| `pytest -v`（TEST_RESULTS.txt） | 485 passed |
| `ruff check src tests browser_companion` | All checks passed |
| `git diff --check` | clean |
| 既有测试未删除/弱化/skip | 确认（474 → 485 单调增长；TEST_USER_AGENT 格式同步为严格合法值，非弱化） |
| tracked 敏感文件 | 无 |
| G2 verdict 未改；G2 Core/Orchestrator/Ports/storage/config 零改动 | 确认（`git diff f4cf199` 该目录树 0 文件） |
| 无 G4 scope creep；无 live RYM 依赖；无反爬绕过 | 确认 |
| 未 merge / 未 tag / 未进入 G4 | 确认 |

---

# G3 Re-review 6 Repair（2026-08-20）

对应 Reviewer commit：`3b5a2c4d0e3d42deb909cddc3672d24ea1d50372`（`review(g3): require exact header boundary validation`）
上一 candidate：`360b2f428277922e4b0ea55f00c00e4aac62d915`
本轮修复 commit：`ddb188b`（G3-005）
先加失败测试复现 Reviewer 六个精确反例、再做最小修复；未弱化既有测试。

## G3-005（P2）— strip 隐藏边界控制字符 + netloc 非 hostname — CLOSED

- **根因**：`_is_contactable_user_agent` 先 `value.strip()` 再查控制字符 → 前导/尾随 CR/LF/Tab 先消失，绕过"无控制字符"契约（静默重写 header 值）；`_url_has_hostname` 返回 `bool(parsed.netloc)` → `https://@`、`https://user@`、`https://:443`（authority 仅 userinfo 或仅 port、无 host）被判为有 host。
- **修复**（`ddb188b`）：
  1. **原始未 strip 值先查控制字符**（`_UA_CTRL.search(value)`）——任何规范化之前；
  2. **拒绝前导/尾随空白**：`value != value.strip()` 直接 `False`，绝不静默重写 header（不再 strip 后使用）；
  3. **hostname 谓词**：`_url_has_hostname` 改为要求 `parsed.hostname` 非空（而非 netloc）；scheme 限 http/https；`hostname`/port 解析异常（如畸形 IPv6）捕获 `ValueError` → `False`。
- **测试**：verdict 六个精确反例（尾随 CRLF、前导 LF、前导/尾随 Tab、`https://@`、`https://user@`、`https://:443`）拒绝；既有 3 类合法形状（URL/mailto/尖括号 email）+ 上轮 11 项反例全部保留通过。
- **关闭证据**：Reviewer 反例全部关闭——控制字符在任何规范化前被拒、首尾空白不静默重写、contact URL 必须真实 hostname；合法联系形状可构造。

## 验证

| 命令 | 结果 |
|---|---|
| `pytest -q -p no:cacheprovider` | **491 passed, 0 failed, 0 skipped, 0 error** |
| `pytest -v`（TEST_RESULTS.txt） | 491 passed |
| `ruff check src tests browser_companion` | All checks passed |
| `git diff --check` | clean |
| 既有测试未删除/弱化/skip | 确认（485 → 491 单调增长） |
| tracked 敏感文件 | 无 |
| G2 verdict 未改；G2 Core/Orchestrator/Ports/storage/config 零改动 | 确认（`git diff 3b5a2c4` 该目录树 0 文件） |
| 无 G4 scope creep；无 live RYM 依赖；无反爬绕过 | 确认 |
| 未 merge / 未 tag / 未进入 G4 | 确认 |

---

# G3 Re-review 7 Repair（2026-08-20）

对应 Reviewer commit：`abf6673b13f4463b964de839559fc3bbfe83bbcf`（`review(g3): require contact port validation`）
上一 candidate：`e30dd43479fe5821f7498ff29a14b5d07d2e427c`
本轮修复 commit：`22be44d`（G3-005）
先加失败测试复现 Reviewer 两个精确反例、再做最小修复；未弱化既有测试。

## G3-005（P2）— 联系 URL 非数字/超范围端口从未被评估 — CLOSED

- **根因**：`_url_has_hostname` 只读 `parsed.hostname`，从未读 `parsed.port`——`urllib.parse` 把端口校验延迟到 `.port` 属性访问；`:notaport`（非数字）与 `:99999`（超出 1–65535）在 hostname 非空时被接受。
- **修复**（`22be44d`）：在**同一受保护解析区**内 `hostname = parsed.hostname` 后追加 `_ = parsed.port`——`ValueError`（畸形 IPv6、非数字端口、超范围端口）→ `False`；`None`/默认端口（无端口、`:443`、`:80`）与合法自定义端口（`:8080`）正常放行。
- **测试**：verdict 两个精确反例（`:notaport`、`:99999`）拒绝；合法端口四类（无端口、默认 https `:443`、自定义 `:8080`、默认 http `:80`）接受；全部既有 UA 合法/非法案例保留通过。
- **关闭证据**：Reviewer 反例全部关闭——联系 URL 必须是可用 HTTP(S) 端点；端口校验在配置边界受控执行。

## 验证

| 命令 | 结果 |
|---|---|
| `pytest -q -p no:cacheprovider` | **497 passed, 0 failed, 0 skipped, 0 error** |
| `pytest -v`（TEST_RESULTS.txt） | 497 passed |
| `ruff check src tests browser_companion` | All checks passed |
| `git diff --check` | clean |
| 既有测试未删除/弱化/skip | 确认（491 → 497 单调增长） |
| tracked 敏感文件 | 无 |
| G2 verdict 未改；G2 Core/Orchestrator/Ports/storage/config 零改动 | 确认（`git diff abf6673` 该目录树 0 文件） |
| 无 G4 scope creep；无 live RYM 依赖；无反爬绕过 | 确认 |
| 未 merge / 未 tag / 未进入 G4 | 确认 |
