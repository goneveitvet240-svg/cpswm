# 项目二 provenance-safe replay dataset protocol v0.2

日期：2026-08-24  
状态：D0 安全与内容完整性硬门已通过；D1–D4 外部数据门仍未进入；未选择外部数据集

## 1. 不可缩减边界

数据缺失只允许记为 `unavailable（不可用）` 或 `partial（部分可用）`，不得删除开放世界、隐藏事件、多行为人、可逆归因、项目一回流或具身反馈能力。Evaluator-only truth（仅评测器可见真值）与模型输入物理分离：

- `ProjectTwoReplayEpisode`：普通方法和 baseline 唯一可消费的可见记录；
- `ProjectTwoEvaluatorTruthEnvelope`：独立 evaluator store（评测器存储）；
- `ProjectTwoReplayDatasetManifest`：版本、来源哈希、成熟度和 split 绑定；
- `ProjectTwoReplayDataset`：验证 manifest、visible episode 和 truth envelope 的完整 join coverage（连接覆盖率）。

递归 leakage scanner（泄漏扫描器）拒绝 `true_actor`、`true_mechanism`、`true_location`、`latent_state`、`event_chain_truth` 及 `oracle_*`/`evaluator_truth` 别名。公开 Pydantic contract 使用 `extra="forbid"`，因此模型输入不能通过额外字段夹带真值。

## 2. 字段语义

每个 `ProjectTwoReplayStep` 表达：household/session/trace/episode、时间戳和 valid-time interval（有效时间区间）、object instance/category（物体实例/类别）、before/after `ObservationDetectionResult`、source/attempted/observed destination location、visibility（可见性）、occlusion（遮挡）、detection confidence（检测置信度）、actor/mechanism/ordered-role evidence、search/place/transfer `ExecutionFeedbackRecord`、不确定 outcome distribution（结果分布）、observation/action opportunity（观察/行动机会）、来源、source hash（来源哈希）和 unavailable fields（不可用字段）。

`attempted_location_id` 与 `observed_destination_location_id` 是两个独立字段。D0 没有 post-action detector（动作后检测器），因此即便 `P(success)=0.8`，`observed_destination_location_id` 仍为 `None`，并显式记录 `post_action_destination_observation=unavailable`；不会把概率性成功自动改写成确定落点。

## 3. 数据成熟度

| 层级 | adapter 状态 | 当前能力 | 明确缺口 |
|---|---|---|---|
| D0 synthetic oracle（合成 oracle） | 已实现 | sealed synthetic trace、独立 truth envelope、完整 replay 闭环 | 不构成真实世界证据 |
| D1 simulator / annotated replay（模拟器/人工标注回放） | 接口已建，数据 unavailable | contract 已冻结 | 未选择模拟器或标注源 |
| D2 real perception replay（真实感知回放） | 接口已建，数据 unavailable | contract 已冻结 | 缺真实检测、标定、pose covariance |
| D3 household execution（家庭执行） | 接口已建，数据 unavailable | contract 已冻结 | 缺家庭长期轨迹、隐私与授权方案 |
| D4 embodied robot execution（具身机器人执行） | 接口已建，数据 unavailable | contract 已冻结 | 缺机器人、执行器和 post-action sensing |

## 4. Split 与 leakage 防护

Validation（验证集）和 sealed test（封存测试集）必须同时满足 household、scene、object-instance、object-family disjoint（家庭、场景、物体实例、物体族互斥）。Manifest 构造阶段拒绝任一键跨 split 重叠；episode、record、feedback ID 重复也会被拒绝。测试集 episode ID 不进入 tuning API，`MethodTuningSelection.test_episode_ids_seen` 非空会直接验证失败。

质量门不再无条件列出检查名称。`enforce_project_two_replay_gate` 会逐项真实判定，失败即抛出 `ProjectTwoReplayGateError`。Manifest 的 `visible_content_hash` 与 evaluator envelope 的 `evaluator_content_hash` 分别绑定两侧内容；adapter 后改写任一字段会在数据集构造阶段失败。

## 5. D0 replay pilot 规模

- 4 episodes：2 validation + 2 sealed test；
- 128 steps，83 条 execution feedback；
- observation coverage = 0.6484375；
- 83 条反馈全部保留原 delayed timestamp；
- 128/128 steps 缺真实 sensor calibration、robot pose covariance 和 post-action destination observation；
- evaluator truth 中 unknown actor = 4、unknown mechanism = 4；D0 已包含合成开放世界 case；
- hard gate `ready=true`、`failures=[]`；真实传感字段仍作为 warning/unavailable 保留。

同一个 `ProjectTwoReplayEpisode` 原样送入项目二完整方法和全部非-oracle baseline；oracle upper bound（oracle 上界）只由 evaluator 在评分阶段读取独立 truth envelope。Benchmark 无需为 D0 特判数据字段，后续 D1–D4 adapter 只要生成相同契约即可被无改动消费。

## 6. 尚需用户决定

本轮遵守约束，没有下载或选定外部数据集。下一步需要用户在收到候选数据集的覆盖能力、许可、缺失字段和适配成本表后决定：

1. D1 采用哪一种 simulator/人工标注来源；
2. D2 是否优先做已有 rosbag/视频回放，还是新采真实感知；
3. D3/D4 的家庭隐私、授权、机器人平台和采集规模；
4. 是否新增带真实 unknown actor / unknown mechanism 的受控采集轨。

实现入口：`src/cpswm/contracts/project_two_replay.py`、`src/cpswm/system/evaluation_operations/project_two_dataset.py`、`project_two_dataset_adapters.py`；冻结配置见 `configs/project_two_datasets/d0_pilot_v0_2.json`。
