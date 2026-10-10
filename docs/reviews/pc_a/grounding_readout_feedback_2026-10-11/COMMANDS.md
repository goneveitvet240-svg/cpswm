# 复现与证据

工作树 `/private/tmp/cpswm-pc-a-grounding-readout-feedback-20261011`，生产/实验源码 `4419ab5bb095cf821b6f04241a95e838ac3bb608`。所有命令在该工作树执行。主环境版本见 `evidence/environment.json`；SDK 单独使用仓库原有 `.venv-ai2thor`。模型必须为源码声明的固定 SHA256，不重新下载/换模型。

## 代码检查

```sh
PYTHONPATH=src:tools:tests OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 \
/private/tmp/cpswm-object-reid-venv/bin/python -m pytest -o addopts= -q \
 tests/test_natural_mask_surface.py tests/test_mask_surface_comparison.py \
 tests/test_structure_two_adaptive_runtime.py \
 tests/test_structure_two_adaptive_runtime_adversarial_round1.py \
 tests/test_structure_two_adaptive_runtime_adversarial_round2.py \
 tests/test_grounding_readout_feedback_repair.py tests/test_structure_two_ciav.py \
 tests/test_structure_two_ciav_negative_observation_layers.py \
 tests/test_structure_two_continuous_input.py tests/test_continuous_state_recovery.py \
 tests/test_project_two_action_readout.py tests/test_surface_episode.py
```

历史扩展组在补充参考点检查前 153 passed / 1 skipped；最后新增一个参考点正负检查，并跑42项受影响检查及23项输出检查。不要把这三组重叠测试相加。跳过项是显式两个 pinned checkpoints 未提供，未伪造为通过。

## 实际 Unity 干预

```sh
/Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/.venv-ai2thor/bin/python \
 tools/unity_depth_counterfactual_capture.py \
 --output /private/tmp/cpswm-live-depth-counterfactual-matched-20261011 \
 --binary /Users/pangwei/.ai2thor/releases/thor-OSXIntel64-f0825767cd50d69f666c7f282e54abfe58f1e917/thor-OSXIntel64-f0825767cd50d69f666c7f282e54abfe58f1e917.app/Contents/MacOS/AI2-THOR \
 --house /Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/output/rgbd-camera-geometry-20260930/probe_house.json

PYTHONPATH=src:tools:tests OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 \
/private/tmp/cpswm-object-reid-venv/bin/python tools/evaluate_live_depth_counterfactual.py \
 --directory /private/tmp/cpswm-live-depth-counterfactual-matched-20261011 \
 --output /private/tmp/cpswm-live-depth-counterfactual-final-eval-20261011 \
 --weights /private/tmp/cpswm-matched-transition-assets-20261009/maskrcnn.pth
```

输出目录必须不存在；重跑时换新目录。新 Unity 采集需正常主机执行权限，沙箱内本机 SDK 导入曾被阻塞，导入诊断不改变任何 SDK 文件。`live-matched-raw.tar.gz` 包含实际使用的 `scene.json`、四帧原始观测和 evaluator-only 数据；没有本地房屋输入时可以从这里复原确切初始场景。第一次默认朝向错误的采集单独保留，不参与有效比较。

## 长期比较

```sh
PYTHONPATH=src:tools:tests OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 \
/private/tmp/cpswm-object-reid-venv/bin/python tools/run_long_horizon_repair_comparison.py \
 --output /private/tmp/cpswm-long32-repair-20261011 --seeds 7 8 9

PYTHONPATH=src:tools:tests \
/private/tmp/cpswm-object-reid-venv/bin/python tools/summarize_grounding_repair.py \
 --directory /private/tmp/cpswm-long32-repair-20261011 \
 --output /private/tmp/cpswm-long32-summary-20261011.json
```

旧的偏人物夹具是显式负控制；不能用于自然人物效果主张。相同语义观测、同观察后决策时机、同先验计数1.0，普通全历史/半衰期1/3/7天全列。三份 `long32-seed-*-raw.tar.gz` 含所有逐步JSON及36份原始/恢复数据库；将其 `long32/` 内容解至新目录并复制 `long32-comparison.json` 为 `comparison.json`，即可先重算摘要。

长期运行精确源码见 `long32-executed-source.tar.gz`（411文件），配合 base `fbe6277d545f98ac570f0ea44513a9b1ea2fbdd4` 可还原。源码清单中两个文件与最终提交不同：补充的纯视觉参考点检查，以及工具收集源码列表的等价语法。所有生产核心、读出、人物/场景文件完全相同。完整差异由 `source-compatibility.json` 显式列出。长期循环中没有修改源文件，末尾自动验证 source_unchanged。

## 封存完整性

`files.json` 对本目录每项证据绑定大小与SHA256；`archive-members.json` 对各tar.gz中的每个普通文件额外绑定未压缩大小与SHA256。先验证压缩包SHA，再检查未压缩成员，之后运行摘要器。数据库只是本次本地实验产物，不能复制覆盖另一台电脑工作树或环境。

本地验算脚本：`python3 docs/reviews/pc_a/grounding_readout_feedback_2026-10-11/evidence/verify_evidence.py`（默认只读核验已封存的SHA和算术；仅首次封存使用`--write-index`，不能用重写清单掩盖失败；不替代独立审查）。

可读结果 `REPORT.md` 对实际完成和未完成分开列示。没有完整全仓、完整S1、B独立验收或跨机器集成通过回执。
