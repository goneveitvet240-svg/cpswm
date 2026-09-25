# B 独立复跑入口

拉取任务分支，核对生产源码与 `40486b981898cb9420fdafe765c9ac49e8e5ff96` 的 `src/tests/tools` 逐文件相同。审核脚本在后续证据提交中。B 自建环境，不能复制 macOS 虚拟环境。

```sh
git fetch origin --prune
uv sync --frozen --extra dev --extra perception --extra hand-perception
.venv/bin/python docs/reviews/pc_a/runtime_candidates_2026-09-26/run_checks.py output/candidate-regression
.venv/bin/python -m pytest -o addopts= -q docs/reviews/pc_a/runtime_candidates_2026-09-26/audit_round1.py
.venv/bin/python -m pytest -o addopts= -q docs/reviews/pc_a/runtime_candidates_2026-09-26/audit_round2.py
```

预期 444 回归、7 第一轮、10 第二轮；mypy 361 文件。三个网络各实际运行 88 个完整六操作候选，303 候选超预算必须原子拒绝。完整伪造正路径涵盖重新评分/采样/重封摘要；同时应明确外部摘要被一并替换时，不具有来源认证能力。

真实视频使用固定政策 `configs/data/bimanual_pixel_policy.json`，沿用先前四视频原始包、已登记 Faster R-CNN 权重及 PR37 第二轮训练目录。A 的持久输入根为主仓 `output`，目录结构已写在 runner 中，B 可复制合规媒体/权重工件或依原公开来源重新取得，不复制 `.venv`：

```sh
.venv/bin/python docs/reviews/pc_a/runtime_candidates_2026-09-26/run_real_checks.py /absolute/path/input-output-root output/candidate-real
```

runner 固定每段前 0.2 秒/10 Hz 两帧；必须全部四段×三网络，不选择成功窗口。输出路径须不存在。逐条检查 `manifest.json` 的实际 argv/退出码/源码摘要，及每段 `result.json`、像素回执/输入文件、完整支持和三个快照。实际视频产生的只有 bootstrap 操作，不应要求或伪造父粒子。

每次恢复需匹配实际源码、PyTorch、线程和权重绑定；跨机器若版本不同，应重新产生本机工件并报告差异，不修改预期摘要过门。记录 B 自己的 SHA、环境、完整伪造结果和账本/动作后果；A 的本机结果不代替 B 签收。
