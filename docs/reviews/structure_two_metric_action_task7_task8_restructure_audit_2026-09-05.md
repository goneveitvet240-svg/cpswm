# 结构二：指标修复、行动死亡测试与 Task 7/8 方法重构审计（2026-09-05）

## 结论先行

执行顺序严格保持为：指标 bug 对抗审核与 order invariance（顺序不变性）回归 → 行动死亡测试
重跑 → Task 7/8 真实失败驱动的方法重构。

- 两个 search utility（搜索效用）语义 bug 已修复；原指标攻击矩阵的 5 条
  forged-but-complete（字段齐全但伪造）路径保持封闭。5 seeds × 24 个
  registered-location permutations（登记位置排列）共 120 次完整报告顺序不变性检查通过。
- 本次又完成两轮异构对抗自查：第一轮发现 4 条 Task 7/8 工件验证器 P0 绕过，第二轮发现
  7 条行动报告、类型混淆和元数据替换绕过；11 条均已从 `ACCEPTED` 变为 `REJECTED` 并固化为
  回归测试。
- 修正口径下的行动死亡测试仍为 `NOT_SUPPORTED`。完整方法没有优于 matched AMG；各方法的
  `search_error_rate` 完全相同，search 输出没有形成可辨别的行动收益。
- Task 7 v0.4 的失败不是 conditional target（条件目标）错误，而是旧前向重采样已经删除历史
  支撑。新增 ESS-gated（有效样本量门控）可逆修订候选在新 holdout seed 上仍失败，未被事后改成
  PASS。
- Task 8 v0.4 的 strongest matched two-stage（最强匹配两阶段）臂是同一个 joint posterior
  （联合后验）的 chain-rule factorization（链式法则分解）。新 16-cell 审计在后验、策略和效用上
  均达到约 `1e-16` 数值等价，因此当前实验不能把差异识别为“联合表示本身的优势”。
- Task 7/8 历史 v0.4 失败均保持不变；七算子授权仍为 `false`。完整统一框架的隐藏事件、多人物、
  开放世界未知、可逆归因和具身反馈能力均未删除或缩小。

## 1. Search utility 指标对抗审核

### 1.1 修复后的唯一语义链

`SearchPlan` 是计划、命中、检查容器数和路径长度的唯一语义来源；`SearchUtilityContract` 是成本
与时间的唯一价格来源。不存在 contract 时，route-A primary utility（路线 A 主效用）保持
unresolved（未解析）并失败关闭，旧启发式数值只保留为 secondary diagnostic（次级诊断）。

完整 action-day row 现在保留 raw plan、target、registered-location count 和 contract；顶层报告从
这些原始字段重算日级分数、method aggregates（方法聚合）、legacy comparison（旧比较）和最终
scientific verdict（科学判定）。

### 1.2 原指标伪造路径

以下 5 条攻击均由回归验证为拒绝：

1. 空 `frozen_protocol_reference` 冒充冻结协议；
2. 负搜索成本且缺 contract identity（合同身份）；
3. 把不同 method 或不同 contract 的日级分数混入同一聚合；
4. 同时改写 raw day rows 与 aggregate metrics 后重哈希；
5. 把主指标方向改成 `maximize`，但继续使用硬编码“小于即通过”的判定。

`authorizes_paper_claim` 固定为 `false`：调用者选择的本地协议路径和自洽 hash 只能证明内部一致，
不能证明 historical authenticity（历史真实性）或 independent custody（独立托管）。

### 1.3 两轮新增对抗自查

第一轮不复用已有负例，直接攻击 Task 7/8 restructure artifact（重构工件）的阳性/后果输出链，
发现以下 4 条真实 P0：

1. 只保留 2 条 Task 7 row、同步改 aggregate 后仍可通过，未强制冻结的 16-cell 覆盖；
2. trust-chain key 齐全但 value 可任意自称可信；
3. Task 7/8 子协议身份可被替换；
4. Task 8 重复同一 factor unit、同步改 count/aggregate 后仍可通过。

修复后验证器强制 exact factor × seed × replicate coverage（精确因素×种子×重复覆盖）、唯一实验
单元、精确子协议、raw-row 派生的全部 aggregate/verdict，以及固定 trust-chain 描述；同时工件协议
升级为 `structure-two-task7-task8-restructure-evidence@0.2-development`，生成后必须再执行一次独立的
fresh recomputation（新鲜重算），仅验证存量 JSON 会失败关闭。

第二轮换到原子状态机、provenance（来源）和 JSON 类型边界，又发现 7 条可接受路径：

1. “第一步找到目标”可与 `first_choice_correct=false` 共存；
2. `location_tuple_digest` 可脱离原始位置元组伪造；
3. action scenario generator protocol（行动场景生成器协议）可替换；
4. `False` 可冒充数值 `0.0`；
5. 整数 `0/1` 可冒充因素布尔值；
6. `True` 可冒充 Task 8 的 identity temperature `1.0`；
7. artifact run date 可任意替换。

现在 action report 保留原始位置元组并重算 digest，绑定每个方法的相同 case/day coverage；生成器协议
必须精确匹配。Task 7/8 验证器拒绝 bool-as-number（布尔冒充数值），并固定 run date、冻结配置
SHA-256、阈值和决策语义。两轮攻击脚本复跑均为 `REJECTED`。

## 2. 修正指标后的行动死亡测试

运行配置：20 validation episodes + 60 sealed episodes，D0 multiseed v0.3。

工件：
`artifacts/project_two_v04_development/structure_two_action_death_test_after_metric_audit_2026_09_05.json`

- file SHA-256：`6939980978d8077c4441846b62d83f84d20d5cb5e7ee5b1f690e924ae24e0fbf`
- 80 episodes、2,560 steps、1,718 feedback events；
- `route_a_primary_utility_evaluated=false`；
- `superiority_supported=false`；
- 12 个 utility price fields 未解析；owner contamination、recovery latency、full-rerun
  equivalence 三个 hard guardrails 未测量；同时存在 secondary metric regression。

关键 sealed aggregates：

| 方法 | put-back error | cumulative action regret | owner contamination | recovery cost | search error | mean search path cost |
|---|---:|---:|---:|---:|---:|---:|
| project-two full loop | 0.142188 | 7.333333 | 0 | 0.591667 | 0.086979 | 1.155208 |
| matched AMG | 0.045313 | 4.233333 | 0 | 0 | 0.086979 | 1.181771 |

完整方法在 put-back、regret 和 recovery 上均落后 matched AMG。全部方法的 search error 都是
`0.086979`，说明当前计划生成没有把方法差异传递到搜索正确率；轻微 path-cost 差异不足以覆盖
其他行动失败，更不能在主价格合同未登记时支持论文主张。

## 3. Task 7：support-aware reversible correction（支撑感知可逆修订）

### 3.1 v0.4 失败归因

v0.4 的 local conditional kernel（局部条件核）和严格 `O(window)` 计量通过，但纠正后的
pre-rejuvenation ESS 仅约 `4–169 / 384`。固定窗口 MH 可以在“窗口外轨迹已经给定”的条件分布上
正确混合，却不能重新创造旧前向 resampling（重采样）已经删除的 prefix/suffix trajectories
（前缀/后缀轨迹）。所以增加 sweep 不能修复全局后验支撑。

### 3.2 新候选与冻结规则

新增 development protocol：
`structure-two-support-guarded-late-correction@0.1-development`。

- 纠正后 ESS ratio `>= 0.30`：保留精确 likelihood-ratio reweighting（似然比重加权）；
- ESS ratio `< 0.30`：在运行 window MH 前显式执行 fully-costed full replay（完整计费全量重放）；
- fallback 必须进入 raw row、route count 和边际成本；
- 必须同时出现本地与 fallback 两条路线，禁止以 100% full replay 冒充局部修订收益；
- belief/action 阈值与 contamination non-expansion（污染不扩张）仍保持 `0.1/0.1` 和原方向。

阈值在读取新 `scenario seed=307 / replicate seed=419` 之前冻结。

### 3.3 新 holdout 结果

工件：
`artifacts/project_two_v04_development/structure_two_task7_task8_failure_restructure_2026_09_05.json`

- artifact content SHA-256：`b99dd61b47f0b7deb43916da4a7e726fd7bb2a008e86c4470515eb21aaba3cfd`；
- file SHA-256：`8c840e7f62626eb158f667ba8ec27af7e1ba77736ff073975289eaaa9f6b6ee8`；
- 路由：1 次 `guarded_reweight`，15 次 `guarded_full_replay`；
- action guardrail：PASS；mixed-route nontriviality：PASS；
- belief guardrail：FAIL；contamination guardrail：FAIL；总体 candidate：FAIL；
- mean marginal work：`539,648.125`，低于 full replay 的 `571,808.125`；
- mean contamination：`0.00171334`，高于 full replay 的 `0.000847137`。

唯一放行的 `G12-S307-0010` 虽有 ESS ratio `0.384711`，belief max-TV 仍为 `0.138937`，污染为
`0.0142333`，而 full replay 仅为 `0.000373997`。这证明 ESS 门只检测权重方差，无法检测
stable-but-missing support（看似稳定但已缺失的支撑）。

下一次方法版本必须改变 retained inference state（保留推断状态），例如：

- correction-ready ancestry reservoir（面向纠正的谱系储备）；或
- backward-message checkpoint（后向消息检查点）。

这是并列的下一步设计选项，不在本轮替项目所有者选择。当前固定窗口方法与 ESS 路由候选均保持
失败，不得继续只增加 sweep 或调阈值。

## 4. Task 8：matched representation identifiability（匹配表示可识别性）

新增 development protocol：
`structure-two-joint-two-stage-identifiability@0.1-development`。

在新 seeds `307/311` 的 16 个因素单元、identity temperature `1.0` 下：

- max posterior L1：`7.08744e-16`；
- max action-policy L1：`4.44089e-16`；
- max absolute expected-cost difference：`5.55112e-17`；
- matched two-stage representation equivalent：`true`；
- joint representation superiority identifiable：`false`。

因此 v0.4 在 temperature `0.75` 处的微小差异是 calibration parameterization（校准参数化）
差异，不能归因为 joint representation 的方法优势。继续研究 `H+Z × C` 联合性仍可保留，但新的
可证伪问题必须由项目所有者在下列轴中选择并另行预注册：

1. online compute（在线计算）：learned joint 与 learned two-stage 在等数据、参数、延迟和状态访问
   预算下比较；
2. distribution shift（分布漂移）：等容量模型在冻结 cross-cell shift 下比较稳健性；
3. information restriction（信息限制）：joint 对不能访问交叉单元的 factorized arm；这只回答
   interaction necessity（交互项必要性），不回答相对 exact two-stage 的优越性。

## 5. 验证与信任边界

- 完整仓库：`3419 collected / 3417 passed / 1 skipped / 1 expected xfailed / 0 failed`；
- search utility、action death、Task 7/8 restructure、backbone falsifier 与 selected-method
  回归均包含在上述完整终检中；
- 触及 source/runner 的 Ruff 与 strict mypy：通过；
- 新 restructure artifact 枚举每个 positive boolean path，并从 raw rows 重算 route、guardrail、
  aggregate 和 identifiability verdict；固定 config hash 后执行独立 fresh recomputation。伪造完整
  阳性字段并重算外层 hash、trust-chain 和 result hash，仍被 semantic verifier（语义验证器）拒绝。

上述仍只能证明当前源码、冻结 development config 与工件之间的 deterministic internal consistency
（确定性内部一致）及同一进程内的二次确定性重算。没有 verifier-owned trust anchor、WORM ledger、
外部签名或独立机器 custody，因此不能证明历史执行的真实性，也不能生成正式授权回执；本报告不把
“两轮未再发现绕过”表述为“没有其他 bug”。
