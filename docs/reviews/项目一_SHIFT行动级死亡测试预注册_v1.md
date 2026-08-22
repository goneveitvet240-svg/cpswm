# 项目一 SHIFT 行动级死亡测试预注册 v1

冻结日期：2026-08-22

## 研究问题与范围

本 gate（门）只回答：在相同观测流、相同划分、相同计算空间和相同下游策略下，joint CF-BOCPD 是否在有意义的习惯 reset/consolidation（重置/巩固）决策上优于 independently retuned ordinary BOCPD（独立重调普通 BOCPD）以及 legacy independent CF-BOCPD（旧独立原因基线）。它不完成正式结构一 B1，不扩展其余八臂，也不提供外部有效性或 SOTA 声明。

## 冻结终点

- primary endpoint（主要终点）：`downstream-action-regret.normalized-per-case@1`，越低越好，MDE（最小可检测效应）为 `0.05`。
- key secondary endpoint（关键次要终点）：`corrupted-habit-mass.mean-per-case@1`，越低越好，MDE 为 `0.02`。
- decomposition metrics（分解指标）：false reset rate、missed reset rate、false consolidation rate、recovery time、unnecessary verification cost、task success。
- mechanism/guardrail metrics（机制/护栏指标）：F1、NLL、Brier、ECE；仅描述，不参与主胜负判定。

主要终点单独使用双侧 `alpha=0.05`；关键次要终点属于 Holm（霍尔姆法）家族，当前家族只有一个指标；机制指标不做确认性多重检验。

## 公平策略与调参

三臂分别完整搜索各自 18 个 detector hyperparameter（检测器超参数）组合，且仅用 validation seeds，以 validation action regret 选参。三臂随后使用完全相同的 detector-neutral policy（检测器中立策略）：reset threshold `0.50`、consolidation threshold `0.70`、attribution margin `0.15`。下游策略不得逐臂调参。

行动遗憾值由冻结成本函数构成：false reset `0.25`、missed reset 每日 `0.10`、corrupted mass 每日 `0.10`、verification `0.05`，逐案例截断到 `[0,1]`。这是冻结合成任务上的行动代价，不等于真实机器人环境效用。

## Power analysis（统计功效分析）与划分

- validation seeds：5 个；
- pilot seeds：8 个，只用于估计 joint-minus-ordinary paired difference variance（成对差值方差）；
- 最终 TEST seeds：151 个，与 validation/pilot 全局不重合；
- 目标 power：`0.80`。

pilot 得到 primary paired stddev `0.057924241575318246`，需 11 个 TEST seeds；corruption paired stddev `0.08764118476161362`，需 151 个。最终规模由较严格的 151 决定。程序在两个 power gate 均 PASS 前不得生成 TEST suite。

## 预注册判决

- `CONTINUE_JOINT`：joint 相对 ordinary 和 legacy 的 regret 95% paired bootstrap interval（成对自助法区间）上界均不高于 `-0.05`，且 corruption 上界均不高于 `-0.02`。
- `USE_ORDINARY`：joint-minus-ordinary regret 区间下界不低于 `+0.05`。
- `REBUILD_JOINT`：legacy 相对 joint 获得至少 `0.05` 的区间级实际优势，或 joint 相对 ordinary 的点估计没有正向行动收益。
- `INCONCLUSIVE`：其余跨越实际意义阈值的结果。
- `BLOCK_UNDERPOWERED`：任一功效门未通过；此时 TEST 不生成、不评价。

无论结果如何，禁止宣称 general superiority（一般方法优越性）、state of the art、外部有效性、正式结构一 B1 完成或全局 11 臂完成。
