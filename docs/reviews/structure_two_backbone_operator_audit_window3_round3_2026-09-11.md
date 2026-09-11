# 结构二窗口三第三轮修复报告（2026-09-11）

分支：`codex/s2-backbone-operators-w3`
本轮起点 / 已审核提交：`d17e88af2c625a62cea95a86482d6dbffdbfff03`
共同起点：`09eb4d48e1c11082e90ca18332d04333e6b5b47a`
工作树：`/private/tmp/s2-w3-native`（原生 macOS 独立 worktree；用户主工作区未改动）
解释器：`/Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/.venv/bin/python`
（Python 3.13.5、numpy 2.5.2、cryptography 47.0.0、pytest 9.1.1、scikit-learn 1.9.0）

**未使用语法降级导入替换，未弱化任何断言，未跳过关键路径。**
本报告全部是工程证据。**不构成任何科学门结论**，不授权消融或路由器训练。

---

## 0. 逐项交付状态总表

| 项 | 状态 | 依据位置 |
|---|---|---|
| R2-1 四种完整错误载荷 | **已修复并验证** | §1.1，`w3_round3_results.json:r2_maintenance.cases` |
| R2-2 不同运行实例相同头部的载荷替换 | **已修复并验证** | §1.1，`…:r2_maintenance.different_runtime_same_head` |
| R2-3 类型/内容/来源与本次调用的关系 | **已修复并验证** | §1.2 |
| R2-4 正式 P0 入口故障注入 | **已修复并验证** | §1.3（三级阶梯），`…:r2_injected_p0_*` |
| R2-5 合法 P0 正路径与零长期提交保护 | **已修复并验证** | §1.4，`…:r2_legal_p0` |
| R2-6 失败事务无成功残留 | **已修复并验证** | §1.5 |
| R2-7 未以强跑七算子掩盖合同问题 | **已修复并验证** | §1.4 |
| R2-附 绑定层可被外来 callable 冒名 | **部分修复 + 需要用户决定** | §1.6、§6 决策项 2 |
| R3-1 两种撤回目标的复现 | **已修复并验证** | §2.1（两组数字都在同一源码上复现） |
| R3-2 原始写入资格 / 隔离原因 / 后续授权 / 谱系 | **已修复并验证** | §2.2 |
| R3-3 重建路径不得绕开授权 | **已修复并验证**（硬安全部分） | §2.3 |
| R3-4 未用永久禁止提升等手段"修复" | **已修复并验证** | §2.4 |
| R3-5 合同允许的提升按合同实现并记录 | **已修复并验证**（记录）+ **需要用户决定**（判据） | §2.4、§6 决策项 1 |
| R3-7 pending-debt 阻断正反对照 | **已修复并验证** | §2.5 |
| R3-III-1 删除恒真断言 | **已修复并验证** | §3.1 |
| R3-III-2 事先保存的独立参考 | **已修复并验证**（有明确边界） | §3.2 |
| R3-III-3 十三项量分别核对 | **已修复并验证** | §3.3 |
| R3-III-4 撤回/重复/乱序/已撤回/回滚/重试覆盖 | **已修复并验证** | §3.4 |
| R3-III-5 迟到反馈时序复现 | **已修复并验证** | §3.5 |
| R3-III-6 按合同恢复历史绑定的可验证处理 | **已修复并验证** + **需要用户决定**（过期策略） | §3.5、§6 决策项 4 |
| R4-1 legacy 结果不与另一路径拼接 | **仅纠正声明 + 新增证据** | §4.1 |
| R4-2 正式 direct-P5 / debt-replay 覆盖矩阵 | **已修复并验证**（部分格未覆盖） | §4.2 |
| R4-3 真实算法输入干预 | **已修复并验证** | §4.2 |
| R4-4 CF→CIAV 实际对象/内容与干预传播 | **已修复并验证** | §4.3 |
| R4-5 真实调用次数 | **已修复并验证** | §4.1 |
| R4-6 应变 / 应不变 / 无法触发的格 | **已修复并验证** | §4.2 |
| R4-7 七类证据分别报告 | **已修复并验证** | §4 全节 |
| R4-8 不把调用方策略说成系统自主撤回 | **仅纠正声明** | §4.4 |
| R5 回归与新鲜证据 | **已修复并验证** | §5 |
| G1/G2/G4/G5/G6/G7/G9 | **功能仍缺失**（保持开启） | §7 |

---

## 1. R2：延期路径维护依赖

### 1.1 复现：审核提出的五个反例，现在全部被拒

同一份独立脚本逻辑，跑在本轮源码上（原生环境）：

| 反例 | 上轮结果 | 本轮结果 |
|---|---|---|
| `evidence_content_sha256s` = 错误哈希集合 | accepted，`semantic_guard_unchanged: true` | **拒绝**：`rgrc maintenance dependency binds evidence from another transition` |
| `evidence_content_sha256s` = 整数 `-999` | accepted | **拒绝**：`… field evidence_content_sha256s is not a content-hash tuple` |
| `consumed_cf_bocpd_maintenance_sha256` = 错误哈希 | accepted | **拒绝**：`rgrc declared consumption of a ccrr output this execution never produced` |
| `consumed_cf_bocpd_maintenance_sha256` = `None` | accepted | **拒绝**：`… field consumed_cf_bocpd_maintenance_sha256 is not a content hash` |
| 两个不同运行实例、相同观测数与空快照 | `different_runtime_same_head_accepted: true` | **拒绝**：`ccrr maintenance dependency came from a foreign runtime execution`（且记录 `semantic_heads_identical: true`，证明两个头部确实逐字段一致） |

第三行的拒绝措辞与反例脚本原本预期的字段级错误不同，这里如实记录实际发生的事：
`consumed_cf_bocpd_maintenance_sha256` 是内容绑定的 CCRR 载荷的一部分，改写它会
先一步被"这不是本次执行产出的 CCRR 载荷"挡下。这比字段级拒绝更强，但不应写成
字段级检查生效。

### 1.2 修复内容

`CorePrototypeSpine` 新增执行域可信上下文 `_AdaptiveMaintenanceContext`：

- `bind_adaptive_maintenance_context(...)` 由 `_execute_p0_safe_deferred` 在维护循环前打开，
  取值全部来自运行时本身——`recorder.runtime_execution_id`、本次真实 `transition` 的证据哈希、
  真实债务凭证的 `certificate_sha256` 与 `origin_transition_sha256`、活的 message-passing 运行时类型；
- 每个维护节点用 `context.record_output(...)` 把自己真实产出的载荷登记进上下文；
- 下游用 `context.require_produced(...)` 对照**上下文自己的记录**核验声明的消费，
  而不是对照载荷自报的哈希；
- 载荷额外打上 `runtime_execution_id` + `maintenance_epoch`，
  `epoch` 单调递增，使同一运行时上一次执行的陈旧载荷也无法重放；
- RGRC 回执体里的 `origin_transition_sha256` / `debt_certificate_sha256` 改为取自上下文，
  不再由调用方传入。

检查顺序是刻意安排的：**先形状 → 再语义 → 最后执行身份**。
这样上一轮的语义反例矩阵仍然逐条产生它原来的错误信息，没有被身份检查掩盖成
一句笼统的"来源不符"。

冻结依据：`hard_safety_kernel.provenance_and_dependency_checks_always_executed = true`
对所有 legal path 成立；一个拿被检对象自己的自报值当参照的检查不是检查。

### 1.3 正式 P0 入口的故障注入（三级阶梯）

`tests/test_structure_two_p0_maintenance_fault_injection.py`，全部经
`process_adaptive_transition` 正式入口：

| 级别 | 注入 | 结果 | 残留 |
|---|---|---|---|
| 绑定层 | 审核脚本原样的外来模块函数 | `ValueError: bound production callable does not belong to the bound implementation type: pchmp._adaptive_pchmp_safety_maintenance` | 无 trace、0 pending debt、committed 不变、上下文已关闭 |
| 上下文层（刻意关掉绑定层） | 同上，无执行印记 | `rgrc maintenance dependency field set drifted from the frozen shape` | 同上 |
| 上下文层 | 抄走本次真实印记，但证据来自别的 transition | `rgrc maintenance dependency binds evidence from another transition` | 同上 |
| 上下文层 | 与正确载荷逐字节相同，只是运行时从未登记它跑过 | `rgrc declared consumption of pchmp before it ran in this execution` | 同上 |

最后一级是这次修复的核心性质：**载荷不能给自己签名**。
上轮该注入得到 `verified_operator_rows: 7` 和一条 pending debt。

### 1.4 合法正路径与零长期提交保护未被破坏

`r2_legal_p0`：`P0_SAFE_DEFERRED`，7 行回执，
executed = `{opceu, pchmp, cf_bocpd, ccrr, rgrc}`，deferred = `{orrer_cheh, ciav}`，
pending debt = 1，committed = 0。

**没有**为了让故障注入"好看"而强行让 P0 跑满七个推断算子。
P0 的语义仍然是 `legal_paths.P0_SAFE_DEFERRED.semantic_purpose` 写的
"运行强制的语义与写安全维护，并在明示推断债务下延期昂贵的精化"。
测试 `test_the_frozen_clauses_this_file_depends_on_are_unchanged` 直接断言该字段
与 `operator_modes` 仍是冻结值。

### 1.5 失败事务无可被读为成功的残留

每个拒绝用例都断言十二项残留量完全不变（observable state、Dirichlet 规范哈希、
committed / quarantined / observed 计数、fast action events、active regime、
动作分布、pending debts、债务账本条数、action-scoped negatives、反馈绑定数），
外加 `sink.trace is None` 与 `_adaptive_maintenance_context is None`。
另有 `test_a_legal_p0_run_still_succeeds_after_a_refused_one` 钉住可恢复性：
fail-closed 不等于把运行时锁死。

### 1.6 顺带发现：绑定层可以被外来 callable 冒名（部分修复）

`bind_runtime_callable` 原本只核对"callable 与**它自己所在的**源文件一致"。
任何其他模块里的函数都天然满足，于是审核脚本的注入被冒名登记在
`CorePrototypeSpine` 的实现符号下，还产生了七行"已验证"回执。

本轮新增 `_require_declared_implementation_member`，要求被绑 callable 必须是实现类型
MRO 自己声明的成员，且其 `__module__` / `__qualname__` 与该声明类一致。
**但它是 opt-in 的**，目前只用在自适应延期路径的四个维护节点上
（`require_declared_member=True`）。
原因如实写明：把它推广到所有绑定会同时拒绝本仓库既有的实例级回执插桩测试
（`test_receipts_hash_the_actual_bound_callable_inputs_and_outputs`、
`test_operator_keyboard_interrupt_rolls_back_without_attempting_sink_commit`）。
这属于**需要用户决定**，见 §6 决策项 2。**其余算子与 legacy 车道的同类替换仍未覆盖。**

---

## 2. R3：撤回触发的大范围隔离提升

### 2.1 两种撤回目标，在同一份源码上复现前后对比

修复只有一个闸门：`_observation_write_eligible`。把**且仅把**这个闸门中性化，
就在本轮源码上精确复现了两份已发布的数字；这样"修复前"与"修复后"是同一棵树上的可比测量，
而不是引自两棵不同的树。

| 目标 | 修复前 committed | 修复前新增 | 其中原写入被阻断 | 修复后 committed | 修复后新增 | 其中原写入被阻断 |
|---|---|---|---|---|---|---|
| 第一个 committed（独立审核） | 3 → **19** | **+17** | 10 | 3 → **4** | **+2** | **0** |
| 多数位置（窗口三报告） | 3 → **18** | **+16** | 10 | 3 → **2** | **+0** | **0** |

两种目标下 `quarantined` 都从 `17 → 0`（修复前）变成 `17 → 10`（修复后）：
10 条原写入被阻断的观测**被扣留而不是被删除**，隔离历史保留。
`hybrid_internal_rerun_equivalent` 两种情况都仍为 `true`——这正说明内部重放一致
从来不能证明提升被授权过，与审核的判断一致。

### 2.2 每条观测的原始写入资格、隔离原因、后续授权与谱系

新增 `_ObservationWriteEligibility` / `_WriteAuthorization`，在 `_process_transition`
里于任何分类之前登记：

| 起源 | `origin_path` | `quarantine_reason` | 写入资格 |
|---|---|---|---|
| 自适应主通道（`force_long_term_write_blocked=True`） | `write_blocked_primary_pass` | `long_term_write_administratively_blocked` | **否**，除非有记录在案的后续授权 |
| 未阻断通道 + CCRR 证据不足 | `unblocked_transition` | `ccrr_insufficient_evidence_deferred` | 是 |
| 未阻断通道 + 已提交 | `unblocked_transition` | — | 是 |

十天自适应历史的实测构成：10 条 `write_blocked_primary_pass` + 7 条
`unblocked_transition / ccrr_insufficient_evidence_deferred` + 3 条已提交，共 20 条。

授权只由**本身被允许写入的执行**签发，并记录 `authority`、签发执行的 revision、
签发时的观测数、以及基于内容哈希的 `basis_sha256`：

- `ccrr_habit_change_promotion`：未阻断执行中 CCRR 判定 `HABIT_CHANGE` 时对隔离集的提升；
- `unblocked_transition_commit`：未阻断执行提交当前事件；
- `ccrr_rebuild_replay_promotion`：重建重放的提升（**只登记依据，不创造资格**——
  资格检查在它之前，被扣留的事件根本走不到这一步）。

只读审计视图：`core.observation_write_eligibility(revision_id)`。

### 2.3 重建路径的修复

`_recompute_active_regime` 的 `commit_for_replay` 现在先查写入资格；
不合格的进入 `withheld_revision_ids`，既**不**进 committed 集合，
也**不**把统计量喂进 `replay_habit` / `replay_regimes`，并被并入返回的隔离列表。

冻结依据：`router_may_grant_long_term_write = false` 与
`maximum_unauthorized_long_term_commits = 0`。路由器的选路不得产生长期写入；
一次由无关撤回触发的重放**与自己一致**不是授权。

资格检查 **fail closed**：没有起源记录的观测不可提交。
`_write_eligibility`、`_revision_binding_history`、`_late_feedback_relocations`
三项都已纳入 `_capture_revision_transaction` / `_restore_revision_transaction`。

### 2.4 没有用禁止提升的方式"修复"

- legacy 车道的 CCRR 延期观测从未被阻断，仍然可被重放提升
  （`test_the_legacy_lane_promotion_path_is_not_banned`）；
- 修复后第一种目标仍然新增 2 条提交，全部来自未阻断车道，
  并带 `ccrr_rebuild_replay_promotion` 授权记录
  （`test_every_rebuild_promotion_carries_a_recorded_authorization`）；
- 隔离历史未删除，长期记忆未关闭，重建未跳过。

**仍需用户决定**：重建重放是否应当被允许**重新分类**从未被阻断的 CCRR 延期观测。
这属于长期提交判据，不自行冻结。最小反例就是上表第一行的 `+2`。见 §6 决策项 1。

### 2.5 pending-debt 阻断的正反对照

- 负对照：存在 pending adaptive debt 时调用公开反馈入口 →
  `pending adaptive debt blocks legacy and direct-core mutation; resolve it through replay_adaptive_debt`，
  十三项状态量完全不变，pending debts 仍为 1；
- 正对照：同一历史、无 pending debt 时，同一形状的反馈被接受并执行 `RETRACT`。

---

## 3. R3：独立参考与时序验证

### 3.1 恒真断言已删除

`tests/test_structure_two_late_counter_evidence_chain.py` 原第 168 行

```python
assert set(core._committed_events) <= before_committed | set(core._committed_events)
```

已替换为严格相等：

```python
assert core._quarantined_events == [], "legacy history must start with no quarantine"
...
assert set(core._committed_events) == before_committed - {revision_id}
```

之所以能写成严格相等：该 legacy 历史事前隔离集为空，重建没有任何可合法提升的对象，
所以幸存集合必然精确等于"事先记下的集合减去被撤回的那一条"。

### 3.2 事先保存的独立参考，及其边界

`_journal(probe)` 在被测系统发生任何变更**之前**读取一次，记录每条观测的
原始写入资格、隔离原因、授权数、位置、`statistical_owner_weight`、当时的分类，
之后不再从系统刷新。Hybrid 对账用的是**事先保存的权重**，不是事后读回的权重，
因此"重建悄悄改了权重"会被这条对账抓住。

**边界如实说明**：重建之后的 committed 集合是一次 CCRR 重放的结果；本文件不重新实现
CCRR，因此**不预测**重放会提升哪些合格观测。能独立推出并被严格断言的是：

1. 任何原写入被阻断的观测都不在 committed 集合里；
2. 新增提交 ⊆（事先保存的合格 ∩ 事先保存的隔离集）；
3. committed ⊆（事先保存的 committed ∪ 事先保存的隔离集）− 撤回目标；
4. 幸存事件的 `statistical_owner_weight` 与事先保存值逐条相等；
5. `hybrid_alpha(L)` = 事先保存权重在 L 上的和；
6. 被阻断且幸存的观测集合 = 现隔离集合与被阻断集合的交集（扣留而非删除）。

### 3.3 分别核对的量

`_full_state` 一次性比对：observed、committed、quarantined、后代生命周期、
Hybrid alpha、Dirichlet 规范哈希、active regime、RLS 快照哈希、fast memory、
发布快照（id + map_version）、反馈去重集合、**实际解码动作**（top-1，不只是分布哈希）、
动作分布哈希、绑定集合、relocation 条数——共 15 项。
合同要求不变的场景（拒绝、故障回滚、幂等重放）全部断言这 15 项**完全相等**。

### 3.4 覆盖的时序与故障场景

| 场景 | 测试 |
|---|---|
| 撤回一个谱系并对账 | `test_formal_counter_evidence_removes_exactly_one_lineage_and_reconciles` |
| 重复投递（同一记录） | `test_an_identical_counter_evidence_replay_is_an_idempotent_no_op` |
| 乱序：引用已撤回 revision 的新记录 | `test_counter_evidence_citing_an_already_retracted_revision_is_refused_cleanly` |
| 迟到反馈绑定到已撤回目标 | `test_a_late_feedback_for_an_already_retracted_revision_is_refused_recoverably` |
| 故障回滚 | `test_a_partial_failure_mid_revision_restores_every_statistical_quantity`、`test_a_failed_relocated_transaction_leaves_no_relocation_row` |
| 回滚后重试成功 | `test_a_failed_relocated_transaction_leaves_no_relocation_row` 尾段 |
| 重复投递已重定位的迟到反馈 | `test_a_relocated_feedback_replayed_a_second_time_is_an_idempotent_no_op` |
| 既有正式纠正/强化路径的绑定发布 | `_publish_revision_binding` 覆盖 `_reinforce_revision` 与 `CORRECT` 两条路径 |

### 3.5 迟到反馈时序：复现与修复

**复现**（与审核完全同形）：12 天 legacy 历史 → 为事件 A、B 各自生成与其真实快照绑定的反馈 →
先验证 B 的绑定合法（`_validate_feedback_revision_binding` 返回 B）→ 撤回 A →
B 仍 committed，但其快照绑定被重建改写 → 提交原本合法的 B 反馈 →
上轮 `ValueError: feedback revision snapshot does not match the committed event`。

**修复**：新增按 revision 的**只追加发布绑定历史** `_revision_binding_history`。
`_resolve_feedback_binding` 在当前绑定不匹配时，去该 revision **自己的**发布历史里找：

- 必须是本运行时**确实为该 revision 发布过**的快照；
- 必须是**同一位置**发布的（原始动作上下文被核验，不被改写）；
- 必须严格早于当前 `map_version`；
- 目标仍须 committed（已撤回则交给既有的死目标处理，不做静默重定位）。

接受后写一条 `_LateFeedbackRelocation` 审计行，且**在统计事务成功之后**才追加，
所以回滚不会留下审计残留。

实测（原生）：`published_binding_count: 2`，`accepted: true`，`operations: ["retract"]`，
`relocations_recorded: 1`，`presented_map_version: 2 → current_map_version: 13`。

**没有取消快照校验**：负对照里，另一个 revision 已发布的快照、以及凭空编造的快照，
都仍然被 `feedback revision snapshot does not match the committed event` 拒绝，
且不留 relocation 行。

**仍需用户决定**：目前对"多旧算太旧"没有上界。见 §6 决策项 4。

---

## 4. R4：正式生产路径上的七算子因果证据

### 4.1 真实调用次数（runtime 证据，单独报告）

用 profile 钩子读活帧计数，**不替换任何对象**，所以运行时身份守卫、源码绑定与回执
都与未插桩的运行完全一致。

| 入口 | CIAV planner | CIAV executor | `_execute_ciav_operator` | 说明 |
|---|---:|---:|---:|---|
| legacy `process_transition`，18 天，window=2 | 0 | 0 | 0 | 复现审核结论 |
| legacy `process_transition`，18 天，window=3 | 0 | 0 | 0 | 复现审核结论 |
| 正式 direct-P5 单步 | 1 | 1 | 1 | 13 行已验证回执 |
| 合法 debt-replay 单步 | 1 | 1 | 1 | 13 行已验证回执 |

因此 legacy 车道上的数值变化**保留为该主干的局部因果证据**，
**不**与另一条路径的七份身份回执拼接成"同一生产车道七算子联合协作已验证"。
旧文件 `test_structure_two_operator_causal_matrix.py` 原样保留，其结论范围以此为准。

### 4.2 覆盖矩阵（binding / 依赖 / 数值 / 动作，分别报告）

`tests/test_structure_two_operator_coverage_matrix.py`，两条正式车道各一份：

- **binding**：两条车道都在 `STRUCTURE_TWO_OPERATOR_ORDER` 七个算子上取得 executed 回执，
  每行都带 `operator_instance_id` / `implementation_symbol` / `callable_symbol`，
  且 CIAV 的真实调用次数 ≥ 1；
- **空对照**：同一输入重跑一次，`opceu / orrer_cheh / pchmp / cf_bocpd / ccrr`
  的回执输出哈希、CIAV 实际收到的快照与 belief 的内容哈希、CIAV 执行器的算法输入哈希、
  动作分布哈希、解码动作、propensity 权重**全部逐项相等**；
- **干预**：六个真实算法输入干预（传播/检出倾向、未解析质量与 actor 先验、
  证据子集、上下文键、CCRR 确认窗口、CIAV 似然），逐格记录
  `own_receipt_output_changed` / `ciav_actual_input_changed` /
  `action_distribution_changed` / `decoded_action_changed` /
  `propensity_weight_changed` / committed / quarantined；
- **不制造动作变化**：不改变解码动作的格子就如实记为不改变。

**明确未覆盖的格**：

1. **RGRC 行**：这两条车道上 RGRC 的可观测作用是长期写入授权，已在 R2/R3 套件覆盖；
   在不删除算子的前提下没有可用的算法输入干预，因此本矩阵把该格记为 uncovered，
   **不**用别的套件的证据把它填成通过。
2. **RGRC / CIAV 自身回执载荷的跨运行可复现性**：它们内嵌每次运行新生成的标识符，
   跨运行不可复现（即仍未关闭的 `_execution_observable_state_sha256` 复现性缺口 G6）。
   因此它们被排除在空对照之外，**也绝不用作"干预产生了影响"的证据**。

### 4.3 CF-BOCPD → CIAV：实际对象、内容与传播

不是"两个对象非空"，而是三层：

1. **对象同一性**：在 CIAV 结束、反馈闭包尚未推进滤波器的那一刻，
   `runtime_cause_snapshot_is_ciav_input = true`，即 CIAV 收到的就是核心发布的那个对象本身；
2. **内容同一性**：`content_sha256(CIAV 收到的快照)` 等于**本次执行**主通道
   CF-BOCPD 回执的 `output_payload_sha256`（`ciav_input_sha256_equals_cf_receipt: true`）；
3. **干预传播**：改动上游真实算法输入后，CIAV 实际收到的快照哈希、belief 哈希、
   以及执行器实际收到的 `actor_prior` 全部改变；同输入重跑的空对照则逐项相同。

另有 CIAV 自身算法输入的干预与空对照（`actor_likelihoods_by_outcome`）。

### 4.4 声明纠正

本套件任何地方用到的撤回策略都是调用方通过 `process_execution_feedback(policy=...)`
这一公开接缝提供的 `CalibratedRetractionPolicy`。
**系统默认策略仍不会自主发出 RETRACT / CORRECT。**
本轮没有任何证据表明系统已具备自主校准撤回能力，报告中也不作此表述。

---

## 5. 回归与新鲜证据（原生环境）

| 批次 | 覆盖 | 结果 |
|---|---|---|
| 上轮指定的 214 项集合 + 本轮新增 38 项 | 16 个文件 | **252 passed** |
| 受影响邻域（反馈 / CIAV / 谱系 / 事务 / 证据轨迹 / 执行接口 / P0 加固） | 12 个文件 | **232 passed** |
| ruff `check src tests docs` | 全仓 | **All checks passed** |

### 5.1 源码绑定门的起点 / HEAD 差分

```text
起点 09eb4d4 : 4 failed, 59 passed, 9 errors  （10 个不同 id）
本轮 HEAD    : 4 failed, 59 passed, 9 errors  （10 个不同 id）
仅在 HEAD 出现（新增回归）: 空
仅在起点出现（被修好）    : 空
```

全部落在 `tests/test_structure_two_runtime_identity_gate.py` 与
`tests/test_structure_two_adaptive_compute_predeath.py`，
校验的是留存 readiness 产物对活源码的绑定，在共同起点上就已不成立。
**既有失败没有被记成通过，也没有在未做差分的情况下归咎于本轮。**

### 5.2 新鲜证据目录

`docs/reviews/data/structure_two_window3_round3_2026-09-11/`

- `round3_evidence.py`：证据生成脚本（可独立运行，接受 worktree 路径参数）；
- `w3_round3_results.json`：本轮最终源码上的实跑结果，含合法 direct-P5 与
  debt-replay 正路径、来源绑定确认与实际行为。

复现命令：

```bash
cd /private/tmp/s2-w3-native
V=/Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/.venv/bin/python

# 1) 指定集合 + 本轮新增
PYTHONPATH=src $V -m pytest -o addopts='' -q -p no:cacheprovider \
  tests/test_structure_two_backbone_operator_wiring.py \
  tests/test_core_prototype_spine.py \
  tests/test_structure_two_production_system.py \
  tests/test_structure_two_execution_interface.py \
  tests/test_structure_two_adaptive_runtime.py \
  tests/test_structure_two_adaptive_runtime_adversarial_round1.py \
  tests/test_structure_two_adaptive_runtime_adversarial_round2.py \
  tests/test_structure_two_p5_direct_trace_probe.py \
  tests/test_structure_two_p5_debt_replay_confirmation.py \
  tests/test_structure_two_backbone_counterexample_regressions.py \
  tests/test_structure_two_late_counter_evidence_chain.py \
  tests/test_structure_two_operator_causal_matrix.py \
  tests/test_structure_two_ciav_negative_observation_layers.py \
  tests/test_structure_two_p0_maintenance_fault_injection.py \
  tests/test_structure_two_formal_revision_lineage.py \
  tests/test_structure_two_operator_coverage_matrix.py

# 2) 源码绑定门差分
for d in /private/tmp/s2-w3-src-09eb4d4 /private/tmp/s2-w3-native; do
  (cd $d && PYTHONPATH=src $V -m pytest -o addopts= -q -p no:cacheprovider -rfE \
     tests/test_structure_two_runtime_identity_gate.py \
     tests/test_structure_two_adaptive_compute_predeath.py)
done

# 3) 本轮证据
PYTHONPATH=src:tests $V \
  docs/reviews/data/structure_two_window3_round3_2026-09-11/round3_evidence.py .
```

### 5.3 失效登记

本轮变更的生产源码：`prototype_spine.py`、`structure_two_production_system.py`、
`structure_two_execution.py`。

`build_production_assembly_manifest` 对 `src/cpswm/**/*.py` 逐文件取哈希，
因此**所有依赖该 manifest 的留存产物在本轮之后需要在最终整合源码上重算**，包括：

| 产物 | 状态 |
|---|---|
| 窗口三留存的 direct-P5 / debt-replay 产物 | 在共同起点就已失效（上轮已登记），本轮未修复也未覆盖 |
| `test_structure_two_runtime_identity_gate.py` / `test_structure_two_adaptive_compute_predeath.py` 依赖的 readiness 产物 | 同上 |
| 任何引用 `prototype_spine.py` / `structure_two_execution.py` / `structure_two_production_system.py` 源码哈希的签发 | **本轮新增失效，待最终整合后重算** |

**未改动任何历史产物、旧摘要或全局检查点。**
未合并其他窗口，未推送，未修改窗口一的证据治理实现或窗口二的比较验证器。

---

## 6. 需要用户决定的事项（保留未通过状态）

### 决策项 1：重建重放是否可以重新分类"从未被阻断"的 CCRR 延期观测

- 现状：可以。修复后第一种撤回目标仍新增 2 条提交，全部来自未阻断车道，
  带 `ccrr_rebuild_replay_promotion` 授权记录。
- 合同依据：`ccrr_promotion_required_before_eligible_write = true` 说的是
  CCRR 提升是合格写入的**必要**条件，没有禁止确定性重放重新分类。
- 影响：一次撤回仍会改变一部分历史分类（本例 +2），Hybrid alpha 随之变化。
- 最小反例：`w3_round3_results.json:r3_formal_revision_first_committed`（`newly_committed: 2`）。
- 可选做法：(a) 维持现状；(b) 让在线分类"粘住"，重放只重算 regime 不重新分类；
  (c) 给重放提升加一个独立判据（如需要连续 N 次确认）。
- **本项保持未通过，不自行冻结阈值。**

### 决策项 2：`require_declared_member` 是否推广到所有算子绑定

- 现状：只在自适应延期路径的四个维护节点开启。
- 影响：推广会拒绝本仓库既有的实例级回执插桩测试（两项），需要同步改造它们；
  不推广则其余算子与 legacy 车道的同类冒名替换**仍未覆盖**。
- **本项保持未通过。**

### 决策项 3：被阻断的观测还能由哪些权威解除阻断

- 现状：只有"本身未被阻断的执行中 CCRR 判定 `HABIT_CHANGE`"会签发
  `ccrr_habit_change_promotion`。在十天不同位置 CIAV 闭包历史里，
  实测该授权未被触发（10 条被阻断观测全部保持隔离）。
- 待定：一次完成的 debt replay 是否应当追溯授权它当初在 P0 阻断下的主通道观测。
- 这与 G1 是同一个根：自适应车道的长期固化目前只经不同位置 CIAV 闭包可达。
- **本项保持未通过。**

### 决策项 4：迟到反馈的过期上界

- 现状：只要是该 revision 自己发布过、同位置、严格早于当前 map_version 的绑定，
  且目标仍 committed，就接受并审计。**没有年龄上界。**
- 待定：是否需要按 map_version 距离或时间设上界。
- **本项保持未通过。**

---

## 7. 本轮**未**关闭的既有缺口（保持开启）

| 编号 | 内容 | 本轮状态 |
|---|---|---|
| G1 | 自适应车道的长期固化只经不同位置 CIAV 闭包可达；同位置与负观测为 0 committed | **仍缺失**。本轮的写入资格修复使这一点**更明显**（10 条被阻断观测保持隔离），但没有打通该通路 |
| G2 | `feedback_revision_loop` 被声明为 ORRER_CHEH 实例却从未被调用，且持有不同的引擎/消息传递器 | **仍缺失** |
| G4 | CCRR `identity_switch_probability` 在生产中恒为零 | **仍缺失** |
| G5 | 完整粒子主干 / 神经摊销提议 / 条件化 RB 块未接入生产 | **仍缺失** |
| G6 | `_execution_observable_state_sha256` 跨运行不可复现（`prototype_spine.py` 的 `uuid4`） | **仍缺失**，且本轮在 §4.2 中被再次量化 |
| G7 | 额外声明的算子实例从未做身份核验 | **仍缺失** |
| G9 | 默认策略不会自主发出 RETRACT / CORRECT | **仍缺失** |

**这些缺口不因本轮回归全绿而关闭。**
结构二的研究范围完整保留：H/R/I/C/Z/r/V 七轴、神经摊销提议、三个 Rao–Blackwellized
统计块、可逆 RGRC 账本、七算子，以及隐藏事件、多人、开放世界未知、可逆归因与具身反馈，
本轮**未删减任何一项**。

---

## 8. 本报告不授权的事项

- 不签发 `TrustedSevenOperatorAblationAuthorization`，不运行七算子消融，不训练路由器；
- 不改动科学阈值、比较数据或预算；
- 不把本轮任何工程通过写成科学门通过；
- 不宣称审计穷尽——本轮是**部分审计**，覆盖边界在 §3.2、§4.2 与 §7 明确写出。
