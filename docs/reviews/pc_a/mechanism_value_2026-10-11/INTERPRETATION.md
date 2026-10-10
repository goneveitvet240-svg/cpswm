# 源码定位及结论边界

## 两条路径必须分开

当前 ContinuousEvidenceInput / StructureTwoProductionSystem 的 primary pass 仍 force_long_term_write_blocked=True；同地点 CIAV 只核验快事件。此前94/94任务的长期写入为0，不是完整机制价值检验。

本轮 Route-C 是仓库已经存在的完整状态开发实现：StatefulFullJointActionState → StatefulFullJointRuntime，结合已有七算子回放链。它会执行长期提升/撤回、反馈修正、三个 RB blocks 和七轴跨时状态。本轮没有绕过生产写授权，也没有把开发入口冒称自然生产闭环。

## 当前生产读出的严格支配性

runtime_readout.current_action_readout() 固定 fast=0.7、surviving=0.2、regime=0.1，fast_confirmation_observations=1、unconfirmed_fast_discount=1、pending_correction_discount=1。fast 是最近有效主人事件位置上的单点分布。

存在有效 fast 事件时，它选择的位置至少得到0.7，其他位置即使汇集两条慢分支全部质量也至多得到0.3；归一化不改变大小关系。因此相同 fast 历史下，慢模型无法翻转当前 argmax。合法反馈若改变 fast 历史仍能改变动作；无合格 fast 的冷启动情况不属于此结论。测试调用实际生产混合函数验证最坏对立的9种组合，而非仅检查参数常量。

来源：src/cpswm/system/runtime_readout.py；prototype_spine.py 的 action_location_distribution、_latest_owner_event_component、_mix_action_components、_apply_pending_correction_discount。

## 完整联合开发路径混用了任务读出

StatefulFullJointActionState.predict() 先计算 native，但在有 particles 后，用同一 runtime.action_distribution() 的 ranked[0] 作为 PUT_BACK，并用 ranked 作为 SEARCH 顺序。

这份联合分布以主人的习惯、owner/target 粒子和其 RB cell 为主体。客人把物体移到别处时，“主人通常放哪里”和“物体现在在哪里”可以不同。相同首选位置不可能在这种时刻同时答对两个问题。报告按 evaluator-only 标签统计冲突机会和分阶段错误，并把这个缺陷与联合密度是否有效分开。

此外，该开发包装器的 CIAV 选择来自底层 spine；joint/factorized 获得相同模拟验证输入。这有助于识别联合推断的额外作用，但不验证联合后验驱动主动采样的净效用。

## 对论文主张的含义

七轴/三个RB/七算子确实运行与改变状态，是可执行性和局部机制证据。joint 与具有相同完整状态、预算、观测和反馈的 factorized 若任务相同，就不能把概率变化或回执数量当作联合建模独有收益。简单控制的读出消融仍复用底层推断，不能据此断言整个底层七算子可删除；AMG是仓库匹配适配器，不是原作者完整机器人系统。

本面板为有限 D0 开发家族和已有模板；相同种子模板可能相关，95% seed bootstrap 只作描述。未测真实自然人物、多物体多家庭泛化、真实运动代价、完整七算子贡献拆分、Task9四耦合或B独立设备验收。完整研究范围保留。

后续优先修复任务分开的决策接口，并让慢机制有实际影响动作的通道；这是接口/诊断工作，不应先叠加新模型来解释当前负结果。任何改读出/权重的候选都需重新在开发集选择并与强对照比较，不能用本轮评价集追调后继续称确认实验。是否继续调整研究机制由用户决定。
