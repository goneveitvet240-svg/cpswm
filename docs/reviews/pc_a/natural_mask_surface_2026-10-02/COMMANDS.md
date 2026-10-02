# 复现

实际冻结代码 `d2c3f51b005b49b97812f43b5dc75c3801017807`。证据封存提交包含后加的独立算术/制图脚本及文档，生产源码未变。使用当前分支交付版亦需核对包内 `frozen-sources.json`。原环境是PR94虚拟环境的符号链接，非本轮重新安装；Python/系统信息见environment.json。

## 输入与权重

在新临时目录解压 `evidence/frozen-run.tar.gz`，得到 `source/` 和 `experiment/`。先核对archive-pin与archive-files全部SHA256。`source/`只有本次实际消费的档案子集（含原public结果），不是整个模拟器原始档案。不要覆盖已有输出目录。

新权重官方地址：https://download.pytorch.org/models/maskrcnn_resnet50_fpn_v2_coco-73cbd019.pth

SHA256：`73cbd0190fcbe3ba339921fbce2c3a0b6bb9126c9a133c85e43a2a8e060a109e`

旧权重官方地址：https://download.pytorch.org/models/ssdlite320_mobilenet_v3_large_coco-a79551df.pth

SHA256：`a79551df90c79834bcd3bb3845ef9d966b5449a3a9b2833ae8404778ca5d65d2`

Torch 2.13.0、torchvision 0.28.0、CPU；模型native transform 800/1333。模型初始化不联网，外部准备权重后再传入。公开输入深度单位m，原公开相机配置/来源摘要逐帧验证。

## 实际命令

工作目录 `/private/tmp/cpswm-pc-a-natural-mask-surface-20261002`，历史输入 `/private/tmp/cpswm-continuous-target-evidence-20261002`，输出 `/private/tmp/cpswm-natural-mask-surface-evidence-20261002`。完整实际argv、时长/退出码/输出摘要见 `evidence/execution-ledger.json`。复现可替换这些绝对路径，但不得改变manifest内容/固定顺序/摘要；manifest中路径均为输入root相对路径。

```sh
CPSWM_SSDLITE_WEIGHTS=/private/tmp/cpswm-natural-candidate-evidence-20261001/ssdlite.pth .venv/bin/pytest tests/test_natural_mask_surface.py tests/test_mask_surface_comparison.py tests/test_visual_target_tracking.py tests/test_natural_vision.py tests/test_unity_rgbd.py tests/test_natural_target_sequence.py -x
.venv/bin/pytest tests/test_temporal_target_position.py::test_continuous_duplicate_pixels_and_transaction_idempotence tests/test_temporal_target_position.py::test_middle_withdrawal_failure_rolls_back_tombstone_and_replay -x
.venv/bin/mypy src/cpswm
.venv/bin/ruff check src tests tools/run_mask_surface_comparison.py
.venv/bin/ruff format --check src tests tools/run_mask_surface_comparison.py
```

推断命令（第二次输出目录换成fresh；每次单独启动进程）：

```sh
.venv/bin/python tools/run_mask_surface_comparison.py infer /private/tmp/cpswm-continuous-target-evidence-20261002 /private/tmp/cpswm-natural-mask-surface-evidence-20261002/manifests/public-manifest.json /private/tmp/cpswm-natural-mask-surface-evidence-20261002/maskrcnn.pth /private/tmp/cpswm-natural-candidate-evidence-20261001/ssdlite.pth /private/tmp/cpswm-natural-mask-surface-evidence-20261002/run --manifest-pin ff77d668619a8959acd04bf6b6a12f364c858cb336ce619919e433b40c5e9a84
.venv/bin/python tools/run_mask_surface_comparison.py evaluate /private/tmp/cpswm-continuous-target-evidence-20261002 /private/tmp/cpswm-natural-mask-surface-evidence-20261002/run /private/tmp/cpswm-natural-mask-surface-evidence-20261002/manifests/evaluation-manifest.json /private/tmp/cpswm-natural-mask-surface-evidence-20261002/run-evaluation.json --inference-pin 9e79d9763f8125abda77ba9cdb3661e8cfcc683c5756b61c34483d275231605f --manifest-pin 47b39924cc342bf58ce9772e50119a15190a9d8259f6d4651a76064d227d12e6
.venv/bin/python docs/reviews/pc_a/natural_mask_surface_2026-10-02/independent_geometry_check.py /private/tmp/cpswm-continuous-target-evidence-20261002 /private/tmp/cpswm-natural-mask-surface-evidence-20261002
```

独立脚本也可直接用解压后的source/experiment；它输出independent-geometry.json，不调用项目推理/评分代码。图由 `render_examples.py SOURCE EXPERIMENT OUTPUT.png` 生成，仅展示public预测；已人工查看三幅图，末帧丢失未画伪造mask或选点。
