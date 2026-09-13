# 窗口一补修完整验证命令索引

执行 cwd：`/private/tmp/cpswm-s2-evidence-repair-window1`；原生 Python 3.13.5。

封存后的五类路径再次生成应被拒绝；复核已有版本使用 `--verify-current`。整合改码后须使用新证据版本或内容寻址路径，不覆盖旧工件。

早期开发试跑的精确 pytest/mypy/ruff 命令及原始工具调用另见 `early_validation_commands.md`。以下保留失败与预期拒绝，不把 exit 1/2 记作通过。

## before/late_import — exit 0

```bash
/private/tmp/cpswm-s2-evidence-repair-window1/.venv/bin/python /Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/docs/reviews/data/structure_two_window1_adversarial_review_2026-09-11/counterexamples.py /private/tmp/cpswm-s2-evidence-repair-window1 late_import
```

原始日志：`../before/late_import.stdout.log.gz`、对应 stderr。

## before/stale_pyc — exit 0

```bash
/private/tmp/cpswm-s2-evidence-repair-window1/.venv/bin/python /Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/docs/reviews/data/structure_two_window1_adversarial_review_2026-09-11/counterexamples.py /private/tmp/cpswm-s2-evidence-repair-window1 stale_pyc
```

原始日志：`../before/stale_pyc.stdout.log.gz`、对应 stderr。

## before/empty_history — exit 0

```bash
/private/tmp/cpswm-s2-evidence-repair-window1/.venv/bin/python /Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/docs/reviews/data/structure_two_window1_adversarial_review_2026-09-11/counterexamples.py /private/tmp/cpswm-s2-evidence-repair-window1 empty_history
```

原始日志：`../before/empty_history.stdout.log.gz`、对应 stderr。

## before/renamed_history — exit 0

```bash
/private/tmp/cpswm-s2-evidence-repair-window1/.venv/bin/python /Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/docs/reviews/data/structure_two_window1_adversarial_review_2026-09-11/counterexamples.py /private/tmp/cpswm-s2-evidence-repair-window1 renamed_history
```

原始日志：`../before/renamed_history.stdout.log.gz`、对应 stderr。

## before/hardlink — exit 0

```bash
/private/tmp/cpswm-s2-evidence-repair-window1/.venv/bin/python /Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/docs/reviews/data/structure_two_window1_adversarial_review_2026-09-11/counterexamples.py /private/tmp/cpswm-s2-evidence-repair-window1 hardlink
```

原始日志：`../before/hardlink.stdout.log.gz`、对应 stderr。

## after_original_attacks/late_import — exit 1

```bash
/private/tmp/cpswm-s2-evidence-repair-window1/.venv/bin/python /Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/docs/reviews/data/structure_two_window1_adversarial_review_2026-09-11/counterexamples.py /private/tmp/cpswm-s2-evidence-repair-window1 late_import
```

原始日志：`../after_original_attacks/late_import.stdout.log.gz`、对应 stderr。

## after_original_attacks/stale_pyc — exit 1

```bash
/private/tmp/cpswm-s2-evidence-repair-window1/.venv/bin/python /Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/docs/reviews/data/structure_two_window1_adversarial_review_2026-09-11/counterexamples.py /private/tmp/cpswm-s2-evidence-repair-window1 stale_pyc
```

原始日志：`../after_original_attacks/stale_pyc.stdout.log.gz`、对应 stderr。

## after_original_attacks/empty_history — exit 0

```bash
/private/tmp/cpswm-s2-evidence-repair-window1/.venv/bin/python /Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/docs/reviews/data/structure_two_window1_adversarial_review_2026-09-11/counterexamples.py /private/tmp/cpswm-s2-evidence-repair-window1 empty_history
```

原始日志：`../after_original_attacks/empty_history.stdout.log.gz`、对应 stderr。

## after_original_attacks/renamed_history — exit 1

```bash
/private/tmp/cpswm-s2-evidence-repair-window1/.venv/bin/python /Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/docs/reviews/data/structure_two_window1_adversarial_review_2026-09-11/counterexamples.py /private/tmp/cpswm-s2-evidence-repair-window1 renamed_history
```

原始日志：`../after_original_attacks/renamed_history.stdout.log.gz`、对应 stderr。

## after_original_attacks/hardlink — exit 1

```bash
/private/tmp/cpswm-s2-evidence-repair-window1/.venv/bin/python /Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/docs/reviews/data/structure_two_window1_adversarial_review_2026-09-11/counterexamples.py /private/tmp/cpswm-s2-evidence-repair-window1 hardlink
```

原始日志：`../after_original_attacks/hardlink.stdout.log.gz`、对应 stderr。

## targeted_preseal — exit 1

UTC：2026-09-11T12:51:05.255315+00:00 至 2026-09-11T12:51:05.352786+00:00；实际环境覆盖见 `commands.jsonl`。

```bash
.venv/bin/pytest -p xdist.plugin -n 8 -q --confcutdir=. tests/test_structure_two_evidence_versions.py tests/test_p0_checkpoint_manifest.py tests/test_structure_two_p5_readout_posthoc_diagnostic.py tests/test_structure_two_p5_readout_prior_factorial.py tests/test_structure_two_trusted_ablation_authorization.py tests/test_structure_two_gate_b_v0_8_raw_formal_execution.py tests/test_structure_two_comparator_typed_dual_gate_b_v0_8.py tests/test_structure_two_engineering_trust_checkpoint.py tests/test_structure_two_evidence_supplement.py
```

stdout: `benchmarks/structure_two/evidence_repair_supplement_2026_09_11/validation_logs/targeted_preseal.stdout.log.gz`
stderr: `benchmarks/structure_two/evidence_repair_supplement_2026_09_11/validation_logs/targeted_preseal.stderr.log.gz`

## formal_source_probe — exit 0

UTC：2026-09-11T13:07:29.448347+00:00 至 2026-09-11T13:07:31.538194+00:00；实际环境覆盖见 `commands.jsonl`。

```bash
.venv/bin/python apps/evaluation_runner/probe_structure_two_execution_source.py
```

stdout: `benchmarks/structure_two/evidence_repair_supplement_2026_09_11/validation_logs/formal_source_probe.stdout.log.gz`
stderr: `benchmarks/structure_two/evidence_repair_supplement_2026_09_11/validation_logs/formal_source_probe.stderr.log.gz`

## targeted_preseal_native — exit 1

UTC：2026-09-11T12:51:20.840918+00:00 至 2026-09-11T13:20:39.875053+00:00；实际环境覆盖见 `commands.jsonl`。

```bash
.venv/bin/pytest -p xdist.plugin -n 8 -q --confcutdir=. tests/test_structure_two_evidence_versions.py tests/test_p0_checkpoint_manifest.py tests/test_structure_two_p5_readout_posthoc_diagnostic.py tests/test_structure_two_p5_readout_prior_factorial.py tests/test_structure_two_trusted_ablation_authorization.py tests/test_structure_two_gate_b_v0_8_raw_formal_execution.py tests/test_structure_two_comparator_typed_dual_gate_b_v0_8.py tests/test_structure_two_engineering_trust_checkpoint.py tests/test_structure_two_evidence_supplement.py
```

stdout: `benchmarks/structure_two/evidence_repair_supplement_2026_09_11/validation_logs/targeted_preseal_native.stdout.log.gz`
stderr: `benchmarks/structure_two/evidence_repair_supplement_2026_09_11/validation_logs/targeted_preseal_native.stderr.log.gz`

## source_commit_raw_log_whitespace — exit 2

UTC：2026-09-11T13:38:53.810536+00:00 至 2026-09-11T13:38:53.874632+00:00；实际环境覆盖见 `commands.jsonl`。

```bash
.venv/bin/python -c 'import subprocess; raise SystemExit(subprocess.run(["git","diff","91dbdc57968071be29976d1a7b99de51d9288cdd","3dce0485234f941fc9520e52b1fe9d8f14ded892","--check"]).returncode)'
```

stdout: `benchmarks/structure_two/evidence_repair_supplement_2026_09_11/validation_logs/source_commit_raw_log_whitespace.stdout.log.gz`
stderr: `benchmarks/structure_two/evidence_repair_supplement_2026_09_11/validation_logs/source_commit_raw_log_whitespace.stderr.log.gz`

## generate_current_v0_3 — exit 0

UTC：2026-09-11T13:22:14.401774+00:00 至 2026-09-11T13:52:10.033359+00:00；实际环境覆盖见 `commands.jsonl`。

```bash
.venv/bin/python apps/evaluation_runner/run_structure_two_evidence_repair.py --generate-current
```

stdout: `benchmarks/structure_two/evidence_repair_supplement_2026_09_11/validation_logs/generate_current_v0_3.stdout.log.gz`
stderr: `benchmarks/structure_two/evidence_repair_supplement_2026_09_11/validation_logs/generate_current_v0_3.stderr.log.gz`

## preserved_and_new_before_p0 — exit 0

UTC：2026-09-11T13:54:30.687580+00:00 至 2026-09-11T13:54:30.998083+00:00；实际环境覆盖见 `commands.jsonl`。

```bash
.venv/bin/python benchmarks/structure_two/evidence_repair_supplement_2026_09_11/validation_logs/check_preserved_and_new.py
```

stdout: `benchmarks/structure_two/evidence_repair_supplement_2026_09_11/validation_logs/preserved_and_new_before_p0.stdout.log.gz`
stderr: `benchmarks/structure_two/evidence_repair_supplement_2026_09_11/validation_logs/preserved_and_new_before_p0.stderr.log.gz`

## refuse_sealed_current — exit 1

UTC：2026-09-11T13:55:04.361523+00:00 至 2026-09-11T13:55:06.238648+00:00；实际环境覆盖见 `commands.jsonl`。

```bash
.venv/bin/python apps/evaluation_runner/run_structure_two_evidence_repair.py --generate-current
```

stdout: `benchmarks/structure_two/evidence_repair_supplement_2026_09_11/validation_logs/refuse_sealed_current.stdout.log.gz`
stderr: `benchmarks/structure_two/evidence_repair_supplement_2026_09_11/validation_logs/refuse_sealed_current.stderr.log.gz`

## history_generate_v0_2 — exit 0

UTC：2026-09-11T13:54:30.672951+00:00 至 2026-09-11T13:59:21.643138+00:00；实际环境覆盖见 `commands.jsonl`。

```bash
.venv/bin/python apps/evaluation_runner/audit_structure_two_evidence_history.py --recompute-first-failure --recompute-failed-replay --output benchmarks/structure_two/evidence_repair_supplement_2026_09_11/historical_source_audit_v0_2.json
```

stdout: `benchmarks/structure_two/evidence_repair_supplement_2026_09_11/validation_logs/history_generate_v0_2.stdout.log.gz`
stderr: `benchmarks/structure_two/evidence_repair_supplement_2026_09_11/validation_logs/history_generate_v0_2.stderr.log.gz`

## history_aggregate_full_replay — exit 0

UTC：2026-09-11T13:54:30.676723+00:00 至 2026-09-11T13:59:22.207010+00:00；实际环境覆盖见 `commands.jsonl`。

```bash
.venv/bin/python apps/evaluation_runner/run_structure_two_evidence_repair.py --verify-history
```

stdout: `benchmarks/structure_two/evidence_repair_supplement_2026_09_11/validation_logs/history_aggregate_full_replay.stdout.log.gz`
stderr: `benchmarks/structure_two/evidence_repair_supplement_2026_09_11/validation_logs/history_aggregate_full_replay.stderr.log.gz`

## v05_current_compatibility — exit 0

UTC：2026-09-11T13:59:37.447783+00:00 至 2026-09-11T13:59:38.026649+00:00；实际环境覆盖见 `commands.jsonl`。

```bash
.venv/bin/python apps/evaluation_runner/audit_structure_two_world_source_bundle_v0_5.py
```

stdout: `benchmarks/structure_two/evidence_repair_supplement_2026_09_11/validation_logs/v05_current_compatibility.stdout.log.gz`
stderr: `benchmarks/structure_two/evidence_repair_supplement_2026_09_11/validation_logs/v05_current_compatibility.stderr.log.gz`

## p0_generation — exit 0

UTC：2026-09-11T13:59:47.641175+00:00 至 2026-09-11T13:59:47.851502+00:00；实际环境覆盖见 `commands.jsonl`。

```bash
.venv/bin/python apps/evaluation_runner/generate_p0_checkpoint_manifest.py
```

stdout: `benchmarks/structure_two/evidence_repair_supplement_2026_09_11/validation_logs/p0_generation.stdout.log.gz`
stderr: `benchmarks/structure_two/evidence_repair_supplement_2026_09_11/validation_logs/p0_generation.stderr.log.gz`

## engineering_audit_v0_2 — exit 0

UTC：2026-09-11T14:00:11.181406+00:00 至 2026-09-11T14:49:50.722101+00:00；实际环境覆盖见 `commands.jsonl`。

```bash
.venv/bin/python apps/evaluation_runner/run_structure_two_engineering_audit_receipt.py
```

stdout: `benchmarks/structure_two/evidence_repair_supplement_2026_09_11/validation_logs/engineering_audit_v0_2.stdout.log.gz`
stderr: `benchmarks/structure_two/evidence_repair_supplement_2026_09_11/validation_logs/engineering_audit_v0_2.stderr.log.gz`

## sandbox_and_known_xfail_supplement — exit 0

UTC：2026-09-11T14:56:09.309106+00:00 至 2026-09-11T14:56:30.675916+00:00；实际环境覆盖见 `commands.jsonl`。

```bash
.venv/bin/pytest -o addopts= -q -rsx --confcutdir=. tests/test_structure_two_sealed_dual_gate_b_v1_0.py::test_real_sandbox_ten_arm_receipts_bind_full_support_and_deny_opening_bytes tests/test_project_one_same_context_rls_ablation.py::test_shipped_wiring_shuffling_costs_real_discrimination
```

stdout: `benchmarks/structure_two/evidence_repair_supplement_2026_09_11/validation_logs/sandbox_and_known_xfail_supplement.stdout.log.gz`
stderr: `benchmarks/structure_two/evidence_repair_supplement_2026_09_11/validation_logs/sandbox_and_known_xfail_supplement.stderr.log.gz`

## preserved_and_new_final — exit 0

UTC：2026-09-11T15:06:39.791906+00:00 至 2026-09-11T15:06:40.035696+00:00；实际环境覆盖见 `commands.jsonl`。

```bash
.venv/bin/python benchmarks/structure_two/evidence_repair_supplement_2026_09_11/validation_logs/check_preserved_and_new.py
```

stdout: `benchmarks/structure_two/evidence_repair_supplement_2026_09_11/validation_logs/preserved_and_new_final.stdout.log.gz`
stderr: `benchmarks/structure_two/evidence_repair_supplement_2026_09_11/validation_logs/preserved_and_new_final.stderr.log.gz`

## reject_old_checkpoint_as_current — exit 1

UTC：2026-09-11T15:06:51.788325+00:00 至 2026-09-11T15:06:53.620553+00:00；实际环境覆盖见 `commands.jsonl`。

```bash
.venv/bin/python apps/evaluation_runner/generate_structure_two_engineering_trust_checkpoint.py --verify benchmarks/structure_two/engineering_trust_checkpoint_2026_09_05/engineering_checkpoint.json --no-fresh-recomputation
```

stdout: `benchmarks/structure_two/evidence_repair_supplement_2026_09_11/validation_logs/reject_old_checkpoint_as_current.stdout.log.gz`
stderr: `benchmarks/structure_two/evidence_repair_supplement_2026_09_11/validation_logs/reject_old_checkpoint_as_current.stderr.log.gz`

## checkpoint_generation_fresh — exit 0

UTC：2026-09-11T14:58:09.904326+00:00 至 2026-09-11T15:07:17.689357+00:00；实际环境覆盖见 `commands.jsonl`。

```bash
.venv/bin/python apps/evaluation_runner/generate_structure_two_engineering_trust_checkpoint.py
```

stdout: `benchmarks/structure_two/evidence_repair_supplement_2026_09_11/validation_logs/checkpoint_generation_fresh.stdout.log.gz`
stderr: `benchmarks/structure_two/evidence_repair_supplement_2026_09_11/validation_logs/checkpoint_generation_fresh.stderr.log.gz`

## checkpoint_currentness — exit 0

UTC：2026-09-11T15:07:36.849236+00:00 至 2026-09-11T15:07:39.068298+00:00；实际环境覆盖见 `commands.jsonl`。

```bash
.venv/bin/python apps/evaluation_runner/generate_structure_two_engineering_trust_checkpoint.py --verify benchmarks/structure_two/engineering_trust_checkpoint_2026_09_11_v0_2/engineering_checkpoint.json --no-fresh-recomputation
```

stdout: `benchmarks/structure_two/evidence_repair_supplement_2026_09_11/validation_logs/checkpoint_currentness.stdout.log.gz`
stderr: `benchmarks/structure_two/evidence_repair_supplement_2026_09_11/validation_logs/checkpoint_currentness.stderr.log.gz`

## checkpoint_regression_diagnosis — exit 1

UTC：2026-09-11T15:08:18.839750+00:00 至 2026-09-11T15:08:26.142488+00:00；实际环境覆盖见 `commands.jsonl`。

```bash
.venv/bin/pytest -o addopts= -q -x --confcutdir=. tests/test_structure_two_engineering_trust_checkpoint.py
```

stdout: `benchmarks/structure_two/evidence_repair_supplement_2026_09_11/validation_logs/checkpoint_regression_diagnosis.stdout.log.gz`
stderr: `benchmarks/structure_two/evidence_repair_supplement_2026_09_11/validation_logs/checkpoint_regression_diagnosis.stderr.log.gz`

## targeted_final — exit 1

UTC：2026-09-11T15:07:36.853118+00:00 至 2026-09-11T15:22:37.940158+00:00；实际环境覆盖见 `commands.jsonl`。

```bash
.venv/bin/pytest -o addopts= -q -n 8 --dist=worksteal --confcutdir=. tests/test_structure_two_evidence_versions.py tests/test_p0_checkpoint_manifest.py tests/test_structure_two_p5_readout_posthoc_diagnostic.py tests/test_structure_two_p5_readout_prior_factorial.py tests/test_structure_two_trusted_ablation_authorization.py tests/test_structure_two_gate_b_v0_8_raw_formal_execution.py tests/test_structure_two_comparator_typed_dual_gate_b_v0_8.py tests/test_structure_two_engineering_trust_checkpoint.py tests/test_structure_two_evidence_supplement.py
```

stdout: `benchmarks/structure_two/evidence_repair_supplement_2026_09_11/validation_logs/targeted_final.stdout.log.gz`
stderr: `benchmarks/structure_two/evidence_repair_supplement_2026_09_11/validation_logs/targeted_final.stderr.log.gz`

## command_contract_fixed — exit 0

UTC：2026-09-11T15:23:06.615775+00:00 至 2026-09-11T15:23:07.018042+00:00；实际环境覆盖见 `commands.jsonl`。

```bash
.venv/bin/pytest -o addopts= -q --confcutdir=. tests/test_structure_two_engineering_trust_checkpoint.py::test_audit_matrix_contains_frozen_offline_uv_environment_check
```

stdout: `benchmarks/structure_two/evidence_repair_supplement_2026_09_11/validation_logs/command_contract_fixed.stdout.log.gz`
stderr: `benchmarks/structure_two/evidence_repair_supplement_2026_09_11/validation_logs/command_contract_fixed.stderr.log.gz`

## p0_generation_final — exit 0

UTC：2026-09-11T15:24:46.651834+00:00 至 2026-09-11T15:24:46.846883+00:00；实际环境覆盖见 `commands.jsonl`。

```bash
.venv/bin/python apps/evaluation_runner/generate_p0_checkpoint_manifest.py
```

stdout: `benchmarks/structure_two/evidence_repair_supplement_2026_09_11/validation_logs/p0_generation_final.stdout.log.gz`
stderr: `benchmarks/structure_two/evidence_repair_supplement_2026_09_11/validation_logs/p0_generation_final.stderr.log.gz`

## targeted_test_inventory — exit 0

UTC：2026-09-11T15:27:20.942778+00:00 至 2026-09-11T15:27:24.288677+00:00；实际环境覆盖见 `commands.jsonl`。

```bash
.venv/bin/pytest -o addopts= --collect-only -q --confcutdir=. tests/test_structure_two_evidence_versions.py tests/test_p0_checkpoint_manifest.py tests/test_structure_two_p5_readout_posthoc_diagnostic.py tests/test_structure_two_p5_readout_prior_factorial.py tests/test_structure_two_trusted_ablation_authorization.py tests/test_structure_two_gate_b_v0_8_raw_formal_execution.py tests/test_structure_two_comparator_typed_dual_gate_b_v0_8.py tests/test_structure_two_engineering_trust_checkpoint.py tests/test_structure_two_evidence_supplement.py
```

stdout: `benchmarks/structure_two/evidence_repair_supplement_2026_09_11/validation_logs/targeted_test_inventory.stdout.log.gz`
stderr: `benchmarks/structure_two/evidence_repair_supplement_2026_09_11/validation_logs/targeted_test_inventory.stderr.log.gz`

## engineering_audit_final — exit 0

UTC：2026-09-11T15:24:56.450394+00:00 至 2026-09-11T16:03:04.711410+00:00；实际环境覆盖见 `commands.jsonl`。

```bash
.venv/bin/python apps/evaluation_runner/run_structure_two_engineering_audit_receipt.py
```

stdout: `benchmarks/structure_two/evidence_repair_supplement_2026_09_11/validation_logs/engineering_audit_final.stdout.log.gz`
stderr: `benchmarks/structure_two/evidence_repair_supplement_2026_09_11/validation_logs/engineering_audit_final.stderr.log.gz`

## sandbox_and_known_xfail_final — exit 0

UTC：2026-09-11T16:05:02.236653+00:00 至 2026-09-11T16:05:15.191662+00:00；实际环境覆盖见 `commands.jsonl`。

```bash
.venv/bin/pytest -o addopts= -q -rsx --confcutdir=. tests/test_structure_two_sealed_dual_gate_b_v1_0.py::test_real_sandbox_ten_arm_receipts_bind_full_support_and_deny_opening_bytes tests/test_project_one_same_context_rls_ablation.py::test_shipped_wiring_shuffling_costs_real_discrimination
```

stdout: `benchmarks/structure_two/evidence_repair_supplement_2026_09_11/validation_logs/sandbox_and_known_xfail_final.stdout.log.gz`
stderr: `benchmarks/structure_two/evidence_repair_supplement_2026_09_11/validation_logs/sandbox_and_known_xfail_final.stderr.log.gz`

## checkpoint_generation_final_fresh — exit 0

UTC：2026-09-11T16:05:28.385397+00:00 至 2026-09-11T16:13:56.557935+00:00；实际环境覆盖见 `commands.jsonl`。

```bash
.venv/bin/python apps/evaluation_runner/generate_structure_two_engineering_trust_checkpoint.py
```

stdout: `benchmarks/structure_two/evidence_repair_supplement_2026_09_11/validation_logs/checkpoint_generation_final_fresh.stdout.log.gz`
stderr: `benchmarks/structure_two/evidence_repair_supplement_2026_09_11/validation_logs/checkpoint_generation_final_fresh.stderr.log.gz`

## checkpoint_currentness_final — exit 0

UTC：2026-09-11T16:14:26.556981+00:00 至 2026-09-11T16:14:30.036204+00:00；实际环境覆盖见 `commands.jsonl`。

```bash
.venv/bin/python apps/evaluation_runner/generate_structure_two_engineering_trust_checkpoint.py --verify benchmarks/structure_two/engineering_trust_checkpoint_2026_09_11_v0_2/engineering_checkpoint.json --no-fresh-recomputation
```

stdout: `benchmarks/structure_two/evidence_repair_supplement_2026_09_11/validation_logs/checkpoint_currentness_final.stdout.log.gz`
stderr: `benchmarks/structure_two/evidence_repair_supplement_2026_09_11/validation_logs/checkpoint_currentness_final.stderr.log.gz`

## preserved_and_new_post_checkpoint — exit 0

UTC：2026-09-11T16:14:52.771277+00:00 至 2026-09-11T16:14:53.331082+00:00；实际环境覆盖见 `commands.jsonl`。

```bash
.venv/bin/python benchmarks/structure_two/evidence_repair_supplement_2026_09_11/validation_logs/check_preserved_and_new.py
```

stdout: `benchmarks/structure_two/evidence_repair_supplement_2026_09_11/validation_logs/preserved_and_new_post_checkpoint.stdout.log.gz`
stderr: `benchmarks/structure_two/evidence_repair_supplement_2026_09_11/validation_logs/preserved_and_new_post_checkpoint.stderr.log.gz`

## reject_reviewed_checkpoint_final — exit 1

UTC：2026-09-11T16:14:52.774568+00:00 至 2026-09-11T16:14:56.067276+00:00；实际环境覆盖见 `commands.jsonl`。

```bash
.venv/bin/python apps/evaluation_runner/generate_structure_two_engineering_trust_checkpoint.py --verify benchmarks/structure_two/engineering_trust_checkpoint_2026_09_05/engineering_checkpoint.json --no-fresh-recomputation
```

stdout: `benchmarks/structure_two/evidence_repair_supplement_2026_09_11/validation_logs/reject_reviewed_checkpoint_final.stdout.log.gz`
stderr: `benchmarks/structure_two/evidence_repair_supplement_2026_09_11/validation_logs/reject_reviewed_checkpoint_final.stderr.log.gz`

## reject_precontract_candidate_final — exit 1

UTC：2026-09-11T16:14:52.793702+00:00 至 2026-09-11T16:14:56.084625+00:00；实际环境覆盖见 `commands.jsonl`。

```bash
.venv/bin/python apps/evaluation_runner/generate_structure_two_engineering_trust_checkpoint.py --verify benchmarks/structure_two/evidence_repair_supplement_2026_09_11/candidate_before_command_contract_fix/engineering_checkpoint.json --no-fresh-recomputation
```

stdout: `benchmarks/structure_two/evidence_repair_supplement_2026_09_11/validation_logs/reject_precontract_candidate_final.stdout.log.gz`
stderr: `benchmarks/structure_two/evidence_repair_supplement_2026_09_11/validation_logs/reject_precontract_candidate_final.stderr.log.gz`

## targeted_final_after_contract_fix — exit 0

UTC：2026-09-11T16:14:26.559702+00:00 至 2026-09-11T16:31:45.223563+00:00；实际环境覆盖见 `commands.jsonl`。

```bash
.venv/bin/pytest -o addopts= -q -n 8 --dist=worksteal --confcutdir=. tests/test_structure_two_evidence_versions.py tests/test_p0_checkpoint_manifest.py tests/test_structure_two_p5_readout_posthoc_diagnostic.py tests/test_structure_two_p5_readout_prior_factorial.py tests/test_structure_two_trusted_ablation_authorization.py tests/test_structure_two_gate_b_v0_8_raw_formal_execution.py tests/test_structure_two_comparator_typed_dual_gate_b_v0_8.py tests/test_structure_two_engineering_trust_checkpoint.py tests/test_structure_two_evidence_supplement.py
```

stdout: `benchmarks/structure_two/evidence_repair_supplement_2026_09_11/validation_logs/targeted_final_after_contract_fix.stdout.log.gz`
stderr: `benchmarks/structure_two/evidence_repair_supplement_2026_09_11/validation_logs/targeted_final_after_contract_fix.stderr.log.gz`

## preserved_after_all_tests — exit 0

UTC：2026-09-11T16:34:05.781680+00:00 至 2026-09-11T16:34:05.991794+00:00；实际环境覆盖见 `commands.jsonl`。

```bash
.venv/bin/python benchmarks/structure_two/evidence_repair_supplement_2026_09_11/validation_logs/check_preserved_and_new.py
```

stdout: `benchmarks/structure_two/evidence_repair_supplement_2026_09_11/validation_logs/preserved_after_all_tests.stdout.log.gz`
stderr: `benchmarks/structure_two/evidence_repair_supplement_2026_09_11/validation_logs/preserved_after_all_tests.stderr.log.gz`

## final_log_archive_integrity — exit 0

UTC：2026-09-11T16:34:06.040515+00:00 至 2026-09-11T16:34:06.227229+00:00；实际环境覆盖见 `commands.jsonl`。

```bash
.venv/bin/python -c 'import gzip, hashlib, json, subprocess, tarfile
from pathlib import Path
root=Path.cwd()
base=root/'"'"'benchmarks/structure_two/evidence_repair_supplement_2026_09_11'"'"'
logs=base/'"'"'validation_logs'"'"'
rows=[json.loads(s) for s in (logs/'"'"'commands.jsonl'"'"').read_text().splitlines()]
count=0
for row in rows:
 for stream in ('"'"'stdout'"'"','"'"'stderr'"'"'):
  item=row.get(stream)
  if isinstance(item,dict) and '"'"'uncompressed_sha256'"'"' in item:
   data=gzip.decompress((root/item['"'"'path'"'"']).read_bytes())
   assert hashlib.sha256(data).hexdigest()==item['"'"'uncompressed_sha256'"'"'], item['"'"'path'"'"']
   count+=1
for directory in ('"'"'before'"'"','"'"'after_original_attacks'"'"'):
 for mode in ('"'"'late_import'"'"','"'"'stale_pyc'"'"','"'"'empty_history'"'"','"'"'renamed_history'"'"','"'"'hardlink'"'"'):
  for stream in ('"'"'stdout'"'"','"'"'stderr'"'"'):
   relative=(base/directory/(mode+'"'"'.'"'"'+stream+'"'"'.log'"'"')).relative_to(root).as_posix()
   expected=subprocess.check_output(['"'"'git'"'"','"'"'show'"'"','"'"'3dce0485234f941fc9520e52b1fe9d8f14ded892:'"'"'+relative],cwd=root)
   assert gzip.decompress((root/(relative+'"'"'.gz'"'"')).read_bytes())==expected,relative
script=gzip.decompress((base/'"'"'before/original_counterexamples.py.gz'"'"').read_bytes())
assert hashlib.sha256(script).hexdigest()=='"'"'7bf4159e6dddeca26b83a1ba6a3b0e3b447c2e39ef658e715f98735f55229e2c'"'"'
early=gzip.decompress((logs/'"'"'early_validation_tool_calls.jsonl.gz'"'"').read_bytes())
assert hashlib.sha256(early).hexdigest()=='"'"'138d67b430b16b846cd265f3e10d2e6d5ccef347f9dc639dc3cbefca0c5f6422'"'"'
assert len(early.splitlines())==4
prefix='"'"'benchmarks/structure_two/engineering_trust_checkpoint_2026_09_11_v0_2/'"'"'
candidate=base/'"'"'candidate_before_command_contract_fix'"'"'
with tarfile.open(logs/'"'"'preseal_command_contract_candidate.tar.gz'"'"','"'"'r:gz'"'"') as tar:
 members=tar.getmembers()
 assert len(members)==24
 for item in members:
  assert item.isfile()
  if item.name.startswith(prefix): target=candidate/item.name.removeprefix(prefix)
  elif item.name=='"'"'benchmarks/p0_checkpoint/content_manifest_v0_3.json'"'"': target=candidate/'"'"'p0_manifest.json'"'"'
  else:
   assert item.name=='"'"'docs/reviews/structure_two_evidence_repair_window1_supplement_2026-09-11.md'"'"'
   target=candidate/'"'"'bound_report.md'"'"'
  source=tar.extractfile(item)
  assert source is not None and source.read()==target.read_bytes(),item.name
receipt=json.loads((root/prefix/'"'"'engineering_audit_receipt.json'"'"').read_text())
assert len(receipt['"'"'command_runs'"'"'])==10
for row in receipt['"'"'command_runs'"'"']:
 assert row['"'"'exit_code'"'"']==0
 for stream in ('"'"'stdout'"'"','"'"'stderr'"'"'):
  path=root/row[stream+'"'"'_path'"'"']
  assert not path.is_symlink()
  assert hashlib.sha256(path.read_bytes()).hexdigest()==row[stream+'"'"'_sha256'"'"']
cp=json.loads((root/prefix/'"'"'engineering_checkpoint.json'"'"').read_text())
for row in cp['"'"'aligned_reports'"'"']:
 assert hashlib.sha256((root/row['"'"'path'"'"']).read_bytes()).hexdigest()==row['"'"'sha256'"'"']
assert subprocess.check_output(['"'"'git'"'"','"'"'diff'"'"','"'"'--name-only'"'"','"'"'HEAD'"'"','"'"'--'"'"','"'"'src'"'"','"'"'apps'"'"','"'"'tests'"'"','"'"'configs'"'"','"'"'conftest.py'"'"'],cwd=root)==b'"'"''"'"'
print(json.dumps({'"'"'completed_command_records_checked'"'"':len(rows),'"'"'indexed_raw_streams_checked'"'"':count,'"'"'original_attack_streams_equal_to_source_commit'"'"':20,'"'"'original_counterexample_script_sha256_verified'"'"':True,'"'"'early_original_tool_calls_verified'"'"':4,'"'"'candidate_archive_files_equal'"'"':24,'"'"'final_native_audit_raw_streams_verified'"'"':20,'"'"'bound_report_hashes_verified'"'"':len(cp['"'"'aligned_reports'"'"']),'"'"'source_and_test_inputs_unchanged_since_commit'"'"':True},indent=2))
'
```

stdout: `benchmarks/structure_two/evidence_repair_supplement_2026_09_11/validation_logs/final_log_archive_integrity.stdout.log.gz`
stderr: `benchmarks/structure_two/evidence_repair_supplement_2026_09_11/validation_logs/final_log_archive_integrity.stderr.log.gz`

## 首轮未封存候选，不作当前依据

回执 content SHA：`09a0b775ef8ca752e5ae9ce8f65bdaaa16516240216bf67a0479e2a4f49f0df4`。

### p5_evidence_current — exit 0

UTC：2026-09-11T14:00:12.298451+00:00 至 2026-09-11T14:16:42.997482+00:00。

```bash
.venv/bin/python apps/evaluation_runner/run_structure_two_evidence_repair.py --verify-current
```

实际原始日志：`benchmarks/structure_two/evidence_repair_supplement_2026_09_11/candidate_before_command_contract_fix/engineering_audit_logs/p5_evidence_current.stdout.log`、对应 stderr。环境覆盖和真实执行文件身份见本节回执。

### p5_evidence_history — exit 0

UTC：2026-09-11T14:00:12.297228+00:00 至 2026-09-11T14:08:01.805071+00:00。

```bash
.venv/bin/python apps/evaluation_runner/audit_structure_two_evidence_history.py --verify benchmarks/structure_two/evidence_repair_supplement_2026_09_11/historical_source_audit_v0_2.json
```

实际原始日志：`benchmarks/structure_two/evidence_repair_supplement_2026_09_11/candidate_before_command_contract_fix/engineering_audit_logs/p5_evidence_history.stdout.log`、对应 stderr。环境覆盖和真实执行文件身份见本节回执。

### p0_adversarial_tests — exit 0

UTC：2026-09-11T14:16:43.000113+00:00 至 2026-09-11T14:16:49.278272+00:00。

```bash
.venv/bin/pytest -o addopts= -q --confcutdir=. tests/test_structure_two_trusted_ablation_authorization.py tests/test_structure_two_gate_b_v0_8_raw_formal_execution.py tests/test_structure_two_comparator_typed_dual_gate_b_v0_8.py tests/test_p0_checkpoint_manifest.py
```

实际原始日志：`benchmarks/structure_two/evidence_repair_supplement_2026_09_11/candidate_before_command_contract_fix/engineering_audit_logs/p0_adversarial_tests.stdout.log`、对应 stderr。环境覆盖和真实执行文件身份见本节回执。

### core_pytest — exit 0

UTC：2026-09-11T14:16:49.278790+00:00 至 2026-09-11T14:49:49.544172+00:00。

```bash
.venv/bin/pytest -o addopts= -p xdist.plugin -n auto --dist=worksteal -q --confcutdir=. --ignore=tests/test_structure_two_engineering_trust_checkpoint.py
```

实际原始日志：`benchmarks/structure_two/evidence_repair_supplement_2026_09_11/candidate_before_command_contract_fix/engineering_audit_logs/core_pytest.stdout.log`、对应 stderr。环境覆盖和真实执行文件身份见本节回执。

### mypy_src — exit 0

UTC：2026-09-11T14:49:49.546156+00:00 至 2026-09-11T14:49:49.811467+00:00。

```bash
.venv/bin/mypy src
```

实际原始日志：`benchmarks/structure_two/evidence_repair_supplement_2026_09_11/candidate_before_command_contract_fix/engineering_audit_logs/mypy_src.stdout.log`、对应 stderr。环境覆盖和真实执行文件身份见本节回执。

### ruff_lint — exit 0

UTC：2026-09-11T14:49:49.822714+00:00 至 2026-09-11T14:49:49.837805+00:00。

```bash
.venv/bin/ruff check src tests apps
```

实际原始日志：`benchmarks/structure_two/evidence_repair_supplement_2026_09_11/candidate_before_command_contract_fix/engineering_audit_logs/ruff_lint.stdout.log`、对应 stderr。环境覆盖和真实执行文件身份见本节回执。

### ruff_format — exit 0

UTC：2026-09-11T14:49:49.847441+00:00 至 2026-09-11T14:49:49.857327+00:00。

```bash
.venv/bin/ruff format --check src tests apps
```

实际原始日志：`benchmarks/structure_two/evidence_repair_supplement_2026_09_11/candidate_before_command_contract_fix/engineering_audit_logs/ruff_format.stdout.log`、对应 stderr。环境覆盖和真实执行文件身份见本节回执。

### compileall — exit 0

UTC：2026-09-11T14:49:49.857773+00:00 至 2026-09-11T14:49:49.970144+00:00。

```bash
.venv/bin/python -m compileall -q src apps tests
```

实际原始日志：`benchmarks/structure_two/evidence_repair_supplement_2026_09_11/candidate_before_command_contract_fix/engineering_audit_logs/compileall.stdout.log`、对应 stderr。环境覆盖和真实执行文件身份见本节回执。

### uv_frozen_offline_check — exit 0

UTC：2026-09-11T14:49:49.990560+00:00 至 2026-09-11T14:49:50.063038+00:00。

```bash
uv sync --frozen --offline --check --extra dev --no-cache
```

实际原始日志：`benchmarks/structure_two/evidence_repair_supplement_2026_09_11/candidate_before_command_contract_fix/engineering_audit_logs/uv_frozen_offline_check.stdout.log`、对应 stderr。环境覆盖和真实执行文件身份见本节回执。

### git_diff_check — exit 0

UTC：2026-09-11T14:49:50.063902+00:00 至 2026-09-11T14:49:50.082042+00:00。

```bash
git diff --check -- . ':(exclude)benchmarks/structure_two/engineering_trust_checkpoint_2026_09_11_v0_2/engineering_audit_logs/*.log'
```

实际原始日志：`benchmarks/structure_two/evidence_repair_supplement_2026_09_11/candidate_before_command_contract_fix/engineering_audit_logs/git_diff_check.stdout.log`、对应 stderr。环境覆盖和真实执行文件身份见本节回执。

## 最终原生工程矩阵

回执 content SHA：`ce51f3f93096d04b8f02584e58a7307ce9a188fd0f20852ce6dee1e26b3b5c79`。

### p5_evidence_current — exit 0

UTC：2026-09-11T15:24:57.058603+00:00 至 2026-09-11T15:37:26.214769+00:00。

```bash
.venv/bin/python apps/evaluation_runner/run_structure_two_evidence_repair.py --verify-current
```

实际原始日志：`benchmarks/structure_two/engineering_trust_checkpoint_2026_09_11_v0_2/engineering_audit_logs/p5_evidence_current.stdout.log`、对应 stderr。环境覆盖和真实执行文件身份见本节回执。

### p5_evidence_history — exit 0

UTC：2026-09-11T15:24:57.059520+00:00 至 2026-09-11T15:31:06.013344+00:00。

```bash
.venv/bin/python apps/evaluation_runner/audit_structure_two_evidence_history.py --verify benchmarks/structure_two/evidence_repair_supplement_2026_09_11/historical_source_audit_v0_2.json
```

实际原始日志：`benchmarks/structure_two/engineering_trust_checkpoint_2026_09_11_v0_2/engineering_audit_logs/p5_evidence_history.stdout.log`、对应 stderr。环境覆盖和真实执行文件身份见本节回执。

### p0_adversarial_tests — exit 0

UTC：2026-09-11T15:37:26.215884+00:00 至 2026-09-11T15:37:31.577459+00:00。

```bash
.venv/bin/pytest -o addopts= -q --confcutdir=. tests/test_structure_two_trusted_ablation_authorization.py tests/test_structure_two_gate_b_v0_8_raw_formal_execution.py tests/test_structure_two_comparator_typed_dual_gate_b_v0_8.py tests/test_p0_checkpoint_manifest.py
```

实际原始日志：`benchmarks/structure_two/engineering_trust_checkpoint_2026_09_11_v0_2/engineering_audit_logs/p0_adversarial_tests.stdout.log`、对应 stderr。环境覆盖和真实执行文件身份见本节回执。

### core_pytest — exit 0

UTC：2026-09-11T15:37:31.577898+00:00 至 2026-09-11T16:03:03.641469+00:00。

```bash
.venv/bin/pytest -o addopts= -p xdist.plugin -n auto --dist=worksteal -q --confcutdir=. --ignore=tests/test_structure_two_engineering_trust_checkpoint.py
```

实际原始日志：`benchmarks/structure_two/engineering_trust_checkpoint_2026_09_11_v0_2/engineering_audit_logs/core_pytest.stdout.log`、对应 stderr。环境覆盖和真实执行文件身份见本节回执。

### mypy_src — exit 0

UTC：2026-09-11T16:03:03.644172+00:00 至 2026-09-11T16:03:03.884290+00:00。

```bash
.venv/bin/mypy src
```

实际原始日志：`benchmarks/structure_two/engineering_trust_checkpoint_2026_09_11_v0_2/engineering_audit_logs/mypy_src.stdout.log`、对应 stderr。环境覆盖和真实执行文件身份见本节回执。

### ruff_lint — exit 0

UTC：2026-09-11T16:03:03.895660+00:00 至 2026-09-11T16:03:03.919713+00:00。

```bash
.venv/bin/ruff check src tests apps
```

实际原始日志：`benchmarks/structure_two/engineering_trust_checkpoint_2026_09_11_v0_2/engineering_audit_logs/ruff_lint.stdout.log`、对应 stderr。环境覆盖和真实执行文件身份见本节回执。

### ruff_format — exit 0

UTC：2026-09-11T16:03:03.929282+00:00 至 2026-09-11T16:03:03.941236+00:00。

```bash
.venv/bin/ruff format --check src tests apps
```

实际原始日志：`benchmarks/structure_two/engineering_trust_checkpoint_2026_09_11_v0_2/engineering_audit_logs/ruff_format.stdout.log`、对应 stderr。环境覆盖和真实执行文件身份见本节回执。

### compileall — exit 0

UTC：2026-09-11T16:03:03.941657+00:00 至 2026-09-11T16:03:04.030159+00:00。

```bash
.venv/bin/python -m compileall -q src apps tests
```

实际原始日志：`benchmarks/structure_two/engineering_trust_checkpoint_2026_09_11_v0_2/engineering_audit_logs/compileall.stdout.log`、对应 stderr。环境覆盖和真实执行文件身份见本节回执。

### uv_frozen_offline_check — exit 0

UTC：2026-09-11T16:03:04.050840+00:00 至 2026-09-11T16:03:04.102539+00:00。

```bash
uv sync --frozen --offline --check --extra dev --no-cache
```

实际原始日志：`benchmarks/structure_two/engineering_trust_checkpoint_2026_09_11_v0_2/engineering_audit_logs/uv_frozen_offline_check.stdout.log`、对应 stderr。环境覆盖和真实执行文件身份见本节回执。

### git_diff_check — exit 0

UTC：2026-09-11T16:03:04.103050+00:00 至 2026-09-11T16:03:04.120094+00:00。

```bash
git diff --check -- . ':(exclude)benchmarks/structure_two/engineering_trust_checkpoint_2026_09_11_v0_2/engineering_audit_logs/*.log'
```

实际原始日志：`benchmarks/structure_two/engineering_trust_checkpoint_2026_09_11_v0_2/engineering_audit_logs/git_diff_check.stdout.log`、对应 stderr。环境覆盖和真实执行文件身份见本节回执。

## staged_diff_before_catalog_cleanup — exit 2

```bash
git diff --cached --check 91dbdc57968071be29976d1a7b99de51d9288cdd
```

stdout: `benchmarks/structure_two/evidence_repair_supplement_2026_09_11/validation_logs/staged_diff_before_catalog_cleanup.stdout.log.gz`；stderr: `benchmarks/structure_two/evidence_repair_supplement_2026_09_11/validation_logs/staged_diff_before_catalog_cleanup.stderr.log.gz`。


## staged_branch_diff_final — exit 0

```bash
git diff --cached --check 91dbdc57968071be29976d1a7b99de51d9288cdd
```

stdout: `benchmarks/structure_two/evidence_repair_supplement_2026_09_11/validation_logs/staged_branch_diff_final.stdout.log.gz`；stderr: `benchmarks/structure_two/evidence_repair_supplement_2026_09_11/validation_logs/staged_branch_diff_final.stderr.log.gz`。
