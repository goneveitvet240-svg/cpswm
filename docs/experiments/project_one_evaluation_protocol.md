# 项目一评测协议 v0.3

日期：2026-08-23
状态：`阶段 0–7 已落地；结论仍为 UNDERPOWERED`
性质：**评测协议与结果**，不是论文证据。

v0.3 修了六个会让读数失真的问题。**v0.2 的调参结论作废**（选择规则里没有异常检出，
shuffled 不是真 derangement，matched pair 的前缀已经分叉）。

---

## 0. 范围边界

协议覆盖**习惯变化判断链**：Dirichlet predictive surprise、RLS residual、habit
signal、joint CF-BOCPD 变化概率、CCRR 路由决策、active regime。不覆盖 ORRER/PCHMP
事件层与 hybrid RGRC 账本。

`prototype_spine.py` 冻结，只消费不修改。surprise 公式直接 `import` spine 的私有
实现，spine 改动会立刻报错而不会静默分叉。仍未修改 `evaluation_operations/__init__.py`
（项目二在改），全部用全路径导入。

---

## 1. v0.3 修了什么

### 1.1 `config_hash` 覆盖完整 payload

v0.2 的链式 arm 只哈希 `ProjectOneProtocolConfig`。owner、household、object、候选
位置集合、shuffle 种子**都不进哈希**——两个实质不同的 arm 会共享同一个身份，存下的
结果就再也追不回来。

现在 `_BaseMethod.config_hash()` 统一返回 `content_sha256(config_payload())`，四个
子类的覆盖全部删掉。

### 1.2 Shuffled 改成严格 derangement

v0.2 用固定滞后。那不是 derangement：

- residual 序列里**大量重复值**（`as_is` 下正确预测一律是 0.269），滞后经常把一个值
  映射到相同的值；
- **前 lag 步没有历史**，v0.2 填 0.0，等于那几步静默退化成 `NO_RLS`。

v0.3 新增 `prime()` 钩子（runner 在 `reset()` 之后、回放之前调用一次）。shuffled arm
在 `prime()` 里跑一份配置为 `FULL` 的自身影子副本，拿到它自己会产生的 residual 序列，
再用带种子的**严格 derangement**（无不动点的置换，用邻位交换修复残余不动点）打乱。

- 严格性定义在**索引**层，不在值层：强行要求每个值都变会扭曲边缘分布，而边缘分布正是
  这个消融唯一必须保留的东西。恰好取到相同值的位置数写进 arm 的 snapshot
  (`derangement_unchanged_values`)，而不是工程掉。
- 这是**离线**的，这就是这个 arm 的诚实代价：它是消融，永远不是可部署方法。文档和
  Protocol docstring 都写明了。
- 如果有人绕过 runner 直接调 `observe()`，未 prime 的步骤会返回**自己的**residual 并
  计入 `unprimed_shuffle_steps`——绝不静默变成 FULL。

### 1.3 共享 snapshot 的 final-step intervention

**v0.2 的 matched pair 名不副实。** 让两个 ablation 跑同一段前缀并不会让它们状态相同：
habit signal 从第一步就不同 → 隔离决策不同 → 学到的计数不同，早在被研究的那一步之前
就已经分叉了。

v0.3 的 `_warm_snapshot()` 只训练**一个** arm，每个分支都是它的 `copy.deepcopy`，
`clone_with(ablation=..., residual_calibration=...)` 只替换读取路径，Dirichlet 计数和
RLS bank 原样带过去。测试断言 `first.residual_history == second.residual_history ==
warm.residual_history`，并断言 clone 写不回 snapshot。

shuffled 是流级消融（一个元素的 derangement 没有意义），它的逐点形式用
`pointwise_residual_override` 从 arm **自己的**前缀边缘分布里取一个值——同量级、错配对。
该字段消费后立即清空，有测试保证不会泄漏到后续步骤。

**这个改动立刻暴露了 v0.2 藏起来的东西**：拿一个在 `raw_clip` 下训练好的模型，用
`as_is` 去读一个完全正常的事件，0.269 的 residual 底噪把 habit signal 注入到 0.466，
而变点检测器是在一个接近 0 的通道上标定的——于是**在模型预测正确的事件上变化概率冲到
~1**。同样用 `as_is` 训练**并**读取时效果弱得多，因为检测器把底噪吸收成了常态。

所以这个文件里有两个 helper，各答各的问题：

| helper | 问题 | 用于 |
|---|---|---|
| `_run_branch` | 给定一个训练好的模型，读取路径对这一个事件做了什么 | **消融**对比 |
| `_run_consistent` | 训练和读取用同一条路线时，整体是什么 | **校准路线**对比 |

用一条路线训练的快照去用另一条路线读取，测的是**失配**，不是路线。

### 1.4 benchmark 与 tuner 的 calibration 统一

v0.2 里 benchmark 默认 `as_is`、tuner 默认 `raw_clip`。两个入口各自挑默认值，正是
两次结果不可比而没人发现的原因。现在两边都读
`DEFAULT_RESIDUAL_CALIBRATION_NAME`（= `raw_clip`），`ProjectOneProtocolConfig` 的
默认值也是它。

### 1.5 `PLATT` 更名 + 实现真正的 Platt scaling

v0.2 里叫 `PLATT` 的其实是**分桶经验直方图**——它声称了一个自己没实现的方法。

- 直方图更名为 `HISTOGRAM`（`HistogramResidualCalibrator`）。
- 新增真正的 `PLATT`（`PlattResidualCalibrator`）：一维逻辑回归
  `P(hit|s) = 1/(1+exp(A·s+B))`，用 Platt 自己的**目标平滑**
  `t₊=(N₊+1)/(N₊+2)`、`t₋=1/(N₋+2)` 在线梯度拟合。

实现过程中抓到自己的一个符号错误：`z = A·s+B`、`p = sigmoid(-z)` 时
`d(log-loss)/dz = t − p`，**下降要减**。第一版写成了加，结果对一个真实命中率 1/4 的
分数报出 `P(hit)=1`。代码里留了注释。

还做了一件必要的事：**对 score 做 Welford 标准化**。`as_is` 路线下 head 的全部信息量程
只有 `[0.5, 0.731]`——0.231 宽，未标准化的拟合需要 −33 量级的斜率，会爬得很慢；而
`raw_clip` 下同样的数据铺满整个单位区间，立刻收敛。不标准化的话，这条路线在 `as_is`
上显得差的原因将是**条件数而不是方法**，路线对比就变成了在测条件数。

标准化后两种量程收敛完全一致（8 次更新后 residual(命中)=0.002 / residual(未命中)=0.856）。

### 1.6 异常检出进入调参目标与 Pareto 门

v0.2 的选择规则是 `confirmation − false_switch`，**完全没有异常检出**——等于宣布短期
扰动能力不重要。

v0.3 的规则四项俱全，权重可在命令行覆盖，并写进 artifact：

```text
utility =  w_confirm * 变化确认率
         + w_anomaly * 异常检出率
         - w_switch  * 误切换率
         - w_alarm   * 误报率
```

Pareto 前沿升为**三维**：`(误切换↓, 变化确认↑, 异常检出↑)`。少了第三个轴，一整项能力
会从搜索里消失。

---

## 2. 阶段 6 重跑：固定阈值（10 场景平均）

链式 arm 随 residual 路线的变化：

| route | arm | 误报↓ | 误切换↓ | 确认↑ | 伪 regime↓ | 配对间隔↑ |
|---|---|---:|---:|---:|---:|---:|
| `as_is` | full | 0.040 | 0.024 | 0.400 | 3 | 0.055 |
| | shuffled | 0.044 | 0.024 | 0.400 | 3 | **0.047**（≈full） |
| `raw_clip` | **full** | 0.030 | 0.009 | 0.400 | 2 | **0.126** |
| | shuffled | 0.033 | 0.009 | 0.400 | 2 | 0.098 |
| `recenter` | full | 0.030 | 0.009 | 0.400 | 2 | **0.127** |
| `platt` | full | 0.030 | 0.015 | 0.400 | 3 | 0.094 |
| `histogram` | full | 0.030 | 0.015 | 0.400 | 3 | 0.069 |

基线（不随 residual 路线变化）：

| arm | 误报↓ | 误切换↓ | 检出↑ | 确认↑ | logloss↓ |
|---|---:|---:|---:|---:|---:|
| categorical_bocpd | 0.049 | 0.049 | 0.000 | 0.000 | 0.560 |
| context_frequency | **0.000** | **0.000** | 0.100 | 0.250 | **0.544** |
| persistence | 0.151 | 0.151 | **0.167** | 0.400 | 0.669 |

**路线排序**：`recenter` (0.127) ≈ `raw_clip` = `logit` (0.126) > `platt` (0.094)
> `histogram` (0.069) > `as_is` (0.055)。

真 Platt 明显优于直方图分箱——短流上参数化形式比逐桶冷启动收敛快得多，这正是重实现
（而不是只改个名字）该得到的结果。

`logit` 仍然**不推荐**：过度自信的分数（raw > 1）它给出 residual = 1.0，方向是反的。
`raw_clip` 和 `recenter` 给 0.0。

---

## 3. 阶段 7 重跑：独立调参（权重全 1.0）

每个 arm 自己的网格、相同 12 点预算、按场景划分、TEST 跑一次。

| arm | val utility | **test utility** | 确认↑ | 检出↑ | 误切换↓ | 误报↓ | logloss↓ | Pareto |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| rls_only | +0.321 | **+0.533** | 0.400 | 0.133 | 0.000 | 0.000 | 0.562 | 6 |
| **full** | +0.321 | **+0.533** | 0.400 | 0.133 | 0.000 | 0.000 | 0.562 | 6 |
| shuffled_rls | **+0.331** | +0.517 | 0.400 | 0.133 | 0.000 | 0.017 | 0.561 | 6 |
| categorical_bocpd | +0.260 | +0.434 | 0.400 | 0.133 | 0.049 | 0.049 | 0.583 | 3 |
| no_rls | +0.163 | +0.433 | 0.300 | 0.133 | 0.000 | 0.000 | 0.561 | 12 |
| context_frequency | +0.400 | +0.300 | 0.300 | 0.000 | 0.000 | 0.000 | **0.544** | 2 |
| persistence | **+0.420** | **+0.108** | 0.400 | 0.133 | 0.213 | 0.213 | 1.180 | 12 |

### 这张表说明什么

**1. full 在 TEST 上确实超过了 shuffled，但只差 0.016。** 而且差距**全部**来自误报
（0.000 vs 0.017）——就是一个事件。

**2. 更要命的是方向反转：validation 上 shuffled（+0.331）高于 full（+0.321），选择
规则实际上更偏好 shuffled。** 一个在 validation 上占优、在 TEST 上落后的差异，就是
噪声的定义。

**3. `full` 与 `rls_only` 在每一个指标上完全相同。** 在这些阈值下，Dirichlet surprise
通道**没有提供任何 residual 之外的东西**。这是本轮最值得追的一条。

**4. persistence 是选择性过拟合的教科书例子**：validation utility 最高（+0.420），
TEST utility 最低（+0.108）。全 1.0 权重下 validation 奖励了它的无差别报警，TEST 的
误切换 0.213 把它打回原形。三维前沿 + 显式权重正在起作用。

**5. categorical_bocpd 从 v0.2 的确认率 0.000 变成 0.400。** 不是基线变强了，是把
异常检出加进目标之后，选到了不同的阈值。v0.2 的目标函数让这个基线看起来比实际弱。

**6. context_frequency 的 log-loss 仍然最好（0.544）。** 地板基线在位置预测上赢过链式 arm。

### 当前判决

**`UNDERPOWERED`。** TEST 只有 5 个场景、单 seed，确认率的最小刻度是 0.2，utility 的
差距是单个事件量级，而且 validation→TEST 出现方向反转。这个规模既不能证明 residual
有用，也不能证明它没用。

---

## 4. 产物清单

```text
src/cpswm/system/evaluation_operations/project_one_protocol.py    冻结接口 + 六条 residual 路线 + 两个校准器 + config hash
src/cpswm/system/evaluation_operations/project_one_dataset.py     记录/真值/流/manifest
src/cpswm/system/evaluation_operations/dataset_adapters.py        adapter 抽象
src/cpswm/system/evaluation_operations/project_one_scenarios.py   十个确定性场景
src/cpswm/system/evaluation_operations/project_one_methods.py     预测时序模板 + prime 钩子 + 严格 derangement + clone_with
src/cpswm/system/evaluation_operations/project_one_metrics.py     逐步指标 + 配对差值
src/cpswm/system/evaluation_operations/project_one_runner.py      统一 runner（prime + config hash）
apps/evaluation_runner/generate_project_one_scenarios.py          场景落盘
apps/evaluation_runner/run_project_one_benchmark.py               固定阈值基准
apps/evaluation_runner/tune_project_one.py                        独立调参 + 三维 Pareto
configs/project_one/default.yaml                                  默认配置 + 选择权重
tests/test_project_one_protocol.py                                阶段 0 验收
tests/test_project_one_same_context_rls_ablation.py               阶段 1 matched test（共享快照）
tests/test_project_one_dataset_contract.py                        阶段 2 验收
tests/test_project_one_evaluation_runner.py                       阶段 3/4 验收 + 防泄漏
```

复现：

```bash
PYTHONPATH=src python apps/evaluation_runner/run_project_one_benchmark.py \
  --output artifacts/project_one/fixed          # 默认 raw_clip，与 tuner 一致
PYTHONPATH=src python apps/evaluation_runner/tune_project_one.py \
  --output artifacts/project_one/tuning         # 权重可用 --w-anomaly 等覆盖
```

---

## 5. 下一步（按依赖顺序）

1. **多 seed，最高优先级。** 每一条结论都卡在 `UNDERPOWERED`，validation→TEST 已经
   出现方向反转。没有它后面每一步都得不出结论。
2. **查 `full == rls_only` 完全相同。** Dirichlet surprise 通道当前是死的，要么是
   `habit_signal` 的 `max` 结构让 residual 恒占优，要么是场景没有能区分二者的情形。
3. **处置 sigmoid 双重压缩**（源头修法：`RLSRegimeBank.score_candidates` 透传
   `apply_sigmoid=False`；那之后评测层的四条恢复路线都不需要）。这是你的决定。
4. 查异常检出率只有 0.133 的原因。
5. 阶段 5 补齐：EWMA、CUSUM、RLS-fixed-threshold、No-CF-BOCPD、No-CCRR、
   No-regime-reactivation。
6. 按匹配 FPR / 匹配 TPR 分别重报（现在 fsw 大多是 0，匹配报告还没有意义）。

阶段 8（半合成与真实数据）和阶段 9（LLM 三种角色）接口已就位：新数据源只需要一个
adapter，LLM 语义解析器的输出目标就是 `ProjectOneDatasetRecord`。
