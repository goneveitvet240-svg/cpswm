# e88f507：第二轮引擎语义与完整矩阵影响审查

- 冻结 SHA：`e88f50752ca50843fc5382b853c65abe134f1281`。
- 工作树：`/private/tmp/cpswm-pc-a-offline-factor-data-20260930`；审查前后 HEAD 不变、`git status --short` 为空。
- 顺序：同 SHA 的 `ADVERSARIAL_e88f507_ROUND1.md` 已完成后才开始本轮。
- 角色：A 组辅助审查，非 B 独立验收。本轮没有启动真实 Unity，未修改源码，未修改首批真实采集原件或失败记录。
- **结论：本轮影响范围内未发现新阻塞项。同 SHA 的两轮顺序工程审查完成，可以执行第二次 fresh 固定十二屋采集。真实采集成功、最终数据资格覆盖、模型训练／校准与闭环收益仍须各自验证。**

## 审核范围

阅读 `cd51415..e88f507` 的完整变更、新 `offline_factor_asset_provenance.py` 及其测试，并对照第一轮报告、固定引擎来源调查和 `ENGINE_SEMANTICS.md`。检查五个工具、六个测试文件以及它们之间的结果流向；尤其检查来源解析是否越权成为目标资格。

- worker 显式选择 default agent；manifest 与 verifier 读取实际 `agentPoses.default` 并核对 agent 别名。源→SDK 初始 y 差独立保留；初始 x/z、方向和后继纯旋转期间完整 XYZ 静止约束仍在。
- 源中心放置参数、SDK transform pivot、SDK AABB center 分开记录；两个跨定义距离只作为描述量。输出明确 `formal_training_position_target_selected=false`，没有把这些距离拟合成噪声，亦未自动选择正式训练位置目标。
- 新 helper 仅解释资产曝光。程序几何不虚构 assetId；派生组件保留原始空字段，仅通过精确父源与 SDK 资产匹配、命名空间和编号契约解释父 prefab 曝光。
- 最终目标仍要求原始源 objects 身份和原始 SDK assetId 一致，并通过完整分区与状态门禁；`known=true`、派生 `exposure_asset_id` 不会替代目标身份。
- 外部 inventory pin 在调用者保留原值时先于结构重建校验；低层不带 pin 的接口继续用于测试结构攻击，不被解释为独立真实性证明。

## 160 项测试与静态检查

```sh
PYTHONPATH=src:tests:tools /private/tmp/cpswm-pc-a-camera-checkpoint-fixture-20260930/.venv/bin/python -m pytest -q -o addopts='' tests/test_offline_factor_manifest.py tests/test_offline_factor_worker.py tests/test_offline_factor_capture_verifier.py tests/test_offline_factor_collection.py tests/test_offline_factor_orchestration.py tests/test_offline_factor_asset_provenance.py
```

结果：**160 passed in 3.59s，退出 0，无 skip**。日志：`e88f507-round2-tests.log`。

五个工具与六个测试文件的 Ruff check 全部通过；Ruff format check 输出 `11 files already formatted`。

## 新的全十二屋组合探针

旧 `/private/tmp/offline_round2_probe.py` 保持不变，与此前留证副本 `cmp` 仍一致。由于协议现在正确要求 `agentPoses.default`，另存新夹具脚本：

```sh
PYTHONPATH=src:tests:tools /private/tmp/cpswm-pc-a-camera-checkpoint-fixture-20260930/.venv/bin/python /private/tmp/offline_e88f507_round2_composed_probe.py
```

脚本副本为 `e88f507-round2-composed-probe.py`，日志为 `e88f507-round2-composed-probe.log`；退出 0，所有显式断言通过。

每屋都生成完整 8 帧 public state、12 个 SDK event、RGB-D、segmentation、完整实例 masks/catalog；十二屋均经过真实生产逐帧 verifier 与整批审计，**不再以其余十一屋的摘要替身代替完整原件**。夹具添加有效 schema、源房间／墙、相同 agent/default 字段，保留两个源对象、三种程序建筑和一个 prefab 组件，每屋共六个实例。

仍明确使用受控压缩包源 pin、模拟 SDK 事件与进程、runtime 描述及信号替身；没有真实 Unity 或官方自然房屋采集。真实 manifest、recorder、RGB-D 构造、StateCodec、capture verifier、collection verifier 与分区资格函数没有被替换。

合法完整结果：**96 公共帧、144 SDK 事件、72 来源已解释实例，其中仅 24 个源对象具有数据资格。** 48 个程序建筑／派生组件均不具有目标资格。夹具同时包含真实记录的初始 y 差和 0.2 m 源中心／SDK pivot 参照差，确认它们被保留描述，未误当运动、未自动选择训练目标。训练与监督导出标志保持 false。

| 完整组合场景 | 实际结果及下游后果 |
| --- | --- |
| 合法十二屋，调用者保留外部 inventory pin | 完整核验通过；24 个源目标 eligible，48 个建筑／组件不 eligible |
| 修改已完成训练／监督导出声明并重新生成 inventory | 固定外部 pin 首先拒绝；单独去掉 pin 测试结构语义时，也因重算结果不同而拒绝 |
| 十二项 attempt 起止统一提前十年、重算 inventory | `frame times differ from owning attempt state interval`，拒绝 |
| 同事件 SDK owner 替换、重算 inventory | `SDK action trace differs from fixed protocol`，拒绝 |
| 在第一屋全部十二事件及 catalog 中将 Floor 伪装为 Wall，重算验证、分区和 inventory | Floor 变成未知；完整曝光标记 false，**全矩阵 0 eligible** |
| 在训练屋组件填入验证目标 `apple-9` 的非空 assetId，同步全部事件／catalog／摘要／inventory | 原始组件资产被保留为曝光；对应验证目标撤销资格，**24→23 eligible**；组件仍无目标资格 |
| 同步改写第一屋父源对象的 SDK assetId | 派生组件无法绑定父源，变成未知；完整曝光标记 false，**全矩阵 0 eligible** |
| 仅将最终报告中的派生组件 a-1___0 提升为 eligible，完整重算 inventory | `saved partition audit differs from recomputation`，拒绝 |
| 恢复全部原件后再提供原始外部 pin | `RESTORED_EXTERNAL_PIN_POSITIVE_PATH`，完整合法路径再次通过 |

跨分区场景中的 `complete_asset_exposure_audit=true` 表示所有资产来源被完整审计，不代表每个原始目标都互斥或都可以训练；那一个发生曝光的验证目标确实被剔除，显示门禁有最终资格后果。未知／错误父源场景保留完整原件并成功复核为“资格关闭”，并非通过删文件或破坏格式来制造早期失败。

上述变更原件的探针在不带外部 pin 的结构诊断接口上重算其后果；如果提供原合法数据的固定外部 pin，它们均应首先因 inventory 变化被拒绝。对已经一起重写的原件重新签一个“可信”新 pin 不构成真实性证明，本报告没有作此主张。

## 仍未完成的证据

1. 首批 `collection-attempt01` 的十二项失败与原始数据保持不变。旧 raw 只能支持协议适用性／来源诊断，不能改名或回填为新源码的 fresh 成功采集。
2. 本轮解决字段语义和资产来源门禁，不等于源放置算法已逐物体独立复现；同一定义 SDK 跨事件位置／姿态检查继续有效。
3. 组件编号解释的是父 prefab 级曝光，不是完整独立 prefab 枚举、部件身份监督或网格／纹理不复用证明。真正无法解释的资产仍须关闭全局资格。
4. 尚未正式选择位置学习目标、导出监督、训练实例／位置因子、拟合误差模型或证明完整闭环收益。
5. A 组两轮审查、同机原件重建与外部 digest 记录不能替代 B 独立复现或独立标签真实性验收。

下一步是在保持 `e88f50752ca50843fc5382b853c65abe134f1281` 不变时 fresh 执行同一原始 index 1–12 和固定八视角，保留失败，不替换房屋；结束后用独立保存的 inventory pin 重新核验完整真实档案。新失败若要求源码修复，应再次冻结并顺序完成两轮审查。
