# 结构二：冻结方法主干与七算子生产路径一致性审计（窗口三）

日期：2026-09-11
共同起点：`09eb4d48e1c11082e90ca18332d04333e6b5b47a`
分支：`codex/s2-backbone-operators-w3`
协议标识：`structure-two-backbone-wiring-probe@0.1`
状态：**PARTIAL_AUDIT — D0 机制级接线审计，非科学门**

## 0. 审计边界（先读这一节）

本报告只做四件事：

1. 把冻结方法条目逐项映射到**实际被调用的**状态对象、运行时、更新者和下游消费者；
2. 建立并运行**机制级**场景矩阵，区分“真实消费”与“trace 声明”；
3. 对有明确冻结合同依据的局部接线缺陷，先写失败测试再作最小修复；
4. 登记真实缺口与后续接入顺序。

本报告**不**建立、也不得被引用为：Task 9 四耦合结果、七算子贡献消融、路由收益、
recovery equivalence、外部效度、`TrustedSevenOperatorAblationAuthorization` 或任何科学门通过。
所有正向判定只在本报告第 4 节列出的场景与种子下成立；矩阵未覆盖的部分一律标为 `not_covered`，
因此本审计整体是**部分审计**。

本窗口未启动 Task 9 消融，未启动路由器训练，未改写历史 benchmark、科学阈值、全局 manifest
或工程 checkpoint，未缩小 H/R/I/C/Z/r/V 七轴、三个 Rao–Blackwellized 统计块、可逆 RGRC 账本、
七算子、隐藏事件、多人、开放世界未知、可逆归因与具身反馈中的任何一项。

## 1. 执行环境与偏差登记（影响所有运行证据的可信度）

审计在云端 Linux 容器内执行，**不是**仓库 CI 所固定的 Python 3.13 环境。必须随证据一并阅读的偏差：

| 项 | 仓库固定 | 本次执行 | 影响 |
|---|---|---|---|
| Python | 3.13（CI pin，`pyproject` `requires-python>=3.11`、`target-version=py313`） | 3.11.15 | 仓库中 17 处 PEP 695 语法（4 处 `type` 别名、9 处泛型 `def`、4 处泛型 `class`）需在**编译前**做只读源码降级才能解析 |
| PEP 695 降级 | 不适用 | 测试夹具级 import hook，**不修改仓库任何文件**，逐行保持行号不变；覆盖 `SourceFileLoader.source_to_code`、`ast.parse`、`builtins.compile`（`bind_runtime_callable` 的源码一致性校验也走 `compile`） | 所有运行结果都是在语法降级解释器上取得的 |
| numpy | `>=2.4.6` | 2.4.4 | 低于下界 |
| scikit-learn | `>=1.9.0` | 1.8.0 | 低于下界 |
| matplotlib | `>=3.11.1` | 3.10.9 | 低于下界 |
| cryptography | `>=46,<48` | 46.0.7（仓库 venv 为 47.0.0） | **4 个既有测试在起点提交即失败**（见下） |
| hypothesis | `>=6.165.10` | 不可用（`hypothesis._native` 为 darwin 二进制） | `tests/test_oam_phm_invariants_property.py` 未执行 |

起点提交（未做任何修改时）的环境性失败，**与本窗口的改动无关**，且在 CI 的 cryptography 47 下不复现：

```
tests/test_structure_two_execution_interface.py::test_sink_cannot_replace_registered_pchmp_delegate_and_rollback_preserves_identity
tests/test_structure_two_execution_interface.py::test_sink_cannot_mutate_registered_pchmp_delegate_authority_in_place
tests/test_structure_two_execution_interface.py::test_sink_cannot_swap_an_in_place_attestation_verifier_key[core]
tests/test_structure_two_execution_interface.py::test_sink_cannot_swap_an_in_place_attestation_verifier_key[wrapper]
```

根因已定位：`cryptography 46.0.7` 的 `Ed25519PublicKey` 不支持 `deepcopy`（47.0.0 支持），
而 `_capture_execution_wrapper_state` 对组件字段做 `deepcopy`。这是环境缺陷，不是代码缺陷。

**因此：本报告所有 `pass` 判定在 Python 3.13 + 锁定依赖上必须重跑确认。** 第 9 节给出复现命令。

## 2. 主干接线表

列含义：方法要求 → 实际状态对象 → 所属运行时 → 更新者 → 下游消费者 → 动作/长期状态后果 → 测试证据。
“更新者”一律写实际执行写入的代码位置，不写类名。

### 2.1 七轴状态 H/R/I/C/Z/r/V

| 轴 | 实际状态对象 | 所属运行时 | 更新者（真实写入点） | 下游消费者（真实读取点） | 动作/长期后果 | 测试证据 |
|---|---|---|---|---|---|---|
| `H` 事件链 | `EventHypothesisHistory`（`receipted_history`） | `CorePrototypeSpine._event_engine`（生产） | `prototype_spine.py:2179` `self._event_engine.branch(...)` | `prototype_spine.py:2202` `self._message_passing.consume(history, evidence)`；`receipted_history.latest.revision_id` → `_CommittedPrototypeEvent` | 决定 `event_revision_id`，进而决定 fast 账本与 CIAV 的 `update_id` | `test_positive_observation_..._thirteen_call_closure` |
| `R` 有序角色 | `history` 内的 role/mechanism 假设 | 同上（`allow_unknown_handoff_roles=True`） | 同 `H` | PCHMP 势函数 | 间接（经 `actor_posterior`） | 场景矩阵 S5/S6（开放角色支持保持） |
| `I` 实例关联 | `identity_switch_probability` | **分裂**：CIAV 侧 `AdaptiveCIAVRuntimeInput.identity_switch_probability`；CCRR 侧 `AutomaticCFBOCPDCCRRRouter.observe(identity_switch_probability=…)` | CIAV 侧由调用方提供；**CCRR 侧生产路径从不传值，恒为默认 `0.0`** | CIAV `StructureTwoCauseBelief.from_snapshot` 使用；CCRR `decide()` 使用 | CCRR 的阶段判定**不受 I 轴影响** | 缺口 **G4**，见第 6 节 |
| `C` 变化原因 | `JointCauseSnapshot`（`assessment.snapshot`，也是 `core._last_cause_snapshot`） | `router.bocpd`（`JointCauseFactorizedBOCPD`） | `project_one_regime_loop.py:208` `self.bocpd.observe_online(frame)` | CCRR `decide(snapshot=candidate.snapshot,…)`；CIAV `_execute_ciav_operator` 读 `core.current_cause_snapshot` | 经 CCRR 结论决定 quarantine/promote/reject | S1/S7；trace 中 `cf_bocpd → ccrr → ciav` 边 |
| `Z` 阶段目的地 | `RegimeDecision.kind`（`stay/create/reactivate`） | `router.ccrr`（`ContextConditionedRegimeReactivator`） | `project_one_regime_loop.py` `self.ccrr.decide(...)` | `prototype_spine.py` `assessment.new_regime` → `switch_regime` → `rls_sample.regime_id` | 决定 RLS regime 与长期写入授权 | **S7：实测 `create`(d4) → `create`(d18) → `reactivate`(d27)，且 reactivate 返回的是更早出现过的 regime id** |
| `r` 阶段 run length | `JointCauseFactorizedBOCPD` 内部 run-length 后验 | `router.bocpd` | `observe_online` | `segment_change_probability` / `transient_noise_probability` | 同 `C` | S7（间接） |
| `V` 修订谱系 | `revision_id / parent_revision_id`、`hybrid_revision_id / hybrid_parent_revision_id`、账本 `_by_revision` | `core._hybrid_loop.ledger` | `_ingest_event_hybrid` / `retract_revision` | `live_promoted_records_for_revision`、`action_location_distribution` | 撤回后动作分布改变，且无残留贡献 | **S8：retract 后 `live_promoted_records == ()`、`verify_hybrid_full_rerun_equivalence().equivalent is True`、重复 retract 幂等** |

### 2.2 三个 Rao–Blackwellized 统计块

| 块 | 实际对象 | 更新者 | 下游 | 证据边界 |
|---|---|---|---|---|
| `α`（Dirichlet） | `HierarchicalDirichletHabitModel` | `_commit_event` → `_habit.update_audited`；被阻断时 `weight_multiplier=0.0` | `habit_prediction` → `suggested_location_id` | 生产自适应车道上**几乎不可达**，见缺口 **G1** |
| `A,b`（RLS） | `RLSRegimeBank._heads[regime]` | `_commit_event` 内的 `rls_sample` 摄入 | `score_candidates` | 同上 |
| `Λ,ξ`（Hybrid） | `HybridStatisticLedger` | `_ingest_event_hybrid` | `hybrid_alpha` / `action_location_distribution` | 同上；撤回语义已验证（S8） |

> 说明：本审计只验证这三块**是否被真实写入与读取**，不对 Rao–Blackwellization 的统计收益作任何判断
> （该判断在 `方向结构二_神经摊销类型化粒子修订与可逆巩固方法冻结_v1.0.md` §9 已被撤回，本报告不恢复）。

### 2.3 `StructureTwoProductionSystem` / `CorePrototypeSpine` / evaluator-local 粒子实现的关系

这是本次审计最需要写清楚的一条：

* `StructureTwoProductionSystem` **不是**第二套模型。它持有唯一 `core: CorePrototypeSpine`，
  并通过 `__getattr__` 把未知属性透传给 `core`（`structure_two_production_system.py:1896`）。
  七算子中 opceu/orrer_cheh/pchmp/cf_bocpd/ccrr/rgrc 的真实执行体全部在 `core._process_transition`
  内；production system 只增加了 **路由、债务账本、CIAV 编排、反馈闭包与回滚包装**。
* `CorePrototypeSpine._execution_callable_bindings`（`prototype_spine.py:1644`）对
  production system 提供的算子实例做**对象身份（`is`）核验**，这是“同一生产运行时”这一类证据的真正来源，
  不是类名匹配。
* **evaluator-local 粒子实现（`structure_two_particle_falsifier.py`、`structure_two_backbone_falsifier.py`、
  `structure_two_stateful_full_joint.py`）与上面两者没有任何调用关系。** 生产 P0–P5 路径不构造、
  不调用、不读取它们的任何状态。它们是独立的证伪器仪器。
  因此“类型化粒子修订（TypedParticleState / 粒子预算 / 重采样 / 回春）”**目前不在生产主干上**：
  生产主干的后验表示是 `event_posterior + actor_posterior + JointCauseSnapshot + RegimeDecision`，
  不是粒子集合。这不是缺陷指控，而是必须写明的**范围事实**，也是缺口 **G5** 的前提。
* **持有实例 ≠ 已接入。** `_runtime_operator_instances_for_execution` 把
  `orrer_cheh` 声明为 `(core._event_engine, self.feedback_revision_loop)` 两个实例，
  但 `feedback_revision_loop` 在任何生产入口下都不被调用（缺口 **G2**，已由测试钉死）。

## 3. 真实调用与消费图

### 3.1 P5 主路径 + CIAV 反馈路径（13 条回执，实测）

以 `run_p5_direct_trace_probe` 与本窗口探针在同一 seed 下取得，`verify_execution_trace` 通过：

| # | phase | operator | binding_kind | 实际被调用的 callable | 声明消费 | 真实消费（数据依赖） |
|---|---|---|---|---|---|---|
| 0 | selected_path | opceu | `direct_operator_callable` | `ObservationPropensityCorrector.weight_for_opportunity` | — | — |
| 1 | selected_path | orrer_cheh | `direct_operator_callable` | `OpenWorldRoleConditionedReversibleEventRevisionEngine.branch` | — | — |
| 2 | selected_path | pchmp | `direct_operator_callable` | `ProvenanceConstrainedMessagePassing.consume` | orrer_cheh | **真实**：`consume(history, evidence)` 直接取 #1 的返回值 |
| 3 | selected_path | cf_bocpd | `direct_operator_callable` | `JointCauseFactorizedBOCPD.observe_online` | pchmp | **真实**：`regime_frame` 的 `NOISE=max(obs_ambiguity, event_posterior.unresolved_probability)`、`ACTOR=1-owner_mass` 均来自 #2 |
| 4 | selected_path | ccrr | `composite_operator_stage` | `AutomaticCFBOCPDCCRRRouter.observe` | pchmp, cf_bocpd | **真实**：`owner_probability=owner_mass`（#2）；内部先 `bocpd.observe_online` 再 `ccrr.decide(snapshot=…)`（#3） |
| 5 | selected_path | rgrc | `enclosing_runtime_stage` | `CorePrototypeSpine._process_transition` | opceu, pchmp, ccrr | **真实但非专属**：`propensity`(#0)、`actor_posterior`(#2)、`assessment`(#4) 都进入提交/读出；但该回执的 `raw_input=transition`、`output=result`，即整段 enclosing stage，**不存在独立的 RGRC callable** |
| 6 | selected_path | ciav | `adaptive_composite_stage` | `StructureTwoProductionSystem._execute_ciav_operator` | ccrr, rgrc | **真实**：读 `core.current_cause_snapshot`（=#4 的 `assessment.snapshot`）与 `primary_result`（=#5 输出） |
| 7 | feedback_closure | opceu | `adaptive_composite_stage`/`direct_operator_callable` | 同位置分支：`CorePrototypeSpine.apply_fast_action_verification`；异位置分支：`weight_for_opportunity` | ciav | **真实**：异位置分支的 `transition.opportunity` 就是 `ciav_receipt.opportunity` |
| 8 | feedback_closure | orrer_cheh | `direct_operator_callable` | `...branch` | ciav | **真实**：`after=canonical_detection`（由 CIAV 检测结果构造） |
| 9–12 | feedback_closure | pchmp/cf_bocpd/ccrr/rgrc | 同主路径 | 同主路径 | 同主路径 | 同主路径 |

**关键结论（消费图的证据强度）：** `consumed_output_ids` 由调用方以 `consumes=(...)` 参数**声明**，
`_TransitionTraceRecorder._consumed_output_ids` 只是把算子名解析成先前回执的 `output_id`；
`_validate_adaptive_trace` 再把它与冻结常量图逐项比对。因此 trace 只证明
“**运行时的声明与冻结图一致**”，本身**不**证明真实数据依赖。真实依赖必须像上表那样逐条读源码确认，
或用本窗口的差分探针测量。`input_payload_sha256 = sha256({raw_input_sha256, consumed_output_ids})`
（`structure_two_execution.py:seal_operator_receipt`）——消费 id 被折进输入哈希，这是**自指的**，
不能当作消费证据。

### 3.2 P0 路径（7 条回执，实测）

| # | operator | status | binding_kind | callable | 声明消费 |
|---|---|---|---|---|---|
| 0 | opceu | executed | `direct_operator_callable` | `weight_for_opportunity` | — |
| 1 | orrer_cheh | **deferred** | — | — | — |
| 2 | pchmp | executed | `adaptive_safety_maintenance` | `_adaptive_pchmp_safety_maintenance(transition)` | — |
| 3 | cf_bocpd | executed | `adaptive_safety_maintenance` | `_adaptive_cf_bocpd_safety_maintenance()` | — |
| 4 | ccrr | executed | `adaptive_safety_maintenance` | `_adaptive_ccrr_safety_maintenance(...)` | cf_bocpd |
| 5 | rgrc | executed | `adaptive_safety_maintenance` | `_adaptive_rgrc_debt_guard(...)` | pchmp, ccrr |
| 6 | ciav | **deferred** | — | — | — |

第 4、5 行在起点提交上是**声明消费但结构上不可能真实消费**的缺陷（两个 callable 零形参）。
已修复，见第 7 节。

## 4. 机制级场景矩阵（实测）

全部由 `tests/test_structure_two_backbone_operator_wiring.py` 执行，28 项通过。
每格给出：预期不变量 / 应当变化 / 应当保持。**正确的 no-op 被断言为 no-op，不计为失败。**

| ID | 场景 | 预期不变量 | 应当变化 | 应当保持 | 实测 |
|---|---|---|---|---|---|
| S1 | 正观测 + 异位置 CIAV | 7 主 + 6 闭包回执，算子序与冻结序一致 | 动作分布、长期提交可达 | 消费图与冻结图一致 | 13 条回执，`full_transition`，动作改变 ✅ |
| S2 | 正观测 + 同位置 CIAV | 8 条回执，闭包仅 1 条 OPCEU | fast 账本 owner mass | 无第二次 transition、无长期提交 | ✅ `changed=True`，`committed=0` |
| S3 | 负观测（CIAV 未检出） | 7 条回执，`closure_kind="none"` | CIAV 下游无任何变化 | 无闭包回执、无提交 | ✅；**且 CIAV 已算出 owner 后验 0.9707（主路径 0.8055）随后被丢弃** |
| S4 | 同位置验证 → 动作 | fast owner mass 每次都变 | 仅当越过 `fast_owner_mass_floor=0.5` 时动作才变 | 未越界时动作不变（正确 no-op） | ✅ 0.8055→0.9937/0.8923/0.6744 动作不变；→0.3036/0.0772 动作变 |
| S5 | 多人歧义 | 开放 actor support 端到端保持 | — | `unknown_actor` 质量 > 0 | ✅；缩小先验到 {owner,guest} 被生产守卫拒绝（`actor posterior support drifted before CIAV`） |
| S6 | 未知人物（开放世界） | unknown 质量不塌缩 | 未知事件日 unknown 质量升高 | 全程 > 0 | ✅ 全程 min 0.0669，未知日 max 0.7705 |
| S7 | 阶段变化 + 历史状态恢复 | CCRR 结论序列出现 `create` 与 `reactivate` | regime id 变化 | reactivate 返回的必须是**更早出现过的** regime id | ✅ d4 `create` → d18 `create` → d27 `reactivate`（回到 d4 的 regime id） |
| S8 | 迟到反证 / 撤回及下游 | 撤回前后 full-rerun equivalence 恒为 True | 动作分布改变、live 记录清零 | 无残留贡献、无重复计数 | ✅ 重复 retract 后动作与等价性均不变 |
| S9 | RGRC quarantine/promote/reject | 自适应主路径恒 quarantine | 仅异位置闭包可 promote | 同位置/负观测恒不提交 | ✅ 见 S13 数据 |
| S10 | direct P5 vs P0 欠账 replay | 语义量一致 | — | actor 后验、habit hash、动作分布、active regime 全等 | ✅ |
| S10b | 状态哈希可比性（反向对照） | — | — | 两次**完全相同**的 direct run 的 `_execution_observable_state_sha256` 必然不同 | ✅ 证明该哈希不可用作跨运行等价见证（根因：`prototype_spine.py:2228` 的 `uuid4()`） |
| S11 | 重复反馈 | 幂等 | — | 重复 `apply_fast_action_verification` → `changed=False`、`receipt_id` 相同、动作不变 | ✅；未知 revision → `KeyError` |
| S12 | 失败回滚 | sink 拒绝提交后模型完全回滚 | — | 状态哈希、动作、committed、quarantined 全部复原 | ✅ |
| S13 | 陈旧状态 | 复用旧特征快照必须被拒 | — | — | ✅ `stale or foreign` |
| S14 | 并发/多债务 | 有未偿债务时任何新执行被拒 | — | `process_adaptive_transition`、`process_evaluation_direct_p5_transition`、错配 CIAV 的 replay 全部拒绝；重复 replay 拒绝 | ✅ |

### 4.1 长期巩固可达性（S13 的量化结果，同一 14 天输入）

| CIAV 实现 | committed | quarantined |
|---|---|---|
| 同位置检出 | **0** | 14 |
| 未检出 | **0** | 14 |
| 异位置检出 | > 0 | < 14 |
| （对照）legacy ordinary 车道 | ≥ 12 | 0 |

这就是缺口 **G1** 的直接测量。

## 5. 五类证据判定表

严格分开，不合并。`not_covered` 表示本窗口没有产生该类证据，不表示失败。

| 算子 | 同一生产运行时 | 算法实现等价 | 状态交接正确 | 动作受影响 | 长期效用提升 |
|---|---|---|---|---|---|
| OPCEU | **pass**（`is` 身份核验 + 源码哈希绑定） | **pass**（`direct_operator_callable`，绑定 `weight_for_opportunity`） | **pass**（`propensity.applied_weight` 进入 `rls_sample.gate` 与 `statistical_owner_weight`） | **pass（有条件）**：仅在同位置闭包且越过 `fast_owner_mass_floor` 时（S4） | not_covered |
| ORRER_CHEH | **pass（部分）**：声明的两个实例中只有 `core._event_engine` 被绑定与调用；`feedback_revision_loop` 从不被调用且是**另一个** engine 实例 | **pass**（`branch`） | **pass**（`history → pchmp.consume`） | **pass**（经 `event_revision_id` 决定 fast 账本条目） | not_covered |
| PCHMP | **pass** | **pass**（`consume`） | **pass**（`event_posterior`/`actor_posterior` 进入 `regime_frame`、`evidence`、CIAV 先验） | **pass** | not_covered |
| CF-BOCPD | **pass** | **pass**（`observe_online`） | **pass**（`snapshot` 进入 CCRR `decide` 与 `core.current_cause_snapshot`） | **pass**（经 CCRR 结论） | not_covered |
| CCRR | **pass** | **pass（边界）**：`composite_operator_stage`，回执绑定 `AutomaticCFBOCPDCCRRRouter.observe`，内部才是 `ccrr.decide`；`I` 轴入参恒为 0.0（G4） | **pass**（S7 的 create/reactivate） | **pass** | not_covered |
| RGRC | **pass** | **fail（诚实登记）**：不存在独立 RGRC callable，回执绑定 `CorePrototypeSpine._process_transition`（`enclosing_runtime_stage`），跨越 quarantine/promote/commit/RLS/地图发布 | **pass**（S8 撤回语义正确、无双计） | **pass（受限）**：自适应车道上只有异位置闭包能改变长期动作（G1） | not_covered |
| CIAV | **pass** | **pass（边界）**：`adaptive_composite_stage`，绑定 `_execute_ciav_operator`，内部才是 `planner.select` + `ciav_opceu_loop.execute_selected_action` | **pass（正观测）** / **fail（负观测）**：负观测下 CIAV 后验被计算后无任何下游消费（G3） | **pass（阈值型）**（S4） | not_covered |

**长期效用提升一列全部 `not_covered` 是本报告的硬边界**：本窗口不运行、也无权运行任何效用比较。

## 6. 真实缺口与后续接入顺序

按“先接线、后方法”排序。凡涉及粒子预算、提议器、重采样、回春核、梯度策略或整体方法改变的，
本窗口**不擅自决定**，只给出接入方案、接口合同、依赖顺序与需用户决策的绑定项。

### G1（最高优先）自适应车道上的长期巩固只经由“异位置 CIAV 闭包”可达

* 现象：`_execute_adaptive_plan` 对 P1–P5 的主路径一律 `force_long_term_write_blocked=True`
  （`structure_two_production_system.py:1136`）。`_process_transition` 在该标志下直接
  `self._quarantined_events.append(...)`（`prototype_spine.py:2395`），
  `HABIT_CHANGE` 的 promote 分支与 `SHORT_TERM_DISTURBANCE` 的 reject 分支都**不可达**；
  长期写入门 `prototype_spine.py:2432` 也被同一标志关闭。自适应路径上唯一未被阻断的
  `_process_transition` 是 CIAV 异位置反馈闭包。
* 后果：一次**确认性**（同位置）主动验证永远不能巩固，一次**否证性**（异位置）验证却可以；
  隔离期无界增长（14 天输入下 quarantined=14，committed=0）。
* 需要用户决策的绑定项（属冻结方法 §9 的 `consolidation thresholds`，本窗口不得代选）：
  1. 同位置确认性验证是否、以及在什么 owner-mass / 确认次数条件下可以解除 `force_long_term_write_blocked`；
  2. 负观测是否允许触发 reject（`SHORT_TERM_DISTURBANCE`）从而清理隔离期；
  3. 隔离期上限与溢出策略（强制升级 P5 / 强制 safe-abstain / 强制 replay）。
* 接入顺序建议：G1 决策 → 改 `_execute_adaptive_plan` 的阻断条件（局部）→ 重跑 S9/S13 → 重算受影响工件。

### G2 `feedback_revision_loop` 被声明为 ORRER_CHEH 实例但从不被生产路径调用，且是另一个 engine

* 现象：`structure_two_production_system.py:494` 用 `ProjectTwoFeedbackRevisionLoop(projector=...)`
  构造，**未传 `engine=` / `message_passing=`**，因此它自建了一个
  `OpenWorldRoleConditionedReversibleEventRevisionEngine` 和一个 `ProvenanceConstrainedMessagePassing`，
  与 `core._event_engine` / `core._message_passing` 不是同一对象。
  `_runtime_operator_instances_for_execution` 仍把它声明为 ORRER_CHEH 的第二个实例。
  全仓库 `ingest_feedback` 的唯一调用方是 evaluator-local 的
  `project_two_action_benchmark.py:1400`；`CorePrototypeSpine.process_execution_feedback`
  的唯一调用方是 `tests/test_project_one_automatic_regime_loop.py`。
* 合同依据：`方向结构二_Tasks10-13…协议_v1.0` §1「算子可以 enabled-no-op，但该 no-op 必须进入认证
  runtime receipt；不能把『没有调用记录』解释成已启用」。目前该实例既无调用记录也无 no-op 回执。
* 为什么本窗口**不**直接改：把 `feedback_loop._engine` 指向 `core._event_engine` 会让
  `_restore_execution_wrapper_state`（对组件字段做 `deepcopy` 回写）与
  `core._restore_revision_transaction` 在同一对象上产生两条回滚所有权路径，
  `replay_adaptive_debt` 的异常路径先后调用二者，回滚语义会改变。这是接口合同问题，不是笔误。
* 接入方案（供决策）：
  1. 合同项 A：ORRER_CHEH 的运行时身份是「单一 engine」还是「engine + 反馈修订环」；
  2. 合同项 B：若为单一 engine，反馈环必须以 `engine=core._event_engine,
     message_passing=core._message_passing` 构造，且回滚所有权归 `core`，
     `_capture/_restore_execution_wrapper_state` 必须把这两个对象从组件表中移除；
  3. 合同项 C：若保留两个 engine，则 `_runtime_operator_instances_for_execution` 不应把反馈环
     声明为 ORRER_CHEH 实例，而应单列为未接入组件，并在 assembly manifest 中显式标注
     `declared_but_never_bound`。
* 依赖顺序：G2 必须在「具身反馈 → 迟到反证 → 可逆撤回」接入生产路径之前解决。

### G3 负观测的 CIAV 后验被计算后丢弃，且证据因子 trace 仍声明了一次 likelihood 消费

* 现象一：`_execute_adaptive_plan` 仅在 `detection.outcome is DETECTED` 时进入闭包；
  否则 `ciav_receipt.evidence.actor_posterior`（实测 owner 0.9707 vs 主路径 0.8055）无任何下游消费。
* 现象二：`ciav_opceu_loop.execute_selected_action` **无条件**向
  `EvidenceFactorConsumptionTrace` 写 `produce → consume(consumed_as_likelihood=True,
  target_distribution_id="fast-action-owner-posterior:{update_id}") → derive`，
  而写入该目标分布的 `apply_fast_action_verification` 只在同位置分支运行。
  负观测与异位置分支下，trace 声明了一次不存在的目标分布消费。
* 现象三：`structure_two_p5_three_arm_death_test.DirectP5LocationAdapter` 的负观测分支
  **完全绕过生产入口**，直接调用 `system.ciav_opceu_loop.execute_selected_action(...)`，
  使用全 1 的 actor 似然表，不产生任何 `StructureTwoExecutionTrace`、算子回执或债务凭证，
  且其 `update_id` 是 `content_uuid(PROTOCOL_ID, {... "negative-closure"})`，并非真实 revision id。
* 合同依据：`结构二_自适应路由特征与路径内核冻结决策表_2026-09-10` 已登记
  「negative observation 尚无完整下游闭包」，因此这是**已登记缺口**，不是未知缺陷；
  本报告把它量化，并新增现象二、现象三两项此前未登记的事实。
* 需要用户决策：负观测应如何进入 OPCEU 观测似然（选择性观察的 MNAR 权重），
  以及负观测是否应产生一条 `enabled-no-op` 的认证回执。本窗口不代选。

### G4 `I` 轴（实例/身份切换）在生产 CCRR 上恒为 0

* 现象：`prototype_spine.py` 调用 `self._automatic_regimes.observe(...)` 时不传
  `identity_switch_probability`，默认 `0.0`；trace 的 `raw_input` 如实记录了
  `"identity_switch_probability": 0.0`。同一量在 CIAV 侧却由 `AdaptiveCIAVRuntimeInput` 提供。
* 后果：阶段判定（`Z`）与身份不确定性（`I`）在生产路径上解耦。
* 需要用户决策：`I` 轴在生产路径上的来源（PCHMP 实例后验？独立实例关联图？调用方？），
  这属于特征冻结范畴（决策表第一节 `instance_ambiguity` 行），本窗口不代选。

### G5 类型化粒子修订不在生产主干上

* 现象：生产主干的后验表示不是粒子集合；`TypedParticleState` 相关实现只存在于 evaluator-local 证伪器中，
  与 `StructureTwoProductionSystem` 无调用关系。
* 这与冻结方法 §9 的现状一致（`particle budget` / `resampling policy` / `rejuvenation kernel` /
  `neural proposer architecture` / `differentiability strategy` 全部 `unresolved`），
  因此**不是**可修复的接线缺陷，而是尚未接入的方法组件。
* 接入顺序（依赖链，均需用户先冻结绑定）：
  `particle budget` → `proposal kernel（含规则候选并存）` → `importance weight + ψ 硬约束` →
  `unresolved 质量归一化` → `resampling policy` → `rejuvenation kernel + replay fallback` →
  `differentiability strategy`。在 `particle budget` 冻结前，后续每一项都无法定义验收阈值。

### G6 运行时状态身份不可跨运行重算

* 现象：`_execution_observable_state_sha256` 经 `HabitLearningEvidence.metadata.record_id = uuid4()`
  （`prototype_spine.py:2228`）引入运行内随机性；
  `adaptive_router_state_sha256` 又包含它。两次**完全相同**的 direct P5 运行得到不同的状态哈希（S10b）。
* 后果：该哈希只能用作**单次运行内**的分支演化检测（`replay_adaptive_debt` 的现用法是正确的），
  不能用作跨运行/跨进程的状态等价见证，也不足以关闭决策表第四个工程门
  「`p0_p5_consequential_runtime_identity_established`：全链可鲜重算」。
* 为什么本窗口不改：把 `uuid4()` 换成 `content_uuid(...)` 会改变记录身份语义，
  与 M03「批内记录ID唯一性」以及 replay 时同一 transition 重复处理产生同一 record_id 的去重假设相互作用，
  属于契约层决策。
* 需要用户决策：记录身份是否改为内容寻址；若是，replay 场景下的重复 record_id 如何与幂等提交协调。

### G7 声明实例多于被绑定实例时不会被发现

* 现象：`_execution_callable_bindings` 的核验条件是
  `len(supplied) < len(expected)` 加 `zip(..., strict=False)`，
  因此**多出来的声明实例既不被身份核验也不会产生回执**；
  `verify_runtime_assembly` 虽然逐项比对类型元组，但它不在 `process_transition` 路径上被调用。
* 与 G2 是同一问题的两个面。建议与 G2 一并决策。

## 7. 已完成的局部接线修复（唯一一处）

只修复了**有明确冻结合同依据**的一处：P0 路径的声明消费图在结构上不可能成立。

* 冻结合同：`structure_two_execution.py` 中
  `ADAPTIVE_PRIMARY_CONSUMPTION_GRAPHS["P0_SAFE_DEFERRED"]` 声明
  `ccrr <- (cf_bocpd,)`、`rgrc <- (pchmp, ccrr)`，并由 `_validate_adaptive_trace` 强制校验。
* 起点缺陷：`CorePrototypeSpine._adaptive_ccrr_safety_maintenance` 与
  `_adaptive_rgrc_debt_guard` 在起点提交上**均为零形参**，
  `_execute_p0_safe_deferred` 也以 `args=()` 调用，
  因此这两条被验证器强制的边**不可能**对应任何数据依赖；
  四个 maintenance 回执的 `raw_input` 还是同一个字典。
* 失败测试先行：
  `tests/test_structure_two_backbone_operator_wiring.py::test_p0_downstream_maintenance_really_consumes_its_declared_upstream_output`
  与 `::test_p0_trace_output_hashes_change_when_the_declared_upstream_output_changes`
  在修复前分别以 `AssertionError: [] == ['cf_bocpd_maintenance']` 和
  `TypeError: ... takes 1 positional argument but 2 were given` 失败。
* 最小修复（不改任何冻结常量、不弱化冻结图）：
  * `prototype_spine.py`：`_adaptive_ccrr_safety_maintenance(cf_bocpd_maintenance)`、
    `_adaptive_rgrc_debt_guard(pchmp_maintenance, ccrr_maintenance)`，
    并把消费到的上游载荷哈希写进各自返回体；
  * `structure_two_production_system.py::_execute_p0_safe_deferred`：
    按冻结图把上游输出实参传给下游 maintenance，并在 `raw_input` 中记录
    `consumed_operator_output_sha256s`。
* 修复后：上述两个测试通过；扰动 cf_bocpd maintenance 输出会改变 ccrr 回执的 `output_payload_sha256`。
* **明确不做的事**：没有改 `ADAPTIVE_PRIMARY_CONSUMPTION_GRAPHS`，没有把声明边删掉以“让测试变绿”。

## 8. 工件失效登记（整合后需重算）

代码变更导致以下工件的哈希不再匹配，必须在整合后重算，本窗口不重算也不改写：

| 工件 | 失效原因 |
|---|---|
| 任何包含 **P0_SAFE_DEFERRED** 执行 trace 的回执/报告（ccrr、rgrc maintenance 的 `output_payload_sha256`、`input_payload_sha256`、`receipt_sha256`、后续链式哈希、`trace` 级哈希） | 第 7 节修复改变了两个 maintenance 的返回体与 raw_input |
| `build_production_assembly_manifest` 产出的 `transitive_source_rows` 中 `src/cpswm/system/prototype_spine.py` 与 `src/cpswm/system/structure_two_production_system.py` 的 `sha256`，以及由其派生的 manifest 哈希 | 两文件内容改变 |
| 任何绑定 `implementation_source_sha256` / `loaded_callable_code_sha256` 到上述两文件的 `RuntimeCallableBinding` 快照 | 同上 |
| 新增文件不使既有工件失效：`tests/structure_two_backbone_wiring_probe.py`、`tests/test_structure_two_backbone_operator_wiring.py` | 探针 harness 刻意放在 `tests/` 而非 `src/cpswm/`：`build_production_assembly_manifest` 会对 `src/cpswm` 下**每个** `.py` 取哈希并写进 `transitive_source_rows`，把审计用模块放进去会改变此后每一次 manifest 重算。导入方式与既有 `tests/ledger_evidence_fixtures.py` 相同 |

`src/cpswm` 下的**文件清单**未改变（只有上述两个既有文件的内容改变），
因此 `transitive_source_paths` 的条目集合不变，只有其中两行的 `sha256` 需要重算。

**未失效**（本窗口未触碰）：历史 benchmark、科学阈值、全局 manifest 文件、工程 checkpoint、
`configs/project_two_experiments/*`、P5 direct trace probe 与 debt replay confirmation 的配置与产物
（其代码路径未改，实测仍通过）。

## 9. 复现

```bash
# 1) 取得本分支
git fetch . codex/s2-backbone-operators-w3
git worktree add /private/tmp/cpswm-s2-w3 codex/s2-backbone-operators-w3

# 2) 在仓库固定的 Python 3.13 环境下（推荐，无需任何语法降级）
python3.13 -m venv .venv && .venv/bin/python -m pip install -e '.[dev]'

# 3) 本窗口新增的机制级场景矩阵
PYTHONPATH=src .venv/bin/python -m pytest -o addopts='' -q -p no:cacheprovider \
  tests/test_structure_two_backbone_operator_wiring.py

# 4) 受影响的既有回归
PYTHONPATH=src .venv/bin/python -m pytest -o addopts='' -q -p no:cacheprovider \
  tests/test_core_prototype_spine.py \
  tests/test_structure_two_production_system.py \
  tests/test_structure_two_execution_interface.py \
  tests/test_structure_two_adaptive_runtime.py \
  tests/test_structure_two_adaptive_runtime_adversarial_round1.py \
  tests/test_structure_two_adaptive_runtime_adversarial_round2.py \
  tests/test_structure_two_p5_direct_trace_probe.py \
  tests/test_structure_two_p5_debt_replay_confirmation.py

# 5) 全量
PYTHONPATH=src .venv/bin/python -m pytest -o addopts='' -q -p no:cacheprovider
```

### 9.1 本窗口实测（Python 3.11 + 语法降级夹具；第 1 节环境偏差适用于全部结果）

| 运行 | 结果 |
|---|---|
| `tests/test_structure_two_backbone_operator_wiring.py`（新增，28 项） | **28 passed** |
| 受影响回归 8 个文件（core spine、production system、execution interface、adaptive runtime ×3、P5 direct probe、P5 debt replay） | **118 passed, 4 failed** — 4 项全部是第 1 节登记的 cryptography 46 `deepcopy` 环境失败 |
| **差分回归**：对 18 个可能受影响的测试文件，在**起点提交的纯净副本**与**本分支**上跑同一集合，比较失败/错误集合 | 起点 49 条、分支 49 条，**集合完全相同（45 个不同测试 id）**；`comm -13` 与 `comm -23` 均为空，即**零新增失败、零新增修复** |

差分回归的两条命令（`/home/claude/base` 是起点提交的纯净副本）：

```bash
# 分支
python -m pytest -o addopts='' -q -p no:cacheprovider -rfE $(cat affected.txt) \
  | grep -E '^(FAILED|ERROR)' | sed 's/\[.*//' | sort -u > branch_set.txt
# 起点
python -m pytest -o addopts='' -q -p no:cacheprovider -rfE $(cat affected.txt) \
  | grep -E '^(FAILED|ERROR)' | sed 's/\[.*//' | sort -u > base_set.txt
comm -13 base_set.txt branch_set.txt   # 新增失败：空
comm -23 base_set.txt branch_set.txt   # 新增修复：空
```

那 45 个在**起点提交上就失败**的测试分两类，均与本窗口改动无关：
cryptography 46 的 `Ed25519PublicKey` 不可 `deepcopy`（4 项）；
以及本容器内的源码树是从设备打包上传的子集（缺 `.git`、`output/`、`artifacts/`、
大于 900KB 的 benchmark 文件），导致 `runtime_identity_gate` /
`full_scientific_loop` / `adaptive_compute_predeath` 等依赖完整检出与历史工件的测试失败。
**这些测试必须在完整检出 + Python 3.13 上重跑才能给出有效结论；本报告不对它们下任何判定。**

全量套件在本容器内未跑完（2 核 + 语法降级夹具下推进到 56% 时被主动终止，以把 CPU 让给上面的差分回归）。
因此全量结果标记为 `not_covered`。

## 10. 本报告不授权的事项

* 不签发 `TrustedSevenOperatorAblationAuthorization`，不运行七算子消融，不运行路由器训练；
* 不把本报告任何 `pass` 解释为 Task 7/8/9、Gate B、P5 死亡测试或 adaptive readiness 通过；
* 不把工程接线通过写成科学门通过；
* 不选择 Task 10 粒子预算、Task 11 重采样策略、Task 12 回春核、Task 13 梯度策略、
  consolidation thresholds、CIAV action budget 或任何路由特征公式；
* 不缩小结构二的研究范围。
