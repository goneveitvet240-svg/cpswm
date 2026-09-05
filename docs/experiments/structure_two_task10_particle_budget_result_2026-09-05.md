# 结构二 Task 10：粒子预算曲线 v0.1 可复算结果

日期：2026-09-05
协议：`structure-two-backbone-particle-budget-task-10@0.1`
证据级别：D0 synthetic deterministic recomputation（D0 合成确定性复算）
冻结配置：`configs/project_two_experiments/structure_two_task10_particle_budget_v0_1.json`

## 结论

Task 10 的 `G=1` 与 `G=2` 多预算曲线已按当前源码各执行两遍，去除墙钟字段后的结果逐字段一致。
这关闭的是工程复算缺口，不是正式预算选择：

```text
task_10_definition_and_rerun_complete = true
formal_task_10_passed = false
seven_operator_efficacy_authorized = false
```

因此本结果可以进入 2026-09-05 的“可复算 D0 证据”集合，但不能充当
`task_10_resolution_receipt`，也不能解锁 Tasks 11–13、P5 或七算子消融。

## 冻结设计

| 设计 | scenario seeds | particle budgets | replicate seeds | 近似臂 |
|---|---|---|---|---|
| `G=1` | 11, 23, 37, 41, 53 | 8, 16, 24, 48, 96, 384, 1536 | 101, 202, 303 | sampled-theta PF、RBPF、typed RBPF、adaptive typed RBPF |
| `G=2` | 11 | 24, 96, 384 | 101, 202, 303 | 同上 |

每个 scenario 的 exact posterior（精确后验）只计算一次并由各预算臂共享。报告保留 TV、truth
coverage（真值覆盖）、owner calibration（主人校准）、action distance（行动距离）、decision
regret（决策遗憾）、ESS、elementary evaluations（基础评估数）及墙钟。

## 代表性结果与边界

- `G=1, K=24`：RBPF TV `0.78136` / truth coverage `0.10833` / elementary evaluations
  `120`；adaptive typed RBPF 为 `0.48788` / `0.62500` / `15528`。同粒子预算优势不等于等计算
  优势。
- `G=2, K=384`：RBPF TV `0.78367` / truth coverage `0.04167` / elementary evaluations
  `3840`；adaptive typed RBPF 为 `0.60288` / `0.62500` / `416640`。该曲线仍显示显著计算口径
  差异，不能据此直接选择预算或宣称方法优越。

机制归因仍未解决：“不注入连续参数采样噪声”和“解析边缘化提供的信息增益”尚未通过干预实验
拆开。

## 工件与 trust chain

| 工件 | file SHA-256 | content SHA-256 | 正向路径数 |
|---|---|---|---:|
| `task_10_budget_sweep_g1.json` | `7944d3f1c7ce9e535d76d525f4c0ec89705fa97bc6a6752fa1101ef8d311389e` | `e8361e2ab44ae4fd3c41170ffd540012ea0ff1952e289e9bb99740b9f28504be` | 41 |
| `task_10_budget_sweep_g2.json` | `48c0eedb3f24d8d5dae489b55be27a26546f633a18c45224f859acd7716cb46b` | `07f24e5631e2a25b02526105170748fe1e47266c7a3a7b2cd1841940297b822a` | 9 |

每个正向布尔输出都逐路径绑定 artifact content、Task 10 冻结配置、协议文档、producer source
bundle 与 fresh task-specific recomputation。自洽重哈希、改阈值、换配置或换任务命令均不能通过
验证。
