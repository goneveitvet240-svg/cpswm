# 批次三：延期取消后的父贡献恢复

原公开反例 `cancellation_before.json`：Project One 返回 deferred，后续真实 CCRR 将其取消并返回 rejected，但父记录、父资格和父快记忆都没有恢复，失败的子记录仍留在 observed/fast store。脚本退出 0 只代表记录完成。

修后 `independent_final_cancellation.json`：相同原样脚本仍先产生非空 deferred；终态 rejected 后，父 committed/observed/fast/eligible 均为 true，子 committed/observed/fast 均为 false，后续触发观测仍保留，延期队列为空。

实现：

- 正式请求进入延期前保存原先实际存活的父贡献、派生贡献和快记忆，而非事后猜测哪些墓碑应恢复。
- 取消保留原纠正事务，追加内容绑定的 `DeferredCorrectionCancellation`。原始 request fingerprint、父/子记录、操作序号、触发 revision、恢复输入和完整体摘要均保留。
- 通过原有 Hybrid 账本和原有模型重放恢复，保留新的触发观测。恢复物理账本 revision 与逻辑 revision 有显式映射，不删除旧账本记录或复用已撤销物理身份。
- 原先已批准的父资格保持不变；取消子 revision 不再写入合格。取消既不是新 CCRR 授权，也不允许十条原阻断观测被重建带入。
- 原有派生贡献只从请求前冻结的实际贡献集合恢复；如果后续输入使父记录不再存活，不强制晋升。已经取消的请求再次提交只追加合同规定的 replay_noop 审计回执，不重复计账。
- 阶段重放结果进入当下 cause snapshot、统计、动作读出与终态回执，原算子实例的异常恢复约束仍保持。

新增 27 项测试覆盖 core/production wrapper、零/一/两代纠正初态、五个真实中断点 × RuntimeError/KeyboardInterrupt、取消后再次纠正/撤回、跨运行语义一致、原非空派生贡献恢复、以及 digest/request/parent/trigger/sequence/缺失取消日志的受控错误检出。最终与原 R5 99 项合计 126 项通过；最终全部 812 项也通过。

独立参考扩展：从冻结原始父输入与操作顺序重建“纠正→取消→新纠正”的存活集合；不会读最终 committed 集合定义预期。仅当完整匹配的取消位于相应历史位置后，才允许同一父 revision 再被纠正。无取消的重复父操作仍拒绝。原八类故障检出保留。新增派生恢复测试的额外参考输入事前冻结，采用独立标量总和和新建叶模型，未以修后值兜底。

中间失败保留：`cancellation_preflight` 为 18 failed（新取消体含 ndarray，执行摘要尚未支持）；`cancellation_diagnostic` 为 1 failed（新增测试错误地要求审计回执也绝对不变）。后者按原 `_replay_receipt` 合同改成精确检查新增一条 replay_noop 回执，同时统计、账本、动作、资格与算子实例不变；不是放宽旧测试。随后 `cancellation_parent_matrix` 18 passed、`cancellation_lineage_matrix` 126 passed，源码绑定分别保存。

未覆盖的能力：跨进程掉电恢复、默认完整联合粒子后缀重放、所有 P0/direct-P5/debt-replay 历史下都能触发此取消的非空矩阵，仍不能由本批 legacy/wrapper 取消正例推断成立。取消参考仍共享底层序列化及 CCRR/Dirichlet/RLS 叶算法；完整历史的外部保管真实性没有因此建立。
