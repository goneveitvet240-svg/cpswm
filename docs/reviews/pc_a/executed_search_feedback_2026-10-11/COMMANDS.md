# 复现命令

base/PR108 `6aeb772a37931d429f07b6934f3fbe9ac34f6e66`；推断、runner、评分及12项新增测试`c5b53ba3dede16c33cec50449875772d1eb20925`；开发冻结、篡改/重复、汇总与封存工具`7e13fd9defbad8d6a89a8299dc51c185b7edbc9f`。描述性记忆效应/分组最终版本`fcd0d4a636229e0a0d8a87f90acef0a2200b6e3f`。跨机器新建工作目录和虚拟环境，按项目依赖安装，不复制macOS解释器或.git指针。本机Python3.13.5，`/private/tmp/cpswm-object-reid-venv/bin/python`。

```bash
export PYTHONPATH=src:tools
python -m pytest -q tests/test_executed_search.py tests/test_active_location_search.py tests/test_task_readout_repair.py tests/test_full_mechanism_value_diagnostic.py tests/test_structure_two_stateful_full_joint.py tests/test_structure_two_stateful_full_joint_adversarial.py
python tools/run_executed_search.py --phase dev --condition sparse32 --output /tmp/executed-main/dev-sparse32
python tools/score_executed_search.py /tmp/executed-main/dev-sparse32 --output /tmp/executed-main/dev-sparse32-score.json
```

开发冻结后，下列三条留出命令可作为独立进程运行；默认新seeds63001–63010，每条件六臂真实独立运行。

```bash
python tools/run_executed_search.py --phase test --condition complete32 --output /tmp/executed-main/test-complete32
python tools/run_executed_search.py --phase test --condition sparse32 --output /tmp/executed-main/test-sparse32
python tools/run_executed_search.py --phase test --condition long64 --output /tmp/executed-main/test-long64
python tools/score_executed_search.py /tmp/executed-main/test-complete32 --output /tmp/executed-main/test-complete32-score.json
python tools/score_executed_search.py /tmp/executed-main/test-sparse32 --output /tmp/executed-main/test-sparse32-score.json
python tools/score_executed_search.py /tmp/executed-main/test-long64 --output /tmp/executed-main/test-long64-score.json
python tools/run_executed_search.py --phase test --condition sparse32 --seeds 63001 --output /tmp/executed-repeat/sparse32
python tools/check_executed_search_artifacts.py /tmp/executed-main/test-sparse32 --repeat /tmp/executed-repeat/sparse32 --output /tmp/executed-main/artifact-checks.json
python tools/summarize_executed_search.py /tmp/executed-main --output /tmp/executed-main/combined.json
python tools/package_executed_search_evidence.py --main /tmp/executed-main --repeat /tmp/executed-repeat --output /tmp/executed-evidence
```

评分/篡改/重复/汇总/封存仅用标准库，不调用模型推断。运行输出目录必须新建；source.json记录实际HEAD与推断/配置文件散列，开发后源码清单必须保持不变。解压后四份评分要求JSON字节一致，检查与汇总要求对象相同。跨进程run文件只排除wall_seconds，保留全部原件；运行内未导出的快照UUID不在该一致性声明内。
