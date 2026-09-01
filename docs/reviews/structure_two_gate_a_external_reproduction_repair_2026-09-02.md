# Structure Two Gate A、Gate B 与外部复现独立审核门修复（2026-09-02）

## 结论

本轮关闭了审计列出的 Gate A 自报成功、来源产物脱离登记哈希、调用者后补冻结声明、组合授权缺少六臂执行/执行器符合性、跨注册表重放、只签结果哈希以及 readiness（就绪度）语义冲突等已知代码级绕过。

当前总体状态仍为“不通过、不得冻结、不得授权 external efficacy comparison（外部效能比较）”。原因不是已知绕过仍可用，而是仓库尚未取得真实的外部 enrollment authority（登记权威）、六臂来源获取产物、独立执行产物、原生/适配忠实度证据与正式 Gate B 轨迹。

## 已关闭的阻断项

1. Gate A 不再接受 `gate_a_passed=true` 加普通自哈希。验证器现在读取内容绑定的 validation input（验证输入）和 deterministic execution log（确定性执行日志），核对冻结清单、registry identifier（注册表标识）、预注册 producer run（生产运行）、ledger（账本）、authority nonce（权威随机挑战）、validation seed（验证种子）与 holdout commitment（留出集承诺）；从逐 rollout 指标重新聚合总指标、按冻结 Gate A spec 重算全部准则，并验证 executor/custodian（执行者/托管者）双签。
2. source acquisition receipt（来源获取回执）的实际 artifact SHA-256 必须精确等于该 arm 在 source register（来源登记表）中的 `primary_source_sha256`。可信 reviewer 对另一文件签名也不能覆盖该不一致。
3. frozen manifest（冻结清单）绑定完整 trust-anchor registry（信任锚注册表）标识与 enrollment authority 公钥指纹，并由 reviewer、custodian、enrollment authority 三签。权威签名范围包括 timezone-aware timestamp（带时区时间戳）、ledger identifier/sequence（账本标识/序号）、外部不可预测挑战声明、冻结早于证据生产声明、预注册 run ID、validation-seed commitment 和 holdout commitment。Gate B 轨迹必须使用该预注册 run ID。
4. standalone efficacy authorization（独立效能授权）现在强制要求解释并验证 executor conformance artifact（执行器符合性产物）与 six-arm reference execution（六臂参考执行）；缺少任一项时最终授权必为 false。
5. conformance verifier（符合性验证器）读取真实测试产物，要求精确六项 capability（能力）、`uv run pytest` 命令中逐项命名的唯一测试、成功 exit code、逐项 assertion evidence（断言证据）、受限仓库路径的源码哈希清单、独立 tester 签名和 executor 报告签名。任意测试哈希加六个 true 不再可通过。
6. 六臂验证器读取 typed input bundle、六个完整结果 artifact、Active Dreaming program/receipt 列表和执行参数；随后确定性重跑六个 reference core 并逐臂比较内容哈希。即使可信 executor 对攻击者改写后的结果重新签名，结果仍因与重执行不一致而被拒绝。
7. 组合授权重新验证规范 source row（来源行）的 method、URL、evidence level、官方代码 URL/commit 与登记 SHA-256，不能仅凭六个 arm 名称冻结任意来源内容。
8. readiness 删除含混的 `ready_to_freeze` 和硬编码 `typed_adaptation_input_contracts_implemented=true`，改为 `design_evidence_ready_for_external_freeze`、分离的 design/authorization blockers（设计/授权阻断项）以及由真实 input/conformance/reference artifacts 推导的状态。

## 冻结时序的信任边界

仓库能验证的是：一个预先登记、通过 out-of-band（带外）方式信任的 enrollment authority 对冻结时序、账本序号、外部挑战和“冻结先于证据生产”作了 Ed25519 证明，并且后续 Gate A/Gate B 产物绑定该承诺。

仓库不能仅凭本地文件独立推导外部真实时间，也不能证明三种人类角色确由不同自然人控制。正式运行仍必须把 enrollment authority 私钥、账本和挑战生成放在候选方环境之外；否则只能称为本地协议演练，不能称为外部冻结证明。

## 两轮验证

Round 1（完整目标回归）：运行 P0/v0.5 历史边界、Gate B 规范、input coverage、external fidelity、来源获取、executor conformance、六臂 reference core、standalone authorization、signed Gate B 与 readiness 共 103 项测试，全部通过。

Round 2（攻击性筛选）：运行 58 项拒绝/篡改/重放/伪造/越界测试，覆盖最小自哈希 Gate A、逐 rollout 聚合篡改、自选 authority、跨 registry 重放、后补冻结声明、非预注册 run、非规范来源行、可信 reviewer 签错文件、虚构 conformance 哈希、路径穿越、重签伪造六臂结果、零聚类、跨聚类回执重放、状态链断裂及历史清单字段伪造，全部失败关闭。

静态检查：相关文件 Ruff 通过；8 个目标 source file 使用 strict mypy（依赖静默跟随）通过。

## 当前机器状态

- `design_evidence_ready_for_external_freeze=false`
- `ready_for_external_custodian_run=false`
- `externally_frozen_manifest_verified=false`
- `gate_a_passed=false`
- `v0_7_six_arm_reference_execution_run=false`
- `v0_6_gate_b_scored=false`
- `v0_6_gate_b_passed=false`
- `external_fidelity_gate_passed=false`
- `external_method_efficacy_comparison_allowed=false`
- `lifecycle_state=DEVELOPMENT_EVIDENCE_INCOMPLETE`

因此，本轮结论是“已知协议绕过的代码级修复与回归闭环完成”，不是“外部复现独立审核门已经通过”。
