# 结构二巩固兼容门：结果

日期：2026-08-29  
协议：`structure-two-consolidation-compatibility-gate@0.1`  
最终裁决：**主要伤害缓解成功，但预注册总门失败；没有巩固正贡献证据。**

## 主要比较

| 比较（左−右） | 每步净行动损失差 | 95% paired cluster interval | 判断 |
|---|---:|---:|---|
| adaptive combined − fixed stale blend | **−0.0913** | **[−0.1146, −0.0673]** | 稳定消除固定混合伤害 |
| compatibility gate − fixed stale blend | **−0.0369** | **[−0.0521, −0.0240]** | 有效缓解 |
| uncertainty decay − fixed stale blend | **−0.0529** | **[−0.0753, −0.0345]** | 有效缓解 |
| immediate quarantine − fixed stale blend | **−0.0913** | **[−0.1146, −0.0673]** | 缓解最强 |
| adaptive combined − per-step projection | 约 0.0000 | [−0.0112, +0.0112] | 打平，没有正贡献 |
| adaptive combined − sequential no consolidation | +0.0080 | [0.0000, +0.0176] | 未优于无巩固对照 |
| adaptive combined − corrected AMG | +0.3608 | [+0.3277, +0.3891] | 仍明显落后 AMG |
| fixed stale blend − per-step projection | **+0.0913** | **[+0.0697, +0.1122]** | 复现固定巩固伤害 |

12 个全新 sealed seeds 跨四个全新场景族聚类。负数表示左侧更好。

## 预注册条件

通过：

- adaptive combined 相对 fixed blend 的主要区间上界 `< 0`；
- identity family 缓解：`−0.0096`；
- long-recurrence family 缓解：`−0.0128`；
- adaptive combined 整体非劣于 per-step；
- role guardrail：adaptive−per-step `−0.0256`；
- 七算子、ancestry、ledger 和 exactly-once 门。

失败：

- cause guardrail：adaptive−per-step `+0.0385`，超过冻结上限 `+0.02`；
- combined runtime receipt 门：identity、long-recurrence、role 三族中，兼容门或立即隔离先把影响权重降为零，使 uncertainty-decay 分支没有产生非零影响收据。

总门按预注册判定为失败，不能因为主要效果显著而事后删除这两个失败条件。

## 四种策略的机制判断

四种策略都稳定优于固定旧分布混合，说明上一轮的 stale consolidation lag（过期巩固滞后）可以通过限制账本行动权限显著缓解。

其中 immediate conflict quarantine（冲突立即隔离）与 adaptive combined（组合策略）的行动结果完全相同。运行时收据显示：组合策略的大多数冲突步骤已经被兼容／隔离门短路，因此 uncertainty decay 没有机会影响动作。这意味着当前证据支持“冲突时停止消费旧账本分布”，但不支持“三种子机制联合产生额外收益”。

单独 uncertainty decay 和 compatibility gate 都能缓解固定混合，但弱于立即隔离。cause-regime 场景中，立即隔离仍相对逐步投影多出 `+0.0385` 损失；说明只撤销旧账本影响还不足以修正当前序贯粒子在 cause/regime 切换时的动作。

## 科研裁决

本轮可以支持：

> 在全新的 D0 合成场景族和封存种子上，对冲突修订立即停止消费已巩固位置分布，稳定消除了固定巩固造成的大部分行动伤害。

本轮不支持：

- 可逆巩固相对无巩固具有正贡献；
- adaptive combined 优于逐步粒子投影；
- uncertainty decay 在组合策略中稳定参与决策；
- cause/regime 冲突问题已经解决；
- 开始 neural amortized proposer 确认实验；
- 完整结构二击败 corrected AMG。

从行动证据看，当前最强对照仍是 sequential no consolidation（序贯无巩固），它比 adaptive combined 平均低 `0.0080`。因此下一次实验若继续，应针对 cause/regime transition proposal（原因／阶段转移提议）和 ledger reactivation semantics（账本再激活语义），而不是继续调混合权重。

这不删除结构二中的可逆巩固能力；它把当前未解决点进一步定位为：冲突隔离已经有效，但正确 revision 的重新激活尚未带来超过无巩固的行动价值。

## 验证与产物

- 预注册：`docs/experiments/structure_two_consolidation_compatibility_gate_preregistration_2026-08-29.md`
- manifest：`configs/project_two_experiments/structure_two_consolidation_compatibility_manifest_v0_1.json`
- sealed seeds：`configs/project_two_experiments/structure_two_consolidation_compatibility_sealed_seeds_v0_1.json`
- artifact：`artifacts/project_two_v04_development/structure_two_consolidation_compatibility_gate_v0_1.json`
- content SHA-256：`34680e95251884308dfba7c723d94f1e370f55ece2d66df2bc86fb55569efada`
- artifact byte SHA-256：`3dee6a71b381ea49507ae1a9b4f0df81e96ddd8c12a2ff7d57f1e20f99f26ff9`
- benchmark source SHA-256：`a2e769d5389b42622e92acef5818dacaf25dee4200f96de30f0cb965924b64f4`
- quick verify：通过；
- full deterministic recomputation：通过。
