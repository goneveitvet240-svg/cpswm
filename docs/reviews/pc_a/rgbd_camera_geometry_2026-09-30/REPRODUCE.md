# 复现与源码边界

封存包 `evidence/rgbd-camera-geometry.tar.gz` 的逐文件 SHA256 在 inventory.json，整体身份在 archive.json，所有文件已读回核验。本机原件在 `/Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/output/rgbd-camera-geometry-20260930`。

1. 恢复/重跑两条真实历史必须 checkout 方法源码 `dacc6c6cf070225fbc5b13ce351f1487636f6ec8`。本机保留 `/private/tmp/cpswm-rgbd-frozen-dacc6c6` 精确工作树。`attempt01/commands.json` 保留解释器、权重、checkpoint、worker、场景、配置和全部命令；`attempt01/source.json` 记录全部 Python/依赖文件。不要在修改后的源码上绕过 source 检查。
2. 核验几何固定轨迹时使用修复源码 `2ff55ee5b69f27b963d389c5ecccd0044f2d7373` 的 `tools/verify_rgbd_geometry.py --directory <解包位置>/attempt01/geometry --verify`。修复只增校验，54 点结果仍逐项等于原件；旧版接受伪造动作的缺口保留并已修复。两轮命令见 `repair-reviews/commands.json`。
3. Python 环境使用现有 `.venv`，设置 `PYTHONPATH=src:tests:tools`。真实检测器需要 `CPSWM_SSDLITE_WEIGHTS` 与 `CPSWM_FASTERRCNN_WEIGHTS` 指向官方固定权重；本轮实际没有跳过可选测试。官方 SDK/Unity 身份见 runtime-before/after 与 runtime-verification.json。
4. `run_frozen.py` 是本机原始编排记录，包含绝对工作树路径，不是已经完成的可移植安装器。旧神经 evidence 的 checkpoint_directory 仍为原机绝对路径，Windows/B 重建及显式可信路径解析尚需后续修复；不能把解包一致冒称跨机独立复现。
5. 所有 oracle 实例掩膜、物体 metadata、射线结果只在评价阶段读取。`surface_membership.py` 输出的是像素掩膜归属，不是自然身份监督或三维中心标签。`ray-direction-diagnostic.json` 是残差分解，不能据此拟合真实传感器噪声。

原分类配置、纯 RGB 和完整统一框架保持。此次实际两条主历史均使用此前用户批准的主动澄清开发目标；未新增正式效用/似然/评价指标。
