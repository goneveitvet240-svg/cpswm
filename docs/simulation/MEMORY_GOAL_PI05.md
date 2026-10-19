# CPSWM选择π0.5执行目标

这是独立的本机仿真工程入口，接在PR117的真实LIBERO、π0.5、SAM链路上。

```text
显式受控历史/归因修订 → SimulationMemory原生目标读出 → 目标目录中的指令
                                                           ↓
公开相机/本体状态 ───────────────────────────────────────→ π0.5
                                                           ↓
SAM预测/丢失 → 独立视觉记忆 ← unknown执行反馈 ← LIBERO实际动作
```

`configs/simulation/libero_goal_fixture.json`复用既有`delayed_attribution`场景，把left/right显式映射为plate/stove。目录只规定目标的语言表达，选择由记忆分布决定。历史及人物归因是受控输入；操作员通过SAM框绑定黑碗。相机图像区域不充当物理地点，也不自动识别人。

默认探针先根据历史选择炉台，执行官方π0.5动作块的前2步；记录真实执行后的SAM反馈；再提供迟到归因修订。原生记忆重新读出盘子目标，废弃旧块剩余3步，以当前相机及本体状态重新推理并执行5步。传播掩码只报告预测/丢失，两个执行段都以`unknown`反馈回写视觉记忆；机器人动作不会反过来学习为人的习惯。没有放置成功检测器。

操作员目录和已有工程读出沿用当前仿真框架，并非冻结的生产任务读出。人物历史自动抽取、语义地点识别、丢失后主动寻找、长回合任务、全局ORRER事务和科学对照仍待接入。没有改变完整统一研究范围。

## 运行

工作树须位于`.local/simulation-stack`下，与`envs`、`models`、`vendor`为兄弟目录，依赖见[原接入说明](LIBERO_PI05_MAC.md)。本机图形访问需在允许macOS渲染的终端执行。仅仿真，无真机。

```bash
../envs/libero/bin/python tools/simulation_python.py tools/run_libero_goal_loop.py \
  --box 104 131 143 163 --output ../runs/memory-goal-pi05-01
../envs/core/bin/python tools/verify_libero_goal_run.py ../runs/memory-goal-pi05-01
```

默认使用原生联合臂、官方π0.5 CPU模型、LIBERO table_center/init0/seed7。`--policy smoke`仅用于无模型工程预检，不计π0.5推理；`--no-correction`保留同样2+5步边界但不投递修订；`--arm`支持原生因子化、来源重放、普通记忆。种子不代表独立科学样本。

输出包含源码/vendor/模型清单摘要、受控输入原件、逐次JSONL进程回执、策略实际输入及完整动作块、逐动作本体状态、三个SAM前缀帧/掩码及录像。校验器以绑定源码重放所有核心请求，对照命令、指令、反馈和实际消费的模型动作。它是内部一致性审计，不是外部物理真实性认证。

原始LIBERO成功标志只在结束后供评估使用，未传入记忆、策略或成功反馈；它仅对应原始“黑碗放盘子”任务。任务成功、接入成功、科学收益必须分别报告。

## 验证

```bash
../envs/core/bin/python -m pytest -o addopts= -q \
  tests/test_memory_goal_control.py tests/test_small_sim_framework.py tests/test_libero_stack.py
../envs/libero/bin/python tools/simulation_python.py -m pytest -o addopts= -q tests/test_libero_stack.py
../envs/core/bin/python -m mypy --follow-imports=silent \
  src/cpswm/simulation/goal_control.py src/cpswm/simulation/integrations
```

测试含合法双段反馈、相同相机不同历史的四臂读出、未发出的完整伪造计划、篡改指令/目标/版本/来源、过期指令、时间/重复来源/反馈约束、反馈写入失败后的无重复执行重试，以及缺失/丢失视觉与平票时不发动作。进程边界是本机可信适配器，不提供对不可信远端调用者的认证。
