# 方向结构二 Task 9 四耦合正式协议 v1.1

- 协议号：`structure-two-task9-four-coupling-protocol@1.1`
- 状态：`DEFINED_NOT_RUN`
- 主指标：`cumulative_action_utility`（累积行动效用）
- 权限边界：Task 9 未正式运行、未通过，七算子系统消融仍未授权。

机器冻结配置为
`configs/project_two_experiments/structure_two_task9_four_coupling_protocol_v1_1.json`；
合同与验证器为
`src/cpswm/system/evaluation_operations/structure_two_task9_protocol.py`。v1.0 因算子身份
错缩和缺 selected-method receipt binding（选定方法回执绑定）而被取代，不能用于正式运行。

## 1. selected-method receipt 与七算子身份

协议同时绑定选定方法回执的相对路径、原始文件 SHA-256、规范内容 SHA-256、方法 ID
及逐项 identity projection（身份投影）。七个身份按选定方法冻结为：

```text
OPCEU, ORRER_CHEH, PCHMP, CF-BOCPD, RGRC, CCRR, CIAV
```

其中 `orrer_cheh -> ORRER_CHEH` 是无损的一对一投影；`CHEH`、`ORRER` 或
`CHEH_ORRER` 均不是 Task 9 v1.1 的可替换身份。加载协议时会重新读取选定方法回执，
拒绝文件改写、内容改写、JSON duplicate-key shadowing（重复键遮蔽）、顺序/身份替换和
绑定哈希不一致。

## 2. 精确四耦合与四臂

Holm family（Holm 检验族）严格只有：

| coupling | 左侧 | 右侧 |
|---|---|---|
| `opceu_x_cf_bocpd` | OPCEU | CF-BOCPD |
| `orrer_cheh_pchmp_x_rgrc` | ORRER_CHEH + PCHMP | RGRC |
| `cf_bocpd_x_ccrr` | CF-BOCPD | CCRR |
| `rgrc_ccrr_x_ciav` | RGRC + CCRR | CIAV |

每个 `household_seed` independent unit（独立单元）按序提交 `00/10/01/11`。同一单元
四臂的 visible input、information/truth-access policy、compute/action/verification
budget、non-target modules、source bundle 和 episode IDs 必须相等。`full_x_b_star` 是
单独 omnibus comparison（总体比较），不得补入四耦合检验族。

总体冻结为 48 个 households，其中前 8 个只作 validation，后 40 个作 confirmatory；
两个 seeds 为 `104729` 和 `130363`，确认检验为 40 clusters / 80 units。每 cell 五个
episodes。效用由原始 semantic outcomes（语义结果）和成本计数重新计算，交互量固定为
`U11-U10-U01+U00`，不能接受调用方直接填写的 effect sample（效应样本）。

## 3. 功效、统计与阈值

冻结 family-wise alpha 0.05、目标 power 0.80、cluster SD 0.40、MDE 0.25、minimum
practical interaction 0.25、最低 32 powered clusters；计划 40 clusters 的近似 power
为 0.927。每个 household 先聚合两个 seed，再做 2000 次、seed `90409` 的 paired
cluster bootstrap（配对簇自助法），四个 p 值执行 Holm step-down。诊断性正交互要求
Holm 拒绝零假设，且点估计与 95% CI 下界都不低于 0.25。

## 4. 三态算子回执与 authenticated enabled-no-op

每个算子回执必须明确属于且仅属于以下一种 outcome（结果）：

- `disabled`：未启用、无 invocation、输入输出状态相同；
- `state_changed`：已启用、有唯一 invocation、输入输出状态不同；
- `enabled_no_op`：已启用且确实调用，但依据冻结规则没有 admissible state change
  （可接受状态变化），因此输入输出相同。

`enabled_no_op` 不是靠布尔值声明。它必须提供 reason code、no-op evidence SHA-256，
并用 `cpswm.structure_two.task9.operator_execution.v2` 域下的 Ed25519 签名覆盖完整回执
payload。评价入口在出现 no-op 时必须获得外部 verification-only public key（只验证公钥）
并逐份验签；缺验证器、HMAC、错误 key/domain、篡改原因/证据/状态均失败关闭。普通
`state_changed` 不得夹带 no-op 证明，`disabled` 也不得冒充 no-op。

这项验签只证明“给定外部公钥下该 no-op payload 未被改写”，不能自行证明密钥由谁保管。
当前 independent custody trust anchor（独立保管信任锚）仍为 `NOT_ENROLLED`，所以即使
no-op 验签成功，本地报告仍不能打开正式 Task 9 门。

## 5. 正式门边界

当前 implementation manifest（实现清单）的七个真实代码身份均为 `NOT_ENROLLED`。
本地验证器可重新计算语义效用、交互、置信区间、Holm 校正，检查回执链、运行哈希一致性、
source-bundle 绑定和 no-op 的给定公钥验签；但它不能认证 implementation identity、独立
custody、freshness 或全局 replay registry。因此固定输出仍包括：

```text
independent_attestation_verified = false
operator_implementation_identity_verified = false
task9_positive_gate_passed = false
seven_operator_ablation_authorized = false
```

只有以后由独立外层 verifier 使用预注册信任锚、已注册实现身份、时间/新鲜度、全局 nonce
与 receipt replay 状态复核正式运行，才可能生成 Task 9 的正式父回执；本协议本身不含任何
可由调用方设置的通过或授权字段。

## 6. 当前验证命令

以下只运行协议测试，不运行七算子系统消融：

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/pytest -q -p no:cacheprovider \
  tests/test_structure_two_task9_protocol.py
```

覆盖包括 selected-method receipt 篡改、`ORRER_CHEH` 身份替换、缺失/重复四耦合与四臂、
posthoc unit 选择、伪 cluster、回执/状态链/源码包篡改、metadata-only 假效应、完整自洽
caller forgery，以及 enabled-no-op 的缺失验证器和错误 Ed25519 key 攻击。
