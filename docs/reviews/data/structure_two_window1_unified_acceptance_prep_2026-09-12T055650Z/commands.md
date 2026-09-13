# 本轮实际验证命令与原始日志

真实工作树 `/private/tmp/cpswm-s2-evidence-repair-window1`，匹配 Python 3.13.5。前8条对应基础实现6ae8dc2；最后3条对应最终实现 `ba816cb7c2a885f743069f6b091962b295249cb9`。共11条已结束记录，3个exit1均为预期拒绝，所有原始字节保留。没有运行统一长实验。

## 1. coordinator_regressions

exit `0`；UTC `2026-09-12T06:17:31.144834+00:00` → `2026-09-12T06:17:53.626405+00:00`。

```sh
/private/tmp/cpswm-s2-evidence-repair-window1/.venv/bin/pytest -o addopts= -q -s --confcutdir=. tests/test_structure_two_unified_acceptance.py
```

- [stdout](validation/coordinator_regressions.stdout.log)，SHA-256 `4d6d82ec04ec1d5a3c87dc55cb5700a494544b47d788d61e1f6df4fa0d623904`。
- [stderr](validation/coordinator_regressions.stderr.log)，SHA-256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`。

## 2. prepare_waiting

exit `0`；UTC `2026-09-12T06:22:11.328913+00:00` → `2026-09-12T06:22:12.991789+00:00`。

```sh
.venv/bin/python tools/structure_two_unified_acceptance.py --run-dir /private/tmp/cpswm-s2-evidence-repair-window1/docs/reviews/data/structure_two_unified_acceptance_runs/prepare_20260912T062000Z
```

- [stdout](validation/prepare_waiting.stdout.log)，SHA-256 `d841c04124db1b278df71c2751b150d827aadca5bec27cfe1eae43bc9200b76f`。
- [stderr](validation/prepare_waiting.stderr.log)，SHA-256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`。

## 3. reject_sealed_branch_outputs

exit `1`；UTC `2026-09-12T06:22:12.992055+00:00` → `2026-09-12T06:22:16.427447+00:00`。

```sh
.venv/bin/python tools/structure_two_unified_acceptance.py --run-dir /private/tmp/cpswm-s2-evidence-repair-window1/docs/reviews/data/structure_two_unified_acceptance_runs/negative_sealed_outputs_20260912T062000Z --unified-root /private/tmp/cpswm-s2-evidence-repair-window1 --expected-head 6ae8dc2f06ba4a8e16fbac9b6cfe2e6b05fee604 --expected-input-sha256 1783cdfa808d803dfeafd0d5ff73bdc79a98a7179bb091e657f11ea662928e11 --execute
```

- [stdout](validation/reject_sealed_branch_outputs.stdout.log)，SHA-256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`。
- [stderr](validation/reject_sealed_branch_outputs.stderr.log)，SHA-256 `527400a55eb7a466b3a8697049ecf7f8338ce6328e2995be0164bffe1922ee7d`。

## 4. preserved_checkpoint_not_current_after_new_test_contract

exit `1`；UTC `2026-09-12T06:22:16.428470+00:00` → `2026-09-12T06:22:17.847047+00:00`。

```sh
.venv/bin/python apps/evaluation_runner/generate_structure_two_engineering_trust_checkpoint.py --verify benchmarks/structure_two/engineering_trust_checkpoint_2026_09_12_v0_3/engineering_checkpoint.json --no-fresh-recomputation
```

- [stdout](validation/preserved_checkpoint_not_current_after_new_test_contract.stdout.log)，SHA-256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`。
- [stderr](validation/preserved_checkpoint_not_current_after_new_test_contract.stderr.log)，SHA-256 `2332f348cf0513a0a9f5744b79c11a7609b14522f5dc1faf8d3e2db12efff991`。

## 5. lint_preparation

exit `0`；UTC `2026-09-12T06:22:17.847115+00:00` → `2026-09-12T06:22:17.891630+00:00`。

```sh
.venv/bin/ruff check tools/structure_two_unified_acceptance.py tests/test_structure_two_unified_acceptance.py
```

- [stdout](validation/lint_preparation.stdout.log)，SHA-256 `82b3e6a6c090a57601d22943bd23fca9218d1031dbe5a7b754092f9a156b4f18`。
- [stderr](validation/lint_preparation.stderr.log)，SHA-256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`。

## 6. format_preparation

exit `0`；UTC `2026-09-12T06:22:17.891698+00:00` → `2026-09-12T06:22:17.904371+00:00`。

```sh
.venv/bin/ruff format --check tools/structure_two_unified_acceptance.py tests/test_structure_two_unified_acceptance.py
```

- [stdout](validation/format_preparation.stdout.log)，SHA-256 `3bc53bf3e981a98a34a852e175bf9b77af841edea74fca595d9aedcbaf9a4938`。
- [stderr](validation/format_preparation.stderr.log)，SHA-256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`。

## 7. native_offline_environment_check

exit `0`；UTC `2026-09-12T06:22:17.904419+00:00` → `2026-09-12T06:22:18.020591+00:00`。

```sh
uv sync --frozen --offline --check --extra dev --no-cache
```

- [stdout](validation/native_offline_environment_check.stdout.log)，SHA-256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`。
- [stderr](validation/native_offline_environment_check.stderr.log)，SHA-256 `3338222768f5671b81a1921e4d177b768e2e0add8850607f47a53896e11d8e5e`。

## 8. diff_check

exit `0`；UTC `2026-09-12T06:22:18.020658+00:00` → `2026-09-12T06:22:18.036685+00:00`。

```sh
git diff --check
```

- [stdout](validation/diff_check.stdout.log)，SHA-256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`。
- [stderr](validation/diff_check.stderr.log)，SHA-256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`。

## 9. coordinator_regressions_final40

exit `0`；UTC `2026-09-12T06:52:15.377217+00:00` → `2026-09-12T06:52:52.191392+00:00`。

```sh
.venv/bin/pytest -o addopts= -q -s --confcutdir=. tests/test_structure_two_unified_acceptance.py
```

- [stdout](validation/coordinator_regressions_final40.stdout.log)，SHA-256 `2cb6051d45ed6b0af6a64b6c947001575cb8ac3838cf3701f4bc6c480b6a5709`。
- [stderr](validation/coordinator_regressions_final40.stderr.log)，SHA-256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`。

## 10. prepare_final40_waiting

exit `0`；UTC `2026-09-12T06:53:52.552360+00:00` → `2026-09-12T06:53:55.845497+00:00`。

```sh
.venv/bin/python tools/structure_two_unified_acceptance.py --run-dir /private/tmp/cpswm-s2-evidence-repair-window1/docs/reviews/data/structure_two_unified_acceptance_runs/prepare_final40_20260912T065300Z
```

- [stdout](validation/prepare_final40_waiting.stdout.log)，SHA-256 `5b54da66e3076140fa676b8c1f0e817ccd85bbd8bf2c14fc63e4a44297c85acb`。
- [stderr](validation/prepare_final40_waiting.stderr.log)，SHA-256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`。

## 11. reject_sealed_outputs_final40

exit `1`；UTC `2026-09-12T06:53:55.845731+00:00` → `2026-09-12T06:53:58.600063+00:00`。

```sh
.venv/bin/python tools/structure_two_unified_acceptance.py --run-dir /private/tmp/cpswm-s2-evidence-repair-window1/docs/reviews/data/structure_two_unified_acceptance_runs/negative_sealed_outputs_final40_20260912T065300Z --unified-root /private/tmp/cpswm-s2-evidence-repair-window1 --expected-head ba816cb7c2a885f743069f6b091962b295249cb9 --expected-input-sha256 3b3ecacb849be546f9bab6666ef7fcabdec38dc1a5aa4102f1ae8706ccc28dc1 --execute
```

- [stdout](validation/reject_sealed_outputs_final40.stdout.log)，SHA-256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`。
- [stderr](validation/reject_sealed_outputs_final40.stderr.log)，SHA-256 `527400a55eb7a466b3a8697049ecf7f8338ce6328e2995be0164bffe1922ee7d`。

## 额外准备记录

最初 `.venv/bin/python -m pip freeze` exit 1，原因是此原生环境没有 pip。没有安装依赖或更改虚拟环境；实际依赖列表改由 importlib.metadata 读取，并用原生 build_execution_environment_fingerprint 核对（前后相等）。初始已审核checkpoint快速当前性exit0发生于新增测试之前，不声称重新执行完整fresh。后续新增测试使旧P0过时，所列最终命令按预期exit1。

测试开发阶段25项、35项及7项选测是探索结果，不累加到最终40项，也不代替最终完整40项原始日志。最小fixture所有子命令在测试stdout或engine_fixture_journals.tar.gz的stage argv中；各自完成不构成统一验收。

初始/最终保全比对已逐文件读实际字节与Git对象、解包后逐项相等核验，详情 preservation_and_final_checks.json；不只读取matches标志。受信边界仍是本地解释器/进程，不建立独立托管真实性。
