# 实际源码与复现命令

工作树 `.local/simulation-stack/cpswm-synergy`，base `dfcfbb2b78cd06865923eda916700c3abee5e3e9`。所有正式运行先提交源码，原件输出在兄弟runs目录。不要覆盖已存在运行目录。

| 执行 | 实际源码SHA |
|---|---|
| 768点六方法配对 | `5c8905ed855e5f60d57b1b4704659db5aa3c8ad8` |
| smoke02和完整π0.5 | `3a00679365c2f50cec2d63d80efa585dbd18fafc` |
| 完整原生重放/人物评分、来源矩阵、旧精确参考比较 | `3ca57e4cf2e57f71b795313a3c2f182d7e39f6ae` |
| 历史统计探针、共有策略输入对照/物理核验器 | `94aa2e675c256942e95cdfc5dddb4a1b26d3aab4` |
| 缺失制度目标干预 | `7219ab9e065ae01803e3c2b9951bbd03ffe0c9d4` |
| 物理伪造反例 | `b0ec243868b8db1f711e0247f8818b05143322a3` |

```sh
PYTHONPATH=src:tools ../envs/core/bin/python tools/run_five_stage_synergy.py --output ../runs/five-stage-synergy-01
PYTHONPATH=src:tools ../envs/core/bin/python tools/audit_synergy_posteriors.py ../runs/five-stage-synergy-01 --output ../runs/synergy-posteriors-01.json
PYTHONPATH=src:tools ../envs/core/bin/python tools/audit_synergy_reference.py --output ../runs/synergy-reference-01.json
PYTHONPATH=src:tools ../envs/core/bin/python tools/audit_synergy_corrections.py --output ../runs/synergy-corrections-01.json
PYTHONPATH=src:tools ../envs/core/bin/python tools/derive_synergy_history.py ../runs/five-stage-synergy-01 --output ../runs/synergy-history-01.json
PYTHONPATH=src:tools ../envs/core/bin/python tools/audit_missing_regime.py ../runs/five-stage-synergy-01 --output ../runs/synergy-missing-regime-01.json
../envs/libero/bin/python tools/simulation_python.py tools/run_libero_goal_episode.py --policy smoke --steps 7 --box 104 131 143 163 --output ../runs/synergy-goal-smoke-02
../envs/libero/bin/python tools/simulation_python.py tools/run_libero_goal_episode.py --arm native_joint --box 104 131 143 163 --output ../runs/synergy-goal-joint-01
PYTHONPATH=src:tools ../envs/core/bin/python tools/verify_synergy_goal_episode.py ../runs/synergy-goal-joint-01
PYTHONPATH=src:tools ../envs/core/bin/python tools/audit_synergy_goal_controls.py ../runs/synergy-goal-joint-01 --output ../runs/synergy-goal-joint-01-controls.json
../envs/libero/bin/python tools/simulation_python.py tools/replay_synergy_goal_physics.py ../runs/synergy-goal-joint-01 --controls ../runs/synergy-goal-joint-01-controls.json --output ../runs/synergy-goal-joint-01-physics.json
../envs/libero/bin/python tools/simulation_python.py tools/audit_synergy_physics_forgery.py ../runs/synergy-goal-joint-01 --output ../runs/synergy-goal-joint-01-negative.json
```

以上正式命令均exit0。第一次smoke01受macOS图形沙箱限制停滞，已终止；另目录smoke02在允许图形服务的环境重跑完成。早期correction矩阵预检把missing源写成自修订，构造期即拒绝；审计输入改为不同source/revises后，正式矩阵和测试通过。只披露脚手架预检修正，不计入机制收益。

```sh
PYTHONPATH=src:tools ../envs/core/bin/python -m pytest -o addopts= -q tests/test_five_stage_synergy.py tests/test_synergy_goal_evaluator.py tests/test_synergy_verification.py tests/test_joint_three_questions.py tests/test_short_history_reference.py tests/test_matched_value.py tests/test_memory_goal_control.py tests/test_current_event.py tests/test_current_event_adversarial.py tests/test_current_event_task_receipt.py
# 101 passed in 70.26s; evidence/tests.log
PYTHONPATH=src:tools ../envs/core/bin/python -m pytest -o addopts= -q tests/test_synergy_missing_regime.py
# 1 passed in 1.90s; terminal result recorded in this command receipt
../envs/libero/bin/python tools/simulation_python.py -m pytest -o addopts= -q tests/test_libero_stack.py tests/test_pi05_full_episode.py
# 33 passed in 4.78s; evidence/sim-tests.log
```

完整π0.5实跑1797.75秒（约30分钟），与CPU审计部分重叠，不与旧118步固定prompt任务比较性能。三记忆对照共享记录的策略输出；物理重放未重新推理π0.5/SAM。权重未上传或重新下载，checkpoint/tokenizer/vendor摘要保留在run manifest；归档仅包含本轮输入、输出、轨迹和核验。
