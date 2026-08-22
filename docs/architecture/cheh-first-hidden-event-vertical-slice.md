# CHEH 首个隐藏事件纵切

版本：`cheh@0.3 + orrer@0.1 + synthetic-routines@0.3`
日期：2026-08-21
成熟度：`method_specified_contract_tested_heuristic_vertical_slice`  
范围：CHEH 的分支、修订、撤销和重建启发式语义；尚不是完整 PCHMP、严格因果反事实推断、真实人物感知或论文创新证据

## 1. 已有覆盖提醒与本轮方法边界

GESTO、EGG、HERMES 等已有项目已经实现人—物事件、活动层次、事件边或时序场景图。因此，下列内容不能作为本项目创新：

- 把 `pick_up`、`carry`、`handoff`、`place` 存入图；
- 给事件边增加人物标签；
- 用 GNN/Transformer 对事件图编码；
- 从前后快照输出一个 top-1 事件解释。

CHEH 本轮改变的是事件记忆的基本对象：不把某一条猜测立即写成确定事件，而是维护同一观察间隙内、共享端点证据的 **mutually exclusive event-chain hypotheses（互斥事件链假设）**，并提供跨时间修订和撤销操作。

## 2. 首个可执行方法

对同一物体在 \(t_0\) 和 \(t_1\) 的两个位置检测结果，CHEH 建立：

\[
\mathcal{H}_{t_0:t_1}=\{h_k\}_{k=1}^{K}\cup\{unresolved\},
\qquad \sum_k p(h_k)+p(unresolved)=1
\]

首纵切支持：

```text
actor-X: pick_up → carry → place
actor-Y: pick_up → carry → place
unknown_actor: pick_up → carry → place
actor-X → actor-Y: pick_up → carry → transfer → place
actor-Y → actor-X: pick_up → carry → transfer → place
```

每个事件链绑定：

- 稳定 `hypothesis_id` 和每一步 `step_id`；
- 最终放置责任人物；
- 事件顺序、事件时间、物体、来源位置和目标位置；
- 两个端点检测及其他人物证据来源；
- 当前 posterior probability（后验概率）；
- active/retracted 状态；
- direct/handoff 解释类型。

## 3. 三个新操作

### 3.1 `branch`

从两个端点观测和人物先验生成多条直接移动/交接候选。接口拒绝单一人物 top-1 输入，强制至少保留两个责任假设，并为无法表达的事件链保留 `unresolved_probability`。

### 3.2 `revise`

新 `ActorResponsibilityEvidence（人物责任证据）` 必须同时声明生成该后验所用的 `reference_actor_prior（参考人物先验）`。CHEH 使用 likelihood ratio（似然比）\(p(A\mid e)/p_0(A)\) 重加权 active hypotheses（活动假设），不再把上游 posterior（后验）直接乘进已有 posterior，从而避免先验双计数。`effective_sample_weight（有效样本权重）` 对相关证据的似然比做幂缩放；低于阈值的假设被显式标记为 `retracted`，其概率质量返回未决项；旧 revision（修订版本）不可变。

### 3.3 `retract/rebuild`

后续矛盾证据可以撤销一个或多个假设，但不能只提交任意 UUID：调用方必须提交完整 `ActorResponsibilityEvidence（人物责任证据）`，该证据必须绑定当前 household/session/trace、同一物体、一个已知端点 detection（检测结果）及其时间，并对每个待撤销责任人物显式给出零概率。撤销不会删除历史记录，而是追加新 revision；完整 revision 链通过 parent binding（父版本绑定）和内容哈希确定性重建。

## 4. 关键不变量

- 所有候选必须解释相同物体和相同前后位置端点；
- 隐藏事件严格位于两次观测之间；
- 事件序号连续、时间严格递增；
- 事件链以 `PICK_UP` 开始、以 `PLACE` 结束；
- `TRANSFER` 必须具有不同的发出者和接收者；
- active hypotheses 与 unresolved 的概率总和为 1；
- retracted hypothesis 的后验必须为 0；
- 每个候选始终保留两个端点检测的来源；
- revision 内容哈希、ID、revision number 和 parent revision 必须一致。
- 同一 `evidence_record_id` 只能消费一次；同一 `evidence_cluster_id` 即使换了记录 ID 也只能消费一次；
- actor evidence（人物证据）还计算忽略 `record_id`、`evidence_cluster_id` 和 `EvidenceRef.evidence_id` 包装身份的 semantic fingerprint（语义指纹）。指纹覆盖 household/session/trace、物体、端点与时间、source/model、人物分布、参考先验、有效权重以及 evidence refs 的规范化内容集合；引用顺序、包装 UUID 或重复同一引用均不产生新语义，同一证据不能跨 revision 或在同一 `retract` 批次重复消费；
- 人物证据必须绑定同一 household/session/trace、物体和端点 detection，不能引用任意外部观测。
- endpoint detection 与 actor evidence 的 metadata schema 分别固定为 `cpswm.ObservationDetectionResult@0.1.0` 和 `cpswm.ActorResponsibilityEvidence@0.1.0`；错误标签不能被当成新的证据语义。
- `hypothesis_set_id` 绑定规范化的完整 before/after detection（前后检测）内容与 engine version，而不只绑定两个 record ID；端点内容变化必须产生不同集合身份。
- 修订历史不允许改变 household/session/trace、时间区间、端点、物体、候选链或 engine version（引擎版本）；所有新证据来源都必须累积保留在候选上。
- branch/revise/retract/rebuild 的公共输入在使用前递归检查 live fields（活动字段）并完整重验证，顶层或嵌套 `model_copy` 注入不能被序列化静默丢弃后接受。

## 5. 当前没有宣称什么

本轮尚未证明：

- CHEH 优于普通 top-1 事件图；
- 当前启发式先验或交接权重是最佳推断方法；
- CHEH 在真实人物检测或遮挡下校准；
- CHEH 能改善人物污染、搜索、放回或递送效用；
- PCHMP 的来源约束消息传递已实现。
- 上述来源校验构成通用 capability security（能力安全）或严格因果识别；它仍是受契约约束的启发式修订边界。
- 当前没有 trusted provenance registry/signature（可信来源注册表/签名）。semantic fingerprint 只能阻止已进入 CHEH 的同内容证据被换包装重复消费，不能证明 `source_id`、`evidence_model_id`、endpoint UUID 或 evidence refs 的外部真实性；调用方仍可构造自洽但未认证的来源声明。

因此创新台账只能记录为 `method-specified, contract-tested heuristic vertical slice + direct baselines runnable`，不能写成 `provenance-constrained revision`、`strict causal counterfactual inference` 或 `direct baseline passed`。

## 6. 下一步直接基线与扩展

1. **top-1 event graph baseline（单一事件图基线）**：已实现，只保存当前 MAP 事件链；
2. **independent event candidate baseline（独立事件候选基线）**：已实现，保留多个独立二元置信候选，但没有互斥归一化、revision 或撤销；
3. **Bernert–Ramparany 2021 compatible-sequence adaptation（兼容序列领域适配）**：已实现，保留所有与前后端点一致的 direct/handoff 序列并查询必然责任人物；不提供概率排序、未知人物或迟到证据历史；
4. **Damen–Hogg 2012 AMG constrained MAP adaptation（AMG 约束 MAP 领域适配）**：已实现，按物理语法、共享约束和事件 likelihood ratio（似然比）选择一个全局 MAP 解释；不是其视频检测器、半高斯训练、RJMCMC-SA 或 IP 求解器的完整复现；
5. M30 `synthetic-routines@0.3` 已生成完整 `pick_up → carry → handoff → place` 真值链，并保留 `@0.2` 冻结 PLACE 基准身份；
6. 下一步加入只观察一部分动作、人物间歇可见、身份切换、相似实例和迟到证据；
7. 新增 hidden-event Top-k、responsible-actor accuracy、错误事件长期污染和 late-evidence recovery（迟到证据恢复）指标；
8. 接入 RGRC 隔离区，比较 top-1 错误写入与 CHEH 延迟巩固；
9. 再实现 PCHMP，使消息传递遵守来源类型和互斥假设约束。

首个干净交接机制案例中，2021 适配基线与 CHEH 都把真值保留在 4 个候选中，独立提供角色似然后的 2012 AMG-MAP 适配也准确选中真值。这个结果只证明新 M30 真值和基线可执行，**没有证明 CHEH 优于已有方法**。能区分新旧方法的实验必须加入跨时间迟到证据、撤销、未知人物、证据簇、身份噪声和长期巩固污染。

## 多种子匹配死亡测试结果（2026-08-21）

后续 `m30-hidden-event-death-test@0.1` 已生成 80 个案例：20 个 validation、60 个 held-out test，覆盖 direct/handoff 成对机制、迟到证据、身份先错后纠、重复证据簇和未知人物；证据强度随 seed 确定性变化。CHEH 与 2012 AMG 领域适配分别独立调参，无状态方法允许在迟到证据后从相同累计证据完整重跑，但不能把该重跑记为 append-only revision。

已知人物 test 上，CHEH 完整链 Top-1 为 24/48=0.500，2012 AMG 适配为 26/48=0.542；两者最终人物责任和从错误人物判断恢复的准确率均为 1.0。CHEH 真链集合覆盖为 1.0、重复证据簇拒绝为 1.0，但所有 handoff 的 Top-1 都失败。原因是当前人物证据只按最终 `responsible_actor_key` 更新，无法区分同一最终人物下的 direct/handoff 机制。未知人物赛道中，CHEH 覆盖 unknown direct，却不能生成 unknown handoff。

因此状态更新为 `direct baseline failed; representation gap identified`。下一 CHEH 候选方法是 ORRER（Open-world Role-conditioned Reversible Event Revision，开放世界角色条件可逆事件修订）：匿名人物可承担交接两侧角色、机制/有序角色证据具有参考先验与簇来源、被阈值撤销的假设可在独立纠正证据下重激活，并通过 RGRC 依赖账本撤销错误长期写入。Damen–Hogg 2012 已经使用事件似然和角色约束，所以单独添加 handoff 分类器不能作为创新；必须用完整 ORRER + RGRC 算子在匹配增强基线上证明恢复、污染和行动效用收益。

## ORRER v0.1 实现结果

ORRER 现已允许 `unknown_actor` 担任交接发起者或接收者，增加带参考先验、端点、来源和证据簇的 mechanism/ordered-role evidence，并用持续更新的 `revival_probability` 支持正证据门控 `REACTIVATE` revision。错误机制证据先剪除交接链、独立纠正证据再恢复的对抗测试已通过；中性证据不能恢复撤销链。

M30 death test v0.2 中，ORRER 的已知人物完整链和未知人物真链覆盖均为 1.0，修复了 CHEH 的 0.500/0.500。但刻意增强、取得完全相同三类证据并允许开放未知角色的 AMG 适配同样达到 1.0。结论是 ORRER 的表示和在线修订能力已实现，**优于强匹配基线的创新收益仍未建立**。下一直接门是 ORRER×RGRC：比较增量可逆长期写入与完整重跑的污染、恢复成本和具身行动 regret。

## 7. 代码入口

- 契约：`src/cpswm/system/counterfactual_event_hypergraph/contracts.py`
- branch/revise/retract/rebuild：`src/cpswm/system/counterfactual_event_hypergraph/engine.py`
- 直接基线：`src/cpswm/system/counterfactual_event_hypergraph/baselines.py`
- 完整 M30 链：`src/cpswm/system/synthetic_routines/generator.py`
- 匹配案例入口：`apps/evaluation_runner/run_m30_hidden_event_baselines.py`
- 测试：`tests/test_counterfactual_event_hypergraph.py`、`tests/test_m30_complete_event_chains.py`
- 多种子死亡测试：`src/cpswm/system/evaluation_operations/hidden_event_death_test.py`、`apps/evaluation_runner/run_m30_hidden_event_death_test.py`、`tests/test_m30_hidden_event_death_test.py`
- 结果与 ORRER 重构：`docs/结构二/方向结构二_推进记录_2026-08-21_M30多种子匹配死亡测试与CHEH重构.md`
- ORRER 实现与匹配增强基线：`docs/结构二/方向结构二_推进记录_2026-08-21_ORRER开放角色可逆修订与匹配增强基线.md`
- 上游人物证据与 D0 场景：`src/cpswm/system/evaluation_operations/d0_shift_scenarios.py`
