# 执行及独立复核入口

实际受测7549f1eaaf16a50bc5ab8be30877f504883b3a65。锁文件及依赖沿用前三、四轮：`uv sync --frozen --extra dev --extra perception --extra hand-perception`。

```sh
MPLCONFIGDIR=/private/tmp/cpswm-pc-a-sharded-hand-matrix-20260926/output/matplotlib-cache .venv/bin/python docs/reviews/pc_a/sharded_hand_matrix_2026-09-26/run_frozen_shards.py --main /Users/pangwei/Documents/ai/continual-personalized-semantic-world-model --output /private/tmp/cpswm-pc-a-sharded-hand-matrix-20260926/output/sharded-hand-matrix/final-01
```

先顺序首审、第二审、mypy和Ruff，再使用ThreadPoolExecutor最多8个独立子进程执行24分片。execution-plan.json列出全部固定窗口归属及候选规模估算，commands.json保存每条实际argv、时刻、耗时、退出码；queued分片若到截止尚未开始，保留failure而不伪造运行回执。完成覆盖核对后才写最终summary和complete=true。

所有模型命令共有 `--prefix-frames 4 --window-scope all --restore-scope first --shard-count 8`，片号0至7。前端pin为677505fa2891aab0b2602a5ec002ea3fb3612d5e219ad788437b5b03feaf3c48，输入主仓output/hand-proposal-input-20260926/closed/final-01/frontend，原权重执行件在同级derived。来源文件与作者评价标签不进入模型特征。

执行器含本次UTC2026-09-26 16:40固定截止。未来复核应按本次回执在自己的授权预算中运行相同模型命令，不修改生产代码来重演旧时点，也不将不同源码结果拼接。各片summary中的available frontend coverage是同一可用集合，不能逐片相加成重复帧数。

全部完整评分与恢复工件将保存在主仓本轮逐文件校验备份，Git保存小型结果摘要、命令、审查日志及源码摘要。旧17/96属于PR49原版本，前三轮范围见对应报告。

## 最终回执

第五轮固定矩阵实际完成 **46/96** 个评分/消融组合和 **10/24** 个首窗恢复组合，9/24 分片完整完成。19/32 个窗口至少一种网络完成，13/32 窗口三网络均完成；已完成组合涉及 76/128 唯一原帧。

四项审核/静态命令退出 0；分片 9 项退出 0，8 项到时退出 124，7 项未启动。总执行器因未完成返回非零；原始回执见 evidence/commands.json，完整备份见 REPORT.md。工件回读配方为 evidence/artifact_readback_recipe.py.txt，仅后处理，不运行模型。将其另存为工作树外的 .py，用同版本环境传入 --root、--frontend、--evaluator、--output；具体固定输入及原始命令均在证据中。
