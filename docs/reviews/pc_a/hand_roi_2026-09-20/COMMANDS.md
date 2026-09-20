# 固定源码复现与B交接

最终生产源码：`e0e572baf602c0e75bf834fd8e9f2aabe62da90b`。
A分支：`codex/pc-a-hand-roi-supervision-20260920`，叠加PR30，未合并。
B状态：未复核。本文件是交接入口，不代表已接受。

环境依照uv.lock重建，不复制macOS虚拟环境：

```sh
uv sync --frozen --extra dev --extra perception --extra hand-perception
uv run mypy src
uv run pytest -ra tests/test_hand_person_regions.py tests/test_archive_media_timeline.py tests/test_hand_object_evidence.py tests/test_core4d_range_reader.py tests/test_natural_hands.py tests/test_interaction_evidence.py tests/test_natural_vision.py tests/test_continuous_state_recovery.py tests/test_structure_two_continuous_input.py tests/test_structure_two_raw_rgbd_ingress.py
```

公开数据获取复用PR30的命令。新增分割只供评价：

```sh
uv run python tools/fetch_core4d_segmentation_supervision.py --output output/datasets/core4d-evaluator-segmentation --cache output/datasets/core4d-segmentation-cache
```

真实推断用 `tools/run_person_interaction_video.py`，与PR30命令保持视频/模型SHA、采样和裁剪一致，只新增 `--hand-person-rois`。
023：17秒，024：19秒；2fps；crop 500 0 1000 900；detector fasterrcnn。
模型和原视频SHA见PR30报告及本轮实际结果source_files/source_sha256。
最终实际命令/摘要及压缩完整记录在evidence。
输出目录须新建，不覆盖旧基线或失败运行。

B应核查：原始与作者监督分离；同源坐标与区域数量；三个新反例修前失败/修后拒绝且状态不变；
合法区域空输出/部分输出、SQLite恢复；实际像素和全图子通道与旧基线相同；
重复候选不计物理手、不把分割行号当视频帧号。
组件测试、真实前端运行、自然P5闭环、科学收益四栏分别记录。
最终整体两轮验收仍待自然闭环实现，不能由本轮两份组件审核抵扣。
