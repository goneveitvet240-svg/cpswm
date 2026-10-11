# 入口与集成边界

本轮提供并在既有反馈链中实际运行了新开发入口 `build_task_separated_full_joint_state`，所在文件：`src/cpswm/system/evaluation_operations/structure_two_task_readout.py`。调用方式：

```python
from cpswm.system.evaluation_operations.structure_two_task_readout import (
    build_task_separated_full_joint_state,
)
from cpswm.system.evaluation_operations.structure_two_stateful_full_joint import FullJointArm

state = build_task_separated_full_joint_state(
    repository_root=repository_root,
    dataset=dataset,
    episode=episode,
    arm=FullJointArm.STATEFUL_FULL_JOINT,
    profile="v06",
)
# 使用原有 observe -> predict -> feedback 顺序与原评价器。
```

|输出或状态|新入口的来源|边界|
|---|---|---|
|PUT_BACK|完整联合后验＋既有RGRC账本的习惯分布|保留旧排序的确定性tie-break|
|SEARCH|底层原生搜索排序：最近检测位置优先，其余位置按既有习惯分布|最近观测可能过时；没有补齐未观测移动，更没有新增视觉定位器|
|unknown probability|原完整联合状态|没有新人物似然或概率门槛|
|反馈回执|最终实际PUT_BACK与完整SEARCH排序；直接调用也绑定|保持原修订、撤回与下一动作因果链|
|慢配置|只改fast/surviving/regime三权重；通过原基础分布继续进入联合更新/账本|候选不是纯输出重排；跨配置状态可不同；严格控制需同配置|
|冷启动|没有联合粒子时使用原生预测|回执显式标明，不伪装联合动作|

历史 `build_stateful_full_joint_state` 入口保留原行为，便于重放PR106及旧Route-C证据；所有旧调用方未被批量切换。新入口已被本轮runner实际接入并验证，**不等于共享集成分支/所有应用已经迁移**。迁移需B按精确SHA复核后，由A接入共享集成；本轮草稿PR不自动合并。

默认 `current_action_readout()` 未改，生产写授权未改。D0的CIAV仍是现有模拟观测实现（选择动作后在realizer内使用隐藏真值产生反馈），不是从自然人物图像得到的校准似然。也没有让联合后验驱动主动验证策略。这些属于尚待完成的实证接线，不以本轮动作接口改善替代。
