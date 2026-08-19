# OMDA Risk Register

> 维护者：Executor（DeepSeek V4 Flash）；重大风险须升级 Owner/Reviewer。
> 更新：2026-08-19（G1）。优先级含义：P0 数据损坏/安全/核心语义错误，绝对阻断；P1 可复现功能错误/架构违约，阻断；P2 可维护性/小风险，视数量与影响而定（OPH §8.3）。
> 缓解验证点 = 本风险在哪个 Gate 验收矩阵中被证明已缓解。

| ID | 优先级 | 风险 | 所需控制 | 缓解验证点 | 状态 |
|---|---|---|---|---|---|
| R-001 | P0 | 失败/歧义交付污染或重复官方历史 | 持久 run journal + 幂等键 + recovery 状态；失败注入测试断言历史不变 | G2 T2.6、G4 T4.3/T4.4 | OPEN |
| R-002 | P0 | 凭据、cookie 或浏览器 profile 进入 Git/模型上下文 | .gitignore 复核、secret 扫描、字段化脱敏日志；prompt 不含敏感材料 | G1 T1.1、G5 T5.3 | PARTIAL（G1 已复核：`.workbuddy/`、`var/*`、`*.sqlite3`、`cookies*.json`、`browser-profile/` 均已忽略；扫描 CI 化留待 G5 T5.3） |
| R-009 | P0 | 虚假声明「外部推送与本地 SQLite 绝对原子」，导致重复投递 | 显式补偿/幂等协议文档；delivered-but-not-committed 恢复路径；禁止「绝对原子」表述 | G2 T2.6、G4 T4.4 | OPEN（G0 新增） |
| R-003 | P1 | Genre 等权被 popularity 评分/LLM 质量分/Tier 概率悄悄替代 | Core 纯契约（选择路径无 popularity 输入）+ 等权 property/统计测试 | G2 T2.1、D.3 | OPEN |
| R-004 | P1 | canonical Album 错配导致重复推荐或错误永久排除 | 稳定 canonical ID 优先、置信度感知的字符串降级、歧义记录、混淆 fixtures | G2 T2.4 | OPEN |
| R-005 | P1 | RYM 布局/会话变化破坏按需 enrichment | 薄 adapter、fixtures 优先、缓存 + provenance、人工介入路径、无对抗行为契约 | G3 T3.4 | OPEN |
| R-006 | P1 | 外部数据（RYM/MusicBrainz/critic）产生许可或条款风险 | 每来源 provenance/license/抓取日期记录；发布前 license audit | G3 T3.2/T3.3、G5 T5.3 | OPEN |
| R-008 | P1 | LLM 越权选择或外部文本注入被当作指令执行 | 有界已验证 fact packet、系统指令不可覆盖、输出结构/长度/引用校验、注入隔离测试 | G4 T4.1/T4.2 | OPEN（G0 新增） |
| R-010 | P1 | seed 或输入数据版本未记录导致选择不可复现 | run journal 记录 seed 与输入版本；测试以 input+config+seed 复现 | G2 T2.1/T2.6、G1 T1.5 | OPEN（G0 新增） |
| R-007 | P2 | Executor 与 Reviewer 角色坍塌（自批、替审、凭报告断言） | exact-SHA Gate 协议、verdict 独立工件、禁止 Executor 写 ACCEPTED | 每 Gate 送审 | OPEN |
| R-011 | P2 | 等权统计测试因 flaky 阈值误报 | 非阈值化分布检验 + 固定 seed 基准；property 测试不依赖脆阈值 | G2 D.3 | OPEN（G0 新增） |
| R-012 | P2 | 时区/「每日」边界含糊导致跨日语义错误 | 时间戳一律 UTC ISO 8601；daily window 显式配置（见 OD-5） | G1 T1.4、G4 | OPEN（G0 新增） |
| R-013 | P2 | 社区贡献摩擦（Schema 无版本、模糊匹配静默永久封禁、错误信息模糊） | 版本化 Schema、行/字段级错误、歧义必须记录、贡献指南与演练 | G3 T3.5、G5 T5.4 | OPEN（G0 新增） |

## G1 进展记录（2026-08-19）

- R-002 部分缓解（见上表）：G1 完成 `.gitignore` 复核与验证（`.workbuddy/`、`var/*`、`*.sqlite3` 等已忽略；`git check-ignore` 通过）；secret 扫描 CI 化属于 G5 T5.3。
- R-012 基础已铺：T1.2 schema 强制 `iso8601-date/datetime` 格式；T1.5 时间戳字段全部走 ISO 8601 字符串（UTC 语义由 G4 运行层落实）。
- R-010 基础已铺：`omda.seed`（确定性 RNG、seed 生成）已交付；run journal 的 seed 记录由 G2/T2.6 落实。
- R-001/R-009 的存储侧前提已就绪：journal/history/receipt 表与 append-only 事务写入（G2/T2.6、G4/T4.4 消费）。
- 其余风险保持 OPEN，缓解验证点不变。

## 风险升级规则

- 触发 BLOCKED_ARCHITECTURE 的信号（OPH §6）：改产品不变量/推荐语义、改公开 Schema/持久化/plugin contract、引入新数据库/框架/大型运行时/浏览器自动化依赖、改历史提交时机、访问策略涉及反爬绕过、新增未明确许可的数据集、不可逆迁移或删用户数据。
- 任一 P0/P1 未缓解则对应 Gate 不得 ACCEPTED（SPEC §10）。
