# Structure Two v0.7 资源受限执行阶段与两轮对抗审核（2026-09-01）

## 结论

本阶段完成了 resource-bounded declarative execution infrastructure（资源受限声明式执行基础设施），但总审核结论仍为“不通过”，不得冻结或授权 efficacy comparison（效能比较）。

已完成的是：Active Dreaming 适配路径不再接受调用者布尔成功声明；一个具体、内容绑定的 declarative scenario（声明式场景）必须由独立进程实际执行，生成可复跑状态链、退出码、executor implementation hash（执行器实现哈希）和 Ed25519 executor receipt（执行者回执），reference core 验证全部证据后才允许 commit。另新增 exact-six-arm runner（精确六臂运行器），要求六个 reference core 从同一个 typed input bundle（类型化输入包）执行。

未完成的是：六臂官方 native protocol reproduction（原生协议复现）、全输入域 component parity（组件等价性）、adaptation parity（适配等价性）、独立 reviewer evidence（审核者证据）和正式 Gate B 运行。因此六臂可执行不能升级成 external fidelity（外部忠实度）或 efficacy（效能）证据。

## 实现边界

1. Counterfactual executor 只解释 `assert_equals`、`set`、`increment` 三类受限操作，不运行调用者提供的任意 shell/Python。
2. program 文件的真实 SHA-256、executor 源码 SHA-256、逐步输入输出状态哈希、最终状态、成功语义和 Ed25519 签名全部重新验证；同一次文件读取同时用于解析与哈希，避免 program 替换竞态。
3. program 与 receipt 同时绑定 `cluster_id`、`failure_set_sha256` 和 `candidate_rule_sha256`；scenario ID 与 cluster hint 必须唯一，receipt/path 集合必须精确覆盖非空 cluster 集合。零有效聚类直接失败。
4. 资源上限为：program 最大 64 KiB、最多 256 条指令、最多 128 个状态键、key 最大 128 字符、string 最大 4096 字符，数值必须有限且绝对值不超过 `1e308`。
5. `1e308 + 1e308` 等运行时溢出生成带 `exit_code=1`、稳定 failure reason 和 Ed25519 签名的失败 receipt，而不是使执行器裸异常退出。
6. 修改 program、修改 receipt、替换 executor key、失败执行、缺失 receipt 或恢复旧 `externally_asserted_execution_success` 字段均失败关闭。
7. 六臂 runner 从 Active Dreaming 实际输出推导 receipt coverage，不再硬编码为 true，并固定输出 `native_protocol_reproduction_passed=false`、`component_parity_passed=false`、`adaptation_parity_passed=false`、`external_fidelity_gate_passed=false` 和 `external_method_efficacy_comparison_allowed=false`。
8. Active Dreaming 规范来源改为版本化页面 `https://engrxiv.org/preprint/view/5919/9826`，并记录官方 PDF；brainctl 官方 whitepaper 页面可访问。来源可定位仍不等于本地 content-bound source artifact 已归档，也不等于原生复现。

## Round 1：执行真实性与组件对抗

- 独立进程 CLI 实际执行：`execution_succeeded=true`、`exit_code=0`，生成两步 execution log 和 Ed25519 receipt。
- Active Dreaming/Auto-Dreamer/TRUSTMEM/brainctl 等 reference-core 对抗回归：`28 passed`。新增覆盖零聚类、重复 scenario/hint、跨聚类 receipt 重放、rule binding 替换、超限 program、运行时状态键增长和浮点溢出。
- 从 Active Dreaming `9c05baf...` 与 brainctl `c634808...` 干净 checkout 重新生成 selected-fixture report：`selected_fixture_parity_passed=true`，但 `component_parity_passed=false`、`native_protocol_reproduction_passed=false`、`adaptation_parity_passed=false`。

Round 1 结论：本轮已知执行回执和核心语义攻击未能绕过；这不是全输入域等价性证明。

## Round 2：六臂完整性与主张升级对抗

- 运行 fidelity、efficacy authorization、input coverage、signed Gate B、canonical protocol、stratified Gate B 和 readiness 回归：`40 passed`。
- readiness artifact 内容哈希重新验证通过。
- machine assertion 确认 resource-bounded execution（资源受限执行）不能升级为 native reproduction、component/adaptation parity、external fidelity、Gate B scored/pass、freeze readiness 或 efficacy authorization。

Round 2 结论：`final_round2_claim_escalation=REJECTED`，`ready_to_freeze=false`。

## 当前机器状态

- `bounded_six_arm_execution_runner_implemented=true`
- `active_dreaming_content_bound_scenario_executor_implemented=true`
- `active_dreaming_zero_cluster_fails_closed=true`
- `active_dreaming_cluster_failure_rule_binding_implemented=true`
- `active_dreaming_executor_resource_bounds_implemented=true`
- `active_dreaming_deterministic_failures_are_signed=true`
- `v0_7_six_arm_reference_execution_run=false`
- `component_parity_passed=false`
- `native_protocol_reproduction_passed=false`
- `adaptation_parity_passed=false`
- `external_fidelity_gate_passed=false`
- `v0_6_gate_b_scored=false`
- `ready_to_freeze=false`

下一阶段需要产生六臂正式输入 artifact 和独立 trust anchors（信任锚），运行六臂统一执行包；之后仍需逐臂完成官方原生协议与适配等价测试，不能用 bounded reference execution 替代。
