# 固定新数据的前端诊断复现

实际功能源码为 `3babc6d1557b4fe54abc6c8ac1f6054cdeb03e57`，base为PR73 head `5a2a963d7f3b9fc8c3084e0b50d1696b2a7314f2`。本轮只增加两个工具和两个测试，不修改生产src、模型权重、正式阈值或采集原件。后续文档交付SHA应与本功能SHA分开。

1. 完整采集原件来自PR73的三卷压缩包，先按其DELIVERY.md连接并校验整包SHA `6264e670f4a848918285f04ec0c1f6ca98a28f52027313c525e9e2cfce43db29`。只使用其中collection-attempt02，不把第一批失败数据并入本轮。第二批inventory外部pin固定为 `9791a946543b9158890324d3ff35a80ea04d51c9cabb6e09540f569abd903d47`。
2. 准备独立历史采集源码目录，对应 `e88f50752ca50843fc5382b853c65abe134f1281` 的src/tests/tools全部865份Python文件。本轮工具增加了分析文件，不能拿本轮目录覆盖历史源码身份，也不能为通过检查重签旧configuration。仅有文档差异的PR73目录也可以，其Python文件哈希必须逐件匹配采集configuration。
3. 本轮实际复用Python3.13.5开发环境，详细版本见runtime-environment.json。历史SDK入口仍为Python3.11.16的虚拟环境入口，不将symlink解析为系统Python。历史verify还检查原官方TRAIN压缩包、AI2-THOR源码及Mac Unity/Python二进制pin；本轮没有建立独立环境或宣称Windows复现。跨平台/B复核须单列实际环境与适用性，不重写旧pin。
4. 两个模型分别使用现有固定官方本地权重：fasterrcnn_resnet50_fpn_v2_coco-dd69338a.pth、ssdlite320_mobilenet_v3_large_coco-a79551df.pth。模型构造器验证完整SHA，不下载替代权重；minimum_score沿用原默认0.5开发设置。category配置沿用apple，但仅调用measurements()输出全部类别，没有调用decode()的类别归约，也没有按私有标签选择候选。

从新功能源码根目录执行，变量替换为自己的路径；输出目录必须不存在且在输入原件之外：

```sh
PYTHONPATH=src:tests:tools .venv/bin/python tools/diagnose_offline_frontend.py \
  --collection "$COLLECTION_ATTEMPT02" --capture-source "$FROZEN_CAPTURE_SOURCE" \
  --archive "$PROCTHOR_TRAIN_ARCHIVE" --sdk-python "$SDK_VENV_PYTHON" \
  --binary "$ORIGINAL_UNITY_BINARY" --weights "$PINNED_WEIGHTS" \
  --output "$NEW_DIAGNOSIS_OUTPUT" --detector fasterrcnn \
  --inventory-sha256 9791a946543b9158890324d3ff35a80ea04d51c9cabb6e09540f569abd903d47
```

SSDLite使用对应权重、`--detector ssdlite`和另一全新输出目录。每个方法固定全部12屋96帧，无候选或无可见目标照常保留。追加`--verify`对已保存目录会再次完整推理96帧，重新读SDK全矩阵并重算摘要，与public/report/inputs三个文档作类型敏感规范化内容比较；不只是比较文件自身哈希。输出文件多余、缺失、symlink或重复JSON key均拒绝。

采集目录的原件身份先在其历史源码下完整核验；本轮神经模型只接收公开观测，先完成全部96帧推理，再做私有全矩阵评价。此源码输入隔离与调用顺序不声称是恶意Python进程隔离。

`run_fixed_diagnosis.py`保存本机实际批命令和顺序，成功输出的逐文件摘要随case-results.json记录。每次模型完整运行和新进程verify各一项；失败如实保留，不替换房屋/帧。`analyze_results.py`只接收四项均成功且与逐文件pin一致的输出，再检查固定96动作/每屋8帧/数值相机8视角/分区/同原件同源码同实例，调用冻结summarize重算。跨视角对象数按实际相机位置、yaw、pitch去重，不以UUID或像素差异代替视角。

测试命令：

```sh
PYTHONPATH=src:tests:tools .venv/bin/python -m pytest -q -o addopts='' \
  tests/test_offline_frontend_diagnostic.py tests/test_offline_frontend_evaluation.py \
  tests/test_surface_factor_diagnostic.py tests/test_offline_factor_manifest.py \
  tests/test_offline_factor_worker.py tests/test_offline_factor_capture_verifier.py \
  tests/test_offline_factor_collection.py tests/test_offline_factor_orchestration.py \
  tests/test_offline_factor_asset_provenance.py
```

本轮定向集合为231项。顺序双审、开发期失败、完整伪造正路径和真实模型结果分别保留；不将A辅助审查写为B独立验收，不将几何重叠写为语义准确率、校准位置或闭环任务收益。具体执行结果以REPORT.md、双审报告与case-results.json为准。
