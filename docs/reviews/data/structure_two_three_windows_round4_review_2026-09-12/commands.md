# 本轮实际复核命令

日期 2026-09-12。工作树为审核前固定的副本，窗口三叠加交付修改后的 src/tests 与 manifest 的 558 文件逐字节相同。以下命令未修改原实现。日志保存 tool 返回的输出片段及最终退出码/测试总数，不声称所有文件都是进程启动以来逐字完整终端日志。

## 窗口一

工作目录 `/private/tmp/s2-review4-w1.p5JONv`。

```sh
PYTHONPATH=src /Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/.venv/bin/python apps/evaluation_runner/run_structure_two_evidence_repair.py --verify-current
PYTHONPATH=src /Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/.venv/bin/python -m pytest -o addopts='' -q -p no:cacheprovider tests/test_structure_two_entry_portability.py tests/test_structure_two_evidence_supplement.py
```

本轮36个新用例中的完整历史测试在真实目录 A/B 执行生成、验证、源替换后拒绝，输出根：`/private/var/folders/x2/000r8p0n6s393lj2sg8wk5f40000gn/T/pytest-of-pangwei/pytest-1662/test_full_history_replay_and_r0`。

原工作目录 `/private/tmp/cpswm-s2-evidence-repair-window1`，保持封存原生环境：

```sh
env -u PYTHONPATH .venv/bin/python apps/evaluation_runner/generate_structure_two_engineering_trust_checkpoint.py --verify benchmarks/structure_two/engineering_trust_checkpoint_2026_09_12_v0_3/engineering_checkpoint.json --no-fresh-recomputation
```

首次少传 --verify 的值，argparse exit 2；上式更正后 exit 0。该命令没有 fresh 重算，不计作新生成检查点。

## 窗口二

工作目录 `/private/tmp/s2-review4-w2.pdinJv`。

```sh
S2_AUDIT_BUNDLE=/private/tmp/s2-review4-w2.pdinJv/docs/reviews/data/structure_two_comparison_audit_window2_fairness_2026-09-12/bundle_v4 PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/.venv/bin/python -m pytest -o addopts='' -p xdist.plugin -n 4 -q -p no:cacheprovider tests/test_structure_two_comparison_audit.py tests/test_structure_two_comparison_audit_verification.py tests/test_structure_two_comparison_audit_execution_source.py tests/test_structure_two_comparison_fairness.py
```

58 passed。新六类完整伪造与真实合法包同批执行，批退出1是预期拒绝，不是测试失败。完整原始矩阵位置记录于 `w2_fairness_forgery_matrix.json`（本目录文件是标明省略模块清单的紧凑摘录）。

## 窗口三

工作目录 `/private/tmp/s2-review4-w3.cwwAVs`。均使用主工作树的同一个原生 Python。

```sh
PYTHONPATH=src /Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/.venv/bin/python -m pytest -o addopts='' -q -p no:cacheprovider tests/test_structure_two_w3_revision_acceptance.py tests/test_structure_two_w3_operator_acceptance.py tests/test_structure_two_w3_supplement.py
PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/.venv/bin/python -m pytest -o addopts='' -q -p xdist.plugin -n 4 -p no:cacheprovider tests/test_structure_two_backbone_operator_wiring.py tests/test_core_prototype_spine.py tests/test_structure_two_production_system.py tests/test_structure_two_execution_interface.py tests/test_structure_two_adaptive_runtime.py tests/test_structure_two_adaptive_runtime_adversarial_round1.py tests/test_structure_two_adaptive_runtime_adversarial_round2.py tests/test_structure_two_p5_direct_trace_probe.py tests/test_structure_two_p5_debt_replay_confirmation.py tests/test_structure_two_backbone_counterexample_regressions.py tests/test_structure_two_late_counter_evidence_chain.py tests/test_structure_two_operator_causal_matrix.py tests/test_structure_two_ciav_negative_observation_layers.py tests/test_structure_two_p0_maintenance_fault_injection.py tests/test_structure_two_formal_revision_lineage.py tests/test_structure_two_operator_coverage_matrix.py
PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/.venv/bin/python -m pytest -o addopts='' -q -p no:cacheprovider tests/test_project_two_feedback_revision_loop.py tests/test_project_two_revision_action_trace.py tests/test_orrer_event_revision.py tests/test_ccrr_context_conditioned_regime.py tests/test_hybrid_ledger_durable_log.py
PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/.venv/bin/python -m pytest -o addopts='' -q -p xdist.plugin -n 4 -p no:cacheprovider tests/test_project_one_automatic_regime_loop.py
```

分别 105、252、82、44 passed，各组不合成完整系统通过。

主工作目录 `/Users/pangwei/Documents/ai/continual-personalized-semantic-world-model`：

```sh
.venv/bin/python docs/reviews/data/structure_two_three_windows_review_2026-09-12/w3_additional_probes.py /private/tmp/s2-review4-w3.cwwAVs
.venv/bin/python docs/reviews/data/structure_two_three_windows_review_2026-09-12/w3_journal_oracle_probe.py /private/tmp/s2-review4-w3.cwwAVs
.venv/bin/python docs/reviews/data/structure_two_three_windows_round4_review_2026-09-12/w3_new_boundary_probes.py /private/tmp/s2-review4-w3.cwwAVs
.venv/bin/python docs/reviews/data/structure_two_three_windows_round4_review_2026-09-12/w3_new_boundary_probes.py /private/tmp/s2-review3-w3.UygOrM direct_revision
.venv/bin/python docs/reviews/data/structure_two_three_windows_round4_review_2026-09-12/verify_snapshot.py
.venv/bin/python docs/reviews/data/structure_two_three_windows_round4_review_2026-09-12/verify_preservation.py
```

新反例脚本以 JSON 如实记录不满足的后置条件，本身 exit 0 不表示被测系统通过；请检查 oracle_accepts_unchanged_corrected_state、after_semantic_equal、new_committed 等实际字段。三个原窗口与主工作树旧证据均未修复、合并或推送；新增临时审核副本保留以便复查。
