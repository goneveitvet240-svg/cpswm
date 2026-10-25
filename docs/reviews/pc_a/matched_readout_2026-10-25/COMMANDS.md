# 复现与边界

实际源码 `d3465ee69b9451bc1d458bcb0b12ab587a3eba2c`，干净独立工作树。使用核心Python3.13.5环境，Windows按锁文件重建，勿复制Mac环境。输出目录必须在工作树外且不存在。

```sh
../envs/core/bin/python -m pytest -o addopts='' -q tests/test_matched_readout.py tests/test_matched_value.py tests/test_current_event.py tests/test_current_event_adversarial.py
../envs/core/bin/ruff check tools/analyze_matched_readout.py tests/test_matched_readout.py
../envs/core/bin/ruff format --check tools/analyze_matched_readout.py tests/test_matched_readout.py
PYTHONPATH=src:tools ../envs/core/bin/python tools/analyze_matched_readout.py --output /private/tmp/cpswm-readout-final-20261025
PYTHONPATH=src:tools ../envs/core/bin/python tools/analyze_matched_readout.py --verify --output /private/tmp/cpswm-readout-final-20261025
```

解压evidence/points.json.gz为另一个临时目录下的points.json，同时复制summary.json和manifest.json，即可使用--verify重算。必须保留原始字节，manifest绑定points和summary哈希及全部关联源码/模型/协议。verify只重算存档；完整推断重放需运行第一条collect命令。PR123的原始压缩包55成员在collect前验证hash，并对其绑定的生产源码/旧runner逐文件核对，不接受不同来源替换。

实际collect和verify均退出0；最终50测试全部通过无跳过。第一版完整运行仅用于发现/核对历史端点统计的范围，最终交付只采用d3465ee重跑。没有新的机器人执行、调参或独立确认集。
