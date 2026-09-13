# 开发阶段补充记录

完整正式日志以 commands.jsonl 为索引。两个较早、尚未接入逐字日志包装器的测试命令另存其真实工具返回，文件为 exploratory_test_tool_outputs.jsonl.gz；其中第二项输出被工具按长度截断，不能冒充完整终端输出。

1. `.venv/bin/pytest -o addopts= -q --confcutdir=. tests/test_structure_two_evidence_supplement.py`：exit 1，52 passed / 1 failed，44.04 秒。失败是测试 BOOT 改为真实入口后遗漏本地变量 boot，导致完成守卫未真正调用；已补回变量，保留原断言，后续整组测试重新验证。
2. `.venv/bin/pytest -o addopts= -q --confcutdir=. tests/test_structure_two_entry_portability.py -k 'old_or_foreign'`：exit 1，2 passed / 4 failed / 20 deselected，11.04 秒。两种参数各在普通/spawn 情形失败：同时间戳攻击未在编译前恢复 mtime；foreign_filename 仅换了编译文件名而代码完全相同，不能据此声称执行错误实现。已改为真实不同嵌套代码并固定编译前后的大小与时间戳，没有放宽拒绝断言。

同一开发阶段的完整 75 passed / 4 failed 日志保留在 entry_history_regressions.stdout.log.gz。随后修正后的 35 项入口正负回归全部通过，完整重放回归和原 79 项另行整组运行，不能将这些有重叠的统计相加。
