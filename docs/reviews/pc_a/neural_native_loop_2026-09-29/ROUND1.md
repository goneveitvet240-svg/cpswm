# 第一轮交付：神经原生枚举与纠错重放

受测源码 `08e5cc1f5cdb049d7bbd68b66e4da829a59e4efd`，43/16 顺序两轮 A 局部对抗自审通过，mypy 375 文件和 Ruff 通过，七条命令前后所有 Python/依赖与同一 Git 提交相同。独立审核人数0，未替代B验收。

三个真实开发检查点均已运行：typed_factor_graph_transformer、slot_conditioned_perceiver、autoregressive_typed_graph_policy。每个仅做2步受控组件优化，非自然联合训练；均由12个已消费来源撤回1个，重算11个，生成22条原生记录、2个当前联合原子，保留6维位姿统计，11份模型执行证明；旧视图被拒绝，新SQLite恢复视图及producer状态完全一致，长期账本未因神经重放发生额外改变。

实际执行合计280.95秒，日志/命令/源码清单与逐臂结果见 evidence/round1。完整63MB检查点、SQLite和结果保存在主仓 `output/neural-native-loop-20260929/round1-attempt01/`，Git提交只含轻量证据。

此前真实“已加载验证函数替换后完整假概率包被接收”的缺陷已修复并重审；见 DESIGN.md 和保留的开发失败日志。合法路径及完整伪造、加载依赖、纠错、重放和账本边界分别检查，不以负例数量代替统一验收。

边界：有限配置支撑的 branch/preserve_unresolved 枚举，积分系数q抵消1/q；验证的是网络实际执行与原生接入，不能声称网络q改善精确枚举后验。完整六操作学习核、自然训练、独立标定、自然记忆和完整仿真任务成功仍未闭合。第一轮已通过后按 SIMULATION_PLAN.md 进入第二轮。
