# 结构二 Gate B 比较器类型化双门协议 v0.8

协议号：`structure-two-comparator-typed-dual-gate-b@0.8`
冻结日期：2026-09-05
状态：**`FROZEN_NOT_EXECUTED`（已冻结，未正式运行）**

机器可读配置：
`configs/project_two_experiments/structure_two_gate_b_v0_8.json`。

实现：
`src/cpswm/system/evaluation_operations/structure_two_comparator_typed_dual_gate_b_v0_8.py`。

## 1. P0 裁决

v0.8 取代了已失效的 v0.7。v0.7 把每个对照都解释成 belief difference AND action
difference（信念差异与行动差异同时存在），这会错杀两类必须证明“等价”的对照：

- action-regret ablation（行动后悔消融）要求决策前 belief 等价，再看 action 与 utility
  （效用）是否不同；
- full-rerun control（完整重放对照）要求 belief 与 action 都等价。

因此 v0.8 不再存在一个可为九个对照通用的“差异门”。每个 comparison（比较）必须
先冻结 comparator type（比较器类型）、belief/action/utility relation（关系）、灰区不重叠的
bounds（上下界）和 causal window（因果窗口），再允许运行。

## 2. 预注册关系与阈值

belief/action 使用 total variation（TV，总变差距离）：

- equivalence region（等价区间）：`0.00 <= TV <= 0.01`；
- material-difference region（实质差异区间）：`0.05 <= TV <= 1.00`；
- `(0.01, 0.05)` 是预注册 gray zone（灰区），不得临时判为等价或差异。

action relation 还必须同时约束 deterministic selected public action（确定性选中的公共行动）：
`equivalent` 要求选中行动相同，`materially_different` 要求选中行动不同。仅修改未影响
argmax 的分布尾部，不能充当 action difference。

action-regret 的 utility 先归一化到 `[-1, 1]`，再比较绝对差：

- utility equivalence：`0.00 <= |delta U| <= 0.01`；
- utility difference：`0.10 <= |delta U| <= 2.00`。

这些阈值已随配置冻结；看到结果后不得调整。

## 3. 九个类型化比较

| comparison | comparator type（比较器类型） | belief relation | action relation | utility relation | causal window |
|---|---|---|---|---|---|
| event-inference-adaptation | causal dual difference（因果双读出差异） | different | different | not scored | shared pre-action |
| object-search-adaptation | causal dual difference | different | different | not scored | shared pre-action |
| no-consolidation-ablation | causal dual difference | different | different | not scored | shared pre-action |
| active-dreaming-adaptation | causal dual difference | different | different | not scored | shared pre-action |
| auto-dreamer-adaptation | causal dual difference | different | different | not scored | shared pre-action |
| trustmem-adaptation | causal dual difference | different | different | not scored | shared pre-action |
| brainctl-adaptation | causal dual difference | different | different | not scored | shared pre-action |
| action-regret-ablation | action regret at equivalent predecision belief（等价决策前信念下的后悔效应） | **equivalent** | **different** | **different** | predecision through consequence, offsets `0..3` |
| full-rerun-control | full-rerun equivalence（完整重放等价） | **equivalent** | **equivalent** | not scored | same-history pre-action |

每一行都在 JSON 中独立重复登记 relation、等价上下界、差异上下界与窗口 ID。
loader 对整个对象做 canonical equality（规范等值）校验，不接受运行者临时把
`equivalent` 换成 `different`，也不接受降低阈值或扩大 causal window。

## 4. 逐 episode 公共本体

每个 episode 都必须在任何 arm（实验臂）开始前冻结一份
`structure-two-episode-public-ontology@0.8`：

- `8–12` 个 canonical non-nil UUID location（规范非空 UUID 位置）；
- `1–3` 个独立 guest UUID；
- target object、owner、robot、locations 与 guests 的 UUID 全部两两不同；
- belief support 为 `location x responsible_actor + unresolved`；
- action support 完整包含 `put_back`、`search`、`deliver`、`ask`。

本体 manifest SHA-256 同时绑定 episode ID、对象、人物、位置、belief support 和 action
support。另一 episode 即使具有相同数量的标签，也不能替换当前本体。

## 5. 无损 runtime-action 投影

每个 `arm x episode` 必须登记一份
`structure-two-runtime-public-action-bijection@0.8`（运行时行动—公共行动双射）。一个 runtime action
是 typed canonical command（类型化规范命令），字段精确为 `runtime_action_id`、`kind`、
`target_object_uuid`、`location_uuid`、`guest_actor_uuid`；缺字段或额外隐藏字段都拒绝。
`put_back/search` 只能携带 location，`deliver/ask` 只能携带 guest；
`runtime_action_id` 由全部语义字段唯一计算，不得自由命名。

验证器对整个 public action support 执行：

1. runtime action 不重复；
2. public action 不重复；
3. public support 不多不少且顺序一致；
4. 先从 runtime typed fields 与当前 episode ontology **计算**唯一 public label；
5. `project(runtime) -> public` 必须等于该计算值；
6. `inverse(public) -> runtime`；
7. 对每项执行双向 round trip equality（往返等值）。

所以，两个 runtime command 投到同一 public action、一个 runtime command 投到两个 public
action、缺行动、错对象／位置／guest、语义置换（例如把 `delete/object=B` 自报为
`put_back/location=A`）或带隐含未投影字段，都失败关闭。

## 6. 因果时序防线

所有 belief 与 action-policy readout（行动策略读出）必须：

- 来自同一 episode、decision ID 和 predecision information-set hash（决策前信息集摘要）；
- 阶段为 `pre_action_pre_evaluator_truth`；
- readout 在 action commit 之前，两者事件差不超过 `1`；
- action commit 前未访问 evaluator truth（评估器真值）；
- 窗口内不存在外生干预。

action-regret 的 utility 必须在 action commit 后的事件偏移 `0..3` 内观测，两臂坐标完全
一致。其他比较不读 utility；不得用 post-action（动作后）结果回填 belief/action。

## 7. 机制连续性与授权边界

v0.8 修正的是 comparator semantics（比较器语义），不删除 v0.7 中对 registered mechanism
evidence（登记机制证据）的要求。未来正式运行仍需由独立受信链同时验证机制、公共本体、
runtime-action 双射、类型化关系与时序。

当前实现只能返回 diagnostic typed-relation result（类型化关系诊断）。即使调用者构造了
九对完整通过的数据，以下值仍硬置为 false：

- `formal_run_present=false`；
- `independent_attestation_present=false`；
- `formal_gate_b_passed=false`；
- `gate_b_passed=false`；
- `seven_operator_ablation_authorized=false`。

在 v0.8 正式运行、独立保管验证和用户要求的两轮对抗全部通过前，**禁止运行或授权
可信七算子消融**。
