# 结构二 Task 8：交叉项后果性端点 v0.3 注册复算

日期：2026-09-05
协议：`structure-two-relative-probability-joint-coupling@0.3`
证据级别：D0 synthetic deterministic rerun（D0 合成确定性复算）
冻结配置：`configs/project_two_experiments/structure_two_task8_relative_probability_coupling_v0_3.json`
配置 SHA-256：`e89f4d8f25080843c20b526b5541d060071d4cd1e2dc227329a799dcfb962772`
结果工件：`benchmarks/structure_two/backbone_b_repairs_2026_09_04/task_8_relative_probability_soft_coupling_v0_3.json`

## 结论

在配置、行动、效用、阈值、信息与预算全部先冻结且未改动的注册总体上，Task 8 的 belief/action/utility（信念/行动/效用）严格合取通过：

- `belief_coupling_instrument_passed = true`
- `endpoint_consumes_interaction = true`
- `consequential_action_endpoint_passed = true`
- `consequential_utility_benefit_passed = true`
- `task_8_passed = true`
- `seven_operator_efficacy_authorized = false`

这里的 `PASS` 只表示任务专用 D0 注册复算通过。没有 independent-custody formal receipt（独立托管正式回执），因此它不是授权级通过，也不能单独打开七算子消融。

## 预注册后果性端点

`joint-cross-safety-policy@0.1` 直接读取 posterior over `(H+Z,C)`（`(H+Z,C)` 后验）中的交叉 cell，而不是读取因子化仍会保留的单独边缘分布。

离散行动为：

- `proceed`：直接继续；
- `verify`：先验证再继续。

冻结 severity（严重度）：

- `cause=actor ∧ mechanism=handoff ∧ Z∈{stay,unresolved}`：`1.0`；
- `cause=habit ∧ Z∈{create,reactivate}`：`0.6`；
- 其他已解析 cell：`0.0`；
- unresolved：`0.8`。

行动策略为 `P(verify)=posterior expected severity`，`P(proceed)=1-P(verify)`；每次 `verify` 的冻结代价为 `0.12`，`proceed` 的事后代价等于真值 severity。策略只能看到注册观测后的 belief（信念），不能看到 truth（真值）或未来观测；真值仅供事后 utility evaluator（效用评估器）计分。

构造性攻击使用两个 H+Z 与 C 边缘完全相同、仅交叉依赖不同的 belief；两者产生不同的离散行动分布。因此端点确实消费交叉项本身，而不是把 interaction（交互）记录后交给无关量决定。

## 冻结设计与结果

- `G=1`；5 seeds × `2×2×2` 场景，共 40 个 paired cells（配对单元）。
- exact-posterior state budget（精确后验状态预算）：`2,000,000`。
- strengths：`0, 0.5, 1.0, 1.5 nats`；`1.5` 是 primary，`0` 是 paired negative control（配对负对照）。
- belief TV 门槛：`0.01`。
- consequential action distribution TV（后果性行动分布 TV）门槛：`0.01`。
- factorized-minus-joint expected cost（因子化减联合期望代价）门槛：`0.001`，正值表示 joint 更好。

注册结果：

| 指标 | 结果 | 门槛/方向 |
|---|---:|---:|
| factorized TV，λ=0 | `2.54169e-14` | negative control |
| factorized TV，λ=1.5 | `0.0817181` | ≥ 0.01 且超过 control 0.01 |
| consequential action TV | `0.0408590` | ≥ 0.01 |
| factorized expected cost | `0.2241490` | lower is better |
| joint expected cost | `0.2108091` | lower is better |
| factorized − joint cost | `+0.0133400` | ≥ 0.001 |
| legacy embodied-action TV | `7.43886e-15` | 仅作旧端点负对照 |

在编码完成后的单 seed 诊断预览中，utility difference（效用差）曾为 `-0.00517433`；它不是注册总体，没有被用于换端点、换阈值或筛 seed。冻结的五 seed 总体随后给出上述阳性结果。

## 工件、验证和边界

- Artifact content SHA-256：`46791b7c59e3851c9acb7bf28416552aed48d81d28b1e6542598270fff7c11a5`
- Artifact file SHA-256：`2956a687e5020d87d296df473cb124dc0b7abb448a80e8a2b6a603970a530ec9`
- Deterministic result SHA-256：`a5ee0ff075d81834dc9c721dd6731d30688d4654a292686d49a3f06314bc14a2`
- Task-specific source bundle SHA-256：`6a429d686167f9b2f16f05cd2ee619caa60d2c30e2fe6c9f32cf1098c6a8f93e`

工件逐路径登记了全部 `341` 个正向布尔输出；每条均绑定 artifact content、任务专用
source bundle、冻结配置、由原始指标重算的语义门和 fresh task-specific recomputation。

artifact verifier（工件验证器）从冻结 config 重新核对端点身份、动作集合、全部 severity/cost、信息边界、state budget 和三个阈值，再做 fresh recomputation；降低阈值、伪造 endpoint-consumption 或只修改外层哈希均不能产生通过。

本工件没有签名、外部时间戳或独立 custody（托管），所以只证明当前源码与冻结配置下的任务专用确定性复算，不证明历史真实性、外部有效性或七算子授权。
