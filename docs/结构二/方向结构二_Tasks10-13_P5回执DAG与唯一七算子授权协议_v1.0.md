# 结构二：Tasks 10–13/P5 回执 DAG 与唯一七算子授权协议 v1.0

日期：2026-09-05
协议：`structure-two-trusted-seven-operator-ablation-authorization@1.0`

## 当前结论

```text
trusted_seven_operator_ablation_authorized = false
seven_operator_ablation_must_not_run = true
```

仓库内策略的 trust-anchor 状态为 `NOT_ENROLLED`，Gate B v0.8、Tasks 7–13、P5 和两轮 P0
对抗审计也没有组成同一个 fresh（新鲜）、受信且完整的正式回执 DAG。因此本协议只冻结授权机制，
没有运行七算子消融，也没有把测试夹具写成科学证据。

## 1. 唯一身份与唯一出口

七算子身份和顺序冻结为：

```text
OPCEU
ORRER_CHEH
PCHMP
CF-BOCPD
RGRC
CCRR
CIAV
```

Task 9 只能接受 `structure-two-task9-four-coupling-protocol@1.1` 和
`structure-two-task9-operator-implementations@1.1`。`CHEH`、旧 v1.0 协议或旧 coupling 名称均不能
替代 `ORRER_CHEH`。算子可以在某个 episode 中 enabled-no-op（已启用但没有状态改变），但该 no-op
必须进入认证 runtime receipt（运行时回执）；不能把“没有调用记录”解释成已启用。

唯一可能输出正向执行令牌的类型是：

```text
TrustedSevenOperatorAblationAuthorization
```

旧 task report、`BindingCandidateDiagnostic`、配置文件中的布尔值以及单项 pass 均不是授权出口。

## 2. Typed receipt DAG

正式依赖图为：

```text
Task 10 -> Task 11 -> Task 12 -> Task 13
                         \-----> P5

Gate B v0.8, Task 7, Task 8, Task 9, Task 10..13, P5
    -> audit round 1
    -> audit round 2 (also parents audit round 1)
    -> TrustedSevenOperatorAblationAuthorization
```

Task 13 与 P5 是 Task 12 之后的两条独立分支；P5 不偷渡或选择 differentiability strategy（可微
策略）。两轮审计都必须把九个科学/骨干依赖作为父回执，第二轮还必须把第一轮作为父回执。

每条正式 receipt 均包含并签名：

- 独立 `receipt_kind`、`protocol_id`、`receipt_id` 和共同 `run_id`；
- `ORRER_CHEH` 选定身份及精确父 receipt 的 ID/content SHA-256；
- source bundle、config、spec、result 四个独立 SHA-256；
- producer 与 independent verifier 的不同身份；
- `issued_at_utc`、`verified_at_utc`、冻结 freshness window 和精确 expiry；
- producer → evidence custodian → independent verifier 的连续 custody（保管）链；
- nonce、replay registry ID、trust-anchor manifest SHA-256；
- 已登记 Ed25519 公钥身份和覆盖整个回执的签名。

trust-anchor manifest 自身必须由独立 registry authority 签名。每一种 receipt 使用不同 authority 和
不同 Ed25519 key；候选实现拿到的是 public verifier（公钥验证器），不能获得签发能力。

## 3. Replay、freshness 与失效传播

验证器按拓扑顺序重新验证模型、父类型、父 content hash、run、时间、custody、登记公钥及签名，最后
才原子消费 nonce。以下任一情况使节点无效：

- 缺失或错误签名；
- 未登记/被替换的 trust anchor；
- 过期、未来时间或不一致 freshness window；
- nonce replay（重放）；
- source/config/spec/result hash 被换；
- 跨 task、跨 protocol、跨 run 替换；
- 父类型、父 ID、父 content hash 或父时间不一致；
- `model_copy` 绕过构造期校验；
- 调用方自报 pass 或 recomputed 布尔值。

父节点无效、缺失或过期后，所有后代标为 `BLOCKED_BY_PARENT`。聚合器返回每一项的独立 blocker，
不允许其他通过项补偿。

## 4. Task 12：从 raw proposal trace 重算

正式 Task 12 receipt 不采信旧 `Task12GateOutcomes` 布尔值。它携带原始有限状态 MH trace：

- `(H,R,I,C,Z)` 五轴 typed state（类型化状态）、action 和 utility；
- 目标概率 `pi(x)` 与完整 proposal matrix `q(y|x)`；
- 每个 proposal 的 source、proposed state、uniform draw、accepted 和 resulting state；
- burn-in、elementary evaluation count；
- full-rerun reference action distribution 与 expected utility。

验证器先逐 event 重算：

```text
alpha(x,y) = min(1, pi(y) q(x|y) / [pi(x) q(y|x)])
```

然后重建完整 MH transition matrix，并从原始 trace 重算：

- maximum detailed-balance error；
- stationarity error；
- acceptance rate；
- lag-one ESS / elementary evaluation；
- action-distribution total variation 与 expected-utility difference；
- `(H,R,I,C,Z)` 五轴是否全部实际跳转；
- non-self move 数量。

阈值固定为 `1e-9 / 1e-9 / [0.01,1.0] / 0.01 / 0.05 / 0.05`。selected kernel、raw
trace hash、重算结果共同决定 result hash。调用方修改 gate 布尔、accepted path、action reference、结果
hash 或 selected kernel 均不能生成有效正式回执。

## 5. P5：逐阶段分解与 mixed bottleneck

P5 保持 diagnosis-only（仅诊断），没有 `passed` 字段。五阶段均报告：

- best deployable recall；
- best oracle recall；
- stage headroom；
- deployable/oracle 相对上一阶段的 recall loss；
- downstream excess loss。

验证器由相邻阶段 recall 重算 loss。raw-stage headroom 表示 proposal bottleneck；后续
`deployable_loss - oracle_loss` 的正差表示 downstream bottleneck。两者都超过冻结的 `0.01` 时输出：

```text
MIXED_PROPOSAL_AND_DOWNSTREAM_BOTTLENECK
```

因此 proposal 与 weighting/resampling 的共同失败不会再被一个笼统 verdict 覆盖。

## 6. 授权条件与当前 blockers

聚合器只有在以下条件全部满足时才会签发正向授权：

1. Gate B v0.8 comparator-typed dual gate 正式回执有效；
2. Task 7 严格 `O(window)`、多轴/action equivalence、non-self、`W>1`、长后缀计量均通过；
3. Task 8 预注册 consequential endpoint、真实消费 `(H+Z,C)` 交叉项且未有事后调阈值；
4. Task 9 v1.1 selected-method receipt 与 `ORRER_CHEH` 实现身份有效；
5. Tasks 10、11、12、13 的正式分辨回执沿父哈希链有效；
6. P5 完整逐阶段诊断回执有效；
7. 两轮独立 P0 攻击审计回执有效；
8. 最终 authorization authority 是登记的独立 Ed25519 anchor，且 authorization nonce 未重放。

当前第 1–8 项没有形成已登记的同 run 正式证据链；故授权必须保持 `false`。正向单元测试仅证明状态
机不是不可达死代码，不构成任何真实运行、科学通过或执行许可。

## 7. 实现与验证位置

- 实现：`src/cpswm/system/evaluation_operations/structure_two_trusted_ablation_authorization.py`
- 冻结策略：`configs/project_two_experiments/structure_two_trusted_seven_operator_ablation_authorization_v1_0.json`
- 攻击测试：`tests/test_structure_two_trusted_ablation_authorization.py`
