# 结构二端到端有效性前置门结果与历史解释修正

日期：2026-09-09；主张边界终审与最终工程回执：2026-09-10

证据等级：`D0_LOCAL_DEVELOPMENT_AND_AUDIT_ONLY`

当前授权：`action_utility_construct_gate_passed=true`；
`historical_route_c_runtime_identity_gate_passed=false`；
`task_8_formal_passed=false`；
`adaptive_readiness=PROTOCOL_IMPLEMENTED_EXECUTION_BLOCKED`；四项完整 adaptive 工程门均为 `false`；
最终机器工件已对 source manifest
`ebf05dad4785182c139a552658344acd9a3b812e3437f32aabfa5dcbe84ac9ff` 重建并鲜验证

## 1. 结论先行

这次工作把原先混在一起的两个问题拆成了两个独立、可失败关闭的前置门：

1. action/utility construct gate（动作/效用构念门）检查 SEARCH（搜索）和 PUT_BACK（放回）是否具有
   不同的类型、目标语义、环境副作用和评价指标；该门在一个 3-step D0 正路径诊断上通过。
2. runtime identity gate（运行时身份门）检查轨迹是否能绑定到实际运行时、具体算子实例、调用和下游
   消费；该门对历史 Route C v0.2 明确失败。

因此，当前可以说“类型化任务动作和分离指标的最小构念正路径已建立”，不能说“生产级完整闭环已
建立”。这两项仍是分立诊断，尚未形成一条集成的 end-to-end falsifier（端到端证伪链）。通过第一个门不会抵消第二个门的失败，也不会授权 combined utility（组合效用）、长期人物
记忆污染、Task 8 正式通过或科学优越性。

Architecture A 的 adaptive lane 已有 transitively read-only plan/consumption registries（传递只读计划/
依赖注册表）与部分 kernels、
P0 debt、异位置 detected full CIAV closure、同位置 fast verification 和 executed-operator elapsed
receipts，并修复两个公开入口的
caller context snapshot 与 pending-debt core-transition barrier；negative-observation full closure 和全
wrapper mutation barrier 未成立。终审确认这仍不足以建立 state-derived path eligibility、完整
legal-path executor、P0–P5 consequential runtime identity 或 full resource accounting；当前共有 12 个
readiness blockers。

## 2. 为什么必须重新解释历史 v0.2

历史工件：
`benchmarks/structure_two/structure_two_full_scientific_loop_v0_2.json`

对主 joint 与 matched full-state factorized 两臂的原始 traces 重新计数得到：

| 项目 | 每臂 | 两臂合计 | 当前解释 |
|---|---:|---:|---|
| 步数 | 27 | 54 | 3 seeds × 9 steps × 2 arms |
| 选择动作等于动作前物体当前位置 | 27 | 54 | 所有动作均以当前位置为目标 |
| `action_success=true` | 22 | 44 | 成功随机量通过，不等于发生状态改变 |
| 实际位置改变 | 0 | 0 | 没有观察到 nonnoop embodied transition |
| search regret 非零 | 0 | 0 | 旧单分布始终把当前位置排第一 |
| put-back error | 15 | 30 | 同一地点选择又被拿来评价主人习惯位置 |
| 旧 contamination event | 9 | 18 | 只是一项地点/人物不匹配代理 |

v0.2 从一个地点分布取 top-1 UUID，然后同时把它用于：

- SEARCH 排序；
- PUT_BACK 目标；
- 环境 relocation（搬移）命令；
- put-back regret；
- contamination 计数。

这使“找物体现在在哪里”和“把物体放回主人习惯位置”两个不同任务被合并成同一个动作。旧
`owner contamination=0.333333` 更准确的名字是
`non_owner/current_location/owner_habit_mismatch proxy`；它不是 RGRC 长期账本污染的直接测量。

历史 joint/factorized 对照的注册机制差异也仅为 learned cross-axis log-potential（学习式跨轴对数势）
与零系数。27/27 个配对步骤虽出现非零 action-posterior TV，最终动作有 0 次不同。这个对照只检验
特定六特征交互势，不能外推为一般 joint architecture（联合架构）相对一般 factorized architecture
（因式分解架构）的结论。

## 3. 动作/效用构念门

- 协议：`structure-two-action-utility-construct-gate@0.1-development`
- 配置：`configs/project_two_experiments/structure_two_action_utility_construct_gate_v0_1.json`
- 工件：`benchmarks/structure_two/structure_two_action_utility_construct_gate_v0_1.json`
- 状态：`D0_CONSTRUCT_VALIDITY_DIAGNOSTIC_NOT_PAPER_EVIDENCE`

### 3.1 合同

- SEARCH 和 PUT_BACK 都是 typed action（类型化动作），带 `target_object_id`、`location_id`、
  `decision_id` 和 `information_set_sha256`。
- 读出另绑定 `run_execution_id`、`source_update_id`、step 和 visible observation commitment
  （可见观测承诺）；SEARCH 与 PUT_BACK 的 decision ID 分别由这一规范信息集派生。
- 两个 head 从同一个 predecision information set（决策前信息集）提交，真值在两种动作提交及后果
  产生后才释放给评价器。
- 环境实例只对当前 observation 签发一次 runtime-local capability（运行时局部能力）；
  提交后立即销毁。它能拒绝跨 step、跨环境、跨 control 和复制读出重放，但不序列化进
  工件，不是 independent custody（独立托管）证明。
- SEARCH 只检查按序位置，不移动物体，也不推进环境世界步。
- PUT_BACK 是唯一可改变物体位置的动作；执行成功与是否达到主人习惯目标分别记录。
- search regret、put-back error 和 narrow non-owner-copy proxy 分开复算；没有默认加权总分。

### 3.2 主正路径

3-step、seed 853 的确定性诊断得到：

| 检查 | 结果 |
|---|---:|
| 三步均使用类型化、信息集绑定动作 | 通过 |
| SEARCH 与 PUT_BACK 选择不同的步骤数 | 1 |
| successful nonnoop PUT_BACK state change | 1 |
| SEARCH 改变物体状态 | 0 |
| combined utility | `UNRESOLVED_NOT_AGGREGATED` |

这关闭了旧 v0.2 从未覆盖的最低正路径：至少有一次实际放回命令与当前位置不同、执行成功且环境状态
发生改变。

### 3.3 单头敏感性对照

| 对照 | 基线 | 干预 | 未被干预侧 |
|---|---:|---:|---|
| SEARCH-only ranking intervention | search regret `0` | `0.5` | PUT_BACK 读出、转移和指标不变 |
| PUT_BACK-only ranking intervention | put-back error `0` | `1` | SEARCH 读出、执行和指标不变 |

PUT_BACK-only 错误动作仍有 `execution_success=true`，但 `goal_satisfied=false`。这证明 actuator success
（执行器成功）和 task utility（任务效用）已被分离，不会再因“命令执行成功”自动记成“放回任务正确”。

这些 sensitivity controls 只证明指标接线能响应单头变化；它们不证明学习策略非退化、任务质量或
科学收益。

## 4. 运行时身份门

- 协议：`structure-two-runtime-identity-gate@0.1`
- 配置：`configs/project_two_experiments/structure_two_runtime_identity_gate_v0_1.json`
- 工件：`benchmarks/structure_two/structure_two_runtime_identity_gate_v0_1.json`
- 状态：`MISSING_LIVE_RUNTIME_OPERATOR_CALL_CONSUMPTION_BINDING`

审计结果：

| 检查 | 结果 |
|---|---|
| 轨迹运行时 | `cpswm.system.evaluation_operations.structure_two_full_scientific_loop.LearnedInteractionRuntime` |
| 注册 Route C runs | 27 |
| 审计 operator receipts | 1,998 |
| `StructureTwoProductionSystem` 角色 | `POST_RUN_STATIC_SIDECAR_NOT_TRAJECTORY_RUNTIME_EVIDENCE` |
| sidecar 是否在全部 Route C runs 后构造 | 是 |
| sidecar 是否绑定轨迹运行时 | 否 |
| production runtime equivalence | false |
| runtime identity gate | false |
| 全局架构选择 | `A_SELECTED_STRUCTURE_TWO_PRODUCTION_SYSTEM` |

历史 Route-C 仍有六个阻断原因：

1. 轨迹没有 `runtime_execution_id`；
2. 回执没有 live `operator_instance_id`；
3. 回执没有绑定的 `callable_symbol` / `invocation_id`；
4. 算子输出没有 `consumed_output_ids` 形成下游消费依赖；
5. production manifest 来自另一个在运行后才构造的 runtime object；
6. Architecture A 落地后，历史 manifest 与当前源码不再 fresh（新鲜一致），旧工件未被重写。

旧工件的源码路径、SHA-256、前向边和自哈希可以证明 static inventory（静态清单）的内部一致性，
不能证明哪个对象实际产生了轨迹。当前纯结构 candidate verifier 也不能自行把 caller-controlled
（调用者控制）证据升级为 live execution authority（现场执行权威）或 independent custody（独立托管）。

## 5. 门状态总表

| 结论 | 当前值 | 允许的解释 |
|---|---|---|
| typed SEARCH/PUT_BACK construct | `true` | 3-step D0 最小正路径通过 |
| actual nonnoop state change | `1` | 仅新构念诊断内成立 |
| metric single-head sensitivity | `true` | 接线响应通过，不是策略收益 |
| combined utility | `UNRESOLVED_NOT_AGGREGATED` | 没有选择权重或长期产品决策语义 |
| long-term product action semantics selected | `false` | 留给项目所有者决定 |
| long-term memory contamination established | `false` | 当前只有 narrow proxy |
| historical Route-C runtime identity | `false` | 历史轨迹缺少实例—调用—消费链 |
| legacy ordinary Architecture-A binding | `true` | 六个真实调用回执 + CIAV N/A；不是 P0–P5 |
| state-derived path eligibility | `false` | router features 仍由调用方提交；production-state feature extractor 尚缺 |
| full legal-path executor | `false` | 只有 plan registry/partial kernels；P1/P2/P4 独立实质内核与真实 fallback 尚缺 |
| P0–P5 consequential runtime identity | `false`（2026-09-10 终审收紧） | 局部 P0 debt、异位置检测完整 closure、同位置快速验证和回执不能代表所有路径的完整后果身份链 |
| full resource accounting | `false` | 已有 operator elapsed receipts，但 feature extraction、fallback、全部路径和全部资源维度未覆盖 |
| global runtime architecture selected | `true` | Architecture A；不追溯提升旧 Route-C |
| transitively read-only plan/consumption registries / partial kernels | `true`（局部工程边界） | 只证明注册表不可原位篡改及已接入局部路径，不得升级为 full executor |
| trace sink contract source-bound | `true` | 与 plan contract、旧入口兼容性独立检查 |
| legacy no-plan/no-trace call shape | `true` | AST 保守核验旧无参数分支仍直达原调用链；该门本身不证明行为等价 |
| cross-system trace/state atomicity | `false` | 类型化确认与补偿中止不等于跨存储持久事务 |
| independent custody | `false` | 本地开发工件 |
| Task 8 formal pass | `false` | 不签发正式回执 |
| scientific superiority | `false` | 不支持论文优越性结论 |

## 6. 与完整范围和历史档案的关系

本轮没有删除或降级 OPCEU、ORRER/CHEH、PCHMP、CF-BOCPD、CCRR、RGRC、CIAV 中的任何一个，
也没有移除隐藏事件推断、多人责任、开放世界未知、可逆归因、主动验证或具身反馈。新构念门是为完整
系统增加一个 fail-closed validity check（失败关闭有效性检查），不是把结构二缩成搜索/放回两项。

Task 7 的用户决定同样保持不变：下一版继续联合 correction-ready ancestry reservoir（面向纠正的
谱系储备）与 backward-message checkpoint（后向消息检查点），并保留 reservoir-only、
backward-message-only、combined、full-rerun reference 和旧失败实现五臂。reservoir-only 的 D0
partial signal 不自动授权切换路线。

所有 2026-09-08 及更早的 dated experiment/review 文档保持原样，继续作为当时的历史快照。本文件
只修正它们在当前 canonical docs 中的解释，不回写旧源码、配置、工件或历史结论。

## 7. Architecture A 之后的下一步

项目所有者已选择 Architecture A：真实 `StructureTwoProductionSystem/CorePrototypeSpine` 接受不可变
`execution_plan + trace_sink`，无参数调用保留旧兼容语义。接口选择本身不使旧 Route-C 成为生产轨迹，
也不使历史 Route-C 的 `runtime_identity_gate_passed` 变为 true；该失败仍是 non-blocking historical
diagnostic（非阻塞历史诊断），不是 Architecture A 的额外 blocker。

对 adaptive lane，目前可以确认的边界仅是：传递只读 plan/consumption registries 与 partial path
kernels、P0 debt、
异位置 detected full CIAV closure、同位置 fast verification、executed-operator elapsed receipts。
caller-provided execution context 已在两个
公开 adaptive 入口复制为 runtime-owned snapshot，避免回调改写提交状态；pending debt 也会阻断 legacy、
traced legacy、direct-core transition 和装饰过的 public core mutator。negative observation 仍没有完整
下游闭包，policy/evidence-trace wrapper rebinding 在债务期间仍允许，replay 也不绑定 origin
policy/trace。这些局部修复不会自动关闭四个
完整工程门。

终审确认：router features 仍由调用方提供，没有 state-derived feature extractor；P1/P2/P4 没有各自
独立的实质内核；failure/timeout fallback 只有注册目标，没有完整执行；耗时回执也没有覆盖特征提取、
fallback、全部路径及全部资源维度。因此：

- `path_eligibility_policy_bound_to_production_state=false`；
- `legal_path_executor_bound_to_production_runtime=false`；
- `p0_p5_consequential_runtime_identity_established=false`；
- `resource_accountant_bound_to_production_execution=false`。

连同原有未决项，当前正好有 12 个 readiness blockers：

1. state-derived path eligibility；
2. full legal-path executor；
3. P0–P5 consequential runtime identity；
4. full resource accounting；
5. durable cross-system trace/state atomicity；
6. path-specific operator budgets；
7. frozen exhaustive branch-point manifest；
8. debt replay versus eager-reference recovery equivalence；
9. empirical power/household ICC binding；
10. independent confirmatory custody；
11. exogenous production RNG binding；
12. long-horizon task-memory-recovery loss bound to actual action consequences。

下一版首先需要实现 production-state feature extractor、P1/P2/P4 独立实质内核和真实 fallback，随后
才可重新审核 full executor、P0–P5 identity 与 resource accounting。之后还需关闭路径预算、分支点
清单、恢复等价、跨系统原子性、功效、独立托管、外生 RNG 和长期动作后果。typed SEARCH/PUT_BACK
与真实 nonnoop transitions 上的强基线重跑只能在这些工程边界明确后产生开发或更高等级证据；
combined utility、长期动作语义和污染定义仍是显式决策点，不由实现默认值替代用户选择。

## 8. 复现入口

```bash
.venv/bin/python apps/evaluation_runner/run_structure_two_action_utility_construct_gate.py

.venv/bin/python apps/evaluation_runner/run_structure_two_action_utility_construct_gate.py \
  --verify benchmarks/structure_two/structure_two_action_utility_construct_gate_v0_1.json

.venv/bin/python apps/evaluation_runner/run_structure_two_runtime_identity_gate.py \
  --output benchmarks/structure_two/structure_two_runtime_identity_gate_v0_1.json

.venv/bin/python apps/evaluation_runner/run_structure_two_runtime_identity_gate.py \
  --verify benchmarks/structure_two/structure_two_runtime_identity_gate_v0_1.json

.venv/bin/python apps/evaluation_runner/run_structure_two_adaptive_compute_predeath.py \
  --verify benchmarks/structure_two/structure_two_adaptive_compute_predeath_readiness_v0_1.json
```

三个 verifier 都会重新检查当前仓库源码与工件绑定；action verifier 还会 fresh
recompute（鲜重算）完整 3-step 路径，因而重新经过不序列化的单次能力检查。这能拒绝只改
JSON 后重算自哈希的伪造，但仍不等于独立托管、外部不可变时间戳或生产现场执行证明。

终审收紧了 adaptive readiness；runtime/adaptive 工件及其级联 source bindings 已在最终快照重建。
action、runtime、adaptive verifier 及 checkpoint 的 fresh/no-fresh verification 均已通过；较早工件
哈希和测试计数仍不得作为本轮回执。

历史 v0.2 验证器会把旧工件的 source binding（源码绑定）和 sidecar manifest
（旁挂清单）与当前 checkout 重算结果比较，所以本次 runtime audit 是 commit-scoped
snapshot（提交范围快照），不是可跨未来源码改动永久 fresh verify 的证据。后续实现全局
runtime 时应新建 v0.3 及其 gate，或回到冻结 commit 验证这份 v0.2；不得为追当前源码而改写历史
v0.2 工件。

## 9. 最终工程验收

终审改变了 adaptive gate 的事实边界，因此较早工程验收数字与哈希全部撤出当前结论。最终快照已在
源码、配置、测试与测试夹具停止变化后重新执行：

- action/runtime/adaptive 工件均 fresh verify；adaptive readiness content SHA 为
  `f1356ad5aa2ac427c4d9168acd79dc43084e8246be264eb423f9521ff077a54b`；
- Architecture-A、自适应运行时、manifest 与 world-audit 定向合并回归：229 passed；checkpoint 独立
  回归：13 passed；第一轮/第二轮 adaptive adversarial 分别 8/12 passed；
- P0 7-scope content manifest SHA：
  `ebf05dad4785182c139a552658344acd9a3b812e3437f32aabfa5dcbe84ac9ff`；其中
  `test_fixture_contract` 单独绑定 78 个 benchmark JSON fixtures；
- current world source inventory：301 files，source-bundle SHA
  `8a48b902c070ea7d1cb1f49ca880f6cb40e40ce282451e7cf0fbbb3686f2c7d7`；与历史冻结 v0.5
  `current_worktree_compatible_with_frozen_v0_5=false`；
- core pytest：3,789 passed、1 skipped、1 xfailed；P0 adversarial matrix：118 passed；mypy、Ruff
  lint/format、compileall、frozen/offline dependency check 与 `git diff --check` 均为 exit 0；
- engineering audit receipt content SHA：
  `1dc800c0a2271beda1cd0e6d69bf12a5dd48937ce8aca1b5c47ac72137b3d0f7`，8/8 命令通过；
- engineering trust checkpoint content SHA：
  `c0da629d5f6da45890409afee3808cd8b7ca11370e784ef8fedc42192f7408d6`，生成与 no-fresh verify 均通过；
  生成过程本身完成 fresh task recomputation。

已经由终审确认并可保留为代码级修复事实的是传递只读 plan/consumption registry、两个 adaptive
公开入口的 caller context/selection snapshot 与 pending-debt core-transition barrier；这些局部事实
不能消除当前 12 个 readiness blockers。negative-observation full closure、全 wrapper debt barrier 和
origin-policy/trace-bound replay 仍未成立。
历史 v0.2 full-loop implementation、runner、配置和工件仍不被改写或重签。

未来即使重新得到 `engineering_trust_gate_passed=true`，其含义也只能是 source-bound、current-local
recorded audit（源码绑定的当前本地记录审计）在该快照内部一致。它不建立
`recorded_execution_authenticity_established`、hermetic toolchain（密闭工具链）、independent custody、
historical authenticity、external/scientific validity 或 seven-operator efficacy；这些边界必须继续为
false 或 unresolved，不能由本地自哈希回执提升。

## 10. 当前安全结论

> 结构二完整七算子范围未缩减；一个 3-step D0 typed SEARCH/PUT_BACK 构念门已经证明任务动作、环境
> 副作用和分离指标存在最小可执行正路径。历史 Route C v0.2 的轨迹仍来自 evaluator-local
> `LearnedInteractionRuntime`，生产系统只是运行后静态 sidecar，历史运行时身份门失败，但该历史
> 诊断不额外阻断 Architecture A。A 当前只建立传递只读 plan/consumption registry、partial kernels、
> P0 debt、异位置检测完整 CIAV closure、同位置快速验证、隔离 replay 入口和已执行算子 elapsed
> receipts；四项完整 adaptive 工程门为 false，仍有 12 个 readiness blockers。组合效用、长期人物
> 记忆污染、Task 8 正式通过、外部有效性和科学优越性均未建立；最终本地工程快照通过不改变这些结论。
