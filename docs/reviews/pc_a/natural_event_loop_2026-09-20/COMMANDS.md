# 复现入口

在本分支根目录执行；输出目录必须新建，禁止覆盖旧结果。完整输入路径在本机主项目
`output/datasets/hocap-development-20260915` 和 `output/datasets/hocap-additional-20260920`。
数据与模型不提交Git；本批evidence包含原始成员清单、哈希和范围下载来源。

```sh
uv sync --frozen --extra dev --extra perception --extra hand-perception
.venv/bin/python tools/fetch_hocap_development_subset.py --windows midpoint suffix --frame-count 60 --download-budget-mib 256 --output output/hocap-additional --cache output/hocap-range-cache
.venv/bin/python tools/audit_natural_event_coverage.py --dataset output/hocap-additional --raw-manifest-sha256 0b8d5fe14d6416f1afe6fcf93e95166291aab9ec234a83f2dc4aa69019632250 --annotation-manifest-sha256 461ea1c4c0a9cdc09d5a63044af5367b7d068fceb418e646b75e0ba66b4e36c3 --receipts-sha256 a7c3969afc892051656a07b72c696fd81e8bd9926eb834f491e4daa77120e573 --output output/coverage-recreated
.venv/bin/python tools/prepare_hocap_development_archive.py --raw-root output/hocap-additional/raw --manifest output/hocap-additional/raw_manifest.json --manifest-sha256 0b8d5fe14d6416f1afe6fcf93e95166291aab9ec234a83f2dc4aa69019632250 --output output/hocap-wire
```

转换器会输出当前receipt hash；重新转换source_sha随检出版本变动，因此按实际输出传入，
不要强用旧receipt。下面参数占位符需要替换成已验证的本地文件／运行摘要值。

```sh
.venv/bin/python tools/run_natural_vision_archive.py --archive output/hocap-wire --manifest-sha256 RECEIPT_SHA --weights FASTER_RCNN_WEIGHT_PATH --detector fasterrcnn --hand-model HAND_MODEL_PATH --output output/real-inference
.venv/bin/python tools/evaluate_natural_hands.py --dataset output/hocap-additional --raw-manifest-sha256 0b8d5fe14d6416f1afe6fcf93e95166291aab9ec234a83f2dc4aa69019632250 --annotation-manifest-sha256 461ea1c4c0a9cdc09d5a63044af5367b7d068fceb418e646b75e0ba66b4e36c3 --hand-frames output/real-inference/hand_frames.json --hand-frames-sha256 HAND_FRAMES_SHA --output output/hand-evaluation
.venv/bin/python tools/check_natural_hand_recovery.py --raw-root output/hocap-additional/raw --raw-manifest output/hocap-additional/raw_manifest.json --raw-manifest-sha256 0b8d5fe14d6416f1afe6fcf93e95166291aab9ec234a83f2dc4aa69019632250 --weights FASTER_RCNN_WEIGHT_PATH --hand-model HAND_MODEL_PATH --output output/real-hand-recovery
.venv/bin/python -m pytest tests/test_interaction_evidence.py tests/test_hocap_development_input.py tests/test_natural_hands.py tests/test_natural_event_coverage.py tests/test_natural_vision.py tests/test_continuous_state_recovery.py tests/test_structure_two_continuous_input.py tests/test_natural_geometry.py tests/test_pose_observation_model.py tests/test_joint_camera_policy.py -q
.venv/bin/mypy src
```

本机macOS上，受限进程的MediaPipe图形服务初始化失败（即使配置CPU），正常本机进程则成功。
失败不是模型正确性或数据能力结果。日志原样保留；本轮不作运行速度比较。

最初360帧运行绑定c8fe8d5；后续恢复修复必须使用最终源码的独立审核／回归／实际恢复结果，
不能把旧版本完整推断自动升级为新源码同次自然P5运行。
