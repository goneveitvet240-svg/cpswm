# 结构二高风险接口闭环记录（2026-09-07 修订）

## 结论先行

本轮修复了 neural proposal `q`（神经提议分布）与 posterior weight（后验权重）的运行时契约，并把 CIAV 的主动观测真正落到 OPCEU 记录和统一 evidence-factor trace（证据—因子消费轨迹）上。CF-BOCPD/CCRR 的 `Z`、identity 和时钟语义也已写成可执行类型与组合函数。

Task 7 的五臂历史支持恢复实验已经完成。修复 reservoir boundary（储备池边界）后，`reservoir_only` 在冻结的 16-cell D0 矩阵上与 full rerun（完整重跑）逐项等价且通过门槛；`backward_message_only` 与 `combined` 仍失败。因此只确认“前置历史检查点 + 边界重放”这一条开发路径，不把后向消息或组合臂改写为成功。

v0.6 的 60-episode belief/readout cross-swap（信念/读出交叉替换）记录到 22 次 put-back readout disagreement（放回读出分歧）。14 个 native contamination event（原生污染事件）的最早可见候选链均包含 RGRC slow commit（慢速提交）：`unknown_actor` 事件的 owner mass 仅为 `0.1065040650`，仍被写进长期统计；但任意一侧 cross-swap 都消除了该污染，所以现有证据只能说明 belief/write 与 readout 的交互，不能单独宣称 RGRC 是因果首错点。

## 1. Neural q 与 posterior weight

`NeuralAmortizedParticleRuntime` 现在将 MLP 输出严格限定为

\[
q(x_t, a_{t-1})
\]

并以 deterministic systematic sampling（确定性可复现的系统采样）抽取 `K=24` 个 parent-child proposals（父子提议）。每个样本的未归一化重要性权重为

\[
\log w = \log p(a_{t-1}) + \log p(x_t\mid a_{t-1})
 + \log \phi_{post}(x_t;B_t) + \log \psi(x_t) - \log q(x_t,a_{t-1}).
\]

这里的 `phi_post` 是 upstream posterior projection（上游后验投影），不是 raw observation likelihood（原始观测似然）。`ParticleRevisionReceipt` 将它放在独立字段并把 observation likelihood 固定为 0；同一 source snapshot ID 只能消费一次。神经分数不再直接混入 `belief.cause_posterior`。全局 trace 将 `neural-q:*` 登记为 `proposal_distribution`，只作为 importance denominator（重要性分母）消费；它不能被标记成 observation likelihood。

## 2. Task 7 历史支持恢复五臂结果

固定 D0 16-cell、seed 307、replicate 419、`K=384`：

| Arm | mean action TV | mean max belief TV | contamination | selected-action match | marginal evals |
|---|---:|---:|---:|---:|---:|
| reservoir only | 0 | 0 | 0.000847 | 1.0000 | 474,848.125 |
| backward message only | 0.167897 | 0.498178 | 0.046012 | 0.8750 | 26,880 |
| combined | 0.262613 | 0.474462 | 0.006688 | 0.6250 | 26,880 |
| current Task 7 v0.4 failure control | 0.166814 | 0.247867 | 0.007975 | 0.8750 | 340,883.75 |
| full rerun reference | 0 | 0 | 0.000847 | 1.0000 | 571,808.125 |

原实现把 reservoir 截在错误观测之后，导致该观测已经淘汰的支持无法恢复；修到错误观测之前并保存 RNG state 后，`reservoir_only` 与 full rerun 精确等价，且 marginal evaluations 减少约 16.95%。`backward_message_only` 仍缺失已淘汰支持；`combined` 每个前缀仅保留一个 suffix descendant/backward message（后缀后代/后向消息），也不足以代表条件后缀分布。五臂实验的 `any_approximate_arm_passed=true` 只由 `reservoir_only` 贡献。

## 3. CF-BOCPD / CCRR 语义

- CF-BOCPD 输出 `p(C,r | evidence)`；`C` 包含 observation、actor、identity、habit、noise。
- CCRR 的 `Z` 是条件 regime transition（状态段转移）：`p(Z | C,r,context,library)`，不是第二次 observation likelihood，也不是经验校准概率的声明。
- 联合量只能按 `p(C,r) p(Z | C,r,context,library)` 组合。非 habit cause 的 create/reactivate mass 被显式转入 unresolved，不能静默创建 habit regime。
- identity association（身份关联）仍是独立粒子变量；identity-switch probability 被显式提升到 `C=identity,r=0`，不再作为旁路质量。
- run length 的时钟为 `effective_observation_opportunity`：每个有效推理机会只走一 tick；CIAV 会产生一个单独且有自身 likelihood-model binding 的 OPCEU action record，但它绑定当前 inference update，不触发第二次 CF-BOCPD tick。wall time（墙钟时间）只作 covariate，不替代离散 run length。
- CF snapshot 与 CCRR scoring envelope 必须具有相同的 clock 和 opportunity index，否则组合直接拒绝。

## 4. 全局 evidence-factor consumption trace

v0.6 真实 `_FullProjectTwoMethod` 已产生一条 append-only hash chain（仅追加哈希链）：

```text
OPCEU observation likelihood
  -> PCHMP exactly-once likelihood consumption
  -> PCHMP posterior summary
  -> CF-BOCPD cause/run transition
  -> CCRR conditional Z transition
  -> RGRC commit or non-commit consumption
  -> action readout

execution feedback
  -> ORRER/CHEH revision posterior
```

Trace 强制同一 observation/action likelihood factor 对同一 target distribution 只能按似然消费一次；posterior summary 不能重新作为似然，也不能通过 DERIVE/COMMIT 再铸造成似然；COMMIT 必须物化为可继续追踪的 `commit_delta`。同一 evidence cluster 不能更换 likelihood model；同一 record ID 不能绑定不同 payload；完全相同的 retry 通过 idempotency key 返回原 receipt，语义不同的重用会失败。哈希链只声明 in-process content binding（进程内内容绑定），不冒充独立签名或外部真实性。

## 5. CIAV 接入真实 OPCEU 闭环

CIAV 选择动作后，先冻结 `ObservationOpportunityRecord`，包含 action ID、selection probability、visibility/detection probability、likelihood-model ID 和 actor-likelihood-table hash。actor prior（主体先验）与按 outcome 注册的 likelihood table 在 callback 前完成校验和绑定。只有随后执行的 realizer callback 才能读取 D0 evaluator truth，并返回已注册 outcome；callback 无权提交 actor posterior、object posterior、location posterior 或 detected location。

CIAV selection 依赖 latent-cause belief，missingness 明确声明为 MNAR（非随机缺失）；当前不作无偏 IPW 声明，applied weight 固定为 1，并记录 residual-bias note。OPCEU loop 用冻结的 `prior × likelihood` 自行归一化 actor posterior；对象与位置来自调用前已经冻结的 robot-visible context。OPCEU 产生 observation factor，CIAV 对 fast-action owner posterior 正好消费一次，然后只把统一证据 record ID 交给 reversible fast ledger（可逆快速账本）。CIAV wrapper 与底层 v0.6 runtime 共用同一个全局 trace。

## 6. Cross-swap 与 v0.6 contamination 首错点

完整 60×32 development holdout（开发留出）结果：

| Belief | Readout | put-back error | contamination | cumulative search regret | cumulative action regret |
|---|---|---:|---:|---:|---:|
| Project Two | Project Two | 0.053646 | 0.007292 | 104.333333 | 207.333333 |
| Project Two | AMG | 0.053646 | 0 | 133.000000 | 236.000000 |
| AMG | Project Two | 0.053646 | 0 | 121.666667 | 224.666667 |
| AMG | AMG | 0.053646 | 0 | 133.000000 | 236.000000 |

两条 native diagonal（原生对角线）在每一步都要求动作严格相等，否则运行失败。结论：

- 固定 Project Two belief，换成 AMG readout 后污染从 `0.007292` 降为 `0`，action regret 增加 `28.666667`；Project Two readout 同时带来 search ordering 收益和污染触发。
- 固定 Project Two readout，换成 AMG belief 后污染也从 `0.007292` 降为 `0`。因此污染需要 Project Two belief components 与 Project Two readout 的交互，不能只归因于其中一侧。
- 14/14 污染都发生在 step index 1，true actor=`unknown_actor`；source owner mass=`0.1065040650`，source was slow committed=`true`、quarantined=`false`；fast/surviving selected mass 均为 0，regime/hybrid selected mass 分别为 `0.5070511136` / `0.1740262501`。
- 当前最早可操作候选接口是：RGRC 允许极低 owner mass 的 unknown-actor event 写入 cold-start slow statistics（冷启动慢统计），随后 regime/hybrid components 与 Project Two readout 共同触发错误动作。它不是 fast-action threshold 过低，但现有 cross-swap 也不能排除 readout interaction。

该定位是 D0 development diagnosis（开发诊断），报告中 `causal_first_fault_claim_allowed=false`；它不是跨环境因果识别或 paper-level claim（论文级结论）。下一轮应围绕 RGRC 的 low-owner-mass admission rule（低主人质量准入规则）和 readout interaction 做预注册的 2x2 干预，同时保留 unknown、reversible attribution、CIAV 和完整七算子系统，不能直接删模块规避污染。

## 工件

- `benchmarks/structure_two/structure_two_task7_support_recovery_five_arm_v0_1.json`
- `benchmarks/structure_two/structure_two_cross_swap_contamination_v0_1.json`
- `configs/project_two_experiments/structure_two_task7_support_recovery_five_arm_v0_1.json`
- `configs/project_two_experiments/structure_two_cross_swap_contamination_v0_1.json`
