# 复跑入口与证据分层

冻结源码：`60453f212c7a9435b272cbd4aece3cf8db4be4a8`。base：`6b9f260530d53ac9c1a58ca35cb881ed86a48cf7`。独立工作目录：`/private/tmp/cpswm-pc-a-full-hand-proposal-matrix-20260926`。

环境沿用锁文件及CPU依赖：`uv sync --frozen --extra dev --extra perception --extra hand-perception`。没有重新训练或下载模型。

本次完整执行命令：

```sh
MPLCONFIGDIR=/private/tmp/cpswm-pc-a-full-hand-proposal-matrix-20260926/output/matplotlib-cache .venv/bin/python docs/reviews/pc_a/full_hand_proposal_matrix_2026-09-26/run_frozen_matrix.py --main /Users/pangwei/Documents/ai/continual-personalized-semantic-world-model --output /private/tmp/cpswm-pc-a-full-hand-proposal-matrix-20260926/output/full-hand-matrix/final-03
```

执行器先逐字核对Git中的全部受测Python，再依次首审、第二审、mypy、Ruff；通过后才并行三个独立实验进程。每个命令前后复核摘要；每个进程独立写日志与模型子目录，收据写入由互斥锁保护。并行进程都到终态后输出最终源码摘要和matrix-status，任一失败不会把其余进程遗漏为成功。

执行器含本次授权的固定UTC 2026-09-26 16:40截止，过期后不能直接用它启动新计算。独立复核应先核对本次命令收据，再在自身授权预算中执行收据内的相同测试/模型命令；不应为复跑修改受测生产代码。三个模型命令共同使用 `--prefix-frames 4 --window-scope all --restore-scope first`，实际全部argv保存在commands.json。

输入依赖：

- 主仓 `output/hand-proposal-input-20260926/closed/final-01/frontend`，外部结果pin `677505fa2891aab0b2602a5ec002ea3fb3612d5e219ad788437b5b03feaf3c48`。
- 同级 `derived` 保存原微型夹具训练权重的执行配置派生件；每臂实际清单pin记录在结果中，不可替换为新训练件。
- 原帧在 `output/person-ambiguity-20260926/closed/final-02/aligned/runtime`，pin `77f02b3dbf093243033f232ce4721d54f1ca35189b1a963d6552b92dd199279f`；原337试次归档重建在第一轮已执行。
- 评价侧阶段统计单独保存于 `evidence/EVALUATOR_COVERAGE.json`，从独立评价文件读取，没有进入上述模型进程。

保留所有尝试：final-01为串行原版本的主动中断；final-02为格式化后未冻结启动被拒绝、没有有效实验；final-03为最终冻结版本。不能拼接不同版本补足完成率。只读性能分析另存profile-01，插桩耗时不是模型公平速度基准，也不计入96组合。
