# 方向结构三 FindingDory Metadata Audit v0.2

日期：2026-08-25  
成熟度：`fixture_validated_real_rows_pending`  
证据边界：官方页面列名与展示样例已用于修正契约；真实 parquet/rows 尚未成功读取

## 1. 修正后的边界

- `task_id` 使用官方展示形式的字符串，例如 `task_41`，契约为 `^task_[0-9]+$`；
- 适配器继续要求八列
  `ep_id / video / question / answer / task_id / high_level_category /
  low_level_category / num_interactions`；
- 当前 3-row fixture 已改用 `task_41 / task_7 / task_12`，证明契约和审计程序可运行；
- fixture 不是官方真实行，因此不再声称“官方 schema 已完成真实数据核验”；
- 真实 parquet 或 rows ingestion（行数据接入）成功前，状态保持
  `fixture_validated_real_rows_pending`。

## 2. 当前可用与不可用字段

现有列可支持 video-question（视频问题）和 answer-frame retrieval（答案帧检索）准备；
不能提供 object instance、actor/person、真实事件、source/target location、pose、room、
container、visibility、occlusion、candidate support 或完整 evaluator truth。

适配器不会用 category、frame index 或 semi-synthetic actor（半合成人物）填补这些字段。

## 3. Dry-run

```text
adapter_version                    findingdory-metadata@0.2
accepted_rows                      3
rejected_rows                      0
real_official_rows_ingested        false
```

运行：

```bash
.venv/bin/python apps/evaluation_runner/prepare_direction_three_findingdory.py \
  tests/fixtures/direction_three/findingdory_metadata_sample.jsonl \
  --output output/direction_three/findingdory_metadata_audit_v0_2.json --force
```

FindingDory Habitat 原始 episode schema、scene/time grouping 和许可边界仍保留在
`S3-DG-08`，没有被本次契约修正替用户决定。
