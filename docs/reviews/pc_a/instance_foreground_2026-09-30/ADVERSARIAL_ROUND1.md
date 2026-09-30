# 实例像素亲和度开发基线：第一轮对抗审查

结论：在本报告绑定的源码、入口及受控覆盖范围内，未发现阻止进入第二轮的新阻塞。344 项定向测试通过；真实 CLI 上的受控训练、保存及重新拟合正路径通过；共同改写模型、全部分数、指标和文件摘要的完整产物被 fresh 重算拒绝。可按相同 SHA 顺序启动第二轮，不能据本轮单独通过就开始真实数据训练。

## 身份与边界

- 冻结源码：`0a8a2384c321c3a2dc14cf218854754161af9ffd`；base：`d698792a8e3750af284a2c991a28aff2453b0729`。
- 工作树：`/private/tmp/cpswm-pc-a-instance-foreground-20260930`。开始／结束 HEAD 一致，`git status --short` 空；未改源码或测试，未提交。
- 执行者：电脑 A 辅助审查代理，之前提供过只读设计建议，未参与本轮源码或测试实现；不是电脑 B 独立验收、全仓 CI 或独立数据托管。
- 完整读取三个新实现文件、三个新测试文件及本轮文档增量，追踪历史采集和公开前端 pin、公开像素对、私有监督、训练标准化、拟合、checkpoint 恢复、全量预测及最终文件比较。
- 没有启动 Unity，没有运行自然检测器，没有使用真实归档训练或按真实验证 mask 调参。本轮真实数值优化只发生在明确合成的受控数据上。

## 命令和结果

工作目录均为上述冻结树；解释器是 `/private/tmp/cpswm-pc-a-camera-checkpoint-fixture-20260930/.venv/bin/python`。沿用现有本机环境，未声称重建独立环境。

```sh
OPENBLAS_NUM_THREADS=1 PYTHONPATH=src:tests:tools /private/tmp/cpswm-pc-a-camera-checkpoint-fixture-20260930/.venv/bin/python -m pytest -o addopts='' -q tests/test_instance_affinity.py tests/test_instance_affinity_dataset.py tests/test_run_instance_affinity.py tests/test_offline_frontend_diagnostic.py tests/test_offline_frontend_evaluation.py tests/test_surface_factor_diagnostic.py tests/test_offline_factor_manifest.py tests/test_offline_factor_worker.py tests/test_offline_factor_capture_verifier.py tests/test_offline_factor_collection.py tests/test_offline_factor_orchestration.py tests/test_offline_factor_asset_provenance.py
```

exit 0：**344 passed in 96.41s**。原始日志：`round1-tests.log`。

```sh
OPENBLAS_NUM_THREADS=1 PYTHONPATH=src:tests:tools /private/tmp/cpswm-pc-a-camera-checkpoint-fixture-20260930/.venv/bin/python /Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/output/instance-foreground-20260930/round1_cli_probe.py
OPENBLAS_NUM_THREADS=1 PYTHONPATH=src:tests:tools /private/tmp/cpswm-pc-a-camera-checkpoint-fixture-20260930/.venv/bin/python /Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/output/instance-foreground-20260930/round1_numeric_check.py
```

两探针均 exit 0；日志为 `round1-cli-probe.log`、`round1-numeric-check.log`。全部独立子进程命令、返回值、stdout/stderr 和原／伪造产物在 `round1-controlled-artifacts/`，case 总表为其 `results.json`。

静态检查：对六个新增 Python 文件执行 `ruff check`、`ruff format --check`，均 exit 0，输出 `All checks passed!` / `6 files already formatted`；`git diff --check d698792a8e3750af284a2c991a28aff2453b0729..HEAD` exit 0。

## 信任链与标签流核对

1. CLI 先以调用方原 collection inventory pin 检查完整原件，再调用源码字节与旧 configuration 匹配的历史 verifier。没有重签真实历史来源或把新训练源码当作旧采集源码。
2. 前端缓存要求调用方原 `case-results.json` 外部 pin；四项 run/verify 次序及整数 exit 0、各方法三文件摘要、历史前端 Python 源码身份、原采集 inventory 和 capture source 全部配对。缓存中的保存预测会重新对实际 RGB-D／相机重建 support；本轮不重新执行 detector，`detector_inference_reused=True` 与实现一致。
3. 每帧全部公开候选先生成固定网格和无序不同像素对，跨候选／两前端同一动作内去重。候选归属单独保留；特征无 SDK ID、类别、asset、资格、位置标签或 split。96 帧公开对生成完成后，训练 label join 才用于拟合。
4. 同实例／不同实例监督要求两个端点各自唯一属于合格渲染实例。未知像素、多个 mask 成员、不合格成员和公开无效深度为 VOID。特征、像素对、回执和相机在 label join 时重建比对；SDK 原始 RGB-D 字节必须与 public delivery 相同。
5. 训练只用固定 train 分区中的非 VOID 行计算 mean、scale、prevalence、Newton 优化及固定 L2；VOID 仍参与输入身份摘要与总行数，但不进入标化或优化。无有效监督或缺任一类显式拒绝。
6. 从 JSON 恢复 checkpoint 后，对所有公开有效 pair 预测，并与原模型的全部分数逐项一致比较。未知／不合格私有标签不会抹掉公开有效预测。之后才调用 validation 的私有 label join 计算开发诊断；空监督房屋 BCE/Brier 为 null，按屋 macro 另报实际有监督房屋数。
7. `--verify` 从原 pin、公开缓存与原标签重新构建特征、重新拟合、恢复和预测，再比较全产物字节清单；不是仅信任 model 或 report 内自签摘要。

注意：历史 frontend report 和完整 runtime audit 的前置来源核验本来会读取含私有评价信息的文件。可声称“验证监督不参与模型拟合或公开特征／score 选择”，不能声称整个进程在预测完成之前完全未读取任何验证私有资料。

## 独立完整正路径

`round1_cli_probe.py` 使用 12 屋 × 8 帧合成 RGB-D；第一屋有 8 个零候选帧，其他屋的两个前端各含三个固定受控框，其中两框完全重复。一个小框覆盖两个合格实例，另一个框同时包含合格、无 mask 的未知像素和不合格 floor。所有框为事先写定的夹具常数，不读取真实标签或选择真实验证场景。

替身明确有两项：既有 `RGBDSupportDecoder` 产生固定合成候选；历史 SDK verifier 是写入受控 source/config 的固定成功状态脚本。前端缓存由真实诊断／保存函数生成并再次用同一受控 detector 重建比较，随后固定 ledger pin。这个夹具不证明真实采集引擎、资产隔离或自然检测质量。当前训练 CLI、公开几何、标签 join、去重、标化、Newton fit、恢复、预测、指标和 fresh 比较均未替换。

七个独立 Python CLI 进程中，初次训练、完整 fresh 重训、攻击后的合法 fresh 重训均 exit 0。三个正路径均执行 96 帧公开对重建与拟合／全量预测；原产物保存后不再被改写。

可手算的分母如下，已与实际全量 NPY/JSON 核对：

- 每个非空帧原候选归属 720 对、实际唯一 240 对；重复框和跨方法重复不增大训练权重。
- 每个非空帧同实例 84、不同实例 64、VOID 92；其中未知像素原因 54、不合格实例原因 38。
- 全体 96 帧保留 8 个零候选帧，原候选归属 **63,360**、唯一公开对 **21,120**；其中 **8,096** 个 VOID 对仍有合法公开分数。
- 训练有效对 **8,288**，class counts `[3584, 4704]`，常数 baseline 的正类频率恰为 `4704/8288`；第一屋保留且损失为 null。

`round1_numeric_check.py` 不调用生产 label helper、fit、predict 或 summarize；用手写合成区域规则逐对计算完整标签，并直接从原始特征复算训练 mean/std、sigmoid 全量分数、prevalence、L2 目标及梯度。结果全部一致：最终惩罚目标 `0.47176050997418006`，梯度最大绝对值 `6.263739527057055e-14`。这验证受控学习算术和分母，不是自然数据收益。

## 完整伪造及实际后果

| 攻击 | 完整构造 | 实际结果 |
|---|---|---|
| 模型＋全部分数＋报告共同改写 | 完整合法 schema 模型 bias 增加 2；新模型可用其新自签 pin 恢复；用真实 predict 重算全部帧分数，重算逐帧／逐屋／分区／macro／总体 BCE/Brier，重写 model pin 和全部 member 摘要 | 独立 CLI 真正完成公开对重建、重新拟合和全预测后，以 `fresh trained outputs differ` 拒绝；伪造原件未覆盖 |
| 私有 VOID 隐去公开输出 | 保留完整帧、pair、特征、模型及标签，把所有私有 VOID 对原有公开有效分数改为 NaN；监督指标保持一致并完整更新 member 摘要 | 同样在 fresh 训练／预测后拒绝；证明仅核对有标签指标不足以验收完整公开 score |
| 前端 public＋report＋ledger 共同重签 | 改写完整候选分数、对应 owned support 与 report 候选，重签 public content hash、所有文件摘要和四行完整 ledger；调用方仍保留原 ledger pin | `frontend ledger pin differs`，在公开对生成及训练前拒绝 |
| 原采集 pin 错配 | 完整合法原件与其他参数不变，只提供不符原 collection pin | `collection external pin differs`，在公开对生成及训练前拒绝 |

第一项的分数和所有评价后果与改写模型自洽，但其原训练履历不能因此获得真实性；`restore` 的结构检查和攻击者新签 pin 本身不证明按固定训练协议得到了这些权重。外层重新训练才关闭这一验收缺口。未把替换外部信任锚当作攻击被拒绝的证据。

344 项定向回归另包含：验证有效标签翻转时模型和全部 score 不变；VOID 极端特征不改变拟合；单类／全 VOID 拒绝；未知、不合格、冲突、无效深度、不可见实例和零对保留；同事件 NPY 字节与所有权攻击；完整公共数组重建；严格 checkpoint 字段／类型、原 pin 防权重改写；旧采集状态机、时间归属与资产曝光／资格规则。

## 剩余限制与下一步

- 本轮是完整入口的定向 A 辅助工程审查。低层 `fit` 或自签 checkpoint 无法独立证明数据分区／标签来源；单独用它们不能继承外层 CLI 的验收结论。
- 同一 mask 的 pair 不保证真实物理深度表面、关系传递性、完整 mask、候选目标选择、跨视角身份或自然观测似然。BCE/Brier 与标准化 logistic 分数不构成已校准概率或正式任务成功指标。
- 本轮没有选择 SDK pivot/AABB 对象原点，没有生成朝向，没有改变用户位置＋朝向任务、原对照或完整统一框架，没有赋予在线记忆权限。
- 已曝光的固定验证来源仍是开发验证；候选内 pair、同屋帧及两个前端的重复归属不是独立统计样本。本轮不据受控损失下降声称泛化或闭环收益。
- 真实固定数据拟合、真实输出重训一致性、自然实例／位置因子和动作收益尚未运行／验证。依用户要求，应先完成同 SHA 的第二轮，再推进真实训练；代码变化后重新冻结审查。

第一轮结束：**可进入第二轮，无本轮新阻塞项。**
