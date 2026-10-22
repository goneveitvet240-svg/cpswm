# 方案书实验入口与实际消费边界

绑定 `2e9694b3d08ebed0f361b342253b40740199e672`。

| 层 | 实际入口 | 配置 / 消费边界 |
|---|---|---|
| 本批 E0/E2 | `tools/run_research_pilot.py` | `--part finite/e0/e2/all`；开发诊断 |
| 原生有限支持参考 | `structure_two_stateful_full_joint.py` 的 candidates/transition/main/interaction/constraints/world/readout | 仅旁路枚举，不覆盖执行中的粒子；pre-ledger 读出 |
| 当前事件主循环 | `tools/run_current_event.py::build`、`CurrentEventRuntime` | v06、24 粒子、既有 sparse32；shared head 仍是执行搜索消费者，不把 pre-ledger reference 误称实际搜索头 |
| 原生联合与消融 | `FullJointArm.STATEFUL_FULL_JOINT / MATCHED_FULL_STATE_FACTORIZED` | 相同状态范围；后者为六显式势消融，不是完全独立模型 |
| 原生固定配置 | `configs/project_two_experiments/structure_two_stateful_full_joint_v0_1.json` | unresolved=.05，neural mix=.7，interaction=1；本批未更改 |
| 仿真语义记忆 | `src/cpswm/simulation/memory.py::SimulationMemory` | controlled fixture；每次重建全部有效非机器人 observed 历史 |
| 记忆到机器人目标 | `src/cpswm/simulation/goal_control.py::MemoryGoalController` | 语义记忆与图像跟踪分开；目标绑定 memory revision |
| π0.5 适配 | `src/cpswm/simulation/integrations/policy.py::local_pi05` | 调用官方模型/层/归一化，不是重新实现 π0.5；推理适配入口属于本项目 |
| 官方 π0.5 原码 | 本机 stack `vendor/openpi` | SHA `215abfb217dbac7d5f1273282331b9b1866c0479`，本批重新核对 clean；不在主仓库 src 内复制一份 |
| 官方模型权重 | 本机 stack `models/pi05_libero` | 既有官方下载检查点；本批没有训练/修改/再次推理 |
| 真实仿真入口 | `tools/run_libero_goal_loop.py`（经 `tools/simulation_python.py`） | 原 PR118 的受控目标修订两段 probe；本批未重跑 |
| LIBERO 成功 | `src/cpswm/simulation/integrations/libero_env.py::step` | evaluator_success 来自固定任务 done；不认证任意新目标 |
| SAM 反馈 | `integrations/perception.py` 与 `goal_control.py` | 跟踪/预测不能认证放置；原链路仍 unknown |

本机 stack 绝对路径：`/Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/.local/simulation-stack`。本批独立工作树位于其 `cpswm-research-pilot`；原接入工作树 `cpswm-goal-loop` 保留。需要查看本次新增内容时应打开新工作树，原 checkpoint 根目录不会自动出现分支上的文件。
