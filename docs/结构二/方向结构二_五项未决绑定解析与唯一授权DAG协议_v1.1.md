# 结构二：五项未决绑定解析与唯一授权 DAG 协议 v1.1

日期：2026-09-05
授权协议：`structure-two-trusted-seven-operator-ablation-authorization@1.1`

## 当前结论

本版本扩充的是协议和验证仪器，不是一次正式实验。Task 9 v1.1、Tasks 11–13 与 P5 的独立定义保持不变；五项新增绑定仍保留在 selected-method receipt（已选方法回执）的完整 `unresolved_method_bindings` 集合中。只有新的独立 resolution receipt（解析回执）通过整条信任链后，某一绑定才可能被认为已解析。

当前 checked-in policy（入库策略）的全部 config/spec commitments（配置/规范承诺）、trust-anchor manifest（信任锚清单）、persistent replay registry（持久重放注册表）和 per-hop custody（逐跳托管）仍为 `NOT_ENROLLED`。正式回执也没有登记。因此唯一聚合器的当前结果必为 `NOT_AUTHORIZED`；不得运行可信七算子消融。

## 五个相互独立的解析协议

| 绑定 | 协议 | 独立 estimand（估计量） | arm（实验臂）边界 | confirmatory gates（确认性门） |
|---|---|---|---|---|
| `neural_proposer_architecture` | `structure-two-neural-proposer-architecture-resolution@0.1` | 冻结下游粒子系统下，validation-selected（仅验证集选择）的 full-scope typed proposer（完整范围类型化提议器）质量、行动等价与代价 | 三个保留完整 H/R/I/C/Z、六种 proposal operations（提议操作）及 unresolved mass（未决质量）的 neural arms；另有不可被选择的结构化诊断 control | truth-compatible recall、相对 exact action TV、每 episode 时间 |
| `training_schedule` | `structure-two-training-schedule-resolution@0.1` | 已解析架构上的 retention（保持率）、exact-action agreement（精确行动一致性）与训练稳定性 | joint、staged-then-joint、alternating；数据、总 optimizer steps（优化步数）和搜索次数相同 | continual retention、action TV、非有限或发散运行率 |
| `consolidation_thresholds` | `structure-two-consolidation-thresholds-resolution@0.1` | 可逆 RGRC 阈值策略的错误提交、修正后召回与恢复成本 | precision/balanced/recall 三个冻结 grid points（网格点）；no-commit 仅作不可选 control，不能借此删除可逆提交能力 | false irreversible commit、post-correction recall、recovery cost |
| `ciav_action_budget` | `structure-two-ciav-action-budget-resolution@0.1` | 相同决策前信息下非零 CIAV 预算的效用、预算合规与 regret（遗憾） | 1/2/4 次验证预算可选；零验证仅为不可选 paired control（配对对照） | 相对零验证效用、预算违规率、action regret |
| `exact_enumeration_falsifier` | `structure-two-exact-enumeration-falsifier-resolution@0.1` | 可穷举完整类型世界上的 coverage（覆盖）、跨引擎 posterior（后验）一致性和后果性行动一致性 | direct Cartesian、factorized DP、certified branch-and-bound 三个 exact engines（精确引擎） | 完整质量覆盖、posterior L1、action/utility 差异 |

每个协议分别冻结自己的 estimand、arm family（实验臂族）、validation metric（验证指标）、confirmatory gates、information contract（信息契约）、budget contract（预算契约）与 claim boundary（声明边界）。五份配置互不复用协议 ID，也不能用一个 binding receipt 替代另一个。

## 原始执行到正式回执

每项解析使用相同的强制链：

1. 协议必须在执行开始前冻结，且内容哈希进入 raw execution trace（原始执行轨迹）。
2. 每个 split（数据分区）必须覆盖精确的 `arm × independent-unit UUID` 笛卡尔积；validation 和 confirmatory UUID 不得重叠。
3. 同一 unit 的所有 arms 必须具有相同 `information_view_sha256` 和 `budget_units`；缺臂、缺 unit、增加预算或更换信息都会拒绝。
4. arm selection（实验臂选择）只由 validation mean（验证均值）决定；confirmatory data（确认性数据）在选择后才参与冻结门判定。
5. typed receipt 重新计算选择和全部 gates，并绑定原始 trace hash、完整 selected-method receipt hash，以及冻结时全部九个 unresolved bindings。删除其他未决绑定会导致解析失败。
6. receipt 继续经过任务独立 Ed25519 signer（签名者）、父回执内容哈希、UTC 时间与 freshness（新鲜度）、独立逐跳 custody、持久 replay registry 和 invalidation propagation（失效传播）。最终 executor（执行器）只使用进程内部 UTC，不接受 caller 提供的“当前时间”；最终 verifier 还必须把 manifest 精确绑定到 checked-in policy 的内容哈希并验证冻结 registry-root signature（注册表根签名）。

Task 9 v1.1 的正式回执仍绑定 `ORRER_CHEH` selected-method receipt、七算子顺序及 implementation manifest（实现清单）。Tasks 11–13/P5 仍有各自类型和父链；Task 12 从 raw proposal trace（原始提议轨迹）重算，P5 保留逐阶段和 mixed bottleneck（混合瓶颈）诊断。缺少任何正式运行或独立登记都只产生 blocker（阻断项），不能由 caller-supplied `ENROLLED`（调用方自报登记）打开。

## Gate B、Task 7、Task 8 的新形状保护

聚合 DAG 只接受以下当前形状：

- Gate B v0.8 receipt 必须绑定 `structure-two-gate-b-v0.8-raw-formal-execution-chain@1.0`，以及 canonical execution（规范执行）、runtime belief/action readouts（运行时信念/行动读出）、逐步 causal broker（因果代理）、独立 custody、freshness/replay、独立 review 和 exact arm×episode coverage 的内容哈希及验证状态。
- Task 7 receipt 只接受 v0.4：相同 conditional target（条件目标）、`1e-10` target tolerance、belief/action TV 阈值 `0.1`、16-cell 完整场景矩阵、terminal responsible actor cache（终端责任行动者缓存）、自适应窗口或显式 full-replay fallback（全量重放回退）、无阈值放宽、contamination non-expansion（污染不扩张）均为必填语义；注册通过回执不能隐藏 fallback。
- Task 8 receipt 只接受 v0.4：精确 `joint/factorized/matched_two_stage` 三臂、相同信息预算、各臂 validation-only 独立调参、confirmatory 前冻结、40 个 confirmatory factor units 的 exact coverage，以及 `matched_two_stage_cost - joint_cost` 的预注册 paired percentile bootstrap（配对百分位自助法）。其 lower confidence bound（置信区间下界）必须严格大于 `0.001`。v0.3 保留为当前三臂问题的失败历史，不能替代 v0.4。

## 两轮攻击回执

Round 1 receipt 的正向语义是：scientific counterexample matrix（科学反例矩阵）完整、每个 positive/consequential output（正向或后果性输出）的信任链均被覆盖，而且每个正向输出都有独立 falsifier（证伪器）。旧版泛化的“攻击通过”布尔字段不能替代这些字段。

Round 2 receipt 必须逐项证明 forged-but-complete（伪造但完备）、cross-version substitution（跨版本替换）、replay（重放）、missing dependency（缺依赖）与 direct runner bypass（直接运行器绕过）均被拒绝。任一字段缺失或为假，审计回执无法解析，所有下游授权失效。

## 唯一 runner 门

`run_project_two_factorial_benchmark` 在检查 seeds（种子）、构造 evaluator（评估器）或生成 dataset（数据集）之前，必须调用 `verify_trusted_seven_operator_ablation_authorization`。缺少 decision、checked-in policy、trust manifest、冻结的 registry-root verifier、expected run ID 或 verifier-owned replay registry 时立即抛出 `TrustedSevenOperatorAuthorizationRequired`。公共 runner 不接收 caller-supplied verification time（调用方提供的验证时间）；freshness 只读执行器内部 UTC。CLI runner 没有旧的无令牌路径，拒绝时不会创建 output artifact（输出工件）。

当前 v1.1 只提供 `formal_grade = false` 的内存诊断 replay registry，没有登记任何可产生正向授权的正式 backend。Gate B candidate 的 path/device/inode 检查只能防 storage identity replacement（存储身份替换），不能证明同 inode 内容回滚或 snapshot rollback 安全；因此它不能替代授权层要求的 verifier-owned monotonic/WORM backend。正式 backend 与其 enrollment receipt 尚未实现并登记，是当前硬 blocker；不得用 subclass、自报属性或复制数据库缩小该要求。

本协议不重算也不改写全局 manifest、source-bundle 或 checkpoint；所有 B 侧写入停止后，由 A 单独完成最终冻结和全量回归。
