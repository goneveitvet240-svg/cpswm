# 固定源码与 B 复核入口

源码 `5188e65986eab9f6345ec03231968858296bd8aa`；分支 `codex/pc-a-handover-phase-supervision-20260920`，叠加 PR32。B尚未复核。保留独立目录，不覆盖已有文件或Mac虚拟环境。

```sh
uv sync --frozen --extra dev --extra perception --extra hand-perception
uv run pytest -o addopts='' -q tests/test_handover_phase_supervision.py tests/test_core4d_range_reader.py tests/test_hand_object_evidence.py tests/test_natural_hands.py tests/test_natural_event_coverage.py
uv run mypy src
uv run python tools/fetch_bimanual_phase_subset.py --output NEW_DATA_DIRECTORY --cache NEW_RANGE_CACHE
uv run python tools/inspect_bimanual_phase_subset.py --dataset NEW_DATA_DIRECTORY --manifest-sha256 HASH_OF_NEW_MANIFEST --output NEW_AUDIT_DIRECTORY
uv run python tools/run_bimanual_pixel_frontend.py --video NEW_DATA_DIRECTORY/raw/clip-0001/camera-1.mp4 --weights LOCAL_FASTER_RCNN_WEIGHTS --hand-model LOCAL_MEDIAPIPE_HAND_MODEL --output NEW_PIXEL_OUTPUT
```

需要PATH中的ffmpeg/ffprobe。本次A清单SHA：`621626525ee58468394943b35cd638f8bb7b622f09deffe448a5304f0e0c2f37`，归档见acquisition-manifest.json。复取清单range_bytes可能受缓存影响而不同；先比较21个member/local_path/bytes/SHA/CRC，而不是默认为同一清单。作者整包MD5未验证；每个选择成员ZIP CRC验证、HTTP区间回执及SHA保留。

模型沿用公开torchvision Faster R-CNN：`fasterrcnn_resnet50_fpn_v2_coco-dd69338a.pth`，SHA `dd69338a24b8d7381807e247652bdc356325bcbaf1cd3e092e00e0a1a58706bf`；MediaPipe `hand_landmarker-1.task`，SHA `fbc2a30080c3c557093b5ddfc334698132eb341044ccee322ccf8bcf3607cde1`。入口内部校验权重，不读作者CSV、不给予者/接收者身份答案。四个片段各跑camera-1；camera-2前两段应拒绝，后两段可独立复核。

验证重点：两份全零视频显式无效；4片段760作者行、6有效视角290帧、16角色阶段边界；同步无实测误差上界、3帧超出作者时间域仍unknown。代理阶段不能授权接触/释放似然。交换合法原作者相机/序列member应拒绝；重复列、缺值、超宽、未闭合引号应拒绝。

发布视频底部烧录Reach/Transfer/Retreat，禁止完整帧作为模型输入。仅限六份SHA allowlist，固定从1920×1080裁成上方1920×960，无CLI覆盖裁剪选项；保存original SHA、crop、wrapper/policy源码SHA及result SHA。检查模型保存的.npy确为960×1920×3，并与对应冻结视频裁剪采样逐字节比较。采样网格是ffmpeg 10Hz输出，不冒充每帧原曝光时刻。

评审限制：两位本机独立组件审核不是Windows B验收，也不是最终两轮整体P5验收。无独立接触真值、视觉角色绑定、姿态校准、自然记忆更新或动作；完整框架范围保持。
