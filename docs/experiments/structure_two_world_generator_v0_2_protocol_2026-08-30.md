# 结构二世界生成器 v0.2：冻结协议

日期：2026-08-30  
协议：`structure-two-world-generator@0.2`  
证据等级：D0 synthetic target-structure validation（D0 合成靶结构验证）

## 冻结结论

在第一次 Gate A 运行前，世界分布、世界级拆分、平凡规则和通过阈值已经冻结在：

`configs/project_two_experiments/structure_two_world_generator_manifest_v0_2.json`

manifest SHA-256：

`88fbf4a47601401b0b95642c99d2bf0644a8d97ac5ae03171cd60bbfabc62cd4`

第一次 Gate A 之后，不得根据验证结果修改这份 manifest 并继续沿用 v0.2 名称。任何修改都必须升版并重新说明其依据。

## 为什么重建

旧生成器的 seed（种子）主要重抽 observation mask（观测掩码），同一族的 latent actor-location skeleton（潜在人物—位置骨架）不随 seed 改变。它不能把 train / validation / holdout（训练 / 验证 / 留出）解释成不同家庭世界，也没有把 owner habit（主人习惯）建模为需要估计的分布。

v0.2 不删除结构二的任何既定能力。multi-actor reasoning（多人物推理）、hidden-event inference（隐藏事件推断）、open-world unknowns（开放世界未知事件）、identity and cause attribution（身份与原因归因）、regime recurrence（阶段复现）和 selective observation（选择性观测）仍保留在生成真值中。

## 三层随机性

1. `world_seed`：抽一个家庭世界，包括时长、位置、访客数、变点、观测倾向和人物—情境—阶段条件化的习惯分布。
2. `trajectory_seed`：在固定世界中抽潜在人物、位置和事件机制序列。
3. `observation_seed`：在固定潜在轨迹上只抽 MNAR observation（非随机缺失观测）和感知噪声。

因此，同一 `world_seed + trajectory_seed` 的不同 observation seed 必须共享完全相同的 evaluator truth（评测真值）；拆分单位只能是 `world_seed`；置信区间也必须按世界聚类。

## 靶语义

- put-back target（放回靶）：当前阶段和可见 calendar context（日历情境）下主人习惯分布的 mode（众数），不是上一次主人样本的位置。
- search target（搜索靶）：当前潜在物体位置。
- recurrence（复现阶段）复用 baseline（基线阶段）的习惯分布，而不是重新抽一个看起来相似的新分布。

## 拆分

- train worlds：24 个，种子在 manifest 中明列。
- validation worlds：12 个，种子在 manifest 中明列。
- sealed holdout worlds：24 个，只冻结 commitment（承诺哈希），Gate A 不读取原始种子。
- 每个 validation world：3 条潜在轨迹，每条轨迹 2 个观测复本，共 72 条 rollout。

Gate A 只运行 validation worlds。它不生成 train worlds，不解封 holdout，也不运行任何研究方法。

## Gate A 的冻结问题

放回靶必须同时满足：

- sticky latest visible owner sample（最近可见主人样本）仍留下足够误差；
- rolling aggregation（滚动聚合）显著优于 sticky；
- calendar context（日期情境）带来额外增益；
- 最佳平凡聚合规则仍留下方法空间；
- 看见一次主人放置不等于直接看见习惯众数。

搜索靶必须同时满足：

- last observed location（最后观测位置）仍留下足够误差；
- observed-else-context fallback（可见时用观测、不可见时用情境回退）优于 last observed；
- 回退规则之后仍有剩余空间；
- 未观测期间位置变化率足够高。

精确阈值已经写入 manifest，不能在看见结果后移动。所有增益以 world-weighted mean（世界等权均值）计算，关键增益同时给出 world-cluster bootstrap CI（世界聚类自助法置信区间）。

## 决策规则

11 项冻结判据必须全部通过，Gate A 才通过。只有通过后，才能开始把现有结构二方法适配到 v0.2 并恢复 method comparison（方法比较）。如果任一项失败，本轮停在生成器层，不调方法，也不根据结果暗改 v0.2。

## 证据边界

Gate A 通过只说明靶没有被已冻结的平凡规则吃掉，且存在可测量的 action-relevant information（行动相关信息）。它不说明 CPSWM 有效，不说明方法创新成立，也不构成真实家庭上的 external validity（外部有效性）。当前分布和阈值仍是作者选定的 D0 设计，后续需要真实或高保真数据校准。
