# 复现与审查入口

实际生产源文件版本 `d3e1d448261f0fef456aab4db32277cec6e6b938`，规范JSON对照工具 `9480c489a22036e1980a813eb83b28b5149d8c1f`；最终报告提交只添加证据和协作文档。审查PR103的具体head，勿把共享集成分支当成本轮已合并。以下从仓库根目录执行。

## 环境和权重

本机host `/private/tmp/cpswm-object-reid-venv/bin/python`（3.13.5）；组件 `/private/tmp/cpswm-object-memory-env-20261010/bin/python`（3.11.16）。分别保留requirements-host.txt和requirements-component.txt。不要把两个环境混装；Open3D worker不导入CPSWM的Python3.13代码。

原OpenCLIP权重由huggingface_hub下载：repo `laion/CLIP-ViT-H-14-laion2B-s32B-b79K`，revision `1c2b8495b28150b8a4922ee1c8edee224c284c0c`，file `open_clip_pytorch_model.bin`。完整SHA/字节数见MODEL.json；worker强制检查固定SHA，不能换成较小模型却沿用此结果。下载文件3,944,692,325 bytes，不提交Git。

另需原Mask R-CNN权重 `maskrcnn_resnet50_fpn_v2_coco-73cbd019.pth` 和owner继承入口要求的SSDLite `ssdlite320_mobilenet_v3_large_coco-a79551df.pth`，均来自`download.pytorch.org/models/`，原生产类仍核验完整SHA。SSDLite并不是本轮对象匹配前端。

```sh
export PYTHONPATH=src:tools:tests
export MPLCONFIGDIR=/private/tmp/cpswm-mpl-cache-20261010
TASK_HOST=/private/tmp/cpswm-object-reid-venv/bin/python
TASK_COMPONENT=/private/tmp/cpswm-object-memory-env-20261010/bin/python
TASK_CLIP=/private/tmp/cpswm-object-memory-models-20261010/models--laion--CLIP-ViT-H-14-laion2B-s32B-b79K/snapshots/1c2b8495b28150b8a4922ee1c8edee224c284c0c/open_clip_pytorch_model.bin
TASK_DOC=docs/reviews/pc_a/object_memory_integration_2026-10-10
TASK_PANEL=docs/reviews/pc_a/matched_transition_death_test_2026-10-09/evidence
```

其他机器调整这些本地路径并重新生成配置；不得直接移动旧SQLite然后把路径错误当模型失败。跨目录的完整owner便携性不是本轮已验收项目。

## 流程1和3：固定前端三臂

```sh
"$TASK_HOST" tools/run_object_memory_frontend.py \
  --root "$TASK_PANEL/natural-30-5-5" --manifest "$TASK_PANEL/manifest.json" \
  --output /private/tmp/object-memory-dev-new \
  --component-python "$TASK_COMPONENT" --weights "$TASK_CLIP" \
  --spatial current iou hybrid
```

输出目录必须不存在。`current`是当前参考特征序列，`iou`是CG组件map读点，`hybrid`保留同candidate内的参考特征点/缺失支持补回。driver只读取manifest约束的raw、prediction、masks；SDK评分另进程进行。

16帧历史源包为 `docs/reviews/pc_a/natural_mask_surface_2026-10-02/evidence/frozen-run.tar.gz`。解包到 `/private/tmp/cpswm-object-memory-holdout-20261010`（内含source和experiment目录）；使用本报告 `evidence/1deg-manifest.json` 或 `5deg-manifest.json` 作为manifest、解包目录作为root，运行同一命令。先保留全部输出再评分。

```sh
"$TASK_HOST" tools/summarize_object_memory.py \
  --development /private/tmp/cpswm-object-memory-d3e1-dev-20261010 \
  --one-degree /private/tmp/cpswm-object-memory-d3e1-1deg-20261010 \
  --five-degree /private/tmp/cpswm-object-memory-d3e1-5deg-20261010 \
  --output /private/tmp/object-memory-summary-new.json
```

汇总器的历史root绑定上面的解包路径；它是evaluator-only工具，绝不能导入推理进程。验算已封存结果：

```sh
"$TASK_HOST" "$TASK_DOC/verify_scores.py" . "$TASK_DOC/evidence" \
  /private/tmp/cpswm-object-memory-holdout-20261010 "$TASK_DOC/evidence/summary.json"
```

## 流程2：真实owner和同前端普通来源记忆

建立JSON配置，值为上述机器的实际绝对路径：

```json
{"python":"/private/tmp/cpswm-object-memory-env-20261010/bin/python","weights":"ABSOLUTE_PATH_TO_PINNED_CLIP","spatial":"iou","readout":"reference_feature_fallback"}
```

保存为 `/private/tmp/object-memory-frontend.json` 后：

```sh
"$TASK_HOST" tools/run_object_memory_owner.py \
  --root "$TASK_PANEL/natural-30-5-5" --manifest "$TASK_PANEL/manifest.json" \
  --output /private/tmp/object-memory-owner-new \
  --mask-weights /private/tmp/cpswm-matched-transition-assets-20261009/maskrcnn.pth \
  --ssdlite-weights /private/tmp/cpswm-object-memory-ssdlite-20261010.pth \
  --frontend /private/tmp/object-memory-frontend.json
"$TASK_HOST" tools/restore_object_memory_probe.py /private/tmp/object-memory-owner-new
```

普通基线自己按相同公开raw重新运行同一前端，保留全部历史；owner通过原命令/交付/consume接口和真实SQLite状态运行。中间来源撤回后双方用同一有效来源集合重算。`comparison-*.json`比较规范化JSON，包括全部前端字段；只去除owner增加的三个历史/计数字段。报告只忽略绑定不同容器的view hash。第二个命令冷启动恢复撤回前backup，检查完整state相等、runtime-helper替换拒绝和恢复后未变。保留3条replay delivery，新增物理动作0。

## 聚焦检查

```sh
CPSWM_SSDLITE_WEIGHTS=/private/tmp/cpswm-object-memory-ssdlite-20261010.pth \
CPSWM_MASK_WEIGHTS=/private/tmp/cpswm-matched-transition-assets-20261009/maskrcnn.pth \
"$TASK_HOST" -m pytest -q \
  tests/test_external_object_mapping.py tests/test_natural_mask_surface.py \
  tests/test_surface_action_model.py tests/test_surface_episode.py \
  tests/test_matched_transition_death_test.py tests/test_mask_surface_comparison.py
```

47 passed；测试用旧图像夹具 `docs/reviews/pc_a/owned_observation_update_2026-10-01/evidence/live-transactions.tar.gz` 也必须checkout。Ruff检查所有改动文件；mypy检查external_object_sequence.py、mask_surface_support.py、mask_surface_sequence.py通过。证据文件摘要清单为 `evidence/files.json`。
