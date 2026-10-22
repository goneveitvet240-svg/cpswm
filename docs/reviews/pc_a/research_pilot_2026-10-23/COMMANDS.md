# 复现命令

源码：`2e9694b3d08ebed0f361b342253b40740199e672`。在该版本仓库根目录，使用满足 uv.lock 的 Python 3.13 核心环境。Mac 本次复用相邻 `../envs/core/bin/python`；不要复制该虚拟环境至 Windows。以下输出目录须位于工作树外，以保持运行源码干净。

```sh
PYTHONPATH=src:tools ../envs/core/bin/python tools/run_research_pilot.py --part finite --output /private/tmp/cpswm-research-pilot-finite.json
PYTHONPATH=src:tools ../envs/core/bin/python tools/run_research_pilot.py --part e0 --output /private/tmp/cpswm-research-pilot-e0.json
PYTHONPATH=src:tools ../envs/core/bin/python tools/run_research_pilot.py --part e2 --output /private/tmp/cpswm-research-pilot-e2.json
../envs/core/bin/python -m pytest -o addopts='' -q tests/test_research_pilot.py tests/test_structure_two_particle_falsifier.py tests/test_current_event.py tests/test_current_event_adversarial.py tests/test_small_sim_framework.py
../envs/core/bin/ruff check tools/run_research_pilot.py tests/test_research_pilot.py
../envs/core/bin/ruff format --check tools/run_research_pilot.py tests/test_research_pilot.py
```

Windows 在自己重建的核心环境中设置 `PYTHONPATH=src;tools`，使用对应 python 和工作树外输出路径。每个报告保存源码 SHA、git status、Python/platform、协议哈希；模型/配置由运行 SHA 绑定。代码退出非零时仍先保存数值失败证据。正式三个运行均退出 0。

测试第一次发现诊断器恢复后事件索引与生产生成制度候选的时点不符，以及 proposal 概率乘除顺序造成字节差异；已在诊断器修复，生产推断未修改。最终测试 67 passed / 1 skipped。跳过项为核心环境没有可选 MuJoCo，不影响事件模型诊断；本次没有重新执行 π0.5/机器人。
