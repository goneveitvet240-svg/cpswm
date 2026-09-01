# 方向结构三 S3-2 Controlled-Noise Baseline v0.1

> **已撤回并由 v0.2 取代。** 本版把 retrieval miss 错标为 true unknown，按候选独立
> 采样通道缺失，并把确定性重复称为多种子实验；其中 retrieval/open-set 与区间结论无效。
> 下文保留的是被撤回的原始记录，仅用于审计，不代表当前结论。

日期：2026-08-25
成熟度：`s3-2_controlled_noise_baseline`
证据级别：确定性合成噪声与 oracle truth（真值）；不是真实感知证据

## 1. 已完成

- 统一 `DirectionThreeVisibleEpisode`，覆盖来源、split、household/scene/session、
  trajectory、video/frame、物体、人物、活动、位置、容器、可见性、遮挡、距离、
  查询、候选、六通道 availability、观察、执行和风险等级；
- `DirectionThreeEvaluatorTruth` 与方法可见 episode 结构分离；
- household、scene、time group、trajectory 和相邻视频帧跨 split 泄漏门；
- 观察动作、结果和 selection probability（选择概率）三者绑定，防止后续偏差校正
  在缺少 logging propensity（日志倾向概率）时静默运行；
- 10 个受控条件 × 6 个真值探针，共 60 cases；
- 扩展轨道覆盖 7 个噪声臂 × 3 个严重度 × 3 个冻结种子 × 6 个探针，
  共 378 cases，并报告 21 个聚合单元的 Student-t 95% 区间和 126 个探针分层；
- Recall@k、MRR、unknown AUROC/AUPRC、selective risk/coverage、ECE、Brier、NLL、
  误拿、询问、identity switch、任务成功、恢复和成本统一指标。

## 2. 首轮矩阵

| 条件 | Top-1 | Mean NLL | Mean Brier | 说明 |
|---|---:|---:|---:|---|
| clean | 1.0000 | 0.0660 | 0.0097 | oracle sanity check |
| visual missing | 0.8333 | 0.1684 | 0.0911 | identity 探针失去决定性通道 |
| six-channel miscalibration | 1.0000 | 0.1982 | 0.0745 | 排名未变但概率质量恶化 |
| visual/geometry correlation discount | 1.0000 | 0.1238 | 0.0390 | 相关证据降权 |
| identity noise | 0.8333 | 0.4819 | 0.2922 | 击穿 identity 探针 |
| actor noise | 0.8333 | 0.4819 | 0.2922 | 击穿 person 探针 |
| event noise | 0.8333 | 0.4819 | 0.2922 | 击穿 event 探针 |
| habit noise | 0.8333 | 0.4819 | 0.2922 | 击穿 habit 探针 |
| retrieval miss/open set | 1.0000 | 0.0952 | 0.0194 | 合成 unknown-mass 压力测试 |
| occlusion/distance proxy | 1.0000 | 0.2166 | 0.1189 | 排名未变但不确定性增大 |

这些数值只验证每类噪声按预期作用于对应通道。尤其 retrieval-miss 条件主动放大
`unknown` likelihood，不能作为 coverage-derived unknown 方法的成绩。

## 3. 运行

```bash
.venv/bin/python -m pytest -q \
  tests/test_direction_three_dataset.py \
  tests/test_direction_three_controlled_noise.py \
  tests/test_direction_three_metrics.py \
  tests/test_direction_three_findingdory_adapter.py \
  tests/test_direction_three_prediction_cache.py

.venv/bin/python \
  apps/evaluation_runner/run_direction_three_controlled_noise.py \
  --output output/direction_three/s3_2_controlled_noise_v0_1.json

.venv/bin/python \
  apps/evaluation_runner/run_direction_three_controlled_noise.py \
  --expanded-study \
  --output output/direction_three/s3_2_controlled_noise_study_v0_1.json
```

## 4. Decision gate

`S3-DG-selection-bias-estimator` 暂缓：observation selection bias（观察选择偏差）
需要先决定 estimand（估计目标）、logging policy（日志策略）和校正方法。当前工作没有
替用户选择；统一 episode contract 先保留后续估计所需的来源与选择上下文边界。

## 5. 尚未完成

- 当前 3-seed 区间仅是诊断，仍需增加种子数后才能作为稳定不确定性区间；
- candidate-set size、风险类别、人物数量、遮挡、时间跨度分层；
- FindingDory 官方八列 metadata adapter 已完成；真实 parquet 尚未在本机读取，且该
  schema 不含实例、人物、位置或事件真值；
- prediction cache 契约已完成；真实 VLM/GPU predictions 尚未产生；
- 各 baseline 独立调参的公平比较；
- 真实 unknown mass、action outcome likelihood 和 observation likelihood 校准。
