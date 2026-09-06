# 结构二 Route-A D0 开发效用合同与 v0.5 重算（2026-09-06）

## 结论

本轮完成了当前最紧要的指标收口，但**没有**把 D0 开发口径冒充论文级口径：

- 新增互不相交的 TRAIN / VALIDATION / sealed TEST 配置，数量为 `20 / 20 / 60`；
- 将 validation selection（验证集选择）的唯一目标改为
  `cumulative_action_regret`（累计行动遗憾），不再仅按 put-back error 调参；
- D0 开发搜索项改为 normalized extra inspections（归一化额外检查量）：第一处命中为 `0`，
  最后一处命中或计划未找到为 `1`；put-back 错误仍为 `0/1`，两项开发权重均为 `1`；
- superiority comparison（优效比较）纳入每个已登记的 non-oracle（非预言机）方法。匹配适配器可以
  否定候选方法，但不能因此升级为 faithful reproduction（忠实复现）；
- 原报告错误的“只在部分 fidelity 类型中找 best reference”已修复。v0.5 正确识别
  matched AMG 为当前最强参考方法；
- `development_primary_utility_evaluated=true`，但
  `route_a_primary_utility_evaluated=false`、`superiority_supported=false`。真实任务成本、优效界值、
  三条硬护栏阈值、独立托管与外部原声复现仍未完成。

## 冻结文件

- 数据配置：`configs/project_two_datasets/d0_multiseed_development_v0_4.json`
  - SHA-256：`994ec34f42e9fc36af164372811dd0941cc9807d5a5351450a0081a04c984631`
- 开发效用合同：
  `configs/project_two_experiments/structure_two_route_a_utility_contract_v0_1.json`
  - SHA-256：`da2856c351f7249352a546dda82daa8dfb633de5d5ed169c61f8a67fcc00e292`
- 重算工件：
  `artifacts/project_two_v04_development/structure_two_action_benchmark_v0_5_development_utility_2026_09_06.json`
  - SHA-256：`a82603f05ca314b54cf0112702033b7e990fddaa1a8eed8c20f14846818e49b1`

上述工件仍位于 development artifact（开发工件）目录，不具备外部历史真实性或独立托管。

## 开发效用定义

对每个 action step（行动步）：

```text
put_back_regret = 1[put_back != true_owner_habit_location]

search_regret =
  0                                      , N = 1 且首处命中
  (inspected_containers - 1) / (N - 1) , 目标在计划内且 N > 1
  1                                      , 目标不在计划内

cumulative_action_regret = Σ(put_back_regret + search_regret)
```

该式只提供无量纲 D0 task-regret unit（任务遗憾单位），范围为每步 `[0, 2]`。它不声称一处容器
检查等价于一次错误放回，也不替代真实机器人时间、能耗、失败风险、隐私成本或金钱成本。旧的
`5.0 s / container` 继续只作为 secondary diagnostic（次级诊断），不进入主效用。

## 20/60 sealed 结果

训练划分未被当前非学习型方法消费；各方法只在 20 个 validation episode 上按同一主效用独立选择
参数，再在 60 个 sealed-test episode 上评分。

| 方法 | put-back error | put-back regret | search regret | cumulative regret | contamination | recovery | search error | mean path |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| project-two full loop | 0.142188 | 4.550000 | 1.655556 | **6.205556** | 0 | 0.591667 | 0.086979 | 1.155208 |
| matched AMG | 0.045313 | 1.450000 | 1.938889 | **3.388889** | 0 | 0 | 0.086979 | 1.181771 |

项目二在 search regret 上比 matched AMG 低 `0.283333`，但 put-back regret 高 `3.10`，总开发
遗憾高 `2.816667`。因此 v0.5 的明确比较是：

```text
cumulative_action_regret 6.20556 is worse than the best reference
damen_hogg_amg_matched_open_world at 3.38889
```

这不是“公平环境已经完成”：AMG、O-STaR、DynaMem、STAR 仍缺各自原系统需要的输入与推断栈。
它只意味着在当前同可见流的 D0 matched-adapter（匹配适配器）环境中，项目二已经被最强参考臂
否定，不能等待外部原声复现后才承认当前行动读出失败。

## 仍未通过

以下门继续失败关闭：

1. paper-grade real task-cost calibration（论文级真实任务成本标定）；
2. superiority margin（优效界值）；
3. owner contamination、recovery latency、full-rerun equivalence 三条数值护栏；
4. D1-D4 外部有效性；
5. 六个外部强邻居的 faithful native reproduction（忠实原声复现）；
6. independent custody（独立托管）与封存后开启。

完整统一框架中的 hidden-event inference（隐藏事件推断）、multi-actor reasoning（多人物推理）、
open-world unknowns（开放世界未知）、reversible attribution（可逆归因）和 embodied feedback
loop（具身反馈闭环）均未删除。

## 验证

- 10 个相关测试文件、234 项测试：通过；
- 16 个本轮触及的 source/runner/test 文件 Ruff lint 与 format：通过；
- 6 个本轮触及的 source 文件 strict mypy：通过；
- `git diff --check`：通过；
- repository-wide mypy（全仓类型检查）仍有 18 个本轮范围外文件的 62 个既有错误，因此不把
  “定向 mypy 通过”写成“全仓 mypy 通过”。

## v0.6 后续取代声明（append-only，2026-09-06）

v0.5 的失败数值和工件保持不变。其慢读出三点已由训练诊断后的 v0.6 三点取代；v0.6 使用新的
`6001--6060` development holdout，并在开发主效用上取得 `3.455556` 对 matched AMG
`3.933333` 的工程优势。详见
`docs/experiments/structure_two_action_readout_v0_6_2026-09-06.md`。该取代不改变 v0.5 的历史失败，
也不把 v0.6 升级为论文级或独立托管证据。
