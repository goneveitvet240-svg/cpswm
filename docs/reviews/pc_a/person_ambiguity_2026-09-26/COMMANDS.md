# 复跑

从本轮完整报告指定的源码 SHA 检出独立目录，按 uv.lock 安装 dev/perception/hand-perception 后执行：

```sh
.venv/bin/python docs/reviews/pc_a/person_ambiguity_2026-09-26/run_frozen_person.py --main <原始数据所在主仓> --output <新的证据目录>
```

执行器依次进行两轮自审、mypy/Ruff、全部原始337训练试次重建、独立新进程复验、固定128原帧/32短窗口感知与身份条件汇总。每条命令前后核对全部受控 Python 文件与 Git 对象及 SHA256；失败即停止，旧失败结果保留。macOS MediaPipe 即使显式 CPU 推理也需本机图形服务完成初始化。

来源是已登记 HFD training 归档，不访问 validation/test；评价者的作者标签保持隔离。实际调用参数、耗时和退出码以 evidence 的 commands.json 为准。
