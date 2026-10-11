# 复现

从独立分支检出本轮最终源码；推断/runner/评分/测试`1421805b199cb949bc9510c802c4c5ce76ae8e69`，开发冻结`3a7f7367e49dacf441859ae69e7c86d1e28c8931`，附加证据工具`ece35b704519c5c224a32a9c6a2262d99a0d9479`。本机Python3.13.5，复用可用依赖环境但PYTHONPATH绑定本工作树src/tools；另一台电脑重建环境，不复制macOS虚拟环境。

```bash
export PYTHONPATH=src:tools
python -m pytest -q tests/test_current_location.py tests/test_executed_search.py tests/test_active_location_search.py tests/test_task_readout_repair.py tests/test_full_mechanism_value_diagnostic.py tests/test_structure_two_stateful_full_joint.py tests/test_structure_two_stateful_full_joint_adversarial.py
python tools/run_current_location.py --phase dev --output /tmp/current-main/dev
python tools/score_current_location.py /tmp/current-main/dev --output /tmp/current-main/dev-score.json
```

核对开发选择并冻结后，FROZEN指向开发freeze.json。本轮使用已提交的FROZEN_CONFIG.json。下列输出目录必须不存在。

```bash
FROZEN=docs/reviews/pc_a/current_location_inference_2026-10-11/FROZEN_CONFIG.json
python tools/run_current_location.py --phase test --freeze "$FROZEN" --output /tmp/current-main/test
python tools/run_current_location.py --phase integrate --seeds 64001 --conditions sparse32 long64 --freeze "$FROZEN" --output /tmp/current-main/integrate
python tools/run_current_location.py --phase test --seeds 64001 --conditions sparse32 --freeze "$FROZEN" --output /tmp/current-repeat
python tools/score_current_location.py /tmp/current-main/test --output /tmp/current-main/test-score.json
python tools/score_current_location.py /tmp/current-main/integrate --output /tmp/current-main/integrate-score.json
python tools/check_current_location.py --main /tmp/current-main --repeat /tmp/current-repeat --output /tmp/current-main/checks.json
python tools/package_current_location.py --main /tmp/current-main --repeat /tmp/current-repeat --output /tmp/current-evidence
```

评分/检查/汇总/归档仅标准库，不调用模型。冻结JSON绑定496来源文件的清单散列；新HEAD只增报告可通过，但推断/评分/测试/配置文件更改会明确失败。归档解压后重新评分与原件逐字节比较，检查/汇总对象相等。耗时仅在新进程导出对比时排除；归档本身保留原始全部字节。原始命令日志在main/logs。
