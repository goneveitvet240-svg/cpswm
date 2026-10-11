# 复现命令与来源

仓库 https://github.com/goneveitvet240-svg/cpswm ，独立分支 `codex/pc-a-shared-location-prediction-20261011`。推断/runner/标准库独立评分/新增测试 `51dd6f261aa04249b88dbc56c839fc2f7a67173f`，开发冻结 `15bd64a51f6c0cda3759b0f34cfc399b297368de`，辅助验证 `33308ff21f3bec563726b3563da1f41e3078c0c6`，最终描述性汇总 `bbf15e44ecb572ad56ef7199059564d70a3616a8`。后者只补支持集外失败及真实轨迹描述，没有重调参数/改变原始动作。

本机工作目录 `/private/tmp/cpswm-pc-a-shared-location-prediction-20261011`；Python 3.13.5，解释器 `/private/tmp/cpswm-object-reid-venv/bin/python`。下面用python指代已按项目依赖建立的该解释器；异机须新建环境，不复制macOS虚拟环境。运行参数与产物保存在raw-main、raw-repeat归档。

```sh
PYTHONPATH=src:tools python -m pytest -q tests/test_shared_location.py tests/test_current_location.py tests/test_executed_search.py tests/test_active_location_search.py tests/test_task_readout_repair.py tests/test_full_mechanism_value_diagnostic.py tests/test_structure_two_stateful_full_joint.py tests/test_structure_two_stateful_full_joint_adversarial.py
PYTHONPATH=src:tools python tools/run_shared_location.py --phase dev --output /private/tmp/cpswm-shared-location-main/dev
PYTHONPATH=tools python tools/score_shared_location.py /private/tmp/cpswm-shared-location-main/dev --output /private/tmp/cpswm-shared-location-main/dev-score.json
PYTHONPATH=src:tools python tools/run_shared_location.py --phase test --freeze /private/tmp/cpswm-shared-location-main/dev/freeze.json --output /private/tmp/cpswm-shared-location-main/test
PYTHONPATH=tools python tools/score_shared_location.py /private/tmp/cpswm-shared-location-main/test --output /private/tmp/cpswm-shared-location-main/test-score.json
PYTHONPATH=src:tools python tools/run_shared_location.py --phase integrate --freeze /private/tmp/cpswm-shared-location-main/dev/freeze.json --seeds 65001 --conditions sparse32 long64 --output /private/tmp/cpswm-shared-location-main/integrate
PYTHONPATH=tools python tools/score_shared_location.py /private/tmp/cpswm-shared-location-main/integrate --output /private/tmp/cpswm-shared-location-main/integrate-score.json
PYTHONPATH=src:tools python tools/run_shared_location.py --phase test --freeze /private/tmp/cpswm-shared-location-main/dev/freeze.json --seeds 65001 --conditions sparse32 --output /private/tmp/cpswm-shared-location-repeat
PYTHONPATH=src:tools python tools/probe_shared_location_revisions.py --output /private/tmp/cpswm-shared-location-main/revisions.json
PYTHONPATH=tools python tools/check_shared_location.py --main /private/tmp/cpswm-shared-location-main --repeat /private/tmp/cpswm-shared-location-repeat --output /private/tmp/cpswm-shared-location-main/checks.json
PYTHONPATH=tools python tools/package_shared_location.py --main /private/tmp/cpswm-shared-location-main --repeat /private/tmp/cpswm-shared-location-repeat --output /private/tmp/shared-location-reproduced-evidence
```

运行输出目录必须新建，避免覆盖原证据。开发270、测试480、完整适配器32、实际重复16，共798；另44个撤回/恢复步骤。测试98通过；第一轮测试曾有一个不正确的任意概率下界断言，已在模型/测试冻结前改为独立数值计算并通过。初次失败、最终通过和实验日志均保留在raw-main/logs；没有把首次失败隐藏成始终全绿。未运行全仓测试。

归档包含原始输入、隔离评分真值、每步计划与真实付费回执、配置、来源manifest、原生审计、修订及日志。920成员逐文件size/SHA256验证，解压后3个评分JSON逐字节重算一致，checks/summary对象一致。顶层MANIFEST.json给出归档与每成员hash；ARCHIVE_VERIFY.json给出回执。这是本机独立实现复算，不是B独立设备验收。

交付前再次fetch确认：集成 `19ddf26830348a2f0b33f0af54d6ba702c5cfb1c`、上游PR110 `b97e00eb9cd2793a52e18fed46abb14a8a8ec5f0`、B `fd4ca6ef5e81c90d7cf7987b42c0b2810d8a810a` 未变。原工作树和STATUS_B不修改，草稿堆叠PR110，不自动合并。
