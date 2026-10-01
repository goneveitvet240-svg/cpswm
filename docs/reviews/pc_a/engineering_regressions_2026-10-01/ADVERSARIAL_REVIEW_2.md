# 第二轮修复审查

在第一轮结束后开始，绑定相同源码 8f7edafd51cdf735ca9c65a7c8e4ac367cebdc68；1021 Python 文件摘要仍不变。实现者顺序自审，非独立 B，非全仓 CI。

review2.log / review2.json：120 passed，146.50 秒。包含 prepared boundary、原生粒子、Native log-weight continuation、完整 raw 因子校验。

- 旧的两项 unresolved_underflow 拒绝要求改为明确合法正路径：独立 Decimal 参考、有限原始 log 支持、显示概率为零、重复幂等、序列化恢复、中性继续、账本不变。
- 正负溢出与 NaN/Infinity 仍明确拒绝、完整原子回滚并允许合法重试；没有通过 epsilon 或裁剪抬高零概率。
- 既有真实 producer/SQLite 测试继续覆盖显示零但原始有限支持的后续更新、撤回、恢复；完整 raw likelihood/aggregate/transition 伪造、父链及模型身份检查仍运行。有限 log 准备边界单测本身只做 StateCodec 恢复，不冒称 SQLite 验收。
- review2-foreign：父进程从仓库外目录启动，继承 PYTHONPATH 首项放置会抛出错误的测试模块；两项子进程测试均通过（11.71 秒 pytest / 12.42 秒进程）。子进程使用从 __file__ 确定的绝对 src/tests/tools，未依赖父进程 cwd 或污染路径。包含真实 SQLite 新进程恢复和 torch 不可用时 legacy/none 路径。
- 最终 Ruff src/tests、791 文件格式检查和389文件 mypy 均通过；源码/配置/收集数量不降低。

本轮范围通过，没有新功能修改。两轮测试包含重叠节点，不能把 283+120+2 报成405个独立测试。不能将这四项原CI失败的局部修复推断为最新CI已经只剩27项；最新CI须实际执行后单列。其余27个已观测失败和超时未覆盖范围仍开放。
