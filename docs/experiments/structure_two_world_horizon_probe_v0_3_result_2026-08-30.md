# 结构二 v0.3：`[320,380]` train-only horizon probe 结果

日期：2026-08-30  
协议：`structure-two-world-horizon-probe@0.3`  
证据等级：train-only benchmark-design evidence（仅训练世界的基准设计证据）

## 冻结输入

- 设计文件：`configs/project_two_experiments/structure_two_world_horizon_probe_v0_3.json`
- design SHA-256：`c5e0754f3d797aa6a62ec4431ea0bf91c5f94cd993fc632002532c9639edb4c3`
- 世界时长：仅测试 `[320,380]`
- train worlds：`410001`–`410024`
- 每世界 trajectory seeds：`[13,29,41]`
- 每条轨迹 observation seeds：`[103,223]`
- 4 个 world-level folds，每折 6 个世界
- TV witness grid：48 组

运行前冻结的晋级要求：

- world-weighted mean top-1 gain ≥ `0.020`
- worst held-out-fold top-1 gain ≥ `0.018`
- mean false resets ≤ `1.0 / rollout`
- stationary false-alarm rate ≤ `0.025 / observation`
- 分别报告 weekday / weekend 有效样本量
- search path 使用正式 pooled-count tail，不使用字典序尾部

false reset 采用一对一匹配：每个真实变点最多豁免一次发生在变点后 14 天内的重置，窗口内额外重置和窗口外重置都算误报。

## 判决

**probe 未通过；`[320,380]` 不得写入待签字 v0.3 manifest。**

48 个候选中没有一个同时满足 rollout false-reset 和 stationary false-alarm 两项约束。因此没有候选获得晋级资格，没有生成任何 validation world，也没有运行任何研究方法。

artifact content SHA-256：

`d02e1748707d343ac882e659d52f8eedce467bbf8989a8b0902b138b2c4ae726`

连续运行与 deterministic recomputation（确定性复算）得到相同哈希。

## 最稳定候选

在通过 stationary false-alarm 约束的候选中，误重置最少且 worst-fold 最好的配置：

```text
recent_window = 10
divergence_threshold = 0.70
minimum_reference_observations = 16
context_shrinkage_pseudocounts = 0.0
owner_probability_threshold = 0.5
```

| 指标 | 数值 | 冻结要求 |
| --- | ---: | ---: |
| world-weighted mean top-1 gain | **0.044723** | ≥ 0.020 ✓ |
| worst-fold top-1 gain | **0.039886** | ≥ 0.018 ✓ |
| fold gains | `[0.041895, 0.047028, 0.050081, 0.039886]` | — |
| normalised path-cost gain | 0.009391 | report-only |
| stationary false-alarm rate | **0.011887** | ≤ 0.025 ✓ |
| mean total resets / rollout | 2.555556 | report-only |
| **mean false resets / rollout** | **1.986111** | **≤ 1.0 ✗** |

增益最高的候选达到 mean `0.046075`、worst fold `0.038563`，但 false resets 为 `4.388889 / rollout`，stationary false-alarm rate 为 `0.031985`，两项约束都失败。

## 有效样本量

所有候选使用同一个 owner admission threshold，因此有效样本量不依赖 TV 网格参数。

| context | 世界等权均值 / rollout | 最低世界均值 | p10 世界均值 |
| --- | ---: | ---: | ---: |
| weekday | 89.916667 | 61.000000 | 66.666667 |
| weekend | 31.569444 | 21.500000 | 23.833333 |

长水平线已经消除了 v0.2 每个情境单元只有少量样本的主要问题。top-1 的 mean 和最差折均大幅超过门槛，所以本轮失败不能再归因于总体观测预算不足。

## 失败机制

绑定约束变成了 detection latency（检测延迟）和 reset attribution（重置归因）。最稳定配置需要 16 个 reference observations 加 10 个 recent observations；在选择性观测下，它虽然能稳定提高预测，却经常无法在真实变点后的 14 天窗口内完成一对一命中。因此许多具有预测收益的重置仍按预注册规则记为 false reset。

这不授权事后扩大 14 天窗口、降低 `1.0` 上限或扩展网格。若继续，必须另建新的 train-only 设计版本，先用观测到达率算术论证检测延迟预算，再冻结新的 detector family；本次结果和 artifact 必须原样保留。

## 边界

- generator code 没有修改；本 probe 仅用临时配置测试 `[320,380]`。
- v0.3 manifest draft 没有获得采用 `[320,380]` 的授权。
- v0.2 manifest、Gate A artifact 和失败判决均未修改。
- validation / holdout 未打开，method comparison 继续冻结。
