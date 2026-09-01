# 方向结构三 FindingDory Metadata Audit v0.1

> **已撤回并由 v0.2 取代。** 本版错误地把 `task_id` 定义为整数，并过度声明
> “官方 schema 已核验”；3-row 自造 fixture 不能证明真实数据已经接入。
> 下文保留的是被撤回的原始记录，仅用于审计，不代表当前证据状态。

日期：2026-08-25
成熟度：`metadata_adapter_dry_run`
证据边界：官方 schema 已核验；本轮运行的是仓库内代表性 fixture，不是真实数据成绩

## 1. 官方来源与许可边界

- [FindingDory 数据页](https://huggingface.co/datasets/yali30/findingdory)列出
  Apache-2.0、train 约 79.2k rows，以及八列
  `ep_id / video / question / answer / task_id / high_level_category /
  low_level_category / num_interactions`；
- [FindingDory 项目页](https://findingdorybenchmark.github.io/)描述长时程 embodied
  memory（具身记忆）任务；页面的 CC BY-SA 4.0 是网站许可，不能自动外推为全部数据许可；
- [FindingDory Habitat 数据页](https://huggingface.co/datasets/findingdory/findingdory-habitat)
  提供单独的 Habitat episode 文件入口，但其 raw schema、scene/time 隔离字段和衍生数据
  许可尚未在本机完成核验，因此登记为 `S3-DG-08`，不擅自采用。

## 2. 适配器结论

八列 SFT metadata 可以直接支持：

- video-question baseline（视频问题基线）；
- answer-frame retrieval truth（答案帧检索真值）；
- `answer=[[-1]]` 的显式无答案标记；
- episode、task、category 和 interaction count 的质量统计。

它不能直接支持：

- object instance identity（物体实例身份）或 candidate support（候选支持集）；
- actor/person、真实 activity event、source/target location；
- room/container、pose、visibility、occlusion、distance；
- instance transition/survival、person/event/habit truth；
- 完整 `DirectionThreeVisibleEpisode` 与 evaluator target。

因此适配器输出 `FindingDoryAdaptationRecord` 中间记录和 readiness audit（就绪审计），
不会把 category 或 frame index 偷换成实例、人物或事件真值，也不会自动注入 semi-synthetic
actor（半合成人物）。

## 3. Dry-run 报告

仓库 fixture 共 3 rows：普通单组答案帧、多组答案帧、`[[-1]]` 各一例。结果：

```text
accepted_rows                                  3
rejected_rows                                  0
can_build_video_question_baseline              true
can_build_frame_retrieval_truth                true
can_build_instance_transition_model            false
can_build_person_event_habit_truth              false
can_build_full_direction_three_episode          false
```

机器可读报告：`output/direction_three/findingdory_metadata_audit_v0_1.json`。

## 4. 运行

```bash
.venv/bin/python apps/evaluation_runner/prepare_direction_three_findingdory.py \
  tests/fixtures/direction_three/findingdory_metadata_sample.jsonl \
  --output output/direction_three/findingdory_metadata_audit_v0_1.json \
  --force
```

真实 parquet 读取当前没有伪装成已完成：本地环境未安装 `pyarrow/pandas`，且直接访问
Hugging Face rows API 本轮超时。后续可以在不改变本适配器语义的情况下增加可选 parquet
reader；只有 Habitat 原始字段核验通过后，才允许尝试构造完整 episode。
