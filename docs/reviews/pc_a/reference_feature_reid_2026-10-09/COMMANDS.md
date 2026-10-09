# 参考特征几何核验复现命令

以下命令从仓库根目录执行。`$OLD_EVIDENCE` 指向 PR100 的 `docs/reviews/pc_a/matched_transition_death_test_2026-10-09/evidence`，`$OUT` 指向本目录的 `evidence`，Python 环境需包含项目 perception 依赖。

```bash
PYTHONPATH=src:tools "$ML_PYTHON" tools/run_matched_transition_death_test.py replay \
  "$OLD_EVIDENCE/natural-30-5-5" "$OLD_EVIDENCE/manifest.json" \
  "$OUT/subpixel-a.json" --arm reference-feature-subpixel-candidate \
  --expected-sha 8acab228c6cdaa85865088f73c82b9455fb3fea1

PYTHONPATH=src:tools "$ML_PYTHON" tools/run_matched_transition_death_test.py replay \
  "$OLD_EVIDENCE/natural-30-5-5" "$OLD_EVIDENCE/manifest.json" \
  "$OUT/subpixel-b.json" --arm reference-feature-subpixel-candidate \
  --expected-sha 8acab228c6cdaa85865088f73c82b9455fb3fea1

cmp "$OUT/subpixel-a.json" "$OUT/subpixel-b.json"

PYTHONPATH=src:tools "$ML_PYTHON" tools/run_matched_transition_death_test.py evaluate \
  "$OLD_EVIDENCE/natural-30-5-5" "$OLD_EVIDENCE/manifest.json" \
  "$OUT/subpixel-a.json" \
  docs/reviews/pc_a/matched_transition_death_test_2026-10-09/TARGETS.json \
  "$OUT/subpixel-evaluation.json"

PYTHONPATH=src:tools "$ML_PYTHON" tools/run_matched_transition_death_test.py replay \
  "$OLD_EVIDENCE/natural-30-5-5" "$OLD_EVIDENCE/manifest.json" \
  "$OUT/subpixel-ambiguity.json" --arm reference-feature-subpixel-ambiguity-control \
  --expected-sha 8acab228c6cdaa85865088f73c82b9455fb3fea1 \
  --ambiguity-from "$OUT/subpixel-a.json"

PYTHONPATH=src:tools "$ML_PYTHON" tools/run_matched_transition_death_test.py evaluate \
  "$OLD_EVIDENCE/natural-30-5-5" "$OLD_EVIDENCE/manifest.json" \
  "$OUT/subpixel-ambiguity.json" \
  docs/reviews/pc_a/matched_transition_death_test_2026-10-09/TARGETS.json \
  "$OUT/subpixel-ambiguity-evaluation.json"

PYTHONPATH=src:tools "$ML_PYTHON" tools/run_matched_transition_death_test.py summarize \
  "$OLD_EVIDENCE/baseline-a.json" "$OLD_EVIDENCE/baseline-b.json" \
  "$OUT/subpixel-a.json" "$OUT/subpixel-b.json" \
  "$OLD_EVIDENCE/baseline-evaluation.json" "$OUT/subpixel-evaluation.json" \
  "$OUT/subpixel-ambiguity.json" "$OUT/subpixel-ambiguity-evaluation.json" \
  "$OUT/subpixel-summary.json"

PYTHONPATH=src:tools "$ML_PYTHON" tools/run_matched_transition_death_test.py diagnose \
  "$OLD_EVIDENCE/natural-30-5-5" "$OLD_EVIDENCE/manifest.json" \
  "$OUT/subpixel-a.json" "$OUT/subpixel-evaluation.json" \
  "$OUT/subpixel-diagnostic.json"
```

聚焦工程验证：

```bash
PYTHONPATH=src:tools "$ML_PYTHON" -m pytest -q \
  tests/test_visual_target_tracking.py \
  tests/test_natural_mask_surface.py \
  tests/test_matched_transition_death_test.py \
  tests/test_native_raw_candidate_verification.py \
  tests/test_mask_surface_comparison.py

PYTHONPATH=src "$ML_PYTHON" -m mypy \
  src/cpswm/perception_mapping/visual_target_tracking.py \
  src/cpswm/perception_mapping/mask_surface_sequence.py

"$ML_PYTHON" -m py_compile \
  src/cpswm/perception_mapping/visual_target_tracking.py \
  src/cpswm/perception_mapping/mask_surface_sequence.py \
  tools/run_matched_transition_death_test.py

ruff check \
  src/cpswm/perception_mapping/visual_target_tracking.py \
  src/cpswm/perception_mapping/mask_surface_sequence.py \
  tests/test_visual_target_tracking.py tests/test_natural_mask_surface.py

ruff format --check \
  src/cpswm/perception_mapping/visual_target_tracking.py \
  src/cpswm/perception_mapping/mask_surface_sequence.py \
  tests/test_visual_target_tracking.py tests/test_natural_mask_surface.py

git diff --check
```
