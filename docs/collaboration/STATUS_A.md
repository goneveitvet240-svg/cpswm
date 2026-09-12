# 电脑 A 状态

## A 数据预检交付 2026-09-13（组件及真实采集连通性，非完整训练/闭环）

- 实际交付代码 SHA `57e8576c7dd48203839cdd0ae3a4cdb295db7185`；最终真实 SDK 复验三步均成功，2.67 秒，源前后一致。此后的提交仅登记该 SHA，不改变被测代码。

- 分支 `codex/pc-a-data-preflight-20260913`，base `2a7a547fba30412d9349605aff3a7df7c60d6b3a`；实际源码逐文件摘要见 `docs/reviews/pc_a/data_preflight_2026-09-13/run_03/manifest.json`。
- method-free 训练世界盘点完成：24 世界、144 轨迹、49,428 步；完整 H/R/I/C/Z/r/V 和六操作监督不齐，不能直接训练全轴模型。未运行方法臂、未生成验证/确认世界。
- 新增可见记录前缀导出和 CLI，分开事件/到达时间，保留人物后验/reference prior，拒绝 oracle/未来记录/额外真值。开发示例已执行真实 CLI，仍明确是符号组件样例。
- 新增原始 SDK 采集接口；43 项回归、Ruff、4 新源文件 mypy 通过。真实采集使用已有 `.venv-ai2thor` Python 3.11.16/SDK 5.0.0 和本地 arm64 Unity，在同一 controller 执行 3 步并保存 RGB-D/实际执行结果，最终绑定证据 `real_simulator_02/result.json`。
- 主 Python 3.13 缺 SDK 的初检 exit 2 与第一次 fixture 失败保留；没有把不同环境混为同一结果。真实 iTHOR 单场景 smoke 不等于 ProcTHOR 日程、完整联合主干或科学收益。
- 未修改 B 的三个生产文件、W1/W2/科学配置。没有训练、采购、付费算力、自动集成。报告与来源/证据/可复跑命令在本批 `REPORT.md`。

## A 数据覆盖、可见前缀与仿真采集预检开工 2026-09-13

- 用户授权：先审核三项建议，可靠部分直接推进；不启动模型训练，不选择网络参数、连续状态或付费算力。
- 分支 `codex/pc-a-data-preflight-20260913`，工作目录 `/private/tmp/cpswm-pc-a-data-preflight.8orI6t`，base SHA `2a7a547fba30412d9349605aff3a7df7c60d6b3a`。fetch 成功，B 最新 `c4eb20b045edb9dc34937f2b9d1038475a02e74a`；保持其五项边界/W1/W2 文件不变。
- 独占新文件 `src/cpswm/data_preflight/`、`tools/structure_two_data_preflight.py`、专属测试和 `docs/reviews/pc_a/data_preflight_2026-09-13/`。不改主干、B 生产修复、现有冻结科学配置和封存集。
- 建议审核：训练世界协议有 method-free 限制，因此只运行允许的训练世界覆盖盘点，不适配到方法或训练模型。可见导出基于既有 ObservationOpportunityRecord/ObservationDetectionResult；加入发生时间与接收时间双重前缀，不把全历史摘要、种子、真值送入方法。
- 本机 Darwin arm64，项目解释器未安装 ai2thor/prior/torch；采集接口与环境预检可做，真实 Unity 运行尚未验证，不能用替身样例宣称真实采集。
- 测试尚未执行；本条推送后是已共享开工登记。

## A1 联合消费者/解析更新组件交付（非默认闭环）

- 实际交付代码 SHA：`1d24099a025c9d7c00a59e4c78c593703924b0eb`；提交后再次核对运行 manifest 全部源码摘要，差异为 0。后续本状态登记提交只更新文档，不改变被测生产源码。

- 分支 `codex/pc-a-native-joint-consumers-20260912`，生产 base `62870a3a38fce882b25d8d77f1d0526cca6fbc14`；实际执行源逐文件 SHA-256 在 `docs/reviews/pc_a/native_joint_consumers_2026-09-12/run_01/manifest.json`，交付代码提交由该分支确定。
- 新增全粒子决策视图、三解析块纯计算；扩展 CIAV 完整粒子期望效用，仍以原因边缘计算原因信息增益。不写 B 独占两个核心文件，不改科学配置。
- 命令：主仓库 `.venv/bin/python docs/reviews/pc_a/native_joint_consumers_2026-09-12/run_checks.py run_01`。85 passed / exit 0；Ruff、三个源文件 mypy 通过；源码前后摘要相同。不是 812 项全回归或 Windows 复现。
- 新增测试含明确标识的合成组件正例/负例与 prepared 接缝集成，不冒充真实默认候选生成。来源授权、完整概率、真实测量模型、默认调度与同一连续执行历史仍未完成。
- 用户确认没有现成全轴模型和测量/噪声工件；获取与训练方案见同目录 `INPUT_ACQUISITION.md`，不是要求用户自行找完才能继续。三候选训练覆盖盘点/可见特征导出可先开展，物理状态含义及未冻结参数需明确。
- 完整报告 `REPORT.md`；推送本人分支后交 B 复核，不自动集成。五项边界修复仍由 B PR #7 负责，本批不宣称关闭其反例。

## A1 默认完整联合主干：非冲突消费者与条件统计批次开工

- 任务目标：继续闭合默认完整联合主干及同一连续历史闭环，不以手工 prepared 注入、占位模型或模拟执行成功宣称完成。
- 本批分支：`codex/pc-a-native-joint-consumers-20260912`；base/开工源码 `62870a3a38fce882b25d8d77f1d0526cca6fbc14`；工作目录 `/private/tmp/cpswm-pc-a-native-joint.Ct7tPQ`。
- 本次 fetch 成功；B 最新 `23506024213d517ba4bab65d4318663163b00913`，PR #7 正在五项边界修复/证据运行器，唯一占用 `prototype_spine.py`、`structure_two_particle_workspace.py` 及直接必要类型。本批不写这两文件，不改 B 审核或比较工具。
- 本批 A 独占新增 `src/cpswm/system/structure_two_joint_consumption.py`、`src/cpswm/system/structure_two_conditional_updates.py`，必要时扩展 grounded_search/active_verification.py 的联合后验消费；专属新测试/工具/报告；不改科学配置。
- 本批落实：完整粒子相关性的期望效用/CIAV 消费及三个解析块的显式条件增量、累计与撤销。数学正例会明确标单元/组件验证，不冒充默认生产路径。
- 待接入依赖：B 边界修复经审查后接入当前工作区；真实全轴模型/选择回执、真实连续测量与噪声模型尚未见共享交付，已向用户询问；不把原因/阶段 MLP 更名为全轴模型。默认候选生成/完整 log-q、主干默认接入、动作执行反馈及完整连续验收均保留为未完成目标。
- 本批开工尚未测试；证据计划 `docs/reviews/pc_a/native_joint_consumers_2026-09-12/`。与 B 通过 GitHub 本状态/PR 公示分界，不自动合并共享集成分支。

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
