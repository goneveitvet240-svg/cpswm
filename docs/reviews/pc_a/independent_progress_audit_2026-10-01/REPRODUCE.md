# 本轮独立复核的实际入口

受审最新交付 b6c6317a35c99cd95fe636251ce1e63bfba5f402；本机审核目录 `/private/tmp/cpswm-pc-a-independent-progress-audit-20261001`。以下命令均在该目录执行。复用 `/private/tmp/cpswm-pc-a-camera-checkpoint-fixture-20260930/.venv/bin/python`，没有重建环境或新增 Unity 采集。后续复核请保留本次原件，在新审核输出目录保存新日志。

## 定向测试和失败复现

```sh
PYTHONPATH=src:tests:tools OPENBLAS_NUM_THREADS=1 /private/tmp/cpswm-pc-a-camera-checkpoint-fixture-20260930/.venv/bin/python -m pytest -q -o addopts='' tests/test_instance_affinity.py tests/test_instance_affinity_controls.py tests/test_instance_affinity_dataset.py tests/test_soft_surface_position.py tests/test_position_observation_model.py tests/test_native_position_production.py tests/test_native_raw_candidate_verification.py tests/test_native_log_weight_continuation.py tests/test_owned_position_delivery.py tests/test_archive_native_bridge.py tests/test_bare_seed_development.py
```

11 文件、356 passed；包含两个依赖完整子进程路径才通过的测试。为复现 CI 路径问题，另实际执行：

```sh
PYTHONPATH=src /private/tmp/cpswm-pc-a-camera-checkpoint-fixture-20260930/.venv/bin/python -m pytest -q -o addopts='' tests/test_native_raw_candidate_verification.py -k 'fresh_process_resume_without_constructing_another_stream or non_neural_collection_keeps_torch_optional'

PYTHONPATH=src:tests:tools OPENBLAS_NUM_THREADS=1 /private/tmp/cpswm-pc-a-camera-checkpoint-fixture-20260930/.venv/bin/python -m pytest -q -o addopts='' tests/test_structure_two_w3_round6_prepared_boundary.py -k unresolved_underflow
```

两次均为2 failed，分别为子进程模块导入失败、旧下溢拒绝断言不再触发。均退出码1；不要把它们与前面的通过数相抵或删掉。类型检查命令是：

```sh
PYTHONPATH=src OPENBLAS_NUM_THREADS=1 /private/tmp/cpswm-pc-a-camera-checkpoint-fixture-20260930/.venv/bin/python -m mypy src --cache-dir /private/tmp/cpswm-independent-mypy-cache-20261001
```

实际结果为155 errors / 12 files，389 source files checked，退出码1，见 local-mypy.log。GitHub 当前同一 SHA 的完整检查原件为 current-ci.json/current-ci-failed.log，摘要ci-summary.json；取得入口为 `gh run view 36783640567 --json headSha,status,conclusion,jobs,url` 和该 run 的 `--log-failed`。

## 独立算术与完整原件再运行

[recompute-results.py.txt](evidence/recompute-results.py.txt)只用 NumPy/SciPy 和标准库，不调用生产 fit/predict/condition/report。脚本验证固定 case-ledger 外部摘要及输出清单，重算全部三模式预测、六种位置误差与训练矩，以及四模型 Native 后验数值。输入是已绑定的特征/公开世界点，不扩大为重新提取原始视觉或新采集验证。结果为 independent-math.json。

[verify-bridge.py.txt](evidence/verify-bridge.py.txt)读取并严格 pin 原 PR79 四次运行 ledger，选择原 bridge verify 的实际 argv；不修改其中输入路径或原输出。先核对旧源码901文件与冻结清单以及本次当前源码对应文件逐字一致，再在 `/private/tmp/cpswm-pc-a-archive-native-bridge-20261001` 原源码执行只读完整 `--verify`。它会重新拟合历史父模型、重跑四模型/八臂以及新进程恢复，并在副本上复核原 SQLite。903文件当前最新功能比该901集合多出的两文件为 owner descriptor 及测试，另由当前356项测试覆盖。

完整命令、cwd、退出码、耗时及原76产物是否保持，在 bridge-independent-full-verify.json；日志同目录。脚本的历史来源与当前来源检查不能被省略。原复现链的 Mac SDK/runtime 绑定仍存在，不宣称复制 argv 到 Windows 就可执行。

两个审核脚本以 `.py.txt` 保存在文档目录，避免改变被绑定的 src/tests/tools Python 全集。它们写入脚本所在审核证据目录，输入只用于读取。独立复核、历史工具自带校验、受控测试和科学结果分别记录。
