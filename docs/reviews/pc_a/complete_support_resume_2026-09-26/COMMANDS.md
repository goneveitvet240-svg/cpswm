# 固定复跑

独立检出报告源码65aa8b35050b0eb85b04200e867e9dc00d746307，按uv.lock重建Python3.13.5、dev/perception/hand-perception环境，然后：

```sh
.venv/bin/python docs/reviews/pc_a/complete_support_resume_2026-09-26/run_frozen_validation.py --main <containing-original-outputs-project> --output <new-validation-directory>
```

main只定位已登记的原视频、原权重及旧失败输入，不从它导入代码。执行顺序为不同双审、mypy/Ruff、显式65,536派生、三臂完整303对照、默认32,768派生与三臂旧失败原子性、四段各四帧视频。所有候选保留。

每条命令前后核对受控Python文件与Git对象以及SHA-256。原始commands.json、source-before/after.json及子命令日志保留。视频失败后仍执行其他预定片段，但总执行器会返回失败，不能再将“执行完列表”解读为整个矩阵通过。

只有原始输入存在并通过来源检查才能执行真实矩阵；不允许夹具冒充缺失真实数据。CPU两线程，无远程付费训练。这个命令是A修复方复验，不能替代B跨机独立复核。
