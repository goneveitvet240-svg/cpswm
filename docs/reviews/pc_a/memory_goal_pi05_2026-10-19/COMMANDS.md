# 实际命令与复现

工作目录`.local/simulation-stack/cpswm-goal-loop`，base `3e1662542fe3299248eb1f1a25dc37416fe56bc2`。先fetch、读取协作文件及PR117最新源码，创建独占分支；运行前源码commit `48e065ac425398afd966728a563871f66c7d2814`，工作树干净。

```bash
../envs/core/bin/python -m pytest -o addopts= -q \
  tests/test_memory_goal_control.py tests/test_small_sim_framework.py tests/test_libero_stack.py
# 58 passed, 8 skipped in 13.03s

../envs/libero/bin/python tools/simulation_python.py -m pytest -o addopts= -q tests/test_libero_stack.py
# 16 passed in 3.95s

../envs/core/bin/python -m mypy --follow-imports=silent \
  src/cpswm/simulation/goal_control.py src/cpswm/simulation/integrations
# Success: no issues found in 7 source files

../envs/libero/bin/python tools/simulation_python.py tools/run_libero_goal_loop.py \
  --box 104 131 143 163 --output ../runs/memory-goal-pi05-01 \
  > ../runs/memory-goal-pi05-01.log 2>&1
# exit 0; macOS graphics permitted, no cloud or physical robot

../envs/core/bin/python tools/verify_libero_goal_run.py ../runs/memory-goal-pi05-01 \
  > ../runs/memory-goal-pi05-01-verification.json
# initial final-tuple comparison failed; verifier fix ab63e9215d00610a4c51700ac7f7f7115cd56c87
# same original run verified after fix, exit 0

../envs/core/bin/python docs/reviews/pc_a/memory_goal_pi05_2026-10-19/audit_artifacts.py \
  ../runs/memory-goal-pi05-01 ../runs/memory-goal-pi05-01-negative-audit.json
# 1 legal run accepted; 4 corrupted copies rejected
```

从GitHub归档复核可把run目录参数换为`docs/reviews/pc_a/memory_goal_pi05_2026-10-19/evidence/run`。校验器要求当前运行模块与manifest绑定源码逐字节一致；后续修改运行模块时应切回该SHA，不绕过检查。审计器修复及文档变更不影响正式运行源码散列。模型原权重不重复上传，来源与摘要由manifest和上一轮PR117证据给出。

录像使用imageio读取确认8帧，初/末overlay经图像工具查看；位移用最后动作后的EEF位置减初始public observation计算。所有25份运行原件复制后逐字节核对，外层`SHA256SUMS.json`覆盖归档证据及验证回执。后续复跑必须使用新的output目录名，以保留原件。
