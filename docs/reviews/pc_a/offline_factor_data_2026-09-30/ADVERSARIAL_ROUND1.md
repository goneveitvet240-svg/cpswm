# 离线实例／位置数据采集：第一轮对抗审查

- 审查源码：`2a7cf9518266107ece334718ec5f53cb49480bed`。
- 工作树：`/private/tmp/cpswm-pc-a-offline-factor-data-20260930`，审查前后 `git status --short` 均为空。
- 角色：A 组只读对抗审查；不是 B 独立复核，不是实际仿真或科学收益验收。
- 范围：4 个新增采集/清单/核验工具及 5 个新增测试文件，沿公开观测、私有 SDK 事件、运行回执、划分资格的完整路径检查。
- 结论：**存在一个阻塞性状态机验收漏洞，应修复后冻结新 SHA，再重新进行两轮审查；当前 SHA 不应据此进入正式采集交付。**

## R1-01：非零退出与失败信息可同时存在于“verified”行，复核仍返回完整通过

位置：`tools/collect_offline_factor_data.py` 的 `runtime_partition_audit()` 和 `verify_collection()`。

当前 `runtime_partition_audit()` 仅按 `status == "verified"` 选取成功记录；`verify_collection()` 也仅依该字段决定是否重放原始采集核验。它们没有约束该行必须具有整数 `exit_code == 0`、没有失败/清理字段，也没有对状态和时间记录进行完整结构校验。

已实际复现：先使用仓库现有 `ControlledMatrix` 合法正路径产生 12 项完整受控采集，再把第一行改成 `status="verified"`、`exit_code=7`、`error="capture process exited 7"`，保持原始采集证据与所有成功核验字段，并重新计算完整 `inventory.json`。调用真正的 `verify_collection()` 返回：

```json
{"forged_exit_code":7,"status":"verified","complete_twelve_house_runtime_audit":true,"complete_asset_exposure_audit":true,"eligible":12}
```

这不是通过缩短输入或漏掉字段引起的早期异常；完整正路径及重计算 inventory 都存在，最终有后果的 `complete_*` 和全部资格结果仍是通过。复现明确使用受控 orchestration harness：进程/运行时/单屋 verifier 被替代为该已检入测试夹具的受控实现，生产 `collect()`、`verify_collection()` 和 `runtime_partition_audit()` 未替代。它证明运行状态边界缺少校验，不是实际 Unity 失败的经验数据。

建议：在采集结果审计和归档复核两处共用严格的完成矩阵状态契约。固定 1–12 的整数顺序；verified 必须准确包含成功字段、整数零退出码且无错误/traceback/cleanup 字段；failed 必须有真实失败描述，并不得携带可被提升为成功的 verification；未知状态拒绝；时间需时区明确、起止及跨房屋顺序成立。新增完整重算 inventory 的非零退出、失败字段、未知状态及非法时间攻击，同时保留合法失败矩阵的可复核路径。

证据：`round1-nonzero-exit-forgery.log`。独立临时复现脚本：`/private/tmp/offline_round1_probe.py`。

## 已执行检查

1. 冻结提交与干净工作树检查。
2. 复跑全部 5 个新增测试文件：

```sh
/private/tmp/cpswm-pc-a-camera-checkpoint-fixture-20260930/.venv/bin/python -m pytest -q -o addopts='' tests/test_offline_factor_manifest.py tests/test_offline_factor_worker.py tests/test_offline_factor_capture_verifier.py tests/test_offline_factor_collection.py tests/test_offline_factor_orchestration.py
```

结果：**93 passed in 2.75s**。首次尝试当前工作树 `.venv/bin/python` 返回 127，因为该目录没有独立虚拟环境；随后使用已存在的实体虚拟环境，工作目录与导入源码均为被冻结的新工作树。93 项通过不覆盖 R1-01。

3. 状态机攻击复现：

```sh
PYTHONPATH=src:tests:tools /private/tmp/cpswm-pc-a-camera-checkpoint-fixture-20260930/.venv/bin/python /private/tmp/offline_round1_probe.py
```

退出 0，输出上述错误接受结果；另一次相同执行保存至报告同目录的 `round1-nonzero-exit-forgery.log`。

4. 读取实际 SDK Python 3.11 安装内 `ai2thor/controller.py` 的 `reset()`：dict 场景最后调用 `CreateHouse`，因此 verifier 对初始 `lastAction == "CreateHouse"` 的要求有实际源码依据。worker 的 Python 3.11 导入已在此前预审实际通过；此次没有启动 Unity。

## 本轮覆盖与保留限制

- 官方完整 archive pin、原始 JSONL 字节、固定 0–12 清单、房屋/资产划分、旧 index0 隔离、嵌套资产及架构资产暴露都有对应来源复算路径；合法目标与共享/未知资产排除测试成立。
- SDK 事件 0–11 与公开曝光 4–11 的完整数量、action/owner、实际 yaw、固定位置/俯仰、RGB-D 字节、掩膜与 segmentation/colors、冻结后对象稳定性均在 verifier 中核验。两种对象位置定义被分开保存。
- 公开通道字段、三传感器成套来源、时序、scope、输入哈希均有核验；未观察到此次新增 worker 把私有对象真值送入公开 response 的路径。
- 训练/验证共享资产不仅检查监督标签，也累计原始房屋及 runtime 全对象目录的曝光；未知 runtime 资产使全部监督资格关闭。这是保守的数据门禁，真实场景中无 assetId 的建筑对象可能令本批没有可训练样本，必须如实报告，不能把门禁通过改写为训练完成。
- 本轮为同机归档一致性与受控攻击覆盖。整个 SDK/分割/RGB-D 一起被伪造、同机全链条同时重写的外部真伪问题不由当前自签哈希解决；代码已明确不宣称独立 custody。
- 尚未进行实际 12 房屋采集、候选覆盖统计、训练、校准、自然后验/动作收益验证。93 项测试不能替代这些阶段。

**本轮停止条件：修复 R1-01；变更将使当前冻结 SHA 审查失效。新 SHA 必须重新依次完成第一轮和第二轮审查。**
