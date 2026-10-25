# 可复现命令与实际代码

base `fbec4e9c2103b8bc505f261112d37313085a4cae`，实际运行/测试/重算源码 `d1bb6442037fc90cfe2fff22410f7f05e85d6b0d`。Python3.13.5，独立工作树使用核心环境；跨机器按锁文件重建，不能复制Mac虚拟环境。以下输出目录须是工作树外的新目录。

```sh
../envs/core/bin/python -m pytest -o addopts='' -q tests/test_joint_three_questions.py tests/test_short_history_reference.py tests/test_matched_readout.py tests/test_matched_value.py tests/test_current_event.py tests/test_current_event_adversarial.py
../envs/core/bin/ruff check tools/run_joint_three_questions.py tests/test_joint_three_questions.py
../envs/core/bin/ruff format --check tools/run_joint_three_questions.py tests/test_joint_three_questions.py
PYTHONPATH=src:tools ../envs/core/bin/python tools/run_joint_three_questions.py --output /private/tmp/cpswm-three-full-20261025
PYTHONPATH=src:tools ../envs/core/bin/python tools/run_joint_three_questions.py --verify --output /private/tmp/cpswm-three-full-20261025 --replay-q1 /private/tmp/cpswm-three-repeat
```

实际完整collect与verify退出0，68测试通过。实际Q1二次完整重跑在Q3尚运行时单独调用`run_short_history_reference.run`，用`verify_replayed_run`和`verify_traces`比较，证据见q1-replay.log和q1-replay-verification.json；上面的组合命令等价执行该验证。计时不能作为独占机器速度比较。

存档重算：复制evidence目录至临时目录，解压points.json.gz为points.json，保持字节不变；在实际源文件相同的工作树运行`--verify --output 临时目录`即可。manifest绑定所有原件和源码，后续仅文档变化不影响源文件核验。重生成全部推断必须使用干净的实际代码SHA，不能用存档重算冒充重跑。

另一个仅依赖Python标准库的计数实现（不导入生产或主诊断汇总函数）：

```sh
python3 docs/reviews/pc_a/joint_three_questions_2026-10-25/derive.py docs/reviews/pc_a/joint_three_questions_2026-10-25/evidence
```

输出应与evidence/independent_counts.json相同。此脚本在主实验之后从已固定结果导出平局与得失说明，未进入模型、参数选择或动作规则；其代码hash由交付MANIFEST.json单独绑定。人物平局容差1e-10；解析质量低于1e-12时不除法还原成分，属于数值可报告范围，不是新的科学通过阈值。
