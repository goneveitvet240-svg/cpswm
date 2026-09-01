# 结构二结构化联合复苏阻断门 v0.2：结果

日期：2026-08-28  
协议：`structure-two-structured-rejuvenation-gate@0.2`  
证据级别：finite synthetic blocking gate（有限合成阻断门），不是论文级证据

## 结论

仓库内运行前冻结的 7 项阻断门在机械意义上全部通过。结构化联合复苏修复了 v0.1 已定位的主要局部缺陷：在 high attribution ambiguity（高归因歧义）与 adverse delayed feedback（不利延迟反馈）同时出现的压力子集中，truth support（真值支持率）由 `0.50` 提升到 `0.75`，达到 full rerun beam（完整重跑束搜索）的 `0.75`。

这里的“运行前冻结”没有独立时间戳机构背书，不能作为正式 external preregistration（外部预注册）陈述。两轮对抗审核还确认：其中一个 action regret（行动遗憾）门因为读出只消费 regime（阶段）而缺乏对本次四个主要修复轴的判别力。因此准确表述是 **7 项条件均为真，其中 6 项提供局部判别证据，1 项只能作为退化诊断**。

因此，下一步可以进入与 corrected AMG（修正 AMG）和旧完整七算子系统的行动级连接实验。但本结果不表示结构二已经击败 AMG，也不表示神经提议器已经得到验证。

## 全部 16 格结果

| 方法 | mean posterior TV | truth support | action regret | action match | mean candidate evaluations |
|---|---:|---:|---:|---:|---:|
| 单字段类型化粒子修订 | 0.09590 | 0.8750 | 0.0000 | 1.0000 | 526.625 |
| **结构化联合类型化粒子修订** | **0.08079** | **0.9375** | **0.0000** | **1.0000** | **533.938** |
| 完整重跑束搜索 | 0.07452 | 0.9375 | 0.0000 | 1.0000 | 744.000 |

相对单字段复苏，联合复苏：

- mean posterior TV 降低约 `15.75%`；
- truth support 提升 `6.25` 个百分点；
- 行动遗憾保持为零；
- 平均解析状态评分量增加约 `1.39%`。

联合复苏的平均解析状态评分量为完整重跑的约 `71.77%`，低于冻结的 `90%` 上限。该指标不含 proposal generation（提议生成）、契约验证或运行时开销，不能解释为墙钟时间、FLOPs 或端到端成本。

## 预注册压力子集

压力子集共有 4 格。

| 方法 | mean posterior TV | truth support | action regret | action match | mean candidate evaluations |
|---|---:|---:|---:|---:|---:|
| 单字段类型化粒子修订 | 0.24969 | 0.50 | 0.0000 | 1.00 | 543.25 |
| **结构化联合类型化粒子修订** | **0.21266** | **0.75** | **0.0000** | **1.00** | **553.00** |
| 完整重跑束搜索 | 0.18891 | 0.75 | 0.0000 | 1.00 | 744.00 |

联合复苏恢复了 `e15` 的真值支持；其联合移动需要同时处理人物角色链及反馈后的其他字段，而单字段邻域无法把真值带入前 24 个粒子。

## 尚未解决的例外

`e13` 仍不包含真值：

```text
handoff | unknown_to_owner | target_instance | habit | new_regime
```

但同一预算下的完整重跑束搜索也未把该真值放入 top-24，因此本轮“达到完整重跑支持率”的门仍合法通过。这也说明当前通过的是 bounded-support parity（有界支持集对齐），不是 exact posterior recovery（精确后验恢复）。

联合复苏的压力 TV `0.21266` 仍高于完整重跑的 `0.18891`；差距约 `0.02375`。这项差距不违反本轮预注册门，但应在后续行动级实验中保留为诊断指标。

## 科研含义

联合核是在观察 v0.1 同一场景族失败之后设计的，因此本轮属于 development evidence（开发证据），存在适应性过拟合风险。本轮支持的主张仅为：

> 在冻结的有限状态反例中，`mechanism–actor role chain（机制—人物角色链）`、`cause–regime（原因—阶段）` 与 `identity–cause（身份—原因）` 联合复苏，比单字段复苏更能抵抗归因歧义和不利延迟反馈，并以低于完整重跑的候选评估量达到相同 truth support。

本轮不支持以下主张：

- 完整结构二优于 AMG；
- 七个算子均产生正贡献；
- neural amortized proposal（神经摊销提议）有效；
- 合成结果可外推到 RGB-D、家庭或机器人执行场景。

七个算子继续全部保留。Neural amortized proposer（神经摊销提议器）仍保持 fail-closed（失败关闭），直到用户确定架构与训练路线并形成冻结训练 artifact。

## 下一阻断门

下一步应先冻结 fresh scenario families / sealed seeds（新场景族／封存种子），再把本轮联合复苏接入同一 corrected AMG matched replay adapter（修正 AMG 匹配重放适配器）和旧完整七算子系统，运行行动级三方比较：

1. corrected AMG；
2. 旧完整七算子系统；
3. 完整七算子系统 + v0.2 联合类型化粒子修订。

必须保持相同可见证据、行动空间、观察成本、随机种子和评分函数；行动读出必须实际消费 actor、identity、cause 与 regime 中任务相关的变量。主要终点仍是每步净行动损失，不用 posterior TV 代替行动收益。

## Artifact 与完整性

- JSON artifact：`artifacts/project_two_v04_development/structure_two_structured_rejuvenation_gate_v0_2.json`
- content SHA-256：`cd692016e0e74b123e4e1375342a20e262e07279c249b961eaf059848492f9c8`
- artifact byte SHA-256：`3258fd03363b7e5fc9871dce2b789a0cc1f1a27082714e4af5c9b3211bb5ae8b`
- v0.2 gate source SHA-256：`d97c825b6363460456fb4c7d0b9a8f580500418e49b03c63a48be3198f6ecec2`
- v0.1 source SHA-256：`147e369c88708cf152510f1978beed7cdbd6baf86d60f0ec0de0837631df7e6c`
- selected method source SHA-256：`2a4ae8f0c7c99f26fd9aa95e4c17456fdd9c85ca6b886ce3b60e107497fe1efb`
- selected method receipt SHA-256：`eff5e472346209053fe867e2ab53fdc455861e1e20125f192e6993e33bb33951`
- protocol SHA-256：`ac698d0b5f64f7c9081f2db63cde0dc2665f3f8dd50f8fc4e8cfc5cade16a447`
