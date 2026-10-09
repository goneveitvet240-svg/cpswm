# 匹配过渡死亡测试复现命令

以下示例以仓库根目录为 `$REPO`，证据目录为 `$EVIDENCE`。捕获需要已安装 AI2-THOR 的 Python 3.11、固定 Unity binary、开发 house 和固定 Mask R-CNN 权重；重放只需要项目运行环境。

```bash
PYTHONPATH=src "$ML_PYTHON" tools/capture_surface_development.py \
  --output "$EVIDENCE/natural-30-5-5" \
  --mask-weights "$MASKRCNN_WEIGHTS" \
  --sdk-python "$AI2THOR_PYTHON" \
  --binary "$UNITY_BINARY" \
  --house "$HOUSE_JSON" \
  --degrees 30 5 5 \
  --target bottle:0 bottle:1 bowl:0

PYTHONPATH=src:tools "$ML_PYTHON" tools/run_matched_transition_death_test.py \
  prepare "$EVIDENCE/natural-30-5-5" "$EVIDENCE/manifest.json"
```

在源码分别处于旧版和候选精确 SHA 的独立工作树执行：

```bash
PYTHONPATH=src:tools "$ML_PYTHON" "$DRIVER" replay \
  "$EVIDENCE/natural-30-5-5" "$EVIDENCE/manifest.json" \
  "$EVIDENCE/baseline-a.json" --arm baseline \
  --expected-sha 6e9c953a81e2fc072f4d079d7a19194b1324ea64

PYTHONPATH=src:tools "$ML_PYTHON" "$DRIVER" replay \
  "$EVIDENCE/natural-30-5-5" "$EVIDENCE/manifest.json" \
  "$EVIDENCE/candidate-a.json" --arm candidate \
  --expected-sha a5385ddaf6724d2d346fc222866edc2b7ec9407c
```

两臂各重复一次为 `baseline-b.json`、`candidate-b.json`，然后在当前交付树评分和汇总：

```bash
PYTHONPATH=src:tools "$ML_PYTHON" tools/run_matched_transition_death_test.py evaluate \
  "$EVIDENCE/natural-30-5-5" "$EVIDENCE/manifest.json" \
  "$EVIDENCE/baseline-a.json" \
  docs/reviews/pc_a/matched_transition_death_test_2026-10-09/TARGETS.json \
  "$EVIDENCE/baseline-evaluation.json"

PYTHONPATH=src:tools "$ML_PYTHON" tools/run_matched_transition_death_test.py evaluate \
  "$EVIDENCE/natural-30-5-5" "$EVIDENCE/manifest.json" \
  "$EVIDENCE/candidate-a.json" \
  docs/reviews/pc_a/matched_transition_death_test_2026-10-09/TARGETS.json \
  "$EVIDENCE/candidate-evaluation.json"

PYTHONPATH=src:tools "$ML_PYTHON" tools/run_matched_transition_death_test.py replay \
  "$EVIDENCE/natural-30-5-5" "$EVIDENCE/manifest.json" \
  "$EVIDENCE/ambiguity.json" --arm candidate-ambiguity-control \
  --expected-sha a5385ddaf6724d2d346fc222866edc2b7ec9407c \
  --ambiguity-from "$EVIDENCE/candidate-a.json"

PYTHONPATH=src:tools "$ML_PYTHON" tools/run_matched_transition_death_test.py evaluate \
  "$EVIDENCE/natural-30-5-5" "$EVIDENCE/manifest.json" \
  "$EVIDENCE/ambiguity.json" \
  docs/reviews/pc_a/matched_transition_death_test_2026-10-09/TARGETS.json \
  "$EVIDENCE/ambiguity-evaluation.json"

PYTHONPATH=src:tools "$ML_PYTHON" tools/run_matched_transition_death_test.py summarize \
  "$EVIDENCE/baseline-a.json" "$EVIDENCE/baseline-b.json" \
  "$EVIDENCE/candidate-a.json" "$EVIDENCE/candidate-b.json" \
  "$EVIDENCE/baseline-evaluation.json" "$EVIDENCE/candidate-evaluation.json" \
  "$EVIDENCE/ambiguity.json" "$EVIDENCE/ambiguity-evaluation.json" \
  "$EVIDENCE/summary.json"

PYTHONPATH=src:tools "$ML_PYTHON" tools/run_matched_transition_death_test.py diagnose \
  "$EVIDENCE/natural-30-5-5" "$EVIDENCE/manifest.json" \
  "$EVIDENCE/candidate-a.json" "$EVIDENCE/candidate-evaluation.json" \
  "$EVIDENCE/false-reidentification-diagnostic.json"
```

本轮定向工程验证：

```bash
PYTHONPATH=src:tools "$ML_PYTHON" -m pytest -q \
  tests/test_matched_transition_death_test.py \
  tests/test_natural_mask_surface.py \
  tests/test_native_raw_candidate_verification.py \
  tests/test_mask_surface_comparison.py

"$ML_PYTHON" -m py_compile tools/run_matched_transition_death_test.py
ruff check tools/run_matched_transition_death_test.py tests/test_matched_transition_death_test.py
ruff format --check tools/run_matched_transition_death_test.py tests/test_matched_transition_death_test.py
git diff --check
```
