# 复现命令与真实执行身份

最终代码 `47e307d97100c7fc1f04cb64fd1a05e926355c7e`。实际工作目录 `/private/tmp/cpswm-pc-a-semantic-diagnostics-20260916`，使用上轮锁定环境的 `/private/tmp/cpswm-pc-a-real-semantic-input-20260915/.venv/bin/python`，每条Python命令均以`PYTHONPATH=src`优先导入当前源码。新的克隆可先`uv sync --frozen --extra dev --extra perception`后使用自己的`.venv/bin/python`。本批没有重新安装依赖或付费计算。

以下在源码根目录执行，输出目录必须不存在。示例变量只是把实际本机长路径集中列出，不代表新的输入：

```sh
CPSWM_DIAG_PY=/private/tmp/cpswm-pc-a-real-semantic-input-20260915/.venv/bin/python
CPSWM_DIAG_DATA=/Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/output/datasets/hocap-development-20260915
CPSWM_DIAG_WEIGHTS=/Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/output/models/torchvision/fasterrcnn_resnet50_fpn_v2_coco-dd69338a.pth

PYTHONPATH=src PYTHONPYCACHEPREFIX=/private/tmp/cpswm-stages-reproduce \
  "$CPSWM_DIAG_PY" tools/capture_hocap_detector_stages.py \
  --raw-root "$CPSWM_DIAG_DATA/raw" --manifest "$CPSWM_DIAG_DATA/raw_manifest.json" \
  --manifest-sha256 2333b3202fa8dbffb56fa931f64a8156f61ec438954d06993b1cf7bbece66107 \
  --weights "$CPSWM_DIAG_WEIGHTS" --output output/detector-stages-reproduced
```

实际首次capture在开工提交`399c7ae4d15576092f7770f3e82597063dcfb4b9`、新工具尚未提交时运行；其工具/检测器逐文件哈希与冻结版本完全相同，原始NPZ及生成清单已保留。不能用base SHA单独重建新增工具。实际清单pin为`b5cabefc482ae8bc61886b766b8c3fdfaa8568ad67537b244188ec653ea01490`；最终源码重跑的manifest含不同source_sha，必须自行固定新清单哈希，不能强塞旧pin。实际数据有持久副本：`output/datasets/hocap-detector-stages-20260916`（主项目根目录下），180个阶段NPZ逐个验证；不把这些大数组提交Git。

下述使用本批实际已固定capture；不再推断、不重新拟合校准：

```sh
PYTHONPATH=src "$CPSWM_DIAG_PY" tools/analyze_hocap_detection_failures.py \
  --raw-manifest "$CPSWM_DIAG_DATA/raw_manifest.json" \
  --raw-manifest-sha256 2333b3202fa8dbffb56fa931f64a8156f61ec438954d06993b1cf7bbece66107 \
  --annotation-manifest "$CPSWM_DIAG_DATA/annotation_manifest.json" \
  --annotation-manifest-sha256 6d0de55f82748c613b90faa978a2882c66add7a8d9220ff4e26cd4674e44d50a \
  --capture-manifest output/detector-stages/manifest.json \
  --capture-manifest-sha256 b5cabefc482ae8bc61886b766b8c3fdfaa8568ad67537b244188ec653ea01490 \
  --baseline-frames /private/tmp/cpswm-pc-a-real-semantic-input-20260915/output/hocap-faster-corrected/frames.json \
  --baseline-frames-sha256 ffb6609d01552c9beb28b129d4fb395aa43b36a276e005ca1d9d5ea60ee69d7d \
  --evaluator-root "$CPSWM_DIAG_DATA/evaluator" --output output/detection-diagnosis-reproduced

PYTHONPATH=src PYTHONPYCACHEPREFIX=/private/tmp/cpswm-natural-reproduce \
  "$CPSWM_DIAG_PY" tools/run_natural_geometry.py \
  --raw-root "$CPSWM_DIAG_DATA/raw" --raw-manifest "$CPSWM_DIAG_DATA/raw_manifest.json" \
  --raw-manifest-sha256 2333b3202fa8dbffb56fa931f64a8156f61ec438954d06993b1cf7bbece66107 \
  --frames output/detector-stages/frames.json \
  --frames-sha256 ffb6609d01552c9beb28b129d4fb395aa43b36a276e005ca1d9d5ea60ee69d7d \
  --intrinsics "$CPSWM_DIAG_DATA/calibration/intrinsics/105322251564.yaml" \
  --intrinsics-sha256 8f004a684c62c94bf21b3b2b0e103aa81e1cb7f315f2f307b2537695243509a8 \
  --output output/natural-geometry-reproduced

PYTHONPATH=src PYTHONPYCACHEPREFIX=/private/tmp/cpswm-controlled-reproduce \
  "$CPSWM_DIAG_PY" tools/run_controlled_semantic_mechanism.py \
  --output output/controlled-semantic-reproduced
```

工程验证实际运行命令：

```sh
PYTHONPATH=src "$CPSWM_DIAG_PY" -m pytest -q \
  tests/test_natural_geometry.py tests/test_detection_diagnostics.py \
  --junitxml=output/new-geometry-diagnostics-tests.xml
PYTHONPATH=src PYTHONPYCACHEPREFIX=/private/tmp/cpswm-controlled-frozen-tests-20260916 \
  "$CPSWM_DIAG_PY" -m pytest -q tests/test_controlled_semantic_mechanism.py \
  --junitxml=output/controlled-semantic-frozen-tests.xml
PYTHONPATH=src PYTHONPYCACHEPREFIX=/private/tmp/cpswm-diagnostics-tests-20260916 \
  "$CPSWM_DIAG_PY" -m pytest -q tests/test_detection_diagnostics.py \
  tests/test_hocap_development_input.py tests/test_natural_vision.py \
  tests/test_structure_two_continuous_input.py tests/test_continuous_state_recovery.py \
  tests/test_structure_two_formal_revision_lineage.py tests/test_structure_two_w3_revision_acceptance.py \
  tests/test_execution_feedback_projector.py tests/test_project_two_feedback_revision_loop.py \
  --junitxml=output/adjacent-tests.xml
PYTHONPATH=src "$CPSWM_DIAG_PY" -m mypy src
```

专项22项中有6项也在相邻回归命令内，报告不能把二者直接相加当互不重复测试数。相邻回归在核心修复后开始，期间只发生其它工具/文档整理；最终生产/测试文件与冻结版本一致。完整最终两轮整体独立对抗审核尚未进行。

数据来源沿用作者[HO-Cap项目](https://irvlutd.github.io/HOCap/)，CC BY 4.0，Wang et al., HO-Cap；完整原始文件和下载来源清单见PR26报告。标注仅用于离线诊断，绝不放入自然producer。受控probe明确是oracle，不能引用为自然人物证据。
