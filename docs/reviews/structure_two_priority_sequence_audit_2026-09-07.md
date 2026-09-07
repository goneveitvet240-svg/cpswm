# 结构二优先级流程复核（2026-09-07）

## 结论

原流程方向合理，但顺序需要收紧：先冻结当前工作区，再执行 Task 8 的 learned equal-compute（学习式等算力）D0 pre-death test（预死亡测试）；Task 7 的 combined（组合式）污染干预紧随其后；D2 timing pilot（真机时序试跑）可以并行准备，但不得阻塞最低成本否证。Task 10–13 在 Task 8 出现可重复的核心价值信号前，不继续扩大工程投入。

这不是缩小结构二。统一七算子框架、hidden-event inference（隐藏事件推断）、multi-actor reasoning（多参与者推理）、open-world unknowns（开放世界未知）、reversible attribution（可逆归因）和 embodied feedback loop（具身反馈闭环）全部保留。

## 为什么这样排

1. 历史 Task 8 v0.4 已经是正式 FAIL；它比较的是已经存在的 exact posterior（精确后验），identity temperature（恒等温度）下的 exact chain-rule two-stage（精确链式两阶段）可以代数重建联合分布，因此不能回答“学出来的联合机制在同等在线算力下是否更值”。
2. 新 Task 8 直接命中当前最危险的不确定性：联合机制是否在 same data / parameters / state access / training compute / inference compute（同数据、参数、状态访问、训练算力、推理算力）下改善 action-quality versus compute frontier（动作质量—算力前沿）。这是目前最便宜、最能提前叫停错误工程扩张的实验。
3. Task 7 combined 路线已经有明确机制假设，但它应在 Task 8 判定核心表征路线值得继续后接入完整 contamination intervention（污染干预），否则会先支付较大的系统集成成本。
4. D2 时序统计会影响未来真机协议中的 `tau_verify`、遮挡、同步和标注工时，因此可以并行做设备与记录格式准备；它不会替代 Task 8 的方法价值检验。

## 执行前冻结

- 冻结提交：`81e5015 checkpoint: freeze structure two local diagnostics`
- 冻结前全量回归：`3507 passed, 1 xfailed in 1672.85s`
- 该提交只作为当前本地诊断状态的可回退检查点，不改变历史 Task 8 v0.4 的 FAIL，也不把本地诊断晋升为 D1/D2 或 formal evidence（正式证据）。

## 本轮执行门

Task 8 v0.1 只允许产生 development signal（开发信号）：

- 主轴：online compute（在线算力）；
- 次轴：distribution shift（分布偏移）与 information restriction（信息限制）；
- 三臂：learned joint（学习式联合）、learned matched two-stage（学习式匹配两阶段）、information-restricted factorized（信息受限因式分解诊断）；
- validation-only selection（仅验证集选参）后再打开 confirmatory seeds（确认集种子）；
- 每个预算点严格匹配有效参数量、训练乘加数与推理乘加数；
- Bonferroni（邦费罗尼）校正后单侧 paired-cluster bootstrap（配对簇自助法）下界大于 0，且相对成本改善至少 10%，才算严格开发信号。

无论结果正负，本轮都不能宣称 Task 8 正式通过、外部有效性成立、全系统 guardrails（护栏）完成或七算子消融获准。

## 审核覆盖边界

本轮覆盖流程依赖、预算公平、确认数据隔离、逐样本结果到结论的推导链，以及伪造完整正向路径。它仍是局部 D0 审核，不是穷尽式安全审计，也没有独立第二机器 custody（保管链）、ProcTHOR 回放或 D2 真机证据。
