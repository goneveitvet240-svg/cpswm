# 结构二 empirical gap closure（实证缺口闭合）记录，2026-08-26

## 本轮边界

本轮不缩小七算子统一框架，也不把已有模块删除或拆成多篇文章。凡是会改变算法、主要效用、独立实验单位、因子水平或外部复现对象的技术设计，保留为显式选择；不涉及这些选择的配置接线、规模化执行、结果封存、真实性标注和测试已经完成。

## 已完成：现有 D0 20/60 配置真正进入 action benchmark

执行入口：

```bash
.venv/bin/python apps/evaluation_runner/run_structure_two_action_death_test.py \
  --dataset-config configs/project_two_datasets/d0_multiseed_evidence_v0_3.json \
  --output artifacts/project_two_data/d0_multiseed_v0_3/action_benchmark_v0_2.json
```

配置和样本：

- config SHA-256：`327794c8fb98c7257f09d20ec188ec91cb9913054c7ba82265d72191d2cdea86`；
- 20 个 validation（验证）episode 独立调参，60 个 sealed test（封存测试）episode 只用于评价；
- 80 个 household/scene/object、2,560 个 step、1,718 条 execution feedback（执行反馈）；
- observation coverage（观察覆盖率）为 0.6711；
- 数据质量门通过，但配置明确为 `development_multiseed`、`confirmatory=false`；
- 输出 JSON 为 21 MB，SHA-256 为 `b7670a0668b506500631f1d2b78a7d7c86a11ce3f81fda9f36c87b97dceeb208`。

每个非 oracle 方法都在同一 validation split（验证划分）上穷尽各自 3 个候选点，再在同一 sealed test、可见历史、feedback stream（反馈流）和 action budget（动作预算）上比较。这个执行证明了当前 runner 的独立调参和公平输入约束确实被使用；它不证明三点搜索空间已经足够强。

## 规模化结果

下表只列 faithful matched/control（忠实匹配／对照）方法。数值为 60 个独立 episode 的均值；区间为 episode-level paired bootstrap（episode 级配对自助法）95% CI。所有误差、regret、污染和恢复成本均为越低越好。

| 方法 | put-back error | cumulative regret | owner contamination | recovery cost |
|---|---:|---:|---:|---:|
| Project Two full | 0.1422 [0.1276, 0.1589] | 7.333 [6.600, 8.100] | 0.0000 [0, 0] | 0.5917 [0.3750, 0.8417] |
| Matched open-world AMG | 0.0453 [0.0344, 0.0573] | 4.233 [3.567, 4.950] | 0.0000 [0, 0] | 0.0000 [0, 0] |
| Markov | 0.2964 [0.2719, 0.3234] | 12.267 [11.300, 13.317] | 0.1609 [0.1464, 0.1734] | 3.2875 [2.7097, 3.8597] |
| Recency | 0.3031 [0.2891, 0.3177] | 12.483 [11.817, 13.217] | 0.2469 [0.2385, 0.2552] | 4.3000 [3.7750, 4.8000] |
| Frequency | 0.4141 [0.3766, 0.4568] | 16.033 [14.650, 17.533] | 0.0708 [0.0521, 0.0922] | 5.6286 [4.9889, 6.2233] |
| Full-rerun control | 0.4141 [0.3766, 0.4568] | 16.033 [14.650, 17.533] | 0.0708 [0.0521, 0.0922] | 5.6286 [4.9889, 6.2233] |

相对 Project Two，matched AMG 的 `baseline - Project Two` 配对差为：

- put-back error：−0.0969，95% CI [−0.1094, −0.0854]；
- cumulative regret：−3.100，95% CI [−3.500, −2.733]；
- owner contamination：0，95% CI [0, 0]；
- recovery cost：−0.5917，95% CI [−0.8333, −0.3750]。

因此当前 D0 证据不是“复杂链普遍没用”，而是一个更具体的结果：完整链相对简单频率、近期、Markov 和 full-rerun 对照有稳定收益，但 matched AMG 在主要 action outcome（行动结果）上更强。O-STaR、DynaMem 和 STAR 仍只是 matched replay adapters（匹配回放适配器），不能作为外部忠实复现结论。

## 现指标不能回答的长期污染与恢复问题

当前 `owner_habit_contamination` 只计算“非 owner 移动时，planner 是否把当前位置当作 owner put-back”的即时动作代理，并没有检查错误证据进入状态后在未来多少步持续污染 belief、statistic、cache 和 policy。

当前 `incorrect_statistic_recovery_cost` 只在“执行反馈失败且当步 put-back 已错”的 episode 片段中计算后续预测恢复延迟。没有可逆账本的 AMG 因为不产生同类 ledger transition（账本转移），仍可得到 0；所以这个 0 不能解释为“完成了可逆恢复”。在确定以下设计前，不能把该列写成论文中的长期恢复优势：

1. 污染起点是 erroneous evidence commit（错误证据提交）、错误 statistic write（统计写入），还是首次错误 action；
2. 恢复终点是 belief equivalence（信念等价）、full-rerun equivalence（完整重跑等价）、action recovery（动作恢复），还是三者都报告；
3. 没有 ledger 的方法是按“从可见历史重建到等价状态”的成本计分，还是只按动作恢复计分；
4. 长期 horizon、访客窗口、真实习惯改变和复发窗口如何缩放。

## 尚未完成且必须由技术选择启动的部分

### A. matched ordinary heterogeneous GNN（匹配普通异构 GNN）

仓库没有普通异构 GNN 的训练和独立调参产物。需要先选择普通模型族和信息预算，例如 R-GCN、HeteroGraphSAGE 或 HGT；还要决定它是静态事件图预测器，还是允许固定长度 temporal window（时间窗口）。在这个选择前直接实现某一个模型会替论文替换 strongest ordinary baseline（最强普通基线）的定义。

### B. change/stage baselines（变化／阶段基线）

ordinary BOCPD 和 BOCPDMS 代码已经存在于 evaluation operations，但尚未在结构二同一 actor/location/observation stream（人物／位置／观察流）上接 action readout。switching HMM 尚不存在。需要选择 emissions（发射分布）、state count（状态数）和从 change/stage posterior（变化／阶段后验）到 action 的公平读出；三者都必须各自独立调参。

### C. powered factorial intervention（功效充足的因子干预）

现有 20/60 D0 是随机场景集合，不是登记过 cell manifest（实验单元清单）的因子实验。已有合同要求 observation process、actor mixture、identity association、owner habit regime、transient noise 五个因子和四个关键交互，但 factor levels、独立实验单位、primary utility、MDE 和 power target 尚未选择。因此本轮没有把 80 episode 冒充成 powered factorial evidence。

### D. cross-module causal coupling（跨模块因果耦合）

19 个 runtime ablation（运行时消融）已经能执行，但旧 pilot 以 deterministic LLM evidence（确定性 LLM 证据）为参照，而且只报告均值差。现有 cut 也多是“删除整个模块”，不等同于只断开一个跨模块边。至少以下 coupling 需要各自定义 coupled/decoupled intervention（耦合／解耦干预）且保持模块本体存在：

- OPCEU → CHEH/PCHMP；
- CF-BOCPD → RGRC；
- CF-BOCPD → CCRR；
- RGRC/CCRR → CIAV。

### E. faithful external reproduction（外部方法忠实复现）

当前 O-STaR、DynaMem、STAR arms 缺 RGB-D、pose、voxel memory、caption/query 和 navigation/manipulation skill observations（导航／操作技能观察）。在选择外部方法、官方代码版本、许可、数据集与传感器输入前，只能保留 proxy 标签，不能宣称忠实比较。

## 待选择后可立即执行的顺序

1. 冻结 primary action utility（主要行动效用）、方向、superiority/non-inferiority margin（优效／非劣界值）和 independent unit（独立实验单位）。
2. 冻结普通 GNN、switching HMM 和 change detector 的信息预算及各自搜索空间。
3. 冻结五因子水平和 long-horizon schedule（长期时序表），据 pilot variance（先导方差）计算样本量。
4. 为四条 coupling 写只断边、不删模块的干预实现，并为每条方法独立调参。
5. 选择至少一个外部强方法及其官方实现、输入和 license path（许可路径），再做 faithful reproduction；其余外部方法继续标为 adapter/proxy。

这些选择完成后，现有 trusted artifact verifier（可信产物验证器）可以从机器可读产物推导调参、公平输入、功效、耦合正效用、full-rerun equivalence 和污染—恢复 Pareto，而不接受调用方自报通过。
