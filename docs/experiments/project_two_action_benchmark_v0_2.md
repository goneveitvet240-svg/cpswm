# 项目二完整反馈闭环 action-level matched benchmark v0.2

日期：2026-08-24  
证据等级：D0 synthetic replay pilot（D0 合成回放试验）；不是论文级外部有效性证据

## 1. 实际运行的完整链

v0.2 的完整方法实际组合现有实现：

```text
ObservationDetectionResult
→ CorePrototypeSpine.process_transition
  → CHEH / ORRER branch
  → PCHMP.consume
  → actor / role / mechanism posterior
  → CF-BOCPD / CCRR / project-one reversible statistics
→ search / put-back action
→ ExecutionFeedbackRecord
→ ExecutionFeedbackProjector
→ ProjectTwoFeedbackRevisionLoop.ingest_feedback
→ new ORRER revision
→ EventRevisionOutcome
→ typed ProjectOneStatRequest
→ apply_project_one_request
→ CorePrototypeSpine.apply_project_one_stat_request
→ next action decision from revised statistics
```

没有复制 CHEH、ORRER、PCHMP、ExecutionFeedbackProjector 或项目一统计栈。聚焦测试用 spy 验证真实 feedback loop 和显式项目一接口确实被调用。测试还暴露并修复了一个既有接口错误：项目一 owner posterior（主人后验）此前漏掉 unknown-mechanism mass（未知机制质量），导致 `owner_mass_before` 与项目二请求不一致；现已与 ORRER 边际定义对齐。

Sealed test 两个 case 中，完整方法分别执行 21/19 次真实反馈 revision，产生 21/19 个 `ProjectOneStatRequest`，其中 18/16 个应用到已晋升的项目一统计；其余 6 个请求对应仍在 quarantine（隔离区）、尚无可撤销 live statistic（活动统计）的事件。这是保留在报告中的接口/证据缺口，不被算作成功应用。

## 2. 公平性与 baseline 身份

所有非-oracle 方法获得完全相同的 visible episode hash（可见 episode 哈希）、robot-visible observation、execution feedback、actor/mechanism/role evidence、32-step action budget、observation coverage 和 delayed-feedback schedule。Truth envelope 只在方法完成预测后由 evaluator 读取。

| 方法 | 报告身份 | 独立调参 | 说明 |
|---|---|---:|---|
| frequency / recency / Markov | faithful/matched（忠实/匹配的经典基线） | 3 configs/方法 | validation-only |
| Damen–Hogg AMG open-world adaptation | faithful/matched adaptation（忠实匹配适配） | 3 configs | 调用现有 `DamenHogg2012AMGMatchedEvidenceBaseline.predict_matched`，获得相同 actor/mechanism/ordered-role evidence |
| O-STaR | matched replay adapter（匹配回放适配） | 3 configs | 缺语言/图/具身技能输入，不冒充忠实复现 |
| DynaMem | matched replay adapter | 3 configs | 缺 RGB-D、pose 与 voxel memory，不冒充忠实复现 |
| STAR | matched replay adapter | 3 configs | 缺 caption/VLM 与真实 temporal/spatial tools，不冒充忠实复现 |
| full rerun without reversible revision | full-rerun control（完整重跑对照） | 3 configs | 每次从全部可见日志重建，不用可逆索引 |
| project two full feedback loop | full project two（完整项目二） | 3 configs | owner threshold 0.4/0.5/0.6 |
| oracle upper bound | oracle upper bound（oracle 上界） | 不调参 | 唯一允许 evaluator truth 的评分臂 |

Validation seeds = {101, 103}；sealed test seeds = {211, 223}。四个 episode 在 household、scene、object-family 三个维度完全互斥。每种非-oracle 方法搜索预算均为 3；选择目标只使用 validation put-back error，test episode IDs 在 tuning receipt 中必须为空。

## 3. D0 held-out 结果

差值定义为 `baseline − project_two`；对 error/cost 指标，正值表示项目二更好。95% CI 是以 test episode 为配对单位的 deterministic paired bootstrap（确定性配对自助法）区间。**这里只有两个 test household，区间极不稳定，不能当作论文级统计证据。**

### Primary metrics

| 方法 | put-back error | cumulative regret | owner contamination | recovery cost |
|---|---:|---:|---:|---:|
| project two full | 0.3438 | 16.50 | 0.0156 | 5.50 |
| frequency | 0.4688 | 20.50 | 0.0938 | 6.00 |
| recency | 0.3281 | 16.00 | 0.2188 | 2.25 |
| Markov | **0.2344** | **13.00** | 0.0938 | **1.00** |
| matched open-world AMG | **0.0938** | **8.50** | **0.0000** | **0.00** |
| O-STaR matched adapter | 0.4063 | 18.50 | 0.1875 | 4.00 |
| DynaMem matched adapter | 0.3281 | 16.00 | 0.2188 | 2.25 |
| STAR matched adapter | 0.4531 | 20.00 | 0.1875 | 4.00 |
| full rerun | 0.4688 | 20.50 | 0.0938 | 6.00 |
| oracle | 0.0000 | 0.00 | 0.0000 | 0.00 |

项目二自身按 test episode bootstrap 的 value CI 分别为：put-back `[0.2813, 0.4063]`、cumulative regret `[15, 18]`、owner contamination `[0, 0.0313]`、recovery cost `[5, 6]`。这些仍只有两个 episode，不应外推。

关键 paired differences（baseline − project two）：

- matched AMG：put-back paired mean `−0.2500`；regret `−8.00`。项目二明确失败。
- Markov：put-back `−0.1094`；regret `−3.50`；recovery cost `−4.50`。项目二失败。
- frequency/full rerun：put-back `+0.1250`；regret `+4.00`；但这不是 strongest-baseline 胜出。
- owner contamination：项目二与 matched AMG/oracle 打平为 0；优于 frequency、recency、Markov、O-STaR、DynaMem、STAR 和 full rerun。由于 test n=2，除部分对比外不把统计区间当作稳定结论。

统计显著性与工程显著性在 machine-readable report（机器可读报告）中分开记录。工程阈值为 rate/contamination 绝对差至少 0.02，其他 cost 至少 0.1；工程差异不能替代 CI 或外部有效性。

### Secondary metrics：项目二完整方法

| 指标 | mean | worst group |
|---|---:|---:|
| search error / success | 0.1719 / 0.8281 | 0.1875 / 0.8438 |
| mean search path length / normalized cost | 1.2031 / 1.2031 | 1.2188 / 1.2188 |
| mean search time | 6.0156 s | 6.0938 s |
| late-feedback recovery latency | 5.50 | 6.00 |
| unnecessary revisions | 0 | 0 |
| unknown calibration Brier | 0.0698 | 0.0713 |
| provenance/dedup rejection correctness | 1.0000 | 1.0000 |

每个 seed/case 的全部 primary/secondary 指标、每种方法的 aggregate、worst group、paired difference、95% CI、统计显著性和工程显著性均由 runner 的 `ProjectTwoActionBenchmarkReport` 输出；未在本文手工省略的维度不会丢失。

## 4. 判决

当前结论是：**不满足论文级 superiority（优越性）**。

- 胜出：相对 frequency/full rerun，项目二的均值在 put-back、regret、contamination 上较好，但 CI 触及 0；相对多种代理和经典基线，owner contamination 是主要优势。
- 打平：owner contamination 与 matched AMG、oracle 均为 0；search error 与多数非-oracle 方法相同。
- 失败：matched AMG、Markov、recency 在 put-back error 和 cumulative regret 上优于项目二；matched AMG 和 Markov 的配对区间不跨 0。项目二 recovery cost 也明显落后于 AMG/Markov。

失败定位到当前行动读出与恢复路径，而不是删除能力：完整链已运行，但项目二的可逆反馈收益没有及时转化为 next-action put-back 和 recovery 优势；同时 6 个 stat request 遇到 project-one event 尚未晋升，暴露 quarantine-to-feedback handoff（隔离到反馈交接）门仍需明确处理。项目二的开放世界、隐藏事件、多行为人、可逆归因、项目一回流和具身反馈范围全部保留，下一步方向由用户决定。

## 5. 未过门禁

- D0 pilot 只有 2 validation + 2 test households，不能支持论文级 CI；
- D0 已加入 unknown actor / unknown mechanism truth，但每类只有 4 个 episode-step；
- O-STaR、DynaMem、STAR 是 matched replay adapter；缺少忠实复现所需的 RGB-D/pose/voxel/caption/embodied-tool 输入；
- D1 simulator、D2 real perception、D3 household、D4 robot execution 均未进入；
- 没有真实传感器标定、pose covariance、post-action destination observation；
- 没有真实机器人 search/place/transfer 时间、路径、能耗、失败模式与隐私成本。

运行入口：`apps/evaluation_runner/run_structure_two_action_death_test.py`。旧 `StructureTwoActionDeathTest` 仅保留为 v0.1 regression proxy（回归代理），不再代表完整项目二 benchmark。

---

## 更正声明（append-only，2026-09-05）

本节为事后追加，**不修改**上文任何历史数值。完整更正见
`docs/experiments/structure_two_search_utility_correction_2026-09-05.md`。

1. 上文 §3 的 primary/secondary 数值**不受**结构二 search-utility bug 影响：v0.2/v0.4 的
   `search_error_rate` 与 `mean_search_path_cost` 都从同一个 `_Prediction.search_order`
   读出，从未按方法类别猜测搜索策略。
2. 但 §3 Secondary metrics 表中的两个量依赖**未注册常数**，引用时必须一并说明：
   - `mean search time` = `5.0 秒 × 路径长度`，该常数没有任何冻结协议来源；
   - 真值位置不在搜索计划内时，路径代价按 `len(known_locations)` 计入，该失败惩罚同样未注册；
   - `mean search path length`、`normalized cost` 与 `mean_search_cost` 是同一个量
     （每步平均检查容器数）的三个名字，不是三次独立测量。
   这三条现在由报告字段 `unregistered_search_metric_assumptions` 显式输出。
3. 冻结的组合 A 路线只指定 primary utility 为 cumulative action regret，**未**冻结它的组成项
   权重、单位、搜索路径代价项与失败惩罚。因此报告新增
   `route_a_primary_utility_evaluated=false` 与 `unresolved_utility_contract_fields`，
   `superiority_supported` 失败关闭。§4「不满足论文级 superiority」的判决**不变**，
   但其依据现在由结构化的 `scientific_verdict` 给出，而不是散落的字符串。
4. 文末提到的旧 `StructureTwoActionDeathTest` v0.1 regression proxy：它的
   `search_cost` / `mean_search_cost` **全部撤销**，现由
   `structure-two-action-death-test@0.2-search-utility-corrected` 取代；旧协议标识保留，
   旧计价函数以 `withdrawn_v0_1_search_cost` 保留但永不参与评分。

---

## v0.5 后续取代声明（append-only，2026-09-06）

v0.4 的数值不删除，但其“最佳参考方法”比较集合与 validation selection objective（验证选择目标）
已被 v0.5 取代：

- v0.4 只让 `faithful_matched` 与 `full_rerun_control` 进入 route-A verdict，错误漏掉了 matched AMG
  及三个匹配适配器；
- v0.4 的参数选择只最小化 put-back error，与它报告的 primary utility 不一致；
- v0.5 将所有 non-oracle 方法纳入否证，并按同一个开发版 cumulative action regret 选择参数与评分；
- v0.5 仍保留 `route_a_primary_utility_evaluated=false`，因为开发合同不替代论文级真实成本与护栏。

新结果见
`docs/experiments/structure_two_route_a_development_utility_v0_5_2026-09-06.md`。

---

## v0.6 后续取代声明（append-only，2026-09-06）

v0.5 的失败结果继续保留。v0.6 只在 TRAIN 上诊断行动读出机制，冻结三个等预算快／慢可逆读出
候选，在 validation 选择后使用全新的 `6001--6060` development holdout。完整系统取得
`3.455556` 对 matched AMG `3.933333` 的开发累计行动遗憾优势，但污染护栏、真实成本、外部
原声复现和独立托管仍关闭。详见
`docs/experiments/structure_two_action_readout_v0_6_2026-09-06.md`。
