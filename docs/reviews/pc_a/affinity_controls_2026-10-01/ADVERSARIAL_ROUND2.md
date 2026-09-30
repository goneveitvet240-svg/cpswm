# 固定特征组对照：第二轮 A 辅助对抗审查

2026-10-01。第一轮报告完成后开始本轮，绑定冻结源码 `a6c026963b5fec1503fa0d582fe016eccf60c756`，工作树 `/private/tmp/cpswm-pc-a-affinity-controls-20261001`。执行者曾实现本轮 feature-group wrapper 及组件测试，本报告明确属于 **A 侧辅助复核，不是 B 侧独立验收**。

**本轮限定范围内未发现阻塞，可以由根任务推进冻结方案的实际固定运行及 fresh verify。** 新增 6 个真实 CLI case（3 个合法通过、3 个预期拒绝）、完整样本移植后真实重训的后果检查，以及 5 个生产 build 层缺类/VOID 边界检查。447 项定向回归通过。未修改冻结源码或测试、未提交、未运行真实新三模式数据或 Unity。未替用户选择优胜模式、阈值或新的科学权限。

## 覆盖和结果

先读 `ADVERSARIAL_ROUND1.md`，审读 driver 的父包入口、历史进程、原始公开数组与训练标签加载、三模式训练、公开预测、评价、输出复算，以及旧 driver 的重新提取特征和监督路径。本轮增量侧重来源/分区移植和路径搬移，未将第一轮的改偏置攻击换名重复。

`round2_cli_probe.py` 使用第一轮合法受控父包和此前封存的合成采集归档。原始 RGB-D、掩膜和候选为明确受控 fixture；历史 SDK 采集验收仍是原封存的显式成功状态替身。历史 affinity 程序、特征重建、标签生成、拟合、预测和当前三模式 CLI 均执行实际生产代码，没有替换为仅返回成功的脚本。

| case | 完整路径与实际后果 | 结果 |
|---|---|---|
| 01 全依赖搬移后运行 | 父包、987 文件采集目录、缓存前端、SDK 历史替身和完整历史源码搬入含空格的新目录；三个外部 pin 不变。实际历史 fresh 后训练三模式、输出 96×3 份分数 | exit 0；292 文件与 R1 原件全部同摘要 |
| 02 输出再次搬移后 fresh | 将上述完整输出复制到第二位置，仍使用全部搬移后的依赖重新运行 CLI `--verify` | exit 0；摘要完全一致 |
| 03 完整样本移植，原父 pin | 交换 train 房屋 1 与 validation 房屋 9 的全部 8×7×2=112 个帧成员，包括公开候选、features/pairs/valid、标签与监督谱系；action 随帧转移，资格 house/split 同步改写。真实重训父模型和全部三模式，重算所有预测、统计、成员和 ledger 摘要 | exit 1，`parent ledger pin differs`；未进入历史训练 |
| 04 同一完整移植候选，攻击者新 pin | 该候选通过自签父结构检查和真实三模式 `build`，combined 与攻击父模型/分数仍精确相等；随后实际 CLI 从原受控输入重新提取/拟合父模型 | 历史公开提取与拟合/预测实际执行后 exit 1，`fresh trained outputs differ`；未进入新三模式训练 |
| 05 搬移后的历史源码替换 | 对另存的历史 CLI 增加一行，保持原父包与外部 pin | exit 1，`parent source, members or authority differs`；未启动历史推理，也未产生结果目录 |
| 06 合法恢复 | 回到原父包和外部 pin，保留搬移路径重新运行完整 fresh | exit 0；292 文件仍与原件同摘要 |

样本移植不是只修改报告 split：训练公开对数 **13,440→15,360**，监督对 **8,288→9,472**，正/负类 **4,704/3,584→5,376/4,096**，VOID **5,152→5,888**，有监督训练屋 **7→8**。真实拟合的模型摘要和原训练 features/targets 摘要均改变。完整候选和真实重训后的 292 个输出保留在独立目录，拒绝后未覆盖原件。此路径验证了来源 pin 与原输入 fresh 复算各自的作用；攻击者自己提供的新摘要不能证明样本资格。

从实际合法 CLI 产物独立检查三组样本：原训练 features 摘要相同、targets 摘要相同，均为 13,440 总行、8,288 拟合行、5,152 VOID，class counts `[3584,4704]`，固定旧优化配置完全相同。每组保留全 96 帧输出，每帧与原 pairs/valid/targets 长度一致，全部有效行分数有限；每组 **8,096 个公开有效 VOID 对**仍有预测。RGB-only 仍共享深度有效性门控，geometry-only 仍共享 RGB 检测框，此证据是同样本特征对照，不是独立传感器系统比较。

另在复制的受控数组上直接执行生产 `build`：训练全 VOID、只剩负类、只剩正类均以 `training needs both non-VOID classes` 拒绝。在验证全 VOID、验证仅 same-instance 两种情况下仍完成全部三模式公开预测，291 份模型/分数文件与合法原输出逐字节一致；缺类统计是 `pairs=0,bce=null,brier=null`，对应屋均值 `houses=0`。有标签的同类验证仍正确计 4,736 对/4 屋。这 5 项是 **build 边界覆盖**，修改过的标签副本不是另一个通过外部 pin 的合法 CLI 父包，不能与上表混计。

## 命令、日志和证据

工作目录为冻结工作树，解释器 `PY=/private/tmp/cpswm-pc-a-camera-checkpoint-fixture-20260930/.venv/bin/python`；所有运行均设置 `OPENBLAS_NUM_THREADS=1 PYTHONPATH=src:tests:tools`。

```sh
$PY -m pytest -o addopts='' -q tests/test_instance_affinity_controls.py tests/test_instance_affinity_controls_driver.py tests/test_instance_affinity.py tests/test_instance_affinity_dataset.py tests/test_run_instance_affinity.py tests/test_offline_frontend_diagnostic.py tests/test_offline_frontend_evaluation.py tests/test_surface_factor_diagnostic.py tests/test_offline_factor_manifest.py tests/test_offline_factor_worker.py tests/test_offline_factor_capture_verifier.py tests/test_offline_factor_collection.py tests/test_offline_factor_orchestration.py tests/test_offline_factor_asset_provenance.py
$PY /Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/output/affinity-controls-20261001/round2_cli_probe.py
$PY /Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/output/affinity-controls-20261001/round2_denominator_probe.py
```

三个外层命令均 exit 0。回归 **447 passed in 80.43s**，日志 `round2-tests.log`；探针日志 `round2-cli-probe.log`、`round2-denominator-probe.log`。6 个 CLI 子进程的实际完整 argv、cwd、UTC 起止、exit、执行阶段、输出摘要逐条保留在 `round2-controlled-artifacts/results.json`，每条另有 stdout/stderr；包含三次预期拒绝的完整错误日志，没有删除失败证据。没有非预期失败。

四个新增 Python 文件 Ruff check、format check、`git diff --check` 均 exit 0，完整命令见 `round2-final-checks.log`。最终 HEAD 不变、工作树 clean。原父包、原采集归档、原缓存前端、历史源文件和 R1 合法控制输出均与开始时逐文件摘要一致；对应快照在 `round2-controlled-artifacts/original-input-inventories.json`。

关键证据 SHA256：

- `round2_cli_probe.py`：`3f3c0eadaec4a7d8da62b4cc115d39281e3108f4721cde3ca1fe529ead49a35b`
- `round2_denominator_probe.py`：`1cd10ef7720d602bb51128e75c016878c64fc4a842079b72f9a9012c4b127b04`
- `round2-controlled-artifacts/results.json`：`5bd465edceab14598e1ffbfb7a48695f95df5a192f68c5d5d026df507918dbcb`
- `round2-controlled-artifacts/transplant-consequences.json`：`838eda796fe690fb3ef59e908f7c3e931f298c2aae9488eda8dfbd3b240b85a6`
- `round2-controlled-artifacts/same-sample-fairness.json`：`bad58458421bb0705350897314fd98e1d57d2135c641b9e1100c26371d8edace`

本轮覆盖完整受控 CLI 正路径、完整伪造后果、外部来源约束、三组同样本公平性和指定缺类边界；它不是全仓 CI、恶意解释器沙箱、独立 SDK 运行验收或真实科学收益证明。未验证真实跨房屋泛化、物理表面归属、完整 mask、跨视角身份、校准似然、自然记忆写入或动作闭环。已有序列化/非法值矩阵由本轮 447 回归复跑；没有声称穷尽所有输入攻击。后续源码修改需要重新绑定审核。
