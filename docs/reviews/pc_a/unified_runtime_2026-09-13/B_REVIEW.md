# B 五项修复的 Mac 独立复核

受测完整 SHA：`c366cad0a92593bb2c4c44db7e8d3408a2b5cc9c`，独立 detached 工作目录 `/private/tmp/cpswm-pc-a-unified-b-review-20260913`。

源码审核范围：R7 基线到该提交的 `prototype_spine.py`、`structure_two_particle_workspace.py`、`structure_two_semantic_identity.py` 及关联新增测试。确认建设时地点支持、跨代证据簇谱系、输入/统计/投影闭包、读出重新验证与 import-time 方法锚点；没有把输入哈希自行等同于外部真实性。

本机实际结果：

- 五边界/锁保护/执行接口范围：139 passed，退出 0，12.97 秒。
- 原 R7 相同 38 文件 exact-812：812 passed / 0 failed / 0 skipped，10 条既有坏枚举/模型构造警告，退出 0，446.76 秒。
- 两轮源文件前后摘要一致；完整命令、JUnit 与输出保留于 `b_review_01`、`b_full_01`。
- 环境为本机 CPython 3.13.5、明确 `PYTHONPATH` 指向受测新工作树；这是 Mac 独立工程复核，不是 Windows 失败关闭，也未运行 W1 的正式全流程执行认证。

接收结论：可将 B 固定提交纳入 A 的候选集成树，随后在最终候选树重跑；不直接合并共享分支、不签完整默认联合主干/科学收益。B 的 Windows CRLF/LF 身份差异与 full -n4 1 秒锁 deadline 失败保留为平台阻塞，未放宽阈值、删测试或篡改旧结果。
