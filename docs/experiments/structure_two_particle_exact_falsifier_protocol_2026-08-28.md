# Structure Two particle exact-enumeration falsifier protocol（2026-08-28）

协议 ID：`structure-two-exact-enumeration-falsifier@0.1`  
证据阶段：**pilot-informed development conformance test（先导试跑辅助的开发符合性测试）**  
适用方法回执：`structure-two-nap-rbtpr-rc@0.1`

本协议在本地临时运行器校准后冻结，正式仓库 artifact 在冻结后生成。因此它不是确认性
预注册，不得用于论文优越性、新颖性或真实机器人有效性声明。

## 1. 问题

在归因歧义、迟到／矛盾反馈、短阶段和开放人物条件下，固定预算的 typed particle
revision（类型化粒子修订）能否：

1. 比不可复苏的 incremental beam（增量束搜索）更接近精确后验；
2. 保留不低于增量束搜索的真值支持；
3. 在 exact Bayes action（精确贝叶斯行动）读出上不产生更高 regret（遗憾）；
4. 在平均 total variation（总变差）上位于 full-rerun beam（完整重跑束搜索）0.05 内；
5. 使用少于完整重跑束搜索的候选评分次数。

本轮不回答完整七算子是否超过 AMG，也不回答 neural amortized proposer（神经摊销提议器）
是否有效。

## 2. 有限状态空间

精确枚举状态为：

\[
\chi=(H,R,I,C,Z),
\]

其中：

- event mechanism：`direct / handoff`；
- ordered actor path：6 种 owner/guest/unknown 有序路径；
- identity：`target / decoy`；
- cause：`observation / actor / identity / habit / noise`；
- regime：`old / new / reactivated`。

完整状态数为：

\[
2\times6\times2\times5\times3=360.
\]

精确后验和所有近似方法还必须保留独立的 `unresolved` 概率质量。

## 3. 登记场景

采用完整 `2^4=16` 场景：

1. low/high attribution ambiguity；
2. ordinary/adverse delayed feedback；
3. long/short regime；
4. known/open-world actor。

每个场景包含初始证据和一条迟到证据。高歧义场景弱化人物和机制证据；adverse feedback
场景在迟到帧中加入机制与原因矛盾；短阶段场景要求阶段证据真正改变行动位置。

## 4. 比较方法

近似状态预算固定为 24：

1. `incremental_beam`：第一帧选出的 24 个状态在迟到证据后只能重加权；
2. `full_rerun_beam`：迟到证据后从全部 360 个状态完整重选 top-24；
3. `bootstrap_particle_filter`：从注册先验采样24个粒子，不做 rejuvenation；
4. `typed_particle_revision`：第一帧 top-24，每个粒子在迟到证据后产生单字段邻域，经过
   类型化约束和显式 unresolved 归一化后保留24个粒子。

`typed_particle_revision` 必须实际通过
`NeuralParticleProposal → ParticleRevisionReceipt → normalize_particle_revisions`
合同运行。

本轮的 proposal 是 `deterministic-structured-proposal@0.1`。由于没有训练产物，真正的
neural amortized proposal arm 固定为 `not_run_no_trained_artifact`，不得用启发式分数冒充。

四种近似方法具有相同状态保留预算，但候选评分次数不同，必须分别报告，不能声称相同计算
预算。

## 5. 指标

- posterior total variation（后验总变差）；
- truth support rate（真值支持率）；
- truth posterior（真值后验）；
- unresolved probability（未决概率）；
- action regret against exact Bayes；
- action match rate；
- candidate evaluations（候选评分次数）。

行动由阶段边缘后验读出：`old→desk`、`new→cabinet`、`reactivated→shelf`。这确保阶段后验
不是内部不可见变量。

## 6. 开发门

全部门必须同时通过：

```text
typed mean TV <= incremental-beam mean TV
typed mean action regret <= incremental-beam mean action regret
typed truth support >= incremental-beam truth support
typed mean TV <= full-rerun-beam mean TV + 0.05
typed candidate evaluations < full-rerun-beam candidate evaluations
high-ambiguity + adverse-feedback subset:
  typed TV <= incremental-beam TV
  typed action regret <= incremental-beam action regret
```

通过只表示当前确定性类型化粒子修订没有在有限模型中被立即证伪。失败则重构粒子状态、
邻域修订核或 unresolved 处理；两种结果都不授权删除结构二能力。

## 7. 固定限制

- 手工定义的有限 likelihood model；
- 没有训练 neural proposer；
- 没有 RGB-D、真实家庭或机器人执行；
- 没有 AMG 行动比较；
- 粒子预算24和0.05门是开发诊断值，不是确认性 margin；
- 不能把本轮通过写成论文方法收益。

