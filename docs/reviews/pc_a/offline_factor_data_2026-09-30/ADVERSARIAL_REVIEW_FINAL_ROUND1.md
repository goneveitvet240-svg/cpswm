# 修复后冻结候选：第一轮对抗审查

- 冻结源码 SHA：`f5c1f638816a60bddacb769e84ac43c44a1c914a`。
- 工作树：`/private/tmp/cpswm-pc-a-offline-factor-data-20260930`；审查前后 `git status --short` 为空。
- 角色：A 组只读对抗审查，不是 B 独立复核，也不是实际仿真或科学收益验收。
- 本报告不覆盖或撤销旧候选 `2a7cf9518266107ece334718ec5f53cb49480bed` 的失败记录；旧报告为 `ADVERSARIAL_ROUND1.md`。
- 结论：**本轮范围内，R1-01 已修复；未发现新的阻塞项。可以在保持该 SHA 不变的前提下，顺序开始第二轮审查。此结论尚不授权将两轮审查写为已完成。**

## 修复核验

新增 `validate_attempt_states()` 由运行划分审计调用，而归档复核在重建原始采集结果后也进入同一函数，因此两条路径共享状态约束。

- 固定十二项整数 index 的顺序为 1–12，重复、遗漏、重排及布尔 index 均不能满足契约。
- verified 仅接受精确成功字段集、整数 `exit_code == 0` 和字典 verification；失败/清理字段不能与成功状态共存。
- failed 要求非空错误和 traceback，允许采集后验证失败的零退出码，也允许生成进程之前/超时导致无退出码；禁止携带 verification。
- 未知状态拒绝。起止时间要求 UTC，结束不得早于开始，下一房屋不得早于上一房屋结束。
- cleanup_failed / 用户中断保留为不完整采集证据，不能提升为完整十二房屋验收。

## 执行结果

完整复跑全部五个新增测试文件：

```sh
/private/tmp/cpswm-pc-a-camera-checkpoint-fixture-20260930/.venv/bin/python -m pytest -q -o addopts='' tests/test_offline_factor_manifest.py tests/test_offline_factor_worker.py tests/test_offline_factor_capture_verifier.py tests/test_offline_factor_collection.py tests/test_offline_factor_orchestration.py
```

结果：**102 passed in 3.38s，退出 0，无 skip。** 包含合法完整矩阵、非零退出/超时/核验失败/进程启动失败的合法失败保留路径、带失败房屋的归档重建正路径，以及九种完整重算 inventory 的矛盾状态攻击。没有为了拒绝攻击而删除失败矩阵的合法复核能力。

未改动旧攻击脚本，再次执行此前能使错误状态获得完整通过的复现：

```sh
PYTHONPATH=src:tests:tools /private/tmp/cpswm-pc-a-camera-checkpoint-fixture-20260930/.venv/bin/python /private/tmp/offline_round1_probe.py
```

结果：**按预期拒绝，进程退出 1**，明确报错：

```text
ValueError: verified attempt state contradicts process outcome
```

失败发生在 `verify_collection()` → `runtime_partition_audit()` → `validate_attempt_states()`，不是缺失文件、早期 fixture 错误或换用简化输入。原脚本仍先构造完整合法正路径，再同时设置 verified、非零退出和 error，重算 inventory。日志为 `final-round1-original-forgery-rejected.log`。这条退出 1 是攻击成功被拒绝的证据，不能写成真实采集成功。

## 其余审查范围与限制

本轮重新核对修复 diff，并结合上一轮对四个工具与五个测试文件的完整采集链路检查。原始 archive/房屋、公开 RGB-D/相机、SDK 事件/掩膜、实际固定八视角、训练/验证全资产曝光和源/运行时绑定的实现未被本次修复放宽；102 项复跑覆盖它们的已有正路径和攻击。

以下边界继续有效：

- 未启动实际 Unity，尚无本轮十二房屋真实采集数据；真实协议适用性、完整目录中的未知资产数量、可监督目标覆盖仍待采集核实。
- 全场景未知资产会使监督资格关闭；可能出现全部目标不能导出，这应视作数据门禁结果，不能跳过未知资产制造通过。
- 本轮及旧复现使用受控进程/SDK数据夹具，不是自然模型准确率、已完成训练、误差校准、闭环收益或独立标签 custody 的证据。
- 同机归档哈希与复算不是外部独立验真；整个引擎输出一起被替换的威胁仍在明确范围之外。

下一项应是对同一 SHA 的第二轮对抗审查；如源码变化，两轮绑定失效，应重新冻结后审查。
