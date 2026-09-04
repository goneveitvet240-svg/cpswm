# 结构二 Task 8：相对概率软耦合与配对重跑

日期：2026-09-04
协议：`structure-two-relative-probability-joint-coupling@0.2`
证据等级：**D0 synthetic exact-posterior evidence（D0 合成精确后验证据）**
冻结配置：`configs/project_two_experiments/structure_two_task8_relative_probability_coupling_v0_2.json`
产物：`benchmarks/structure_two/backbone_b_repairs_2026_09_04/task_8_relative_probability_soft_coupling_v0_2.json`

## 结论先行

Task 8 已加入不改变 support（支撑集）的 relative-probability soft coupling（相对概率软耦合）：

\[
\psi(H,C)=1.5\,\mathbf 1[C=\text{actor},H=\text{handoff}].
\]

因此，在 `cause=actor` 条件下，`handoff/direct` 的相对 odds（赔率）乘
`exp(1.5)=4.481689`；原来合法的每个 cell 仍有正概率。truth generator（真值生成器）与
inference target（推断目标）使用同一交互，`lambda=0` 对照也走同一个随机生成器实现，避免把
“确定性旧生成器 vs 随机新生成器”混进干预。

配对重跑表明：**belief coupling instrument（信念耦合仪器）通过，但 Task 8 总门失败。**
原因不是软耦合太弱，而是当前 factorized arm（因子化臂）保留了后续 action readout（行动读出）
所消费的边缘分布，所以它虽丢失联合依赖，却几乎不改变行动或效用。

## 冻结运行与结果

- `G=1`；5 个 scenario seed；每个强度覆盖 8 个环境 cell，共 40 个 cell；
- 敏感性强度：`0, 0.5, 1.0, 1.5` nats；`1.5` 为预注册主强度；
- event partition：`H+Z`；
- factorization TV（因子化总变差）实质阈值：`0.01`；
- action posterior distance（行动后验距离）实质阈值：`0.01`；
- directional downstream-cost advantage（方向性下游代价优势）阈值：`0.001`，定义为
  `factorized decision regret + factorized consolidation cost - joint consolidation cost`；
- artifact content SHA-256：`6bb121f2b0e8121aa144455016668d7921cdf1e8bae136f12de3ac2c444df353`。

| lambda | factorized TV 对 joint | action posterior distance | decision regret |
|---:|---:|---:|---:|
| `0.0` | `2.54e-14` | `1.19e-15` | `0` |
| `0.5` | `0.022845` | `9.59e-16` | `0` |
| `1.0` | `0.050222` | `9.68e-15` | `0` |
| `1.5` | `0.081718` | `7.44e-15` | `0` |

主强度相对零耦合的 factorized TV 增量为 `0.081718 > 0.01`，故
`belief_coupling_instrument_passed=true`。但
`joint_utility_endpoint_informative=false`；主强度的方向性下游代价优势也为 `0`，所以
`joint_utility_benefit_passed=false`、`joint_action_utility_passed=false`、
`task_8_passed=false`，verdict 为
`BELIEF_INSTRUMENT_PASS_ACTION_ENDPOINT_UNINFORMATIVE`。

协议与验证器明确禁止把任意 action-distribution shift（行动分布变化）自动写成效用收益；即便
未来行动距离越过 `0.01`，仍须方向正确的净代价优势越过 `0.001` 才能通过总门。

## 主张边界

本结果证明合成任务中存在可测的非支撑型 `H×C` 依赖，也证明当前仪器能检出其因子化损失；它
**没有**证明 joint inference（联合推断）带来具身行动或效用收益。后续必须预注册真正消费
`(H+Z,C)` 交叉项的 consequential endpoint（后果性端点），例如 cause-conditioned
verification/consolidation utility（原因条件化的验证／巩固效用），并保持动作预算和信息集一致。
在此之前不得进入可信七算子系统消融。
