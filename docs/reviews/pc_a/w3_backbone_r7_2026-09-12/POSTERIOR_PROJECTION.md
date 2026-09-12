# 批次二：真实生产后验投影消费

默认 CorePrototypeSpine 观测路径在实际 OPCEU → ORRER → PCHMP → CF-BOCPD/CCRR → RGRC 执行后发布真实 PCHMP 输出及完整生产输入。消费者解析运行内来源，重验原始内容、源修订与事件对象、当前世界支持、快照、原始证据与生产算子计算；消费系数必须等于该候选的真实 PCHMP 后验对数值。

来源身份绑定运行与生产 revision，不是当前快照 UUID 的别名。一个真实来源只能贡献一次；重复原输入是无副作用重放，换 evidence cluster 再使用已消费来源会拒绝。历史源保留，撤回、纠正、下一观测或跨运行输入不能越过当前依赖检查。完整来源体参与执行摘要；原始完整性验证后，其语义对应值保留所有引用和派生哈希。

真实正例来自默认观测，未手填授权或注册收据。正例权重与解析式 `4p/(4p+4/3+1)` 比较，且 known、unknown 和 unresolved 质量均非空。负例含随机/current UUID/外来运行和对象/撤销/过期/错误数值/完整重封的错误后验、父链、上下文、世界和重放新键。RuntimeError 与 KeyboardInterrupt 在实际消费完成边界注入，检查统计、账本、动作、去重和原算子实例恢复，再合法重试。

验证：projection_preflight 107 passed；原 647+67 = 714 passed，exit 0（868.63 秒）。随后仅把 Optional 来源 ID 的字典查询改成显式 None 分支以通过类型检查，再跑 projection_typed_final 85 项。每组命令、真实退出码和修改前后源码清单保存在同名前缀 command.json；不同版本结果不混称同一源码测试。

范围：这是实际 PCHMP 后验的**已支持 known-instance 投影**，不发明实例关联概率。显式候选现在可真实消费，但候选生成、完整联合似然/转移、三个 RB 增量来源、默认行动及自主反馈策略尚未因此接通。此批次不能签收完整主干或七算子科学收益。原 714 项没有删除、skip、放宽阈值或修改断言。

## 后续反例与修正（不得用前次绿色覆盖）

`projection_typed_final` 实际为 **82 passed / 3 failed / exit 1**。原因不是 Optional 分支，而是共享旧散列器把 CF-BOCPD 的 frozenset 原因集合键转成 repr，Python 哈希种子及 deepcopy 能改变等价集合的显示顺序。单改成精确类型值比较后，新增独立进程种子 5/11 又检出公开 getter 深拷贝后的原始来源哈希误报：`projection_hashseed_fixed` **85 passed / 2 failed / exit 1**。

最终给新 native workspace 使用保留集合类型/全部成员/完整引用的确定序列化，继续验证完整原始内容摘要；没有删除授权字段、禁用原始哈希检查，也没有改动共享 W1/W2 的旧散列或旧工件。完整重封负例使用相同正式序列化重封，仍须被实际生产关系核验拒绝。`projection_canonical_sets` **109 passed / exit 0**，包括种子 5/11 的独立进程合法消费。最后仅调整 cast 与导入排序，通过 mypy，完整最终回归另行记录。以上各次失败均原样保留。
