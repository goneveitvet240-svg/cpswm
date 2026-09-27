# 冻结执行入口

在独立工作目录从锁文件重建：`uv sync --frozen --extra dev --extra perception --extra hand-perception`。

```sh
MPLCONFIGDIR=/path/to/worktree/output/matplotlib-cache .venv/bin/python -u docs/reviews/pc_a/visor_pixel_supervision_2026-09-27/run_frozen.py --main /path/to/source-storage --output /path/to/new-output
```

source-storage须含上一轮`output/visor-contact-supervision-20260927/closed/raw`和`closed/final-02/packet`，以及原`output/models/torchvision/fasterrcnn_resnet50_fpn_v2_coco-dd69338a.pth`。原作者字节及完整模型摘要通过源码固定根验证，不以新包自签清单代替来源。

执行器在每条命令前后核对跟踪Python与Git blob。顺序两审、mypy、Ruff后，构建完整485帧两轴监督；新进程从头重建比对；运行固定16帧学习探针；再由第三进程从作者源和原骨干重新提取特征、重新执行16步训练及恢复检查，比较report/head完整字节。

探针固定前8帧训练两遍、后8帧仅记录相邻数据的损失；选择依据只是原帧顺序，按源编译包的完整索引保留，无难帧过滤。SGD无momentum、lr0.01、零初始化两通道1×1读出，Torch CPU两线程并启用deterministic algorithms；现有FasterRCNN的图像变换和FPN0保持原样。每次正式训练计划16次，另对训练后原件/恢复件分别做1次下一更新检查，共2次隔离验证更新；保存的checkpoint仍为正式16步处。重放是另一次执行，不称为多次独立试验。

完整argv/UTC/耗时/退出码与源码SHA在evidence/final-01/commands.json；每个epoch/ordinal的有效像素、梯度范数、更新前后参数指纹、全像素输出指纹及源包绑定在实际probe/report.json。训练损失下降只说明局部优化信号，不能当作检测/接触能力提升或独立泛化。
