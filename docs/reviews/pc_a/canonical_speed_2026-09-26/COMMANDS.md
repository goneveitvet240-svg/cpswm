# 复跑依据

实际受测完整源码为 **e018c432c2c6f4181b8521c4ea2eb7a700be971b**。以commands.json记录为准。

原执行：

```sh
MPLCONFIGDIR=/private/tmp/cpswm-pc-a-canonical-scoring-speed-20260926/output/matplotlib-cache .venv/bin/python docs/reviews/pc_a/canonical_speed_2026-09-26/run_frozen_speed.py --main /Users/pangwei/Documents/ai/continual-personalized-semantic-world-model --output /private/tmp/cpswm-pc-a-canonical-scoring-speed-20260926/output/canonical-speed/final-01
```

runner包含本次16:40 UTC固定截止，未来复核应在自己的授权预算中运行evidence/commands.json中的原测试及比较命令，不修改生产代码来伪造旧时点执行。锁文件/依赖与前三轮相同。源码前后逐文件摘要906份可核对Git blob；reference_reproducibility.py逐字绑定60453f2的原文件，pin见测试及COVERAGE。

真实输入固定为前轮手物前端，pin677505fa2891aab0b2602a5ec002ea3fb3612d5e219ad788437b5b03feaf3c48。三个执行检查点仍是原微型夹具训练权重。完整target/trace工件在主仓本轮备份real-equality子目录；Git只存较小摘要和日志。
