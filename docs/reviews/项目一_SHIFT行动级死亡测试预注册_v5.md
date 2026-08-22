# 项目一 SHIFT 行动级死亡测试预注册 v5

冻结目标日期：2026-08-22

v4 仅保留方向性证据。v5 是第一个要求 causal prefix-online prediction（因果前缀在线预测）的 action death-test contract 候选版本。

## Prefix-online prediction

- 每个 detector 对 day 3 至 day 10 的每个 `as_of_time` 分别运行。
- 每次调用只收到 `recorded_time < as_of_time` 的 observation opportunity、detection result 和 actor evidence。
- 每个 prefix snapshot 保存 prefix input hash、可见 evidence IDs、当前 posterior 和首次 change-time estimate。
- validator 从完整 split input 重新截断所有 prefix，并从 params 确定性重放全部 trajectory。
- 首次 change-time estimate 一旦出现必须冻结；后续 prefix 只能增加可见 evidence，不能读取未来记录。

## 三类时间语义

- `change_time_estimate`：detector 根据当时前缀估计的变化时间。
- `decision_time`：某个 prefix posterior 首次满足 reset policy 的截断时刻。
- `posterior_at_decision`：严格来自该 `decision_time` 前缀的原始 detector posterior。

reset 在 `decision_time` 执行，禁止把估计的历史 change time 当作动作执行时刻。

## Verification 与 consolidation

规范 verification predicate 为 `owner-associated-repeat-object-location@1`：reset 后必须出现两条时间严格递增、属于同一 object 和同一 location 的 DETECTED results，并且两条记录均具有 target owner posterior ≥0.60。

第二条证据的 recorded time 是 `verification_time`。consolidation 只能在 verification 之后的下一个或更晚真实 prefix cutoff 执行，且 detector posterior 必须重新满足 consolidation threshold 和 attribution margin。禁止机械 `+1 microsecond`。

## Truth/input binding

每个 action truth 保存并验证：

- `model_input_sha256`；
- `evaluator_truth_sha256`；
- `generated_case_sha256`。

报告 validator 使用 split input artifact 中的原始 `OnlineShiftGeneratedCase` 重建完整 arm artifact，逐案例精确比较 truth、trajectory、verification evidence、outcome 和 aggregate metrics。

## Action baselines 与 balanced regret

TEST 同时报告两个 detector-independent action policy baselines：

1. `never-act`：从不 reset、verify 或 consolidate；
2. `always-reset-verify`：在第一个合法 prefix reset，随后服从同一 verification predicate 和真实 prefix consolidation 时序。

primary endpoint 改为 balanced downstream action regret：habit cases 与 non-habit cases 各占 50% 权重。普通总体均值继续报告，但不再作为 primary endpoint。

每臂在 shared/retuned 两轨都与两个行动基线做 paired seed bootstrap。任何 `CONTINUE_JOINT`、`REBUILD_JOINT` 或 `USE_ORDINARY` 总判决，都要求相应候选方法在两轨相对 `never-act` 的 regret 95% CI 上界 ≤ -0.05；否则总判决降为 `INCONCLUSIVE`。这防止“某 detector 看似胜出，实际只是复现不行动策略”的伪优势。

## Power 与全新 TEST

每个 track × reference × endpoint 使用：

```text
powered paired SD = max(pilot empirical paired SD × 1.5, 0.05)
```

pilot-only 规划的最大 required n 为 50，因此冻结第五组 50 个全新奇数 TEST seeds：15101–15199。该集合与 v1/v2/v3/v4 TEST seeds 全部不相交。冻结 v5 Git snapshot 前不得生成 TEST；v4 TEST 不得用于 v5 调参、阈值选择或结果解释。

正式结构一 B1 与 11 臂联合实验继续 BLOCK。v5 结果出来前禁止恢复 v4 的论文确认性 `REBUILD_JOINT` 或 legacy 优势声明。
