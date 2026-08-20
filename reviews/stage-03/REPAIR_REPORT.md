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
