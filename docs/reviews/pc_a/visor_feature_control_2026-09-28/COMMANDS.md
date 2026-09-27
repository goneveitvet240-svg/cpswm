# 复现命令与环境

从本轮实际受测SHA建立独立工作树，使用Python3.13.5与仓库uv.lock，`uv sync --frozen --extra dev --extra perception --extra hand-perception --offline`（需已有依赖缓存）。没有修改依赖锁或正式比较模块。

实际命令入口：

```sh
.venv/bin/python -u docs/reviews/pc_a/visor_feature_control_2026-09-28/run_frozen.py --main /Users/pangwei/Documents/ai/continual-personalized-semantic-world-model --output output/visor-control/final-04
```

执行器按顺序运行第一审、第二审、mypy、Ruff、完整真实对照和新进程完整重放；每条前后核对所有跟踪Python与该Git源码，并保存参数、起止、退出码。完整argv见evidence/final-04/commands.json；旧失败见final-01～03。

输入包括既有P01_01原始五源/完整接触包/485帧像素包、新P01_03五源、既有官方FasterRCNN权重。通过所有源摘要后重新构造目标；不是接受任意外来缓存或标签清单。Windows须重建环境并修改本机路径，字节级重现结果尚未跨平台验证。

训练预算为每臂128次优化调用，中间保存第16步，合计256次；四个快照各自以原件副本/恢复件做一次下一更新检查，共另8次，均不修改交付快照。循环错配只用于诊断；没有用任何诊断标签选预算/拟合/回调学习率。第二个预算并非看到本轮结果后追加。
