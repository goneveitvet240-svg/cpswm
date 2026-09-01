# CARE-WM 精确反事实证伪门：结果

日期：2026-08-29  
协议：`care-wm-exact-counterfactual-gate@0.1`  
证据等级：有限合成精确反事实机制证据，不是完整项目二、论文或机器人证据

## 1. 判定

本门通过：11 个冻结判据全部为 `true`，因此只能把 CARE-WM 标记为
`candidate_positive_mechanism`。这表示“根据未来行动污染与验证成本决定
promote / escrow / verify，并保留可精确撤销的写入账本”在本门的有限生成模型中成立。

它不证明 CARE-WM 超过已发表系统，也不证明名称、组成部件或完整机制具有文献新颖性。

## 2. 冻结设计

- 8 个 validation seeds，24 个 sealed holdout seed clusters；
- 5 个场景族，每个 holdout cluster 在全部场景族中配对，共 120 个 holdout cases；
- 8 个实验臂，包含 matched composed baseline、no consolidation、corrected AMG 和
  full-rerun oracle；
- 4,000 次 paired-cluster bootstrap；负差值表示 CARE-WM 更好；
- 测试集打开前已冻结场景、搜索空间、非劣界值、种子承诺和通过条件。

## 3. 总体行动结果

| 对照 | CARE − 对照平均每步净行动损失 | 95% 配对簇区间 | 结论 |
|---|---:|---:|---|
| matched risk + TRW + current-task VOI | -0.06379 | [-0.10138, -0.02741] | CARE 更低 |
| no consolidation | -0.15176 | [-0.18290, -0.12033] | CARE 更低 |
| posterior confidence | -0.10813 | [-0.16143, -0.05707] | CARE 更低 |
| current-task VOI | -0.10813 | [-0.15845, -0.05674] | CARE 更低 |
| TRW conflict quarantine | -0.07006 | [-0.10853, -0.03119] | CARE 更低 |
| corrected AMG | -0.07610 | [-0.11547, -0.03589] | CARE 更低 |
| full-rerun oracle | +0.05888 | [+0.04665, +0.07499] | CARE 仍有明显上界差距 |

## 4. 场景分解

| 场景族 | CARE − matched | CARE − no consolidation | 解释 |
|---|---:|---:|---|
| 高多人归因污染 | -0.17188 | -0.15997 | 验证阻止高后果错误写入 |
| 迟到身份纠正 | -0.21406 | -0.17031 | 托管与纠正降低污染和修复损失 |
| 干净重复习惯 | +0.03281 | -0.44844 | 相对 matched 多付验证成本，但保留了相对不巩固的学习收益 |
| 相同熵、低后果位置 | 0.00000 | -0.00964 | 达到冻结非劣护栏 |
| 后果模型高估 | +0.03417 | +0.02958 | CARE 过度验证；仍在 `+0.06/step` 错设护栏内 |

总体改善不是无条件占优：它主要来自高后果污染与迟到纠正；在干净和后果错设场景中，
验证成本是明确代价。

## 5. 机制审计

- CARE 回执总计：70 verify、57 promote、63 escrow、4 retract、4 corrected revision；
- 全部适用 case 的 `rollback_equivalence_rate = 1.0`；
- 非 oracle 策略只接收 `VisibleCareCase`，隐藏真值只在 evaluator 内；
- 相同后验熵与相同即时 VOI 审计中，置信门和 current-task VOI 保持同决策，CARE 会响应
  长期行动后果；
- 内容哈希与确定性重算均通过：
  `bafb8737323f73b78a8c4ca6d803f3e9d80884b6e0fbdb8245a425321f0459cd`。

首次 artifact 核验曾把浮点数 `1.052202166...` 中的连续数字误判为原始 seed 泄漏。
修复仅把检测从任意子串改为独立 seed token 检测，并增加回归测试；未修改方法、场景、
阈值或数据。随后重新生成 artifact，哈希核验和确定性重算通过。

## 6. 当前结论边界

这道门回答的是“该最小决策机制在一个真值隔离的有限模型中是否可能产生行动收益”，
答案为是。它没有回答：

1. 是否优于 Active Dreaming Memory、Auto-Dreamer、TrustMem、ChronoMem 或其他真实系统；
2. 预测行动后果在 RGB-D、家庭场景或机器人执行中是否足够准确；
3. 多主体、开放世界未知、隐藏事件与四轴粒子后验耦合后是否仍有收益；
4. 验证动作的真实路径、时间、能耗和失败成本是否会吃掉收益；
5. 该机制是否构成可发表的新颖贡献。

因此，下一道必须是 strongest-neighbor matched gate：把最接近方法按其原始语义忠实接入
相同 replay，并以 success、path/time/cost 和 true-environment regret 为主要结果。
