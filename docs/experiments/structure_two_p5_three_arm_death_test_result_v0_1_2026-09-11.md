# 结构二 adaptive-path P5 三臂行动死亡测试 v0.1（2026-09-11）

协议：`structure-two-p5-matched-three-arm-death-test@0.1-development`  
实现 checkpoint：`0e9373e`  
项目所有者选择：`A1 + B1`  
结果：`P5_ACTION_SIGNAL_NOT_DETECTED`

## 1. 结论先行

在同一 A1 exogenous precommitted schedule（外生预承诺观测日程）、同一 CIAV
候选/结果/成本和同一 typed SEARCH/PUT_BACK（类型化搜索/放回）解码器下，evaluation-only direct
`P5_FULL_EAGER` 没有优于 learned matched two-stage（学习式匹配两阶段）或 independently tuned AMG
（独立调参 AMG）。SEARCH 三臂完全相同；PUT_BACK 中 direct P5 明显更差。因此注册的行动信号门为
`false`。

这次失败目前**不能解释为完整统一模型已被证伪**。运行后追踪发现一个更靠前的 adapter/readout
confound（适配器/读出混杂）：v0.1 direct P5 adapter 没有显式传入此前 validation-only（仅验证集）
选出的 dual-timescale reversible readout（双时间尺度可逆读出），因而使用默认
`HYBRID_ALPHA`；与此同时 direct P5 的评估路径将 long-term write（长期写入）强制阻断。结果是 P5
在全部检查步骤中输出恒定均匀的 owner-habit location distribution（主人习惯位置分布），共享
PUT_BACK 解码器只能反复选择 support（支持集）的第一个位置。

所以 v0.1 是一个真实、必须保留的协议失败结果，但其科学解释是：**当前 direct P5 评估接线没有
读到 P5 已产生的 fast/surviving/regime-local（快速/存活修订/局部状态）统计；尚不能据此断言这些
统计本身没有行动信息。**

## 2. 数据、选择和三臂

- D0 数据：`project-two-d0-multiseed-readout@0.5`；20 train、20 validation、60 test episodes；
  test 共 1,920 steps。
- 三臂：direct `P5_FULL_EAGER`、learned matched two-stage、independently tuned AMG。
- A1：episode 开始前提交 schedule；三臂逐步接收完全相同的 action、outcome 与 cost 回执；臂不能
  改写 schedule。
- B1：learned two-stage 使用共享 `p(location | cause,event)` head（条件位置头）；cause/event 只从
  train truth 构造标签，validation/test truth 只在 typed action commit（类型化动作提交）后评分。
- learned 选择：`base_width=8`、`learning_rate=0.1`、`l2=0.0`、
  `location_smoothing=0.25`。
- AMG 选择：`parameter=0.2`。
- 两个臂的超参数均只按 validation PUT_BACK error（验证集放回错误率）选择；选择回执记录
  `test_episode_ids_seen=[]`。

## 3. test 结果

| arm（臂） | SEARCH error | normalized SEARCH regret | PUT_BACK error |
|---|---:|---:|---:|
| direct P5 full-eager | 0.0890625 | 0.0616319 | 0.6848958 |
| learned matched two-stage | 0.0890625 | 0.0616319 | 0.2739583 |
| independently tuned AMG | 0.0890625 | 0.0616319 | 0.0536458 |

配对 episode bootstrap（3,000 次）按 `comparator error - P5 error` 报告：

| task | comparison | mean improvement | 95% CI | 注册信号 |
|---|---|---:|---:|---|
| SEARCH | learned − P5 | 0.0000000 | [0.0000000, 0.0000000] | false |
| SEARCH | AMG − P5 | 0.0000000 | [0.0000000, 0.0000000] | false |
| PUT_BACK | learned − P5 | -0.4109375 | [-0.4885417, -0.3281250] | false |
| PUT_BACK | AMG − P5 | -0.6312500 | [-0.7156250, -0.5427083] | false |

负值表示 P5 错误率更高。SEARCH 与 PUT_BACK 继续分别报告；
`combined_utility=UNRESOLVED_NOT_AGGREGATED`，没有把两者拼成一个事后指标。

## 4. 生产路径与匹配执行审计

- 1,920/1,920 matched CIAV steps（匹配主动验证步骤）均有精确三臂回执；
- 1,243 个 detected steps 执行真实 `P5_FULL_EAGER`，每次都有七个 primary operator traces
  （主算子轨迹）；
- 677 个 negative observations（负观测）消费真实 CIAV→OPCEU evidence，不伪造 before/after
  transition；
- 677 次对 transition-dependent operators（依赖转移的算子）显式记录 `no_new_transition`；
- evaluator truth 在 typed SEARCH/PUT_BACK 提交前不可见；
- 没有执行 adaptive-router calibration（自适应路由校准）；固定解析阈值仍只保留为基线。

这些证据证明三臂的观测匹配和 P5 生产入口确实运行，不证明 P5 的动作读出正确，也不证明七算子
联合贡献。

## 5. 失败后的读出追踪

逐步检查 direct P5 的两个 location posterior（位置后验）得到：

1. `current_location_distribution` 在 detected step 退化为检测位置的 one-hot；negative step 沿用上一
   状态。因此 SEARCH 主要由共享外生观测决定，三臂自然完全相同。
2. `owner_habit_location_distribution` 在整条 episode 上恒为均匀分布。共享 PUT_BACK 解码器的固定
   tie-break（平局规则）于是总选 support index 0。
3. `DirectP5LocationAdapter` 构造 `StructureTwoProductionSystem` 时未传 `ActionReadoutConfig`，使用默认
   `HYBRID_ALPHA`。
4. direct P5 评估入口对 core transition 设置 `force_long_term_write_blocked=True`；因此默认 pooled
   hybrid counts（池化混合计数）不会随观察更新。
5. 仓库已有冻结的 v0.6 validation-selected readout：
   `DUAL_TIMESCALE_REVERSIBLE`，权重为 fast `0.7`、surviving `0.2`、regime-local `0.1`。v0.1 没有
   消费这一配置。

这是一项在 test split 打开后发现的实现解释，不得回写或覆盖 v0.1。

## 6. 下一项受约束诊断

下一项只能标为 post-hoc readout diagnostic（事后读出诊断）：保持 A1、B1、数据、三臂匹配、共享
解码器和已冻结 v0.6 readout 不变，仅检查把 P5 adapter 接到该读出后，owner-habit posterior 是否
不再恒定均匀，以及 SEARCH/PUT_BACK 结果怎样变化。

由于 v0.1 test split 已被打开，修正版即使变好也不是新的 preregistered death test（预注册死亡测试），
不能签发 confirmatory（确认性）结果。若要重新做无污染死亡测试，必须先冻结修正版，再使用未见过的
新 development holdout 或独立托管 confirmation split。

production debt replay（生产债务重放）仍排在 direct P5 接线诊断之后，用来确认生产重放路径是否消费
同一读出和状态；它不能挽救或改写本次 v0.1 结果。

## 7. 复现与依赖边界

结果工件：
`benchmarks/structure_two/structure_two_p5_three_arm_death_test_v0_1.json`，content SHA-256：
`df44a16e4b450fc77239d0e3e3bbcf9f3fbb3fbbcca9a2db6a0844ce8a6267b5`。

本次 fresh run 在当前工作树执行，工件额外绑定
`production_assembly_manifest_sha256=c726da73267fd7c7a453026950d06d1689b95bcbe49b05d2ddabc90b80eea201`。
尝试在干净 `0e9373e` worktree 复现时，导入阶段因
`prototype_spine.py` 引用的 `RegimeStage` 只存在于未提交的结构一工作树改动而失败。因此：

- v0.1 结果绑定了实际运行时 source bytes（源字节）；
- 但它目前不是从干净 `0e9373e` checkout 可独立复现的结果；
- 本轮不擅自提交三份结构一改动来掩盖该依赖缺口；应由结构一改动所有者单独整理并提交后，再验证
  clean-checkout reproducibility（干净检出可复现性）。

## 8. 声明边界

本结果不聚合 SEARCH/PUT_BACK，不估计 production CIAV net utility，不通过 Task 7/8/9，不验证
adaptive routing，不授权七算子消融、科学优越性或外部有效性，也不删除隐藏事件推断、多人推理、
开放世界 unknown、可逆归因、主动验证或具身反馈闭环。
