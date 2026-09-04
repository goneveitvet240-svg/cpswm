# 结构二骨干门：Tasks 11–13 与 P5 独立协议

版本：`v0.1`
协议包：`structure-two-backbone-open-tasks@0.1`
定义状态：**`DEFINED_NOT_RUN`**
证据等级：**仅完成协议定义，尚无实验结果**

机器可读配置：

`configs/project_two_experiments/structure_two_backbone_open_tasks_v0_1.json`

可执行合同：

`src/cpswm/system/evaluation_operations/structure_two_backbone_open_task_protocols.py`

本协议把此前合并登记的 Tasks 10–13 显式拆开：

| 编号 | 唯一问题 | 目标绑定（本地只可提名候选） |
|---|---|---|
| Task 10 | particle budget（粒子预算） | `particle_budget`；由既有 Task 10 承担 |
| Task 11 | resampling policy（重采样策略） | `resampling_policy` |
| Task 12 | rejuvenation kernel（回春核） | `rejuvenation_kernel` |
| Task 13 | differentiability strategy（可微策略） | `differentiability_strategy` |
| `backbone.proposal.P5` | proposer headroom（提议器上界）及 recall decomposition（召回分解） | **无；仅诊断** |

四项拥有不同的 protocol ID（协议标识）、primary estimand（主要估计量）、nuisance
bindings（干扰变量绑定）、结果 schema（模式）和 claim boundary（声明边界）。任何一项的
artifact（产物）不得通过重命名、复制字段或修改自洽哈希冒充另一项。

---

## 1. 共同状态与权力边界

### 1.1 初始状态

本版本四项都只能是：

```text
DEFINED_NOT_RUN
```

它表示“问题、对照、估计量和边界已定义”，不表示实现完成、实验运行、绑定冻结、Gate B
通过或论文结论成立。配置中的状态字段被 `Literal` 和严格 `extra=forbid` 合同锁定，直接把
状态改成 `PASSED`、`COMPLETE` 或其他字符串必须 fail closed（失败关闭）。

### 1.2 历史选择回执

协议包绑定既有用户选择：

```text
method_id = structure-two-nap-rbtpr-rc@0.1
content_sha256 = a3ccafd6612a6ee57a855e82572524622b6f15f305924b3de99bd3e94e17ed2f
```

不得原地改写既有选择回执来“消除 unresolved”。本模块不定义、签发或接受任何正式正向
`BindingResolutionReceipt`（绑定解析回执）。

### 1.3 一任务一绑定

允许的映射严格为：

```text
Task 11 -> resampling_policy
Task 12 -> rejuvenation_kernel
Task 13 -> differentiability_strategy
```

本地验证器可以从完整逐臂结果计算 `BindingCandidateDiagnostic`（绑定候选诊断），但该对象固定
声明：independent authority、custody、freshness、replay 均未验证，`formal_binding_resolved=false`
且 `seven_operator_ablation_authorized=false`。不同的 caller-supplied（调用者提供）execution ID /
producer ID 只是不同标签，不能证明独立重算；两份内容完全一致、自洽重哈希的结果同样不能生成
正式正向回执。

配置明确登记当前 trust anchor 为 `NOT_ENROLLED`、outer verifier handle schema 为
`UNAVAILABLE_NOT_IMPLEMENTED`，本地 verifier 不得打开正式解析。未来正式解析必须由本模块之外的
独立 authority 持有已注册 trust anchor 与原始证据，并检查签名域、custody、freshness window 和
跨提交 replay registry 后提供不可由调用方构造的 opaque verifier handle（不透明验证句柄）。在该
设施存在前，`derive_binding_resolution` 和 `verify_binding_resolution` 始终 fail closed。

---

## 2. Task 11：重采样策略

协议 ID：`structure-two-backbone-resampling-task-11@0.1`

### 2.1 科学问题

在粒子预算、proposal kernel（提议核）、回春、训练和推断语义不变时，哪一组 resampling
trigger + algorithm（重采样触发器与算法）能在相同 elementary evaluations（基本评估次数）
下改善动作与信念质量，同时不破坏 lineage（谱系）、开放世界未知项和未决质量？

### 2.2 对照臂

必须保留以下全部算法：

1. `no_resampling`；
2. `systematic`；
3. `stratified`；
4. `residual`；
5. `multinomial_negative_control`，仅作高方差负面对照。

ESS 阈值只允许在 validation（验证集）上从 `{0.25, 0.50, 0.75}` 中选择。最后一个时间步
禁止重采样，避免先抹平权重再报告虚假完美 ESS。

### 2.3 主要估计量

```text
paired_delta_action_loss_per_elementary_evaluation_with_exact_posterior_fidelity_guardrail
```

scenario seed 是 cluster unit（聚类统计单元）。主要动作指标不能抵消以下 fidelity
guardrails（忠实度护栏）：小状态 exact posterior TV、log-normalizer bias、owner
contamination、unknown/unresolved 支撑保持。

### 2.4 干扰变量绑定

| 干扰变量 | 冻结来源 |
|---|---|
| particle budget | `task_10_resolution_receipt` |
| proposal kernel | `frozen_backbone_proposal_held_constant` |
| rejuvenation kernel | `disabled_for_task_11` |
| differentiability / training | `not_applicable_inference_only` |

若 Task 10 尚无合格解析回执，Task 11 可以保持定义完成，但不得开始正式选择。

### 2.5 强制输出与正确性门

必须报告逐步 ESS、重采样时点、unique parents、unique root ancestors、unknown/unresolved
重采样前后质量、log-normalizer bias、posterior TV、action posterior distance、owner
contamination、基本评估次数和 wall time。

执行前必须通过：有限且归一化权重、玩具分布频率检验、父谱系记录、末步不重采样、未知项与
未决项报告、不同策略真实改变 runtime trace（运行轨迹）、approximate arm 无 oracle 调用。

“保留至少一个 unknown 粒子”不能作为无条件修补；若没有相应 importance correction（重要性
修正），它会改变目标分布。本协议默认只测量支撑流失。

### 2.6 声明边界

Task 11 本地最多提名一个 `resampling_policy` 诊断候选，不能正式解析该绑定。它不验证 Task 12、
Task 13、神经提议器、Gate B、七算子联合收益或论文级优越性。

---

## 3. Task 12：回春核

协议 ID：`structure-two-backbone-rejuvenation-task-12@0.1`

### 3.1 与 Task 7 的不可混淆边界

Task 7 只定义：

- 迟到纠正的 window（窗口）；
- checkpoint（检查点）复用；
- 窗口外变量不可修改；
- 不可达或数值失败时的 replay/full-rerun fallback（重放/完整重跑回退）。

Task 12 才能选择窗口内部的 Markov kernel（马尔可夫核）。因此
`task_7_window_semantics` 与 `full_suffix_rerun` 被显式登记为 non-kernel controls（非核参照），
不能作为 Task 12 的候选核或通过证据。

### 3.2 条件目标

对窗口 (W=[s,e))，固定窗口外状态 (x_{\neg W})，核必须保持：

\[
\pi_W(x_W\mid x_{\neg W},y_{1:T})
\propto p(x_{1:T},y_{1:T}).
\]

若使用 Metropolis–Hastings（MH），接受率必须包含完整 target ratio（目标比）以及 forward /
reverse proposal density（正向/反向提议密度）。修改窗口内状态后必须重建依赖的 regime
state machine（状态机）和 analytic sufficient-statistic blocks（解析充分统计块）；固定后缀不
可达时拒绝提议或进入已定义 fallback。

### 3.3 对照臂

1. `no_rejuvenation`；
2. `single_site_typed_metropolis_hastings`；
3. `blocked_typed_metropolis_hastings`；
4. `exact_conditional_gibbs_evaluator_only`，只允许 (G\le2) 的 evaluator oracle。

exact conditional Gibbs 不得被选为部署核，也不得进入 approximate arm。

### 3.4 主要估计量与干扰变量

主要估计量：

```text
conditional_window_kernel_effective_sample_size_per_elementary_evaluation_with_invariance_guardrail
```

固定 particle budget、Task 11 resampling receipt、backbone proposal、Task 7 窗口语义；训练与
可微策略在纯推断实验中不适用。

先检查 detailed balance / stationarity（细致平衡/平稳性）、正反密度、状态机可达性、窗口外
byte equality（字节级一致）、解析块重建和 oracle 隔离；之后才比较 acceptance、axis jump
distance、autocorrelation/ESS、unique ancestry、full-rerun actor marginal distance、recovery、
contamination、unresolved、fallback 原因和实际触碰索引。

### 3.5 声明边界

Task 12 本地最多提名一个 `rejuvenation_kernel` 诊断候选，不能正式解析该绑定。当前 Task 7 中
出现的任何 provisional MH（临时 MH）实现都只是候选，不能因“窗口式回春已经运行”而自动获得
Task 12 选择权。

---

## 4. Task 13：可微策略

协议 ID：`structure-two-backbone-differentiability-task-13@0.1`

### 4.1 唯一受控变量

Task 13 的 controlled variable（受控变量）只能是：

```text
gradient_estimator_only
```

以下内容是固定干扰变量，不是 Task 13 臂：particle budget、resampling policy、rejuvenation
kernel、proposal architecture、training schedule、optimizer、training compute budget。

特别地，`training_schedule` 与 `neural_proposer_architecture` 保持独立 unresolved binding；
Task 13 不得顺带解析它们。

### 4.2 对照臂

1. `stop_gradient_supervised_proposal`；
2. `score_function_unbiased_estimator`；
3. `relaxed_pathwise_resampling_biased`，必须始终保留 biased（有偏）标签。

### 4.3 主要估计量

```text
sealed_holdout_action_loss_delta_per_training_compute_with_gradient_validity_guardrail
```

先在 tiny exact task（微型精确任务）上做 finite-difference / exact-expectation gradient check；
再报告多 seed 的 gradient bias、variance、norm、nonfinite count、hard-constraint violation、
unknown/unresolved retention 和 inference-target hash equality。只有 correctness gates 全过后，
才解释 learning curve、holdout proposal recall、posterior TV 与 action loss。

训练时禁止改变部署推断目标、将 relaxed surrogate（松弛替代目标）冒充无偏结果，或赋予 neural
proposer 长期 commit authority（写入权限）。

### 4.4 声明边界

Task 13 本地最多提名一个 `differentiability_strategy` 诊断候选，不能正式解析该绑定。它不解析
训练计划或架构，不验证 Gate B，也不授权完整系统或论文级优越性声明。

---

## 5. `backbone.proposal.P5`：提议上界与召回分解

协议 ID：`structure-two-backbone-proposal-headroom-p5@0.1`

### 5.1 科学问题

固定 Tasks 10–12 的选择、structured weighting（结构化加权）和 action readout（动作读出）
后，完整提议器是否仍有可实现上界收益？真值兼容支撑在哪一层丢失？

P5 不训练模型；differentiability 与 training schedule 均为 `not_applicable_diagnostic_only`。

### 5.2 对照臂

1. bootstrap proposal；
2. 当前 deterministic/adaptive typed proposal；
3. locally optimal conditional-posterior oracle，仅 evaluator；
4. truth-inclusion Top-K oracle，仅 evaluator 诊断。

所有 truth read（真值读取）和 exact enumeration（精确枚举）都必须计数。oracle 输出不得进入
部署方法、参数选择、Gate B 或长期账本。

### 5.3 逐层召回分解

每个臂必须报告完整链 truth-compatible recall 在以下全部阶段的值：

```text
raw candidate generation
  -> hard constraint survival
  -> weighted support
  -> resampling survival
  -> final chain support
```

同时报告 (H/R/I/C/Z) 五轴召回、`branch / revise / retract / reactivate / rejuvenate /
preserve_unresolved` 六类操作召回、posterior mass coverage、unknown/unresolved retention、动作
后果和计算成本。

主要估计量：

```text
oracle_minus_deployable_full_chain_truth_compatible_recall_decomposed_by_pipeline_stage
```

### 5.4 互斥诊断，不设 pass

P5 必须按注册顺序提交四臂完整矩阵；每一臂都独立报告五阶段 recall、五轴 recall、六类操作
recall、动作损失、评估次数和 oracle/truth-read 账本。验证器从矩阵重新计算每阶段
`best_oracle_recall - best_deployable_recall`、最终 headroom 和 oracle action gain，再按照冻结顺序
给出且只给出一个枚举诊断：

- `NO_PROPOSAL_HEADROOM`；
- `PROPOSAL_BOTTLENECK`；
- `DOWNSTREAM_WEIGHTING_OR_RESAMPLING_BOTTLENECK`；
- `MIXED_PROPOSAL_AND_DOWNSTREAM_BOTTLENECK`；
- `READOUT_INCONCLUSIVE`。

其中 raw candidate 阶段的 oracle/deployable 差定义 proposal bottleneck（提议瓶颈）；后续每一阶段
分别重算 deployable recall loss 与 oracle recall loss，其正差定义 downstream bottleneck（下游瓶颈）。
两者同时超过预注册 `0.01` 时必须报告 `MIXED_PROPOSAL_AND_DOWNSTREAM_BOTTLENECK`，不得用笼统的
“proposal failed”吞掉混合成因。

P5 result schema 没有 `passed` 字段；`passed`、`binding_resolution`、
`paper_claim_authorization`、`architecture_selection` 都是禁止输出。额外注入这些字段必须被
严格 schema 拒绝。

### 5.5 声明边界

P5 只回答“是否存在 headroom，以及瓶颈在哪”。它不能解析任何方法绑定、选择神经架构、验证
Gate B 或七算子收益，也不能授权部署或论文声明。

---

## 6. 结果 schema 与运行时绑定回执

代码分别定义：

- `Task11RunResult`；
- `Task12RunResult`；
- `Task13RunResult`；
- `TaskP5DiagnosticResult`。

前三类结果使用：

```text
RAN_INELIGIBLE
RAN_ELIGIBLE_NO_SELECTION
RAN_ELIGIBLE_SELECTION
```

只有最后一种状态、完整注册臂都存在、正确性门通过且冻结选择规则复算出唯一值时，本地才可输出
`BindingCandidateDiagnostic`。result disposition（结果状态）与 typed candidate（类型化候选）
必须由逐臂证据共同推导；Task 12 evaluator oracle 即使结果好也禁止成为部署候选。caller pair 的
决定性投影必须一致且所声明 execution/producer 标签必须不同，但这仅是结构诊断，不构成独立性、
custody 或 freshness 证明，也不能输出正式 binding receipt。

每个 Tasks 11–13 和 P5 结果都必须携带 `RuntimeBindingReceipt`。它逐项记录 configured value
（配置值）、observed runtime value（实际运行值）和 trace-payload hash，并绑定 task、protocol、
execution、producer、spec、完整配置及可信 source bundle。仅有同名键不够；值漂移、缺项、跨任务
回执或 spec/config/source drift 均拒绝。配置 loader 也拒绝任意层级重复 JSON key，防止键遮蔽。

P5 使用单独的 `TaskP5DiagnosticResult`：四个臂必须各自一次性覆盖五个 pipeline stage、五个
粒子轴和六个 proposal operation；headroom、action gain 和 diagnosis 均由验证器复算，且 schema
没有 `passed`。

---

## 7. 正式执行前的两轮对抗自查

### 第一轮：合同、状态与越权攻击

必须至少尝试：

1. 把任一 `DEFINED_NOT_RUN` 改成 `PASSED`；
2. 用另一任务的 estimand 替换当前 estimand；
3. 删除一个对照臂、metric 或 correctness gate；
4. 把 Task 7 window kernel 塞入 Task 12 candidates；
5. 将 exact conditional oracle 选为部署 kernel；
6. 让 Task 13 同时改变 training schedule / architecture；
7. 从 Task 11 解析 Task 12 binding，或从 P5 解析任一 binding；
8. 给 P5 注入 `passed=true` 或 architecture selection。

所有攻击必须 fail closed。

### 第二轮：运行时、证据链与科学归因攻击

正式 runner 接入后必须至少尝试：

1. 配置参数存在但实现未消费，runtime trace 不变；
2. approximate arm 偷调 exact enumerator 或 evaluator truth；
3. 重采样强保留低质量 unknown particle，却无 importance correction；
4. MH 正反 proposal density 不对称或回春后错误抹平权重；
5. 修改窗口内状态后复制旧 timeline/analytic block，制造不可达后缀；
6. 用 validation/test 相同 seed 调参并报告虚假泛化；
7. 同时重写 result、trust map 和自洽 hash，构造 forged-but-complete artifact；
8. 用字符串或数值型 consequential output 绕过只追踪 `True` 的 verifier；
9. 用 (G\le2) oracle 结果冒充 (G\ge3) scalability；
10. 将“定义完成”或“诊断有 headroom”提升为 Gate B、七算子或论文声明。

本次协议层测试已覆盖第一轮攻击，以及第二轮中的 forged-complete 回执、跨臂/缺臂、运行时值与
spec/config/source 漂移、P5 伪造诊断和 oracle 泄漏。新增的最小复现明确证明：攻击者提交两份
内容相同、仅 execution/producer 标签不同的完整结果时，本地最多得到全部 authority 字段为 false
的诊断；`derive_binding_resolution` 必须拒绝，调用者自造且自洽重哈希的诊断也不能被提升为解析
回执。它们只证明协议验证器会 fail closed，不是 Tasks 11–13/P5 的实验运行；其余依赖真实 runner、
数据和外部证据保管的第二轮攻击必须在执行后再次进行。四项状态因此仍是
`DEFINED_NOT_RUN`，P5 仍不产生 pass，七算子消融仍未授权。
