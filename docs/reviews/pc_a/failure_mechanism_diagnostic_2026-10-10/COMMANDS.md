# 复现命令

从本分支仓库根运行，Python3.13环境 `/private/tmp/cpswm-object-reid-venv/bin/python`。依赖版本见 `evidence/environment.json`。稀疏checkout须包含 `src tests tools apps configs docs/collaboration`、本报告、matched_transition_death_test_2026-10-09和object_memory_integration_2026-10-10的完整证据。所有输出目录必须新建，不覆盖已封存结果。

```sh
export PYTHONPATH=src:tools:tests
TASK_PYTHON=/private/tmp/cpswm-object-reid-venv/bin/python
TASK_PANEL=docs/reviews/pc_a/matched_transition_death_test_2026-10-09
TASK_DOC=docs/reviews/pc_a/failure_mechanism_diagnostic_2026-10-10
"$TASK_PYTHON" tools/diagnose_surface_failures.py \
  --root "$TASK_PANEL/evidence/natural-30-5-5" \
  --manifest "$TASK_PANEL/evidence/manifest.json" --targets "$TASK_PANEL/TARGETS.json" \
  --archive docs/reviews/pc_a/object_memory_integration_2026-10-10/evidence/dev \
  --output /private/tmp/paired-geometry-new
```

该工具只在当前前端重新算序列，CG/hybrid用已散列绑定的原输出；没有重新运行检测或4GB模型。GT评分与敏感性在evaluator-only工具中，生产序列不读取SDK标注。

```sh
"$TASK_PYTHON" tools/run_correction_replay_comparison.py \
  --output /private/tmp/paired-core-new-different-7 --seed 7 \
  --ciav-outcome detected_different_location
"$TASK_PYTHON" tools/run_correction_replay_comparison.py \
  --output /private/tmp/paired-core-new-same-7 --seed 7 \
  --ciav-outcome detected_same_location
```

每种设置分别运行7、8、9。same组预期写出 `comparison.json` 的 `NO_LEGAL_CORRECTION_TARGET` 后以非零退出；这是保留的实验失败，不得当成纠正通过，也不得换目标消除该失败。different组产出在线、恢复、全重放、整步删去反事实四个SQLite；最后一个不是相同输入的算法参考。

```sh
"$TASK_PYTHON" tools/score_correction_mechanisms.py \
  /private/tmp/paired-core-new-different-7/comparison.json \
  /private/tmp/paired-core-new-different-8/comparison.json \
  /private/tmp/paired-core-new-different-9/comparison.json \
  --output /private/tmp/paired-different-score-new.json
```

same组同理评分。`diagnose_core_readout.py` 的reference目录名绑定本轮六个case；用封存包可恢复相同命名的参考结果，或仅复制六份comparison到 `/private/tmp/cpswm-paired-v3-{detected_same_location|detected_different_location}-{7|8|9}-20261010/comparison.json`。只读比较会新运行生产序列，核验其默认分布与参考逐步一致。

```sh
"$TASK_PYTHON" tools/diagnose_core_readout.py \
  --output /private/tmp/paired-readout-new --reference-root /private/tmp
```

几何外部控制使用PR63原件 `attempt01/geometry`。可从该版本证据 `docs/reviews/pc_a/rgbd_camera_geometry_2026-09-30/evidence/rgbd-camera-geometry.tar.gz` 还原；脚本按git中的inventory逐文件核验，不接受任意同名目录。

```sh
"$TASK_PYTHON" "$TASK_DOC/verify_geometry_controls.py" \
  --panel "$TASK_PANEL/evidence" \
  --raycast-root /Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/output/rgbd-camera-geometry-20260930/attempt01/geometry \
  --output /private/tmp/paired-geometry-controls-new.json
"$TASK_PYTHON" "$TASK_DOC/verify_evidence.py" "$TASK_DOC/evidence"
```

最后一个命令直接核验压缩包每个原件并重新算读出选择、正确数、普通计数和失败分类，无需提取SQLite。完整state仍含同机runtime边界，本轮不声称Windows路径可直接使用。

```sh
"$TASK_PYTHON" -m pytest -o addopts='' -q \
  tests/test_paired_failure_diagnostics.py tests/test_unity_rgbd.py \
  tests/test_matched_transition_death_test.py tests/test_project_two_feedback_revision_loop.py \
  tests/test_ccrr_context_conditioned_regime.py tests/test_history_reconstruction.py \
  tests/test_structure_two_continuous_input.py tests/test_project_two_action_readout.py \
  tests/test_structure_two_p5_readout_posthoc_diagnostic.py::test_corrected_readout_is_the_previously_selected_v0_6_configuration
```

实际165 passed，132.24秒。未跑全仓；组件测试不计科学收益。运行失败与观测后追加对照见PLAN及封存日志。最终源码209b688只新增比较器当前人物权重的普通计数读出，生产src未改。
