# 项目一 SHIFT 行动级死亡测试预注册 v2

冻结日期：2026-08-22

v1 报告因 power topology（功效拓扑）、pilot variance binding（pilot 方差绑定）和 matched-policy fairness（匹配策略公平性）不足而撤回确认性地位。v2 不复用 v1 TEST seeds。

## 双轨问题

v2 同时运行以下轨道：

1. shared-policy track（共享策略轨道）：三臂使用相同未重调策略，测量直接 plug-in（即插即用）表现。
2. independently-retuned-policy track（独立重调策略轨道）：每臂只用相同 validation cases，在相同搜索空间和预算下联合选择 detector 参数、probability temperature calibration（概率温度校准）、reset threshold、consolidation threshold 和 attribution margin。

每臂共享相同的 18 个 detector candidates 和 117 个 policy candidates，共 `18 × 117 = 2106` 个 validation-only combinations。TEST 不参与选参。

## 冻结终点与动作语义

- primary endpoint：`downstream-action-regret.normalized-per-case@1`，MDE `0.05`，越低越好。
- key secondary：`corrupted-habit-mass.mean-per-case@1`，MDE `0.02`，越低越好。
- F1、NLL、Brier、ECE 为 descriptive mechanism guardrails（描述性机制护栏）。

consolidation 不是与 reset 同时发生的无语义布尔量，而是显式顺序：

```text
RESET_OLD_REGIME → CONSOLIDATE_NEW_REGIME
```

置信度不足时为：

```text
RESET_OLD_REGIME → VERIFY_NEW_REGIME
```

`task_success_proxy` 只表示冻结合成成本模型下没有 false/missed action，不代表真实搜索、导航或机器人任务成功。

## Power topology 与 artifact binding

每条轨道的 power analyses 必须按固定顺序精确包含四项：

1. regret：joint − ordinary；
2. corrupted mass：joint − ordinary；
3. regret：joint − legacy independent；
4. corrupted mass：joint − legacy independent。

不得为空、重复、遗漏或乱序。validator 必须从报告内 pilot artifacts、config pilot seed 集合和逐 seed paired differences 重算 empirical stddev、required n 与 PASS/BLOCK。只有两轨共八项全部 PASS 后，runner 才可生成 TEST suite。

pilot-only 规划结果：

| track | comparison | regret required n | corruption required n |
|---|---|---:|---:|
| shared | joint − ordinary | 11 | 151 |
| shared | joint − legacy | 16 | 141 |
| retuned | joint − ordinary | 3 | 66 |
| retuned | joint − legacy | 11 | 101 |

全局取最严格 `n=151`。最终 TEST seeds 为从未用于 v1 的 151 个奇数 seeds：`9101..9401`。

## 预注册跨轨判决

- `REBUILD_JOINT`：shared 与 independently-retuned 两轨中，joint-minus-legacy regret 区间下界都不低于 `+0.05`。
- `CONTINUE_JOINT`：两轨都满足 joint 相对 ordinary、legacy 的 regret 与 corruption 实际意义门。
- `USE_ORDINARY`：两轨都满足 ordinary 相对 joint 的 regret 实际意义门。
- `INCONCLUSIVE`：轨道结论不一致或跨越实际意义阈值。
- `BLOCK_UNDERPOWERED`：八个 power gates 任一未通过；此时 TEST 不得存在。

这是 intersection-union decision（交并判决）：任何方法级结论必须在两轨和全部规定 reference gates 上同时成立。仍禁止 general superiority、SOTA、外部有效性、正式结构一 B1 完成和全局 11 臂完成声明。
