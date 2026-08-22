# 方向结构二 Major Revision P0 整改与创新边界

日期：2026-08-14  
结论：P0 实现缺陷已形成代码与测试闭环；论文创新仍未成立，下一阶段必须跑忠实近邻基线和行动级效用实验。

## 1. 审核问题与整改状态

| 审核问题 | 本轮整改 | 自动化门禁 | 当前结论 |
|---|---|---|---|
| D0 随机流被 policy hash 改变，不是真共同随机数 | 新增 `run_paired(..., paired_noise_seed)`，同一 \(U_t\) 分别阈值化 | 改 policy ID 后 100-step 选择序列相同；低 propensity 选择集合是高 propensity 子集 | 已修复 |
| D0-O 拼接产生 session/trace 标签捷径 | 配对运行共享规范化 stream/session/trace；输入契约强制每对只有一个共同身份 | 三类 D0 的全部 opportunity/result 只有一个 session 和 trace | 已修复 |
| D0 是已知变点的配对诊断，不是在线归因 | 保留 D0 诊断；另建单流未知变点任务 | 30 cases；6 seeds；5 families；跨 household/object；含两类组合变化；输入不含 control/change/family/truth | 任务底座已完成，算法未完成 |
| 不可识别样本仍按单标签 MAP 计分 | 新增 identifiability status、acceptable cause set、intervention available 与正确弃权 | Log Loss、Brier、正确/错误弃权、selective risk、risk–coverage 均有测试 | 已修复 |
| CHEH 把 posterior 再乘 posterior，先验双计数 | Actor evidence 必须声明 reference prior；CHEH 乘 likelihood ratio | neutral posterior=reference prior 时更新前后完全一致 | 已修复 |
| 同一人物证据可反复使用 | revision/history 记录 record ID 与 evidence cluster ID；重复/相关簇拒绝；有效样本权重缩放似然比 | 同 ID 重放拒绝；换 ID 但同 cluster 仍拒绝 | 已修复 |
| authorization 被作为可补偿软乘数 | 从三份方法公式中移出，改为 hard gate；privacy 为显式效用成本 | 文档约束，工程 hard-gate 尚待 RGRC 实现 | 规范已修复，运行时待实现 |

## 2. 近邻先验工作的直接威胁

本轮实际核验来源：Springer Nature 原文页、White Rose 作者稿元数据/摘要、PMLR 全文、Boutilier 作者公开全文/出版元数据。未访问 Google Scholar、Web of Science、Scopus、IEEE Xplore、ACM DL、CNKI、万方，因此这是 scoped prior-art check（限定范围先验审核），不是 systematic review（系统综述）。

| 先验工作 | 证据等级 | 已覆盖功能 | 对本项目的限制 |
|---|---|---|---|
| Bernert & Ramparany, 2021, *A Belief Update System Using an Event Model for Location of People in a Smart Home* | full text checked（Springer HTML 全文） | 在稀疏智能家居观测间探索所有兼容事件序列，用事件序列解释新观察并更新人物位置事实 | “观测间隙事件序列 + 信念更新”不能作为 CHEH 新颖性 |
| Damen & Hogg, 2012, *Explaining Activities as Consistent Groups of Events* | full text checked（2026-08-21 下载 White Rose 作者稿并检查方法、搜索、实验、结论与限制） | 用 AMG 规定事件层次、属性与约束，映射为 Bayesian network；比较 greedy、MHT、RJMCMC-SA 和整数规划求全局 MAP | “相互依赖事件的全局一致解释/多假设搜索”不能作为 CHEH 新颖性；必须在跨时间可撤销来源、未知人物和行动污染上区分 |
| Knoblauch & Damoulas, 2018, BOCPDMS | full text checked（PMLR PDF） | 在线联合维护 run length 和 model identity，并进行预测、模型选择与变点检测 | CF-BOCPD 不能只说“BOCPD 加原因变量”；cause-specific selective reset 必须改变不同长期参数块并产生行动收益 |
| Boutilier, 1996, *Abduction to Plausible Causes: An Event-based Model of Belief Update* | full text checked（作者公开全文经搜索索引核验） | 用可信事件解释观察，再预测这些解释的后果，建立事件溯因式 belief update | “用事件解释新观察并更新信念”已有基础；CHEH 必须落在具身人物—物体责任、概率互斥、来源版本、迟到证据撤销和长期污染代价 |

代表性查询：

```text
site:link.springer.com "A Belief Update System Using an Event Model"
"Explaining Activities as Consistent Groups of Events" multiple hypotheses
site:proceedings.mlr.press BOCPDMS model selection run length
Craig Boutilier event-based model belief update plausible causes
```

## 3. 已实现功能与仍需证明的方法创新

### CHEH

已有覆盖必须明确提醒：事件逻辑序列解释、Bayesian 多假设活动解释和 event-based belief update 都已经存在。当前代码新增了 mutually-exclusive normalized hypothesis history（互斥归一假设历史）、likelihood-ratio revision（似然比修订）、record/cluster 防双计数、provenance binding（来源绑定）、retract/rebuild，以及 top-1/独立候选两个直接基线。

但目前只可写：`method specified + implementation vertical slice + baselines runnable`。要真正创新，必须在完整 pick-up/carry/handoff/place 真值、迟到证据、身份噪声和下游长期污染中，显著优于：

1. 2021 事件序列 belief update；
2. 2012 multiple-hypothesis activity explanation；
3. top-1 event graph；
4. independent event candidates。

### CF-BOCPD

已有覆盖必须明确提醒：BOCPDMS 已联合 \(p(r_t,m_t\mid y_{1:t})\)。本项目不能把 \(m_t\) 改名为 \(C_t\) 就宣称创新。

仍有价值的新增算子是：

\[
p(r_t,C_t,Z_t,\Theta_t\mid D_{1:t}),\qquad
\Theta_t = R_{C_t}(\Theta_{t-1}, D_t)
\]

其中 \(R_C\) 必须是可测试的 selective reset operator（选择性重置算子）：observation cause 只更新观察模型，actor cause 只更新人物混合，identity cause 只更新关联，owner-habit cause 才允许更新个体阶段，noise cause 不改长期参数。它必须在未知变点单流任务上与独立调参的 BOCPDMS 比较 false owner-habit change、延迟、proper score 和真实行动效用。

## 4. 当前创新成熟度与下一道门

- D0：`diagnostic benchmark corrected`，不是算法创新；
- online attribution：`task implemented`，不是 CF-BOCPD 完成；
- CHEH：`vertical slice implemented; direct baselines runnable`，尚未通过直接对照；
- PCHMP / OPCEU / RGRC / CCRR / CIAV：仍按统一论文范围保留，不能删；下一步按依赖顺序实现；
- 论文主张：仍为 `Major Revision`，禁止使用“首次”“已证明优于”或把 31 个定向测试当作论文实验。

2026-08-21 推进：M30 `synthetic-routines@0.3` 已扩展为完整隐藏交接链；2021 compatible-sequence 和 2012 AMG constrained MAP 的领域适配基线已可运行。80-case 多 seed 死亡测试先发现 CHEH 完整链 Top-1=0.500、unknown handoff 不可表示。随后 ORRER v0.1 已实现开放未知角色、机制/有序角色证据、影子后验和正证据门控 reactivation；完整链与 unknown coverage 均修复到 1.0。但是获得相同三类证据、同样开放 unknown roles 的 matched AMG 也达到 1.0，所以 `strong baseline superiority` 仍失败。下一门为 ORRER×RGRC 的长期错误写入、可逆恢复成本和具身行动效用。项目二其余模块与统一单篇论文范围不删减。
