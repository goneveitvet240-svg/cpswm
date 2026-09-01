# 结构二巩固兼容门：预注册

日期：2026-08-29  
协议：`structure-two-consolidation-compatibility-gate@0.1`

## 问题与边界

上一轮在独立封存集上发现：序贯粒子无巩固相对逐步粒子基本打平，而固定 `0.28` 旧分布混合使每步净行动损失稳定恶化。该 holdout 不再用于开发或调参。

本轮使用全新的四个场景族、4 个 validation seeds 和 12 个 sealed holdout seeds，检验 consolidation compatibility（巩固兼容性）能否消除 stale consolidation lag（过期巩固滞后）。本轮仍不训练 neural amortized proposer（神经摊销提议器）。

## 冻结实验臂

1. `corrected_amg`：外部锚点；
2. `per_step_particle_projection`：当前逐步粒子投影；
3. `sequential_particle_no_consolidation`：序贯无巩固对照；
4. `fixed_stale_blend`：上一轮固定 `0.28` 混合失败实现；
5. `revision_compatibility_gate`：仅在人物、身份、原因、阶段修订兼容时消费账本分布；
6. `uncertainty_decayed_influence`：按当前主导粒子置信度和修订兼容度衰减账本影响；
7. `immediate_conflict_quarantine`：人物／原因／阶段冲突时立即暂停账本行动影响；
8. `adaptive_combined_consolidation`：兼容门＋不确定性衰减＋冲突立即隔离。

除 AMG 外，所有臂共享完整七算子系统和 `K=24` 粒子预算；每臂、每场景族搜索 3 个 profile，预算相同。四种巩固臂共享相同 ancestry、ledger promotion 和 correction 后端，只改变账本分布进入行动的门控。

## 冻结主要条件

机制缓解门同时要求：

1. `adaptive_combined - fixed_stale_blend` 的 95% paired cluster interval 上界 `< 0`；
2. adaptive combined 相对 fixed blend 在 identity 与 long-recurrence 两族的平均差均 `< 0`；
3. `adaptive_combined - per_step_particle_projection` 的 95% 区间上界 `≤ +0.02`；
4. adaptive combined 相对 per-step 在 role 与 cause guardrail 的平均差均 `≤ +0.02`；
5. 四种策略产生各自非空运行时收据：compatibility suppression、uncertainty decay 或 immediate quarantine；
6. ancestry、exactly-once ledger、四轴行动消费和七算子保留门全部通过。

即使本轮通过，也只说明上一轮巩固伤害得到缓解；只有 adaptive combined 相对 per-step 的区间上界 `< 0`，才能额外形成“巩固具有正行动贡献”的候选证据。

若失败，不删除可逆巩固能力；应报告失败策略和作用路径，并停止进入 neural proposer 确认实验。
