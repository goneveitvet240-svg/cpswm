# 实际运行与复核命令

环境为本机Python 3.13.5，已有独立环境`/private/tmp/cpswm-object-reid-venv/bin/python`，在本分支工作树运行。推断、runner、独立评分和测试源码`b2910c7a0d06f71aefb46d26b70456d984543926`；开发冻结、独立辅助复核/合并/归档工具及实际重跑默认基准`7cd811103b03961881be3aa4c1c46b066e3e3ba4`。检查器随后补充候选数、冻结清单和分片seed对应核验；其最终来源见REPORT.md。后续交付文档不改变推断来源文件。

## 开发与留出

```sh
export PYTHONPATH=src:tools
PY=/private/tmp/cpswm-object-reid-venv/bin/python
$PY tools/run_particle_support.py --phase dev --sampler systematic --output /private/tmp/cpswm-particle-support/dev/systematic
$PY tools/run_particle_support.py --phase dev --sampler stratified --output /private/tmp/cpswm-particle-support/dev/stratified
$PY tools/score_particle_support.py /private/tmp/cpswm-particle-support/dev/systematic --output /private/tmp/cpswm-particle-support/dev/systematic/score.json
$PY tools/score_particle_support.py /private/tmp/cpswm-particle-support/dev/stratified --output /private/tmp/cpswm-particle-support/dev/stratified/score.json
```

开发实际运行完成、独立评分通过并提交FROZEN_CONFIG.json之后才启动留出。沿用PR112的v06、共享位置头参数和24粒子，无再次选型/调参；开发只用于验证修复。留出按两种采样各拆两个不相交seed分片并行执行，分片复制结果字节不改，重新编排文件名和索引中的episode序号；合并记录每个原件hash。并行运行的墙钟时间不能作为独立的延迟优势比较。

```sh
$PY tools/run_particle_support.py --phase test --sampler systematic --seeds 67001 67002 --output /private/tmp/cpswm-particle-support-shards/systematic-a
$PY tools/run_particle_support.py --phase test --sampler systematic --seeds 67003 67004 --output /private/tmp/cpswm-particle-support-shards/systematic-b
$PY tools/run_particle_support.py --phase test --sampler stratified --seeds 67001 67002 --output /private/tmp/cpswm-particle-support-shards/stratified-a
$PY tools/run_particle_support.py --phase test --sampler stratified --seeds 67003 67004 --output /private/tmp/cpswm-particle-support-shards/stratified-b
$PY tools/merge_particle_support_shards.py --first /private/tmp/cpswm-particle-support-shards/systematic-a --second /private/tmp/cpswm-particle-support-shards/systematic-b --output /private/tmp/cpswm-particle-support/test/systematic
$PY tools/merge_particle_support_shards.py --first /private/tmp/cpswm-particle-support-shards/stratified-a --second /private/tmp/cpswm-particle-support-shards/stratified-b --output /private/tmp/cpswm-particle-support/test/stratified
$PY tools/score_particle_support.py /private/tmp/cpswm-particle-support/test/systematic --output /private/tmp/cpswm-particle-support/test/systematic/score.json
$PY tools/score_particle_support.py /private/tmp/cpswm-particle-support/test/stratified --output /private/tmp/cpswm-particle-support/test/stratified/score.json
$PY tools/run_particle_support.py --phase test --sampler stratified --seeds 67001 --conditions sparse32 --output /private/tmp/cpswm-particle-support-repeat
```

## 定向测试及默认兼容性

```sh
PYTHONPATH=src:tools /private/tmp/cpswm-object-reid-venv/bin/python -m pytest -o addopts='' -q \
  tests/test_particle_support_sampling.py tests/test_current_event.py \
  tests/test_current_event_adversarial.py tests/test_current_event_task_receipt.py \
  tests/test_shared_location.py tests/test_current_location.py tests/test_executed_search.py \
  tests/test_active_location_search.py tests/test_task_readout_repair.py \
  tests/test_full_mechanism_value_diagnostic.py tests/test_structure_two_stateful_full_joint.py \
  tests/test_structure_two_stateful_full_joint_adversarial.py \
  tests/test_structure_two_w3_native_posterior_projection.py \
  --junitxml=/private/tmp/particle-support-regression.xml
```

164通过（15本轮新增、149已有）；全仓/S1/B未运行。初测日志保留：可枚举测试最初错误地要求有限N自归一化均值接近无偏目标，已改为与精确枚举的有限N期望比较，未放宽提议频率或相对误差检查；两个测试先误用不存在的撤回API，随后又将深复制账本按对象身份比较，均更正为实际API和账本内容。与工程修复前后实测分开，不包装为生产缺陷。

默认基准通过`run_stateful_full_joint_development(repository_root=Path.cwd())`实际重跑，再调用`verify_stateful_full_joint_result(result, repository_root=Path.cwd())`，断言新旧`result['summaries']`完全一致后更新`benchmarks/structure_two/structure_two_stateful_full_joint_v0_1.json`。未通过仅改hash绕过源码绑定。

## 独立复核与封存

```sh
$PY tools/probe_particle_support.py --output /private/tmp/cpswm-particle-support/probe.json
$PY tools/probe_current_event.py --output /private/tmp/cpswm-particle-support/revisions.json
$PY tools/check_particle_support.py --main /private/tmp/cpswm-particle-support --repeat /private/tmp/cpswm-particle-support-repeat --output /private/tmp/cpswm-particle-support/checks.json
$PY tools/package_particle_support.py --main /private/tmp/cpswm-particle-support --repeat /private/tmp/cpswm-particle-support-repeat --output docs/reviews/pc_a/particle_support_repair_2026-10-12/evidence
```

封存包括原始逐步动作/因子/采样回执、实际搜索与真值隔离文件、来源清单、开发/留出评分、合并字节映射、修订探测和测试日志。解压后按main/repeat路径重跑标准库评分器和检查器；检查器`--repository`必须指向505个来源文件一致的工作树。它检查记录算术/偏移/区间及正负例，不证明有权限代码无法篡改内存。原生完整候选CDF仅在固定开发前缀独立枚举，不宣称批量已精确枚举完整目标后验。
