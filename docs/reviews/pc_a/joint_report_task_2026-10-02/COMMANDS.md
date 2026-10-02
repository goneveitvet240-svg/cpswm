# 命令与证据

实际新增源码 `10af59aba3a26bbbe66346b1bee89ae9b0a55de1`。工作目录 `/private/tmp/cpswm-pc-a-joint-report-evaluation-20261002`，虚拟环境为前序工作树的借用环境，不称独立重建。Python3.13.5，依赖版本沿PR92证据。

```sh
CPSWM_SSDLITE_WEIGHTS=/private/tmp/cpswm-natural-candidate-evidence-20261001/ssdlite.pth .venv/bin/python -m pytest tests/test_target_position_report.py tests/test_owned_target_position_report.py -x
.venv/bin/python -m pytest tests/test_structure_two_joint_consumption_components.py tests/test_joint_camera_policy.py -x
.venv/bin/mypy src
.venv/bin/ruff check src tests
.venv/bin/ruff format --check src tests
```

分别见evidence/review-r1.log、review-r2.log及静态检查日志。frozen-sources.json与source-unchanged.json绑定928文件。

实际旧归档诊断运行如下，第二次只更换输出目录为live-owned-report-fresh；脚本先完成报告生成，之后才加载SDK盒。旧core源码与新报告源码各自明确，不变更已有绑定以迁就恢复。

```sh
PYTHONPATH=/private/tmp/cpswm-pc-a-joint-target-observations-20261002/src:/private/tmp/cpswm-pc-a-joint-target-observations-20261002/tests:/private/tmp/cpswm-pc-a-joint-target-observations-20261002/tools .venv/bin/python docs/reviews/pc_a/joint_report_task_2026-10-02/evidence/archive_report_probe.py /private/tmp/cpswm-joint-target-evidence-20261002/live-frozen /private/tmp/cpswm-report-evidence-20261002/live-owned-report --evaluator-instance 'WineBottle|surface|2|8'
```

原始live输入和模型随PR92的transactions/regression归档保存；本次新增两套public-reports.json/result.json及fresh-equality.json。原始直接跨源码恢复失败见archive-readout.log。owned-development.log保留fixture setup失败，owned-development-2.log为修复后的开发检查；它们不替代冻结R1。

R1数据库/检查点原件7项随owned-report-r1.tar.gz封存，成员SHA及归档SHA已回读验证。旧SQLite依赖原源码与路径配置；未承诺跨版本或跨Windows环境恢复。独立机器应从代码重新运行R1/R2，并按前序环境说明准备固定权重。
