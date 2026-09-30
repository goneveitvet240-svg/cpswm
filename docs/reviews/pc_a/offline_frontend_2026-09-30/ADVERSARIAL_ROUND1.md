# 固定离线公开前端：第一轮对抗审查

结论：在下述冻结版本和覆盖范围内，未发现阻止进入第二轮审查的新阻塞项。231 项定向测试通过，完整受控产物的独立伪造被公开入口的原件绑定／重新推理比较拒绝；两种生产检测器在合成 8 视图上保存后重新推理一致。此结论不批准直接跳过第二轮进行实数据推理。

## 身份与范围

- 日期：2026-09-30。执行者：电脑 A 的辅助审查子任务；不是电脑 B 独立验收，也不是独立标签托管。
- 工作树：`/private/tmp/cpswm-pc-a-offline-front-end-20260930`。
- 冻结 SHA：`3babc6d1557b4fe54abc6c8ac1f6054cdeb03e57`；base：`5a2a963d7f3b9fc8c3084e0b50d1696b2a7314f2`。
- 开始与结束均核对 HEAD；`git status --short` 空，源码和测试未修改。`git diff --check 5a2a963..HEAD` exit 0。
- 阅读完整增量：两个工具、两个新测试及交接／计划／接口文档；追踪既有 `_public`、`reconstruct_catalog`、生产 detector 的固定权重与绑定路径。
- 本轮没有启动 Unity，没有对 `collection-attempt02` 或其他真实仿真归档做推理，没有训练、校准、语义映射、目标参考点选择或在线记忆写入。
- 远端同步由父任务负责；本报告结论只绑定上述本地冻结源码，不另作最新远端状态声明。

## 执行命令与结果

工作目录均为上面的冻结工作树；解释器为 `/private/tmp/cpswm-pc-a-camera-checkpoint-fixture-20260930/.venv/bin/python`，`PYTHONPATH=src:tests:tools`。

实际环境：CPython 3.13.5、NumPy 2.5.2、Torch 2.13.0、Torchvision 0.28.0、pytest 9.1.1。这里是前端分析环境；不冒充历史采集 SDK 的 Python 3.11 环境。

```sh
PYTHONPATH=src:tests:tools /private/tmp/cpswm-pc-a-camera-checkpoint-fixture-20260930/.venv/bin/python -m pytest -q tests/test_offline_frontend_diagnostic.py tests/test_offline_frontend_evaluation.py tests/test_surface_factor_diagnostic.py tests/test_offline_factor_manifest.py tests/test_offline_factor_worker.py tests/test_offline_factor_capture_verifier.py tests/test_offline_factor_collection.py tests/test_offline_factor_orchestration.py tests/test_offline_factor_asset_provenance.py
```

退出码 0，231 项通过。工具捕获结果为三行各 72 个通过点加末行 15 个通过点；项目默认 `addopts=-q` 与命令 `-q` 叠加，因此没有 pytest 最后统计行。另以 `--collect-only -o addopts='' -q` 核对相同九文件集合为 231 项，保存到 `round1-collected-tests.log`；这是收集核对，不是第二次测试运行。

```sh
PYTHONPATH=src:tests:tools /private/tmp/cpswm-pc-a-camera-checkpoint-fixture-20260930/.venv/bin/python /Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/output/offline-front-end-20260930/round1_probe.py > /Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/output/offline-front-end-20260930/round1-probe.log 2>&1
PYTHONPATH=src:tests:tools /private/tmp/cpswm-pc-a-camera-checkpoint-fixture-20260930/.venv/bin/python /Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/output/offline-front-end-20260930/round1_production_probe.py > /Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/output/offline-front-end-20260930/round1-production-probe.log 2>&1
```

两个独立探针均 exit 0。探针属于报告证据，不纳入仓库源码；修改报告证据不会被当成生产源码修复。

## 合法路径与完整伪造路径

`round1_probe.py` 先生成受控的 12 屋 × 8 帧完整公共 RGB-D／自位姿与私有实例目录，通过真实几何、评价和摘要代码产生 96 帧结果，再重复 96 次受控 detector 推理并比较保存文件。合法路径接受。受控 detector 明确不是自然模型；这个合成批次不是满足真实资产隔离规则的采集验收替代物。

| 独立攻击 | 完整性／后果 | 实际结果 |
|---|---|---|
| 全部原本不合格实例升格 | 所有帧中同时更改 `eligible`、排除原因和保留的 eligibility；重新计算完整摘要，合格独立实例由 24 改为 36 | `fresh report differs`；拒绝且不覆盖伪造原件 |
| SDK 两种对象参照整体平移 | 所有 SDK pivot、AABB center 及保留的审计坐标同时平移 7 m；重新计算每个候选 × 实例 × 样本的两组位移及摘要 | `fresh report differs`；不是仅缺字段或旧哈希攻击 |
| 完整零候选伪造 | 同时清空每帧公开 detector／owned support／geometry 候选及私有评价候选，保留全部实例、96 帧零矩阵并重算摘要与公开预测哈希 | `fresh public differs`；不能将已有候选伪装成成功保存的零候选结果 |
| JSON 布尔改成数字 | 完整 report 中 `training_performed: false` 改为 `0`；Python 字典相等仍为真 | 类型敏感内容哈希比较拒绝：`fresh report differs` |
| 输入资格与本地清单共同重签 | 完整 runtime audit 所有行升格且清空原因，再重算 collection inventory；保留调用方原来的外部 pin | `collection external pin differs`，在历史 verifier 子进程前拒绝 |

原始合法输出及四类完整伪造保留于 `round1-controlled-artifacts/` 的独立目录；原／伪造 runtime audit、原／新清单及 pin 也保留。没有用新 pin 替换原信任锚来宣称攻击失败。

现有定向测试补充覆盖了：外部 pin／原件／历史源码破坏；历史 verifier 非零或伪成功、数值布尔、额外状态与运行中原件变化；公开推理在缺少私有目录时仍可完成；96 次公开推理先于私有评价；SDK owner、相机、mask 和表面点错配；全实例 × 全候选矩阵中的不可见、零重叠、重复框、空候选和无效深度；房屋／分区与实例审计不一致；CLI `--verify` 对真实重新计算输出进行比较；输出额外文件和重复 JSON key 等既有严格读取边界。旧采集状态机、时间归属与资产解析测试也全部保留通过。

## 生产模型的受控运行检查

`round1_production_probe.py` 仅使用 `build_capture` 产生的合成常值图像、深度与 8 个固定姿态，没有读取真实仿真像素。通过未替换的 `make_decoder → PixelCategoryOutcomeDecoder.measurements → predict_public_house → evaluate_frame → summarize → save_or_verify`，分别新建两次检测器并重新推理：

| 检测器 | 固定本地权重 | 两次帧数／候选数 | 保存重验 |
|---|---|---|---|
| SSDLite | `ssdlite320_mobilenet_v3_large_coco-a79551df.pth` | 每次 8 帧／0 候选 | 接受，完整文档哈希两次均 `dee95173bbbf9c01736e122f275c434b6d7862e18c5baa11d15370be17efc84a` |
| Faster R-CNN | `fasterrcnn_resnet50_fpn_v2_coco-dd69338a.pth` | 每次 8 帧／0 候选 | 接受，完整文档哈希两次均 `9d42e393d655e072f420fd50838240b8fc7d4d2497caa512c14665a6daced1ff` |

权重来自主项目 `output/models/torchvision/`，生产构造器执行自身固定 SHA 检查。合成捕获原件、保存 public/report/inputs 在 `round1-production-artifacts/`；日志保留模型 binding、耗时与两次文档哈希。此项支持实际模型调用和零候选正路径可运行，不支持任何检测准确率、非零候选质量或真实场景表现结论。

## 关键边界及限制

1. 外部信任入口是 CLI 的固定 collection pin、匹配历史源码的完整 verifier 与当前公开重新推理。`summarize` 只校验传入矩阵的结构／算术一致性，不是独立真值验收器：上述完整参照／资格伪造可在内部一致时通过单独摘要，但无法通过保存结果对新推理的比较。未来若复用 helper，必须保留外层绑定，不能直接把自洽摘要当作验收。
2. 公开输入只有 RGB-D、获准的理想相机自位姿和来源标识；私有 SDK ID、mask、位置与资格只进入后置评价。公开候选的世界实例、对象中心、朝向、概率和记忆权限没有被本轮赋值。这个同进程次序及源码检查不是恶意 Python 环境隔离或独立托管证明。
3. 房屋 1–8／9–12 的固定分区、不可见实例和零覆盖保留；资产隔离来自通过原件绑定的历史 runtime audit，不来自前端词表。完整资产曝光不等于所有场景资产无交叉。COCO 与 SDK `objectType` 原生词表仍分开，任意框／mask 重叠不是正确类别识别或实例关联。
4. 距离只对实际 mask-member 表面样本计入分布，SDK pivot 与 AABB center 分别保留；不是校准误差，也未隐式选择正式对象位置参考点。不同 RGB-D／位姿哈希仅去重输入，不代表独立统计样本。
5. 本轮完整 96 帧非零候选后果依赖明确的受控 detector；生产模型本轮只在合成 8 帧的零候选路径上补验。真实固定 96 帧两种模型的完整运行、持久化重验、经验覆盖结果以及自然实例／位置观测因子训练仍未完成，应在第二轮通过后分别记录。

下一步：将本报告交父任务，按相同冻结 SHA 顺序启动第二轮；若源码改变，当前通过不自动继承给新 SHA。
