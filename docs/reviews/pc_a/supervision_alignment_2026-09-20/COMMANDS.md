# 固定源码与B复核入口

源码：3534e9796bb2aae99b594a330671a1328ddf5ccf；A独立分支codex/pc-a-supervision-alignment-20260920，叠加PR31。
B复核未执行。原始数据获取沿用PR30/31脚本，三份清单身份固定如下；不要复制Mac虚拟环境。

```sh
uv sync --frozen --extra dev --extra perception --extra hand-perception
uv run pytest -ra tests/test_supervision_alignment.py tests/test_natural_event_coverage.py tests/test_core4d_range_reader.py
uv run mypy src
uv run python tools/audit_core4d_supervision_alignment.py --dataset PATH_TO_CORE4D_SUBSET --output NEW_OUTPUT_DIRECTORY --raw-manifest-sha256 f949b5bc8ac6c0297fded51db9eb4e3d525cf3499931daa596c0765b222026e0 --motion-manifest-sha256 fef29ac8945da8e4818c3d791cda627c56ea775432ea4da577a6fbdc72eb55e9 --mask-manifest-sha256 6ce8f10d991ff8c8daf6c2aaeed19520ae78781d547f648c525723cd05aca064
```

需要PATH中的ffmpeg/ffprobe；作者分割不送入模型。输出目录必须新建，失败产物不覆盖。
检查7个非刚体行及原数据未改、两条时间轴、所有假设未授权、没有事件/身份标签、源码前后摘要。
评分只是辅助核查，不能以最高分或平均得分更高宣布对齐成立。
