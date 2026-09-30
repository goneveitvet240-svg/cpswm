# 固定特征组对照：第一轮 A 辅助对抗审查

2026-10-01（上海时区）。冻结源码 `a6c026963b5fec1503fa0d582fe016eccf60c756`，base PR76 `ffcaa7b292c73201d799f6631688387409c21cb7`，工作树 `/private/tmp/cpswm-pc-a-affinity-controls-20261001`。本执行者参与了只读设计建议，未实现本轮生产源码或测试；这是同机 A 辅助源码/工程审查，不是电脑 B 独立验收。

**结论：本轮限定范围内未发现阻塞，可顺序进入 R2。** 447 项定向测试通过；实际 CLI 完成 2 次受控父结果生成/复核及 8 个控制链路 case。完整输出伪造在从原输入真正重训后被拒绝，合法恢复通过。尚未运行真实新特征组对照、Unity 或真实验证数据调参。未修改冻结源码、测试、旧封存原件或提交 Git。

## 审读与执行范围

审读完整 base→冻结 SHA 差异：四个新增 Python 文件（wrapper、driver、两个测试），以及三份计划/交接文档；沿父外部 ledger→674 文件→历史源码 fresh CLI→公开数组→训练标签→三模式拟合/恢复→全部公开预测→验证评价→完整输出复验追踪。原 `instance_affinity.py`、原 driver 和 dataset helper 相对 base 未改变。

- wrapper 先校验原始全部八列再复制置零，保持 dtype，不改变原输入；枚举与列集合严格绑定；禁用列均值/权重为零、scale 为一。原输入摘要、内层投影输入摘要、标签摘要与内外检查点摘要分别保存。
- 三模式使用同一训练数组、标签、VOID 和常数，固定原 L2/优化器；没有平衡采样或分别筛样。RGB-only 仍共享 RGB-D 有效性门控，geometry-only 仍条件于 RGB 检测框，属于同样本特征组对照。
- 父 ledger、674 成员、875 份历史源码内容分别核验。历史入口参数从显式 CLI 参数重建，不执行 ledger 保存的 argv。PR76 文档 head `ffcaa7b` 与真实功能源码 `0a8a2384c321c3a2dc14cf218854754161af9ffd` 分开记录。新增控制源码清单为 879 个 Python 文件。
- combined 内层 JSON 与父模型、96 份 combined NPY 与父分数逐字节相等。所有模式均保留无候选帧及有效 VOID 分数；所有 288 次公开预测后才连接当前 driver 的验证标签。历史 fresh 过程会读取私有验证归档，此保证是拟合/模型输入隔离，不是恶意进程隔离。
- 逐帧、逐屋、分区、正/负类与常数使用一致分母；无该类时为 `pairs=0, bce=null, brier=null`，屋均值同时记录非空屋数。

## 回归命令与结果

工作目录为上述冻结工作树；解释器 `/private/tmp/cpswm-pc-a-camera-checkpoint-fixture-20260930/.venv/bin/python`。

```sh
OPENBLAS_NUM_THREADS=1 PYTHONPATH=src:tests:tools /private/tmp/cpswm-pc-a-camera-checkpoint-fixture-20260930/.venv/bin/python -m pytest -o addopts='' -q tests/test_instance_affinity_controls.py tests/test_instance_affinity_controls_driver.py tests/test_instance_affinity.py tests/test_instance_affinity_dataset.py tests/test_run_instance_affinity.py tests/test_offline_frontend_diagnostic.py tests/test_offline_frontend_evaluation.py tests/test_surface_factor_diagnostic.py tests/test_offline_factor_manifest.py tests/test_offline_factor_worker.py tests/test_offline_factor_capture_verifier.py tests/test_offline_factor_collection.py tests/test_offline_factor_orchestration.py tests/test_offline_factor_asset_provenance.py
```

结果 **447 passed / 81.17s**，exit 0，日志 `round1-tests.log`。新增四文件 Ruff check、format check 及 `git diff --check` 均通过；审核前后工作树 clean，HEAD 未改变。完整源码选择、非法值/类型、缺类矩阵、路径搬移和验证标签时序测试均包含在此定向集合；不是全仓 CI。

## 独立真实 CLI 正路径与完整伪造

脚本 `round1_cli_probe.py`，日志 `round1-cli-probe.log`，逐 case 完整 argv、UTC 时间、exit code、阶段与成员摘要见 `round1-controlled-artifacts/results.json`；每次 stdout/stderr 和全部伪造候选保留。执行命令：

```sh
OPENBLAS_NUM_THREADS=1 PYTHONPATH=src:tests:tools /private/tmp/cpswm-pc-a-camera-checkpoint-fixture-20260930/.venv/bin/python /Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/output/affinity-controls-20261001/round1_cli_probe.py
```

先从旧封存受控 collection/cached frontends/history fixture 只读生成新父包。旧源码真实 `run_instance_affinity.py` run 与 verify 均 exit 0，两次 674 个文件与旧封存 original 全部同摘要。这里历史 affinity 构建、拟合、恢复、预测、评价及新的三模式 CLI 都是真实生产代码执行；仅原始 RGB-D/masks、检测器候选和 SDK 历史审计是明确受控替身。没有用仅返回 exit 0 的脚本替代旧 affinity fresh 或新控制 CLI。

| case | 候选及实际后果 | 结果 |
|---|---|---|
| parent-run / parent-verify | 旧 affinity 实际生成并从原受控输入 fresh 复算完整父包 | 两次 exit 0，674 文件相同 |
| 01 original-run | 父 fresh 后三模式真实 fit/restore/predict，全 96 帧输出 | exit 0，292 文件 |
| 02 original-fresh | 再次运行父 fresh 与三模式 fit，比较全输出 | exit 0 |
| 03 complete-model-score-report-forgery | 三模型偏置分别改变；内外检查点自签可恢复；96×3 分数、逐帧/屋/分区/正负类/屋均值、全部成员哈希重算 | 父 fresh 与三模式所有公开预测均真实执行后 exit 1：`fresh trained outputs differ` |
| 04 mode-transplant-complete | RGB/geometry 参数相互移植到合法列，重建禁用列与投影摘要；内外自签、全部分数/统计/哈希重算，combined 保留 | wrapper 可在自签下恢复；实际完整重训后 exit 1 |
| 05 hide-all-void-scores | 三模式全部有效 VOID 分数共 24,288 个改为 NaN；非 VOID 指标不变、成员哈希重签 | 实际完整重训后 exit 1 |
| 06 parent-original-external-pin | 完整父模型改偏置，重新预测所有分数、全部旧报告统计及模型/成员/两行 ledger 摘要；保留调用方原 pin | exit 1：父外部 ledger pin 不同，未进入训练 |
| 07 parent-new-self-pin-fresh | 同一完整父伪造候选由攻击者提供自己的新 pin；`verify_parent` 结构与自签校验可通过 | 旧源码从原输入实际 fit/predict 后拒绝；未开始新三模式 fit，exit 1 |
| 08 legal-recovery | 返回原父包与原控制输出，再次完整 fresh | exit 0，292 文件保持原摘要 |

03/04 的全部分组统计由独立脚本算式生成，不依赖生产 `scores/summarize/house_macro`。攻击文件没有覆盖原始或合法输出。不存在只删字段或只检查命名的替代验收。

受控独立 CLI 样本分母：96 帧，8 帧零候选；21,120 个公开有效去重对，13,024 个有监督、8,096 个 VOID。训练 13,440 对，其中 8,288 有监督（负 3,584 / 正 4,704），5,152 VOID；验证 7,680 对，其中 4,736 有监督（负 2,048 / 正 2,688），2,944 VOID。上述是审查 fixture 计数，不能写成真实仿真实验结果。

## 独立算术与标签隔离

脚本 `round1_numeric_probe.py`，日志 `round1-numeric-probe.log`，结果 `round1-controlled-artifacts/independent-numeric-check.json`，同一解释器与 `OPENBLAS_NUM_THREADS=1 PYTHONPATH=src:tests:tools` 执行，exit 0。

从受控父数组自行计算三组训练均值/标准差、类别频率、固定正则目标、训练梯度与全部逐帧 sigmoid 分数；不调用生产拟合/预测/评分来得到这些算术期望。全部有效 VOID 分数有限，combined 父模型/分数字节一致。梯度最大绝对值分别约 `2.40e-17 / 6.26e-14 / 6.26e-14`。逐帧、12 屋、两分区、所有类别及屋均值与报告在 `atol=rtol=2e-12` 下相符。

另做独立内存时序探针：固定同一 train X/y，观察确实三次 fit；仅当所有 288 次公开预测结束后，将验证 0/1 标签全部反转。结果 291 份模型/分数文件与实际原输出逐字节一致，只有报告改变。此时序探针直接调用生产 build 并显式插桩，不冒称另一个未插桩 CLI case。

20 次独立拒绝检查覆盖禁用列中的 NaN、Inf、负数（project/fit/predict）及完全重签的禁用列非零系数。回归集合另含 bool/int、错误 dtype/shape、非法模式、缺类/空输出矩阵与 checkpoint 外部 pin 检查。

## 证据绑定与限制

- 受控父 ledger pin：`d5588e80e6e971138c612740b7b9dca7b8e8889cf376613e50301a95235a16f1`。
- 受控 collection pin：`9d700eafe41d876a02d4678d01588c13949f13c94369f1c73f300a6ac57a51ab`；受控前端 ledger pin：`8e6742b4de3ec23126ac4d14d34f645055148d36b09ad9c35705ef1d32ba1b6c`。它们不替代真实 PR76 的外部信任锚。
- CLI 脚本 SHA256：`3641c413fab24ed9b72cf1776bbc042cd8e3082b68ae90401110020c515b362a`；数值脚本：`3766be51e03eb17e793e029688b33678d05cdb0648237d4fadac9714795e1729`。
- CLI 结果 ledger SHA256：`21e6563b02a5435fe93b56499356b3e86823a6250df6a6100e07aeb6dbe30054`；独立数值结果：`9cff71740a435c1463d5ffc3a176b9a63dc1305cef5a6938b91b58e03363b95a`。

本轮没有检验真实三模式效果、跨房屋泛化、物理深度表面归属、完整 mask、跨视角身份、对象位置/朝向校准、自然联合似然、记忆或动作闭环收益。单独检查点的结构与自签不证明拟合历史；证明来自调用方保留的原信任锚及实际 fresh 重训。受信任解释器/运行环境不是恶意沙箱，A 同机复核不等于 B 独立验收。R2 仍须在同一冻结源码上顺序执行；任何功能源码修改使本报告对新 SHA 不再适用。
