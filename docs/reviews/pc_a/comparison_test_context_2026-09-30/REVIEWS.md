# 两轮顺序对抗审查

实际源码 fa4dc032c9ef843d8ec0975810c010cd1c5ca7d6；原件 attempt01/commands.json、source.json、各阶段 pytest.log / pytest.xml / result.json。每阶段源码和 HEAD 稳定。

1. 第一轮 14/14，零跳过：真实非空 CORRECT 不准入→拒绝→事务回滚；RETRACT 真执行；正式修订谱系合法与攻击；coverage 占用父 tracer 的真实子进程正路径，以及生产拒绝已有 tracer。185.62 秒。
2. 第二轮 2/2，零跳过，hash seed 123：先保存新生成的当前 D0 合法包，再两个完整 CLI 各自 fresh replay。合法包两次接受；动态伪造 nonempty_commit/action_consequence/corrected_memory/contract_freeze 四项拒绝；公平性伪造 future_support/missing_owner/costs/selection_access/consumer_features/fairness_claim 六项拒绝。每个攻击均重算相应摘要和归因，伪造原件保存在 round2-originals。1881.01 秒。

矩阵 dynamic-matrix/matrix.json、fairness-matrix/fairness_forgery_matrix.json 记录每项真实拒绝位置。第一轮结束后才启动第二轮，两轮结束后才同步父文档。2 个测试函数包含 2 条正路径和 10 个攻击输入，不把它们误报为 12 项 pytest 测试。此为本轮限定范围 A 自审，不是 B 独立、Windows、全仓或科学统一验收。
