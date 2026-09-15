# 开发中失败与修复（非独立审核）

本轮修复方在源码冻结前实际遇到并处理：

1. 新解码器的跨快照反例已经被旧位置来源合同拒绝，但测试误期待更晚的 `cross-snapshot` 错误。实际错误为 `location does not resolve in the frozen snapshot catalog`；只纠正测试定位，不放松生产条件。
2. 新采集函数增加执行历史协议后，调用点最初漏传参数。mypy报告 `Missing named argument execution_history`；功能正例显示失败动作又被选择。补上 `execution_history=stream.observation_history()`，确保真实保存回执进入下次模型输入，保留永久正例。
3. 初始mypy发现可空命令赋值类型不一致；增加明确类型及执行前非空断言。整理新增源码的导入及格式，未改变科学协议。

上述记录摘录实际工具输出。最终结论以冻结源码的regression.json/XML为准；不是两轮整体对抗审核结果。

4. 修复方源码审视发现，有限极大logits可让极小条件概率下溢为0、静默丢掉受支持分支。最终版在构建分布时明确拒绝，保留永久反例；并把运行工厂的仓库路径检查移到导入前。初版252回归仍保留为regression_initial系列，最终254回归绑定新SHA，不沿用旧结果。
