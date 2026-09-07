#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/../.." && pwd)"
replay_root="$(mktemp -d /tmp/cpswm-task12-replay.XXXXXX)"
output_dir="$replay_root/task12"
recomputed="$replay_root/recomputed.json"

cd "$repo_root"
PYTHONPATH=src uv run python apps/evaluation_runner/run_structure_two_task12_rejuvenation_diagnostic.py \
  --output-dir "$output_dir" \
  --invocation-id task12-rejuvenation-diagnostic-2026-09-06-final
PYTHONPATH=src uv run python \
  apps/evaluation_runner/recompute_structure_two_task12_rejuvenation_diagnostic.py \
  --g1-traces "$output_dir/raw_traces/task12_g1_raw_traces.jsonl" \
  --g2-traces "$output_dir/raw_traces/task12_g2_raw_traces.jsonl" \
  --output "$recomputed"

printf 'replay_root=%s\n' "$replay_root"
printf 'result_sha256=%s\n' "$(uv run python -c 'import json,sys; print(json.load(open(sys.argv[1]))["deterministic_result_sha256"])' "$recomputed")"
