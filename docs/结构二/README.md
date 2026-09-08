# 结构二文档入口

最后更新：2026-09-08
当前结论：**项目所有者已选择 Route C；完整 H/R/I/C/Z/r/V、三个 RB blocks 和七算子现已进入 action-responsive（动作响应）闭环。跨轴交互已由 train/validation 学习并冻结，RGRC 正反例与撤销路径已激活，七个算子均完成“保留算子、仅中和作用”的消融。工程缺口已补齐，但 joint 与 matched factorized 行动遗憾仍打平，27 步中 0 步改变最终动作，owner contamination 均为 0.333333；论文级优越性、强外部基线胜利、外部有效性和七算子行动贡献仍未成立。**

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

## 四份必须保留的详细依据

- [完整研究问题与范围](项目方向结构二_选择性观察隐藏事件同屋多人非平稳个体习惯_v1.0.md)
- [统一单篇论文创新总纲](方向结构二_全框架统一单篇论文创新总纲_v1.0.md)
- [选定推断主干与权限合同](方向结构二_神经摊销类型化粒子修订与可逆巩固方法冻结_v1.0.md)
- [Task 7、Task 8 与外部验证最终决定](方向结构二_Task7_Task8与外部验证用户决策记录_2026-09-06.md)
- [Task 8 在线算力流程复核](../reviews/structure_two_priority_sequence_audit_2026-09-07.md)
- [Task 8 learned online-compute v0.1 结果](../experiments/structure_two_task8_online_compute_result_v0_1_2026-09-07.md)
- [Task 8 v0.1 运行后范围复核](../reviews/structure_two_task8_online_compute_postrun_audit_2026-09-07.md)
- [Route C 完整联合状态回放反馈环 v0.1](../experiments/structure_two_stateful_full_joint_result_v0_1_2026-09-07.md)
- [Route C 两轮对抗审核](../experiments/structure_two_stateful_full_joint_two_round_adversarial_audit_2026-09-07.md)
- [Route C 动作响应完整科学闭环 v0.2](../experiments/structure_two_full_scientific_loop_result_v0_2_2026-09-08.md)
- [Route C v0.2 两轮对抗审核](../experiments/structure_two_full_scientific_loop_two_round_adversarial_audit_2026-09-08.md)
- [Route C v0.2 第二次两轮对抗审核](../experiments/structure_two_full_scientific_loop_second_two_round_adversarial_audit_2026-09-08.md)

## 如何理解旧文件

- 带日期的 `experiments/` 文件是当次实验快照；后续实验可以否决它，但不能改写历史。
- `reviews/` 文件是某一轮审计，不自动等于最终科学结论。
- 名字相似的 Gate A/Gate B 可能属于不同协议，引用时必须写协议号和版本。
- `implemented`、`tests passed`、`receipt verified` 只表示对应工程性质成立，不等于论文方法胜出。
- `D0 development holdout` 不是 independent confirmation（独立确认），不能升级成外部有效性。

## 当前唯一安全的对外一句话

> 结构二研究一个长期家庭机器人怎样在选择性观察、隐藏事件、多人共享、未知人物和习惯变化下，
> 维护可撤销、可追溯的个体化世界模型，并用主动验证改善搜索、放回、交接与协助；当前已建立完整
> 七算子动作响应开发闭环和可执行中和消融，但仍需通过联合行动收益、外部强基线、ProcTHOR、真实 RGB-D
> 和独立托管确认门。
