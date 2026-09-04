# 方向结构二 Task 9 四耦合正式协议 v1.0

> **SUPERSEDED / 不得用于正式运行。** v1.0 将 selected-method receipt（选定方法回执）
> 中的 `ORRER_CHEH` 错缩为 `CHEH`，且没有绑定该回执，也不能表达经认证的
> `enabled-no-op`。正式定义已迁移至 v1.1；v1.0 只能作为历史草案，不能生成 Task 9
> 正式回执或任何七算子消融授权。

- 协议号：`structure-two-task9-four-coupling-protocol@1.0`
- 当前状态：`DEFINED_NOT_RUN`
- 主指标：`cumulative_action_utility`（累积行动效用）
- 当前结论：仅完成定义，未运行、未通过，也不授权七算子系统消融。

机器冻结配置位于
`configs/project_two_experiments/structure_two_task9_four_coupling_protocol_v1_0.json`；
合同与本地诊断验证器位于
`src/cpswm/system/evaluation_operations/structure_two_task9_protocol.py`。

## 1. 精确四对与严格四臂

Holm family（Holm 检验族）固定且只有以下四对：

| coupling | 左侧 | 右侧 |
|---|---|---|
| `opceu_x_cf_bocpd` | OPCEU | CF-BOCPD |
| `cheh_pchmp_x_rgrc` | CHEH + PCHMP | RGRC |
| `cf_bocpd_x_ccrr` | CF-BOCPD | CCRR |
| `rgrc_ccrr_x_ciav` | RGRC + CCRR | CIAV |

每个 independent unit（独立单元）必须按顺序提交 `00/10/01/11`，分别代表
左右侧 `关关/开关/关开/开开`。缺失、重复、替换、拆分复合侧或只改 cell
标签均使整对无效。

`full_x_b_star` 是独立 omnibus comparison（总体比较），不属于这四对，不进入
Holm family，也不能补位。

## 2. 非事后总体、seed 与 split 承诺

总体固定为 `household-001` 至 `household-048`；两个 replicate seeds（重复种子）
固定为 `104729`、`130363`。

- `household-001` 至 `household-008`：validation（验证集），不得进入确认检验；
- `household-009` 至 `household-048`：confirmatory（确认集）；
- 确认集固定为 40 个 household clusters × 2 seeds = 80 个 units；
- unit ID 固定为 `<household>::seed-<seed>`，次序为 household 后 seed；
- 四个 coupling 必须共享同一 ordered visible-input population（有序可见输入总体）。

配置分别冻结 population、seed、split 的 canonical SHA-256。本地自洽哈希只能检测
不同步改写，不能提供历史真实性；所以它不能代替外部时间锚或独立保管。任何只挑四个
效果好的 units、把 80 个伪样本压到两个 clusters、改 unit-cluster 映射或重标 replay
（重放）的路径都失败关闭。

## 3. 功效、MDE 与实际效应阈值

预注册设计采用 `conservative_normal_approximation`（保守正态近似），用四检验
Bonferroni 临界值作为 Holm 的最坏情况界：

- family-wise alpha：0.05；目标 power（功效）：0.80；
- assumed cluster SD：0.40；
- MDE（最小可检测交互）：0.25 累积效用；
- minimum practical interaction（最小实际交互）：0.25；
- 保守最低 powered clusters：32；正式计划：40 clusters / 80 units；
- 40 clusters 在冻结假设下的近似 power：0.927。

该功效是设计假设，不是实验结果。实际结果仍须披露 cluster dispersion（簇间离散）和
模型偏离。诊断性 positive interaction（正交互）要求 Holm 拒绝零假设，且点估计和
95% 区间下界都不低于 0.25；仅仅 `p < .05` 不够。

## 4. 冻结匹配条件

同一 unit 的四臂只允许两个注册开关变化，以下内容必须相等：visible input、
information policy、truth-access policy、compute/action/verification budgets、
non-target modules、source bundle 和 ordered episode IDs。同一 coupling 的所有 units
还必须共享预算、信息、非目标模块和源码绑定；四个 couplings 也共享输入总体与执行绑定。

## 5. 原始语义事件与效用重算

每个 cell 固定五个 episode。提交者不能直接填写 reward 或 utility，只能提交枚举的
semantic outcome（语义结果）及整数计数：`success/partial/failure/safety_abort`、action
cost units、verification actions、owner-contamination events、safety violations。

冻结效用为：

```text
reward(success, partial, failure, safety_abort) = (1.0, 0.4, 0.0, -1.0)
utility = reward
          - 0.02 * action_cost_units
          - 0.05 * verification_actions
          - 0.75 * owner_contamination_events
          - 2.00 * safety_violations
```

验证器从 raw semantic events（原始语义事件）逐 episode 重算 cell utility，再逐 unit
重算 `I = U11 - U10 - U01 + U00`。metadata、trace 文件名或调用方填写的 effect
sample 不得改变效应。

## 6. 算子运行回执

开关布尔值本身不能证明算子运行。每个 cell 必须对该 coupling 的每个算子提交按固定
顺序排列的 `OperatorRuntimeReceipt`（算子运行回执），绑定：

- canonical run/receipt ID、unit、cell、operator 和一次性 nonce；
- enabled 状态和唯一 invocation IDs；
- runtime implementation hash、冻结 implementation-manifest SHA、source-bundle SHA、
  visible input、input/output state、runtime event log；
- raw semantic trace SHA；
- 从 visible input 开始、到 semantic-trace source state 结束的连续状态链；
- signature-shaped attestation claim（签名形状的证明声明）。

enabled 算子必须有 invocation 且发生状态转换；disabled 算子不得有 invocation 或状态
转换。缺失/重复/替换回执、断链、回执复用、nonce/invocation replay、trace 与回执解绑
全部失败关闭。

### 6.1 实现身份不是自洽哈希

正式配置冻结七个 operator IDs 的 implementation manifest（实现清单）：OPCEU、
CF-BOCPD、CHEH、PCHMP、RGRC、CCRR、CIAV。当前仓库没有由独立保管者注册的真实
operator-to-code hashes，因此七个 identity 的状态明确为 `NOT_ENROLLED`，冻结的
`implementation_sha256` 均为 `null`；不得拿运行方填写的哈希冒充已注册代码身份。

本地验证器只执行两类较弱但必要的检查：

1. 同一个 operator 的 runtime implementation hash 必须跨四个 couplings、所有
   `00/10/01/11` cells 和全部 80 units 完全一致；
2. 每份回执必须绑定冻结 implementation-manifest SHA，并且其 source-bundle SHA 必须
   等于该 arm 的 frozen execution binding。

攻击者若只替换 cell `10` 的 OPCEU 实现哈希并同步重算 receipt、content hash 和伪签名，
仍会因跨 cell/unit 不一致而失败。若攻击者把所有位置一起同步替换，本地只能确认“一致”，
仍不能确认“是真实注册实现”；正式门继续关闭。

## 7. 统计协议

每个 household 内先对两个 seed 的 unit-level DiD 取均值，再对 40 个 household means
等权平均。置信区间使用 paired cluster bootstrap（配对簇自助法）：95% CI、2000 次、
seed `90409`。双侧原始 p 值来自在零假设下中心化的 cluster effects，而不是未中心化
正效应样本。四个 p 值共同执行 alpha 0.05 的 Holm step-down；必须保留全部正负结果。

## 8. 独立证明与正式门边界

本地模块只能输出 `DIAGNOSTIC_ARITHMETIC_VERIFIED`。即使四对诊断结果全为正、所有
哈希与伪签名都自洽，其固定输出仍为：

```text
independent_attestation_verified = false
operator_implementation_identity_status = NOT_ENROLLED
operator_implementation_identity_verified = false
task9_positive_gate_passed = false
seven_operator_ablation_authorized = false
formal_gate_reason = TRUSTED_OUTER_ATTESTATION_NOT_VERIFIED
```

原因是 implementation hashes、回执、key ID、signature bytes 和 custody hash 均来自
调用方。本地验证器没有已注册 operator identity 或 trust anchor（信任锚），不能验证
源码身份、私钥独立性、外部托管、签名真实性、时间新鲜度或跨提交
replay registry（重放登记）。正式正门未来只能由独立外层 verifier（验证器）打开，并且
必须验证：预先注册且不由运行方控制的 trust anchor、独立持有的原始回执、签名域、
freshness window、全局 run/nonce/receipt replay 状态及不可变外部锚。本 v1.0 不提供任何
caller boolean 或本地函数绕过该边界。

## 9. 强制对抗测试

测试覆盖 exact four、严格 `00/10/01/11`、posthoc 四单元选择、双簇伪确定性、算子与
cell 替换、任意 switch boolean、缺失运行回执、伪造/陈旧 trace 与 receipt、预算/信息/
非目标模块替换、metadata-only 差异、伪 effect sample、omnibus 补位、重复 JSON key
shadowing、cell `10` 单点替换 OPCEU implementation hash 后重算完整回执、source-bundle
替换，以及结构完整的 caller forgery 永远不能打开正式门。

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/pytest -q -p no:cacheprovider \
  tests/test_structure_two_task9_protocol.py
```
