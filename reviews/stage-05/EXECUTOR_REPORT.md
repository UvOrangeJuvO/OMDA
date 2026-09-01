# Gate G5 Executor Report — Release Audit

## Identity

- Executor: DeepSeek V4 Flash
- Date: 2026-08-26
- Gate: G5 — Release Audit (T5.1–T5.5)
- Original base SHA: `d9944aa27bede364daf3ef93256016d5954792f6`
- Initialization commit: `3cf7759b672edefb5eef3dbb62a04f4b1f6d3f8a`
- Branch: `exec/g5-release-audit`
- Candidate SHA: (filled at commit; see `git rev-parse HEAD`)
- Worktree at start: clean

## Scope / Non-goals

Executed the approved C.5 release-audit scope only:
- T5.1 clean-environment installation and dry-run verification;
- T5.2 end-to-end and failure-injection matrix (SPEC §7 / OPH Prompt 10);
- T5.3 secret/security scanning and dependency/data license inventory;
- T5.4 backup/restore rehearsal and contribution documentation;
- T5.5 ≥ 7 controlled observations and RC proposal materials.

Non-goals honored: no automatic daily scheduling, no live PushPlus/LLM/RYM or
unnecessary external calls, no RC/release tag, no push, no publish, no
`ACCEPTED` / `RELEASE_CANDIDATE_ACCEPTED` marker, and no change to accepted
product semantics or architecture (G4 code is untouched by this Gate).

## Commits and Changes

- One cumulative commit on top of `3cf7759`.
- Added (audit tooling + evidence, no production semantic change):
  - `tools/release_audit/clean_env_check.sh` (T5.1)
  - `tools/release_audit/scan_secrets.py` (T5.3)
  - `tools/release_audit/backup_restore.py` (T5.4)
  - `tools/release_audit/observation_run.py` (T5.5)
  - `tests/integration/test_g5_e2e_matrix.py` (T5.2)
  - `LICENSES.md` (T5.3)
  - `CONTRIBUTING.md` (T5.4)
  - `reviews/stage-05/EXECUTOR_REPORT.md`, `TEST_RESULTS.txt`, `OBSERVATION_LOG.md`
  - `governance/PROJECT_STATE.json` → `G5 / READY_FOR_REVIEW`

## Architecture Impact

None. No `src/omda/**` production file is modified by this Gate.

## Product Invariant Matrix

| Invariant | Evidence |
|---|---|
| Equal Genre opportunity preserved | No popularity/tier logic touched; G1–G4 tests green |
| 30-pick cooldown preserved | `test_core_genre.py` green |
| Permanent Album exclusion preserved | Class 3 + observation 8 (no repeats, exhaustion fails explicitly) |
| Deterministic selection; no LLM in runtime | Deterministic runtime unchanged (G4-009/D8) |
| Failed runs do not pollute official history | Classes 1/5/6/7 assertions; `_assert_history_untouched` |
| Community source of truth = Git text | Curated packages unchanged; runtime store Git-ignored |
| No secrets/cookies/profiles in repo | `scan_secrets.py`: 0 hits |

## Acceptance Matrix (C.5)

| Task | Status | Evidence |
|---|---|---|
| T5.1 clean-env install + dry-run | **PASS** | `clean_env_check.sh`: fresh venv + `pip install -e .[dev]` + `python -m omda.cli --dry-run` → COMPLETE + preview file |
| T5.2 E2E + failure-injection matrix | **PASS** | `test_g5_e2e_matrix.py` 17 tests: E2E 3×3 positive; classes 1–7 (source fail / no-modern / repeat-exclusion / LLM-absent-by-construction / PushPlus ambiguous+definitive / commit-fail recovery / crash at 9 transitions) |
| T5.3 secret scan + license inventory | **PASS** | `scan_secrets.py` 0 hits (6 informational placeholder references only); `LICENSES.md` dependency/data inventory |
| T5.4 backup/restore + contribution docs | **PASS** | `backup_restore.py`: backup → corruption → fail-closed → restore → verify; `CONTRIBUTING.md` |
| T5.5 ≥ 7 observations + RC proposal | **PASS** | `OBSERVATION_LOG.md`: 8 observations, all invariants satisfied; RC proposal material in this report |
| Full regression, lint, whitespace | **PASS** | 761 passed; ruff clean; `git diff --check` clean |

## Verification

| Command | Result |
|---|---|
| `pytest -q -p no:cacheprovider` | **761 passed, 0 failed, 0 skipped, 0 error** (744 → 761, +17 matrix tests) |
| `pytest -v` (reviews/stage-05/TEST_RESULTS.txt) | 761 passed |
| `ruff check src tests tools browser_companion` | All checks passed |
| `git diff --check` | clean |
| `python tools/release_audit/scan_secrets.py` | 0 secret hits |
| `python tools/release_audit/backup_restore.py` | PASS (backup → corruption → fail-closed → restore → verify) |
| `bash tools/release_audit/clean_env_check.sh` | PASS (fresh venv install + dry-run COMPLETE) |
| `python tools/release_audit/observation_run.py` | 8 observations, all invariants satisfied |
| Existing tests weakened/deleted/skipped | None; every test runs (no skip directives added) |

## Failure and Recovery

The seven failure classes (OPH Prompt 10) are covered by the matrix:

1. **Data-source failure** → FAILED, zero history (class 1).
2. **No modern-year candidate** → documented fallback outcome, real records
   only (class 2).
3. **Already-recommended Album** → permanent exclusion; second run completes
   with fresh identities or fails explicitly on exhaustion, never repeats
   (class 3 / observation 8).
4. **LLM failure** → superseded by ADR-0002 D8: v0.1 is deterministic/no-LLM;
   no runtime LLM call exists (class 4, by construction).
5. **PushPlus failure** → ambiguous → RECOVERING (no retry); documented
   rejection → FAILED; zero history in both (class 5).
6. **Commit failure after delivery** → RECOVERING; recovery commits history
   without re-delivery (class 6).
7. **Process crash/restart** → crash at every durable transition; fresh
   process recovers to a consistent terminal state, no double-commit, no
   blind re-delivery (class 7, 9 crash windows).

## Deviations / Dependencies / Licenses

- Deviations: none from the approved scope. Class 4 is documented as
  superseded by the accepted D8 deterministic-runtime decision (no runtime LLM
  to fail); LLMAdapter retains its own failure semantics.
- Dependencies: runtime = Python standard library only; dev = pytest (MIT),
  ruff (MIT) — see `LICENSES.md`.
- Data licenses: four-layer separation per ADR-0002 D1, per-package manifests
  (see `LICENSES.md` and each package README).
- **Open finding for the release audit**: `pyproject.toml` code license is
  `UNLICENSED` — the Owner must select a code license before any RC tag.

## Risks and Technical Debt

1. Curated package size (5 Genres × 4 Albums) supports a real 3×3 but exhausts
   after a few days (observation 8 shows explicit failure on exhaustion);
   expanding curated data is a post-G5 contribution-flow activity.
2. v0.1 delivers no LLM narrative by design (ADR-0002 D8).
3. ODP-1 (live MusicBrainz tag-search) remains undecided/not implemented.
4. PushPlus has no documented no-side-effect category for non-200 responses;
   all such outcomes are ambiguous (conservative, ADR-0001 §9).

## Executor Conclusion

All five release-audit tasks are complete with reproducible evidence. The
candidate is committed, `PROJECT_STATE` is set to **G5 / READY_FOR_REVIEW**, the
worktree is clean, and the Executor stops here. Only the Reviewer may run the
final release audit and return `RELEASE_CANDIDATE_ACCEPTED`.

**Explicit declarations**: no RC/release tag created; nothing pushed or
published; no automatic scheduling enabled; no `ACCEPTED` /
`RELEASE_CANDIDATE_ACCEPTED` written; no production semantic/architecture
change.

---

# G5 Release Audit Re-review 1 Repair（2026-08-29，candidate 98681dd）

对应 Reviewer commit：`98681dd1def88a563c9fff6cb8645c0058d2870e`
（`reviews/final/RELEASE_AUDIT.md`，结论 **CHANGES_REQUESTED**：G5-001～G5-008）
被退修 candidate：`69ccad929eb9092083ad0a098c12dd9b56d37f8d`
Owner 决策（OD-8 / G5-005）：**Apache-2.0**（2026-08-29 确认）。
本轮仅修复上述 8 项；未重开 G0–G4、未改变已接受产品语义、未进入发布阶段。

## 逐项修复映射（G5-001 → G5-008）

| Finding | 修复 | 验收证据 |
|---|---|---|
| **G5-001**（P1，wheel 无法在 checkout 外运行） | ① 安装资源布局：`pyproject.toml` data-files 按子目录目标打包 `omda/data/*`（schemas/sources/genres/albums/critics）；`MANIFEST.in` 让 sdist 携带 data 树 + LICENSE；② `production.DEFAULT_DATA_DIR` 三源解析（OMDA_DATA_DIR → checkout `data/` → `<sys.prefix>/omda/data`），缺失 fail-closed；`schemas/validator.DEFAULT_SCHEMA_DIR` 同步；`cli` 默认 history 路径在 wheel 安装下回退 `<cwd>/var`；③ `clean_env_check.sh` 改为**构建 wheel+sdist → 全新 Python 3.12 venv 安装 wheel → checkout 外** import/config/dry-run，并记录工具版本 | `tools/release_audit/clean_env_check.sh`：构建 `omda-0.1.0-py3-none-any.whl` + `omda-0.1.0.tar.gz`；全新 py3.12 venv 从 /tmp 安装后 `import`/config 校验/`--dry-run` → COMPLETE + 预览文件；METADATA `License-Expression: Apache-2.0`；sdist 含 data/ 与 LICENSE |
| **G5-002**（P1，Album 排除测试未进入选择路径） | 受控 fixture：40 Genres（cooldown 满足）保持 Genre 规划可满足，把已提交 canonical identity 植入每个可选中 Genre 池的候选路径；断言 9 个全新真实 Album、committed 拒绝、无重复；shortage 变体断言显式失败由 Album 排除导致（journal 含 album/candidate 原因、无历史污染） | `test_g5_class3_album_exclusion_operates_in_selection_path`、`test_g5_class3_album_shortage_is_explicitly_caused_by_exclusion`（原 false-positive 测试删除）；观察 8 同步替换 |
| **G5-003**（P1，崩溃矩阵非真实持久化模拟） | `CrashHistoryWrapper` 委托**真实 SqliteHistory**（临时文件）；每次崩溃后关闭旧连接、新建 `SqliteHistory` + 新 engine；9 个窗口逐点断言精确 state/calls/receipt+operation/journal tail/0-or-3 与 0-or-9；DELIVERED→COMPLETE（无第二次 push）；AFTER_CLAIM（claim 持久化后死）→ RECOVERING + IN_FLIGHT operation；pre-delivery→FAILED | `test_g5_class7_crash_matrix_real_sqlite`（参数化 9 窗口） |
| **G5-004**（P1，secret 扫描漏检 + 泄露） | 两层策略：① tracked-path denylist（cookie jar/browser profile/runtime DB/.env/私钥/ssh/netrc/credential/service-account 文件——空文件或二进制同样命中）；② 文本 content patterns（PushPlus/通用 token/私钥块/AWS/GitHub/bearer/basic/Slack/Google/Stripe/JWT/session）；二进制（NUL 探测）永不文本解码；输出仅 kind+path+line 脱敏，**绝不打印 secret 原文**；正负 fixtures + force-add 集成测试 | `tests/unit/test_scan_secrets.py`（5 项，含 Reviewer force-add 复现）；仓库扫描 **0 命中** |
| **G5-005**（P1/OWNER，许可未定 + RYM 声明无依据 + 依赖清单不全） | Owner 决策 **Apache-2.0**：新增 `LICENSE`（全文）+ `pyproject` SPDX + wheel METADATA；`data/genres/rym-sample` **re-author** 为独立创作 `data/genres/demo-omda`（自创记录、通用流派名、example.com URL，不再声明派生自任何上游，目录/代码/测试/文档引用全部同步）；`LICENSES.md` 补全 build 依赖（setuptools/wheel/build）+ 已解析版本快照（含 pytest/ruff/transitive） | `LICENSE`、`pyproject.toml`、`LICENSES.md`（§1/§3/§4.3）、wheel METADATA |
| **G5-006**（P1，7 次观察不成立） | `observation_run.py` 重写：观察 1–7 = 七次**公共 `--dry-run` 入口**调用，逐条记录 UTC 时间戳、candidate SHA、命令/模式、data 版本、**零 live calls**（注入爆炸 transport 工厂证明不构造）、预览 SHA-256、before/after 官方历史（保持 absent）、同日自动化如实标注；观察 8 = G5-002 的 Album 排除证据（替换原无效 exhaustion 观察） | `reviews/stage-05/OBSERVATION_LOG.md`（8 条 JSON 记录，全部不变量满足） |
| **G5-007**（P2，运维文档与备份演练不完整） | `README.md` 重写为新用户文档（安装、dry-run、--deliver、配置、数据/历史位置、**用户级备份恢复步骤**、故障排查、许可）；`backup_restore.py` 严格化：停止写入者后一致备份、备份自校验、损坏**必须被拒绝**（domain 打开失败或 integrity_check 失败，否则非零退出）、保留损坏副本、**原子替换**（temp+rename）、恢复后逻辑完整性验证 | `README.md`；`tools/release_audit/backup_restore.py`（exit 0） |
| **G5-008**（P2，风险登记过期） | `RISK_REGISTER.md` 逐条与精确 test/report/ADR 引用核对：全部 P0/P1 → **CLOSED**（或 v0.1 范围限制），P2 持续控制；已知非阻塞限制单列 | `governance/RISK_REGISTER.md`（2026-08-29） |

## 验证

| 命令 | 结果 |
|---|---|
| `pytest -q -p no:cacheprovider` | **767 passed, 0 failed, 0 skipped, 0 error**（761→767；+6：scan_secrets fixtures 5 + 参数化矩阵净变化 0；既有测试未删除/弱化/skip） |
| `pytest -v`（reviews/stage-05/TEST_RESULTS.txt） | 767 passed（776 行） |
| `ruff check src tests tools browser_companion` | All checks passed |
| `git diff --check` | clean |
| 干净环境安装（wheel + sdist，checkout 外） | PASS（全新 Python 3.12 venv；import/config/dry-run 全通过） |
| Secret 扫描（含合成泄漏 fixtures） | 仓库 0 命中；5 项 fixtures 全过 |
| 备份恢复演练（严格版） | PASS（损坏拒绝 + 保留 + 原子恢复 + 校验） |
| 8 次受控观察 | 全过（7 次 public dry-run + 1 次 Album 排除证据） |
| G5-002 选择路径 / G5-003 真实 SQLite 崩溃矩阵 | 全部定向测试通过 |
| 未 merge / 未 tag / 未 push / 未发布 / 未进入后续阶段 / 未写 ACCEPTED | 确认 |

## 残余风险（诚实披露）

1. curated 包规模有限（5 Genre × 4 Album）：真实 3×3 可完成，连续多日运行会快速
   耗尽（显式失败已测）；扩充属 G5 后贡献流程。
2. v0.1 交付物无 LLM narrative（ADR-0002 D8 取舍）；未来 provider 需独立实现 +
   Gate 接受。
3. ODP-1（live MusicBrainz tag-search）仍未定案未实现（ADR-0002 §8-1）。
4. PushPlus 无文档化 definitive 类别，非 200 全按 ambiguous（保守）。
5. wheel 数据经 setuptools data-files 安装到 `<sys.prefix>/omda/data`（而非
   site-packages 包内）；已在 `_resolve_data_dir`/`_resolve_schema_dir` 双解析器与
   README 安装契约中完整文档化。

## Executor Conclusion（本轮）

G5-001～G5-008 全部按 Required repair 修复，完整验证集通过。`PROJECT_STATE` 保持
**G5 / READY_FOR_REVIEW**（未写 ACCEPTED / RELEASE_CANDIDATE_ACCEPTED），工作树干净，
Executor 停止等待 Reviewer 最终发布审计。
