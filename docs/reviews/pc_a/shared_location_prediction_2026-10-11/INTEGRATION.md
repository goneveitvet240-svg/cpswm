# 接入与原生事件时间边界

新增入口在 `src/cpswm/system/evaluation_operations/structure_two_shared_location.py`。本轮runner显式构造 `SharedLocationBelief` 和 `AuditedCurrentLocationActionState`；旧入口和默认配置不变。

`SharedLocationBelief.table()` 从基础软计数表计算各人物的跨前位置分布，向各上下文加 sharing/A 倍该分布；Markov使用不区分人物的全局分布。前位置非空时，向停留单元再加 persistence/A。人物线索作为已给定的后验替换人物边缘一次，不能再次作为似然相乘。学习仍采用原公开人物线索，缺失时均匀；未将模型反推的人物责任当作真值循环学习。

`finish()`复制本模型实际消费的 input、updates、found 作为来源并绑定内容hash。`revise_location_source(step_id, expected_digest, restore=False)`只接受已有来源与合法撤回/恢复状态；未结束的搜索不能修订。它从原始历史重新生成所有后续 `previous` 边，撤回槽保留时间但不贡献found，不把“来源撤回”解释为“真实全菜单否定”。原动作/成本/回执不改，下一次begin才产生新的预测；旧当前后验被清空。恢复返回原模型统计与后续预测。

这是位置头内部的来源所有权与局部审计，不是原生CCRR/RGRC事务，不能抵抗能同时篡改所有内存和工具代码的进程，也不授予主人习惯写入权。撤回的后续动作可能变化，原始已执行动作不会倒写成未发生。

适配器在原生observe之后读取真实 `step_results` 和 `runtime._last_observation.source_update_id`，核对当前step的event revision。完整运行中96个不重复时刻：47个已消费原位置，49个没有当前事件revision。所有新位置因子应用标记均false。原生位置已知的重查与原观测共享理想真值，不能按独立测量双计。

后续原生接线的必要条件：

1. 缺测时刻也有当前事件的预测态/唯一revision；不能复用旧事件锚点。
2. 新观测绑定当前episode、object、step、action、sensor/source及模型版本；区分新独立观测和对原证据的替换/重算。
3. 撤回时从有权威的原件重算受影响粒子、读出、长期贡献与依赖后续；保留已付动作账本；失败原子回滚。
4. 同状态因子化和简单控制接收同样信息、预算、撤回机会；评价后续动作成本与错误，不只人物概率变化。
5. 菜单外对象位置须由公开因果发现机制处理；本轮18次失败不许用私有真值位置修补。

这些条件明确了下一工程边界，未声称已实现原生缺测转移、新观测似然或开放支持扩张。自然测量模型/先验与新科学路线仍需按用户既有授权和显式协议推进。
