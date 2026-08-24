# 项目一评测协议 v0.2

日期：2026-08-23
状态：`阶段 0–7 已落地；结论仍为 UNDERPOWERED，不支持任何方法优越性主张`
性质：**评测协议与首批结果**，不是论文证据。

v0.2 相对 v0.1 修了三个会让读数失真的问题，并把 BOCPD 基线换成信息对等版本。
**v0.1 的全部数字作废**——其中链式 arm 的 log-loss 是偷看来的。

---

## 0. 范围边界（只说一次）

协议覆盖**习惯变化判断链**：Dirichlet predictive surprise、RLS residual、由二者
导出的 habit signal、joint CF-BOCPD 变化概率、CCRR 路由决策、结果 active regime。

不覆盖 `CorePrototypeSpine` 同时集成的 ORRER/PCHMP 事件层与 hybrid RGRC 账本。

`prototype_spine.py` 冻结，只消费不修改。协议层的 surprise 公式直接 `import`
spine 的私有实现，spine 改动会在此立刻报错而不会静默分叉。

本次仍**没有修改** `evaluation_operations/__init__.py`（项目二在改），全部用全路径导入。

---

## 1. v0.2 修了什么

### 1.1 prediction timing（这条最严重）

v0.1 里链式 arm 的 `predicted_location_probabilities` 取自 **吸收当前事件之后**
的后验，而 `context_frequency` 取自**之前**的先验。等于链式 arm 在被打分的那道题上
先看了答案。

修法是结构性的：`_BaseMethod.observe` 变成模板方法，顺序固定为
**预测 → 决策 → 学习**，子类只实现 `_predict`（只能读事件前状态）和 `_step`。

代价立刻可见：

| | v0.1（泄漏） | v0.2（修复后） |
|---|---:|---:|
| 链式 arm log-loss | 0.390 | **0.529** |
| context_frequency log-loss | 0.623 | 0.623 |

链式 arm 原本 0.23 的 log-loss 优势，有 0.14 是偷看来的。

> 注意：在学习前读 `event.observed_location` **不是**泄漏——surprise 和 residual
> 的定义就是"先验对随后看到的东西错得多离谱"，它们读的是产生预测的同一个事前状态。

通用防泄漏测试 `test_no_arm_peeks_at_the_event_it_is_scored_on`：两条只在**最后一个
事件位置**不同的流，最后一步的位置概率必须完全相同。七个 arm 逐个参数化验证。

### 1.2 所有配置字段真实生效，并写入 artifact

- `rls_regularization` 之前**声明了但从未使用**，现在传给
  `RLSHabitScoreHead(ridge=...)`。默认值改成 `1e-6`（该类自己的默认），所以接线
  本身不改变行为。`test_the_rls_regularization_field_actually_reaches_the_head`
  用两个 ridge 值产生不同 residual 来证明它活着。
- 基线参数之前是硬编码的，既不能独立调参也无法审计。现在每个基线有自己的
  `CategoricalBOCPDConfig` / `ContextFrequencyConfig` / `PersistenceConfig`。
- 每个 arm 实现 `config_payload()` 与 `config_hash()`；runner 把它们写进
  `ArmRunResult`，benchmark 写进 `metrics.json` 的 `arm_configs`，并逐行写进
  `predictions.jsonl`。
- 顺带发现一个协议/spine 不一致：协议允许 `confirmation_window >= 1`，而冻结的
  `PrototypeLoopConfig` 要求 `>= 2`——调参扫到 1 时才会在运行中途炸。已收紧并加测试。

### 1.3 BOCPD 换成 categorical / context-matched

v0.1 的 BOCPD 跑的是二元"是否移动"指示量，而链式 arm 看到完整分类位置 + 上下文。
那是被削弱的基线，削弱的基线不构成证据。

v0.2 是 Dirichlet-multinomial changepoint 模型，观测量是**位置类别**，每个游程的
充分统计量按 `context_key` 分层——与链式 Dirichlet 同一个 pooling 层级。

效果：在 morning 上下文预测 dining_table 0.734，evening 上下文预测 desk 0.736。
`test_categorical_bocpd_ranks_locations_a_binary_detector_cannot` 断言它能把
"同上下文里偶尔出现"和"从未出现"排序——二元指示量根本没有这个表示能力。

log-loss 相应从 0.607 提升到 0.560。

> 读数约定：常数 hazard 下 Adams–MacKay 递推给出 `P(r_t=0) ≡ H`，changepoint 分支
> 与 growth 分支共用同一组 per-run predictive，归一化后正好抵消成 hazard。拿它当
> 变化概率会让这个基线由构造得到直线。所以变化信号取**短游程后验质量**（`r ≤ 1`）。

### 1.4 same-context test 延伸到 change probability 与 decision

原本只断言 residual 和 habit_signal。现在加了变化概率排序、四类 decision、以及
"单次异常不得被确认为习惯变化"（应为 `INSUFFICIENT_EVIDENCE`，确认窗口的护栏）。

**决策层暴露了出厂接线更严重的后果**（anomalous 分支）：

| calibration | full | no_rls | shuffled | rls_only |
|---|---:|---:|---:|---:|
| `as_is`（出厂） | 0.9728 | 1.0000 | 0.9416 | **0.2135 → decision 停在 STABLE** |
| `raw_clip`（修复） | 1.0000 | 1.0000 | 1.0000 | 1.0000 |

出厂接线下 `rls_only` **根本没能把异常报出来**；而给 surprise 加上出厂 residual
反而**压低**了 full 的变化概率（0.9728 < no_rls 的 1.0000），因为 residual 底噪
把平常日子的 habit 通道也抬高了，变点检测器于是学会了"高 habit 信号是常态"。

---

## 2. 阶段 1：same-context matched test

两分支看到的一切都相同（object、actor、context_key、context_value、时间槽、观测
质量、完整 12 周期学习前缀）。前缀结束在 evening，两分支上一位置都是书桌，
`habit_transition` 都等于 1。唯一差异是最后一个早晨杯子在餐桌还是阳台。

### 缺陷本身

`RLSHabitScoreHead.score_candidates` 默认 `apply_sigmoid=True`，但底层是已经拟合到
`{0,1}` 目标的最小二乘回归——**它的原始输出就是分数**。再套一层 sigmoid：

```text
完美学到的  1.0  ->  sigmoid(1.0) = 0.7311  ->  residual = 0.2689
完美排除的  0.0  ->  sigmoid(0.0) = 0.5000  ->  residual = 0.5000
```

residual 被压进 `[0.269, 0.5]`，只剩约四分之一量程，正确预测的事件永远带 0.269
的常数底噪；经 `1-(1-r)²` 后任何一次移动的 habit signal 都不低于 **0.466**。

`test_the_rls_head_learns_the_context_perfectly_before_the_sigmoid` 证明模型本身
没问题：`apply_sigmoid=False` 时原始分数正好是 `[1.0, 0.0, 0.0, 0.0]`。

---

## 3. 阶段 5 的四条 residual 路线对比（供你决定）

`ResidualCalibration` 现在有五个取值，都**不修改**冻结的 spine 或共享的 RLS head：

| 路线 | 做法 | 假设 |
|---|---|---|
| `as_is` | 原样使用 | 复现出厂行为 |
| `logit` | 反解 sigmoid，取 `\|1-raw\|` 截到 1 | 无 |
| `raw_clip` | 反解后先把 raw 夹进 `[0,1]`，再取 `1-raw` | raw 落在 `[0,1]` |
| `recenter` | 把 `[sigmoid(0), sigmoid(1)]` 仿射映回 `[0,1]` | 同上；不需要反解 |
| `platt` | 在线经验校准 `P(hit \| score)` | 无，但有冷启动 |

关键分歧点在**过度自信**的分数（raw > 1，即 score > 0.731）：

| score | as_is | logit | raw_clip | recenter |
|---|---:|---:|---:|---:|
| 0.7311 | 0.2689 | 0.0 | 0.0 | 0.0 |
| 0.5000 | 0.5 | 1.0 | 1.0 | 1.0 |
| **0.9000** | 0.1 | **1.0** | **0.0** | **0.0** |

`logit` 把过度自信当成"错得离谱"，方向是反的。**这排除了 logit。**

十场景基准（链式 arm，固定阈值，平均）：

| route | full 配对间隔↑ | shuffled 配对间隔 | full 误切换↓ | full 伪 regime↓ |
|---|---:|---:|---:|---:|
| `as_is` | 0.055 | 0.052（≈full） | 0.024 | 3 |
| `logit` | 0.126 | 0.095 | 0.009 | 2 |
| **`raw_clip`** | **0.126** | 0.095 | **0.009** | **2** |
| `recenter` | 0.127 | 0.095 | 0.009 | 2 |
| `platt` | 0.069 | 0.052 | 0.015 | 3 |

`raw_clip` 与 `recenter` 实测上无法区分（0.126 vs 0.127）；`platt` 因冷启动明显更差，
并重新引入了 0.084 的 residual 底噪。

### 建议（决定权在你）

1. **真正的修法是在源头**：让 `RLSRegimeBank.score_candidates` 透传
   `apply_sigmoid=False`。那样评测层这四条路线全都不需要。但那个文件同时服务
   项目二，所以是你的决定。
2. 源头修好之前，评测层用 **`raw_clip`**：它恢复模型真实输出，且把过度自信正确地
   当作零误差。
3. **`platt` 不要丢**——真实数据上 raw 分数未必落在 `[0,1]`，那时它是唯一不做量程
   假设的路线。现在差只是因为合成流太短、桶里没数据。

---

## 4. 阶段 6 重跑：固定阈值（10 场景平均，`raw_clip`）

| arm | 误报↓ | 误切换↓ | 异常检出↑ | 变化确认↑ | 伪 regime↓ | 配对间隔↑ | logloss↓ |
|---|---:|---:|---:|---:|---:|---:|---:|
| full | 0.030 | 0.009 | 0.067 | **0.400** | 2 | **0.126** | 0.528 |
| no_rls | **0.014** | **0.004** | 0.067 | 0.250 | **1** | 0.131 | 0.528 |
| shuffled_rls | 0.033 | 0.009 | 0.067 | 0.300 | 2 | 0.095 | 0.527 |
| rls_only | 0.030 | 0.009 | 0.067 | 0.400 | 2 | 0.126 | 0.528 |
| categorical_bocpd | 0.049 | 0.049 | 0.000 | 0.000 | **0** | −0.062 | 0.560 |
| context_frequency | **0.000** | **0.000** | 0.100 | 0.250 | **0** | 0.092 | 0.623 |
| persistence | 0.151 | 0.151 | **0.167** | 0.400 | **0** | 0.015 | 0.669 |

---

## 5. 阶段 7：独立调参

每个 arm **自己的网格、相同预算（12 点）**；只在 validation 上选择；TEST 跑一次。
按**场景**划分而不是按事件——事件划分会把同一个 regime 的历史泄漏进它自己的测试半边。

选择规则写在输出里而不是藏进加权分：`max(confirmation_rate − false_switch_rate)`，
延迟低者优先。完整 Pareto 前沿一并保存。

- validation：`stable_habit` `short_disturbance` `permanent_change` `context_change` `gradual_drift`
- test：`periodic_habit` `recurring_regime` `missing_observations` `biased_observation` `abrupt_change`

### TEST 结果（跑一次）

| arm | 变化确认↑ | 误切换↓ | 误报↓ | 异常检出↑ | logloss↓ |
|---|---:|---:|---:|---:|---:|
| full | **0.400** | **0.000** | **0.000** | 0.133 | 0.562 |
| rls_only | **0.400** | **0.000** | **0.000** | 0.133 | 0.562 |
| **shuffled_rls** | **0.400** | **0.000** | 0.017 | 0.133 | 0.559 |
| no_rls | 0.300 | **0.000** | **0.000** | 0.133 | 0.561 |
| context_frequency | 0.300 | **0.000** | **0.000** | 0.000 | **0.544** |
| categorical_bocpd | 0.000 | 0.049 | 0.049 | 0.000 | 0.593 |
| persistence | 0.400 | 0.213 | 0.213 | 0.133 | 1.180 |

### 这张表说明什么

**独立调参之后，`shuffled_rls` 在 TEST 上追平了 `full`（0.400 vs 0.400）。**

按你自己阶段 10 的结论分级表，这正是「Shuffled 与 Full 相同 → RLS residual 可能
只是尺度信号」那一行——**而且这次是在 `raw_clip` 下，不是出厂接线**。

但在下这个结论之前必须看清楚它的统计强度：

1. validation 上 full=0.400、shuffled=0.200，差异是存在的，只是没活到 test。
2. TEST 只有 5 个场景、单 seed，变化点总数是个位数，confirmation rate 的**最小
   刻度就是 0.2**。0.300 与 0.400 之间只差**一个事件**。
3. `full` 的 Pareto 前沿上 6 个非支配点的 (fsw, conf) **完全相同**——说明在这批
   场景上，链式 arm 的阈值几乎不起作用。场景没有压到阈值。

**因此当前判决是 `UNDERPOWERED`，不是 `shuffled == full`。** 这个规模的实验既不能
证明 residual 有用，也不能证明它没用。

另外两条必须记的：

- **`context_frequency` 的 log-loss 最好（0.544）**，比链式 arm 好。地板基线在
  位置预测上赢了。
- `categorical_bocpd` 调参后 TEST 确认率仍是 0.000。它选到 `run_length=20,
  threshold=0.2`，但在测试场景上短游程质量没有到过 0.2。这是基线的真实读数，不是
  被削弱的结果。

---

## 6. 产物清单

```text
src/cpswm/system/evaluation_operations/project_one_protocol.py    冻结接口 + 五条 residual 路线 + 全部 config hash
src/cpswm/system/evaluation_operations/project_one_dataset.py     记录/真值/流/manifest
src/cpswm/system/evaluation_operations/dataset_adapters.py        adapter 抽象
src/cpswm/system/evaluation_operations/project_one_scenarios.py   十个确定性场景
src/cpswm/system/evaluation_operations/project_one_methods.py     预测时序模板 + 七个 arm
src/cpswm/system/evaluation_operations/project_one_metrics.py     逐步指标 + 配对差值
src/cpswm/system/evaluation_operations/project_one_runner.py      统一 runner（含 config hash）
apps/evaluation_runner/generate_project_one_scenarios.py          场景落盘
apps/evaluation_runner/run_project_one_benchmark.py               固定阈值基准
apps/evaluation_runner/tune_project_one.py                        独立调参 + Pareto
configs/project_one/default.yaml                                  默认配置
tests/test_project_one_protocol.py                                阶段 0 验收
tests/test_project_one_same_context_rls_ablation.py               阶段 1 matched test
tests/test_project_one_dataset_contract.py                        阶段 2 验收
tests/test_project_one_evaluation_runner.py                       阶段 3/4 验收 + 防泄漏
```

复现：

```bash
PYTHONPATH=src python apps/evaluation_runner/run_project_one_benchmark.py \
  --output artifacts/project_one/fixed --calibration raw_clip
PYTHONPATH=src python apps/evaluation_runner/tune_project_one.py \
  --output artifacts/project_one/tuning --calibration raw_clip
```

---

## 7. 下一步（按依赖顺序）

1. **处置 sigmoid 双重压缩**（见 §3.建议）。这是你的决定。
2. **加多 seed**——当前所有结论都卡在 `UNDERPOWERED`。阶段 3 步骤 5 的多 seed 随机
   版本现在是**最高优先级**，没有它后面每一步都得不出结论。
3. 查异常检出率只有 0.133 的原因。
4. 阶段 5 补齐：EWMA、CUSUM、RLS-fixed-threshold、No-CF-BOCPD、No-CCRR、
   No-regime-reactivation。
5. 按匹配 FPR / 匹配 TPR / 匹配检出率分别重报（现在 fsw 基本全是 0，匹配报告还没有
   意义；要等场景能压到阈值之后）。

阶段 8（半合成与真实数据）和阶段 9（LLM 三种角色）接口已经就位：新数据源只需要一个
adapter，LLM 语义解析器的输出目标就是 `ProjectOneDatasetRecord`。
