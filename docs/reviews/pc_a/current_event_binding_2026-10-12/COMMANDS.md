# 实际运行与复核命令

本机Python 3.13.5：`/private/tmp/cpswm-object-reid-venv/bin/python`。以下命令在本分支工作树执行，使用项目已有依赖；工作目录不是原用户工作树。最终推断/runner/独立评分/定向测试来源为 `8ca11cbe2ad42d0f256ba000dcfad513f8134bb5`，辅助检查/支持诊断为 `b852242de94845fb74baa4de26fa41cb34aac4be`。原生默认基准已实际重跑，产物在 `5796af8ae384c54bbb248810b9b5fd33ec3ca832` 更新。

## 最终运行

```sh
export PYTHONPATH=src:tools
PY=/private/tmp/cpswm-object-reid-venv/bin/python
$PY tools/run_current_event.py --phase dev --output /private/tmp/cpswm-current-event-final/dev
$PY tools/run_current_event.py --phase test --freeze /private/tmp/cpswm-current-event-main/dev/freeze.json --output /private/tmp/cpswm-current-event-final/test
$PY tools/run_current_event.py --phase test --freeze /private/tmp/cpswm-current-event-main/dev/freeze.json --seeds 66001 --conditions sparse32 --output /private/tmp/cpswm-current-event-final-repeat
$PY tools/probe_current_event.py --output /private/tmp/cpswm-current-event-final/revisions.json
$PY tools/diagnose_current_event_support.py --output /private/tmp/cpswm-current-event-final/support-diagnostic.json
$PY tools/score_current_event.py /private/tmp/cpswm-current-event-final/dev --output /private/tmp/cpswm-current-event-final/dev-score.json
$PY tools/score_current_event.py /private/tmp/cpswm-current-event-final/test --output /private/tmp/cpswm-current-event-final/test-score.json
$PY tools/check_current_event.py --main /private/tmp/cpswm-current-event-final --repeat /private/tmp/cpswm-current-event-final-repeat --output /private/tmp/cpswm-current-event-final/checks.json
$PY tools/compare_current_event_receipt_fix.py --before /private/tmp/cpswm-current-event-main --after /private/tmp/cpswm-current-event-final --output /private/tmp/cpswm-current-event-final/repair-comparison.json
$PY tools/package_current_event.py --main /private/tmp/cpswm-current-event-final --repeat /private/tmp/cpswm-current-event-final-repeat --output docs/reviews/pc_a/current_event_binding_2026-10-12/evidence
```

`FROZEN_CONFIG.json`是第一次留出前的选择，不因补修而重新选型；上述test/repeat实际读取其原始副本。最终dev重跑仅核对同样选择及开发成本。默认dev为7/8，test为66001–66004，两个条件sparse32/long64。factor与matched_factor配置相同，明确复用同一物理运行；索引中的逻辑标签数不能当作实际运行数。

## 定向测试

```sh
PYTHONPATH=src:tools /private/tmp/cpswm-object-reid-venv/bin/python -m pytest -o addopts='' -q \
  tests/test_current_event.py tests/test_current_event_adversarial.py \
  tests/test_current_event_task_receipt.py tests/test_shared_location.py \
  tests/test_current_location.py tests/test_executed_search.py \
  tests/test_active_location_search.py tests/test_task_readout_repair.py \
  tests/test_full_mechanism_value_diagnostic.py \
  tests/test_structure_two_stateful_full_joint.py \
  tests/test_structure_two_stateful_full_joint_adversarial.py \
  tests/test_structure_two_w3_native_posterior_projection.py \
  --junitxml=/private/tmp/current-event-final-tests.xml
```

149通过；不是全仓、S1或B独立复核。原合法路径回执失败和历史源码绑定失败保留，后者通过实际重跑旧默认基准修复，未放松断言。旧默认基准整体summaries相同，不能称全部输出字节相同。

## 归档复算

`evidence/raw-main.tar.gz`及`raw-repeat.tar.gz`封存最终运行，`MANIFEST.json`逐成员记录SHA256和长度。`ARCHIVE_VERIFY.json`来自实际解压及重新评分：dev/test评分JSON逐字节一致，检查及汇总对象一致。`repair-comparison.json`核对修复前后48次开发/留出运行，忽略wall_seconds和新增task_readout_actions后逐对象相等。

评分器仅依赖标准库和已有标准库评分工具，不调用原生推断。检查器另外校验501个推断/运行/评分来源文件；它要求匹配源码工作树，不能在随意变化的分支上声称来源一致。可解压为`main/`和`repeat/`后，将上面的评分、检查命令路径替换为解压目录；`--repository`指向最终来源文件一致的工作树。

`pre_receipt_fix/`保留首批52次实际运行及旧格式检查。旧归档必须在 `5796af8ae384c54bbb248810b9b5fd33ec3ca832` 工作树使用当时工具评分，新严格评分器会拒绝缺少task_readout_actions的旧格式。首批/最终共享相同数据，不能合计为104次独立研究试验。

`support-diagnostic.json`是固定开发前缀的候选与实际系统采样复现，未修改采样方法或科学参数；`revisions.json`只验证原生位置因子来源的后续重放，不宣称全局所有组件同步撤回事务完成。
