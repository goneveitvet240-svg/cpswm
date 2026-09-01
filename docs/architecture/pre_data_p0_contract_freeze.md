# 结构一/二：正式数据接入前 P0 contract freeze（partial）

当前状态：`contract_freeze_partial`。不得标记为 `pre_data_integration_complete`；三道
required gate（必要门禁）继续全部 `BLOCK`。

本文件冻结数据入口与权限，不宣称任何方法有效，也不替用户选择 FindingDory episode、HCS、
CO-CIP 或三层位置融合路线。

## 1. Unified evidence contract（统一证据契约）

正式入口候选是 `UnifiedEvidenceContract` / `ProjectOneEvidenceDatasetRecord`。它同时保存 actor
posterior（含 `unknown_actor`）、observation opportunity、是否选择与 selection probability、
视野/遮挡/容器状态、检测失败原因、valid/recorded time、direct/inferred/model 来源、
evidence cluster 与相关性、有效样本权重、actor/object/location 开放集 posterior、候选空间及
evidence refs。

D0 开发纵向链现已可执行：raw synthetic fixture → `UnifiedEvidenceContract` → structure-two
runtime；同一 formal record 也可进入 structure-one runtime adapter。结构一现有方法仍是 legacy
arm，因此该桥必须由调用者显式选择 actor/location collapse，并为每次调用返回
`EvidenceDowngradeReceipt`。formal record 本身不再携带独立 `observed_location`。

`ProjectOneDatasetRecord` 继续保留为 `legacy baseline input`。formal manifest/stream 不得静默
调用它；只有带 receipt 的显式降级路径可用。

Observation opportunity 的定义概率允许 `[0,1]`，从而保留 structural zero（结构零）和
coverage gap；但 realized selected observation 必须 `>0`，zero propensity 禁止逆加权。
direct detection 必须绑定同 household/session/trace、时间落在 valid interval 内的 selected
opportunity；inferred/model evidence 必须有父 evidence refs。

## 2. Compatibility 不得提升 maturity

`contract_compatibility` 与 `source_evidence_maturity` 分开记录。maturity 不使用整数 rank，
而使用 allowed-transition graph（允许转换图）：同 kind 保持允许，任何来源可显式降级为
`D0_DEVELOPMENT_FIXTURE`；fixture → oracle、D0 → D1/D2 等证据种类变更全部拒绝。

episode 的 compatibility 由每个 step 是否携带完整 `UnifiedEvidenceContract` 自动推导；manifest
还必须绑定全部 formal evidence record IDs，并与 episode 做内容级复核。调用者不能只填写
`FULL_REPLAY_CONTRACT` 枚举来声明兼容。

## 3. Shared LLM provenance 与融合权限

结构一、结构二共享 `LLMProviderIdentity` 和 `LLMInvocationProvenance`：provider、model、
version、role/authority、temperature、prompt template version、prompt SHA-256、输入证据引用、
token、latency、cost 与 cache key 都进入回执。真实模型证据的 source/track 是 `MODEL`，
不能标成 `CONTROLLED_NOISE`。

四种不确定性必须独立输出：`unknown_actor_mass`、`unknown_mechanism_mass`、
`unresolved_event_mass`、`abstention_probability`。

probability semantics、fusion permission、calibration receipt 与 caller-frozen reference-prior
snapshot ID 都属于 request/cache key。provider 只能回显请求权限，不能选择 semantics 或先验。
adapter 不暴露统一 raw output，而按权限只返回 `CandidateProposalBundle`、
`CalibratedLikelihoodBundle` 或 `ReferencedPosteriorBundle`。posterior 各轴必须归一化且拒绝重复
`(kind, value)`，转换时不再二次归一化 unknown mass。

| probability semantics | 允许做什么 | 禁止做什么 |
|---|---|---|
| proposal only | 扩候选集 | 进入后验融合 |
| calibrated likelihood | 作为直接 likelihood factor | 被当成 posterior 或再次除先验 |
| posterior relative to reference prior | 只以 posterior/reference-prior likelihood ratio 融合 | 使用人为补造均匀先验或直接再乘 posterior |

输出 schema 可以按角色不同，但上述 provenance/cache/accounting identity 必须一致。

## 4. Regime authority（阶段权限）

CF-BOCPD 负责变化与原因后验；RGRC 负责证据准入和可撤销性；CCRR 负责阶段去向提议；
reversible ledger 是阶段指针与长期统计的唯一最终写入者。RGRC-first 与 CCRR-first 都可比较，
但不能出现第二个最终阶段写入权。

## 5. 统计与基线

动作指标按 episode bootstrap。隐藏事件、修订准确率与 unresolved quality 按 episode cluster
bootstrap，并输出 household/object-family cluster sensitivity，禁止 step-level 独立重采样。

OAM-PHM 的 adapter、每基线独立 tuning protocol、current/habitual 双评分、GT/track identity
mapping、扩展 query grid 与性能预算已具备。tuning/evaluation 同时绑定 dataset/truth/group/
identity hashes 和 sample/group disjointness，不能通过改名 `split_id` 复用内容。LastSeen、
HouseholdFrequency 与 Markov 各自提供 native dual head；一次双头调用按一次 component model
invocation 计账。O-STaR 忠实复现、独立重调参、增强版本和 STREAK 仍为
`external_reimplementation_required`；脚手架完成不等于强基线复现完成。

## 6. Full regression budget（全量回归预算）

CI 的 pytest 使用 `--dist=loadscope`，确保 module-scoped（模块级）昂贵 fixture 只在一个
worker 构建一次；默认逐测试调度会让 SHIFT report 被多个 worker 重复生成。2026-08-27
修复后第二轮全量实测（排除待最终冻结的 checkpoint manifest）为 2479 passed、1 xfailed、
coverage 89%，耗时 35:59。该实测推翻了旧 22 分钟预算，因此执行预算修正为 45 分钟、CI job
总预算修正为 50 分钟，并继续输出最慢 25 项；没有删除或降级慢测。
2026-08-28 新增证据链与安全测试后，全量实测增至 2550 passed、1 xfailed，coverage 89%，
耗时 53:41；45/50 分钟预算再次被实测证伪，因此当前执行预算为 65 分钟、CI job 总预算为
70 分钟。预算只随实测调整，仍不通过删除慢测、降低覆盖率或跳过安全测试缩短时间。
static typing 与 regression 是独立 CI gate，任一失败都保持 BLOCK，但 mypy 失败不能阻止
pytest 实际启动。超时不能靠删除慢测或刷新 checkpoint 掩盖。

`p0_checkpoint` 内容清单绑定整个代码快照。2026-08-27 修复和两轮对抗完成后，按项目 owner
本次明确修复授权刷新一次；之后任何内容变化都应继续使清单失败，不能靠自动刷新掩盖漂移。

## 7. 仍保持 BLOCK 的边界

- 当前纵向链是 D0 fixture，不是真实 FindingDory rows/video 或真实视觉 prediction cache。
- structure-one 方法臂通过 receipted downgrade 执行；尚无一个原生消费完整 posterior 的正式方法臂。
- O-STaR、增强 O-STaR、STREAK 与外部独立重调参仍未完成。
- M07–M12、structure-one replay validation 与整体 WS completion gate 仍未通过。
- mobility 的 activity coupling 与 regime-change status 仍保持 `None/UNASSESSED`，没有伪造七类可学习结论。

因此本文件只冻结了可执行契约和防绕行测试，不构成真实数据已接入、正式调参获准或方法有效性证据。
