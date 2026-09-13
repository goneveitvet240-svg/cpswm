# 结构二文档入口

2026-09-13 用户后续选择：C（位置＋朝向）与本地小预算开发已生效。见[位姿开发报告](../reviews/pc_a/pose_local_dev_2026-09-13/REPORT.md)及对应配置；完整范围与正式架构/训练顺序选择协议不变。这不代表真实姿态感知、模型训练或完整闭环已经完成。

2026-09-13 组件进展补充：[完整提议合同与 ProcTHOR 调度交付](../reviews/pc_a/proposal_scheduler_2026-09-13/REPORT.md)。125 项相邻组件测试通过；真实单屋 7 模拟日几何调度跑通，但角色证据与训练数据仍未就绪，不覆盖下文科学/完整主干未验收结论。

最后更新：2026-09-11
当前结论：**项目所有者已选择 Route C、Architecture A、`P5_FIRST` 以及三臂方法定义 `A1 + B1`，完整 H/R/I/C/Z/r/V、三个 RB blocks 和七算子范围保持不变。首轮 v0.1 匹配死亡测试无信号；随后定位并修复 readout 漏接与 PCHMP→CIAV sequential actor-prior reset 两个问题。完整 60-episode post-hoc 重算中，P5 owner-habit posterior 在 1,870/1,920 步非均匀，PUT_BACK error 从 0.6849 降到 0.0401，优于 learned two-stage 的 0.2740 和 AMG 的 0.0536；但相对 AMG 的绝对改善仅 0.01354，低于冻结门槛 0.02，所以严格 P5 action signal 仍为 false。production debt replay 已在 60 个 episodes 的 1,243 个正转移上确认：`P0_SAFE_DEFERRED → expired debt replay P5` 与 direct P5 的 12 项后验、读出、动作、欠账和七算子路径检查全部一致，失败为 0，fresh recomputation 逐字段一致。该工程确认不重测科学信号，也不覆盖负观测、异位置反馈、并发欠账或长期路由效用。下一决策点是选择新的未见 D0 holdout 或独立托管确认集；在新数据复现信号前，不启动 validation-only router calibration，固定解析阈值继续保留为基线。组合效用、长期人物记忆污染、Task 8 正式通过、外部有效性和七算子行动贡献均未成立。**

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
- [P5 readout + sequential-prior post-hoc 诊断结果](../experiments/structure_two_p5_readout_posthoc_diagnostic_result_v0_1_2026-09-11.md)
- [P5 production debt replay 工程确认结果](../experiments/structure_two_p5_debt_replay_confirmation_result_v0_1_2026-09-11.md)
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
