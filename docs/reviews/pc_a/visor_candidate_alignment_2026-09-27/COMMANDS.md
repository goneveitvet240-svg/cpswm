# 复跑入口

使用本分支独立工作目录和uv.lock：`uv sync --frozen --extra dev --extra perception --extra hand-perception`。

```sh
MPLCONFIGDIR=/path/to/worktree/output/matplotlib-cache .venv/bin/python -u docs/reviews/pc_a/visor_candidate_alignment_2026-09-27/run_frozen.py --main /path/to/source-storage --output /path/to/new-output
```

source-storage下须保留上一轮`output/visor-contact-supervision-20260927/closed/raw`和`closed/final-02/packet`，以及`output/models/torchvision/fasterrcnn_resnet50_fpn_v2_coco-dd69338a.pth`、`output/models/mediapipe/hand_landmarker-1.task`。模型完整摘要在源码PROFILE及生产检测器中校验，不联网下载。重跑输出必须不存在。

先校验所有跟踪src/tests/tools/A审查Python与Git一致；每条命令前后重查。顺序执行第一审、第二审、mypy、Ruff、官方冻结源重建比对；单独进程只把RGB子树交给前端，然后把执行预测摘要固定在execution-pin.json，再由另一进程重建作者标注和所有几何。最后第三进程通过verify_alignment实际回读，完整比对源重算结果。

Torch CPU两线程；MediaPipe CPU delegate仍依赖macOS原生图形服务，本机按既有授权在沙箱外运行。没有改变检测阈值、自动选择候选对应或开展训练。模型/库版本和实际导入UTC写在predictions.json；该导入时间不是曝光时间，所有帧无archive timeline。

完整argv、UTC、秒数、退出码、受测SHA及Python摘要见evidence/final-01与final-02。新SHA需重审，不继承旧审查。

最终修正评估使用同一执行器加`--reuse-prediction output/visor-alignment/final-01/predictions.json`。只允许源码内冻结摘要对应的那份485帧预测，并自动比较推理依赖AST及Git生产差异；预测生产于98c64b1，最终评估与两审于860bc46。final-02的reuse-bound-prediction不是模型推理耗时；若不加此参数，执行器会按最终代码重新完整推理。
