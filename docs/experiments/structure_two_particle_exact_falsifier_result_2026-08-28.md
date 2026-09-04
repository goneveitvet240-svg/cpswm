# Structure Two particle exact-enumeration falsifier result（2026-08-28）

> **证据降级声明（2026-09-02）**
>
> 本报告的数值结论已于 2026-09-02 经代码级核验后降级。表中 mean TV `0.0959`、真值支持率 `0.875`、候选评分数 `502.6` 不构成方法收益证据。
> 原文全文保留，不做删改；降级范围与理由见下方「证据降级与仪器局限」一节。

## 证据降级与仪器局限（2026-09-02 追加）

### 该实验实际证明了什么

1. **contract conformance（合同一致性）**：`TypedParticleState → NeuralParticleProposal →
   ParticleRevisionReceipt → normalize_particle_revisions` 这条调用链可以在有限状态下真实执行。
2. **normalization check（归一化检查）**：$\sum_i w^{(i)}_t + w^{unresolved}_t = 1$ 在含显式
   未决质量的情况下成立，未决项没有退化为异常出口。
3. **finite-state truncation behavior（有限状态截断行为）**：在 360 个静态状态上，按结构化
   邻域保留 24 个候选所损失的后验质量是可测且有界的。

### 该实验不能证明的内容（已从收益证据链中移除）

- ~~typed particle revision 比 exact enumeration（精确枚举）更高效~~；
- ~~已证明 rejuvenation（回春修订）相对完整重跑的计算优势~~；
- ~~已支持 Rao–Blackwellization（RB 化）的计算或方差收益~~；
- ~~已支持 neural amortized proposer（神经摊销提议器）~~。

### 已确认的仪器局限（2026-09-02 代码核验）

1. **静态 360 状态**：`LatentState` 为 mechanism(2) × actor_path(6) × identity(2) ×
   cause(5) × regime(3)，没有时间下标。
2. **两帧条件独立**：`_state_log_target` 对固定状态在两帧上求和，帧与帧之间没有转移。
3. **没有真实转移**：`ParticleRevisionReceipt.transition_log_probability` 恒为 `0.0`。
4. **没有真实解析状态 $S_t$**：`statistic_state_ref` 是字符串 `f"analytic-state:{state.key}"`，
   $(\alpha,A,b,\Lambda,\xi)$ 一个都不存在；`run_length` 由 `1 if short_regime else 4` 硬编码。
5. **提议分布退化**：`proposal_log_probability = -log(len(selected))` 为均匀分布，
   `_accepted_constraints()` 使全部 $\psi_j$ 通过，因此重要性权重退化为截断支持上的精确贝叶斯。
6. **Top-K 方法内部先全枚举**：`_beam_result` 与 `_typed_particle_result` 均调用 `_top_states`，
   而 `_top_states` 对全部 360 个状态计算精确 log target 后排序。所谓"近似"= 精确枚举 + 截断。
7. **成本口径不统一**：`candidate_evaluations` 对 incremental beam 是 `360+K`、对
   full-rerun beam 是 `360×2+K`、对类型化修订 v0.1 是 `360+|pool|`（v0.2 复苏门再加一个 K，
   即 `360+|pool|+K`）、对 bootstrap PF 是 `K×frames`。前三者按构造 ≥360（即 ≥ 精确枚举
   本身的代价），最后一个是真实采样代价。这些数字不在同一量纲上，不能同列比较，也不能
   解释为墙钟时间或 FLOPs。

### 结论

本实验保留为 **development evidence（开发证据）**，用于证明合同可执行与归一化正确。
它 **不再进入论文方法收益证据链**。骨干的近似质量、RB 收益、类型化约束收益和提议器收益
必须由 `docs/结构二/方向结构二_骨干尺度证伪器协议_v0.1.md` 定义的链式阶梯任务重新测量。

---

协议：`structure-two-exact-enumeration-falsifier@0.1`  
证据状态：**finite synthetic development conformance evidence；不是论文收益证据**  
方法回执：`structure-two-nap-rbtpr-rc@0.1`

正式 artifact：

`artifacts/project_two_v04_development/structure_two_particle_exact_falsifier_v0_1.json`

- report content SHA-256：
  `01dc66d05f0e2f3896dc8ece23ed3a13d1311e3c4d8de22bb48bb2c2c1809381`
- artifact byte SHA-256：
  `369c45b1ca2620e5ef73c677054c811cb70fe00d5f155c7f1a5bd553f363ca5a`

artifact 同时绑定 falsifier 源码、所选方法源码、方法选择回执和开发协议四个文件哈希。

## 1. 总体结果

360个精确状态、16个完整 `2^4` 场景、近似状态预算24下：

| 方法 | mean TV ↓ | 真值支持率 ↑ | exact-Bayes action regret ↓ | action match ↑ | 候选评分数 ↓ |
|---|---:|---:|---:|---:|---:|
| incremental beam | 0.3710 | 0.3750 | 0.0666 | 0.7500 | 384.0 |
| full-rerun beam | **0.0745** | **0.9375** | **0.0000** | **1.0000** | 744.0 |
| bootstrap particle filter | 0.7524 | 0.1875 | 0.0507 | 0.8125 | **48.0** |
| typed particle revision | **0.0959** | **0.8750** | **0.0000** | **1.0000** | 502.6 |

类型化粒子修订相对不可复苏增量束搜索：

- mean TV 从0.3710降至0.0959；
- 真值支持率从0.375升至0.875；
- exact-Bayes action regret 从0.0666降至0；
- action match 从0.75升至1.0。

它仍未超过完整重跑束搜索：TV 更高0.0214，真值支持率低0.0625；但平均候选评分数减少
约32.4%。因此当前支持的是“较低评分成本下逼近完整重跑”，不是“后验质量超过完整重跑”。

## 2. 高归因歧义＋恶劣迟到反馈子集

| 方法 | mean TV ↓ | 真值支持率 ↑ | action regret ↓ | action match ↑ |
|---|---:|---:|---:|---:|
| incremental beam | 0.5843 | 0.0000 | 0.1329 | 0.5000 |
| full-rerun beam | **0.1889** | **0.7500** | **0.0000** | **1.0000** |
| bootstrap particle filter | 0.8443 | 0.0000 | 0.0661 | 0.7500 |
| typed particle revision | 0.2497 | 0.5000 | **0.0000** | **1.0000** |

类型化粒子修订在最关键压力子集中恢复了 exact-Bayes 行动，但只在一半场景保留真值状态，
低于完整重跑束搜索的0.75。这是当前最重要的失败信号：单字段邻域 rejuvenation（粒子复苏）
仍不足以稳定恢复同时发生的人物、机制、原因和阶段修订。

## 3. 门禁结果

七项 development gates 全部通过：

- 总体 TV 不差于增量束搜索；
- 总体行动遗憾不差于增量束搜索；
- 总体真值支持不差于增量束搜索；
- 总体 TV 位于完整重跑束搜索0.05以内；
- 候选评分次数少于完整重跑束搜索；
- 压力子集 TV 不差于增量束搜索；
- 压力子集行动遗憾不差于增量束搜索。

这只表示确定性类型化粒子修订没有被第一轮有限模型立即证伪。

## 4. 对新结构二的含义

### 已得到支持的局部判断

1. 显式多假设和迟到证据 rejuvenation 比只重加权旧 beam 更合适；
2. `TypedParticleState → ParticleRevisionReceipt → unresolved normalization` 合同可以执行；
3. 阶段后验已真正进入行动读出，不再出现 CCRR 变量存在但行动完全不消费的假通过；
4. 完整重跑仍是必须保留的强恢复基线。

### 尚未得到支持

1. neural amortized proposal 尚未训练或运行；
2. PCHMP 尚未接成神经提议器或粒子势函数；
3. OPCEU、CF-BOCPD、RGRC、CCRR、CIAV 的真实联合收益未测试；
4. 没有与 corrected AMG adapter 比较；
5. 没有真实感知、家庭或机器人证据；
6. 不能声称完整新路线已经成功。

## 5. 下一道阻断门

下一轮不应直接扩大完整七算子实验，而应先修复压力子集的真值支持缺口：

1. 增加二字段／角色链结构化 rejuvenation kernel；
2. 保留 deterministic PCHMP proposal 作为强后备；
3. 训练真实 neural amortized proposer 后，和确定性提议器使用相同粒子预算独立比较；
4. 在新随机种子下要求高歧义＋恶劣反馈真值支持率不低于完整重跑 beam 的预注册容差；
5. 通过后才接 corrected AMG、旧七算子系统和完整行动级比较。

如果神经提议器不能改善压力子集支持率，或只靠显著增加候选评分数追平完整重跑，则当前
amortized proposal/rejuvenation 设计必须重构。

