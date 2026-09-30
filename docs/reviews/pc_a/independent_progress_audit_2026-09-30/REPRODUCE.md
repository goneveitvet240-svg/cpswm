# 本轮独立审核复现记录

受审交付 `d698792a8e3750af284a2c991a28aff2453b0729`，独立工作目录 `/private/tmp/cpswm-pc-a-independent-progress-audit-20260930`。以下为本机实际环境，不声称已在新机器重建；原始完整数据及绑定环境的恢复见 [PR73 复现说明](../offline_factor_data_2026-09-30/REPRODUCE.md)和 [PR74 复现说明](../offline_frontend_2026-09-30/REPRODUCE.md)。

使用 `/private/tmp/cpswm-pc-a-camera-checkpoint-fixture-20260930/.venv/bin/python`，保留该虚拟环境入口，不把它 resolve 成基础 Python。Python 3.13.5，torch 2.13.0，torchvision 0.28.0；运行从受审工作目录启动，`PYTHONPATH=src:tests:tools`。诊断 CLI 设置 torch 两线程。

## 实际运行

```sh
PYTHONPATH=src:tests:tools /private/tmp/cpswm-pc-a-camera-checkpoint-fixture-20260930/.venv/bin/python -m pytest -q -o addopts='' tests/test_offline_frontend_diagnostic.py tests/test_offline_frontend_evaluation.py tests/test_surface_factor_diagnostic.py tests/test_offline_factor_manifest.py tests/test_offline_factor_worker.py tests/test_offline_factor_capture_verifier.py tests/test_offline_factor_collection.py tests/test_offline_factor_orchestration.py tests/test_offline_factor_asset_provenance.py

PYTHONPATH=src:tests:tools /private/tmp/cpswm-pc-a-camera-checkpoint-fixture-20260930/.venv/bin/python -m pytest -q -o addopts='' tests/test_unity_rgbd.py tests/test_owned_rgbd_support.py tests/test_owned_visual_neural.py tests/test_camera_policy_identifiability_artifacts.py

PYTHONPATH=src:tests:tools /private/tmp/cpswm-pc-a-camera-checkpoint-fixture-20260930/.venv/bin/python -m pytest -q -o addopts='' tests/test_p0_checkpoint_manifest.py::test_p0_checkpoint_v0_3_is_current_and_self_consistent
```

结果依次为 231 passed、79 passed、1 failed。P0 失败是已保存的审核发现，不是复现应该跳过的检查。

[rerun.py.txt](evidence/rerun.py.txt)读取原四次命令中的两个 verify 命令，在本审核源码工作目录重新运行；全部 argv、退出码、时间和来源一致性在 [independent-inference.json](evidence/independent-inference.json)。该命令会完整读回历史采集数据并完成每个前端全部 96 帧实际推理，没有再调用 Unity 启动采集。

[recompute.py.txt](evidence/recompute.py.txt)只用标准库和 NumPy，直接读取原分割图/掩膜/SDK，独立检查摘要、交集、采样成员、距离与相机位置/航向。它没有导入生产评价/汇总实现。所有与原始文件不一致都会使断言失败；描述性结果在 [independent-raw-recomputation.json](evidence/independent-raw-recomputation.json)。脚本以 `.py.txt` 保存，避免改变原诊断的 Python 源文件全集绑定。

两个脚本均会写各自所在证据目录内的结果文件。以后重新审核时复制到新的审核目录运行，保留本次原记录。输入文件为只读用途。

## 远端状态

开工与结束均 fetch origin，受审前端 d698、新计划 c8c、共享集成 19dd、B fd4c 未变，完整 SHA 在 [audit-metadata.json](evidence/audit-metadata.json)。运行信息由 `gh run view 36652585929 --json databaseId,headSha,status,conclusion,jobs,url` 获取；失败日志由同一 run 的 `--log-failed` 获取，均已保存。

最新实际 CI 在 14409 源码结束于失败，不能用本审核文档分支或尚无全仓运行的新交付替代它。复用环境、确定性原图推理和原件算术重算的独立性有限；本次不增加独立房屋数、Unity 运行次数或长期任务成功证据。
