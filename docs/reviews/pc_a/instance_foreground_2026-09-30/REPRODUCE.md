# 渲染实例像素亲和度开发基线复现

实际功能源码`0a8a2384c321c3a2dc14cf218854754161af9ffd`，base为PR74 head `d698792a8e3750af284a2c991a28aff2453b0729`。生产任务路径与依赖不改；新增纯开发学习模块、公开/私有分离的数据helper、训练CLI及三个测试文件。后续文档交付SHA与实际功能SHA分开。

输入需要两个分别外部钉住的历史包，不改写其源码身份：

1. PR73采集原件仅用collection-attempt02；inventory外部SHA256固定`9791a946543b9158890324d3ff35a80ea04d51c9cabb6e09540f569abd903d47`。完整获取方式见父PR73的DELIVERY.md。历史采集源码的865份Python文件须匹配`e88f50752ca50843fc5382b853c65abe134f1281`；只含文档差异的5a2a963目录可用。
2. PR74完整前端原件包SHA256 `19f379aefd42434e311bba00b5116fdc9f562f73982b67e280244bf038742177`；其中case-results.json外部SHA256固定`517fc5b24afd80e4311d0de66dcfa6d113de6cd11763d61aeaaecd345740ccf6`。四条旧run/verify记录所绑定的两方法全部public/report/inputs必须逐件匹配。历史前端源码869份Python文件须匹配`3babc6d1557b4fe54abc6c8ac1f6054cdeb03e57`；文档版d698792目录可用。本轮复用这些固定检测结果，不宣称重新运行两个检测器。

先由原采集CLI验证原件、SDK环境和Mac二进制，再对公开缓存执行外部ledger pin、旧源码身份、原collection输入、完整96帧同动作同分区核验。不能拿本轮新增Python目录替代865/869份历史身份。历史SDK解释器须使用虚拟环境入口，不解析symlink跳到基础解释器。原Mac运行身份不等于Windows复现。

实际本轮复用Python3.13.5开发环境，OPENBLAS_NUM_THREADS=1；历史SDK为原Python3.11.16环境。具体版本见runtime-environment.json。没有新增依赖/下载权重/独立重建环境。

在当前功能源码根目录执行，替换路径变量；输出必须是全新且与各输入/源码互不包含的目录：

```sh
PYTHONPATH=src:tests:tools OPENBLAS_NUM_THREADS=1 .venv/bin/python tools/run_instance_affinity.py \
  --collection "$COLLECTION_ATTEMPT02" --capture-source "$FROZEN_CAPTURE_SOURCE" \
  --archive "$PROCTHOR_TRAIN_ARCHIVE" --sdk-python "$SDK_VENV_PYTHON" \
  --binary "$ORIGINAL_UNITY_BINARY" --frontends "$PR74_FRONTEND_ARTIFACTS" \
  --frontend-source "$FROZEN_FRONTEND_SOURCE" --output "$NEW_EXPERIMENT_OUTPUT" \
  --inventory-sha256 9791a946543b9158890324d3ff35a80ea04d51c9cabb6e09540f569abd903d47 \
  --frontend-ledger-sha256 517fc5b24afd80e4311d0de66dcfa6d113de6cd11763d61aeaaecd345740ccf6
```

追加`--verify`会从原始公开RGB-D、钉住的候选框和离线mask重新构建全部像素对，重新从train标签拟合、恢复checkpoint、预测全部96帧并计算评价，然后逐文件比较全部新产物与保存目录。不是读回旧模型后自验。多余文件、symlink、旧pin下共同改写输入或输出均拒绝。首次拟合若缺少任一标签类会明确失败，不据验证集改变采样或目标。

固定顺序：96帧公开特征→仅64训练帧监督→训练并恢复模型→全部96帧公开特征预测→32验证帧标签/评分。历史来源核验本来会读取私有数据，此调用顺序不是恶意进程隔离；模型接口只接八维公开数值特征。所有mask资格/未知/冲突、零候选与不可用深度均保留。

每个公开框8×8网格，只取中心在半开框内的像素；去重后全部无序不同点对，按同动作同规范像素对跨框/两前端去重。监督两端唯一属于合格渲染mask才0/1，其余VOID=-1。训练有效对计算均值/尺度和频率常数，固定L2=0.01、30步阻尼Newton；没有验证选型或分割接受阈值。输出是未校准亲和分数，没有自动实例ID、完整mask、位置或语义权限。

产物`model.json`保存可移植参数、固定配置、训练特征/标签摘要、类频率与优化记录。`frames/000`至`095`分别保存features/pairs/valid/targets/scores的NPY、公开来源/候选归属JSON及私有标签审计JSON。无效score在NPY中为NaN，对应valid=false；不会纳入有监督损失。`report.json`绑定每件文件、源码、两个外部输入以及逐帧/逐屋/分区的实际分母。公开特征文件与私有监督文件分开；训练目录整体不是可直接传给线上模型的输入。

定向回归命令：

```sh
PYTHONPATH=src:tests:tools OPENBLAS_NUM_THREADS=1 .venv/bin/python -m pytest -q -o addopts='' \
  tests/test_instance_affinity.py tests/test_instance_affinity_dataset.py tests/test_run_instance_affinity.py \
  tests/test_offline_frontend_diagnostic.py tests/test_offline_frontend_evaluation.py \
  tests/test_surface_factor_diagnostic.py tests/test_offline_factor_manifest.py \
  tests/test_offline_factor_worker.py tests/test_offline_factor_capture_verifier.py \
  tests/test_offline_factor_collection.py tests/test_offline_factor_orchestration.py \
  tests/test_offline_factor_asset_provenance.py
```

冻结前344 passed in107.87s。两轮顺序A辅助审查、实数据拟合和新进程重算结果分别见对应报告/日志；该回归不是全仓CI/B独立/科学收益。BCE/Brier用于当前开发学习诊断，不是正式自然任务验收；开发验证已经被上一轮观察。两模型/框/像素对和旋转视角有相关性，不视为独立试验。
