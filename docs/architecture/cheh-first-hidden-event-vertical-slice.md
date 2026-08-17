# CHEH 首个隐藏事件纵切

版本：`cheh@0.3`  
日期：2026-08-14  
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
actor-X → actor-Y: pick_up → transfer → carry → place
actor-Y → actor-X: pick_up → transfer → carry → place
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
3. 将 M30 从单个 `PLACE` 真值扩展为完整 pick-up/carry/handoff/place 链；
4. 加入只观察一部分动作、人物间歇可见、身份切换和相似实例；
5. 新增 hidden-event Top-k、responsible-actor accuracy、错误事件长期污染和 late-evidence recovery（迟到证据恢复）指标；
6. 接入 RGRC 隔离区，比较 top-1 错误写入与 CHEH 延迟巩固；
7. 再实现 PCHMP，使消息传递遵守来源类型和互斥假设约束。

## 7. 代码入口

- 契约：`src/cpswm/system/counterfactual_event_hypergraph/contracts.py`
- branch/revise/retract/rebuild：`src/cpswm/system/counterfactual_event_hypergraph/engine.py`
- 直接基线：`src/cpswm/system/counterfactual_event_hypergraph/baselines.py`
- 测试：`tests/test_counterfactual_event_hypergraph.py`
- 上游人物证据与 D0 场景：`src/cpswm/system/evaluation_operations/d0_shift_scenarios.py`
