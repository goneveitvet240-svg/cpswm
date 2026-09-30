# Archive → Native 公开输入准备（不是实验）

已按预声明的 frame ordinal → candidate(method,id) → canonical grid(u,v) 顺序选定第 **000** 帧、第 0 个候选、第 0 个有效网格点。没有跳过更早帧、候选或像素；没有读取私有 mask、targets、supervision 或 SDK 实例标签来选择。

- 原件：`/Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/output/offline-factor-data-20260930/collection-attempt02/house-01/public/000-state.json`；固定采集顺序对应 house 01 / SDK index 004。
- 候选：`ssdlite / de8a15ab-6a24-503c-87e3-f3dbd7646311`；框 `[1.7716217041015625, 14.789138793945312, 317.8302001953125, 316.30072021484375]`。框来自 PR76 公开候选，并逐字段对应外部 PR74 账本钉住的公开检测结果。没有重新检测或依据类别/分数挑选。
- seed：`[21, 33]`；原始 rendered depth 为 `2.960951805114746` m。完整 8×8 去重网格 64 点均 public-valid；完整坐标、逐点有效性及网格摘要在 JSON。这里不判定任何实例身份，也未计算训练位置代表点。
- 原始 action：`09cab850-18ce-4329-9d45-189d6df2a0b8`；receipt：`2fd74e969fb5ae2fed7f63f14978c230b972ee7f565fd0fac93b6abe939a90d6`。
- 原 raw tuple binding：`c5cd7dd0741ae73f5fb89d10d978b969cec35297169ef9d51b5c88d178970399`；原始 household/session/trace、三通道 UUID、envelope/payload 摘要、深度单位和完整相机自位姿均保留在 JSON。
- 语义锚：`T = 2026-09-30T14:18:52.085281+00:00`，严格取原 received/capture/arrival 最大值再加 1 秒。尚未创建语义 fixture 或 semantic_record_id；原始时间、包和 offline command 均未改写。

本次核验使用历史外部 pin：PR76 ledger `32e0dc7cec8fce6dfca5bc36755cfba5cf3551b454c1f746f20ac2076936e842`；PR74 ledger `517fc5b24afd80e4311d0de66dcfa6d113de6cd11763d61aeaaecd345740ccf6`；PR73 inventory `9791a946543b9158890324d3ff35a80ea04d51c9cabb6e09540f569abd903d47`。检查两批 ledger 的完整 run/verify 成功形状、PR74 public/inputs 字节与双 ledger、inputs 与原 inventory 表、PR76 当前公开帧、house 01 capture + 8 个 public 原件摘要，随后通过 `_public` 原 transport 契约校验 8 帧的配对/scope/时间，并从原 depth 重建网格有效性。所有读取的原件在写准备产物前再次逐件核对未变；脚本审计钩子只允许这 17 个公开/来源文件及两个新准备输出。没有把 inventory 中私有文件的摘要表核对称为逐个私有原件复验。

命令在 `/private/tmp/cpswm-pc-a-soft-position-factor-20261001` 下使用 `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests:tools OPENBLAS_NUM_THREADS=1 /private/tmp/cpswm-pc-a-camera-checkpoint-fixture-20260930/.venv/bin/python` 的 heredoc 执行，exit 0；导入 `_public`、`decode_unity_rgbd`、`grid_pixels`、`pixel_pairs`、canonical hash，未调用模型 fit/predict/restore、未加载 checkpoint、未启动 Native/Unity。transport 模块传递导入了 Torch，只有依赖导入，没有模型构建或权重加载。原命令和输出在工具会话可见；本次没有另造原始日志。

JSON SHA256：`0d1a0e2241acb0e41fd93da1896288fc217551162d651ae16ef1b88e893f1538`。这是输入准备，不替代新轮 fresh CLI 复核，也不产生位置训练或自然闭环证据。新软位置归档完成后仍须用实际完整 neighborhood 对应候选来源、64 点、RGB-D、有效性、全部权重与代表点；不可只比较 XYZ 或强改 ID。原 offline command 不得伪称 owner-issued camera。四个 estimator/reference 组合继续保留；仅实际 fit 成功项进入后续 active/no-factor 受控 Native 对照，失败项保留原因，身份关联仍明确为受控 fixture。
