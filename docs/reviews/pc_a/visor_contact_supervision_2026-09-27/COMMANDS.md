# 复核入口

代码7fba64d39699be5e47fe1b9867583ac8c3854f62，锁环境由 `uv sync --frozen --extra dev --extra perception --extra hand-perception` 创建。全部实际参数、时刻和返回码见evidence/final-02/commands.json；7命令均exit0，914 Python前后同Git。原失败见final-01，不将其真实导入失败隐藏。

完整顺序执行：

```sh
.venv/bin/python docs/reviews/pc_a/visor_contact_supervision_2026-09-27/run_frozen.py --source /path/to/closed/raw --output /path/to/new-run
```

`--source` 指向本地完整备份的raw目录，五个固定文件及来源身份见SOURCES.json；CLI不接受调用者自填新摘要。执行器先首审/二审，再mypy/Ruff，然后创建全485帧包、新进程从源重验、第三进程实际组件读取。输出必须是新目录，不覆盖旧证据。相邻来源包测试包含本地socket特殊文件攻击，需要环境允许本机临时文件夹具；没有跳过该测试。

现成包重验：

```sh
.venv/bin/python tools/prepare_visor_contact_supervision.py --source /path/to/closed/raw --output /path/to/closed/final-02/packet --verify
```

组件读取：`cpswm.data_preflight.visor_contact_supervision.load_contact_component(source, packet)`。返回源重建的inputs、targets及scope report。targets中的binary_contact_target为True/False/None；None保持原始不同状态，不用于二分类损失。此返回值不是完整提议训练样本，也不自动开启优化器、模型或行动。

本机Python3.13.5，图像以Pillow12.3.0解码；无GPU、付费资源或新依赖版本选择。B须按自己的环境重建并记录实际Python/平台/锁，不能复制本机venv或沿用A自审作为独立验收。
