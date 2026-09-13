#!/bin/sh
# Run from this Window-2 worktree; OUT must be a NEW directory. Never overwrite old bundles.
set -eu
PY=/Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/.venv/bin/python
OUT=${1:?provide a new output directory}
export PYTHONPATH="$PWD/src"
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1
mkdir -p "$OUT/evidence"
OUT=$(cd "$OUT" && pwd)
"$PY" apps/evaluation_runner/run_structure_two_comparison_audit.py --output "$OUT/bundle_v4" --timing-repeats 3 --timing-episodes 2 > "$OUT/evidence/generation.log" 2>&1
"$PY" apps/evaluation_runner/summarize_structure_two_comparison_audit.py --bundle "$OUT/bundle_v4" > "$OUT/evidence/attribution_generation.log" 2>&1
"$PY" apps/evaluation_runner/run_structure_two_comparison_audit.py --output "$OUT/bundle_v4" --verify --timing-repeats 1 --timing-episodes 1 > "$OUT/evidence/main_verify.log" 2>&1
"$PY" apps/evaluation_runner/summarize_structure_two_comparison_audit.py --bundle "$OUT/bundle_v4" --verify > "$OUT/evidence/attribution_verify.log" 2>&1
# These parallel regression timings are NOT performance comparisons.
export S2_AUDIT_BUNDLE="$OUT/bundle_v4"
export S2_AUDIT_EVIDENCE_DIR="$OUT/evidence/r1_matrix"
export S2_SOURCE_EVIDENCE_DIR="$OUT/evidence/source_tests"
export S2_FAIRNESS_EVIDENCE_DIR="$OUT/evidence/fairness_tests"
"$PY" -m pytest -n 3 -q -o addopts='' --junitxml="$OUT/evidence/pytest.xml" tests/test_structure_two_comparison_audit.py tests/test_structure_two_comparison_audit_verification.py tests/test_structure_two_comparison_audit_execution_source.py tests/test_structure_two_comparison_fairness.py > "$OUT/evidence/regressions.log" 2>&1
