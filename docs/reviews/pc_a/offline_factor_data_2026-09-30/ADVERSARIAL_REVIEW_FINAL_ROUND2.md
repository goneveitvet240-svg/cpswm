# 冻结候选第二轮对抗审查：存在阻塞项

- 审查绑定 SHA：`f5c1f638816a60bddacb769e84ac43c44a1c914a`。
- 工作树：`/private/tmp/cpswm-pc-a-offline-factor-data-20260930`；审查前后 `git status --short` 为空，未改源码。
- 顺序：此前第一轮已完成，报告 `ADVERSARIAL_REVIEW_FINAL_ROUND1.md`；本轮针对同一 SHA 开始第二轮。
- 角色：A 组辅助对抗审查，不是 B 独立复核；没有启动实际 Unity，也没有训练模型。
- **结论：第二轮未通过。发现并完整复现 R2-01：采集任务时间窗口与其原始公共事件时间未绑定，完整重算哈希后仍能获得完整资产审计与目标资格。修复、重新冻结并重新顺序完成两轮审查之前，不能将该候选记为两轮通过。**

## R2-01：任务时间与原始事件时间脱离，仍授予下游资格

位置：`tools/collect_offline_factor_data.py:161`，`validate_attempt_states()` 当前仅验证开始／结束为 UTC、结束不早于开始，以及房屋之间不倒序；没有要求已验证公共事件属于其对应 attempt 时间区间。`runtime_partition_audit()` 在同一函数返回后将全部 verified 状态计为完整矩阵并生成目标资格。

完整复现使用真实的 manifest 构建／重建逻辑、`OfflineFactorRecorder`、公共 RGB-D 构造与 StateCodec、逐帧 `verify_capture()`、整批 `collect()`／`verify_collection()`／`runtime_partition_audit()`。替身仅用于：受控压缩包的可信源 pin、模拟 SDK 事件和进程、runtime 描述与进程信号；没有替换实际逐帧 verifier、分区资格判定或整批归档重算。此受控夹具不宣称来自官方自然房屋或真实 Unity。

1. 构造十二屋完整正路径，每屋 8 帧、12 个 SDK 事件：共 **96 帧、144 个 SDK 事件、24 个源与运行时一致且资产互异的实例**。
2. 首先运行真实整批核验，得到完整资产审计和 24 个 eligible 实例，证明合法正路径并非被全部关闭。
3. 保留全部 RGB-D、相机、掩膜、对象、scope、action ID、公共 decision/capture/receipt 时间、验证摘要及 `exit_code=0`；仅将每个 attempt 的开始／结束整体提前 3650 天。十二项仍为完整、有序、UTC、无失败字段。
4. **重新计算整个 inventory** 后调用真实 `verify_collection()`。
5. 攻击被接受：`complete_asset_exposure_audit=true`，**24 个实例仍 eligible**。记录中第一任务开始为 `2016-10-02T13:50:40.044121+00:00`，其第一公共 capture 为 `2026-09-30T13:50:40.075396+00:00`。

这是归档内部已经足以判断的因果矛盾，不依赖外部引擎真实性证明。后果是与该次任务窗口不相容的事件仍能获得“本次完整采集／可进入后续数据门禁”的资格；并未运行训练或真实导出监督。

建议：逐帧重建摘要保留来自公开原件的 `decision_time`、`capture_time` 和 `received_at`，对成功任务强制 `started_at <= decision_time <= capture_time <= received_at <= finished_at`，并保留帧间 receipt 不晚于下一 decision 的约束。修复测试应同时包含正常完整组合档案、合法失败矩阵、整体迁移 attempt 年代以及单端点越界的完整重哈希攻击；不能通过删除失败矩阵复核路径来解决。

## 已执行验证

完整复跑四个工具对应的五个新增测试文件：

```sh
PYTHONPATH=src:tests:tools /private/tmp/cpswm-pc-a-camera-checkpoint-fixture-20260930/.venv/bin/python -m pytest -q -o addopts='' tests/test_offline_factor_manifest.py tests/test_offline_factor_worker.py tests/test_offline_factor_capture_verifier.py tests/test_offline_factor_collection.py tests/test_offline_factor_orchestration.py
```

结果：**102 passed in 4.07s，退出 0，无 skip**。九个相关 Python 文件的 Ruff check 同样通过。日志：`final-round2-tests.log`。

独立组合探针：

```sh
PYTHONPATH=src:tests:tools /private/tmp/cpswm-pc-a-camera-checkpoint-fixture-20260930/.venv/bin/python /private/tmp/offline_round2_probe.py
```

探针副本：`final-round2-composed-probe.py`；结果：`final-round2-composed-probe.log`。该脚本退出 0 表示完成攻击观察，其中明确存在被错误接受的 R2-01，不能把退出 0 解释为审查通过。

| 场景 | 实际结果与后果 |
| --- | --- |
| 完整十二屋正路径，全部原始帧／事件与分区重算 | 接受；96 帧、144 事件、24 eligible；无训练和监督导出 |
| 完整归档中伪造 training/export 已完成并重算 inventory | `saved partition audit differs from recomputation`，拒绝 |
| 完整归档中整体迁移 attempt 时间年代并重算 inventory | **错误接受；完整标记和 24 个目标资格保留，构成 R2-01** |
| 保留完整文件但替换同事件 owner，再重算 inventory | `SDK action trace differs from fixed protocol`，拒绝 |
| 恢复原件后重新整批核验 | 合法完整正路径再次通过 |

已有 102 项复跑还覆盖：共享资产仅删训练标签仍不能获得验证资格、运行时生成／未知资产关闭相关或全局资格、源与 SDK 资产／位置变化隔离、不可见实例遗漏、完整公共 packet 重新生成 hash/receipt 后换 depth/camera/provenance、跨屋 scope/action 重放、失败／超时／非零退出／清理失败保留，以及源码／运行时变更阻止继续派发。它们与本次新增组合探针互补；没有将只测 helper 的覆盖冒充真实 SDK 运行结果。

## 实际 SDK 可运行性检查及剩余范围

只读检查当前已安装 AI2-THOR `controller.py`：程序化 reset 最终执行 `CreateHouse` 并返回该 `last_event`（约 731–741 行）；Unity 子进程的 `Popen` 未另起 session（约 1132 行），因此由 collector 创建的子进程组可以包含 SDK 及 Unity 后代。这支持当前事件0与进程清理设计的接口假设。

用实际 SDK Python 成功导入 `offline_factor_manifest` 和 `unity_offline_factor_worker`，输出 `SDK_INTERPRETER_IMPORT_OK`，Python `3.11.16`。这仅是 Python／依赖导入兼容性；没有启动 Unity，不证明十二个官方房屋都能创建，也不证明实际 SDK 掩膜、未知资产、相机初始化／静止容差满足本协议。

保留以下边界：

- 原始官方 TRAIN 压缩包 pin、固定 index 划分、原始 house 字节、全场景资产表是来源与数据隔离门禁；本轮探针使用的是明确声明的受控源，不能充当自然数据结果。
- 实际目录若有未知资产，整批资格会关闭。不得为增加通过数而跳过未知对象、遗漏失败房屋或替换房屋。
- 同机哈希、完整重算及本轮伪造攻击仍不是外部独立真实性验收；整体伪造引擎输出、真实标签误差与独立人审标签不在已完成范围。
- 尚未采集本轮真实数据，尚未训练／拟合自然实例或位置因子，尚未证明闭环收益。

下一步为修复 R2-01，绑定新的完整 SHA，再顺序进行两轮审查；本报告应保留，不被新报告覆盖为通过。
