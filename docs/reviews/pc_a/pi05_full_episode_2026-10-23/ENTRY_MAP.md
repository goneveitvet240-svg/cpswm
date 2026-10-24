# 当前代码与运行入口

- 官方原版源码：仓库根下 `.local/simulation-stack/vendor/openpi`，锁定 `215abfb217dbac7d5f1273282331b9b1866c0479`。网络/Tokenizer/变换来自这里；不把本项目桥接器称为官方完整训练工程。
- 官方权重：`.local/simulation-stack/models/pi05_libero`，运行manifest绑定校验清单和tokenizer哈希。模型未复制进Git。
- 本项目Mac推理适配：`src/cpswm/simulation/integrations/policy.py` 的 `local_pi05`，按官方pi05_libero构建JAX CPU推理，绕过无关CUDA训练依赖；不是直接执行官方训练脚本。
- LIBERO环境与公开观测：`src/cpswm/simulation/integrations/libero_env.py`。
- 完整固定目标运行：`tools/run_libero_stack.py --policy pi05-local --steps 220 --stop-on-success`。
- 本次动作/物理/成功重放核验：`tools/verify_pi05_full_episode.py`。
- CPSWM选择目标闭环（上一批PR118/120）：`tools/run_libero_goal_loop.py`、`src/cpswm/simulation/goal_control.py`，支持显式suffix重放。本次固定目标实验没有启用该控制器。

所有文件在独立工作树 `.local/simulation-stack/cpswm-full-episode`，主目录旧checkpoint分支并没有自动切换或合并，所以在旧工作树里找不到新文件是预期的。共享集成仍为 `codex/dual-pc-handoff-20260912`；按具体PR分支/SHA查看工作。

完整科学范围保留。本次即使成功，也只说明一个已知目标实例的执行能力，不说明多人隐藏事件归因、长期记忆或CPSWM自主目标收益。
