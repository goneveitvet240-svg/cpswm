# 项目一：sigmoid 源头修复 + 真实数据/LLM 薄层（2026-08-24）

性质：**实现记录与实测对照**，不是论文证据。
结论先行：sigmoid 双重压缩已在源头修复，`full` 与 `shuffled_rls` 首次在合成基准上分开；
但功效仍不足，`UNDERPOWERED` 判决不变，方法优越性主张一条都不成立。

---

## 1. sigmoid 源头修复

### 1.1 改了什么

| 位置 | 改动 |
|---|---|
| `src/cpswm/system/continual/rls/habit_head.py` | `score_candidates(..., apply_sigmoid=)` 默认由 `True` 改为 `False` |
| `src/cpswm/system/continual/rls/regime_bank.py` | 新增 `apply_sigmoid` 透传参数，默认 `False`；**并修复无 head 回退的量程 bug**（见 1.2） |
| `project_one_protocol.py` | `AS_IS`（"原样使用 bank 返回值"）现在读原始分；新增 `LEGACY_SIGMOID` 显式请求旧压缩，保住修复前读数可复现 |
| `project_one_methods.py` | 链式臂按校准路线决定是否向 bank 请求 sigmoid，而不是依赖共享默认值 |

RLS head 的底层模型是已经拟合到 `{0,1}` 目标的最小二乘回归器，它的原始输出**就是**校准后的分数。
再压一层 sigmoid 把完美学到的 `1.0` 映射成 `0.731`、完美排除的 `0.0` 映射成 `0.5`，
于是 `1 - score` 形式的残差永远出不了 `[0.269, 0.5]`——**正确预测的事件也带 0.269 的残差底噪**。

对 `prototype_spine` 的影响已逐点核查：两处残差计算（`:576`、`:1702`）因此被修正；
两处只把分数当 `max()` 次序打破器（`:708`、`:1824`）——sigmoid 单调，**排序不变**，建议输出不变。

### 1.2 顺带发现的第二处同类 bug

`RLSRegimeBank.score_candidates` 在「该 regime 还没有 head」时直接返回 `1/n`，
两种量程下都返回同一个数。但 `0.5` 在原始量程下表示"分数 0.5"，在 sigmoid 量程下表示"raw 0"——
**同一个数字指代两个不同的分数**。这导致读原始分的调用方和反解 sigmoid 的调用方在
regime 建 head 之前的每一个事件上都不一致（实测差 1.3e-5）。

修法：回退值定义为**原始量程上的** `1/n`，被请求 sigmoid 时在出口压一次。
修复后 `as_is` 与 `raw_clip` 在真实形状数据上的最大差降到 **2.8e-15**（纯浮点噪声）。

### 1.3 测试怎么改的

三个 `xfail(strict=True)` 中只有一个翻成 xpass。诚实的做法不是删掉了事：

- 三个原 "shipped wiring" 测试改指向 `LEGACY_SIGMOID`，继续 xfail —— 缺陷仍可演示，不变成传说；
- 新增修复后的对照测试，其中**两个仍然 xfail**，并在 reason 里写明"源头修复没有买到这一条"：
  - `shuffling costs real discrimination`：本 fixture 上差距仍 < 0.1；
  - `full change probability exceeds no_rls`：两臂都饱和在 1.0，"超过"无从谈起，需要不饱和的 fixture；
- 新增 `test_as_is_and_raw_clip_agree_after_the_source_fix`：两条路线必须给出同一个数，
  否则说明 head 发出的东西和 harness 以为的不一致，所有前后对照都失去意义。

---

## 2. 修复前 vs 修复后（10 场景固定阈值平均）

| 指标 | arm | legacy（修复前） | as_is（修复后） |
|---|---|---:|---:|
| 变化确认↑ | full | 0.4000 | 0.4000 |
| | **shuffled_rls** | **0.4000** | **0.3000** |
| 误切换↓ | full | 0.0241 | **0.0094** |
| 伪 regime↓ | full | 0.3 | **0.2** |
| 配对间隔↑ | full | 0.0561 | **0.1273** |
| | rls_only | 0.0225 | **0.1273** |
| | shuffled_rls | 0.0541 | 0.0964 |

**`full` 与 `shuffled_rls` 的可分性**（这是"residual 到底有没有配对信息"的直接读数）：

| 路线 | 确认率差 | 配对间隔差 |
|---|---:|---:|
| legacy（修复前） | **+0.0000** | +0.0020 |
| as_is（修复后） | **+0.1000** | +0.0309 |
| raw_clip | +0.1000 | +0.0309 |
| recenter | +0.1000 | +0.0315 |

修复前 `full` 和 `shuffled_rls` 在四个主指标上**完全相同**。出厂那层 sigmoid 正好把
这个问题抹平了——按项目自己的分级表，这会被读成"residual 只是尺度信号"。

**独立调参 TEST 配对间隔**：

| 路线 | full | shuffled_rls | no_rls | rls_only |
|---|---:|---:|---:|---:|
| legacy | +0.004 | +0.002 | **+0.106** | −0.024 |
| as_is | **+0.114** | +0.071 | +0.106 | +0.114 |

修复前 `no_rls`（+0.106）**高于** `full`（+0.004）——出厂接线下加 RLS residual 是净损失。
修复后才反过来。

---

## 3. 仍然不成立的（必须写清楚）

1. **判决仍是 `UNDERPOWERED`。** 调参 TEST 只有 5 个场景、单 seed，确认率最小刻度 0.2。
   固定阈值那张表是 10 场景平均、单 seed，0.4 与 0.3 之间只差一个场景。
   协议 §7 把"加多 seed"列为最高优先级并写明"没有它后面每一步都得不出结论"，这句话依然成立。
2. **上面的数字只支持一条结论：sigmoid 该修，而且已经修了。** 不支持"residual 有用"。
3. **两条 xfail 是真负结果**，不是待办事项：置换洗牌的代价仍 < 0.1，两臂在变化概率上仍饱和。
4. `context_frequency` 地板基线的 log-loss（0.6226）在这张固定阈值表上输给链式臂（0.5282），
   与协议 v0.2 §5 调参后 5 场景 TEST 的"0.544 赢过 0.562"方向相反。**两张表不是同一个实验**，
   不构成矛盾，但也说明单 seed 下这类比较不稳定——同样要等多 seed。

---

## 4. 真实数据与 LLM 薄层（四个新模块）

不修改 `prototype_spine.py`、项目二反馈回流代码或既有项目一算法公式；全部按 failing-first 落地。

| 模块 | 职责 | 关键保证 |
|---|---|---|
| `project_one_stream_binding.py` | 按 `(household, actor, object)` 三元组切分流，每桶一套模型状态 | 分区完整（无静默丢弃）；隔离是结构性的（每桶重建组件，不靠 key 纪律）；候选位置只来自训练流或显式 manifest |
| `real_data_adapters/jsonl_adapter.py` | 通用 JSONL 入口 | 排序 / 重复 / 时区 / 缺字段 / 未知位置五类风险逐条处理；**报告而非静默修复**，每一次修复写进 manifest 的 `preprocessing`；事件行携带真值字段直接拒收 |
| `project_one_semi_synthetic.py` | 四类已知变化注入 | 扰动**不**标记为变化点（这正是抓误报的场景）；源流永不原地修改，记录源 content hash；种子决定论 |
| `project_one_llm_method.py` | `llm_direct` 基线臂 | 继承 `_BaseMethod`，predict-before-learn 结构性保证；prompt 不含被打分事件；schema 校验 + 归一化 + 缓存 + 超时 + 重试 + token/延迟/费用全账；client 走 Protocol 注入，测试零网络 |
| `project_one_data_pilot.py` | 编排与产物 | 不可评估分桶带原因进 manifest；`full_as_is` 与 `full_raw_clip` 作为**真实数据上的在线一致性检查**，不一致即整份报告存疑并非零退出 |

七个固定参数臂：`full_as_is` `full_raw_clip` `no_rls` `rls_only` `categorical_bocpd`
`context_frequency` `persistence`；LLM pilot 加 `llm_direct`。本轮**不做自动调参**。

### 4.1 实跑结果（234 事件 / 10 物体 / 3 家庭 / 含 2 行故意的坏数据）

```text
real_data_pilot     : 234 accepted, 1 duplicate dropped, 1 rejected
                      7 bindings evaluated, 4 skipped
                      as_is vs raw_clip: agree=True  max_abs_difference=2.803e-15
semi_synthetic_pilot: 三类注入 → planted 21 changes across 7 bindings
                      四类全开 → 只有 1 个分桶够长，6 个过短保留未注入并记录
llm_pilot           : 8 arms / 56 results
                      calls=169 cache_hits=2 retries=0 timeouts=0
                      schema_failures=0 fallbacks=0
                      prompt=44293 tok  completion=5945 tok  latency=0.007s
```

### 4.2 尚未支持

- **LLM provider：只有 `offline_stub`。** 它用历史频率作答，是**接线检查，不是语言模型基线**。
  接真实 provider = 写一个实现 `LLMClient` Protocol 的类 + 在
  `run_project_one_llm_pilot.py` 的 `PROVIDERS` 注册；method 层不需要改。
  **在此之前阶段 9 不算开始。**
- **数据格式：只有 JSONL。** HOMER / WorldLines / DynaBench / MEMENTO 等各自的原生格式
  各需一个 adapter。
- **单文件单流。** 一个文件含多个 `stream_id` 会被拒绝，要求先切分。
- **半合成的基线习惯 = 日志实际观测到的位置。** 这是假设不是事实：真实日志本就含有
  我们没有种植的真实变化，某个臂标出来可能是对的。所以结果只能说"是否检出了**种植的**变化"，
  永远不能报成干净的误报率。
- **LLM prompt 不含绝对时间戳**（为可缓存性与 no-peek），因此该臂没有"经过了多久"的概念；
  历史窗口截断，比窗口更长的周期性习惯对它不可见。

---

## 5. 下一步（依赖顺序不变）

1. **多 seed**——仍是最高优先级，没有它后面每一步都得不出结论；
2. 查异常检出率卡在 0.133 的成因（是场景天花板还是 `expected_location` 比对漏判）；
3. 阶段 5 补齐 EWMA / CUSUM / RLS-fixed-threshold / No-CF-BOCPD / No-CCRR / No-regime-reactivation；
4. 接真实 provider，阶段 9 才真正开始；
5. 接第一个真实数据集 adapter（路线 A），M05 dataset adapter 优先级高于 M07–M12。

---

## 6. 复现

```bash
.venv/bin/pytest tests/test_project_one_protocol.py \
  tests/test_project_one_dataset_contract.py \
  tests/test_project_one_same_context_rls_ablation.py \
  tests/test_project_one_evaluation_runner.py \
  tests/test_project_one_stream_binding.py \
  tests/test_project_one_jsonl_adapter.py \
  tests/test_project_one_semi_synthetic.py \
  tests/test_project_one_llm_method.py \
  tests/test_project_one_data_pilot.py \
  tests/continual/
```

注意：命令里**不要**再加 `-q`——`pyproject.toml` 的 `addopts` 已含 `-q`，叠成 `-qq` 会把汇总行整个压掉。

修复前后对照：

```bash
PYTHONPATH=src .venv/bin/python apps/evaluation_runner/run_project_one_benchmark.py \
  --output artifacts/project_one/fixed_pilot_legacy_sigmoid --calibration legacy_sigmoid
PYTHONPATH=src .venv/bin/python apps/evaluation_runner/run_project_one_benchmark.py \
  --output artifacts/project_one/fixed_pilot_as_is --calibration as_is
```
