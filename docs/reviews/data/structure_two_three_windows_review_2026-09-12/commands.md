# 本审核复现索引

解释器：`/Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/.venv/bin/python`。
以下为本次实际命令；输出文件名带 completion 的只保存最终终端输出段。
所有临时工作树均固定到主报告中的提交；三个原窗口实现不变。

## 窗口一

工作目录 `/private/tmp/s2-review3-w1.BPdcNo`：

```sh
PYTHONPATH=src /Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/.venv/bin/python apps/evaluation_runner/run_structure_two_evidence_repair.py --verify-current
PYTHONPATH=src /Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/.venv/bin/python apps/evaluation_runner/run_structure_two_evidence_repair.py --verify-history
PYTHONPATH=src /Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/.venv/bin/python -m pytest -o addopts='' -q -p no:cacheprovider tests/test_structure_two_evidence_supplement.py tests/test_structure_two_evidence_versions.py
PYTHONPATH=src /Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/.venv/bin/python -m pytest -o addopts='' -q -p no:cacheprovider tests/test_structure_two_evidence_supplement.py
```

最后一条为新增53项的单独复核，43.98秒全部通过；与上面的79项集合重叠，不相加为132个独立用例。
两文件扩展集合最终79 passed，2073.09秒，无失败或跳过；保存的最终输出段为 `w1_targeted_tests.txt`。
检查点需匹配原环境；在 `/private/tmp/cpswm-s2-evidence-repair-window1` 使用该工作树自己的解释器：

```sh
env -u PYTHONPATH .venv/bin/python apps/evaluation_runner/generate_structure_two_engineering_trust_checkpoint.py --verify benchmarks/structure_two/engineering_trust_checkpoint_2026_09_11_v0_2/engineering_checkpoint.json --no-fresh-recomputation
```

## 窗口二

工作目录 `/private/tmp/s2-review3-w2.NPchtE`：

```sh
S2_AUDIT_BUNDLE=/private/tmp/s2-review3-w2.NPchtE/docs/reviews/data/structure_two_comparison_audit_window2_round3_2026-09-11/bundle_v3_final PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/.venv/bin/python -m pytest -o addopts='' -p xdist.plugin -n 3 -q -p no:cacheprovider tests/test_structure_two_comparison_audit.py tests/test_structure_two_comparison_audit_verification.py tests/test_structure_two_comparison_audit_execution_source.py
```

42 passed，828.33秒。测试内部启动真正的正式 CLI 子进程并保存各攻击原始输出。

## 窗口三

工作目录 `/private/tmp/s2-review3-w3.UygOrM`：

```sh
PYTHONPATH=src /Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/.venv/bin/python -m pytest -o addopts='' -q -p no:cacheprovider tests/test_structure_two_backbone_operator_wiring.py tests/test_core_prototype_spine.py tests/test_structure_two_production_system.py tests/test_structure_two_execution_interface.py tests/test_structure_two_adaptive_runtime.py tests/test_structure_two_adaptive_runtime_adversarial_round1.py tests/test_structure_two_adaptive_runtime_adversarial_round2.py tests/test_structure_two_p5_direct_trace_probe.py tests/test_structure_two_p5_debt_replay_confirmation.py tests/test_structure_two_backbone_counterexample_regressions.py tests/test_structure_two_late_counter_evidence_chain.py tests/test_structure_two_operator_causal_matrix.py tests/test_structure_two_ciav_negative_observation_layers.py tests/test_structure_two_p0_maintenance_fault_injection.py tests/test_structure_two_formal_revision_lineage.py tests/test_structure_two_operator_coverage_matrix.py
/Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/.venv/bin/python docs/reviews/data/structure_two_window3_round3_2026-09-11/round3_evidence.py .
```

252 passed，151.41秒；证据脚本 exit 0。测试全绿不覆盖本次另行发现的纠正回归。

在主工作区 `/Users/pangwei/Documents/ai/continual-personalized-semantic-world-model` 运行独立差分：

```sh
.venv/bin/python docs/reviews/data/structure_two_three_windows_review_2026-09-12/w3_additional_probes.py /private/tmp/s2-review3-w3.UygOrM
.venv/bin/python docs/reviews/data/structure_two_three_windows_review_2026-09-12/w3_additional_probes.py /private/tmp/s2-review2-w3.adyJ2U
```

最终四种纠正路径对照保存在 `w3_current_all_paths.json` / `w3_previous_all_paths.json`。
早期只含两个 legacy 纠正路径的输出也保留，没有覆盖成最终四路径结果。

## 保全和入口缓存对照

独立逐条核验窗口一保全清单19份、窗口二保全清单37份：当前字节等于指定旧 Git 字节、等于清单SHA256，零不符。

入口缓存实验只在 `/private/tmp/s2-review3-w1-entry.sdfpXd` 进行：用 apply_patch 向诊断 CLI 输出加入 `stale_entry_executed: true`，用 `py_compile.PycInvalidationMode.UNCHECKED_HASH` 正常编译，再用 apply_patch 移除该行，确认源码 `git diff --exit-code HEAD` 为0。分别用 `python -m apps.evaluation_runner.probe_structure_two_execution_source` 和 `python apps/evaluation_runner/probe_structure_two_execution_source.py` 启动；只有前者返回旧标记，两者返回相同来源 inventory。

该实验只刻画初始入口信任边界，不将诊断输出当成五类正式结果的伪造通过证据。
