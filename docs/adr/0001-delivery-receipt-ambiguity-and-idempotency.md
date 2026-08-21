# ADR-0001 — Delivery 收据的歧义表示与幂等发送协议（修订版 v2）

- Status: **Proposed**（修订版 v2，等待 GPT-5.6 Sol 复审；评审通过后改
  Accepted，否则 Rejected/Superseded）
- Date: 2026-08-21（修订 v2：2026-08-21）
- Gate: G4（Agent & Delivery），T4.3 / T4.4
- 触发 Reviewer finding：G4-002（P1）——`ambiguous` 状态违反已接受的
  Delivery Port / `DeliveryReceipt` / `delivery_receipt.schema.json` v1 契约；
  同一幂等键直接重放仍产生第二次外部推送；provider 非成功响应被一律当作
  "明确拒绝"并重试。
- 触发流程：Executor 进入 **BLOCKED_ARCHITECTURE**（按 verdict 明确要求
  "stop and submit an ADR"）。
- 修订触发：`reviews/stage-04/ADR_0001_REVIEW.md`（Reviewer commit
  `a699a4955e2e925641ee979a7dd8f26b74beef5f`，结论 **REVISE**），
  finding ADR-001 ~ ADR-005。本修订逐条解决；**仍不修改 production code**。

## 0. 修订记录（ADR-001 ~ ADR-005 响应）

| Reviewer finding | 本修订的解决方案 |
|---|---|
| ADR-001 REGISTERED→SENT 并发双发窗口 | **删除可恢复 REGISTERED 协议**。改为外部调用前**原子创建** operation 于 `IN_FLIGHT_OR_MAY_HAVE_SENT`（与 DELIVERING journal 同一 SQLite 事务，`INSERT ... ON CONFLICT` 保证仅一方成功）；已有任意 operation 行 → 阻止所有其他自动调用方（§4）。崩溃于 claim 后、调用前 = 假歧义 → 人工（availability 取舍，换 at-most-one）。不采用 lease/fencing（成本高且非必需）。 |
| ADR-002 不可变 failed 收据与同 key 重试矛盾 | **分离 DeliveryOperation 与 DeliveryAttempt 两层**；`failed` 对当前 operation 是 **terminal**（不自动重试、不覆盖不可变收据）；人工确认未投递后以**新 generation key**（`<run>:<channel>:<gen>`）开新 operation 并绑定原 run（§5）。 |
| ADR-003 ambiguous 无人工 resolution 路径 | 新增 **append-only `delivery_resolution`** 记录（run/operation/key/attempt/actor/time/reason/outcome），outcome ∈ {CONFIRMED_DELIVERED, CONFIRMED_NOT_DELIVERED, STILL_UNKNOWN}；定义允许转换与恢复动作（§6）。 |
| ADR-004 持久化 API/事务边界未指定 | 定义语义级原子 Port 方法 `begin_delivery_operation` / `finalize_delivery_attempt`（CAS 期望 state+version）/ `record_delivery_resolution`；payload digest（SHA-256）；journal+operation 同事务且网络前 commit；SQLite v1→v2 DDL 草案、两独立连接并发行为与崩溃点（§7、§8）。 |
| ADR-005 4xx 全重试无依据 | **取消笼统 4xx 重试**。自动重试类别收窄为：仅 transport 证明**未发送任何请求字节**（`NoBytesSentError`，连接建立/首字节前失败）；未知响应、5xx、解析失败、写后异常一律 ambiguous/no-retry；认证/参数/配置拒绝 = 该 operation 的 CONFIRMED_FAILED terminal（§9）。 |

## 1. 背景与问题

已接受的跨层契约只允许两种收据状态：

- `src/omda/ports/delivery.py`：`Delivery.deliver(...) -> DeliveryReceipt`，
  docstring 写明 `status "ok" or "failed"`；
- `src/omda/ports/domain.py` 的 `DeliveryReceipt.status: str  # "ok" | "failed"`；
- `data/schemas/delivery_receipt.schema.json` v1：
  `"status": {"enum": ["ok", "failed"]}`。

G4-002 第一轮修复时，`PushPlusDelivery` 在 transport 异常（超时/响应丢失）时
返回 `status="ambiguous"`。该状态**未经 ADR 即扩展了已接受的跨层契约**；
同时 `PushPlusDelivery` 是**无状态**的：同一 key 调用 `deliver()` 两次会发起
两次外部请求并返回两个 `ok` 收据（Reviewer 独立复现 `external_calls=2`）；
既有幂等测试只调用 adapter 一次，重放分支执行 `pass`，属于空洞测试。

存在三个必须由 ADR 解决的架构问题：

1. **歧义没有合法的表示位置**（运行时三分法已预期非二元，持久化契约仍是二元）；
2. **幂等没有执行点**（防重复权威只在恢复路径生效，adapter 不查询、不注册，
   直接重放/并发调用都能绕过）；
3. **"明确拒绝"与"交付歧义"未区分**（任意非 200 都被当"未接受"重试）。

## 2. 术语区分

| 术语 | 定义 | 持久化位置 | 示例 |
|---|---|---|---|
| **Delivery Operation（交付操作）** | 每个稳定幂等键**唯一一个**的交付意图单元；持有 claim、payload digest、状态机 | `delivery_operation` 表（§8） | `run-1:pushplus` 的操作行 |
| **Delivery Attempt（交付尝试）** | 一次对外部 provider 的调用及其不可变证据 | `delivery_attempt` 表（append-only） | attempt `at-…`：outcome=ok |
| **Confirmed failure（确认失败）** | 有**官方文档证明** provider 未接受/未产生副作用（§9 精确类别），或人工确认未投递 | operation=CONFIRMED_FAILED；attempt=failed | 认证拒绝（文档化码） |
| **Ambiguous outcome（交付歧义）** | 无法确认 provider 是否接受/发送 | operation=AMBIGUOUS；attempt=ambiguous | 响应丢失 / 5xx / 解析失败 |
| **Receipt（收据）** | 每幂等键**唯一、不可变、权威**的交付证据（G1-002），ok/ambiguous 每键至多一个 | `delivery_receipt` 表（v2 兼容 v1） | ok / failed / ambiguous |
| **Resolution（人工裁决）** | append-only 人工/操作员决定记录 | `delivery_resolution` 表（§6） | CONFIRMED_DELIVERED |

要点：**Operation 是"意图与归属"，Attempt 是"事实"，Receipt 是"不可变
结论"，Resolution 是"人工结论"**。ambiguous 不等于 failed（未知 ≠ 确认未
送达），也不等于 ok（未知 ≠ 成功）；failed 是 operation 的 terminal 状态。

## 3. 方案比较

### 方案 A：保持现有 `ok|failed`，不新增状态

- 歧义通过异常路径表达（不写收据）→ 收据表无记录 → 恢复无法区分"从未发送"
  与"发送过但未知"，重启后可能重发；仍需 durable intent 记录才能防重（改动面
  反而大于 enum 增项）；RunEngine 三分法兜底成为死代码。
- **结论：否决**（无法满足幂等与"歧义有合法表示位置"）。

### 方案 B：版本化增加 `ambiguous` + operation/attempt/resolution 模型 —— **推荐**

- `delivery_operation`（每 key 一行，状态机）+
  `delivery_attempt`（append-only 不可变尝试记录）+
  `delivery_receipt` v2（enum 增项 + 关联 attempt_id）+
  `delivery_resolution`（append-only 人工裁决）。
- 原子 claim（§4）保证 at-most-one；failed 为 terminal（§5）；歧义有
  人工 resolution（§6）；Port 原子方法 + CAS + digest + DDL（§7/§8）；
  provider 分类钉死文档化码（§9）。
- **结论：采用**（满足 Reviewer 全部验收点；符合 SPEC §5 版本化要求与
  G2-012 三分法；不宣称跨系统原子）。

### 方案 C：没有安全保证时禁用真实 PushPlus

- 零契约变更、零重复推送风险；但 G4-007 的生产 Agent/PushPlus 组合无法
  成立，`--deliver` 保持 dead-end，且需范围变更 ADR 才合法。
- **结论：作为"评审认为任何 schema 变更都不可接受"时的最后手段**
  （届时另提范围变更 ADR）；不作为主选。

## 4. 原子 claim 协议：消除并发双发窗口（ADR-001 修订）

**废弃**上一版的 `REGISTERED → SENT` 双步协议（两进程间存在双发窗口）。
本版采用 Reviewer 首选的保守协议：

1. 外部调用**之前**，`begin_delivery_operation(run_id, key, channel, payload_digest)`
   在**同一个 SQLite 事务**内完成：写 `DELIVERING` journal（含 key 与 digest）
   + `INSERT INTO delivery_operation`（state=`IN_FLIGHT_OR_MAY_HAVE_SENT`，
   version=1）。`INSERT ... ON CONFLICT DO NOTHING` + 事务内 `SELECT` 决定
   返回 `created` 或 `existing` 快照。
2. **已有任意 operation 行 → 该键的权威快照返回给调用方，调用方必须按状态
   决定（§5）：非 CONFIRMED_FAILED 的一切状态都阻止其调用 transport。**
   即：任何已存在的行阻止任何其他自动调用方（含新进程、并发进程）。
3. 网络调用前必须提交的写 = 上述事务（journal + operation 行）。
4. 崩溃在 claim 提交后、外部调用前 → 恢复时该键为
   `IN_FLIGHT_OR_MAY_HAVE_SENT` 且无 attempt → **视为假歧义，要求人工**
   （不自动重发）。这是显式的 availability 取舍：以"崩溃后需人工"换取
   "任何情况下至多一次自动外部请求"的硬保证。
5. **不采用** owner token / lease / fencing 恢复式重发（成本高，且任何
   "可自动重发 REGISTERED"的设计都要求完整的 fencing 证明；保守协议不需要）。

## 5. Operation 状态机与 Attempt（ADR-002 修订）

```text
DeliveryOperation（每稳定 key 一行）
  （不存在）──begin（原子）──> IN_FLIGHT_OR_MAY_HAVE_SENT
                                 │
     finalize(attempt outcome)───┤
                                 ▼
        ┌──────────────┬─────────┴──────────────┐
        ▼              ▼                        ▼
   SUCCEEDED     CONFIRMED_FAILED           AMBIGUOUS
   （ok 收据）   （failed 收据，terminal）  （不可变，无自动重试）
        │              │                        │
        └──┬───────────┘        record_delivery_resolution（人工）
           ▼                    ▼              ▼           ▼
   RESOLVED_DELIVERED   RESOLVED_DELIVERED  RESOLVED_NOT_DELIVERED  STILL_UNKNOWN
   （提交历史，不重推）  （提交历史，不重推） （abandon/新操作）      （保持阻塞）
```

- **DeliveryOperation 与 DeliveryAttempt 分离**：operation 一行 = 归属与
  状态机；attempt 零/一/多行 = append-only 不可变调用证据
  （`attempt_id` PK、operation_key FK、outcome、evidence、attempted_at）。
  自动路径下每 operation 恰好一个 attempt；人工重试会为**新 operation** 追加
  attempt。
- **`failed` 是 terminal**：同 key 的不可变 failed 收据**永不被覆盖/追加**
  （G1-002）；同 key **不自动重试**。如需更正重试：人工 resolution 记录
  CONFIRMED_NOT_DELIVERED（abandon 当前 operation）→ 开**新 operation**，
  使用**新 generation key**（如 `run-1:pushplus:gen2`），并在 resolution 中
  记录对新 key 的引用与原因，保持与原 run 的绑定——不削弱同 run 重放保护
  （重放保护按 operation key 生效，原 key 的任何重放仍被既有行拦截）。
- **每 operation 至多一次自动外部请求**（§10 保证边界）。

## 6. 人工 resolution（ADR-003 修订）

新增 append-only `delivery_resolution` 记录（不修改不可变收据）：

- 字段：`id`、`operation_key`、`run_id`、`idempotency_key`、
  `attempt_id`（可为空）、`outcome`、`actor`、`reason`、`decided_at`。
- outcome ∈ {`CONFIRMED_DELIVERED`, `CONFIRMED_NOT_DELIVERED`,
  `STILL_UNKNOWN`}。
- 允许转换与恢复动作：

| 人工裁决 | 对 operation 的转换 | 恢复动作 |
|---|---|---|
| CONFIRMED_DELIVERED（确认已送达） | AMBIGUOUS / IN_FLIGHT → RESOLVED_DELIVERED | **提交官方历史，不重推**（等价于 ok 收据的 delivered-but-not-committed 路径） |
| CONFIRMED_NOT_DELIVERED（确认未送达） | AMBIGUOUS / IN_FLIGHT → RESOLVED_NOT_DELIVERED | **abandon 当前 operation**；如要重试，开新 generation operation（§5），不静默复用被阻塞的 key |
| STILL_UNKNOWN（仍未知） | 维持 AMBIGUOUS | **保持阻塞**（no-send / no-commit），等待再次人工 |

- resolution 是 append-only：每次裁决追加一条，状态机按最新记录推进；记录
  必须绑定 run/operation/key/attempt/actor/time/reason，供审计。
- 未决议的 AMBIGUOUS 永不自动重推、永不自动提交历史。

## 7. 持久化 API 与事务边界（ADR-004 修订）

### Port 方法（语义级原子，全部经 `HistoryPort` 暴露）

1. `begin_delivery_operation(run_id, idempotency_key, channel, payload_digest)
   -> DeliveryOperationSnapshot`
   - 同一 SQLite 事务：append `DELIVERING` journal（含 key+digest）+
     `INSERT ... ON CONFLICT DO NOTHING` operation 行（state=
     IN_FLIGHT_OR_MAY_HAVE_SENT, version=1）；
   - 返回 `created=True, snapshot` 或 `created=False, existing`；
   - 调用方规则：`created=False` 时按 §5 状态表决定——除 CONFIRMED_FAILED
     的"人工新操作路径"外，**一律不得调用 transport**。
2. `finalize_delivery_attempt(operation_key, expected_version, attempt_id,
   outcome, evidence, attempted_at) -> DeliveryOperationSnapshot`
   - **CAS**：`UPDATE delivery_operation SET state=…, version=version+1
     WHERE operation_key=… AND version=expected_version`（RETURNING）；
    写入 append-only attempt 行 + 不可变 receipt（ok/failed/ambiguous）同一
    事务；`affected==0` → 冲突异常（fail-closed，绝不覆盖既有证据）。
3. `record_delivery_resolution(operation_key, run_id, idempotency_key,
   attempt_id, outcome, actor, reason, decided_at) -> DeliveryOperationSnapshot`
   - append-only resolution 行 + CAS 推进 operation 状态
     （AMBIGUOUS/IN_FLIGHT → RESOLVED_*）同一事务。
4. `find_delivery_operation(idempotency_key) -> snapshot | None`（只读）；
   既有 `find_delivery_receipt` / `save_delivery_receipt` 保留（G1-002 语义）。

### payload digest

- `payload_digest = SHA-256(payload_bytes)`，begin 时记录，finalize/复用前校验；
- **同 key 不同 digest → fail-closed（不达网络）**——同一 key 不可重放不同内容
  （验收 5）。

### 事务边界

- 网络调用前必须提交的写：`begin_delivery_operation`（journal DELIVERING +
  operation 行）——即 §4 的原子 claim；
- attempt + receipt + operation 状态推进在同一事务（finalize）；
- resolution + operation 状态推进在同一事务；
- journal 的其余追加（PLANNED…VALIDATED、DELIVERED/FAILED/RECOVERING、
  HISTORY_COMMITTED/COMPLETE）沿用 G2 既有事务语义，不在此变更。

## 8. SQLite v1 → v2（ADR-004 修订）

- `PRAGMA user_version` 1 → 2；v1 的 `delivery_receipt` 表**保留且只读兼容**
  （旧 ok/failed 行仍有效；不改写——G1-002）。
- 新增表（草案，实现时以迁移脚本为准）：

```sql
CREATE TABLE delivery_operation (
  operation_key   TEXT PRIMARY KEY,          -- 稳定幂等键
  run_id          TEXT NOT NULL,
  channel         TEXT NOT NULL CHECK (channel IN ('markdown','pushplus')),
  payload_digest  TEXT NOT NULL,             -- SHA-256 hex
  state           TEXT NOT NULL CHECK (state IN
                    ('IN_FLIGHT_OR_MAY_HAVE_SENT','SUCCEEDED',
                     'CONFIRMED_FAILED','AMBIGUOUS',
                     'RESOLVED_DELIVERED','RESOLVED_NOT_DELIVERED')),
  version         INTEGER NOT NULL DEFAULT 1, -- CAS 计数器
  created_at      TEXT NOT NULL
);
CREATE TABLE delivery_attempt (
  attempt_id      TEXT PRIMARY KEY,
  operation_key   TEXT NOT NULL REFERENCES delivery_operation(operation_key),
  outcome         TEXT NOT NULL CHECK (outcome IN ('ok','failed','ambiguous')),
  evidence        TEXT NOT NULL,             -- provider 响应摘要/异常类别
  attempted_at    TEXT NOT NULL
);
CREATE INDEX idx_attempt_op ON delivery_attempt(operation_key);
CREATE TABLE delivery_resolution (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  operation_key   TEXT NOT NULL REFERENCES delivery_operation(operation_key),
  run_id          TEXT NOT NULL,
  idempotency_key TEXT NOT NULL,
  attempt_id      TEXT,
  outcome         TEXT NOT NULL CHECK (outcome IN
                    ('CONFIRMED_DELIVERED','CONFIRMED_NOT_DELIVERED','STILL_UNKNOWN')),
  actor           TEXT NOT NULL,
  reason          TEXT NOT NULL,
  decided_at      TEXT NOT NULL
);
CREATE INDEX idx_resolution_op ON delivery_resolution(operation_key);
```

- 约束要点：`operation_key` PK 即并发唯一裁判；attempt 追加不可变；
  resolution append-only；状态/outcome 用 CHECK 约束 fail-closed。
- **两个独立连接并发行为**（验收 1/2）：`BEGIN IMMEDIATE` 事务下
  `INSERT … ON CONFLICT DO NOTHING` → 仅一方插入成功并获得 created；
  另一方拿到既有行快照 → 阻止 transport；finalize 的 CAS 同理。并发测试
  使用两个独立 `sqlite3` 连接（非共享内存）。
- 迁移/回滚：v1→v2 迁移不触碰旧行；v2→v1 回滚前导出 AMBIGUOUS /
  RESOLVED_* 清单交人工处置，v1 读取器对未知状态 fail-closed（读失败而非
  误判 ok/failed）。

## 9. provider 响应分类（ADR-005 修订）

`HttpTransport` 升级为**类型化结果**：`ProviderSuccess(body)` /
`ProviderDefinitiveRejection(http_status, code, msg)` /
`NoBytesSentError`（连接建立/首字节写出前失败，可证明未发送任何请求字节）/
`AmbiguousFailure`（超时、连接重置、EOF、解析失败、写后异常、5xx、
未知业务码）。

| 观测 | 分类 | 自动动作 |
|---|---|---|
| PushPlus 文档化成功码（`code == 200`） | 成功 | finalize → SUCCEEDED / receipt ok；不重试 |
| `NoBytesSentError`（可证明未发送字节） | 无副作用 | **唯一允许的自动重试类别**，有界（≤ `max_retries`）；其余一律不自动重试 |
| 认证/参数/配置拒绝（文档化且明确未入队的精确类别） | CONFIRMED_FAILED terminal | finalize → failed 收据；**不是重试循环**（改输入需人工开新 operation） |
| 未文档化/未知业务码、HTTP 5xx、解析失败、响应丢失、写后 transport 异常 | AMBIGUOUS | finalize → ambiguous 收据；**no-retry**，进 RECOVERING/人工 |
| provider 提供真实服务端幂等保证（未来） | 由届时文档补充 | 仅在文档证明下放宽 |

- **原则**：只允许**官方文档证明"请求未产生副作用"的精确类别**自动重试；
  PushPlus 当前文档无此承诺的类别一律 no-retry。绝不对任意非成功响应推断
  "未投递"。

## 10. 保证边界（明确声明）

- OMDA **保证：每个 delivery operation 至多一次自动外部请求**——由
  §4 原子 claim（网络前持久化保守状态）+ §9 无自动歧义重试共同实现。
- OMDA **不宣称** provider 端 exactly-once：PushPlus /send 无服务端幂等键，
  远程恰好一次无法保证（SENT→evidence 之间崩溃的极小窗口除外，此时
  REQUIRE_HUMAN 而非重发，来自 OMDA 的自动调用至多一次）。
- **不宣称 PushPlus 与 SQLite 跨系统原子**（SPEC §4）：协议为"先推送
  （稳定 key）→ 持久化证据 → 提交本地历史"；ok+commit 失败 → 只提交本地
  历史；ambiguous → 人工；不虚构分布式事务。

## 11. rollout / rollback / 恢复

- **rollout**：① schema v2 DDL（新表 + user_version=2，旧表只读保留）→
  ② Port 原子方法 → ③ adapter 切换（begin→transport→finalize）→
  ④ 恢复/CLI 接线。旧 ok/failed 收据继续有效。
- **rollback**：v2→v1 前导出 AMBIGUOUS/RESOLVED_* 清单人工处置；v1 读取器
  对未知状态 fail-closed；不删除数据。
- **恢复**：`RunEngine.recover()` 只读 durable 证据——journal tail +
  operation 快照 + receipt + resolution：
  - operation=SUCCEEDED / RESOLVED_DELIVERED（+绑定证据）→ COMMIT_HISTORY，
    不重推；
  - operation=AMBIGUOUS（无 resolution）→ REQUIRE_HUMAN（不重推不提交）；
  - operation=CONFIRMED_FAILED / RESOLVED_NOT_DELIVERED → 不提交历史；
    重试仅经人工开新 generation operation；
  - operation 缺失但 journal 有 DELIVERING → 从未完成 claim（崩溃于
    begin 之前）→ 可安全重新 begin（无外部副作用证据）。

## 12. 验收测试（本地 fake/fixture，零 live 调用；纳入 Reviewer 10 项）

| # | 验收 | 测试设计 |
|---|---|---|
| 1 | 两独立 SQLite 连接竞争同一缺失 key | 仅一方获 created 授权；外部调用 `<= 1` |
| 2 | 第二调用方在 claim 与 send 之间到达 | 看到既有行 → 从不调用 transport（calls==1） |
| 3 | claim 后、调用前崩溃 | 重启不自动发送；状态显式 AMBIGUOUS/人工（保守协议） |
| 4 | 调用后、证据前崩溃 | 重启不自动发送（attempt 缺失 → 人工） |
| 5 | 同 key 不同 payload digest | 网络前 fail-closed（calls==0） |
| 6 | 既有 ok / ambiguous(in-flight) / resolved-delivered 证据 | 永不重发（calls 不增） |
| 7 | `failed` 终态与不可变证据 | 同 key 不覆盖不重试；attempt/operation 基数断言 |
| 8 | 人工裁决三结果 | CONFIRMED_DELIVERED 提交历史不重推；CONFIRMED_NOT_DELIVERED 走 abandon/新 operation；STILL_UNKNOWN 保持阻塞 |
| 9 | schema v2 + SQLite 迁移 v2 | 接受旧 v1 行；校验每个新状态；降级/fail-closed 保留数据 |
| 10 | 类型化 provider 响应 | 精确文档化码 + 未知 4xx、5xx、畸形体、超时、连接重置、响应丢失 全表断言 |

崩溃窗口（§4/§8 映射到验收 3/4）：`begin 前崩溃`（无 operation）→ 安全重
begin；`begin 后、调用前崩溃`（IN_FLIGHT 无 attempt）→ 假歧义人工（验收 3）；
`调用后、finalize 前崩溃`（IN_FLIGHT 有/无 attempt 但无 evidence）→ 人工
（验收 4）；`finalize 后崩溃` → 按 operation 状态恢复。

## 13. 受影响契约与文件（Accepted 后）

- `src/omda/ports/delivery.py`：docstring 三态 + 幂等/原子义务；
- `src/omda/ports/domain.py`：`DeliveryReceipt.status` 注释
  `# "ok" | "failed" | "ambiguous"`，新增 operation/attempt/resolution 快照类型；
- `data/schemas/delivery_receipt.schema.json`：v2（enum 增项 + attempt_id）；
- 新增 `delivery_operation` / `delivery_attempt` / `delivery_resolution`
  DDL 与迁移脚本（v1→v2）；
- `src/omda/ports/history.py`：§7 四个新方法；
- `src/omda/adapters/delivery.py`：begin→transport→finalize、§9 分类、
  `NoBytesSentError` 唯一自动重试；
- `src/omda/orchestrator/run.py` / `recovery.py`：接线新 Port 与 §11 恢复；
- 测试：`tests/unit/test_delivery_adapters.py` 空洞重放测试替换为 §12 矩阵。

## 14. 决策与下一步

- **决策**：采用**方案 B**（版本化增加 ambiguous + operation/attempt/
  resolution 模型 + 原子 claim + 保守 provider 分类）。
- **本 ADR 为 Proposed（修订 v2）**：等待 GPT-5.6 Sol 复审。评审期间
  Executor 不修改 production code，不修复 G4-005/G4-007，不进入 G5。
- 评审通过 → 更新本 ADR 为 Accepted 并按其实现 G4-002 修复；
  评审否决 → 按 Reviewer 意见再修订。
