# 复现与B交接

固定代码 `b391400d7272510067cd5b1173843077cb92091c`；本批叠加PR29，未合并共享集成。
下面路径占位符按本机目录替换；公开数据与模型文件不提交Git，B需自行重建环境和取得相同工件。

```sh
uv sync --frozen --extra dev --extra perception --extra hand-perception
.venv/bin/python tools/fetch_core4d_development_subset.py --endpoint https://hf-mirror.com --output DATASET --cache CACHE
# 仅失败的未完成目录可继续；已存在成员/元数据不一致则拒绝覆盖：
.venv/bin/python tools/fetch_core4d_development_subset.py --endpoint https://hf-mirror.com --resume-incomplete --output DATASET --cache CACHE
.venv/bin/python tools/fetch_core4d_motion_supervision.py --endpoint https://hf-mirror.com --sequence 20231002/023 20231002/024 --output DATASET/evaluator/motion --cache SUPERVISION_CACHE
```

默认端点为huggingface.co；本机使用明确记录的公共镜像。没有密码、访问申请或付费计算。
镜像元数据和CRC不等于验证全部LFS档案或独立作者签名。源代码固定作者版本，不使用可变main拉数据。

```sh
.venv/bin/python tools/run_person_interaction_video.py --video DATASET/raw/allocentric_RGBD_videos_mp4/20231002/023/camera1/color.mp4 --sha256 74b0abaaaa278101f4db19179b168ca38a67bccc7edbc7863c7c73ca885fd79c --source-url https://huggingface.co/datasets/leolyliu/CORE4D/tree/81bb2bb876a4a54ac94e67c788d7c31364f1c43e/CORE4D_Real/allocentric_RGB_videos --crop 500 0 1000 900 --duration 17 --fps 2 --detector fasterrcnn --weights FASTER_RCNN_PATH --hand-model HAND_MODEL_PATH --output NEW_OUTPUT
```

024同样命令：改视频序列为024、duration为19、视频SHA为
`6ef090d63a86d0e3086dd33a21fb7ea49cbf3d8b23858320791c2d3196d63f5e`，输出新目录。
这些是保留的开发裁剪，非模型自动选视角，非原始曝光时刻或连续真实动作结果。

```sh
.venv/bin/python -m pytest tests/test_archive_media_timeline.py tests/test_hand_object_evidence.py tests/test_core4d_range_reader.py tests/test_natural_hands.py tests/test_interaction_evidence.py tests/test_natural_vision.py tests/test_continuous_state_recovery.py tests/test_structure_two_continuous_input.py tests/test_structure_two_raw_rgbd_ingress.py -q
.venv/bin/mypy src
.venv/bin/python tools/run_continuous_unity_camera.py --sdk-python SDK_PYTHON --binary AI2THOR_BINARY --weights SSDLITE_PATH --mode transport-probe --max-actions 2 --output NEW_UNITY_OUTPUT
```

A本机已核验环境位置：
- SDK：`/Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/.venv-ai2thor/bin/python`，ai2thor5.0.0。
- Player：`/Users/pangwei/.ai2thor/releases/thor-OSXIntel64-f0825767cd50d69f666c7f282e54abfe58f1e917/thor-OSXIntel64-f0825767cd50d69f666c7f282e54abfe58f1e917.app/Contents/MacOS/AI2-THOR`。
- 二进制SHA256：`d8bbfbee47581f4aa4f5df71e095f0a1c00888bed7b493eaffcc0f37d6364df3`。
- 数据：主项目`output/datasets/core4d-development-20260920`。

本机MediaPipe/Unity需要正常macOS图形服务；受限进程无法初始化并不构成模型正确性失败。
B不得复制macOS虚拟环境直接当Windows环境。请独立检出源码、固定权重/数据摘要，记录平台差异、
通过/失败/跳过和自己的STATUS_B，使用独立B分支/PR交接。
B本次尚未复跑；本文件是复核入口，不能记录B通过。
重点复核合法迟到/多相机、媒体回执跨源/重签、恢复与原状态、分卷缓存/中断，以及未校准测量不越权。
完整自然GroundedTransition、角色/位姿误差、P5、反证执行与科学比较仍未交付。
