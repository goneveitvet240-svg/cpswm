# 固定正确指令 π0.5 完整任务开发验证

2026-10-23 开工，base `ea0d6f231ba9971d75131e9fa9fc4820ab4452cc`，分支 `codex/pc-a-pi05-full-episode-20261023`。

沿用官方 openpi `215abfb217dbac7d5f1273282331b9b1866c0479` / pi05_libero 权重，JAX CPU，table_center、init0、seed7、policy seed0。官方 spatial 最大220动作、settle10、每5步重规划，首次 evaluator success 停止。保存逐步成功标志、原始动作、策略输入/输出、视频、源码/模型绑定；成功标志仅用于评价/终止，不进模型输入。

这是一条固定正确官方指令的执行器基线，不是 CPSWM 选择目标，不启用 SAM，也不用于记忆收益/成功率估计。单episode无统计结论；官方done只证明 bowl-to-plate，不能证明 stove目标。完整H/R/I/C/Z/r/V、三RB块、七算子和E0–E6保留。独立B复核、统一验收待完成。

已有220步上限可能超过原12小时窗口；用户最新“继续”授权下完成本次运行和交付，不因窗口边界截断并冒充完整任务。
