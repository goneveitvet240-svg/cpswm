# CARE-WM 精确反事实证伪门：预注册

日期：2026-08-29  
协议：`care-wm-exact-counterfactual-gate@0.1`

## 1. 冻结问题

当前结构二证据表明：固定巩固会稳定增加行动损失；冲突隔离能够消除主要伤害，但未证明
巩固相对无巩固具有正贡献。本门检验 CARE-WM 的最小机制主张：把长期记忆写入建模为
`promote / escrow / verify` 决策，并依据未来行动污染与修复成本，而不是只依据后验置信度
或当前任务信息价值，是否能够同时避免多人/身份误归因污染并保留真实重复习惯的学习收益。

本门是有限二元隐藏状态微型证伪，不是完整结构二、真实数据或论文证据。

## 2. 真值隔离

策略只接收 `VisibleCareCase`：候选习惯后验、预测行动后果、反馈时刻、验证成本和修复成本。
隐藏的 `habit_truth`、真实行动损失和 decoy 生成状态只存在于 evaluator。除
`full_rerun_oracle` 外，任何实验臂不得接收隐藏真值。

## 3. 冻结实验臂

1. corrected AMG：同后验下 top-hypothesis 提交，迟到反馈后允许完整修订；
2. sequential no consolidation：不写长期习惯，反馈前沿用旧习惯；
3. posterior-confidence consolidation：全局置信阈值提交，无精确回滚；
4. current-task VOI：只按下一次动作的信息价值决定是否验证；
5. TRW-style conflict quarantine：阈值提交，反馈冲突时精确撤销；
6. matched composed baseline：未来风险提交门 + current-task VOI + TRW 回滚；
7. CARE-WM：未来风险提交门 + prevented-contamination VOI + 有符号回滚；
8. full-rerun oracle：隐藏真值上界，只作锚点。

每个非 oracle 方法按臂、按场景族在 validation seeds 独立选参；完成后才打开本地 sealed
holdout seed 文件。所有结果按 seed 跨场景族聚类。

## 4. 冻结场景族

- 相同后验熵、高多人归因污染后果；
- 相同后验熵、低位置后果；
- 高置信身份诱饵与迟到纠正；
- 干净重复习惯，无及时纠正；
- 后果模型高估的 misspecification guardrail（错设护栏）。

前两族冻结相同的先验、证据强度、噪声和 decoy rate，只改变长期行动后果。另执行两个
机械审计：同后验熵但不同长期后果；同即时行动代价但不同长期后果。置信门和 current-task
VOI 应保持同决策，CARE-WM 必须允许不同决策。

## 5. 主要指标

- `net_action_loss_per_step`：行动错误、验证和修复的总成本除以时长；
- `contamination_auc_per_step`：错误长期提交在时间上的面积；
- `post_correction_regret_per_step`：明确纠正后仍由旧提交造成的损失；
- `missed_adaptation_auc_per_step`：真实新习惯未被提交造成的面积；
- `rollback_equivalence_rate`：迟到纠正后有符号账本是否等价于 leave-one-cluster-out
  full rerun；
- verify/promote/escrow/retract 运行时回执。

## 6. 冻结通过条件

全部同时满足才把 CARE-WM 标为 `candidate_positive_mechanism`：

1. CARE − matched composed baseline 的 paired-cluster 95% 区间上界 `< 0`；
2. CARE − no consolidation 的区间上界 `< 0`；
3. 高污染与迟到纠正两个 required family 的 CARE 平均损失更低；
4. 干净重复习惯族 CARE 优于 no consolidation；
5. 低后果族相对 matched baseline 不劣于 `+0.03/step`；
6. 后果错设族相对 matched baseline 不劣于 `+0.06/step`；
7. CARE 在全部可纠正 holdout cases 上达到 exact rollback equivalence；
8. CARE 至少产生一次 verify、promote、escrow 和 retract 回执；
9. 两个 counterfactual sensitivity audit 均通过；
10. 无原始 holdout seed 泄漏，artifact 与源码/配置/预注册哈希可核验。

如果 CARE 只击败固定置信巩固、却不能击败无巩固或 matched composed baseline，停止本轮
CARE-WM 方法收益叙事。即使全部通过，也只允许声称有限合成机制候选成立；下一门仍须接入
完整四轴粒子后验、corrected AMG/O-STaR 增强基线和真实/半真实回放。
