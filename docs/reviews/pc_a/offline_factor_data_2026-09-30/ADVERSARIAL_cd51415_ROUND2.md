# cd51415：第二轮影响审查与完整组合回归

- 冻结 SHA：`cd51415ced36b16f2e7ebcb743fdda5ca8a9b7ab`。
- 工作树：`/private/tmp/cpswm-pc-a-offline-factor-data-20260930`；审查前后 HEAD 不变、`git status --short` 为空，未修改源码或原攻击脚本。
- 顺序：同一 SHA 的第一轮已经完成，见 `ADVERSARIAL_cd51415_ROUND1.md`；之后才开始本轮。
- 身份：A 组辅助审查，不是 B 独立复核；没有启动实际 Unity。
- **结论：本轮范围内未发现新阻塞项。R2-01 原完整组合攻击现在被明确拒绝，同时合法的完整组合路径仍通过；同一 SHA 的顺序两轮工程对抗审查已经完成，可进入固定清单的实际采集。此结论不表示真实数据、训练、校准、科学收益或全项目验收已经通过。**

历史失败报告 `ADVERSARIAL_REVIEW_FINAL_ROUND2.md` 及其原始探针／日志继续保留，不把旧 SHA 改写为通过。

## 修复影响核对

逐项检查本次变更及其与原全链路的关系：

- `verify_capture()` 的 `decision_time` 与 `received_at` 分别来自实际解码的公开 command、delivery；原 `capture_time` 来自公开 camera。没有从 attempt 摘要或私有标签复制这些时间。
- `verify_collection()` 继续将保存的 verification 与完整原件重建结果比较，伪造摘要不能绕过此门禁。
- 随后的 `runtime_partition_audit()` 对八帧逐一检查 UTC、所属任务起止范围，以及上一帧 receipt／下一帧 decision 的因果顺序。因此 R2-01 中所有 attempt 一致迁移年代的攻击也会在真实语义约束处失败。
- 固定十二项、非零退出拒绝、完整失败证据保留、跨屋 scope/action 防重、源与 SDK 资产匹配、未知资产关闭资格和训练／导出标志未被此次修复放宽。

## 运行结果

完整复跑五个新增测试文件：

```sh
PYTHONPATH=src:tests:tools /private/tmp/cpswm-pc-a-camera-checkpoint-fixture-20260930/.venv/bin/python -m pytest -q -o addopts='' tests/test_offline_factor_manifest.py tests/test_offline_factor_worker.py tests/test_offline_factor_capture_verifier.py tests/test_offline_factor_collection.py tests/test_offline_factor_orchestration.py
```

**105 passed in 3.26s，退出 0，无 skip。** 日志：`cd51415-round2-tests.log`。四个工具与五个测试文件的 Ruff check 全部通过，Ruff format check 输出 `9 files already formatted`。

原完整组合探针先与上一轮留证副本逐字节比较：

```sh
cmp /private/tmp/offline_round2_probe.py /Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/output/offline-factor-data-20260930/final-round2-composed-probe.py
```

比较成功，未改攻击脚本；随后原样运行：

```sh
PYTHONPATH=src:tests:tools /private/tmp/cpswm-pc-a-camera-checkpoint-fixture-20260930/.venv/bin/python /private/tmp/offline_round2_probe.py
```

探针退出 0，日志 `cd51415-round2-composed-probe.log` 包含以下全部结果：

| 场景 | 本轮结果 |
| --- | --- |
| 完整十二屋合法组合路径 | `BASELINE_FULL_CHAIN`：**96 帧、144 个 SDK 事件、24 eligible** |
| 修改已完成训练／导出声明、重算完整 inventory | `REJECTED_FORGED_DOWNSTREAM_AUTHORITY`：`saved partition audit differs from recomputation` |
| 将十二项 attempt 起止统一提前 3650 天，保留原件，重算完整 inventory | **`REJECTED_ATTEMPT_TIME_FORGERY`：`frame times differ from owning attempt state interval`** |
| 替换同事件 SDK owner，保留完整文件并重算 inventory | `REJECTED_SAME_EVENT_OWNERSHIP_FORGERY`：`SDK action trace differs from fixed protocol` |
| 恢复所有合法原件后再次完整核验 | `RESTORED_COMPLETE_POSITIVE_PATH` |

时间攻击现在失败的位置是实际 `runtime_partition_audit()` 的任务归属区间检查，而非缺失文件、失效 hash、测试夹具未能走到正路径或换用弱化攻击。恢复后再次通过，说明没有通过一律拒绝数据来制造安全结论。

组合探针实际运行 manifest 构建／复核、`OfflineFactorRecorder`、公共 RGB-D 构造和 StateCodec、逐帧 verifier、整批 collector／verifier／分区资格判定。受控替身仅用于源压缩包 pin、模拟 SDK 事件与进程、runtime 描述和进程信号；没有替换真实逐帧或分区审计函数。其完整正路径仍是受控工程证据，不能被计为官方自然房屋的真实采集。

## 未完成范围与下一步

- 真实 Unity 十二屋创建、初始化相机／对象静止容差、完整实例目录与未知资产覆盖尚未实测；保持固定 index，不替换失败房屋。
- 若真实 SDK 存在未知资产或源／SDK 不一致，应按现有规则保留并隔离；不得为了得到目标数量而删除未知对象或放宽源绑定。
- 本轮复用既有冻结依赖环境，未独立重建环境；A 组两轮审查不是 B 独立验收。
- 同机来源／哈希／完整重算不是外部独立真实性证明；整套引擎输出被一致替换的 custody 问题仍在明确边界之外。
- 尚未完成本轮实际数据采集，尚未训练／拟合自然实例或位置因子，也没有闭环性能结论。

下一步：在保持 `cd51415ced36b16f2e7ebcb743fdda5ca8a9b7ab` 不变的条件下按固定十二屋协议采集并保留所有结果，再对真实档案进行完整重算。若需要修改源码来处理实际失败，应保留失败证据，重新冻结并完成对应两轮审查。
