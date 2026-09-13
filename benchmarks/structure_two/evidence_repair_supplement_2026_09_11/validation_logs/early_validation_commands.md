# 早期验证命令补录

从本任务原始执行记录提取，未根据最终代码猜测命令。时间是工具调用记录时间，不冒充独立托管或精确的子命令开始时间。

原始四条工具调用（包含当时前置修改和验证命令）无损归档为 `early_validation_tool_calls.jsonl.gz`。

解压后 SHA-256：`138d67b430b16b846cd265f3e10d2e6d5ccef347f9dc639dc3cbefca0c5f6422`。

这些是当时开发树的调试轨迹，初次失败与后续修复均保留；最终验收以完整定向运行和原生审计矩阵为准。

## 2026-09-11T12:37:56.369Z / call_9TqUy9atgllfRhAgg7obXIb9

```bash
.venv/bin/pytest -o addopts= -q tests/test_structure_two_p5_readout_posthoc_diagnostic.py tests/test_structure_two_p5_readout_prior_factorial.py > .checkout/supplement_initial_smoke.log 2>&1
```

## 2026-09-11T12:41:24.240Z / call_a7XkxN3dEC0kcbXDSlovdWFF

```bash
.venv/bin/ruff check --fix tests/test_structure_two_evidence_supplement.py apps/evaluation_runner/probe_structure_two_execution_source.py
.venv/bin/ruff format tests/test_structure_two_evidence_supplement.py tests/test_structure_two_evidence_versions.py apps/evaluation_runner/probe_structure_two_execution_source.py apps/evaluation_runner/run_structure_two_evidence_repair.py
.venv/bin/pytest -o addopts= -q tests/test_structure_two_evidence_supplement.py > .checkout/supplement_adversarial_first.log 2>&1
```

## 2026-09-11T12:49:17.954Z / call_BRLdP7U45Mg8usuVjsrPoHjp

```bash
.venv/bin/ruff format apps tests/test_structure_two_evidence_supplement.py
.venv/bin/ruff check src tests apps
.venv/bin/mypy src > .checkout/supplement_mypy.log 2>&1
```

## 2026-09-11T12:49:38.473Z / call_vQnI1sagcpdEGMZ8kRDtWPrm

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/pytest -p xdist.plugin -n 8 -q --confcutdir=. tests/test_structure_two_evidence_supplement.py > .checkout/supplement_adversarial_second.log 2>&1
```

## 对应原始日志

- `supplement_initial_smoke.log.gz`：两份 P5 定向测试，7 项通过。
- `supplement_adversarial_first.log.gz`：41 passed、3 failed，后续修复原聚合 import 错误和攻击输入缺陷。
- `supplement_adversarial_second.log.gz`：当时的 47 项通过；随后扩充到 53 项。
- `supplement_mypy.log.gz`：当时 mypy 结果；最终完整矩阵再次执行。
