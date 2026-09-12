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

## 批次三最终交付：取消恢复、完整源绑定回归与连续连接证据

- 本批代码及证据提交：`1d6887206605841074ada0f5ed67db278d1b7958`；基于 R6 `1bd513f51ab7e54a7290870a5f34b524254d55c6`，未重建旧 HEAD，原有工作目录保留。
- 前两批提交：模型 `8607a751cc482661baefa127968b4bc0758ec1d8`；投影 `5fa093290f7f69d1e789915a66645ef1d0b3b875`。
- 最终命令：主仓库 `.venv/bin/python -m pytest -o addopts= -q -n 4 -p no:cacheprovider`，完整 38 个测试文件及 JUnit 参数在 `final_812.command.json`。结果 **812 passed / 0 failed / 0 skipped / exit 0**；包括原 647+67、邻接 50、新投影 21、新取消 27。最终源码前后相同，666 文件快照与本批提交逐一匹配。
- 非零退出保留：原模型 17 项失败/错误、投影集合序列化失败、取消开发失败、早期错误汇总断言 exit 1。原 round4 独立脚本 direct_revision 仍记录 CCRR 原子拒绝异常；没有把退出 0 当作字段全部通过。round5 正负结果、修前修后取消对照均保留。
- 新能力：真实 PCHMP 来源合法消费；延期取消通过唯一 Hybrid 账本恢复原父及被撤销的原派生贡献，资格、快记忆、来源、摘要、再次纠正/撤回保持，异常和 KeyboardInterrupt 原子回滚可重试。不是跨进程掉电持久恢复证明。
- 连续 24 次学习、主动验证、迟到纠正、后续读出，8 个公开干预/对照运行记录真实七算子对象、输入输出、消费及数值后果；不是每条连接全部中断组合已穷尽。
- **完整默认主干未完成**：默认完整联合粒子数实测 0，普通 ΔΛ/Δξ 为 0，CIAV 未消费完整粒子后验，默认自主修订尚未校准。全轴模型工件、真实条件信息模型/联合读出绑定与重采样决定详见 REMAINING_NATIVE_BACKBONE.md；不能将所有剩余接线都称作用户决策。
- 未改科学配置、窗口一编排器或窗口二专属比较实现；完整统一框架范围和既有用户决策保持；本批没有科学收益验证。
- 证据：`docs/reviews/pc_a/w3_backbone_r7_2026-09-12/REPORT.md`、`FINAL_COMMANDS.md`、`TEST_SUMMARY.json`、`committed_source_binding.json`。
- PR 草稿：<https://github.com/goneveitvet240-svg/cpswm/pull/4>。请求电脑 B 绑定本批实际代码 SHA 复核；不请求自动整合或窗口整体验收。
- 下一步：取得明确缺失的全轴模型/观测与读出绑定及待决重采样规则，继续默认候选调度、条件增量束、后验到行动、反馈后缀与重放工程；仍未实现项逐项保留。本状态随本人分支推送共享。
