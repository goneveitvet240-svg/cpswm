# 复跑入口

基于报告绑定的完整 SHA 检出单独 A 工作目录，在 Python 3.13.5 中执行：

```sh
uv sync --frozen --python 3.13.5 --extra dev --extra perception --extra hand-perception
.venv/bin/python docs/reviews/pc_a/full_support_compute_2026-09-26/run_frozen_validation.py \
  --main /Users/pangwei/Documents/ai/continual-personalized-semantic-world-model \
  --output output/full-support-compute-20260926/reproduction
```

`--main` 只定位已经获得的原始开发检查点、四段官方视频和已校验 Faster R-CNN 权重；不从该目录导入项目源码。执行环境独立重建，输出目录必须不存在。原始视频/模型不提交 Git，工件清单提供 SHA-256。

入口顺序固定：第一审与关联回归 → 第二审及完整重封恢复攻击 → mypy/Ruff → 派生三臂执行检查点 → 三臂 303 完整支持密集/分块数值对照及恢复 → 四段视频固定四帧试验。每个子命令单独日志和退出码；任一受控验证失败立即停止，视频失败保留后继续其余预定片段，以免只报告成功片段。

每条命令前后对 src/tests/tools/pc_a 审核目录中的受版本控制 Python 文件做 Git blob 和 SHA-256 对照。`commands.json` 记录开始 UTC、耗时、退出码和完整 argv；`source-before.json`/`source-after.json` 为同源依据。报告限定具体文件范围，未把工具运行称为 B 独立审核。

本地 stdout 不含最终结果不代表失败：较大完整支持会在一个臂完成后才输出进度。CPU 2 线程、无收费 GPU；没有后台远程训练。
