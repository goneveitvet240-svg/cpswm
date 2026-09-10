# 结构二自适应计算预死亡测试 v0.1

日期：2026-09-09
协议：`structure-two-adaptive-computation-pre-death-test@0.1-development`
证据等级：`D0_COUNTERFACTUAL_BRANCHING_DEVELOPMENT_ONLY`

冻结配置记录的 schema 状态：
`PROTOCOL_SCHEMA_FROZEN_LOCAL_ADAPTIVE_RUNTIME_BOUND_REMAINING_GATES_UNRESOLVED`；终审后的 canonical
readiness 状态仍为 `PROTOCOL_IMPLEMENTED_EXECUTION_BLOCKED`。最终机器工件已重建并鲜验证：readiness
content SHA 为 `f1356ad5aa2ac427c4d9168acd79dc43084e8246be264eb423f9521ff077a54b`，source
manifest SHA 为 `ebf05dad4785182c139a552658344acd9a3b812e3437f32aabfa5dcbe84ac9ff`。
冻结的是 schema、六条候选路径的精确 mode vector（模式向量）、安全/债务边界、
总体切分和统计判据，不是六条路径均已具有完整生产实现的证明。项目所有者已在 2026-09-09 选择
Architecture A（架构 A）；当前实现边界是 transitively read-only plan/consumption registries
（传递只读计划/依赖注册表）与部分路径 kernel（内核）、P0 debt（P0 推理债务）、P3/P5 的
different-location detected full CIAV closure
（异位置检测的完整主动验证反馈闭包）、same-location fast verification（同位置快速验证），以及已执行
算子的 elapsed-time receipts（耗时回执）。caller-provided
context 已在两个 adaptive 公开入口冻结为 runtime-owned snapshot（运行时自有快照），pending debt 也已
阻断 legacy 与 direct-core 的核心状态演化；negative observation 尚无完整下游闭包，屏障也不覆盖全部
wrapper rebinding（包装层重绑定），replay 也不绑定 origin policy/trace。这些修复不等于完整 P0–P5
executor、state-derived path eligibility（状态派生路径资格）、后果性运行时身份或
完整资源核算已经成立。

## 当前结论

协议、合法路径注册表、inference debt（推理债务）契约、完整影子矩阵校验器、
validation-selected best fixed（验证集选择最佳固定路径）与 leave-one-seed-out cross-fitted
hindsight selector（留一随机种子交叉拟合事后选择器）已有实现和定向检查；终审后的最终 source-bound
回执已经重建并通过 fresh verification（鲜验证），不能沿用较早工件的哈希或状态。

当前真实执行状态仍为：

`PROTOCOL_IMPLEMENTED_EXECUTION_BLOCKED`

历史 Task 8 状态保持 `IMMUTABLE_FAIL`，本协议没有重写或覆盖旧证据。

这不是实验失败，也不是缩小结构二。Architecture A 保留旧 no-plan/no-trace call shape（无计划/无轨迹
调用形态）；该窄门本身不是行为等价证明。traced legacy 路径能为现有普通
transition（状态转移）生成六个阶段调用回执及一个明确的 CIAV 未调用处置回执；它没有把普通
transition 冒充 `P5_FULL_EAGER`。adaptive 入口目前能够使用传递只读计划/依赖注册表和部分 path kernels，
签发 P0 debt，并在 P3/P5 对异位置 detected observation 进入完整反馈闭包、对同位置检测进入快速验证；
已执行算子的正耗时进入回执。终审还确认两个公开入口的 caller context snapshot 与 pending-debt
legacy/direct-core transition barrier 已修复；未检测到观测的完整闭包和全 wrapper 屏障均未成立。

但是，`AdaptiveRouterFeatures` 仍由调用方提交，尚无从当前生产状态独立构造它的 feature extractor
（特征提取器）；P1、P2、P4 尚无相互独立的实质内核，运行时 failure/timeout fallback（失败/超时
回退）也只有注册语义、没有完整执行。因此以下四项必须为 `false`：

- `path_eligibility_policy_bound_to_production_state=false`；
- `legal_path_executor_bound_to_production_runtime=false`；
- `p0_p5_consequential_runtime_identity_established=false`；
- `resource_accountant_bound_to_production_execution=false`。

纯评估器接收的仍是 caller-controlled development matrix（调用方控制的开发矩阵），无论算出正候选
还是负候选，都不得升级为 headroom 成立、死亡判定或 router（路由器）训练许可。

## 研究问题

在全部七个算子、统一状态、写入权限和可逆纠正能力都保留的前提下，检验：

> 在相同硬安全条件和资源预算下，依赖状态选择合法计算路径，能否在长期任务、记忆与恢复质量
> 前沿上超过验证集独立选择的最佳固定合法路径？

只有未来 source-bound（源码绑定）、清单完整且有确认集保管的执行中，cross-fitted selector 仍不能
超过 best fixed，才有资格讨论淘汰 adaptive routing（自适应路由）主张；即使如此也不淘汰七算子
统一框架。当前纯评估器本身无权作出正结论或死亡判定。

## 完整范围

每条路径都必须产生以下七个算子的 mode receipt（模式回执），并保持生产顺序：

`OPCEU → ORRER/CHEH → PCHMP → CF-BOCPD → CCRR → RGRC → CIAV`

实际调用另用 ordered invocation receipts（有序调用回执）记录 operator、mode、phase、调用 ID 及
输入/输出状态哈希；同一算子在 CIAV 反馈闭包或债务重放中可以重复出现。这样既保留隐藏事件推断、
多人责任、开放世界未知、非平稳阶段学习、可逆归因、主动验证与具身执行反馈，也禁止把它们变成
任意七位开关或用一个算子哈希掩盖多次调用。

`P3/P5` 中 CIAV planner（主动验证规划器）的调用是必需的，但物理验证动作不是强制执行。取得
不同位置的新 observation（观测）时，必须出现并哈希绑定后续 `OPCEU → … → RGRC` 完整 feedback
closure（反馈闭包）；确认仍在原位置时走单独的 `same_location_fast_verification`，只修改可逆快速
记忆且 `long_term_write=false`；合法 no-action（不执行动作）不能伪造任何闭包。

## 六条合法宏路径

| 路径 | 作用 | 允许延迟的重计算 |
|---|---|---|
| `P0_SAFE_DEFERRED` | 强制语义维护与写入安全，日常昂贵精化延后 | ORRER/CHEH、CIAV |
| `P1_EVENT_ACTOR_LOCAL` | 局部事件—人物展开、受影响传播和可逆闭包 | CIAV |
| `P2_REGIME_RECOVERY_LOCAL` | 变化点、历史阶段竞争和定向恢复 | CIAV |
| `P3_ACTIVE_VERIFY` | 主动验证及 CIAV→OPCEU 反馈闭包 | 无 |
| `P4_EVENT_ACTOR_PLUS_REGIME` | 检验事件—人物与阶段—恢复的组合互补性 | CIAV |
| `P5_FULL_EAGER` | 同等优化条件下的完整即时精化参照 | 无 |

这张表冻结的是六条宏路径最终必须满足的语义，不是当前实现完成度。当前只有 plan registry、部分
kernels、P0 debt、异位置 detected full CIAV closure 和同位置 fast verification；negative-observation
full closure 尚未实现，
尤其 P1/P2/P4 还不能被解释成三条已独立实现的实质计算路径。

“延迟”必须生成有效债务，不能解释为反证。运行中 timeout/failure（超时/失败）从 `P0`–`P4`
回退到 `P5_FULL_EAGER`，P5 再失败必须终止于有动作回执的 safe abstain（安全弃权）。前置升级则按
typed cause（类型化原因）冻结目标：invalid router input、expired debt、risk bound exceeded 可升级
到 P5；privacy violation 或 unsafe/unauthorized memory transition 必须在任何原路径调用前直接
`SAFE_ABSTAIN`，不能先执行同样不合资格的 P5。每一级成本及 failure/timeout receipt 都必须入账，
fallback outcome 不得冒充原低成本路径的成功结果。上述是目标合同；当前 fallback executor 尚未
实现，因此不能把 router 选择了 fallback target 写成已经执行 fallback。

## 推理债务契约

每项延迟计算必须绑定：

- 原始证据哈希、未决假设和路由前检查点；
- 七算子版本哈希、延迟算子集合、重放算子序列与作用域；
- 动作与归因翻转风险上界及各自推导哈希；
- 结算前允许/实际发生的动作，以及禁止/实际发生的长期记忆迁移；两者均使用封闭 enum（枚举），
  未知名称 fail closed（失败即关闭）；正翻转风险必须禁止长期写入、永久身份/归因提交和不可逆撤销；
- 迟到反证、长期提交前、风险越界和到期四种强制升级触发器；
- 恢复状态、eager reference（即时完整参照）、信念 TV、动作、人物身份、commit/retract、权限、
  privacy state（隐私状态）和效用差异。

债务重放不是去重后的算子集合：若上游精化与 CIAV 同时延迟，先从最早延迟算子向前重建到 CIAV，
再执行 `CIAV → OPCEU → … → RGRC` 反馈闭包，因此允许重复调用。评分 horizon（时域）结束时仍有
pending debt（未结债务），或债务在迟到反证前就被宣称结清，该分支不可行，不能按零损失处理。

恢复门冻结为：belief TV p95 不超过 `0.05`、单项最大值不超过 `0.10`、action top-1 agreement
不低于 `0.99`，后果动作、人物身份、commit/retract、authority state（权限状态）与 privacy state
必须完全一致，效用相对与绝对差异均不超过 `0.02`。p95 分别在 validation/confirmatory 内按
“家庭内最坏值，再对家庭等权取 p95”计算，证书拆分数量不能改变权重。

## 反事实分叉与防泄漏

每个决策点必须在 router 和任何路径相关特征运行之前分叉。所有路径必须拥有相同的：

- 路由前状态、机器人可见输入、模型权重与候选支持；
- 按变量键控的外生事件日程与共同随机数；
- 路由特征及其来源哈希。

动作发生分歧后，各分支必须从相同结构因果噪声自行生成后续观察，禁止复制 factual log
（事实日志）。每条分支使用全局唯一的新运行时实例，并提供有序、可重复的算子调用回执。决策 ID、
checkpoint 与 debt ID 不得跨上下文复用。每条记录必须把 replicate seed 精确绑定到统一冻结的
RNG algorithm/version、初始状态哈希、RNG source digest 和 canonical schedule payload hash；不同
seed 可以在离散或无事件场景中合法地产生相同 schedule 内容，不能用“哈希必须不同”冒充随机流
独立性证明。当前 RNG source 仍未绑定生产 executor，因此仍是 readiness blocker（就绪阻断项）。
路由前禁止读取真值、未来反馈、其他路径输出或完整推断结果。

evidence package（证据包）显式绑定完整 protocol content SHA，report 再绑定完整 evidence digest；
但调用方仍可整体伪造并自洽重哈希，因此只有从仓库重新加载协议、由生产 executor 重算且具备独立
保管的未来入口才可授权结论。

数据按 household（家庭）隔离，并复用 Task 9 v1.1 的已冻结 population/seed/split binding
（总体、种子与切分绑定）：`household-001` 至 `household-008` 为验证家庭，`household-009` 至
`household-048` 为确认家庭；每个家庭必须覆盖 seeds `104729` 与 `130363`。验证家庭只用于选择
固定路径；确认家庭一次性比较，不能反向改变选择。当前 frozen branch-point manifest（冻结决策点
清单）尚未绑定，所以这些结构校验仍不能证明没有挑选 trajectory/decision。

## 质量—成本前沿

不把安全违规并入可抵消的标量效用。硬门通过后，分别在以下质量轴上比较：

- `task_loss`
- `memory_loss`
- `recovery_loss`

成本按完整 eager 路径归一化，显式记录 online compute、latency、energy、peak memory、persistent
storage、replay compute、embodied sensing 和 router overhead。当前冻结三个资源包络：
`LEAN_050`、`BALANCED_075` 与 `FULL_EAGER_ENVELOPE`。

每个预算—质量轴组合中：

1. 只用 validation 选择一个固定路径；
2. 在 confirmatory 上保持该路径不变；
3. 对每个确认上下文留出一个 replicate seed，仅用其他 seed 的结果选择路径，再只在留出 seed 上
   评估；两个 seed 交换角色后聚合，避免用同一随机噪声既选赢家又估计收益；strict-winner gap
   只与留出 seed 上同样合格且不超预算的竞争路径比较；
4. point estimate（点估计）与 bootstrap 都先在家庭内聚合、再对家庭等权；
5. 对 absolute effect、relative effect、其余轴 non-inferiority 与六条路径的 winner share 共 `90`
   个单侧界做 family-wise Bonferroni 校正。

Gate 1 是纯诊断上界：hindsight oracle 与 best fixed 都不支付 router 特征和推断开销，避免固定
路径被不公平地收取它根本不需要的调度成本；两者仍支付各自真实路径的执行、存储、重放和具身
成本。后续 observable policy gate 必须完整计入特征提取、路由推断与调度同步开销。

冻结配置使用 `400000` 次 household-cluster bootstrap；在 `α=0.05/90` 的每个极端尾部至少保留
`200` 个 Monte-Carlo draws，避免用少数 order statistics（次序统计量）作死亡门。只有未来
source-bound 执行同时满足以下条件，才可记录 hindsight headroom（事后上界空间）：

- 绝对改善点估计及校正后单侧下界都至少为 `0.02`；
- 相对改善点估计及校正后单侧下界都至少为 `10%`；
- 其他质量轴的校正后单侧上界均不劣超过 `0.02`；
- 至少两条路径的家庭等权 strict-winner share（严格赢家占比）点估计及校正后单侧下界都不少于
  `10%`，且严格胜出差至少 `1e-6`；单一可行路径或平局不算赢家。

未来 source-bound 正结果也只允许进入 observable policy ceiling（可见信息策略上界），不代表部署
路由器成立。当前 caller-controlled matrix 只会输出
`CALLER_CONTROLLED_*_CANDIDATE_REQUIRES_SOURCE_BINDING`；无可评估预算单元时输出
`INVALID_NO_SCIENTIFIC_CONCLUSION`。它既不能授权正结论，也不能输出有效的
`KILL_ADAPTIVE_ROUTING_FOR_REGISTERED_LIBRARY`。

## 当前阻断项

终审后的 canonical readiness（规范就绪判断）显示：

- 新的 typed SEARCH/PUT_BACK 动作构造门仍是通过的单独 D0 诊断；
- historical Route-C runtime identity（历史 Route-C 运行时身份）门仍失败；它是保留的历史诊断，
  **不作为当前 Architecture-A 修复的额外 blocker**，也不追溯改写旧 Route-C；
- production execution-plan interface（生产执行计划接口）已选择 Architecture A，immutable plan
  registry 与部分 kernels 存在；selected-method receipt 的 `operators` 仍只承担七算子 inventory
  （能力清单）校验，不证明六条宏路径均有不同的实质执行；
- P0 debt、异位置 detected full CIAV closure、同位置 fast verification 和 executed-operator elapsed
  receipts 已有局部实现；caller context
  在两个 adaptive 公开入口复制为 runtime-owned snapshot，pending debt 会阻断 legacy、traced legacy、
  direct-core transition 与装饰过的 public core mutator；但 negative-observation full closure 未实现，
  policy/evidence-trace 等 wrapper rebinding 在债务期间仍允许，replay 也不绑定 origin policy/trace；
- 上述局部正项不关闭完整路径 executor、状态派生 eligibility、P0–P5 consequential identity 或完整
  resource accounting 四个门。

当前共有 12 个 `blocking_reasons`：

1. `production_router_feature_extractor_not_bound`：没有从当前生产状态独立生成冻结 router features 的
   feature extractor，路径资格仍依赖调用方提交的特征；
2. `legal_path_executor_not_bound_to_production_runtime`：P1/P2/P4 没有独立实质内核，failure/timeout fallback 也未
   执行化，不能把 plan registry 或 partial kernels 当作完整六路径 executor；
3. `p0_p5_consequential_runtime_identity_not_established`：局部调用/闭包回执尚未形成所有合法路径的完整
   execution—invocation—consumption—final-state 后果身份链；
4. `full_adaptive_resource_accounting_not_bound`：已有 elapsed-time receipts，但未覆盖 feature extraction、
   fallback、全部路径和全部注册资源维度；
5. `cross_system_trace_state_atomicity_not_established`：类型化 commit acknowledgement（提交确认）与
   compensating abort（补偿中止）不能证明运行时状态和外部 trace store 共享持久事务边界；
6. `path_specific_operator_budgets_unbound`：六条路径的 operator-specific budgets 尚未数值绑定；
7. `frozen_branch_point_manifest_unbound`：无法排除 decision/trajectory 挑选；
8. `debt_replay_verifier_not_bound_to_production_replay`：债务重放尚未与生产 replay 和 eager-reference
   reconstruction（即时参照重建）形成恢复等价验证；
9. `power_analysis_not_bound_to_empirical_variance_and_icc`；
10. `confirmatory_access_custody_unbound`；
11. `exogenous_rng_source_not_bound_to_production_execution`；
12. `long_horizon_loss_not_bound_to_production_action_consequences`。

当前 readiness JSON 已对 source/config fresh verify；其 12 项 blocker 与上表一致。Task 9 仍是
`DEFINED_NOT_RUN`，不混入上述 12 项，也不能被本地修复开启。

因此当前禁止 confirmatory shadow run（确认性影子运行）、hindsight headroom 主张和 router 训练。
下一项工程工作首先是实现 state-derived feature extractor、P1/P2/P4 独立实质内核和真实 fallback，
再关闭完整 executor、P0–P5 consequential identity 与 full resource accounting；随后才是路径预算、
分支点清单、恢复等价、跨系统原子性、功效、独立托管、外生 RNG 和长期动作后果。

## 文件与复现

- 冻结配置：`configs/project_two_experiments/structure_two_adaptive_compute_predeath_v0_1.json`
- 契约与评估器：`src/cpswm/system/evaluation_operations/structure_two_adaptive_compute_predeath.py`
- 运行器：`apps/evaluation_runner/run_structure_two_adaptive_compute_predeath.py`
- 测试：`tests/test_structure_two_adaptive_compute_predeath.py`
- 自适应运行时测试：`tests/test_structure_two_adaptive_runtime.py`
- 两轮对抗测试：`tests/test_structure_two_adaptive_runtime_adversarial_round1.py`、
  `tests/test_structure_two_adaptive_runtime_adversarial_round2.py`
- 当前就绪工件：`benchmarks/structure_two/structure_two_adaptive_compute_predeath_readiness_v0_1.json`

运行：

```bash
uv run --frozen pytest -q tests/test_structure_two_adaptive_compute_predeath.py
uv run --frozen python apps/evaluation_runner/run_structure_two_adaptive_compute_predeath.py
uv run --frozen python apps/evaluation_runner/run_structure_two_adaptive_compute_predeath.py \
  --verify benchmarks/structure_two/structure_two_adaptive_compute_predeath_readiness_v0_1.json
```

上述 `--verify` 已在最终工件上通过。相关回归为：本文件测试 54 passed，基础 adaptive runtime
10 passed，第一轮 adversarial 8 passed，第二轮 adversarial 12 passed；结构二定向合并回归 229
passed。完整工程审计另有 3,789 passed、1 skipped、1 xfailed，且 mypy、Ruff、compileall、
frozen/offline dependency check 和 `git diff --check` 均通过。

本协议及本地测试均不能建立 independent custody（独立保管）、外部有效性、科学优越性或论文
新颖性。
