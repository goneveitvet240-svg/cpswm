# 结构二 strongest-neighbor matched death test：预注册

日期：2026-08-29  
协议：`structure-two-strongest-neighbor-gate@0.1`

## 1. 冻结问题

本门检验 CARE-WM 的联合方法主张：在结构二完整可见状态上，按未来具身行动遗憾在
`promote / escrow / physically verify` 之间决策，并保存可局部撤销的来源贡献，是否优于
公开文献中最接近的记忆巩固语义以及结构二既有对照。

本门不删除或绕开 actor / object identity / hidden-event cause / regime 四轴，不删除开放世界
unknown、多主体推断、可逆归因或具身反馈。所有方法读取同一 visible replay；evaluator truth
物理隔离。CARE 只有在先根据可见状态选中物理核验动作后，才能接收该动作的潜在观测结果。

## 2. 冻结实验臂

1. corrected AMG matched replay adapter；
2. O-STaR matched replay adapter；
3. sequential particle no consolidation；
4. Active Dreaming semantic-faithful matched adapter：合成反事实验证后才提升；
5. Auto-Dreamer semantic-faithful matched adapter：按下游效用和反事实移除收益做区域写入；
6. TrustMem semantic-faithful matched adapter：按 coverage / preservation / faithfulness
   transition score 决定 WRITE / REVISE / no-op；
7. brainctl semantic-faithful matched adapter：future utility / confidence / novelty / recency /
   type-prior admission，冲突进入 quarantine；
8. CARE without action regret：保留可逆账本，但只按置信度写入；
9. CARE-WM；
10. full rerun without reversible index；
11. evaluator-owned full-rerun oracle。

“semantic-faithful matched adapter”表示保留论文或系统的决策语义并在共同结构二接口上重新
实现，不表示运行作者官方代码或完整复现实验环境。该限制必须进入结果。

除 oracle 外，每个臂使用相同的三个 validation search points，按全部验证场景的
`true_environment_regret_per_step` 独立选择一个全局参数；完成后才打开新的 sealed holdout。

## 3. 冻结场景与外部回放

主确认集包含六个 D0 场景族：高多人污染、迟到身份纠正、开放世界隐藏事件、干净重复习惯、
低后果位置和后果模型高估。每个 holdout seed 跨六族聚类。

确认结果之外，使用仓库已有 D1 simulator-annotated replay 和 D2 real-perception example 做
transfer audit。外部回放不重新调参；D2 样例只有三个 test episodes，只能作为方向性护栏。

## 4. 冻结主要结果

- `true_environment_regret_per_step`：实际后果加权的 put-back/search regret、物理核验、
  模拟验证和修复成本；
- task/search success；
- path length、time 和总 search cost；
- owner-habit contamination；
- post-feedback recovery latency；
- promote / escrow / verify / retract / corrected-revision 回执；
- 四轴消费、同流哈希、真值访问时序和 exact local rollback 审计。

## 5. 冻结通过条件

CARE-WM 只有全部满足时才通过：

1. CARE − validation-selected strongest published neighbor 的 paired-cluster 95% CI 上界 `< 0`；
2. CARE − no consolidation 的 95% CI 上界 `< 0`；
3. 高污染、迟到纠正和开放世界三个 required family 均优于 strongest neighbor；
4. 干净、低后果和后果错设三族满足各自非劣界；
5. CARE − CARE-without-action-regret 的 95% CI 上界 `< 0`；
6. CARE 的 actor / identity / cause / regime 消费均大于零；
7. 所有非 oracle 决策均在读取 evaluator truth 前完成；
8. CARE 至少执行一次 promote、escrow、physical verify 和 retract/corrected revision；
9. 可纠正写入的 ledger replay 与局部撤销结果一致，且无重复提升；
10. D1 transfer 不劣于 strongest neighbor 超过 `+0.05/step`；D2 只报告，不作确认性显著性；
11. 无原始 holdout seeds 泄漏，artifact、源代码、配置和预注册哈希可复核。

如果第 1、2 或 5 条失败，停止把 CARE-WM 描述为结构二核心方法创新；结果仍保留，但不得用
缩小任务或删除完整结构二能力来挽救叙事。

## 6. 执行期接口修正记录

第一次冻结执行已完成 D0 validation/holdout 计算、尚未输出或查看任何结果时，D2 transfer audit
触发 CHEH exactly-once 守卫：D2 样例会把同一感知簇的 actor / mechanism / ordered-role 标注绑定到
相同 `evidence_cluster_id`。为避免把同一感知簇重复当作独立证据，所有实验臂统一增加可见信息去重：
每个共享簇只保留相对 reference prior 的 information gain 最大的一项，同分按字段名稳定排序，其余
进入 quarantine。该修正不读取 evaluator truth，不改变 D0/D1 数据、方法参数、seed、指标或通过阈值；
D2 仍仅作为方向性审计。最终报告必须披露 quarantine 数量与本执行期修正。
