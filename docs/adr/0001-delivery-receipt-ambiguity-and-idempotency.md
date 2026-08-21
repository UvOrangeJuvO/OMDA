# ADR-0001 — Delivery 收据的歧义表示与幂等发送协议

- Status: **Proposed**（等待 GPT-5.6 Sol 评审；评审通过后改 Accepted，否则 Rejected/Superseded）
- Date: 2026-08-21
- Gate: G4（Agent & Delivery），T4.3 / T4.4
- 触发 Reviewer finding：G4-002（P1）——`ambiguous` 状态违反已接受的
  Delivery Port / `DeliveryReceipt` / `delivery_receipt.schema.json` v1 契约；
  同一幂等键直接重放仍产生第二次外部推送；provider 非成功响应被一律当作
  "明确拒绝"并重试。
- 触发流程：Executor 进入 **BLOCKED_ARCHITECTURE**（按 verdict 明确要求
  "stop and submit an ADR"，以及用户指令"若现有 Port 无法安全表达交付歧义，
  停止实现，进入 BLOCKED_ARCHITECTURE 并提交 ADR"）。
- 本 ADR 期间**不修改 production code**；只提交 ADR、状态与必要报告。

## 1. 背景与问题

已接受的跨层契约只允许两种收据状态：

- `src/omda/ports/delivery.py`：`Delivery.deliver(...) -> DeliveryReceipt`，
  docstring 写明 `status "ok" or "failed"`；
- `src/omda/ports/domain.py` 的 `DeliveryReceipt.status: str  # "ok" | "failed"`；
- `data/schemas/delivery_receipt.schema.json` v1：
  `"status": {"enum": ["ok", "failed"]}`。

G4-002 第一轮修复时，`PushPlusDelivery` 在 transport 异常（超时/响应丢失）时
返回 `status="ambiguous"`。该状态**未经 ADR 即扩展了已接受的跨层契约**：
独立的 schema 校验以 `value 'ambiguous' not in enum ['ok', 'failed']` 拒绝。
同时 `PushPlusDelivery` 是**无状态**的：同一 key 调用 `deliver()` 两次会发起
两次外部请求并返回两个 `ok` 收据（Reviewer 独立复现 `external_calls=2`）；
既有幂等测试 `test_same_idempotency_key_does_not_cause_second_push` 只调用
adapter 一次，重放分支执行 `pass`，属于空洞测试。

因此存在三个必须由 ADR 解决的架构问题：

1. **歧义没有合法的表示位置**：运行时状态机（G2-012 三分法
   DELIVERING/DELIVERED/RECOVERING，`RunEngine._deliver_and_commit` 已有
   "every OTHER value → RECOVERING" 兜底）在语义上已经预期非二元结果，
   但持久化收据契约仍是二元的——跨层缝隙未文档化。
2. **幂等没有执行点**：防重复的唯一权威（`HistoryPort` 收据的
   G1-002 不可变/幂等语义）只在 Orchestrator 恢复路径生效；adapter 本身
   不查询、不注册，直接重放/并发调用都能绕过。
3. **"明确拒绝"与"交付歧义"未区分**：任何非 200 响应都被假设为
   "provider 未接受"而重试；但 5xx/业务错误码/响应丢失都可能意味着
   provider 已入队，重试会造成重复推送。

## 2. 术语区分（设计点 1）

| 术语 | 定义 | 持久化位置 | 示例 |
|---|---|---|---|
| **Delivery Attempt（交付尝试）** | 对 provider 发起的一次外部调用，含 attempt_id、时间、调用边界 | `delivery_intent` outbox（新记录，见 §5） | attempt `at-001` 于 2026-08-21T00:00:01Z 调 PushPlus /send |
| **Confirmed failure（确认失败）** | provider **明确**表示未接受/未发送（只有 §6 分类表中"明确拒绝"类） | `delivery_receipt.status="failed"` | 认证失败 401（provider 未处理请求） |
| **Ambiguous outcome（交付歧义）** | 无法确认 provider 是否接受/发送（超时、连接重置、响应丢失、5xx、未文档化的业务错误码） | `delivery_receipt.status="ambiguous"`（v2 新增） | 请求已发出但响应丢失 |
| **Receipt（收据）** | 每幂等键**唯一、不可变、权威**的交付证据（G1-002） | `delivery_receipt` 表（v2） | ok / failed / ambiguous 之一 |

要点：

- **Attempt 是"事实"，Receipt 是"结论"**。一次 deliver() 最多产生一个
  attempt；attempt 结束于三种结论之一：ok（已发送）、failed（明确未发送）、
  ambiguous（未知）。
- **ambiguous 不等于 failed**：failed 是"确认未送达"，ambiguous 是
  "可能已送达、可能未送达"。两者对恢复动作的语义完全不同
  （见 §4/§7）。
- **ambiguous 不等于 ok**：不得把未知当成功提交官方历史。

## 3. 方案比较（设计点 8）

### 方案 A：保持现有 `ok|failed`，不新增状态

- **含义**：收据保持二元；歧义通过**异常路径**表达（adapter 抛
  `DeliveryAmbiguousError`，Orchestrator 捕获后 journal RECOVERING 且
  **不写收据**）；同 key 防重依赖 `HistoryPort` 收据幂等 + 恢复决策。
- **优点**：schema/Port/domain 零变更；改动集中在 adapter 异常分类。
- **缺点**：
  1. "不写收据"意味着该 key 在收据表中无记录——恢复时
     `find_delivery_receipt` 返回 None，无法区分"从未发送"与"发送过但结果
     未知"，**进程重启后可能重发**（违反幂等验收）；
  2. 要真正防重/防并发，仍需引入 durable intent/outbox 记录（§5）——
     这本身就是新契约与新表，改动面反而大于"enum 增项 + Port 文档"；
  3. RunEngine 三分法已存在的 "unrecognized status → RECOVERING" 兜底
     在二元 schema 下永远不可达，成为死代码，跨层缝隙悬空。
- **验收满足度**：重放/并发防重可满足（若引入 outbox），但"歧义有合法
  表示位置"与"Port 契约如实描述能力"不满足；违背"stale/corrupt 证据不能
  授权历史提交"的保守原则（无收据 = 无证据 = 只能 REQUIRE_HUMAN，导致
  每次歧义都永久卡人工，且丢失 attempt 证据）。

### 方案 B：版本化增加 `ambiguous`（及 attempt 字段）—— **推荐**

- **含义**：`delivery_receipt` schema v2 将 `status.enum` 扩展为
  `["ok", "failed", "ambiguous"]`，可选新增 `attempt_id` 字段；Delivery Port
  docstring、`DeliveryReceipt` 注释同步三态；新增 `delivery_intent` outbox
  表（UNIQUE `idempotency_key`）作为外部调用前的 durable 注册；写入顺序按
  §5；provider 拒绝/歧义分类按 §6；恢复决策按 §7。
- **优点**：
  1. 歧义有**合法、持久化、跨层一致**的表示位置，与 G2-012 运行时三分法
     对齐（"unrecognized status → RECOVERING" 兜底变成显式第三态）；
  2. outbox UNIQUE 键在**外部调用之前**拦截同 key 的并发/重放（§4），
     这是唯一能真正防并发的机制；
  3. enum 增项是向后兼容的 schema 演化（v1 记录仍有效、不可变不改写，
     符合 G1-002）；符合 SPEC §5 "每个持久记录带 schema version"；
  4. ambiguous 收据在恢复时给出确定性动作（REQUIRE_HUMAN 不重发），
     不丢失 attempt 证据。
- **缺点**：需要改 Port 文档、domain 注释、schema v2、adapter、Orchestrator
  接线、迁移/回滚文档（§7/§8）；均为 G4 T4.3/T4.4 授权范围。
- **验收满足度**：Reviewer 全部验收点可满足——直接重放、重启、并发恰一次
  外部副作用（在文档化保证内）；schema 校验通过；明确拒绝与歧义可区分。

### 方案 C：没有安全保证时禁用真实 PushPlus

- **含义**：在幂等/歧义模型落地前，`--deliver` 保持 dead-end（不提供真实
  PushPlus transport），仅在显式配置 + 文档化"存在重复投递风险"时启用；
  或完全推迟到后续 Gate。
- **优点**：零契约变更、零重复推送风险、实现量最小。
- **缺点**：G4-007 要求的生产 Agent/PushPlus 组合无法成立，`--deliver`
  仍是死路；Reviewer 明确要求"不要静默把生产功能实现移入 G5 audit；
  Gate 归属变更须用 ADR/plan 更新"——方案 C 实际上要求一个**范围变更 ADR**
  才能合法；产品功能推迟交付。
- **验收满足度**：幂等/歧义验收全部"真空通过"，但 T4.3/T4.5 里程碑 FAIL。

### 结论

**采用方案 B**。理由：它是唯一同时满足 (a) 歧义有合法跨层表示、
(b) 同 key 重放/重启/并发不二次推送（靠 outbox UNIQUE + receipt 幂等）、
(c) 明确拒绝与歧义可区分、(d) 不宣称跨系统原子的方案；且都在 G4 授权范围
内，无需 Gate 归属变更。方案 A 作为"评审认为 schema 变更过重"时的降级备选；
方案 C 作为"评审认为任何 schema 变更都不可接受"时的最后手段（届时需另提
范围变更 ADR）。

## 4. 防止同一 key 二次推送（设计点 3）

目标：在**明确文档化的保证范围**内，同一幂等键的 (a) 直接重放、(b) 进程
重启、(c) 并发调用都不能从 OMDA 侧发出第二次外部调用。

- 权威机制是**本地的 durable ledger**，不是 adapter 内存，也不是 provider
  （PushPlus /send 无服务端幂等键，无法在 provider 侧去重——这一点必须
  如实声明，见 §6）。
- **先注册、后发送（reserve-before-send）**：
  1. 外部调用**之前**，先向 `delivery_intent` 插入
     `(idempotency_key PRIMARY KEY, run_id, channel, attempt_id, state='REGISTERED')`；
  2. 唯一约束保证**并发**下只有一个调用方能注册成功，另一方收到
     conflict → fail-closed（REQUIRE_HUMAN / 幂等返回既有收据），
     绝不发起第二次外部调用；
  3. 注册成功后调用 provider，随后写 receipt（ok/failed/ambiguous），
     并将 intent 置 `SENT` → `RECEIPTED`。
- **直接重放**：Orchestrator/adapter 在调用前查 receipt 与 intent：
  已存在 ok/ambiguous 收据 → 返回既有收据（或按 §7 恢复），不调用外部；
  intent 已存在但无收据 → 按 §5 崩溃窗口规则处理，不盲重发。
- **进程重启**：`RunEngine.recover()` 只读 durable 证据：
  journal tail + receipt + intent；没有 ok/ambiguous 收据的 DELIVERING tail
  必须能区分"从未发送"（intent REGISTERED 无 SENT → 允许重发一次）与
  "已发送但结果未知"（SENT 无 RECEIPTED → REQUIRE_HUMAN，不重发）。
- **并发调用**：唯一约束即最终裁判；任何绕过查询的竞态都被数据库层拦截。
- **保证边界（如实声明）**：OMDA 保证"同 key 的并发/重放不会从 OMDA 侧
  发出第二次调用"（本地 ledger 硬保证）；由于 PushPlus 无服务端去重，
  "provider 侧恰好一次"是 best-effort（SENT→RECEIPTED 之间崩溃的极小窗口
  除外，此时 REQUIRE_HUMAN 而非重发，副作用至多一次未知——绝不超过一次
  来自 OMDA 的调用）。

## 5. durable intent / receipt 写入顺序与崩溃窗口（设计点 5）

单次交付的持久化顺序（全部在本地 SQLite，与 journal 同一事务边界 T1.5）：

| 步骤 | 写入 | 崩溃于此步之后 | 恢复动作 |
|---|---|---|---|
| ① | journal `DELIVERING`（含 idempotency_key） | 无外部副作用 | 重新从 ① 开始（幂等） |
| ② | `delivery_intent` 插入（UNIQUE key, state=REGISTERED） | **未调用 provider** | intent 无 SENT 标记 → 允许重发一次（安全：无外部副作用证据） |
| ③ | 调用 provider（前置 intent state=SENT） | **外部调用可能已发出**，未写收据 | intent=SENT 且无收据 → **歧义 → REQUIRE_HUMAN，绝不重发** |
| ④ | 写 receipt（ok/failed/ambiguous，G1-002 不可变） | 收据已存在 | 幂等复用，不重发 |
| ⑤ | journal `DELIVERED`（ok）/ `FAILED`（bound failed）/ `RECOVERING`（ambiguous/不匹配） | 三分法状态已持久 | 按 G2-012/recovery 恢复 |
| ⑥ | `commit_history`（G1-001 全有或全无） | 已交付未提交 | delivered-but-not-committed → COMMIT_HISTORY，不重发 |

- receipt 写入必须保持 G1-002：exact replay no-op、conflicting write
  fail-closed、成功收据永不被覆盖。
- **不宣称跨系统原子**（设计点 6）：PushPlus 与本地 SQLite 是两个独立
  系统，OMDA 不实现、不宣称二者之间的分布式原子性（SPEC §4：
  "No implementation may claim atomicity across an external push service and
  local SQLite"）。协议是：稳定幂等键先推送 → 持久化收据 → 提交本地历史；
  "ok 收据 + commit 失败" → 只提交本地历史；"ambiguous 收据" → 人工介入。

## 6. provider 非成功响应分类（设计点 4）

`HttpTransport` 契约升级为可暴露 **HTTP status 与响应体**（或分类异常）后，
PushPlus 响应按下表分类（以 provider 文档为准，未文档化的码一律保守）：

| 观测 | 分类 | 动作 |
|---|---|---|
| `code == 200`（或 HTTP 2xx + 业务成功） | 成功 | `ok`，不重试 |
| HTTP 4xx（认证/参数错误，provider 明确未处理） | **明确拒绝** | confirmed failure：有界重试（安全，provider 未接受）→ 耗尽 `failed` |
| HTTP 5xx | **歧义**（服务端可能已入队） | `ambiguous`，**不重试** |
| 超时 / 连接重置 / EOF / 响应解析失败 | **歧义**（响应丢失，请求可能已接受） | `ambiguous`，**不重试** |
| 业务码非 200 但 provider 文档未声明"未入队" | **歧义**（默认保守） | `ambiguous`，不重试 |

原则：**只有可证明"provider 未接受"的响应才是 confirmed failure**；任意
非成功响应一律推断为未投递是错误假设（Reviewer 明确指出）。

## 7. 恢复语义（设计点 5 续）

`resolve_recovery_action`（已含 G4-004 绑定强化）在三态下：

- journal tail ∈ {DELIVERING, DELIVERED, RECOVERING} + receipt ok（run/key/
  channel 全绑定）→ `COMMIT_HISTORY`（不重发）；
- journal tail ∈ {DELIVERING, DELIVERED, RECOVERING} + receipt ambiguous →
  `REQUIRE_HUMAN`（不重发、不提交历史）；
- receipt failed（绑定）→ 已确认未送达 → 可安全重试交付（新 attempt，
  复用同一 key，因为无外部副作用）；若重试仍失败 → 终止；
- intent 存在但无收据：REGISTERED 无 SENT → 允许重发一次；SENT 无
  RECEIPTED → `REQUIRE_HUMAN`（歧义，不重发）；
- 证据缺失/不匹配 → `REQUIRE_HUMAN`（维持 G4-004 语义）。

## 8. rollout / rollback / 验收测试（设计点 7）

### rollout

1. 先合入 `delivery_receipt` schema **v2**（enum 增项 + 可选 attempt_id）
   与读取器（接受 v1/v2；未知状态 fail-closed）；
2. 再合入 `delivery_intent` 表与 reserve-before-send 协议；
3. 最后切换 adapter 分类（§6）与恢复决策（§7）；
4. v1 旧收据记录只读保留（不可变，不改写——G1-002）。

### rollback

- 回退到 v1 代码时，v2 记录中 `status="ambiguous"` 条目会被 v1 校验拒绝
  ——**回退前必须**：导出 ambiguous 记录清单交由人工处置（REQUIRE_HUMAN
  清单），或在 v1 读取器中保留"未知状态 fail-closed"（读失败而非误判
  ok/failed）。回退不得静默把 ambiguous 当 failed/ok。
- 回退后 `delivery_intent` 表保留（无写入即可），不删除数据。

### 验收测试（全部本地 fake/fixture，零 live 调用；可执行计数器）

| 验收 | 测试 |
|---|---|
| 直接重放 | 同 key 连续两次 deliver() → 外部调用恰 1 次（第二个调用被 receipt/intent 拦截返回既有收据） |
| 进程重启 | deliver → 模拟崩溃（收据已写、commit 未做）→ 新 RunEngine 实例 recover() → 外部调用仍 1 次 |
| 并发 | 两线程/两"进程"同 key 同时 deliver → UNIQUE 冲突 fail-closed，外部调用恰 1 次 |
| 歧义不重试 | transport 超时 → `status="ambiguous"`、calls==1、零退避、RunEngine → RECOVERING |
| 明确拒绝重试 | 4xx 连续失败 → 有界重试后 `failed`；期间每次都是新 attempt 但同 key |
| schema 校验 | ambiguous 收据通过 v2 schema；v1 校验拒绝 ambiguous（fail-closed） |
| 恢复绑定 | ok/ambiguous 收据 + 绑定 journal → 相应动作；无证据 → REQUIRE_HUMAN |
| 崩溃窗口 | REGISTERED 无 SENT → 重发一次；SENT 无 RECEIPTED → REQUIRE_HUMAN |

## 9. 受影响契约与文件（Accepted 后）

- `src/omda/ports/delivery.py`：docstring 三态 + 幂等义务；
- `src/omda/ports/domain.py`：`DeliveryReceipt.status` 注释
  `# "ok" | "failed" | "ambiguous"`，新增可选 `attempt_id`；
- `data/schemas/delivery_receipt.schema.json`：v2（enum 增项 + attempt_id）；
- 新增 `delivery_intent` 表定义（SQLite，UNIQUE idempotency_key）与
  HistoryPort 两个方法（`register_delivery_intent` / `find_delivery_intent`）；
- `src/omda/adapters/delivery.py`：reserve-before-send、§6 分类、无状态
  消除（幂等查询收据）；
- `src/omda/orchestrator/recovery.py`：§7 决策；
- 测试：`tests/unit/test_delivery_adapters.py` 空洞重放测试替换为 §8 验收。

## 10. 决策与下一步

- **决策**：采用**方案 B**（版本化增加 ambiguous + attempt 字段 +
  durable intent outbox + reserve-before-send + 明确拒绝/歧义分类）。
- **本 ADR 为 Proposed**：等待 GPT-5.6 Sol 评审。评审期间 Executor 不修改
  production code，不修复 G4-005/G4-007，不进入 G5。
- 评审通过 → 更新本 ADR 为 Accepted 并按其实现 T4.3/T4.4 修复；
  评审否决 → 按 Reviewer 意见修订或改选方案 A/C。
