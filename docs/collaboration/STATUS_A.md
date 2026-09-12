# 电脑 A 状态

## A1 窗口三完整主干工程 R7 — 进行中

- 分支：`codex/pc-a-w3-backbone-r7-20260912`。
- 工作目录：`/private/tmp/cpswm-pc-a-w3-backbone-r7-20260912`。
- base SHA / 当前被测代码 SHA：`1bd513f51ab7e54a7290870a5f34b524254d55c6`，包含 R4/R5/R6 实际修复。
- 已 fetch 核验集成 SHA：`bdec3ee21b7db361e390496d97ff2eb30390dc6c`；审核依据：`97e1d2c1e83a4532e2b3bab3bf87cc6a2927f274` 的 round6 REPORT。
- 任务边界：模型来源、真实后验消费、默认联合主干、唯一账本与延期取消恢复、同一连续运行七算子后果矩阵。不得改 W1 编排器或 W2 专属比较模块。
- 已冻结：Route C、Architecture A、P5_FIRST、A1+B1、H/R/I/C/Z/r/V、三个 RB blocks 与七算子；不重新选择。
- 本次命令：`git fetch origin --prune` 成功；本次尚未运行代码验收。
- 证据：`docs/reviews/pc_a/w3_backbone_r7_2026-09-12/`，保留远端四文件及版本。
- 下一步：定位并恢复可验证模型原件；分别提交依赖批次并推送本分支，通过 PR 交接，不自动集成。
- 本条随分支推送后为 GitHub 已共享的开工登记；完整主干和科学收益未验收。

## 批次一交付：真实模型原件恢复

- 实际被测生产代码仍为 `1bd513f51ab7e54a7290870a5f34b524254d55c6`；新增工件绑定历史提交 `505e723170c29f8707ee19d113a5b8646680c5f6`，精确字节/源码哈希见 model_recovery 和 model_restored_50.command.json。报告提交不自引用。
- 命令：主仓库 Python 3.13 运行 `docs/reviews/pc_a/w3_backbone_r7_2026-09-12/run_checked.py model_restored_50`，结果 50 passed / exit 0；恢复前 exit 1 的 17 项失败/错误保留。
- 下一步：真实生产后验绑定与消费、默认联合主干和延期取消恢复仍在进行；完整能力与科学收益未验收。

## 批次二交付：真实 PCHMP 生产来源与投影消费

- 生产者、消费者、证据和语义身份绑定已实现，合法非空正例和完整重封负例见 POSTERIOR_PROJECTION.md。
- 原 714 项回归通过（exit 0，868.63 秒）；107 项预检通过；Optional 类型守卫修改后的 85 项定向回归及 mypy 日志单独保存。
- 精确被测源码绑定：projection_regression_714.command.json、projection_typed_final.command.json；本批提交可由 GitHub 分支查看，不把旧代码测试冒作当前结果。
- 下一步：延期取消后的父贡献恢复，以及默认完整联合主干连接。安全拒绝与模型工件恢复均不等于完整能力完成。
- 后续定向复测检出 Python 原因集合键的顺序问题，85 项曾出现 3 失败、扩展后 87 项曾出现 2 失败，均保留原日志；最终109项通过。使用 native 局部确定序列化，未改共享旧散列格式。前述714通过是较早绑定，最终集成版本仍需重跑。
