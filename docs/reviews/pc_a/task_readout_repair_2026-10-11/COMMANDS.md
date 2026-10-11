# 复现命令

分支 `codex/pc-a-task-readout-repair-20261011`，base `97d008d141b5438ec973ba07e12027d94599542a`。推断/runner源码 `f6190f1febe0c834674568f67763726c759ea0a9`；独立评分/后验分析工具 `4ace116fb13735ce541e222aadaae232445cd084`；最终重复/篡改检查 `c5af5c13a1ff67d91f7ee65e654bf525094190c0`。使用Python3.13.5与仓库依赖；本机解释器 `/private/tmp/cpswm-object-reid-venv/bin/python`。以下在仓库根目录运行，`python`应指向重建的虚拟环境；不要跨机器复制旧虚拟环境。

```bash
PYTHONPATH=src:tools python -m pytest -q tests/test_task_readout_repair.py tests/test_full_mechanism_value_diagnostic.py tests/test_structure_two_stateful_full_joint.py tests/test_structure_two_stateful_full_joint_adversarial.py
PYTHONPATH=src:tools python tools/run_task_readout_repair.py --phase dev --condition complete32 --output /tmp/readout-dev-complete32
PYTHONPATH=src:tools python tools/run_task_readout_repair.py --phase eval --condition complete32 --selection-dir /tmp/readout-dev-complete32 --output /tmp/readout-eval-complete32
python tools/score_task_readout_repair.py /tmp/readout-eval-complete32 --development /tmp/readout-dev-complete32 --output /tmp/readout-independent-complete32.json
```

另两条件将 `complete32` 换为 `sparse32`、`long64`。本轮在所有条件的dev选择完成并封存之后，才启动任何eval；不要把未选中的配置拿到评价集重新挑选。测试默认seeds61001–61010。仅做重复性检查时可指定 `--seeds 61001` 和新的输出目录，并使用同一封存selection目录。输出目录必须不存在。

独立scorer仅用标准库和原PR106的bootstrap函数；它不调用推断类或项目指标计算。`source.json`覆盖推断源码、runner及其直接实验工具依赖、所有相关配置和固定神经模型；scorer源码由Git提交单独约束。运行时间含回执/诊断开销且多进程竞争，不能当部署时延。

附加证据检查（读取归档解压后的目录）：

```bash
python tools/summarize_task_readout_effects.py /tmp/cpswm-task-readout-main --output /tmp/readout-effects.json
python tools/check_task_readout_artifacts.py /tmp/cpswm-task-readout-main/eval-complete32 --development /tmp/cpswm-task-readout-main/dev-complete32 --repeat /tmp/readout-repeat-complete32 --output /tmp/readout-checks.json
```

说明：raw `actions`沿用PR106的`current_readout_choice/distribution`字段，表示同一底层状态上的**默认v0.6诊断回读**；慢配置实际输出在`task_readout.habit_distribution`与`put_back/search_order`。不能拿诊断回读冒充候选的实际动作。所有臂的后续反馈及评分绑定实际输出。

剩余搜索错误诊断为只读post-hoc计数，不用于重新选择配置。对每个条件的10个`visible-i.json`、`evaluator-truth-i.json`与`test-i-split_v06.json`按`step_id`对齐：先以SEARCH首位与`true_location`不等筛出错误，再分为`after is None`、`after.detected_location_id is None`、检测位置与truth不符、检测正确但动作错误四类。这只能解释当前D0回放，不等于自然视觉错误归因。

重复性检查的第一次严格JSON比较因新增回执中的`source_snapshot_id`失败。已追踪到`BaseRecordMetadata.record_id`默认`uuid4`（`src/cpswm/contracts/base.py:70`）：本次两实际任务分离臂各32个运行内快照ID不同，其余动作行、概率、关键指标/修订回执和runtime audit完全相同。检查工具只在跨运行对比时去掉这个明确字段，并记录排除字段与64个原始ID差异；两个原始归档均保留，不修改推断或覆盖主实验。不是以数值容差掩盖动作/后验差异，也不把这项局部检查称作完整元数据伪造验收。
