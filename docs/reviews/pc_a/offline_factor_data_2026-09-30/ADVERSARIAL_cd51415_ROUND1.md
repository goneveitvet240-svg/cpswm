# cd51415：修复时间归属后的第一轮影响审查

- 冻结 SHA：`cd51415ced36b16f2e7ebcb743fdda5ca8a9b7ab`。
- 工作树：`/private/tmp/cpswm-pc-a-offline-factor-data-20260930`；审查前后干净，未编辑源码，未启动仿真。
- 身份：A 组只读对抗审查，不是 B 独立验收。
- 范围：审查 `f5c1f638816a60bddacb769e84ac43c44a1c914a..cd51415ced36b16f2e7ebcb743fdda5ca8a9b7ab` 的全部变更，并重跑全部新增链路测试与两条独立临时攻击脚本。
- 结论：**本轮范围内未发现新阻塞项。旧非零退出攻击保持拒绝；新增时间归属攻击被拒绝。可在同一 SHA 上顺序启动第二轮，尚不能宣称两轮已完成或真实采集通过。**

历史 `ADVERSARIAL_ROUND1.md`、`ADVERSARIAL_REVIEW_FINAL_ROUND1.md` 及第二轮发现均保留。本报告不倒填旧 SHA 的验收结论。

## 修复影响

`verify_capture()` 现在从实际解码的公开 `ObservationCommand`、`CameraSelfPose` 和 `ObservationDelivery` 生成每帧 `decision_time`、`capture_time`、`received_at`。这些字段来自公开原件，不从 attempts 摘要或私有标签回填。

`verify_collection()` 仍将保存的 verification 与重建结果完整比较，随后 `runtime_partition_audit()` 要求每帧满足：

```text
attempt.started_at <= previous_frame.received_at <= decision_time
                  <= capture_time <= received_at <= attempt.finished_at
```

首帧 previous 取 owning attempt 的开始时间。三种帧时间都必须为明确 UTC。原有固定八帧、全局作用域/动作 ID 防重、各 attempt 起止与跨房屋因果顺序保持生效。因此，把所有 attempt 时间一致平移而不改变公开原件，不再能获得完整通过。

## 执行结果

```sh
/private/tmp/cpswm-pc-a-camera-checkpoint-fixture-20260930/.venv/bin/python -m pytest -q -o addopts='' tests/test_offline_factor_manifest.py tests/test_offline_factor_worker.py tests/test_offline_factor_capture_verifier.py tests/test_offline_factor_collection.py tests/test_offline_factor_orchestration.py
```

**105 passed in 3.43s，退出 0，无 skip。** 合法完整矩阵、四类采集失败保留路径、带失败房屋的归档重建正路径继续通过；新增完整重算 inventory 的十年整体平移、开始晚于公开决策、结束早于公开接收三类攻击均被拒绝。

未改动旧 R1 攻击脚本，执行：

```sh
PYTHONPATH=src:tests:tools /private/tmp/cpswm-pc-a-camera-checkpoint-fixture-20260930/.venv/bin/python /private/tmp/offline_round1_probe.py
```

**预期拒绝，退出 1**：`ValueError: verified attempt state contradicts process outcome`。日志：`cd51415-round1-original-forgery-rejected.log`。

新增独立临时脚本先创建完整合法受控矩阵，并实际调用 `verify_collection()` 确认正路径完整通过；再将十二项起止时间统一提前 3650 天，保留各项内部和跨项顺序及所有公开原件，完整重算 inventory，重新调用生产归档复核：

```sh
PYTHONPATH=src:tests:tools /private/tmp/cpswm-pc-a-camera-checkpoint-fixture-20260930/.venv/bin/python /private/tmp/offline_round1_interval_probe.py
```

**预期拒绝，退出 1**：`ValueError: frame times differ from owning attempt state interval`。日志：`cd51415-round1-interval-forgery-rejected.log`。失败落在实际时间归属检查，不是由于文件缺失、重算不完整或构造正路径失败。

两个临时复现均使用仓库已检入的 `ControlledMatrix`：进程、运行时、单房屋数据核验采用受控替身，生产 `collect()`、`verify_collection()` 与 `runtime_partition_audit()` 不替换。因此证据是完整状态机/归档协议边界验证，不是自然数据或真实 SDK 运行结果。

## 剩余边界

未执行真实十二房屋采集，未训练/校准自然因子。SDK 缺失资产导致资格关闭、真实目标覆盖不足和初始化失败仍需按固定清单原样保留。同机归档一致性不解决整套公开与私有原件一起被伪造的外部 custody 问题。两次攻击脚本的退出 1 是拒绝证据，不能计为真实采集成功。

下一步为同一 `cd51415ced36b16f2e7ebcb743fdda5ca8a9b7ab` 的第二轮审查；源码变化则需重新冻结并审核。
