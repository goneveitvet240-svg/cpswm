# 复现与版本范围

1. 检出实际诊断源码 `4798bd67059eb96f2128a957cfd81d1b1f5d509f`。冻结依赖入口为 `uv sync --frozen --extra dev --extra perception --extra hand-perception --python 3.13.5`。本轮实际复用 `/private/tmp/cpswm-pc-a-camera-checkpoint-fixture-20260930/.venv/bin/python`，没有把复用环境称为重新建立的独立环境。
2. 原始五份归档已分别封存在此前 `rgbd_camera_geometry_2026-09-30`、`owned_visual_neural_2026-09-30`、`portable_checkpoints_2026-09-30`、`ci_action_report_2026-09-30` 的 evidence 压缩包；保留其中目录的全部原件，再按 fixed-cases.json 对应历史目录运行。每个目录的逐文件清单在 case*/inputs.json，清单的摘要是外部 --input-sha256；不要为通过检查重新生成摘要或修改旧原件。本轮 archive-audit/relocated-history 另保存一份完整合法原件，用于搬移复算。
3. 固定 Faster R-CNN 权重为 `fasterrcnn_resnet50_fpn_v2_coco-dd69338a.pth`。工具使用仓库现有权重核验，不下载或重写模型，不接受新的标签输入参数。
4. POSIX 示例，替换路径，保持 pin：

```sh
PYTHONPATH=src:tests:tools .venv/bin/python tools/diagnose_surface_factors.py \
  --history /absolute/path/to/fasterrcnn-north-rgbd_self_pose \
  --output /absolute/path/to/new-diagnosis \
  --weights /absolute/path/to/fasterrcnn_resnet50_fpn_v2_coco-dd69338a.pth \
  --input-sha256 062b86a4f76c2ece70f1eba0346bd5c0c7fe851a6e516fe92579efd46a8283db
```

追加 `--verify` 会重新实际运行检测器和几何，逐字段比较 public.json、report.json 和 inputs.json；不是只查输出哈希。首次运行拒绝覆盖旧结果，输出必须位于原件之外。只有真实正路径先完成后，才应使用伪造副本检查拒绝路径。

5. `review-commands.json` 保存最终两轮顺序审查完整参数、退出码、耗时及源码 SHA；对应 JUnit 和日志均在本包。`attempt01` 保留初版局部审查和五份真实材料失败，不可与最终版本合并报告通过数。`development-real` 是修复冻结前的调试证据，正式结果为 case1–case5。
6. `case-results.json` 固定五项的运行命令及结果；`archive-audit/results.json` 保留一项跨目录正路径和三项完整伪造的真实子进程返回。三个攻击 exit 1 是预期拒绝，不是三次正常数据通过。
7. `source.json` 记录整个 src/tests/tools 的源码哈希；本轮没有更改 src 生产代码。历史 manifest 的 source 是历史内容摘要，不能当成当前代码 SHA。当前工具只重算公开图像与几何及评价对应，不重放旧语义/账本/神经动作链。
8. `run_reviews.py`、`run_fixed_cases.py`、`audit_actual_archive.py`、绘图与汇总脚本是本机运行记录，含实际绝对路径；搬移时需显式替换这些定位路径。CLI 的搬移正路径已在本机验证，Windows/Linux 的依赖与浮点结果仍需 B 独立复现，不因此宣称跨平台通过。

图像已渲染并检查。首次绘图的字体缓存警告保留，最终使用临时 MPLCONFIGDIR；不影响原始数据或公开模型输入。
