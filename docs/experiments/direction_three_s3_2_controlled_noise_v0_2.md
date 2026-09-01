# 方向结构三 S3-2 Controlled-Noise Baseline v0.2

日期：2026-08-25  
成熟度：`s3-2_controlled_noise_semantics_corrected`  
证据级别：oracle truth（真值）与合成噪声，不是真实感知证据

## 1. v0.2 纠正

- `known_in_support / known_out_of_support / true_unknown` 三种真值状态分离；
- retrieval miss（检索漏召回）只计入 known-target retrieval recall，不再改标为 unknown；
- Recall@k、MRR、ECE、Brier、NLL、unknown AUROC/AUPRC 和 selective risk 只在
  retrieval 成功或真实 unknown 的 conditional fusion set（条件融合集合）计算；
- sensor/channel missingness（传感器／通道缺失）按 `(episode, channel)` 采样一次，
  同一 episode 的全部候选共享 availability；
- 只对含随机 missingness 的条件使用 seed 重复；确定性条件只运行一次敏感度扫描；
- Student-t 95% 区间仅用于随机臂，accuracy 区间截断在 `[0,1]`；确定性臂区间为 null；
- 拿错物体指标拆成 known-target misidentification、unknown-target false-pick 和
  overall unsafe-pick。
- prediction cache `@0.2` 在读取时必须重新绑定调用方当前 dataset manifest、split、
  model versions、calibration domains 和 inference config，而不只验证缓存内部哈希。

## 2. 基础矩阵

| 条件 | Conditional Top-1 | Conditional NLL | Conditional Brier | Retrieval recall |
|---|---:|---:|---:|---:|
| clean | 1.0000 | 0.0660 | 0.0097 | 1.0000 |
| visual missing | 0.8333 | 0.1684 | 0.0911 | 1.0000 |
| six-channel miscalibration | 1.0000 | 0.1982 | 0.0745 | 1.0000 |
| visual/geometry dependence discount | 1.0000 | 0.1238 | 0.0390 | 1.0000 |
| identity / actor / event / habit noise | 0.8333 | 0.4819 | 0.2922 | 1.0000 |
| known target out of support | 1.0000* | 0.0000* | 0.0000* | 0.0000 |
| occlusion/distance proxy | 1.0000 | 0.2166 | 0.1189 | 1.0000 |

`*` 只来自该条件中唯一的真实 unknown probe；5 个 known-target probes 全部是 retrieval
miss，因此不进入 conditional fusion 指标。该条件的 unknown AUROC/AUPRC 均为 null，
不能再被解释成 open-set 成绩。

## 3. 扩展扫描

```text
configuration runs                 33
cases                              198
stochastic configurations          18
deterministic configurations       15
aggregate cells                     21
scenario strata                    126
```

其中 stochastic configurations 只包括 `visual_missing` 和
`combined_sensing_noise`；temperature、dependence、occlusion、known-out-of-support
unknown-mass sensitivity 和 context noise 都是确定性敏感度扫描。

## 4. 运行

```bash
.venv/bin/python apps/evaluation_runner/run_direction_three_controlled_noise.py \
  --output output/direction_three/s3_2_controlled_noise_v0_2.json --force

.venv/bin/python apps/evaluation_runner/run_direction_three_controlled_noise.py \
  --expanded-study \
  --output output/direction_three/s3_2_controlled_noise_study_v0_2.json --force
```

这些结果仍只是 pipeline semantics（管线语义）和敏感度 sanity check（健全性检查），
不能代替真实噪声标定、足够种子数或外部有效性实验。

## 5. 数据接入前复核

2026-08-25 已重新生成基础报告与扩展报告。随机缺失操作显式记录
`scope=episode_channel`，同一 episode 内所有候选共享一次通道缺失采样。

```text
s3_2_controlled_noise_v0_2.json
sha256 d8fb9c939f5d72a46554ee942a2580c01ea372321b3b4cebeddae92cf5449f3a

s3_2_controlled_noise_study_v0_2.json
sha256 08190bf538134d28778c2a7e201cdb9892eaddb1ce2c6c595b117615386fbcb9
```

数据契约同时升级为 `direction-three-episode@0.2`：`session_id`、
`object_instance_ids`、`source_name/source_version/source_record_refs` 已进入 manifest
谱系、跨 split 泄漏检查和 prediction cache episode binding。该变化只完成真实数据接入前
的隔离与绑定边界，不代表已经接入 FindingDory 真实 rows、视频或视觉模型预测。
