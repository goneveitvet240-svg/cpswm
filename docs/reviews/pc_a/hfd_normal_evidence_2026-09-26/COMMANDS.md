# 已执行与待执行命令

修后源码 cd687f92a3cf23922d94ac24b4b1f62b75ce85a9 的已执行命令：

```sh
.venv/bin/python -m pytest -o addopts='' -q tests/test_full_hfd_training.py docs/reviews/pc_a/hfd_normal_evidence_2026-09-26/audit_round1.py
```

结果21通过，原始日志在 evidence/round1-repaired.log。首审原始四失败在 evidence/round1-original-b692ef1.log。第二轮尚无执行命令或结果，不伪造回执。

下面只是后续真实数据入口，用前必须先取得完整作者摘要一致的归档并完成第二轮审查，不表示已经运行：

```sh
.venv/bin/python tools/inspect_hfd_training_archive.py --archive <verified-training-set> --metadata <enrolled-public-evidence> --output <new-evidence-directory>
.venv/bin/python tools/inspect_hfd_training_archive.py --archive <verified-training-set> --metadata <enrolled-public-evidence> --output <same-evidence-directory> --verify
```

只允许训练分区；在独立工作目录按uv.lock重建Python3.13.5和dev/perception/hand-perception环境，不重用macOS虚拟环境到Windows。不把分片或作者结果目录当作已通过的完整视频数据。
