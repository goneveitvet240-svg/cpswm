# 运行与核验命令

实际运行源码 `ee356b2393c1786fc87083d079b2d8517aa31e6f`。在该提交的独立、干净工作树运行，输出必须在工作树外。Mac本轮复用已有Python 3.13.5核心环境 `../envs/core/bin/python`；完整已安装包清单见 evidence/environment.json，Windows须按uv.lock重建，不能复制Mac环境。

```sh
../envs/core/bin/python -m pytest -o addopts='' -q tests/test_matched_value.py tests/test_current_event.py tests/test_current_event_adversarial.py tests/test_small_sim_framework.py
../envs/core/bin/ruff check tools/run_matched_value.py tools/verify_matched_value.py tests/test_matched_value.py
../envs/core/bin/ruff format --check tools/run_matched_value.py tools/verify_matched_value.py tests/test_matched_value.py
PYTHONPATH=src:tools ../envs/core/bin/python tools/run_matched_value.py --output /private/tmp/cpswm-matched-full-20261025
PYTHONPATH=src:tools ../envs/core/bin/python tools/run_matched_value.py --output /private/tmp/cpswm-matched-repeat-20261025
PYTHONPATH=src:tools ../envs/core/bin/python tools/verify_matched_value.py /private/tmp/cpswm-matched-full-20261025 /private/tmp/cpswm-matched-repeat-20261025 --output /private/tmp/cpswm-matched-verification-20261025.json
```

首次运行前半段独占本批诊断，后半段与第二次重复运行有时间重叠；记录wallclock与每臂observe/predict/feedback原始耗时，但不作为受控性能比较或显著性证据。每臂耗时不含构造、内部审计和额外full rerun参考。两个运行输出分别保留，不把重复当作新增独立样本。

完整重复核验只排除seconds/method_seconds两个计时字段，其余JSON（包括选择记录、逐步输入/动作/分布/状态/账本/RB、真值及manifest）全部匹配。source/环境共享，不能冒充B独立实现或认证。

初次4步预检查因旧D0 adapter缺少显式公开地图而退出1，原始manifest另存。修正专用adapter后第二次quick预检查退出0；正式证据仅使用上面的全运行。首次ruff检查格式问题经format修复；无生产模型修改。

## 解压存档与独立重评分

```sh
mkdir -p /private/tmp/matched-primary-extracted /private/tmp/matched-repeat-extracted
tar -xzf docs/reviews/pc_a/matched_value_2026-10-24/evidence/primary.tar.gz -C /private/tmp/matched-primary-extracted
tar -xzf docs/reviews/pc_a/matched_value_2026-10-24/evidence/repeat.tar.gz -C /private/tmp/matched-repeat-extracted
../envs/core/bin/python docs/reviews/pc_a/matched_value_2026-10-24/rescore_archived_actions.py --input /private/tmp/matched-primary-extracted --output /private/tmp/matched-rescored.json
PYTHONPATH=src:tools ../envs/core/bin/python tools/verify_matched_value.py /private/tmp/matched-primary-extracted /private/tmp/matched-repeat-extracted --output /private/tmp/matched-archive-verification.json
```

上述存档重评分工具随报告提交；运行源码的src/tools/配置/模型/协议哈希必须与manifest相符。清单同时列出压缩包与全部解压JSON的SHA256，原件不因报告压缩而改变。
