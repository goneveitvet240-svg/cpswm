# 实例像素亲和度开发基线：第二轮对抗审查

结论：在本报告绑定的入口与受控覆盖范围内，未发现阻止固定实际 run／fresh verify 的新阻塞。344 项定向测试通过；全部输入、缓存、来源代码及结果搬移后，保留原外部 pin 的真实 CLI 重训通过；完整房屋分区移植、重新训练模型和全部证据被原输入重算拒绝，自签原件／缓存分别被原 pin 拒绝。

## 身份与范围

- 冻结源码：`0a8a2384c321c3a2dc14cf218854754161af9ffd`；base：`d698792a8e3750af284a2c991a28aff2453b0729`。
- 工作树：`/private/tmp/cpswm-pc-a-instance-foreground-20260930`。开始、结束 HEAD 一致，`git status --short` 空；源码／测试未修改，未提交。
- 先读取已完成的 `ADVERSARIAL_ROUND1.md`，收到明确启动指令后顺序执行本轮。本执行者参与纯学习模块及其测试实现，本轮重点审查未编写的数据 helper／驱动和最终输出后果；这是电脑 A 辅助复核，不是电脑 B 或独立实现团队验收。
- 未启动 Unity，未读取真实训练／验证图像或运行真实数据训练，没有按真实验证标签选型。补充探针只使用第一轮明确合成的原件；第一轮全部原件的逐文件摘要前后相同。

## 命令与结果

工作目录为冻结树，使用复用解释器，未声称独立环境重建。

```sh
OPENBLAS_NUM_THREADS=1 PYTHONPATH=src:tests:tools /private/tmp/cpswm-pc-a-camera-checkpoint-fixture-20260930/.venv/bin/python -m pytest -o addopts='' -q tests/test_instance_affinity.py tests/test_instance_affinity_dataset.py tests/test_run_instance_affinity.py tests/test_offline_frontend_diagnostic.py tests/test_offline_frontend_evaluation.py tests/test_surface_factor_diagnostic.py tests/test_offline_factor_manifest.py tests/test_offline_factor_worker.py tests/test_offline_factor_capture_verifier.py tests/test_offline_factor_collection.py tests/test_offline_factor_orchestration.py tests/test_offline_factor_asset_provenance.py
```

退出码 0，**344 passed in 56.37s**，完整日志 `round2-tests.log`。

```sh
OPENBLAS_NUM_THREADS=1 PYTHONPATH=src:tests:tools /private/tmp/cpswm-pc-a-camera-checkpoint-fixture-20260930/.venv/bin/python /Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/output/instance-foreground-20260930/round2_partition_probe.py
```

探针退出码 0，完整日志 `round2-partition-probe.log`。五个独立 CLI 进程的命令、退出码、stdout／stderr及结果表位于 `round2-controlled-artifacts/`。六个新增 Python 文件的 `ruff check`、`ruff format --check` 均 exit 0（`All checks passed!`／`6 files already formatted`）；`git diff --check d698792a8e3750af284a2c991a28aff2453b0729..HEAD` exit 0。

## 新增合法路径与完整攻击

探针把第一轮合成 collection、两个前端缓存、历史采集代码、前端代码和已经保存的全量训练输出复制到新的含空格路径。保留第一轮的原 collection pin 与原 ledger pin，启动未替换的 `tools/run_instance_affinity.py --verify`。96 帧公开像素对重建、训练标签连接、重新拟合、checkpoint 恢复、全部预测与结果比较均通过。

随后构造完整分区移植：交换 house 1 和 house 9 的整个采集目录，同时交换两个前端的相应 8 帧 public／report；更新全部实例审计中的房屋／split、完整摘要、collection inventory、cache inputs、public 摘要、各文件摘要和四项完整 ledger。原先无候选的训练房屋被移到验证分区，原验证房屋进入训练分区。

为了证明攻击不是缺字段或陈旧内部摘要的负例，探针先用攻击者自己的新摘要通过缓存结构检查，再调用真实 `build()` 完整生成新的特征、标签、模型、分数和所有指标／member 摘要。模型可以用自己的新 pin 通过严格恢复。实际后果：训练监督行由 **8,288 增至 9,472**，class counts 变为 `[4096, 5376]`，有监督训练房屋由 **7 增至 8**，零候选房屋由 house 1 变为 house 9；模型训练输入／标签摘要相应改变。两份完整结果保留，未用手写摘要替代真实计算。

| CLI case | 使用的信任锚及实际后果 | 结果 |
|---|---|---|
| 全部路径搬移 | 原两个外部 pin、原输入、搬移后的完整输出 | exit 0，fresh 重训一致 |
| 分区移植模型与全证据 | 用原输入与原缓存重新训练，比较完整替代结果 | exit 1，完成 `fit_and_public_predict` 后 `fresh trained outputs differ` |
| 完整原件及缓存共同重签 | 提交交换后的原件／缓存，调用方继续保留原 collection pin | exit 1，`collection external pin differs`，未开始公开对／拟合 |
| 仅替代缓存 | 原 collection 保持合法，提交完整重签缓存，继续保留原 ledger pin | exit 1，`frontend ledger pin differs`，未开始公开对／拟合 |
| 攻击后合法复核 | 再使用原输入、缓存和搬移后的原输出 | exit 0，fresh 重训一致 |

攻击者新 pin 只用于证明伪造候选的内部完整性，**没有**替换 CLI 调用方原信任锚后再宣称攻击被拒绝。替代输出验证后字节未被覆盖；原输入、原缓存、第一轮原件与冻结源码全部保持不变。原／新 pin、完整前后清单、重签 ledger、runtime audit 和训练分母变化保存于 `round2-controlled-artifacts/forged-input-pins.json`。

## 数据 helper／驱动审读要点

- 固定 public 候选与真实 RGB-D／自位姿重建 support；每个框固定网格，两前端／重复框在同一动作中对无序像素对去重，候选归属单独保留，不因私有标签决定采样或删预测。
- 标签连接重新构造公共数组，并核对原 SDK RGB-D 字节、owner、相机、颜色／mask、完整对象及资格审计；两个端点都唯一属于合格渲染实例时才产生 0／1，其余保留 VOID 和原因。未知／不合格实例没有被自动变成负例。
- 拟合只使用固定 train 行；恢复后完成全部公开 score，再连接 validation 标签作开发诊断。前置历史核验会读含私有信息的归档，因此这里是模型输入／拟合顺序隔离，不是整个进程从未提前读取私有文件的保证。
- `--verify` 重新构建和拟合，并比较全部结果文件字节；模型自签摘要、单独统计一致性和一次 checkpoint restore 都不代替这条完整入口。上述分区移植的完整再训练结果正说明外层原件 pin 与 fresh 重算各自的作用。

## 保留限制及下一步

本轮继承第一轮合成夹具中的显式 detector 候选与历史 SDK 成功状态脚本；它们不证明真实引擎／资产隔离或自然检测效果。本轮 CLI、public geometry、label join、fit、restore、predict、summary 和 fresh 比较均未替换。344 项是定向回归，不是全仓 CI、B 独立或跨平台验收。

该模型输出仍是未校准的同渲染实例亲和分数，不保证关系传递性、完整 mask、目标选择、跨视角身份、物理深度归属、正式位置／朝向、观测似然或在线记忆权限。已曝光验证来源仍属开发验证；像素对和同屋帧不能当独立样本。本轮没有判断真实数据收益或自然因子完成。

在冻结 SHA 不变的前提下，主任务可以执行已经计划的固定实际 run 与完整 fresh verify，保留零候选、VOID、不合格实例和全部公开 score，并按原分区报告开发结果。若修改源码，本轮结论不自动继承到新 SHA。
