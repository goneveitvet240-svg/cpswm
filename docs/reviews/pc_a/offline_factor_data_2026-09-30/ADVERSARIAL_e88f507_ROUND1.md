# e88f507：固定引擎语义与资产来源解析第一轮审查

- 冻结 SHA：`e88f50752ca50843fc5382b853c65abe134f1281`。
- 工作树：`/private/tmp/cpswm-pc-a-offline-factor-data-20260930`；审查前后干净，未编辑源码，未启动新的 Unity 采集。
- 角色：A 组只读对抗审查，不是 B 独立验收。
- 范围：`cd51415..e88f507` 全部实现及测试差异、固定引擎源码依据、完整单屋公开/私有归档到最终划分资格路径、既有状态与时间攻击回归。
- 结论：**本轮范围内未发现新的阻塞项；可以保持此 SHA 不变，顺序开始第二轮。真实新批采集、监督导出、训练与校准尚未由本轮验收。**

首批 `collection-attempt01` 的 12 项失败状态及全部原件未改写。本轮源语义修复不把旧批回填成新候选通过，也不把组件测试写为真实采集成功。

## 固定引擎语义核对

读取了 `ENGINE_SEMANTICS.md`、`RUNTIME_ASSET_PROVENANCE_INVESTIGATION.md`，并直接读取保存的 `ProceduralTools.cs`。实际重算该文件 SHA256 为：

```text
877589b9ed6b7dba31aa860d1dc8469e7ff0f415d1a3cdf29582d936212dc877
```

与实现和调查中的 pin 一致。

- `setAgentPose()` 实际读取 `metadata.agentPoses[agentMode]`，设置源位置后执行 CharacterController 的重力 Move。新 worker 显式 `agentMode="default"`，源清单和 verifier 校验 alias 一致。源→初始 SDK 的 y 差保留为描述，而 x/z、yaw、horizon 及随后完整 XYZ 不动检查继续存在；没有把本批 −0.049m 硬编码成普遍真值。
- prefab 放置的 `positionBoundingBoxCenter` 分支通过边界中心计算 transform，因此源位置与 SDK pivot 的跨定义差不能直接证明对象移动。新实现保留源位置、SDK pivot、SDK AABB center 及两个跨定义距离，明确未选定正式训练位置目标；同一定义的 SDK 跨事件位置/旋转/边界变化检查未放宽。
- 固定源码生成子部件 ID 的规则为源根 ID 加 `___` 和从零连续编号；根资产 ID 赋给根对象。来源解析要求存在精确父源与匹配的 SDK 父资产，拒绝命名空间冲突和非规范/缺失编号。这里只解释父 prefab 级曝光，未声称编号验证了每个实际子部件的语义、几何或完整 prefab 枚举。
- 程序墙/地板解析依精确源 ID、SDK 类型与有效源几何规则；不补造 assetId。目标资格依然读取原始 SDK assetId 与源 objects 身份，而不是解析后的 `known` 或 `exposure_asset_id`。

## 全套测试与实际 SDK 解释器检查

```sh
/private/tmp/cpswm-pc-a-camera-checkpoint-fixture-20260930/.venv/bin/python -m pytest -q -o addopts='' tests/test_offline_factor_manifest.py tests/test_offline_factor_worker.py tests/test_offline_factor_capture_verifier.py tests/test_offline_factor_collection.py tests/test_offline_factor_orchestration.py tests/test_offline_factor_asset_provenance.py
```

结果：**160 passed in 3.62s，退出 0，无 skip。** 覆盖合法固定采集/失败矩阵、来源/资产/命名空间/几何攻击、原状态与时间归属修复、外部 inventory pin 替换攻击。

实际 SDK Python 3.11.16 导入 `unity_offline_factor_worker` 成功，动作序列仍为 Pass 后七次 RotateRight 45°；未启动 Unity。

## 独立临时完整来源链检查

临时脚本：`/private/tmp/offline_e88f507_round1_chain.py`。执行命令：

```sh
PYTHONPATH=src:tests:tools /private/tmp/cpswm-pc-a-camera-checkpoint-fixture-20260930/.venv/bin/python /private/tmp/offline_e88f507_round1_chain.py
```

结果退出 0。它生成具有原件配对的完整单屋 8 个公开帧、12 个 SDK 事件、RGB-D、完整 masks/segmentation/catalog，包含源对象 a/b、程序房间/墙/全屋地板及 a___0 prefab 部件。构造阶段为受控 fixture，不是天然场景。经生产 `verify_capture()` 得到原始验证结果，再放入完整十二项 `runtime_partition_audit()`；其余十一项采用已有受控矩阵摘要，未虚称十二屋都由真实 SDK 采集。

| 完整输入与攻击 | 最终结果 |
| --- | --- |
| 合法程序建筑＋prefab 部件 | 6 个来源已解释；第一屋只有原始 a/b 有监督资格；建筑/部件全部无资格 |
| 全十二事件及 catalog 同步将 Floor 类型伪装成 Wall | Floor 未知；全局曝光门禁关闭，所有目标无资格 |
| 全十二事件及 catalog 同步改写父 a 的资产 | a___0 无法借用父源资产；全局曝光门禁关闭，所有目标无资格 |
| 给部件 a___0 填入其自身非空资产并同步全部事件/catalog | 该资产保留为曝光；部件仍不在原始源 objects 中，不能取得目标资格；a/b 合法资格保留 |

日志：`e88f507-round1-provenance-chain.log`。这些攻击沿完整且可重算的单屋原件进入最终 `eligible` 结果，而非仅检查局部解析器 `known` 值。没有通过删除不可见对象、删掉 private 文件或破坏早期格式来制造拒绝。

## 既有攻击与外部 pin 回归

原两个临时攻击脚本均未修改：

- `/private/tmp/offline_round1_probe.py`：完整重算 inventory 后，非零 exit_code 与 verified 共存仍被 `ValueError: verified attempt state contradicts process outcome` 拒绝，退出 1。日志 `e88f507-round1-original-forgery-rejected.log`。
- `/private/tmp/offline_round1_interval_probe.py`：先验证合法完整矩阵，再把全部 attempt 起止时间提前十年，仍被 `ValueError: frame times differ from owning attempt state interval` 拒绝，退出 1。日志 `e88f507-round1-interval-forgery-rejected.log`。

实际执行 CLI `--verify` 而不给 `--inventory-sha256`，在读取不存在的输入之前由 argparse 拒绝，退出 2。日志 `e88f507-round1-cli-pin-required.log`。完整测试中固定外部 pin 的正路径通过，替换整个记录并重算自报 inventory 后无法替换该外部 pin。

这些非零退出是攻击被拒绝的证据，不是真实采集失败或成功的计数。

## 剩余限制与下一门槛

- 此次归档结构、来源规则和目标资格验证没有选定正式位置监督定义；不能把 SDK pivot 或 AABB center 自动写成最终训练目标。
- 资产隔离保证限于记录的 prefab assetId 级曝光，不证明不同 assetId 不复用网格/纹理。源部件连续编号不是独立 prefab 部件清单。
- 外部 inventory pin 只在其记录位置不被同一修改一起替换时具有边界作用；不是独立人工标注或 B 侧真实复现。
- 初始重力高度差与源放置参照差现在被正确描述，不代表全部源位姿已按 prefab 构造公式独立验真。
- 新候选尚需同 SHA 第二轮审查，随后 fresh 固定十二屋完整采集及实际资格覆盖检查。未知来源仍须关闭全局曝光门禁；旧批必须保持原始失败状态。
