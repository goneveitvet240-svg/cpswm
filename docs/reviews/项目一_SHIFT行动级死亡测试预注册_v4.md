# 项目一 SHIFT 行动级死亡测试预注册 v4

冻结日期：2026-08-22

v3 仅保留方向性否决证据。v4 是 action death-test contract 的论文确认性候选版本。

## Candidate ledger 与 deterministic replay

- 报告保存完整 validation input artifact。
- 每臂保存全部 18 个 detector candidates 的 params、prediction、input hash 和 prediction hash。
- validator 从 input+params 重新运行模型，逐案例精确比较 prediction。
- shared track 从 18 个候选重算完整 metrics ledger、ledger hash 和预注册排序 argmin。
- independently-retuned track 从相同 detector predictions 与固定 117-policy space 重算全部 2106 项 metrics ledger、ledger hash 和 argmin。
- pilot/TEST 保存独立 input artifacts；选定参数的 prediction 必须可从对应 input 确定性重放。

## 跨时间状态机

consolidation 必须经过三个严格递增时间戳：

```text
RESET_OLD_REGIME(t0)
→ VERIFY_NEW_EVIDENCE(t1)
→ CONSOLIDATE_NEW_REGIME(t2), t0 < t1 < t2
```

`t1` 来自 observation stream 中 reset 之后真实存在的新 detection evidence；没有新证据不得 consolidation。只有到 `t2` 才视为恢复。

## Utility sensitivity

固定四个场景，不重调 detector/policy，只重算已冻结动作的 utility：

1. base；
2. false reset 与 corrupted mass cost ×1.5；
3. unrecovered habit cost ×1.5；
4. verification cost ×2。

shared/retuned 两轨均报告四场景 × 三臂 metrics 和 joint-vs-ordinary/legacy regret intervals。`REBUILD_JOINT` 必须在全部八个 track×utility 场景中保持 joint-minus-legacy regret 区间下界 ≥0.05，否则降为 `INCONCLUSIVE`。

## Conservative power

每个 endpoint×reference×track 使用：

```text
powered SD = pilot empirical paired SD × 1.5
```

安全系数、powered SD、required n 均写入报告并从 pilot artifacts 重算。八项 required n：shared 39、340、22、317；retuned 19、326、24、317。全局冻结 n=340。

最终 TEST 使用第四组全新 340 个奇数 seeds：13101–13779，不复用 v1/v2/v3 TEST，也不根据 v3 结果调参。正式 B1 与 11 臂联合实验在 v4 contract 通过前继续 BLOCK。
