# Project-two action benchmark（current v0.6）

Authoritative runner:

```bash
.venv/bin/python apps/evaluation_runner/run_structure_two_action_death_test.py
```

The runner constructs a provenance-safe D0 replay pilot, tunes each method only
on the validation split, opens the sealed test split only after tuning, and
emits per-case, aggregate, worst-group, paired-difference and 95% bootstrap-CI
records. O-STaR, DynaMem and STAR are labelled `matched_replay_adapter`; the
report records their missing faithful inputs. Every non-oracle arm may falsify
the candidate in development, but no matched adapter may authorize a faithful
paper-level superiority claim. Matched AMG is the current strongest reference
arm in D0.

No external dataset is selected by this directory.

## 更正声明（2026-09-05）

`replay_evidence_v0_3/` 下的数值**不受**结构二 search-utility bug 影响（correctness 与
path cost 一直消费同一个 `_Prediction.search_order`）。但引用其中的
`mean_search_cost` 时必须同时引用报告的 `unregistered_search_metric_assumptions`：
每容器 5.0 秒的耗时常数、以及真值不在计划内时按 `len(known_locations)` 计的失败惩罚，
都不是冻结协议注册的常数。

冻结的组合 A 路线未规定 cumulative action regret 的组成项权重，因此报告新增
`route_a_primary_utility_evaluated=false` 与 `unresolved_utility_contract_fields`，
superiority 失败关闭。详见
`docs/experiments/structure_two_search_utility_correction_2026-09-05.md`。

## v0.5 D0 开发合同（2026-09-06）

v0.5 新增一个明确标记为 `d0_development_only` 的效用合同：put-back 错误为 `0/1`，search
regret 为相对 oracle 首次命中的归一化额外检查量。validation selection 与 sealed scoring 现在
消费同一个 `cumulative_action_regret` 公式，所有已登记 non-oracle 方法都进入 strongest-reference
falsification（最强参考否证）。

该合同不提供真实时间/能耗/金钱价格，也不能授权论文主张。新增的 20/20/60
TRAIN/VALIDATION/sealed TEST 配置仍为 `confirmatory=false`。结果与边界见
`docs/experiments/structure_two_route_a_development_utility_v0_5_2026-09-06.md`。

## v0.6 双时间尺度行动读出（2026-09-06）

在两轮 report/action-boundary 对抗自查后，v0.6 用 TRAIN `1--20` 诊断并冻结三个等预算
planner readout（规划器读出）候选，在 validation `1001--1020` 选择后首次开启新的 development
holdout `6001--6060`。完整系统的累计行动遗憾为 `3.455556`，matched AMG 为 `3.933333`；
放回与恢复打平，搜索遗憾更低，但 owner contamination 为 `0.007292` 对 `0`，数值护栏仍未注册。

因此 v0.6 只建立 D0 development engineering advantage（开发工程优势），不建立论文级胜出。
记录与边界见
`docs/experiments/structure_two_action_readout_v0_6_2026-09-06.md`。
