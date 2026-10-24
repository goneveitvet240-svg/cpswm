# E0 两步历史原生目标枚举 / bootstrap 对照：运行前协议

分支 `codex/pc-a-short-history-reference-20261023`；base `31477f8fd36e44bbaa19125802c7e509a9b8360b`（PR120）。已 fetch；用户授权12小时自主窗口内第三批任务。完整科研范围和既有模型/先验不变。

本批将 PR119 的给定近似父粒子单步枚举扩展为从初始状态连续两次更新的全候选路径枚举。采用现有 sparse32 validation 的 seed 7、8 两个 episode，取各自前两次 observe→predict 后已绑定 paid-location source 的观测快照，由既有 joint/independent_strata_v1 生产链生成一次，冻结后向所有比较臂提供同样序列。生成输入时已有合成环境提供受控搜索反馈，不能称为自然传感器校准。比较阶段不执行自适应搜索或不同政策获取信息。

比较 native_joint 与六显式势消融；每个目标下比较既有 systematic、既有 independent_strata_v1，以及 parent-prior × normalized-transition 的 bootstrap proposal，全部24粒子。bootstrap仍保留原生状态/三个RB blocks及所有目标势，使用相同候选支持生成器；支持构造仍调用共享neural实现，但proposal概率不使用其预测值，计时包含这一开销，不冒充最优实现。

精确参考枚举全部第一步候选并保留其后验为第二步父状态，不截取24个父粒子。所有父子路径的 target 使用既有 floor/transition/projection/independent likelihood/constraints。枚举不除q；bootstrap/采样在各自proposal下做重要性校正。第二步终端流式构造RB状态和读出，保存全部路径/对数目标/概率压缩原件；不将第二步结果冒充无限历史精确推断。

当前内核接收posterior-projection并附加独立位置likelihood，unresolved质量沿用固定投影规则。这里的“精确”指同一原生更新目标在全候选路径上的数值枚举，**不是已证明正确的原始生成模型Bayes后验**。报告明确模型失配/重复计证风险仍未解决。

指标沿用开发诊断：人物/机制/身份/原因/制度边际TV、完整路径TV、参考支持覆盖、同pre-ledger动作读出分布/排序、ESS、目标评分/transition/候选成本与时间。3个比较方法不是独立世界，2步和两个validation世界均不支持确认性显著性结论。完整状态轴保留；不为制造动作翻转调整权重，不开展新训练。

测试要求：可手算两步Markov目标；第一步与PR119参考一致；流式动作混合与原读出一致；bootstrap parent/transition cancellation；路径重复合并及不可伪造为新独立样本；输入快照与运行SHA绑定。更新账本不影响本批目标转移，比较pre-ledger读出；完整ledger/主动政策与长历史仍另验。结果、局部工程通过、B复核、统一验收、科学收益分开报告。
