# 命令、退出码与执行源码索引

以下为已执行命令原记录；每份 command.json 还包含运行目录、解释器、耗时及源码前后摘要。原非零退出完整保留。脚本运行后仅为通过仓库格式检查产生格式化副本；executed_script_manifest.json 指向实际执行时的精确脚本字节（.py.source.txt），不把格式化副本哈希冒作旧执行哈希。外部独立审核脚本未修改。

## cancellation_lineage_matrix.command.json

```sh
/Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/.venv/bin/python -m pytest -o addopts= -q -n 4 -p no:cacheprovider --junitxml=/private/tmp/cpswm-pc-a-w3-backbone-r7-20260912/docs/reviews/pc_a/w3_backbone_r7_2026-09-12/cancellation_lineage_matrix.xml tests/test_structure_two_w3_deferred_cancellation.py tests/test_structure_two_w3_round5_boundaries.py
```

退出码：0；完整记录：cancellation_lineage_matrix.command.json

## cancellation_parent_matrix.command.json

```sh
/Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/.venv/bin/python -m pytest -o addopts= -q -n 4 -p no:cacheprovider --junitxml=/private/tmp/cpswm-pc-a-w3-backbone-r7-20260912/docs/reviews/pc_a/w3_backbone_r7_2026-09-12/cancellation_parent_matrix.xml tests/test_structure_two_w3_deferred_cancellation.py
```

退出码：0；完整记录：cancellation_parent_matrix.command.json

## cancellation_preflight.command.json

```sh
/Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/.venv/bin/python -m pytest -o addopts= -q -n 4 -p no:cacheprovider --junitxml=/private/tmp/cpswm-pc-a-w3-backbone-r7-20260912/docs/reviews/pc_a/w3_backbone_r7_2026-09-12/cancellation_preflight.xml tests/test_structure_two_w3_deferred_cancellation.py
```

退出码：1；完整记录：cancellation_preflight.command.json

## continuous_final_base.command.json

```sh
/Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/.venv/bin/python docs/reviews/pc_a/w3_backbone_r7_2026-09-12/continuous_connections.py base docs/reviews/pc_a/w3_backbone_r7_2026-09-12/continuous_final_base.json
```

退出码：0；完整记录：continuous_final_base.command.json

## continuous_final_ciav.command.json

```sh
/Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/.venv/bin/python docs/reviews/pc_a/w3_backbone_r7_2026-09-12/continuous_connections.py ciav docs/reviews/pc_a/w3_backbone_r7_2026-09-12/continuous_final_ciav.json
```

退出码：0；完整记录：continuous_final_ciav.command.json

## continuous_final_identity.command.json

```sh
/Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/.venv/bin/python docs/reviews/pc_a/w3_backbone_r7_2026-09-12/continuous_connections.py identity docs/reviews/pc_a/w3_backbone_r7_2026-09-12/continuous_final_identity.json
```

退出码：0；完整记录：continuous_final_identity.command.json

## continuous_final_null.command.json

```sh
/Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/.venv/bin/python docs/reviews/pc_a/w3_backbone_r7_2026-09-12/continuous_connections.py null docs/reviews/pc_a/w3_backbone_r7_2026-09-12/continuous_final_null.json
```

退出码：0；完整记录：continuous_final_null.command.json

## continuous_final_opceu.command.json

```sh
/Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/.venv/bin/python docs/reviews/pc_a/w3_backbone_r7_2026-09-12/continuous_connections.py opceu docs/reviews/pc_a/w3_backbone_r7_2026-09-12/continuous_final_opceu.json
```

退出码：0；完整记录：continuous_final_opceu.command.json

## continuous_final_orrer.command.json

```sh
/Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/.venv/bin/python docs/reviews/pc_a/w3_backbone_r7_2026-09-12/continuous_connections.py orrer docs/reviews/pc_a/w3_backbone_r7_2026-09-12/continuous_final_orrer.json
```

退出码：0；完整记录：continuous_final_orrer.command.json

## continuous_final_pchmp.command.json

```sh
/Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/.venv/bin/python docs/reviews/pc_a/w3_backbone_r7_2026-09-12/continuous_connections.py pchmp docs/reviews/pc_a/w3_backbone_r7_2026-09-12/continuous_final_pchmp.json
```

退出码：0；完整记录：continuous_final_pchmp.command.json

## final_812.command.json

```sh
/Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/.venv/bin/python -m pytest -o addopts= -q -n 4 -p no:cacheprovider --junitxml=/private/tmp/cpswm-pc-a-w3-backbone-r7-20260912/docs/reviews/pc_a/w3_backbone_r7_2026-09-12/final_812.xml tests/test_structure_two_backbone_operator_wiring.py tests/test_core_prototype_spine.py tests/test_structure_two_production_system.py tests/test_structure_two_execution_interface.py tests/test_structure_two_adaptive_runtime.py tests/test_structure_two_adaptive_runtime_adversarial_round1.py tests/test_structure_two_adaptive_runtime_adversarial_round2.py tests/test_structure_two_p5_direct_trace_probe.py tests/test_structure_two_p5_debt_replay_confirmation.py tests/test_structure_two_backbone_counterexample_regressions.py tests/test_structure_two_late_counter_evidence_chain.py tests/test_structure_two_operator_causal_matrix.py tests/test_structure_two_ciav_negative_observation_layers.py tests/test_structure_two_p0_maintenance_fault_injection.py tests/test_structure_two_formal_revision_lineage.py tests/test_structure_two_operator_coverage_matrix.py tests/test_structure_two_w3_revision_acceptance.py tests/test_structure_two_w3_operator_acceptance.py tests/test_structure_two_w3_supplement.py tests/test_project_two_feedback_revision_loop.py tests/test_project_two_revision_action_trace.py tests/test_orrer_event_revision.py tests/test_ccrr_context_conditioned_regime.py tests/test_hybrid_ledger_durable_log.py tests/test_project_one_automatic_regime_loop.py tests/test_structure_two_w3_round5_boundaries.py tests/test_structure_two_w3_native_bundle.py tests/test_structure_two_w3_native_particles.py tests/test_project_two_action_readout.py tests/test_structure_two_w3_round6_prepared_boundary.py tests/test_structure_two_selected_method.py tests/test_structure_two_particle_falsifier.py tests/test_structure_two_neural_amortized.py tests/test_structure_two_stateful_full_joint.py tests/test_structure_two_stateful_full_joint_adversarial.py tests/test_structure_two_task7_support_recovery.py tests/test_structure_two_w3_native_posterior_projection.py tests/test_structure_two_w3_deferred_cancellation.py
```

退出码：0；完整记录：final_812.command.json

## independent_final_cancellation.command.json

```sh
/Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/.venv/bin/python /private/tmp/cpswm-pc-a-w3-backbone-r7-20260912/docs/reviews/pc_a/w3_backbone_r7_2026-09-12/cancellation_probe.py /private/tmp/cpswm-pc-a-w3-backbone-r7-20260912
```

退出码：0；完整记录：independent_final_cancellation.command.json

## independent_final_round4.command.json

```sh
/Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/.venv/bin/python /Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/docs/reviews/data/structure_two_three_windows_round4_review_2026-09-12/w3_new_boundary_probes.py /private/tmp/cpswm-pc-a-w3-backbone-r7-20260912
```

退出码：0；完整记录：independent_final_round4.command.json

## independent_final_round5.command.json

```sh
/Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/.venv/bin/python /Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/docs/reviews/data/structure_two_three_windows_round5_review_2026-09-12/w3_independent_prepared_probes.py /private/tmp/cpswm-pc-a-w3-backbone-r7-20260912
```

退出码：0；完整记录：independent_final_round5.command.json

## model_before_50.command.json

```sh
/Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/.venv/bin/python -m pytest -o addopts= -q -n 4 -p no:cacheprovider --junitxml=/private/tmp/cpswm-pc-a-w3-backbone-r7-20260912/docs/reviews/pc_a/w3_backbone_r7_2026-09-12/model_before_50.xml tests/test_structure_two_selected_method.py tests/test_structure_two_particle_falsifier.py tests/test_structure_two_neural_amortized.py tests/test_structure_two_stateful_full_joint.py tests/test_structure_two_stateful_full_joint_adversarial.py tests/test_structure_two_task7_support_recovery.py
```

退出码：1；完整记录：model_before_50.command.json

## model_restored_50.command.json

```sh
/Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/.venv/bin/python -m pytest -o addopts= -q -n 4 -p no:cacheprovider --junitxml=/private/tmp/cpswm-pc-a-w3-backbone-r7-20260912/docs/reviews/pc_a/w3_backbone_r7_2026-09-12/model_restored_50.xml tests/test_structure_two_selected_method.py tests/test_structure_two_particle_falsifier.py tests/test_structure_two_neural_amortized.py tests/test_structure_two_stateful_full_joint.py tests/test_structure_two_stateful_full_joint_adversarial.py tests/test_structure_two_task7_support_recovery.py
```

退出码：0；完整记录：model_restored_50.command.json

## projection_canonical_sets.command.json

```sh
/Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/.venv/bin/python -m pytest -o addopts= -q -n 4 -p no:cacheprovider --junitxml=/private/tmp/cpswm-pc-a-w3-backbone-r7-20260912/docs/reviews/pc_a/w3_backbone_r7_2026-09-12/projection_canonical_sets.xml tests/test_structure_two_w3_native_posterior_projection.py tests/test_structure_two_w3_round6_prepared_boundary.py tests/test_structure_two_w3_native_particles.py
```

退出码：0；完整记录：projection_canonical_sets.command.json

## projection_hashseed_fixed.command.json

```sh
/Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/.venv/bin/python -m pytest -o addopts= -q -n 4 -p no:cacheprovider --junitxml=/private/tmp/cpswm-pc-a-w3-backbone-r7-20260912/docs/reviews/pc_a/w3_backbone_r7_2026-09-12/projection_hashseed_fixed.xml tests/test_structure_two_w3_native_posterior_projection.py tests/test_structure_two_w3_round6_prepared_boundary.py
```

退出码：1；完整记录：projection_hashseed_fixed.command.json

## projection_preflight.command.json

```sh
/Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/.venv/bin/python -m pytest -o addopts= -q -n 4 -p no:cacheprovider --junitxml=/private/tmp/cpswm-pc-a-w3-backbone-r7-20260912/docs/reviews/pc_a/w3_backbone_r7_2026-09-12/projection_preflight.xml tests/test_structure_two_w3_native_posterior_projection.py tests/test_structure_two_w3_native_particles.py tests/test_structure_two_w3_round6_prepared_boundary.py
```

退出码：0；完整记录：projection_preflight.command.json

## projection_regression_714.command.json

```sh
/Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/.venv/bin/python -m pytest -o addopts= -q -n 4 -p no:cacheprovider --junitxml=/private/tmp/cpswm-pc-a-w3-backbone-r7-20260912/docs/reviews/pc_a/w3_backbone_r7_2026-09-12/projection_regression_714.xml tests/test_structure_two_backbone_operator_wiring.py tests/test_core_prototype_spine.py tests/test_structure_two_production_system.py tests/test_structure_two_execution_interface.py tests/test_structure_two_adaptive_runtime.py tests/test_structure_two_adaptive_runtime_adversarial_round1.py tests/test_structure_two_adaptive_runtime_adversarial_round2.py tests/test_structure_two_p5_direct_trace_probe.py tests/test_structure_two_p5_debt_replay_confirmation.py tests/test_structure_two_backbone_counterexample_regressions.py tests/test_structure_two_late_counter_evidence_chain.py tests/test_structure_two_operator_causal_matrix.py tests/test_structure_two_ciav_negative_observation_layers.py tests/test_structure_two_p0_maintenance_fault_injection.py tests/test_structure_two_formal_revision_lineage.py tests/test_structure_two_operator_coverage_matrix.py tests/test_structure_two_w3_revision_acceptance.py tests/test_structure_two_w3_operator_acceptance.py tests/test_structure_two_w3_supplement.py tests/test_project_two_feedback_revision_loop.py tests/test_project_two_revision_action_trace.py tests/test_orrer_event_revision.py tests/test_ccrr_context_conditioned_regime.py tests/test_hybrid_ledger_durable_log.py tests/test_project_one_automatic_regime_loop.py tests/test_structure_two_w3_round5_boundaries.py tests/test_structure_two_w3_native_bundle.py tests/test_structure_two_w3_native_particles.py tests/test_project_two_action_readout.py tests/test_structure_two_w3_round6_prepared_boundary.py
```

退出码：0；完整记录：projection_regression_714.command.json

## projection_typed_final.command.json

```sh
/Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/.venv/bin/python -m pytest -o addopts= -q -n 4 -p no:cacheprovider --junitxml=/private/tmp/cpswm-pc-a-w3-backbone-r7-20260912/docs/reviews/pc_a/w3_backbone_r7_2026-09-12/projection_typed_final.xml tests/test_structure_two_w3_native_posterior_projection.py tests/test_structure_two_w3_round6_prepared_boundary.py
```

退出码：1；完整记录：projection_typed_final.command.json

## continuous_final_openworld

```sh
/Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/.venv/bin/python docs/reviews/pc_a/w3_backbone_r7_2026-09-12/continuous_connections_openworld.py openworld docs/reviews/pc_a/w3_backbone_r7_2026-09-12/continuous_final_openworld.json
```

退出码：0。真实输入/输出、脚本摘要、源码前后摘要及 completed=true 均在 continuous_final_openworld.json。

## 最终验证范围

final_812.command.json 是最终 812 项的精确命令，TEST_SUMMARY.json 按原组统计。final_ruff.txt、cancellation_mypy.txt 保留格式/静态检查输出。git diff --check 最终退出 0。模型恢复前的 17 项失败/错误、两次投影集合序列化失败、取消开发失败及错误汇总断言退出 1 全部保留；旧日志不重写。

## 环境与移植

测试使用主仓库 .venv/bin/python（Python 3.13.5）；没有把 macOS 虚拟环境拷贝给 Windows。每次 pytest 使用新 PYTHONPYCACHEPREFIX，OPENBLAS_NUM_THREADS/OMP_NUM_THREADS/MKL_NUM_THREADS=1，关闭默认 addopts，xdist 4 worker。Windows 独立复现需要按项目依赖重建解释器；本机通过不等于 Windows 复现。
