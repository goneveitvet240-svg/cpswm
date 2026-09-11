# 结构二：窗口三第二轮 —— 合同级修复、生产入口端到端证据与结论收窄

日期：2026-09-11
分支：`codex/s2-backbone-operators-w3`
本轮起点：`d6db421d33b6499ca7dfbead3d4ecb543a371970`（第一轮终点）
共同起点：`09eb4d48e1c11082e90ca18332d04333e6b5b47a`
外部对抗复核：`docs/reviews/structure_two_windows2_3_adversarial_review_2026-09-11.md`
状态：**PARTIAL_AUDIT（部分审计）— D0 工程接线证据，不构成任何科学门**

## 0. 本轮做了什么，没做什么

做了四件事：

1. 按冻结合同判定 P0 的真实语义，实现合同要求的依赖检查，并**收窄第一轮的过度声明**；
2. 用**正式生产入口**（`process_execution_feedback`）建立迟到反证全链路证据，替换第一轮直接调用私有子账本的 S8；
3. 用**逐算子受控干预 + 空对照**重建七算子因果证据表，把“绑定方式”与“算法等价”彻底分开；
4. 对 CIAV 负观测做四层分解，修正回执语义，并对留存产物按正式验证器重新登记失效状态。

没做：不启动 Task 9 消融、不训练路由器、不改写历史 benchmark/科学阈值/全局 manifest/工程 checkpoint、
不合并其他分支、不修改窗口一的证据治理实现或窗口二的比较验证器、不缩小结构二框架。

**所有运行证据本轮改用项目原生环境**：`/Users/pangwei/.../.venv/bin/python`，Python 3.13.5、
numpy 2.5.2、cryptography 47.0.0、pytest 9.1.1、scikit-learn 1.9.0。
**不再使用第一轮的 PEP 695 语法降级夹具，也不使用任何导入替换。**
第一轮报告中登记的四项 cryptography 环境失败在原生环境下不复现，本轮据此撤回“它们是已确认代码问题”的说法。

## 1. 逐项交付状态

每条按四种状态之一交付。只有前两类可以关闭。

| 编号 | 事项 | 状态 | 证据 |
|---|---|---|---|
| R2 | P0 下游维护节点“收到并绑定字节”被当成“已消费/已检查” | **已修复且反例回归通过** | 独立反例的三种矛盾载荷现在被 `AdaptiveMaintenanceContractError` 拒绝；22 项反例回归 |
| R2-claim | 第一轮把“哈希改变”写成“真实算子消费” | **原结论已纠正** | 两个第一轮测试被重写为检查语义，而非输出差异 |
| R3 | S8 只撤回 Hybrid 子账本 | **已补正证据 + 发现并修复一处生产缺陷** | 10 项正式入口全链路测试；`_rebuild_personalized_models` 快照重绑定修复 |
| R3-gap | 一次正式修订会把被写入阻断的隔离期观测全部提交 | **需要用户决定的协议/方法变更** | 见 §5 G8，已由特征化测试钉死 |
| R4 | 七算子动作影响与算法等价表超出证据 | **已补正证据 + 原结论已纠正** | 20 项逐算子受控干预与空对照；表已重建并分列 |
| R5 | “留存产物未失效”不成立 | **原结论已纠正** | 四态失效登记表，按各自正式验证器实跑 |
| R6 | CIAV 负观测“似然未被消费”表述过粗 | **已修复且回归通过** | 四层分解；回执 `target_distribution_id` 已改为真实写入目标；12 项测试 |
| G1 | 自适应车道长期巩固只经异位置闭包可达 | **需要用户决定的协议/方法变更** | 第一轮量化结果保持，本轮新增 G8 与之关联 |
| G2 | `feedback_revision_loop` 未被生产路径调用、且是另一个 engine | **功能仍缺失** | 第一轮结论保持；本轮未扩大范围 |
| G4 | CCRR 身份轴输入恒为 0.0 | **功能仍缺失** | 第一轮结论保持 |
| G5 | 粒子主干/神经提议器/条件化 RB 块未接入生产 | **功能仍缺失** | 保留在架构映射与缺口表中，未删除 |
| G6 | 运行时状态身份不可跨运行重算 | **需要用户决定的协议/方法变更** | 第一轮结论保持；本轮 §4.6 补充了新的佐证 |

## 2. R2：P0 的真实语义与已实施的检查

### 2.1 合同判定：P0 不是纯回执绑定

冻结来源：`configs/project_two_experiments/structure_two_adaptive_compute_predeath_v0_1.json`。

`legal_paths[P0_SAFE_DEFERRED]`：

```text
semantic_purpose = "Run mandatory semantic and write-safety maintenance while
                    deferring expensive refinement under explicit inference debt."
rgrc_remains_only_long_term_write_authority = true
all_seven_operator_receipts_required = true
```

`hard_safety_kernel`（对所有合法路径生效）：

```text
provenance_and_dependency_checks_always_executed   = true
unexecuted_inference_may_not_be_encoded_as_negative_evidence = true
router_may_grant_long_term_write                   = false
rgrc_is_only_long_term_write_retract_authority     = true
maximum_safety_violations                          = 0
maximum_provenance_violations                      = 0
maximum_unresolved_as_negative_events              = 0
maximum_unauthorized_long_term_commits             = 0
```

因此结论是明确的：**P0 的下游节点不是“纯回执绑定的安全空操作”**。
`provenance_and_dependency_checks_always_executed` 对每条合法路径都为 `true`，
而 `ADAPTIVE_PRIMARY_CONSUMPTION_GRAPHS["P0_SAFE_DEFERRED"]` 声明的
`ccrr <- cf_bocpd`、`rgrc <- (pchmp, ccrr)` 就是这条路径的依赖结构。
“收到载荷并写入哈希”不满足“检查已执行”。

同时必须承认：`semantic_purpose` 只说“语义与写入安全维护”，
**没有逐算子列出检查清单**。本轮只实现能从上面三条字面条款直接推出的检查，
不发明新的语义判据。

### 2.2 已实施的检查

实现位置：`src/cpswm/system/prototype_spine.py`
（`_require_maintenance_payload`、`_adaptive_ccrr_safety_maintenance`、`_adaptive_rgrc_debt_guard`），
新异常 `AdaptiveMaintenanceContractError` 定义在 `src/cpswm/system/structure_two_execution.py`。

| 检查 | 冻结依据 | 拒绝的载荷 |
|---|---|---|
| 载荷必须是 mapping | `provenance_and_dependency_checks_always_executed` | 元组/None/标量 |
| `maintenance_kind` 必须匹配 | 同上（跨节点替换即依赖不成立） | 把 pchmp 载荷当 cf_bocpd 传入 |
| 字段集合必须与冻结形状一致 | 同上 | 缺字段、多字段 |
| `observation_count` 必须等于本运行时当前值 | 同上（陈旧/跨执行替换） | `-999`；另一运行时产生的载荷 |
| `current_snapshot_sha256` 必须等于当前 cause snapshot | 同上（跨快照替换） | `"foreign"` |
| `posterior_advanced` 必须为 `False` | `P0` 的 `semantic_purpose`（deferring refinement）+ `mandatory_maintenance_executed` 模式 | `True` |
| `unexecuted_inference_encoded_as_negative` 必须为 `False` | `unexecuted_inference_may_not_be_encoded_as_negative_evidence`、`maximum_unresolved_as_negative_events=0` | `True` |
| `message_passing_runtime_type` 必须等于活运行时类型 | `provenance_and_dependency_checks_always_executed` | 伪造类型名 |
| `regime_transition_applied` 必须为 `False` | P0 deferral 语义 | `True` |
| `active_regime` / `pending_candidate_sha256` 必须等于活状态 | 同上 | 伪造 regime、伪造 pending 哈希 |
| 返回体 `long_term_write_authorized` 恒为 `False` | `router_may_grant_long_term_write=false` | —（不变量） |

**拒绝路径不修改状态**：所有检查都在返回体构造之前完成，只读 `self`，随后抛异常。
回归 `test_ccrr_maintenance_rejects_a_contradictory_cf_bocpd_dependency` 与
`test_rgrc_debt_guard_rejects_a_contradictory_declared_dependency`
在每次拒绝前后比较 7 元组语义状态（观测哈希、Dirichlet 哈希、fast 事件、committed、quarantined、regime、动作分布），要求完全相等。

**事务级拒绝也不留残留**：`test_a_refused_p0_commit_leaves_no_pending_debt_and_no_state_change`
用失败 sink 中断一次 P0。P0 的债务凭证是在维护循环之前就写入 `_adaptive_debt_ledger` 的，
因此这是最强的检查点：事务失败后 `pending_adaptive_debts() == ()`，语义状态完全复原。

### 2.3 修改前失败 / 修改后通过

独立反例脚本（未修改）：

```bash
.venv/bin/python docs/reviews/data/structure_two_windows2_3_adversarial_review_2026-09-11/counterexamples.py \
  /private/tmp/s2-w3-native w3
```

- 修改前（`d6db421`）：打印 `"invalid_upstream_payload_accepted": true`、
  `"ccrr_semantic_output_unchanged": true`、`"rgrc_semantic_output_unchanged": true`。
- 修改后：在 `counterexamples.py:33` 抛出
  `AdaptiveMaintenanceContractError: ccrr maintenance dependency observation count differs from this runtime`。

该脚本此后不再能跑完 W3 段，这是预期的：它的 P0 段构造的就是现在被合同拒绝的载荷。
同样的矩阵已固化为 22 项回归，位于
`tests/test_structure_two_backbone_counterexample_regressions.py`。

### 2.4 收窄后的声明

可以声称的**只有**：

> P0 的 CCRR 与 RGRC 维护节点会对其冻结声明的上游依赖执行形状、类型、跨快照、
> 跨执行与延迟语义一致性检查，并在任何不一致时先于任何状态修改失败关闭；
> 其返回体永远不授权长期写入。

**不能声称**：P0 已经执行了算子级推断消费。
检查通过时下游返回体是活状态快照，而载荷必须**等于**活状态才能通过，
所以任何被接受的载荷都不可能改变返回体。
这一边界本身也被测试钉死（`test_a_passing_p0_dependency_check_does_not_make_the_body_upstream_dependent`）。
第一轮的两个测试已相应重写：不再断言“上游扰动改变下游输出”，改为断言“矛盾载荷被拒绝”
与“回执可由被检查的依赖链重算”。

## 3. R3：正式生产入口的迟到反证全链路

### 3.1 用的是哪个入口

`CorePrototypeSpine.process_execution_feedback`（`@_serialized_core_mutation` 公开方法，
`StructureTwoProductionSystem` 通过 `__getattr__` 直通）。它依次执行：
反馈↔修订绑定校验 → `_hybrid_loop.prepare_execution_feedback` 似然投影 →
重放检测（幂等空操作）→ 解释策略 → `apply_event_revision_outcome`（全或无事务）。

`DefaultPrototypeFeedbackPolicy` 的源码注释写明「negative evidence is deliberately
quarantined by default. A caller may plug in a calibrated policy that emits RETRACT or
CORRECT」，而 `process_execution_feedback` 本身就有 `policy=` 具名参数。
因此本轮提供 `CalibratedRetractionPolicy` 是**使用已声明的生产接缝**，不是绕开它。
仓库内目前没有内置的校准撤回策略——这一点本身记入缺口表（G9）。

### 3.2 独立对账参考

不使用「同一个已修改子账本重算」。参考量由**幸存的 committed 事件集合**独立重建：

```text
hybrid_alpha(L)  ==  Σ_{e ∈ committed, e.location == L} e.statistical_owner_weight
```

在 12 天 legacy 历史上实测逐位置吻合到 1e-9（`44b33099:8.701511`、`a5a97d44:1.449248`）。
每次撤回后重新对账；残留贡献或重复计数都会破坏该等式。
第二个独立参考是仓库自带的 append-only 重放 `verify_hybrid_full_rerun_equivalence()`。

### 3.3 全链路对账结果

| 追踪项 | 一次正式撤回后的实测 |
|---|---|
| 目标修订在 `_committed_events` | 移除 |
| 目标修订在 `_observed_events` | 移除 |
| Hybrid live promoted records | 0 |
| Hybrid 质量（目标位置） | 精确减少 1 个事件的 `statistical_owner_weight`（1.2430730699988313） |
| Hybrid 质量（其他位置） | 不变 |
| 独立对账等式 | 成立 |
| full-rerun equivalence | True |
| 后代修订 | 标记 `TOMBSTONED_ANCESTOR_INVALIDATED` |
| 地图发布 | `map_version` 递增 |
| 动作分布 | 改变 |
| 解码 PUT_BACK top-1 | 见 §3.5 |
| 债务账本 | 无残留（P0 场景另测） |

连续 6 次撤回：目标位置质量从 `8.701511` 逐次精确减 `1.2430730699988313`，
每步都通过独立对账——**没有重复计数，也没有残留**。

### 3.4 发现并修复的生产缺陷：一次修订后全部幸存修订失去快照绑定

**现象（修改前，在 `d6db421` 上实测）**：12 条 committed 事件中 12 条带 `belief_snapshot_id`；
经过一次正式 `process_execution_feedback` 撤回后，剩余 11 条**全部**变成 `belief_snapshot_id is None`，
于是 `_validate_feedback_revision_binding` 对它们一律抛
`"feedback revision has no committed snapshot binding"`。
**正式迟到反证入口在一次修订之后，对整条剩余历史不可用。**

**根因**：`_process_transition` 只把快照 id 写进 `_committed_events`，不写进 `_observed_events`；
`_rebuild_personalized_models` 又从 `_observed_events` 重建 `_committed_events`，
且只对 `restored_derived_ids` 这一小类重新绑定快照。

**合同依据**：这是类内不变量，不是新机制。
`_process_transition` 在每次转移后建立该不变量，`_validate_feedback_revision_binding`
依赖该不变量（它甚至为已不在 committed 中的修订保留了 `_revision_feedback_bindings` 归档回退，
说明「已提交的修订应当持续可被反馈寻址」就是设计意图）。重建路径丢掉了它。

**最小修复**：在 `_rebuild_personalized_models` 发布快照之后，对所有缺失 `belief_snapshot_id`
的 committed 事件执行与 `_process_transition` 完全相同的重绑定，并同步 `_revision_feedback_bindings`
与 `_derived_event_archive`。不改变任何统计量、不改变提交判据、不授权任何写入。

**修改前失败 / 修改后通过**：修复前第二次撤回抛
`ValueError: feedback revision has no committed snapshot binding`；修复后连续 6 次撤回全部成功，
且每步独立对账通过。

### 3.5 应当改变动作的场景与对照

两者都用默认 `HYBRID_ALPHA` 读出（`hybrid_alpha` 权重 1.0，即 RGRC 拥有的长期质量）。

| 场景 | 合同预期 | 实测 |
|---|---|---|
| 对多数位置连续投入合法迟到反证，直到其质量低于次席 | 解码 top-1 应当改变 | 第 6 次撤回后 top-1 由 `44b33099` 切换到 `a5a97d44`，且此时 `alpha(44b33099) < alpha(a5a97d44)` |
| 对**次席**位置投入一次同样的迟到反证 | 解码 top-1 不应改变 | 分布改变、top-1 保持 `44b33099` |

对照组说明「动作分布改变」与「解码动作改变」是两件事，正是独立复核在 S8 上指出的区分。

### 3.6 重复 / 乱序 / 陈旧 / 部分失败

| 用例 | 结果 |
|---|---|
| 同一反馈记录重复提交 | 第二次返回 `QUARANTINE` 且 rationale 含 `idempotent`；11 项语义状态完全不变 |
| 新记录引用已撤回的修订（乱序到达） | `KeyError: superseded revision is not a committed prototype event`；11 项语义状态完全不变 |
| 新记录携带被取代的旧快照 | `ValueError: feedback revision snapshot does not match the committed event`；语义状态不变 |
| 事务中途故障（`_revision_fault_hook("dirichlet")`，模块自带的空操作故障注入接缝） | 抛出后 11 项语义状态完全复原；随后同一反馈仍可正常应用并通过对账 |

**关于回滚见证的修正**：回滚后 `_execution_observable_state_sha256` 仍会不同，
但逐属性比较显示差异只在 `_corrector` / `_habit` / `_regimes` / `_automatic_regimes`
四个**对象身份**上（恢复安装的是深拷贝），所有数值与集合完全一致。
这与第一轮 G6 一致：该哈希不是语义等价见证，本轮因此改用 11 项语义量作为见证。

## 4. R4：重建后的七算子因果证据表

### 4.1 干预设计原则

每个算子一次**受控干预**加一次**空对照**，固定 seed、固定输入、确定性场景生成器。
干预一律作用于该算子的**真实算法输入**或合法执行路径；
不替换哈希、不手写回执、不停用任何算子，因此这些都**不是**七算子消融。
`docs/reviews/data/.../counterexamples.py` 的 CIAV 局部干预结论予以保留，但只作为 CIAV 一栏的证据。

### 4.2 证据表

`runtime`＝是否运行在同一生产系统；`binding`＝绑定方式（**不等于算法等价**）；
`handoff`＝该算子自身回执输出随其输入改变；`numeric`＝下游数值状态改变；
`dist`＝读出分布改变；`decoded`＝解码 PUT_BACK top-1 改变；
`equiv`＝算法语义等价（由公式/更新规则/不变量测试支持）；`benefit`＝任务收益。

| 算子 | runtime | binding | handoff | numeric | dist | decoded | equiv | benefit |
|---|---|---|---|---|---|---|---|---|
| OPCEU | pass | `direct_operator_callable` | pass | pass | pass | **pass** | **pass**：`applied_weight == 1/(p_select·p_visible·p_detect)` 精确成立 | not_covered |
| ORRER_CHEH | pass（仅 `core._event_engine`；第二个声明实例见 G2） | `direct_operator_callable` | pass | pass | pass | **not_covered**（覆盖区间内触发条件未满足） | partial：开放人物/未决支持保持、归一化、修订链父绑定等不变量通过；分支/修订核的完整等价未证 | not_covered |
| PCHMP | pass | `direct_operator_callable` | pass | pass | pass | **pass** | partial：后验归一化、冻结 actor 支持、证据集合置换语义不变（至 1e-9）通过；完整来源约束消息传递等价未证 | not_covered |
| CF-BOCPD | pass | `direct_operator_callable` | pass | pass | not_covered | not_covered | partial：原因后验归一化、变点概率在 [0,1]、对真实信号突变单调上升、常量序列保持低位 | not_covered |
| CCRR | pass | `composite_operator_stage` | pass | pass | pass | **not_covered**（触发条件未满足） | partial：确认窗口单调性（更宽窗口不会产生更少的隔离）通过；身份轴输入恒为 0.0（G4） | not_covered |
| RGRC | pass | `enclosing_runtime_stage`（无独立 callable） | pass | pass | pass | **pass**（经 §3.5 的迟到反证链） | partial：`hybrid_alpha == Σ 幸存 committed 的 statistical_owner_weight` 精确成立、append-only 重放等价、隔离门空对照通过 | not_covered |
| CIAV | pass | `adaptive_composite_stage` | pass | pass | pass | **pass**（owner-likelihood 0.95→0.05 改变解码选择） | partial：局部后验为先验×似然的精确贝叶斯更新（§6）；规划器效用/信息项等价未证 | not_covered |

**空对照**（都必须不改变结果，全部通过）：
OPCEU 改 `context_key`（它从不读取）；ORRER 同输入重跑；PCHMP 置换同一证据集合；
CF-BOCPD 常量帧序列；CCRR 同一 `confirmation_window` 重跑；
RGRC 自适应主通道（必须 0 提交）；CIAV 隐私预算阻断（`should_act=False`）。

### 4.3 三点必须写清的边界

1. **`binding` 不是 `equiv`。** 第一轮把「直接/复合/外层绑定」列成「算法实现等价」是错的。
   直接绑定只证明实现身份；RGRC 没有独立 callable 也不等于算法不等价。
   本表把两者拆成两列，`equiv` 一律由公式或不变量测试支撑，其余写 `partial`，并说明未证部分。
2. **`decoded` 与 `dist` 是两件事。** ORRER 与 CCRR 的干预确实改变了读出分布，
   但在覆盖的场景/horizon 内没有改变解码 top-1。这被如实记为 `not_covered`，
   没有为了凑一个变化而挑选场景。
3. **`benefit` 全列 `not_covered`。** 本窗口无权、也没有运行任何效用比较。

### 4.4 PCHMP 的一项实测性质

同一证据集合的**置换**不会改变决策，但不是逐比特不变：
每位置 Hybrid 质量与解码选择一致到 1e-9，而浮点重结合会让
`action_distribution_sha256` 不同。这是本实现的实测性质，如实记录，
也是该空对照断言数值而非哈希的原因。

## 5. R6：CIAV 负观测的四层分解与回执修正

### 5.1 四层分别成立与否

| 层 | 问题 | 负观测下的实测 |
|---|---|---|
| 1 局部后验 | 真的做了贝叶斯更新吗 | **是**。`posterior = normalize(prior × likelihood)` 精确成立；owner 由 `0.8055113493592428` 变为 `0.970703272855737`。第一轮「局部似然完全没被消费」的说法**撤回** |
| 2 持久化目标 | 回执记录的目标是真实写入位置吗 | **修改前不是**。三种结局都记成 `fast-action-owner-posterior:{update_id}`，而该存储只由 `apply_fast_action_verification` 写，只发生在同位置分支。**已修正** |
| 3 快记忆/修订更新 | 有没有真实写入 | **没有**（负观测与异位置分支都没有 `fast_verification_receipt`；只有同位置分支有） |
| 4 动作消费 | 解码动作变了吗 | **没有**。与「CIAV 动作被隐私硬约束直接阻断」的参照运行相比，动作分布逐位相同 |

层 3、4 的缺失**不是**违反合同：冻结协议的 `claim_boundary` 明确写着
「a negative CIAV observation does not yet enter a complete downstream closure」。
因此本轮按用户规则的第二种情形处理——**修正回执语义并补不变量测试**，不发明下游写入。

### 5.2 已实施的回执修正

`src/cpswm/world_model/grounded_search/ciav_opceu_loop.py`：
`target_distribution_id` 由 `fast-action-owner-posterior:{update_id}`
改为 `ciav-local-actor-posterior:{update_id}`，即该循环**自己真正写出的**分布
（就是 `CIAVOPCEUReceipt.evidence.actor_posterior`）。
`consumed_as_likelihood=True` 保留，因为似然确实被消费进了这个局部后验。
`derive` 的 `POSTERIOR_SUMMARY` 目标同步更新。全仓不再有任何
`fast-action-owner-posterior` 引用。

### 5.3 三条必须保护的性质（均已测试）

| 性质 | 冻结条款 | 实测 |
|---|---|---|
| 未执行的动作不得被编码成负观测 | `unexecuted_inference_may_not_be_encoded_as_negative_evidence` | 隐私阻断时 `should_act=False`，**证据因子 trace 为空**（0 条因子），无检测记录、无证据记录，七条回执中 CIAV 仍为 executed 的规划回执 |
| 一次真实证据不得在直接执行/反馈/重放中重复计入 | `atomic_evidence_bundle_commit_or_retract` | direct P5 与 `P0→debt replay` 的 CIAV 后验、committed 数、逐位置 `hybrid_alpha`、动作分布全部相等；重复执行同一 CIAV 调用因幂等键不产生第二条因子 |
| 负观测不得被升格为正事件或长期提交 | `maximum_unresolved_as_negative_events=0`、`maximum_unauthorized_long_term_commits=0` | `detected_location_id / detected_object_instance_id / detection_time` 均为 None，`location_posterior["unknown_location"] == 1.0`，无反馈闭包，无提交，所有位置 `hybrid_alpha == 0` |

## 6. R5：留存产物失效状态的四态重新登记

**撤回第一轮的说法**：「文件未触碰，所以历史产物未失效」。未改文件字节不代表产物仍绑定当前代码。

方法：产物字节一律取自本分支（未改动），只变化被验证的**源码树**，
分别调用各自的正式验证器并强制 `fresh_recompute=True`。不手改任何历史哈希。

### 6.1 结果

| 产物 | 文件是否保持历史原样 | 对其产出提交有效 | 对窗口三起点 `09eb4d4` 有效 | 对本轮 HEAD 有效 |
|---|---|---|---|---|
| `benchmarks/structure_two/structure_two_p5_direct_trace_probe_v0_1.json` | **是**（与 `09eb4d4` 及本分支逐字节相同） | **无法验证**：产出提交 `749afaf` 的源码树本身不可导入 | **否**：`direct P5 trace probe source binding mismatch` | **否**：同一错误 |
| `benchmarks/structure_two/structure_two_p5_debt_replay_confirmation_v0_1.json` | **是** | **是**：在 `4103bea` 上 `fresh_recompute=True` 通过 | **否**：`P5 debt-replay result identity, hash, or binding drifted` | **否**：同一错误 |

### 6.2 失效归因（逐字段）

**direct trace probe**：`source_binding` 六个字段中**只有一个**不匹配——
`production_system_module_sha256`。

```text
产物记录值                     73485a03a94f1f81c3d8b5d37a67117e51e34dcf8f9eb50f7bd55f8b1721b2b7
4103bea 实测                   306b72ae2223b03bcc609691afa67aa5fd284f728c49cade1e292b6491ba22c5   不匹配
09eb4d4 实测（窗口三起点）      306b72ae2223b03bcc609691afa67aa5fd284f728c49cade1e292b6491ba22c5   不匹配
本轮 HEAD 实测                 8e148fe5d9fe8adf0293ddafe8080426f9328e47fc287d8019fe688414e67afe   不匹配
```

其余五个（configuration、decision_record、probe_module、decoder_module、adaptive_runtime_module）
在三个源码树上**全部匹配**。

归因：**起点已有漂移**。该产物在窗口三开始之前就已失效，且其记录值不等于任何被检查提交的实测值；
结合「产出提交 `749afaf` 的树不可导入」（`prototype_spine.py` 导入 `RegimeStage`，
而该提交的 `project_one_regime_loop.py` 未定义它），最合理的解释是该产物由一棵**未提交的工作树**产生。
窗口三的改动会让 live 值再次变化，但**不是**失效原因。

**debt replay confirmation**：其 `source_binding` 含
`production_assembly_manifest_sha256`，而 `build_production_assembly_manifest`
对 `src/cpswm` 下**每一个** `.py` 取哈希。因此 src 的任何改动都会使其失效。
它在 `4103bea` 上有效、在 `09eb4d4` 上已失效 → 漂移由 `4103bea..09eb4d4` 之间的提交引入
（`09eb4d4` 本身修改了 `src/.../structure_two_p5_three_arm_death_test.py`）。
**同样是起点已有漂移，不是窗口三新增。** 窗口三的改动是**第二个**独立失效原因。

### 6.3 本轮未做

- 未生成新版本的 direct-probe / debt-replay 产物：它们的绑定覆盖整棵 `src/cpswm`，
  而窗口一的证据治理工作尚在进行，现在生成只会立刻再次失效。
- 未覆盖、未手改任何历史产物；两份旧产物的真实失败状态原样保留。
- 未核对全仓其他留存产物——本节只覆盖上表两份，其余标为**未覆盖**。

## 7. 未解决的缺口与需要用户决定的事项

### G8（本轮新增，需要用户决定）一次正式修订会提交全部被写入阻断的隔离期观测

**当前行为**（10 天自适应 direct-P5 历史，实测）：
执行前 committed=3、quarantined=17；一次正式 `process_execution_feedback` 撤回之后
committed=18、quarantined=0，新增的 16 条**全部**来自此前的隔离集合。

**机制**：每条自适应主通道都以 `force_long_term_write_blocked=True` 运行，
P0 的 RGRC 守卫也报告 `long_term_write_authorized: False`；但
`apply_event_revision_outcome` 末尾调用 `_rebuild_personalized_models`，
其 `_recompute_active_regime` 会对整条观测日志重新分类，从而提交它们。

**合同两面**：
- 支持「这是违规」：`maximum_unauthorized_long_term_commits=0`、
  `router_may_grant_long_term_write=false`、`rgrc_remains_only_long_term_write_authority=true`、
  P0 的 deferral 语义；
- 支持「这是合规」：`ccrr_promotion_required_before_eligible_write=true` ——
  重建过程确实重放了 CCRR 才决定提交集合。

**这属于长期提交判据，本轮不自行选路。** 需要用户决定：

1. 重建是否可以提交「自适应车道曾阻断写入」的观测？（选项：不可以，须保留阻断标记；
   可以，但须在回执中登记为 rebuild-promoted；可以，无须登记）
2. 若不可以，是否为 `_CommittedPrototypeEvent` 增加 `long_term_write_blocked_at_origin` 来源标记，
   并让 `_rebuild_personalized_models` 排除它们？（会改变状态哈希与既有产物）
3. 该判据与 G1（同位置/负观测长期巩固不可达）是否应一并冻结？

现状已由 `test_one_formal_revision_promotes_every_write_blocked_quarantined_observation`
特征化钉死，不会被悄悄改变。

### G9（本轮新增，功能仍缺失）仓库内没有内置的校准撤回/纠正策略

`DefaultPrototypeFeedbackPolicy` 只会 `REINFORCE` 或 `QUARANTINE`，从不 `RETRACT`/`CORRECT`。
`process_execution_feedback` 的 `policy=` 接缝是公开的，但生产侧没有任何已冻结的校准策略实现，
`ProjectTwoFeedbackRevisionLoop` 的阈值也没有被任何生产入口使用。
因此「生产系统能自主对迟到反证作出撤回决定」目前**不成立**；本轮的撤回链是由调用方提供策略驱动的。
需要用户决定：撤回/纠正的校准判据由谁冻结、放在哪一层。

### 继续保持的缺口（第一轮结论，本轮未扩大也未缩小）

- **G1** 自适应车道的长期巩固只经异位置 CIAV 闭包可达（同位置与负观测在 14 步内 0 提交 / 14 隔离；legacy 对照 ≥12 提交）。**需要用户决定。**
- **G2** `feedback_revision_loop` 被声明为 ORRER_CHEH 的第二个运行时实例，但所检查的 P0 / direct / replay 入口都不调用它，且它自建了与 `core._event_engine`、`core._message_passing` 不同的实例。**功能仍缺失。** 范围限于所检查入口，不外推到所有公开 API。
- **G4** CCRR 的 `identity_switch_probability` 在生产路径上恒为 `0.0`。**功能仍缺失。**
- **G5** 完整粒子主干、神经摊销提议器、条件化 Rao–Blackwellized 统计块**不在生产主干上**；evaluator-local 的证伪器实现与 `StructureTwoProductionSystem` 无调用关系。既有原型类存在不等于生产已接入。**保留在架构映射与缺口表中，不删除。**
- **G6** `_execution_observable_state_sha256` 不可跨运行重算（`uuid4` 记录 id），本轮回滚测试再次佐证：语义完全复原而该哈希仍不同。**需要用户决定。**
- **G7** `_execution_callable_bindings` 对多于预期的声明实例不做身份核验（与 G2 同源）。**功能仍缺失。**

## 8. 验证：原生环境实跑结果

环境：`/Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/.venv/bin/python`
（Python 3.13.5、numpy 2.5.2、cryptography 47.0.0、pytest 9.1.1、scikit-learn 1.9.0）。
工作树：`/private/tmp/s2-w3-native`（本分支的独立 worktree）。
**未使用任何语法降级导入、未弱化断言、未跳过关键路径。**

| 批次 | 命令覆盖 | 结果 |
|---|---|---|
| 本轮新增四个测试文件 | counterexample regressions、late counter-evidence chain、operator causal matrix、CIAV negative layers | **64 passed** |
| 独立复核指定的 150 项集合 | 第一轮新增 + 八个相关回归文件 | **150 passed** |
| 反馈/CIAV/证据轨迹邻域 + 两个源码绑定门 | 9 个文件 | 167 passed、4 failed、9 errors |

第三批的 4 failed + 9 errors 全部落在
`tests/test_structure_two_runtime_identity_gate.py` 与
`tests/test_structure_two_adaptive_compute_predeath.py`。
**差分归因（同一原生环境、同一完整检出、同一命令）：**

```text
窗口三起点 09eb4d4 : 10 个不同的失败/错误 id
本轮 HEAD          : 10 个不同的失败/错误 id
仅在 HEAD 出现（新增回归）: 空
仅在起点出现（被修好）    : 空
```

即**零新增失败**。这两个文件校验的是留存 readiness 产物对活源码的绑定，
在共同起点上就已经不成立——与 §6 的产物失效结论一致。

独立反例脚本在修复后的行为见 §2.3（P0 段现在按合同拒绝）。

## 9. 复现命令

```bash
# 1) 取得分支与独立工作树
cd /Users/pangwei/Documents/ai/continual-personalized-semantic-world-model
git worktree add /private/tmp/s2-w3-native codex/s2-backbone-operators-w3
V=/Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/.venv/bin/python

# 2) 本轮新增的四个测试文件
cd /private/tmp/s2-w3-native
PYTHONPATH=src $V -m pytest -o addopts='' -q -p no:cacheprovider \
  tests/test_structure_two_backbone_counterexample_regressions.py \
  tests/test_structure_two_late_counter_evidence_chain.py \
  tests/test_structure_two_operator_causal_matrix.py \
  tests/test_structure_two_ciav_negative_observation_layers.py

# 3) 独立复核指定的 150 项集合
PYTHONPATH=src $V -m pytest -o addopts='' -q -p no:cacheprovider \
  tests/test_structure_two_backbone_operator_wiring.py \
  tests/test_core_prototype_spine.py \
  tests/test_structure_two_production_system.py \
  tests/test_structure_two_execution_interface.py \
  tests/test_structure_two_adaptive_runtime.py \
  tests/test_structure_two_adaptive_runtime_adversarial_round1.py \
  tests/test_structure_two_adaptive_runtime_adversarial_round2.py \
  tests/test_structure_two_p5_direct_trace_probe.py \
  tests/test_structure_two_p5_debt_replay_confirmation.py

# 4) 源码绑定门的差分归因（起点 vs HEAD，应得到相同的失败集合）
git worktree add --detach /private/tmp/s2-w3-src-09eb4d4 09eb4d48e1c11082e90ca18332d04333e6b5b47a
for d in /private/tmp/s2-w3-src-09eb4d4 /private/tmp/s2-w3-native; do
  (cd $d && PYTHONPATH=src $V -m pytest -o addopts='' -q -p no:cacheprovider -rfE \
     tests/test_structure_two_runtime_identity_gate.py \
     tests/test_structure_two_adaptive_compute_predeath.py)
done

# 5) 独立反例脚本（P0 段现在按合同拒绝）
$V docs/reviews/data/structure_two_windows2_3_adversarial_review_2026-09-11/counterexamples.py \
   /private/tmp/s2-w3-native w3
```

留存产物的四态复核脚本与日志保存在 `/private/tmp/s2-w3-artifacts/`
（`check.py` / `detail.py` / `all.log` / `detail.log`）。该目录是临时目录，
§6 的表格与逐字段哈希已完整抄录在本报告内，不依赖它继续存在。

## 10. 交给窗口一的失效登记与重算清单

### 10.1 本轮的源码变更

| 文件 | 变更性质 |
|---|---|
| `src/cpswm/system/structure_two_execution.py` | 新增 `AdaptiveMaintenanceContractError`（契约异常类型） |
| `src/cpswm/system/prototype_spine.py` | 新增 `_require_maintenance_payload`；`_adaptive_ccrr_safety_maintenance` / `_adaptive_rgrc_debt_guard` 增加合同检查与 `maintenance_kind`；`_adaptive_pchmp_safety_maintenance` / `_adaptive_cf_bocpd_safety_maintenance` 增加 `maintenance_kind`；`_rebuild_personalized_models` 补回快照重绑定 |
| `src/cpswm/system/structure_two_production_system.py` | （第一轮）P0 维护调用按冻结图传递上游输出并记录消费哈希 |
| `src/cpswm/world_model/grounded_search/ciav_opceu_loop.py` | `target_distribution_id` 改为 `ciav-local-actor-posterior:*` |

`src/cpswm` 的**文件清单未改变**（探针 harness 与全部新测试都在 `tests/` 下），
因此 `transitive_source_paths` 的条目集合不变，只有上述四个文件的 sha256 需要重算。

### 10.2 需要在最终源码版本上统一重算的项

| 项 | 原因 |
|---|---|
| 任何含 `P0_SAFE_DEFERRED` 执行 trace 的回执/报告 | 四个维护节点的返回体与 raw_input 均已改变 |
| `build_production_assembly_manifest` 的 `transitive_source_rows`（上述四文件行）及其派生 manifest 哈希 | 文件内容改变 |
| 绑定 `implementation_source_sha256` / `loaded_callable_code_sha256` 到上述文件的任何 `RuntimeCallableBinding` 快照 | 同上 |
| `benchmarks/structure_two/structure_two_p5_direct_trace_probe_v0_1.json` | 起点已失效（`production_system_module_sha256`）；本轮再次改变该文件 |
| `benchmarks/structure_two/structure_two_p5_debt_replay_confirmation_v0_1.json` | 起点已失效（whole-`src` manifest）；本轮再次改变 `src` |
| 任何含 CIAV 证据因子 trace 的产物 | `target_distribution_id` 语义修正 |
| `tests/test_structure_two_runtime_identity_gate.py` 与 `tests/test_structure_two_adaptive_compute_predeath.py` 依赖的 readiness 产物 | 起点已失效，本轮未修复也未覆盖 |

### 10.3 交接原则

- **不要**手改任何历史哈希使其通过；
- **不要**把不同提交的绿色结果拼成一个系统通过结论；
- 旧产物的真实失败状态原样保留，本轮没有覆盖任何历史产物；
- 待窗口一完成、最终源码版本确定后，由证据链工作在同一版本上统一重算并重新签发。

## 10.4 本轮提交

| 项 | 值 |
|---|---|
| 分支 | `codex/s2-backbone-operators-w3` |
| 本轮提交 | `77724e81fb58d72ae6b009c4958948bc7fe87096` |
| 本轮起点 | `d6db421d33b6499ca7dfbead3d4ecb543a371970` |
| 共同起点 | `09eb4d48e1c11082e90ca18332d04333e6b5b47a` |
| 变更规模 | 11 个文件，+2540 / -46 |
| 生产源码变更 | `prototype_spine.py`、`structure_two_execution.py`、`ciav_opceu_loop.py`（`structure_two_production_system.py` 为第一轮变更，本轮未再改） |
| 新增测试 | 4 个文件，64 项 |
| 工作方式 | macOS 原生独立 worktree `/private/tmp/s2-w3-native`；用户主工作区未改动 |

## 11. 本报告不授权的事项

- 不签发 `TrustedSevenOperatorAblationAuthorization`，不运行七算子消融，不训练路由器；
- 不把任何 `pass` 解释为 Task 7/8/9、Gate B、P5 死亡测试或 adaptive readiness 通过；
- 不宣称主干与七算子「已正常协作」：G1、G2、G4、G5、G7、G8、G9 仍未关闭；
- 不宣称科学优越性、长期效用或审计穷尽；
- 不选择粒子预算、重采样策略、回春核、梯度策略、consolidation thresholds、
  CIAV action budget、长期提交判据或任何路由特征公式；
- 不缩小结构二的研究范围：H/R/I/C/Z/r/V 七轴、三个 RB 统计块、七算子、
  隐藏事件、多人、开放世界未知、可逆归因与具身反馈全部保留在架构映射与缺口表中。
