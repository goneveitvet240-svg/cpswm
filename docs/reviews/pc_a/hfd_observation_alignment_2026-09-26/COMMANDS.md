# 固定版本复跑

基础PR44 `34ad8d35f12d74bd6c2c357e73db32b69b9e5add`；真实执行Python `1c180cfdecc35bed0233d89646201398c5b1217d`，最终双审 `dc2c23183d244a443fae05494912b6cd7619d81a`（仅第二审脚本改变，src/tools/tests逐字相同）。分支 `codex/pc-a-hfd-observation-alignment-20260926`。先fetch、读取协作状态，勿覆盖他方活动目录。

```sh
uv sync --frozen --extra dev --extra perception --extra hand-perception
.venv/bin/python docs/reviews/pc_a/hfd_observation_alignment_2026-09-26/run_frozen_alignment.py --main /path/to/local-data-root --output output/your-new-run
```

Windows用 `.venv/Scripts/python.exe`；main参数指向包含相同 `output/` 数据目录的本地根目录，不是macOS工作树绝对路径。源归档、作者元数据及PR44完整包复现见前轮报告；不能以同一不可信包中取得的摘要冒充独立来源针。

执行器默认依次运行首轮79检查、第二轮14检查、mypy、Ruff、全归档源验证及原帧对齐、独立新进程从原归档重建、真实视觉前端。每条命令前后对所有受控Python计算摘要并与Git blob比对；命令、开始时间、时长、退出码保存在commands.json。中途失败不继续，保留目录，修后用新输出目录从首轮重新开始。不要在运行中修改Python。

真实执行只消费已源重建的runtime子目录与固定既有Faster R-CNN权重。该入口的manifest参数是调用方持有的来源针；本身不能认证第三方自报的runtime清单。评价数据由完整源重建验证，前端明确不读取该目录。主程序生成完整候选或整体资源拒绝，不把截断候选当完整分布；本轮没有调用三种提议网络进行新评分或训练。

OpenCV解码、CPU环境及两轮自审只在本机实测。跨平台解码差异需由B记录，不能把A同实现新进程重建称为独立实现或跨机复现。B需特别复核完整伪造正路径、合法重试、旧入口兼容、标签排序置换以及原帧到语义记忆/动作后果。

最终交付还将旧RGB-D、手部和连续入口纳入首轮，共138检查；精确参数和4条命令退出码见 `evidence/final-audit-02/commands.json`。将其中Python和工作树路径替换为本地环境后按顺序执行。真实执行7命令见 `evidence/final-02/commands.json`，总执行器exit0；生产代码和依赖实现没有因审查加强而改变，未将第二审脚本更新冒充新的真实数据实验。
