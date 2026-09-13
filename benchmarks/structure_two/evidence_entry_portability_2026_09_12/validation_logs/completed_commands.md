# 窗口一实际执行命令与原始日志

工作树 `/private/tmp/cpswm-s2-evidence-repair-window1`；Python 3.13.5；源码提交 `05c78af2a38e07e0171c5352bf4ab9b9da3124d2`。

以下为完整命令账本中的 26 条已结束记录。两项开发失败、旧检查点预期拒绝均保留。不要把嵌套运行或重复复核叠加成独立测试总数；计时为 wrapper 单调时钟秒数。

每条命令实际由同目录 run_logged.py 记录器运行；重新执行时需选择未使用的日志名。生成命令只允许发布新版本，不应直接重跑覆盖已封存文件。完整复现建议在独立来源副本中为新产物选择独立版本路径。

## before_reproductions

exit `1`；1.032 秒；UTC `2026-09-11T18:20:25.687072+00:00` → `2026-09-11T18:20:26.719820+00:00`。

```sh
.venv/bin/python benchmarks/structure_two/evidence_entry_portability_2026_09_12/validation_logs/reproduce_before.py
```

- [stdout](before_reproductions.stdout.log.gz)，解压 SHA-256 `cbaa26836ebc23d2bf0d3bda355fe6a706dfcfd779e7a2ecd49af01f050b308d`。
- [stderr](before_reproductions.stderr.log.gz)，解压 SHA-256 `9f44be8cc27055d31fe518b1d60f2081a72ed6b78e56f0847d1ed775e6e336b3`。

## before_reproductions_complete

exit `0`；161.943 秒；UTC `2026-09-11T18:20:37.959412+00:00` → `2026-09-11T18:23:19.903822+00:00`。

```sh
.venv/bin/python benchmarks/structure_two/evidence_entry_portability_2026_09_12/validation_logs/reproduce_before.py
```

- [stdout](before_reproductions_complete.stdout.log.gz)，解压 SHA-256 `e0d50e22c540d0e70cfba628cd1eca0120eefc36429e62a276db1529187a5c33`。
- [stderr](before_reproductions_complete.stderr.log.gz)，解压 SHA-256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`。

## entry_cache_corrected_regressions

exit `0`；12.074 秒；UTC `2026-09-11T18:28:03.914095+00:00` → `2026-09-11T18:28:15.987923+00:00`。

```sh
.venv/bin/pytest -o addopts= -q -n 8 --dist=worksteal --confcutdir=. tests/test_structure_two_entry_portability.py -k 'not full_history'
```

- [stdout](entry_cache_corrected_regressions.stdout.log.gz)，解压 SHA-256 `5ee4cc53ca288f0ba2467644fd6b229cf3e59f911fdbd802085d65c7b95c062b`。
- [stderr](entry_cache_corrected_regressions.stderr.log.gz)，解压 SHA-256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`。

## preserve_reviewed

exit `0`；3.836 秒；UTC `2026-09-11T18:29:47.282709+00:00` → `2026-09-11T18:29:51.119143+00:00`。

```sh
.venv/bin/python benchmarks/structure_two/evidence_entry_portability_2026_09_12/validation_logs/preserve_reviewed.py
```

- [stdout](preserve_reviewed.stdout.log.gz)，解压 SHA-256 `363a75be59f6c34c90a8ecff271a03d0c1a1b15a8743f890a403e27c4f16bc27`。
- [stderr](preserve_reviewed.stderr.log.gz)，解压 SHA-256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`。

## after_entry_reproductions

exit `0`；11.844 秒；UTC `2026-09-11T18:32:47.776536+00:00` → `2026-09-11T18:32:59.620838+00:00`。

```sh
.venv/bin/python benchmarks/structure_two/evidence_entry_portability_2026_09_12/validation_logs/reproduce_after_entry.py
```

- [stdout](after_entry_reproductions.stdout.log.gz)，解压 SHA-256 `01d6976c65fc4154fd74848cc5285c17ef7416afb3e22ee9e310e8c031988456`。
- [stderr](after_entry_reproductions.stderr.log.gz)，解压 SHA-256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`。

## entry_history_regressions

exit `1`；641.496 秒；UTC `2026-09-11T18:26:26.111941+00:00` → `2026-09-11T18:37:07.552131+00:00`。

```sh
.venv/bin/pytest -o addopts= -q -n 8 --dist=worksteal --confcutdir=. tests/test_structure_two_evidence_supplement.py tests/test_structure_two_entry_portability.py
```

- [stdout](entry_history_regressions.stdout.log.gz)，解压 SHA-256 `7452767208257417975a2c8b0b31d83bc3466f1a234f1893eabe92c32aa5c11c`。
- [stderr](entry_history_regressions.stderr.log.gz)，解压 SHA-256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`。

## original79_plus36_regressions

exit `0`；1455.899 秒；UTC `2026-09-11T18:29:09.086964+00:00` → `2026-09-11T18:53:24.926591+00:00`。

```sh
.venv/bin/pytest -o addopts= -q -s -n 8 --dist=worksteal --confcutdir=. tests/test_structure_two_evidence_versions.py tests/test_structure_two_evidence_supplement.py tests/test_structure_two_entry_portability.py
```

- [stdout](original79_plus36_regressions.stdout.log.gz)，解压 SHA-256 `845772d48a324ef28e091c4a20e763f93de82ea04786858afec23471e68bc4ba`。
- [stderr](original79_plus36_regressions.stderr.log.gz)，解压 SHA-256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`。

## cross_root_full_raw

exit `0`；1341.850 秒；UTC `2026-09-11T18:33:40.043036+00:00` → `2026-09-11T18:56:01.831189+00:00`。

```sh
.venv/bin/python -c 'import runpy,tempfile; from pathlib import Path; test=runpy.run_path('"'"'tests/test_structure_two_entry_portability.py'"'"'); test['"'"'test_full_history_replay_and_report_verification_across_roots'"'"'](Path(tempfile.mkdtemp(prefix='"'"'w1-cross-root-full-'"'"',dir='"'"'/private/tmp'"'"')))'
```

- [stdout](cross_root_full_raw.stdout.log.gz)，解压 SHA-256 `8ca4e97a6e5784927deb691297617dcc1408b444371bfe49921b1c2503032adf`。
- [stderr](cross_root_full_raw.stderr.log.gz)，解压 SHA-256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`。

## generate_five_v04

exit `0`；1865.047 秒；UTC `2026-09-11T18:53:26.415034+00:00` → `2026-09-11T19:24:31.452293+00:00`。

```sh
.venv/bin/python apps/evaluation_runner/run_structure_two_evidence_repair.py --generate-current
```

- [stdout](generate_five_v04.stdout.log.gz)，解压 SHA-256 `cacff1c5c799744509e22c33ddedde1cddcb62cce18c8deab5885fa4eab0211c`。
- [stderr](generate_five_v04.stderr.log.gz)，解压 SHA-256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`。

## verify_five_v04

exit `0`；763.265 秒；UTC `2026-09-11T19:24:31.489599+00:00` → `2026-09-11T19:37:18.590588+00:00`。

```sh
.venv/bin/python apps/evaluation_runner/run_structure_two_evidence_repair.py --verify-current
```

- [stdout](verify_five_v04.stdout.log.gz)，解压 SHA-256 `cacff1c5c799744509e22c33ddedde1cddcb62cce18c8deab5885fa4eab0211c`。
- [stderr](verify_five_v04.stderr.log.gz)，解压 SHA-256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`。

## generate_history_v03

exit `0`；152.033 秒；UTC `2026-09-11T19:37:18.635289+00:00` → `2026-09-11T19:39:56.388174+00:00`。

```sh
.venv/bin/python apps/evaluation_runner/audit_structure_two_evidence_history.py --recompute-first-failure --recompute-failed-replay --output benchmarks/structure_two/evidence_entry_portability_2026_09_12/historical_source_audit_v0_3.json
```

- [stdout](generate_history_v03.stdout.log.gz)，解压 SHA-256 `070c541651641a0e5da22b59d7a10be8935efbd5546921c3def56a220d4d66f3`。
- [stderr](generate_history_v03.stderr.log.gz)，解压 SHA-256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`。

## verify_history_v03

exit `0`；153.817 秒；UTC `2026-09-11T19:39:56.408394+00:00` → `2026-09-11T19:42:33.665182+00:00`。

```sh
.venv/bin/python apps/evaluation_runner/audit_structure_two_evidence_history.py --verify benchmarks/structure_two/evidence_entry_portability_2026_09_12/historical_source_audit_v0_3.json
```

- [stdout](verify_history_v03.stdout.log.gz)，解压 SHA-256 `21e61dfa96fc2e8d8f12fe8c3436461069c166f4726c9c62c7e7c407521a9daa`。
- [stderr](verify_history_v03.stderr.log.gz)，解压 SHA-256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`。

## aggregate_history_v03

exit `0`；153.514 秒；UTC `2026-09-11T19:42:33.686142+00:00` → `2026-09-11T19:45:11.729132+00:00`。

```sh
.venv/bin/python apps/evaluation_runner/run_structure_two_evidence_repair.py --verify-history
```

- [stdout](aggregate_history_v03.stdout.log.gz)，解压 SHA-256 `1088a3bb41f5b8d6b72a3066af8385d17cd58e65871b7cec1168ffed512132bb`。
- [stderr](aggregate_history_v03.stderr.log.gz)，解压 SHA-256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`。

## v05_compatibility

exit `0`；0.522 秒；UTC `2026-09-11T19:45:11.749675+00:00` → `2026-09-11T19:45:12.271676+00:00`。

```sh
.venv/bin/python apps/evaluation_runner/audit_structure_two_world_source_bundle_v0_5.py
```

- [stdout](v05_compatibility.stdout.log.gz)，解压 SHA-256 `5e0fec6879ac42086431c90957154e794a53010286ec5a40909e99ec03c0117c`。
- [stderr](v05_compatibility.stderr.log.gz)，解压 SHA-256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`。

## preservation_and_scientific_equality

exit `0`；1.452 秒；UTC `2026-09-11T19:45:12.291902+00:00` → `2026-09-11T19:45:13.743517+00:00`。

```sh
.venv/bin/python benchmarks/structure_two/evidence_entry_portability_2026_09_12/validation_logs/check_preservation_and_semantics.py
```

- [stdout](preservation_and_scientific_equality.stdout.log.gz)，解压 SHA-256 `e0864729b8dd3563e2e3e03d3dc89f94224aa1030cd0971e15e524381e1e53fe`。
- [stderr](preservation_and_scientific_equality.stderr.log.gz)，解压 SHA-256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`。

## generate_p0

exit `0`；0.190 秒；UTC `2026-09-11T19:45:13.762768+00:00` → `2026-09-11T19:45:13.952795+00:00`。

```sh
.venv/bin/python apps/evaluation_runner/generate_p0_checkpoint_manifest.py
```

- [stdout](generate_p0.stdout.log.gz)，解压 SHA-256 `e03bb2e3e5796298728e2d73926c9a145f88d794020158cf5633edc646357184`。
- [stderr](generate_p0.stderr.log.gz)，解压 SHA-256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`。

## native_engineering_audit

exit `0`；2321.691 秒；UTC `2026-09-11T19:45:13.972625+00:00` → `2026-09-11T20:26:49.741435+00:00`。

```sh
.venv/bin/python apps/evaluation_runner/run_structure_two_engineering_audit_receipt.py
```

- [stdout](native_engineering_audit.stdout.log.gz)，解压 SHA-256 `d6303432cad8f49d2298b4891a893bab089121ac58bb371f2c03250c994cada4`。
- [stderr](native_engineering_audit.stderr.log.gz)，解压 SHA-256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`。

## host_sandbox_and_known_xfail

exit `0`；15.252 秒；UTC `2026-09-12T04:41:46.613724+00:00` → `2026-09-12T04:42:01.865899+00:00`。

```sh
.venv/bin/pytest -o addopts= -q -rsx --confcutdir=. tests/test_structure_two_sealed_dual_gate_b_v1_0.py::test_real_sandbox_ten_arm_receipts_bind_full_support_and_deny_opening_bytes tests/test_project_one_same_context_rls_ablation.py::test_shipped_wiring_shuffling_costs_real_discrimination
```

- [stdout](host_sandbox_and_known_xfail.stdout.log.gz)，解压 SHA-256 `8157002a32de00b73e2537937168e21062c6555a463b65df416cbdeb83d9bf51`。
- [stderr](host_sandbox_and_known_xfail.stderr.log.gz)，解压 SHA-256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`。

## generate_fresh_checkpoint

exit `0`；499.094 秒；UTC `2026-09-12T04:42:28.467009+00:00` → `2026-09-12T04:50:47.546201+00:00`。

```sh
.venv/bin/python apps/evaluation_runner/generate_structure_two_engineering_trust_checkpoint.py
```

- [stdout](generate_fresh_checkpoint.stdout.log.gz)，解压 SHA-256 `b5a40dd4f18e0f8170e8d04a6768e1938945139ae4d2b6ff513f24e07ca009b2`。
- [stderr](generate_fresh_checkpoint.stderr.log.gz)，解压 SHA-256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`。

## checkpoint_adversarial_regressions

exit `0`；10.736 秒；UTC `2026-09-12T04:51:09.270233+00:00` → `2026-09-12T04:51:20.006204+00:00`。

```sh
.venv/bin/pytest -o addopts= -q --confcutdir=. tests/test_structure_two_engineering_trust_checkpoint.py
```

- [stdout](checkpoint_adversarial_regressions.stdout.log.gz)，解压 SHA-256 `a6d6fc6ebfcecabeba873c1c1fb8e55e1a45c4b6877bba710160110007d430c1`。
- [stderr](checkpoint_adversarial_regressions.stderr.log.gz)，解压 SHA-256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`。

## final_preservation_and_semantics

exit `0`；2.241 秒；UTC `2026-09-12T04:55:06.343932+00:00` → `2026-09-12T04:55:08.584584+00:00`。

```sh
.venv/bin/python benchmarks/structure_two/evidence_entry_portability_2026_09_12/validation_logs/check_preservation_and_semantics.py
```

- [stdout](final_preservation_and_semantics.stdout.log.gz)，解压 SHA-256 `e0864729b8dd3563e2e3e03d3dc89f94224aa1030cd0971e15e524381e1e53fe`。
- [stderr](final_preservation_and_semantics.stderr.log.gz)，解压 SHA-256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`。

## verify_fresh_checkpoint

exit `0`；509.725 秒；UTC `2026-09-12T04:50:55.601670+00:00` → `2026-09-12T04:59:25.323864+00:00`。

```sh
.venv/bin/python apps/evaluation_runner/generate_structure_two_engineering_trust_checkpoint.py --verify benchmarks/structure_two/engineering_trust_checkpoint_2026_09_12_v0_3/engineering_checkpoint.json
```

- [stdout](verify_fresh_checkpoint.stdout.log.gz)，解压 SHA-256 `841ed045590a7850bfab37034ceb25f1a1a754f2d636bef3ba88d7c5c4ff5a16`。
- [stderr](verify_fresh_checkpoint.stderr.log.gz)，解压 SHA-256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`。

## final_checkpoint_currentness

exit `0`；1.717 秒；UTC `2026-09-12T04:59:48.292001+00:00` → `2026-09-12T04:59:50.009394+00:00`。

```sh
.venv/bin/python apps/evaluation_runner/generate_structure_two_engineering_trust_checkpoint.py --verify benchmarks/structure_two/engineering_trust_checkpoint_2026_09_12_v0_3/engineering_checkpoint.json --no-fresh-recomputation
```

- [stdout](final_checkpoint_currentness.stdout.log.gz)，解压 SHA-256 `841ed045590a7850bfab37034ceb25f1a1a754f2d636bef3ba88d7c5c4ff5a16`。
- [stderr](final_checkpoint_currentness.stderr.log.gz)，解压 SHA-256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`。

## reject_reviewed_checkpoint_as_current

exit `1`；1.729 秒；UTC `2026-09-12T04:59:48.292045+00:00` → `2026-09-12T04:59:50.021430+00:00`。

```sh
.venv/bin/python apps/evaluation_runner/generate_structure_two_engineering_trust_checkpoint.py --verify benchmarks/structure_two/engineering_trust_checkpoint_2026_09_11_v0_2/engineering_checkpoint.json --no-fresh-recomputation
```

- [stdout](reject_reviewed_checkpoint_as_current.stdout.log.gz)，解压 SHA-256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`。
- [stderr](reject_reviewed_checkpoint_as_current.stderr.log.gz)，解压 SHA-256 `136b1edd5454b768c928c7aea881920dc253b615a43f14efd0d366f87975108f`。

## final_log_integrity

exit `0`；0.030 秒；UTC `2026-09-12T05:00:07.152257+00:00` → `2026-09-12T05:00:07.182643+00:00`。

```sh
.venv/bin/python benchmarks/structure_two/evidence_entry_portability_2026_09_12/validation_logs/check_log_integrity.py
```

- [stdout](final_log_integrity.stdout.log.gz)，解压 SHA-256 `d3018adf1303220483c8b94af47a3d642a4a753f36bfdd1951aa9ad2d3bf74f8`。
- [stderr](final_log_integrity.stderr.log.gz)，解压 SHA-256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`。

## post_format_boundary_check

exit `0`；3.525 秒；UTC `2026-09-12T05:03:36.422523+00:00` → `2026-09-12T05:03:39.947672+00:00`。

```sh
.venv/bin/python -c '
import ast
import hashlib
import subprocess
import tarfile
from pathlib import Path
base = Path('"'"'benchmarks/structure_two/evidence_entry_portability_2026_09_12/validation_logs'"'"')
with tarfile.open(base/'"'"'executed_helper_sources_before_format.tar.gz'"'"') as archive:
    members = archive.getmembers()
    assert len(members) == 7
    for member in members:
        old = ast.parse(archive.extractfile(member).read())
        new = ast.parse((base/member.name).read_bytes())
        def body(tree):
            return ast.dump(ast.Module(body=[n for n in tree.body if not isinstance(n, (ast.Import, ast.ImportFrom))], type_ignores=[]))
        assert body(old) == body(new), member.name
print('"'"'7 executed helper originals preserved; non-import AST exact'"'"', flush=True)
assert not subprocess.check_output(['"'"'git'"'"','"'"'diff'"'"','"'"'HEAD'"'"','"'"'--'"'"','"'"'src'"'"','"'"'apps'"'"','"'"'tests'"'"','"'"'configs'"'"','"'"'conftest.py'"'"'])
commands = [
    ['"'"'.venv/bin/ruff'"'"','"'"'check'"'"',str(base)],
    ['"'"'.venv/bin/ruff'"'"','"'"'format'"'"','"'"'--check'"'"',str(base)],
    ['"'"'.venv/bin/python'"'"',str(base/'"'"'check_preservation_and_semantics.py'"'"')],
    ['"'"'.venv/bin/python'"'"',str(base/'"'"'check_log_integrity.py'"'"')],
    ['"'"'.venv/bin/python'"'"','"'"'apps/evaluation_runner/generate_structure_two_engineering_trust_checkpoint.py'"'"','"'"'--verify'"'"','"'"'benchmarks/structure_two/engineering_trust_checkpoint_2026_09_12_v0_3/engineering_checkpoint.json'"'"','"'"'--no-fresh-recomputation'"'"'],
]
for command in commands:
    subprocess.run(command, check=True)
path=Path('"'"'benchmarks/structure_two/engineering_trust_checkpoint_2026_09_12_v0_3/engineering_checkpoint.json'"'"')
assert hashlib.sha256(path.read_bytes()).hexdigest() == '"'"'8a657e219807d68eed4b6a4e8150d1aef4464e74aee6cab59ede2cc99f898793'"'"'
print('"'"'Bound source/tests, P0, receipt, checkpoint unchanged; only unbound helper formatting changed'"'"', flush=True)
'
```

- [stdout](post_format_boundary_check.stdout.log.gz)，解压 SHA-256 `aea7f94bb78c6fb38fd94cf9c6bcb7de6b1f1a7b4d88da995fa515dba892a5fe`。
- [stderr](post_format_boundary_check.stderr.log.gz)，解压 SHA-256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`。

## 原生工程审计矩阵

下列 10 条命令是 native_engineering_audit 的实际嵌套执行，不另外累加为外层命令数。路径、实际环境和可执行文件绑定见 engineering_audit_receipt.json。

### p5_evidence_current (exit 0)

```sh
.venv/bin/python apps/evaluation_runner/run_structure_two_evidence_repair.py --verify-current
```

UTC `2026-09-11T19:45:14.635915+00:00` → `2026-09-11T19:57:43.055963+00:00`。

stdout: `benchmarks/structure_two/engineering_trust_checkpoint_2026_09_12_v0_3/engineering_audit_logs/p5_evidence_current.stdout.log`；stderr: `benchmarks/structure_two/engineering_trust_checkpoint_2026_09_12_v0_3/engineering_audit_logs/p5_evidence_current.stderr.log`。

### p5_evidence_history (exit 0)

```sh
.venv/bin/python apps/evaluation_runner/audit_structure_two_evidence_history.py --verify benchmarks/structure_two/evidence_entry_portability_2026_09_12/historical_source_audit_v0_3.json
```

UTC `2026-09-11T19:45:14.636708+00:00` → `2026-09-11T19:50:38.835109+00:00`。

stdout: `benchmarks/structure_two/engineering_trust_checkpoint_2026_09_12_v0_3/engineering_audit_logs/p5_evidence_history.stdout.log`；stderr: `benchmarks/structure_two/engineering_trust_checkpoint_2026_09_12_v0_3/engineering_audit_logs/p5_evidence_history.stderr.log`。

### p0_adversarial_tests (exit 0)

```sh
.venv/bin/pytest -o addopts= -q --confcutdir=. tests/test_structure_two_trusted_ablation_authorization.py tests/test_structure_two_gate_b_v0_8_raw_formal_execution.py tests/test_structure_two_comparator_typed_dual_gate_b_v0_8.py tests/test_p0_checkpoint_manifest.py
```

UTC `2026-09-11T19:57:43.056839+00:00` → `2026-09-11T19:57:48.909298+00:00`。

stdout: `benchmarks/structure_two/engineering_trust_checkpoint_2026_09_12_v0_3/engineering_audit_logs/p0_adversarial_tests.stdout.log`；stderr: `benchmarks/structure_two/engineering_trust_checkpoint_2026_09_12_v0_3/engineering_audit_logs/p0_adversarial_tests.stderr.log`。

### core_pytest (exit 0)

```sh
.venv/bin/pytest -o addopts= -p xdist.plugin -n auto --dist=worksteal -q --confcutdir=. --ignore=tests/test_structure_two_engineering_trust_checkpoint.py
```

UTC `2026-09-11T19:57:48.909805+00:00` → `2026-09-11T20:26:48.502664+00:00`。

stdout: `benchmarks/structure_two/engineering_trust_checkpoint_2026_09_12_v0_3/engineering_audit_logs/core_pytest.stdout.log`；stderr: `benchmarks/structure_two/engineering_trust_checkpoint_2026_09_12_v0_3/engineering_audit_logs/core_pytest.stderr.log`。

### mypy_src (exit 0)

```sh
.venv/bin/mypy src
```

UTC `2026-09-11T20:26:48.507243+00:00` → `2026-09-11T20:26:48.887088+00:00`。

stdout: `benchmarks/structure_two/engineering_trust_checkpoint_2026_09_12_v0_3/engineering_audit_logs/mypy_src.stdout.log`；stderr: `benchmarks/structure_two/engineering_trust_checkpoint_2026_09_12_v0_3/engineering_audit_logs/mypy_src.stderr.log`。

### ruff_lint (exit 0)

```sh
.venv/bin/ruff check src tests apps
```

UTC `2026-09-11T20:26:48.899095+00:00` → `2026-09-11T20:26:48.915460+00:00`。

stdout: `benchmarks/structure_two/engineering_trust_checkpoint_2026_09_12_v0_3/engineering_audit_logs/ruff_lint.stdout.log`；stderr: `benchmarks/structure_two/engineering_trust_checkpoint_2026_09_12_v0_3/engineering_audit_logs/ruff_lint.stderr.log`。

### ruff_format (exit 0)

```sh
.venv/bin/ruff format --check src tests apps
```

UTC `2026-09-11T20:26:48.925616+00:00` → `2026-09-11T20:26:48.935433+00:00`。

stdout: `benchmarks/structure_two/engineering_trust_checkpoint_2026_09_12_v0_3/engineering_audit_logs/ruff_format.stdout.log`；stderr: `benchmarks/structure_two/engineering_trust_checkpoint_2026_09_12_v0_3/engineering_audit_logs/ruff_format.stderr.log`。

### compileall (exit 0)

```sh
.venv/bin/python -m compileall -q src apps tests
```

UTC `2026-09-11T20:26:48.935889+00:00` → `2026-09-11T20:26:49.047218+00:00`。

stdout: `benchmarks/structure_two/engineering_trust_checkpoint_2026_09_12_v0_3/engineering_audit_logs/compileall.stdout.log`；stderr: `benchmarks/structure_two/engineering_trust_checkpoint_2026_09_12_v0_3/engineering_audit_logs/compileall.stderr.log`。

### uv_frozen_offline_check (exit 0)

```sh
uv sync --frozen --offline --check --extra dev --no-cache
```

UTC `2026-09-11T20:26:49.068501+00:00` → `2026-09-11T20:26:49.118532+00:00`。

stdout: `benchmarks/structure_two/engineering_trust_checkpoint_2026_09_12_v0_3/engineering_audit_logs/uv_frozen_offline_check.stdout.log`；stderr: `benchmarks/structure_two/engineering_trust_checkpoint_2026_09_12_v0_3/engineering_audit_logs/uv_frozen_offline_check.stderr.log`。

### git_diff_check (exit 0)

```sh
git diff --check -- . ':(exclude)benchmarks/structure_two/engineering_trust_checkpoint_2026_09_12_v0_3/engineering_audit_logs/*.log'
```

UTC `2026-09-11T20:26:49.120090+00:00` → `2026-09-11T20:26:49.134374+00:00`。

stdout: `benchmarks/structure_two/engineering_trust_checkpoint_2026_09_12_v0_3/engineering_audit_logs/git_diff_check.stdout.log`；stderr: `benchmarks/structure_two/engineering_trust_checkpoint_2026_09_12_v0_3/engineering_audit_logs/git_diff_check.stderr.log`。
