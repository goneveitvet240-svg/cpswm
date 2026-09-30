# 固定离线公开前端：第二轮对抗审查

结论：在下面绑定的源码、入口及受控覆盖范围内，没有发现阻止主任务运行固定真实归档前端诊断的新阻塞。231 项定向测试全部通过；独立进程 CLI 的合法完整路径、输入／输出／源码搬移复核通过；候选几何、时间归属、分区、资产资格、权威标志及输出类型攻击均被拒绝。这个结论属于电脑 A 辅助审查，不是电脑 B 独立验收，也不是自然检测质量或完整研究闭环验收。

## 版本、顺序与边界

- 冻结工作树：`/private/tmp/cpswm-pc-a-offline-front-end-20260930`。
- 实际源码 SHA：`3babc6d1557b4fe54abc6c8ac1f6054cdeb03e57`；开始与结束 `git rev-parse HEAD` 一致，`git status --short` 均为空。
- 先阅读已经完成的 `ADVERSARIAL_ROUND1.md`，收到主任务明确启动第二轮后才执行本轮。实现阶段的 19 项驱动测试不冒充本轮运行；本轮从冻结源码重新执行全部 231 项。
- 本执行者参与过驱动测试编写；本轮增加新的外部临时探针和独立 Python 进程执行。不能把同一 A 任务内部复核写成独立团队验收。
- 没有修改冻结源码或测试，没有提交，没有启动 Unity，没有读取真实采集归档像素进行推理。新增脚本、日志与本报告只位于本轮输出证据目录。
- 代码审读覆盖两个新工具、两个新测试，以及历史 `_public`、SDK 同事件所有权、RGB-D 回执重建、几何计算、全矩阵校验和汇总的调用链。远端同步由主任务负责，本结论只绑定上述冻结源码。

## 命令及结果

以下命令工作目录为冻结工作树，解释器是复用的 `/private/tmp/cpswm-pc-a-camera-checkpoint-fixture-20260930/.venv/bin/python`，不是本轮独立重建环境，也不是历史 AI2-THOR SDK 的 Python 环境。

```sh
PYTHONPATH=src:tests:tools /private/tmp/cpswm-pc-a-camera-checkpoint-fixture-20260930/.venv/bin/python -m pytest -o addopts='' -q tests/test_offline_frontend_diagnostic.py tests/test_offline_frontend_evaluation.py tests/test_surface_factor_diagnostic.py tests/test_offline_factor_manifest.py tests/test_offline_factor_worker.py tests/test_offline_factor_capture_verifier.py tests/test_offline_factor_collection.py tests/test_offline_factor_orchestration.py tests/test_offline_factor_asset_provenance.py
```

退出码 0，**231 passed in 26.40s**。完整输出保存在 `round2-tests.log`。

```sh
PYTHONPATH=src:tests:tools /private/tmp/cpswm-pc-a-camera-checkpoint-fixture-20260930/.venv/bin/python /Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/output/offline-front-end-20260930/round2_cli_probe.py
PYTHONPATH=src:tests:tools /private/tmp/cpswm-pc-a-camera-checkpoint-fixture-20260930/.venv/bin/python /Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/output/offline-front-end-20260930/round2_rebound_provenance_probe.py
```

两个脚本均退出码 0，日志分别为 `round2-cli-probe.log`、`round2-rebound-probe.log`。第一脚本保存 17 个独立 CLI 进程的完整命令、stdout、stderr、退出码、推理／评价计数；结果表在 `round2-controlled-artifacts/results.json`。第二脚本保存完整回执重签攻击及原／伪造外部摘要，结果在 `round2-rebound-artifacts/pins-and-result.json`。

另外运行以下静态检查，全部退出码 0：

```sh
/private/tmp/cpswm-pc-a-camera-checkpoint-fixture-20260930/.venv/bin/python -m ruff check tools/diagnose_offline_frontend.py tools/offline_frontend_evaluation.py tests/test_offline_frontend_diagnostic.py tests/test_offline_frontend_evaluation.py
/private/tmp/cpswm-pc-a-camera-checkpoint-fixture-20260930/.venv/bin/python -m ruff format --check tools/diagnose_offline_frontend.py tools/offline_frontend_evaluation.py tests/test_offline_frontend_diagnostic.py tests/test_offline_frontend_evaluation.py
git diff --check 5a2a963d7f3b9fc8c3084e0b50d1696b2a7314f2..HEAD
```

Ruff 输出 `All checks passed!`、`4 files already formatted`。

## 完整正路径与替身说明

第一脚本每次启动新的 Python 进程，通过实际 `main()` 参数解析、历史核验子进程、公开推理、真实几何、真实私有评价、真实汇总以及保存／`--verify` 比较。使用 `build_capture` 构造 12 屋 × 8 帧、共 96 帧完整受控档案。第一屋故意产生零候选，其余屋保留三个跨类别候选。

明确替身只有两项：检测器换成既有受控 `RGBDSupportDecoder`；历史 SDK 资格核验子进程换成明确标注的固定状态脚本。后者仍是实际创建的子进程，其代码纳入 `configuration.source_files`，由驱动真实核对来源与退出状态。它不证明该合成批次满足真实资产隔离、引擎来源或完整历史采集状态机；这些依赖由既有 231 项回归覆盖，本轮不声称重做真实采集验收。

没有替换 `surface_support`、`evaluate_frame`、`summarize` 或保存比较。包装器只添加计数和先后顺序断言，并继续调用真实函数。每个成功或保存结果篡改复核进程都完成 **96 次公开推理，然后 96 次私有评价**。历史核验本来可以先读取私有材料，这里断言的是神经输入和本轮评价顺序，不声称整个进程在此之前完全没有私有读取。

合法结果保留 8 个零候选帧、264 个候选、288 个实例帧次、792 个候选 × 实例配对、176 个正重叠与 616 个零重叠，64／32 训练／验证帧，以及 36 个全部实例／24 个受控合格实例。观测 ID、三路摘要、相机动作 ID、结构化相机位姿和回执完整保留，不给候选填充世界实例、对象中心、朝向或概率。

17 个 CLI case 中有五条合法接受路径：初次保存、原位复核、输入／输出／历史源码同时搬移、再将当前源码搬移后复核、攻击恢复后的最终复核。所有文件内容不变的搬移均保持结果一致。另在临时复制源码中只给驱动添加注释，重新加载复制代码后，96 帧数值计算仍完成，但旧产物因 `diagnostic_source_files` 不同而拒绝；冻结工作树没有被修改。

## 攻击及实际后果

| 攻击 | 完整构造及后果 | 实际拒绝边界 |
|---|---|---|
| 相机与候选几何共同伪造 | 全部公开相机平移 3 m、yaw 增加 45°；用真实相机公式重算全部候选表面点、全部实例的两类位移、geometry group 和完整摘要；同步公开预测摘要 | 完成 96／96 后 `fresh public differs` |
| 输出时间与动作 owner 改写 | 96 个动作换新 UUID，公开命令、相机 owner、报告 owner 同步；decision／capture／arrival／cutoff 全部推迟 3650 天并保留时序；重算预测摘要 | 完成 96／96 后 `fresh public differs` |
| 房屋分区互换 | 完整交换 house 1 与 house 9 的报告房屋、split 及每实例保留的审计归属，重新汇总；汇总本身接受该内部一致矩阵 | 完成 96／96 后 `fresh report differs` |
| 资产别名及资格改写 | 所有帧中把实例 a 的资产换成假验证资产，同时改写保留审计、资格和排除原因；重算全部摘要，使合格实例人口发生变化 | 完成 96／96 后 `fresh report differs` |
| 语义／位置／在线权限升格 | 完整报告把自动身份、类别映射、正式位置参照、观测似然写入及在线记忆写入标志改为 true | 完成 96／96 后 `fresh report differs` |
| 输出源码身份伪造 | 完整报告内驱动源码摘要改为假值，其余结果保留 | 完成 96／96 后 `fresh report differs` |
| 公共布尔值数字化 | 所有 `memory_write_authorized: false` 改为 `0`；Python 对象比较相等，重算公开预测摘要 | 类型敏感比较拒绝：`fresh public differs` |
| 历史核验非零退出但 stdout 完全成功 | 实际子进程输出四个合法布尔标志后 exit 7 | `historical collection verifier failed`，0 次推理／评价 |
| 历史核验数值成功标志 | 实际子进程 exit 0，但用 0／1 代替四个布尔值 | `not a complete eligible`，0 次推理／评价 |
| 历史源码改变 | 只改历史脚本注释，保留原配置源码摘要 | `historical capture source bytes differ`，0 次推理／评价 |
| 外部 pin 改变 | 给合法档案提供不匹配摘要 | `collection external pin differs`，0 次推理／评价 |

上述输出层几何／时间攻击保留了完整文档和重算的后续数字，但没有伪称它们的原始观测回执也已重签。第二个探针专门补足这一更强层次：先运行合法 96 帧 CLI，再把全部 96 帧推迟 3650 天、替换动作与 snapshot UUID，调用真实 `observations_from_response` 重新生成 **288 条公开观测及全部回执**，同步对应 96 个 SDK event owner 和实例目录 action owner，重新签署 collection inventory。

这份伪造档案通过低层 `_public → RGB-D geometry → evaluate_frame → summarize`，得到真实重算的完整 96 帧／792 配对伪造结果；说明它不是缺字段、陈旧内部摘要或单项错位的简单负例。然而调用 CLI 时仍保留最初调用方的外部 pin，因此在历史子进程和推理之前被 `collection external pin differs` 拒绝。原 pin 与伪造 pin、完整前后清单、示例原／伪造公开状态、同事件 owner 及完整伪造输出均留证。没有把攻击者新签的 pin 当作原信任锚。

所有输出攻击后核对伪造目录字节未被验证过程覆盖；最终合法复核仍通过。输入库存与开始相同，冻结源码摘要与开始相同。

## 剩余范围与允许的下一步

1. 新增工具是描述性诊断。框与 mask 重叠不等于正确语义识别；原生检测器类别与 SDK 类别没有自动映射，样本到 pivot／AABB 的距离不等于定位校准误差。正式对象位置参照、身份关联、观测因子训练和自然闭环收益仍未完成。
2. `summarize` 检查内部矩阵一致性，不决定外部真实性或资产隔离；本轮的自洽分区／资产／时间反例说明，外部 pin、可信历史源码核验和当前重推比较必须作为完整入口保留。不能把低层 helper 单独升格为科学验收接口。
3. 本轮非零候选全矩阵来自显式受控检测器；没有再次运行第一轮的生产模型合成图像探针，也没有运行任何真实采集数据推理。本轮结果不评价 SSDLite／Faster R-CNN 的自然场景质量、速度或稳定性。
4. 当前源码身份覆盖 `src/tests/tools` 文件内容；路径搬移不改变身份，内容变化会改变身份。这个机制不是防御恶意解释器、运行时 monkeypatch、被篡改依赖或外部信任锚被替换的安全沙箱，也不是独立标签托管证明。
5. 231 项是本轮定向工程回归，不是全仓 CI 或电脑 B／跨平台验收。该解释器是复用环境，不把通过结果记为独立环境重建。

在上述范围内可由主任务按固定配置开始真实 12 屋归档的两种公开前端诊断，保留完整 96 帧、零候选与所有不合格实例，并在运行后使用同一冻结源码和固定外部 pin 重新复核输出。若源码改变，本轮结论不自动继承到新 SHA。
