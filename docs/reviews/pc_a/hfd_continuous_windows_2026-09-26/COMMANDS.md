# 可复跑命令

从本轮分支建立独立工作目录；不要复用 macOS `.venv` 或跨机器 `.git` 指针。按项目锁文件运行 `uv sync --frozen --extra dev --extra perception --extra hand-perception`。

完整串行运行入口（`--main` 指向已有、来源固定的下载/模型存放根；`--output` 必须不存在）：

```sh
.venv/bin/python -u docs/reviews/pc_a/hfd_continuous_windows_2026-09-26/run_frozen_windows.py --main /path/to/source-storage --output /path/to/new-output
```

执行器先校验所有受跟踪 src/tests/tools/A 审查 Python 文件与 Git blob 相同；每条命令前后重查。依次执行首审、二审、mypy、Ruff、原归档重建、新进程原归档复核、128 原帧真实前端。真实前端使用 CPU 两线程、既有 Faster R-CNN 与 MediaPipe 手模型；不下载或训练新模型。

每条完整 argv、实际开始 UTC、退出码、秒数、源码 SHA 均保留在 `evidence/*/commands.json`，stdout/stderr 在同目录日志；失败记录不会由正式重跑覆盖。包内 manifest 摘要不可替代这一步原始源验证。
