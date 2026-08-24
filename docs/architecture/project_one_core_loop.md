# 项目一：持续个性化世界模型核心闭环

这是最短可运行的核心原型，不替代 M01–M32 正式成熟度门，也不缩小结构一、结构二、
真实感知或具身验证的既定范围。

## 自动状态判断链

```text
连续机器人可见习惯证据
  -> Joint CF-BOCPD（仅提出变化候选）
  -> confirmation window（确认窗口；候选先隔离）
  -> CCRR（create / reactivate / stay / unresolved）
  -> RLSRegimeBank 自动切换或保留 head
  -> HierarchicalDirichletHabitModel
  -> HybridStatisticLedger / Hybrid RGRC
  -> VersionedBeliefMap
  -> 搜索与归位建议
```

单个异常点返回 `insufficient_evidence` 并执行 `quarantine`，当下不会写入 Dirichlet、
RLS 或 Hybrid RGRC。候选在配置的确认窗口内持续出现后，CCRR 才能创建新 regime 或
恢复历史 regime；此前隔离的完整样本会按确认后的 regime 执行 `promote`，不会丢弃。
默认 `forgetting_factor=1.0`；旧 regime 的 RLS 参数和 covariance（协方差）不被衰减
或覆盖。

`PrototypeLoopConfig` 显式暴露 baseline 长度、确认窗口、变化概率阈值、短期扰动阈值、
owner evidence 阈值、反馈强度和反馈 decision margin。默认值只是原型配置，不是论文预注册
阈值，调用方可以注入其他配置。

候选确认还绑定语义 `context_key`；相同位置若来自不兼容情境，不能作为同一候选的第二个
确认样本。观测的统一 owner 统计权重定义为：

```text
statistical_owner_weight = owner_posterior × evidence_weight × IPW
```

该值原样进入 RLS weighted update（加权更新）和 Hybrid RGRC delta；Dirichlet 通过同一
actor posterior、evidence weight 与 IPW 相乘得到相同 owner contribution。合法的 IPW>1
不再被 RLS 静默截断。

## 执行反馈与项目二修订

```text
ExecutionFeedbackRecord + snapshot-bound DecisionContextBinding
  -> ExecutionFeedbackProjector（似然投影）
  -> ExecutionFeedbackInterpretationPolicy（可插拔解释策略）
  -> reinforce / quarantine / retract / correct
  -> Dirichlet 与 RLS 重放修订
  -> Hybrid RGRC 原生撤销或原子替换
  -> 重新发布 VersionedBeliefMap 和建议
```

默认策略把一次失败视为带 likelihood（似然）的负向证据，只隔离，不把位置概率清零；
显著正向成功证据会按配置强度强化它明确引用的 owner-attributed revision。强化统计保存
`derived_from_revision_id`，原 observation 被撤销、修正或因确认样本撤销而重新 quarantine
时，所有多层 derived descendants（派生后代）都会递归撤出 Dirichlet、RLS 和 Hybrid
RGRC。恢复语义由 `DerivedEvidenceReactivationPolicy` 明确控制：默认
`require_fresh_feedback`，父 observation 后续重新 committed 也不会自动复活旧反馈；显式选择
`restore_prior_derived` 也只会按谱系顺序恢复状态为
`SUSPENDED_PARENT_QUARANTINED` 的派生证据。显式 retract 会写入永久 tombstone（墓碑）；
显式 correct 只保留 corrected revision，旧 revision 写入 corrected tombstone；多层谱系的
中间节点被显式撤销或修正时，其全部后代写入 ancestor-invalidated tombstone，均不得从
archive 自动复活。需要其他语义时，策略必须显式输出目标 revision 和操作。项目二通过
`EventRevisionOutcome` 触发撤销或修正；Hybrid RGRC 使用现有 revision 索引执行撤销/替换，
Dirichlet 与 RLS 则从仍然有效的原型事件登记重放。修正后的 owner mass 会同时重写
Dirichlet actor posterior、RLS gate 和 Hybrid delta，未另建学习算法栈。

反馈必须同时绑定 `feedback record / source revision / object / location / belief snapshot`。
投影采用 prepare → statistic apply → idempotency commit 两阶段时机：策略或统计应用失败
不会提前消费反馈幂等键，重试仍会执行；成功后相同反馈只返回 replay no-op。revision 后续
被撤销时仍保留不可变绑定档案。`corrected_owner_mass=0` 表示完全归因给非 owner：保留修订
审计记录，但三个 owner 统计分支均写入零质量。

项目二发出的 `ProjectOneStatRequest` 由 `CorePrototypeSpine` 作为同一修订事务消费，
一次请求同步重放 Dirichlet、RLS 与 Hybrid RGRC，不能只修改 Hybrid 账本。`RETRACT`
保留零 owner-mass 的逻辑 revision，后续 `REINFORCE` 可沿已撤销的 Hybrid 谱系重新进入，
从而支持 owner mass `positive → 0 → positive` 的完整可逆修订。

事件撤销或修正后，CF-BOCPD/CCRR 使用仍然存活的前缀证据重新播放；active regime
来自重算结果，而不是无条件沿用修订前的 regime。

修订事务设置 `hybrid → dirichlet → rls` 三阶段故障注入点。任一阶段失败都会恢复
Dirichlet 参数对象、RLS sufficient statistics、Hybrid 可重放日志及 revision lineage、
信念地图快照和自动 regime 路由状态。regime 重算也不是机械回退到 `stable`：如果撤销
某个旧确认样本后仍有足够的后续存活证据，CCRR 会继续确认或恢复相应的非 stable regime。

普通 transition 同样使用事务检查点；RLS 或 Hybrid 阶段失败时，Dirichlet、RLS、Hybrid、
CF-BOCPD/CCRR router 与 VersionedBeliefMap 一起回滚。修订重放按 `event_time` 排序，
因此 `f<1` 时也必须等于从头进行的 chronological replay（时间序重放），不能依赖 revision
字典的插入顺序。重放还重新给每条 RLS sample 分配 regime head，禁止沿用被撤销变化点产生的
旧 head 标签。

在线路径使用 CF-BOCPD 的单步 posterior update（后验更新），每个新 prefix 只执行一次
beam step，不再对全部历史调用 batch run。候选确认除 `state_key` 外还要求 context feature
distance 不超过显式配置 `context_confirmation_max_distance`；合法的情境交替序列作为固定的
非持续变化回归护栏。

严格成熟度判断保持不变：当前系统是可信核心雏形，更接近“带隔离窗口的 regime 状态机
+ RLS 多头模型”；个性化模型残差尚未成为变化判断的主要输入，因此不能宣称已经完成
“残差驱动、可逆且严格在线的持续习惯变化判断系统”。

修订分类以 `_observed_events` observation log 为权威来源，不再从 committed 子集反推。
每次 revision 后 fresh replay 同时产生 committed、quarantined、discarded 分类和 RLS head
归属：撤销唯一确认样本会把首候选从 Dirichlet/RLS/Hybrid 长期统计撤回并恢复 pending
quarantine；修订无关历史则保留仍存活候选的确认进度。已撤回候选再次确认时，逻辑 event
revision 保持不变，Hybrid 使用指向已撤销 revision 的新子 revision 重新进入，避免重复
semantic dedup ID。

Habit cause signal 现包含 Dirichlet predictive surprise（预测惊讶度）与 RLS target
residual（目标残差）。位置改变本身不再产生满值信号；只有位置改变与这两个模型误差信号
共同出现时才形成 unexpected-move signal。Dirichlet 先计算
`q=-log(p)/log(K)`，再使用 `1-exp(-max(0,q-1))` 得到相对均匀分布的 bounded excess
surprise（有界超额惊讶度）：均匀概率在任意 location class 数量 `K` 下都映射为 0；比均匀
概率更小的结果仍保留严格严重程度排序，不会在 1 处全部截平。RLS residual 使用
`1-(1-residual)^2` 映射后与 surprise 做概率并集。两个独立 guardrail 权重由
`dirichlet_surprise_weight`、`rls_residual_weight` 显式配置，默认均为 `0.1`，不是论文冻结
阈值。已预测周期移动和未预测新移动必须产生不同 regime decision；周期习惯和正常情境交替
仍作为不得创建伪 regime 的回归护栏。所有公开 probability 字段在构造边界强制为有限的
`[0,1]` 值。

当前工程成熟度可描述为约 78% 的核心原型进度，但这不是正式 B1 完成度或论文证据。
下一研究缺口是用对照实验验证新接入的个性化 residual 是否真正改善变化判断，并在真实
具身下游决策中证明收益，不能从本轮工程契约通过外推方法优势。

每个自动步骤返回 decision record，包含旧/新 regime、变化概率、CCRR 结论、证据来源、
统计操作、map version 和 snapshot ID。反馈结果还保留似然后验概率。

## 运行

```bash
PYTHONPATH=src .venv/bin/python apps/prototype_spine/run_project_one_regime_demo.py
```

## 保留的适配点

- CF-BOCPD/CCRR 阈值与确认窗口的 validation-only 调参和正式预注册；
- 更完整的 verification evidence predicate（验证证据谓词）；
- 反馈解释策略的标定、actor responsibility（行动者责任）和业务效用定义；
- 签名、防重放、防对抗、生产持久化与崩溃恢复；
- M05–M12 真实感知，以及 M20–M27 导航、操作和真实执行回流；
- 正式 B1 和十一臂公平实验。

这些接口保留在研究方向内；原型跑通不代表正式 B1、论文确认性实验或真实具身效用完成。
