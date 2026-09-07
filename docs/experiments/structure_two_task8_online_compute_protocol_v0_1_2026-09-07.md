# Structure Two Task 8 Learned Online-Compute Protocol v0.1

**冻结日期：** 2026-09-07  
**证据层级：** D0 development pre-death test（开发预死亡测试）  
**配置：** `configs/project_two_experiments/structure_two_task8_online_compute_v0_1.json`

## 问题

在训练数据、robot-visible input（机器人可见输入）、有效参数量、训练乘加数、推理乘加数和动作读出都相同的条件下，learned joint inference（学习式联合推断）是否比 learned matched two-stage inference（学习式匹配两阶段推断）得到更好的 consequential action cost versus online compute frontier（后果动作成本—在线算力前沿）？

历史 v0.4 的 exact-posterior（精确后验）FAIL 保持不变；本协议不重跑或改写它，而是补测它无法识别的学习与在线算力问题。

## 冻结三臂

1. `learned_joint`：直接学习 `p(C_group,E_group|x)`；
2. `learned_matched_two_stage`：学习 `p(C_group|x)p(E_group|C_group,x)`；
3. `information_restricted_factorized`：学习 `p(C_group|x)p(E_group|x)`，只作 interaction necessity（交互必要性）诊断，不是主要 claim arm（主张臂）。

三臂都只读观测序列，不读 scenario flags（场景标记）或 latent truth（潜在真值）。每个基础宽度 `w` 的有效参数和单样本推理乘加数均为 `8w`；通过两阶段条件头的激活方式和 epoch 数匹配，使每个调参候选的训练乘加数也相等。

## 数据隔离与判定

- 训练种子：64 个；验证种子：16 个；确认种子：32 个；三块互斥；
- 宽度：8、16、32；学习率：0.05、0.1；L2：0、0.001；
- 每个 arm × width 只按 validation mean consequential cost（验证集平均后果成本）选参，并在读取确认结果前写入哈希选择回执；
- 主比较为每个确认种子的 `matched_two_stage cost - joint cost`；
- 三个算力点做 familywise alpha 0.05（族错误率 0.05）的 Bonferroni 校正单侧配对簇自助下界；
- 任一冻结算力点下界大于 0 且平均相对改善至少 10%，并且全部预算公平回执通过，才记为 strict development signal（严格开发信号）。

## 预注册处置

- 有严格信号：进入 full-system guardrail integration（全系统护栏集成），然后才能考虑更昂贵的外部扩展；
- 无严格信号：默认先重做 joint mechanism（联合机制），不进入昂贵外部扩展；
- 两种结果都保留结构二全部七算子与既定研究范围；
- 两种结果都不能把 `task_8_formal_passed`、外部有效性、全系统护栏或七算子消融授权设为真。
