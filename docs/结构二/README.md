# 结构二文档入口

最后更新：2026-09-11
当前结论：**项目所有者已选择 Route C、Architecture A、`P5_FIRST` 以及三臂方法定义 `A1 + B1`，完整 H/R/I/C/Z/r/V、三个 RB blocks 和七算子范围保持不变。首轮 matched direct `P5_FULL_EAGER` typed SEARCH/PUT_BACK 死亡测试已完成：1,920 个 matched steps，1,243 次真实七算子正路径和 677 次不伪造转移的负观测闭环；SEARCH 三臂打平，P5 的 PUT_BACK error 为 0.6849，差于 learned two-stage 的 0.2740 和 AMG 的 0.0536，注册行动信号为 false。失败后定位到两个接线问题：v0.1 P5 adapter 未接入已冻结的 v0.6 dual-timescale readout；且 PCHMP 已形成的人物后验被 CIAV 用原始均匀 prior 重算并抹掉。后者已按 sequential Bayes 修复并通过 production/adaptive/P5 定向回归；单 episode 修复后 posterior 已非均匀，但完整 60-episode 运行尚未完成。因此 v0.1 必须保留为失败，修正版只能标为 post-hoc，已打开的 test split 不得伪装成新预注册结果。下一步先冻结修复实现，再运行完整 post-hoc 三臂诊断和 production debt replay。validation-only calibration 与固定解析阈值基线均保留但尚未执行。组合效用、长期人物记忆污染、Task 8 正式通过、联合行动收益、外部强基线胜利、外部有效性和七算子行动贡献均未成立。**

这里是方向结构二的规范阅读入口。仓库保留了大量按日期冻结的协议、实验和审计文件；那些文件是
证据档案，不应让第一次接触项目的人逐个猜阅读顺序。

## 推荐阅读顺序

1. [00_结构二一页读懂.md](00_结构二一页读懂.md)
   用一个家庭物品故事解释研究问题、七个算子、最终输出和当前真实状态。
2. [01_结构二完整框架与技术路线.md](01_结构二完整框架与技术路线.md)
   说明从传感器证据到隐藏事件、人物习惯、可逆记忆、主动验证和具身行动的完整数据流。
3. [02_结构二任务地图与当前进度.md](02_结构二任务地图与当前进度.md)
   说明工作包、Task 7--13、P5、Gate A/B、D0--D4 分别在做什么，哪些完成、失败或尚未运行。
4. [03_结构二实验协议与复现入口.md](03_结构二实验协议与复现入口.md)
   说明指标、硬护栏、数据层级、基线、运行入口、工件和复现边界。

## 必须保留的详细依据与历史证据

- [完整研究问题与范围](项目方向结构二_选择性观察隐藏事件同屋多人非平稳个体习惯_v1.0.md)
- [统一单篇论文创新总纲](方向结构二_全框架统一单篇论文创新总纲_v1.0.md)
- [选定推断主干与权限合同](方向结构二_神经摊销类型化粒子修订与可逆巩固方法冻结_v1.0.md)
- [Task 7、Task 8 与外部验证最终决定](方向结构二_Task7_Task8与外部验证用户决策记录_2026-09-06.md)
- [P5 优先与路由校准用户决策](结构二_P5优先与路由校准用户决策记录_2026-09-10.md)
- [adaptive-path P5 三臂行动死亡测试 v0.1 结果](../experiments/structure_two_p5_three_arm_death_test_result_v0_1_2026-09-11.md)
- [Task 8 在线算力流程复核](../reviews/structure_two_priority_sequence_audit_2026-09-07.md)
- [Task 8 learned online-compute v0.1 结果](../experiments/structure_two_task8_online_compute_result_v0_1_2026-09-07.md)
- [Task 8 v0.1 运行后范围复核](../reviews/structure_two_task8_online_compute_postrun_audit_2026-09-07.md)
- [Route C 完整联合状态回放反馈环 v0.1](../experiments/structure_two_stateful_full_joint_result_v0_1_2026-09-07.md)
- [Route C 两轮对抗审核](../experiments/structure_two_stateful_full_joint_two_round_adversarial_audit_2026-09-07.md)
- [Route C 动作响应完整科学闭环 v0.2（历史命名与历史快照）](../experiments/structure_two_full_scientific_loop_result_v0_2_2026-09-08.md)
- [Route C v0.2 两轮对抗审核](../experiments/structure_two_full_scientific_loop_two_round_adversarial_audit_2026-09-08.md)
- [Architecture A / P0–P5 两轮对抗审核](../experiments/structure_two_adaptive_runtime_two_round_adversarial_audit_2026-09-10.md)
- [Route C v0.2 第二次两轮对抗审核](../experiments/structure_two_full_scientific_loop_second_two_round_adversarial_audit_2026-09-08.md)
- [Route C 端到端有效性前置门结果与历史解释修正](../experiments/structure_two_end_to_end_validity_gates_result_2026-09-09.md)
- [Architecture A 与 adaptive-compute pre-death 协议](../experiments/structure_two_adaptive_compute_predeath_protocol_v0_1_2026-09-09.md)

## 如何理解旧文件

- 带日期的 `experiments/` 文件是当次实验快照；后续实验可以否决它，但不能改写历史。
- `reviews/` 文件是某一轮审计，不自动等于最终科学结论。
- 名字相似的 Gate A/Gate B 可能属于不同协议，引用时必须写协议号和版本。
- `implemented`、`tests passed`、`receipt verified` 只表示对应工程性质成立，不等于论文方法胜出。
- `D0 development holdout` 不是 independent confirmation（独立确认），不能升级成外部有效性。

## 当前唯一安全的对外一句话

> 结构二研究一个长期家庭机器人怎样在选择性观察、隐藏事件、多人共享、未知人物和习惯变化下，
> 维护可撤销、可追溯的个体化世界模型，并用主动验证改善搜索、放回、交接与协助；当前已保留完整
> 七算子范围，建立 evaluator-local D0 原型、类型化 SEARCH/PUT_BACK 构念诊断和可执行中和诊断，
> legacy A seam 已有实例—调用—消费回执，P0–P5 只有计划注册表和部分内核；历史 Route-C 与
> P0–P5 后果性轨迹的完整生产身份、组合行动
> 收益、长期污染控制、外部强基线、ProcTHOR、真实 RGB-D 和独立托管确认门仍未通过。
