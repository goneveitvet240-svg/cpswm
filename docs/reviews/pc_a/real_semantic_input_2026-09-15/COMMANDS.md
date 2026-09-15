# 本批复现入口

实际运行目录 `/private/tmp/cpswm-pc-a-real-semantic-input-20260915`，实际源码 `521d4f17c8538116b30a7c3c3c6c5e5a8f894141`。下述为从该源码根目录复现的命令；每个 output 目录须不存在，禁止覆盖旧证据。

```sh
uv sync --frozen --extra dev --extra perception
.venv/bin/python tools/fetch_hocap_development_subset.py --output output/hocap-recreated --cache output/hocap-range-cache
.venv/bin/python tools/prepare_hocap_development_archive.py --raw-root output/hocap-recreated/raw --manifest output/hocap-recreated/raw_manifest.json --manifest-sha256 2333b3202fa8dbffb56fa931f64a8156f61ec438954d06993b1cf7bbece66107 --output output/hocap-method-recreated
```

准备命令会输出 receipt SHA256；在同一源码下转换得到的 receipt 以实际输出为准。首次转换在 `9fe996a7f785edc9ff36182fd993f6b81eec71d8` 执行，实际原始归档 pin 是 `b109edd49a465ad1a65bab54539f8d8b50ae400bea83a8c10bc5eb5e887e0b03`。之后模型变化没有改变转换器；最终两个模型都消费这一完全相同归档。重新转换会在 receipt.source_sha 记录新的源码，因此不要强行复用旧 receipt hash。

模型权重的官方 URL／完整 SHA 见 REPORT 和源文件常量。不得以任意同名文件替代。当前本机持久副本在 `/Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/output/models/torchvision/`，其 manifest.json 记录完整哈希。实际运行命令为：

```sh
PYTHONPYCACHEPREFIX=/private/tmp/cpswm-hocap-corrected-runtime .venv/bin/python tools/run_natural_vision_archive.py --archive output/hocap-method-input --manifest-sha256 b109edd49a465ad1a65bab54539f8d8b50ae400bea83a8c10bc5eb5e887e0b03 --weights /private/tmp/cpswm-natural-vision-models/ssdlite320_mobilenet_v3_large_coco-a79551df.pth --detector ssdlite --output output/hocap-ssdlite-corrected
PYTHONPYCACHEPREFIX=/private/tmp/cpswm-hocap-corrected-runtime .venv/bin/python tools/run_natural_vision_archive.py --archive output/hocap-method-input --manifest-sha256 b109edd49a465ad1a65bab54539f8d8b50ae400bea83a8c10bc5eb5e887e0b03 --weights /private/tmp/cpswm-natural-vision-models/fasterrcnn_resnet50_fpn_v2_coco-dd69338a.pth --detector fasterrcnn --output output/hocap-faster-corrected
```

两个运行依次执行；每个模型使用两条 CPU 线程。`inference_seconds` 仅计连续推断循环，包含入站／候选关联等开销，不含下载、环境安装、模型构造与完整生命周期成本。期间允许轻量日志／证据整理，不是受控性能基准。不得据此比较结构二方法收益。

预测完成后，评价命令仅读取已固定预测文件与独立作者标签。将 `FRAMES_SHA` 替换为该运行 summary.json 中的 frames_sha256，不能绕过 pin；选择对应预测／输出目录。

```sh
.venv/bin/python tools/evaluate_hocap_candidates.py --raw-manifest output/hocap-recreated/raw_manifest.json --raw-manifest-sha256 2333b3202fa8dbffb56fa931f64a8156f61ec438954d06993b1cf7bbece66107 --annotation-manifest output/hocap-recreated/annotation_manifest.json --annotation-manifest-sha256 6d0de55f82748c613b90faa978a2882c66add7a8d9220ff4e26cd4674e44d50a --frames output/hocap-faster-corrected/frames.json --frames-sha256 FRAMES_SHA --evaluator-root output/hocap-recreated/evaluator --output output/hocap-faster-eval-recreated
```

工程检查：

```sh
PYTHONPYCACHEPREFIX=/private/tmp/cpswm-hocap-corrected-tests .venv/bin/python -m pytest -q tests/test_hocap_development_input.py tests/test_natural_vision.py tests/test_interaction_evidence.py tests/test_structure_two_continuous_input.py tests/test_continuous_state_recovery.py tests/test_pose_observation_model.py tests/test_joint_camera_policy.py
.venv/bin/mypy src
```

`evidence/corrected_source_before.json`／`corrected_source_after.json` 是实际生产、工具、测试、pyproject 与 lock 的固定清单；`corrected_*.log/json/xml` 绑定最终源码。旧 `baseline_*`、`final_*` 和 `version32_*` 保留初始失败／中间版本，不升级为最终证据。完整整体两轮独立对抗审核尚未启动。
