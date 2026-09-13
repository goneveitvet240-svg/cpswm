# CPSWM 项目导航

[当前工作与 PR 分类](docs/collaboration/GITHUB_INDEX.md) · [双机交接入口](docs/collaboration/START_HERE.md) · [任务板](docs/collaboration/TASK_BOARD.md) · [结构二完整框架](docs/结构二/README.md)

共享集成分支目前只归并文档证据；统一运行候选在 [#15](https://github.com/goneveitvet240-svg/cpswm/pull/15)，位姿开发在 [#16](https://github.com/goneveitvet240-svg/cpswm/pull/16)，B 最新修复在 [#17](https://github.com/goneveitvet240-svg/cpswm/pull/17)。CI/独立复核仍有阻塞，尚未统一验收。

以下是本分支旧代码基线的说明，保留历史内容；当前研究进展以工作导航的分支和 SHA 为准。

<details>
<summary>展开历史代码说明</summary>

# Continual Personalized Semantic World Model

当前代码阶段：正式数据接入前的 contract/fixture vertical slices（契约/样例纵切）可运行，
静态质量门禁和两轮对抗回归已闭环；真实数据、真实机器人、外部强基线与论文有效性门禁仍为
`BLOCK`，不得把 `implemented_vertical_slice` 标记为 `accepted` 或真实验证完成。

## 方向结构二规范入口

结构二现有协议、实验和审计文件较多。第一次阅读请从
[`docs/结构二/README.md`](docs/结构二/README.md) 开始，其中按“一页总览 → 完整框架与技术路线 →
Task 地图与进度 → 实验与复现”组织，并明确区分工程完成、开发证据、失败门和论文级未完成项。

## 本地运行

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m pytest
```

## 已实现

### M01：公共契约

- 基础记录元数据、半开有效时间区间和证据引用；
- `RelationAssertion`、`EventRecord`、`BeliefSnapshot`；
- `ObservationLikelihoodRequest` / `ObservationLikelihoodModel`；
- 带读取预算的 `WorldModelQuery` / `WorldModelQueryResult`；
- 独立的 `UserCorrectionEvent` 与权限范围；
- `ProjectionCheckpoint` 与 `RebuildCostEstimate`；
- 独立 `cpswm_gt` 真值类型和 import boundary（导入边界）测试。

### M02：身份、时间与坐标

- UUID 命名空间和 household 隔离；
- UTC 时间标准化与跨时钟对齐；
- 有效时间版本化的直接、逆向和多跳坐标变换；
- 跨 session 地图对齐所需的统一 Frame Registry（坐标系注册表）。

### M03：持久化与回放

- append-only（追加式）原子事务日志；
- `global_commit_seq`、`InputWatermark` 和幂等提交；
- online / training / replay 分区；
- canonical（规范）与 derived（派生）存储隔离；
- `ReplayManifest`、快照清单和失效记录。
- 固定零水位、批内记录ID唯一性和日志落盘/重新加载；
- 指定水位日志指纹，防止清单与实际输入脱离。

### M04：运行编排

- 同进程 Command / Event / Handler；
- 确定性事件处理顺序、有界重试和幂等执行；
- trace、代码、配置和模型版本记录；
- 固定时间、随机种子和确定性 UUID 的回放；
- 精确或声明数值容差内的结果比较。
- 实际 Git HEAD、源码树、配置和模型版本强制核验；
- 两个独立Python进程加载同一日志后的重启回放测试。
- emitted message 的确定性身份、完整契约边界复验及 household/session/trace/causation 继承校验。

### 方向结构二：D0 漂移原因诊断基准

- D0-O / D0-A / D0-H 三组可复现、单因素配对场景；
- 模型输入与 evaluator-only truth（仅评价器真值）结构隔离；
- observation/actor/identity/habit/noise 五类因子指纹和防混杂校验；
- 漂移原因 accuracy、macro-F1、主人习惯误报与泄漏指标；
- 首个位置-only 诊断基线及可执行评估入口；
- 已确认：缺少人物证据时，访客变化与主人习惯变化观测等价，位置基线的 actor→owner leakage 为 1.0。
- 无人物、受控噪声人物后验、oracle 人物三条诊断轨；受控噪声/oracle 在首版场景中将 actor→owner leakage 降至 0，但不作为新方法成绩。

详细设计见 `docs/architecture/d0-shift-cause-paired-benchmark.md`。

### CHEH：反事实假设事件超图首纵切

- 从物体前后位置观测生成主人、访客、未知人物和交接事件链的互斥假设；
- 支持 `branch / revise / retract / rebuild`；
- 所有候选保留端点和人物证据来源；
- 不可变 revision chain（修订链）、内容哈希和父版本绑定；
- 当前为 `method-specified, contract-tested heuristic vertical slice（方法已规格化、契约测试的启发式纵切）`；来源字段已做上下文、端点、时间、去重与反证约束，但尚不能宣称严格 `provenance-constrained revision（来源约束修订）` 或 causal counterfactual inference（因果反事实推断），也尚未通过 top-1/独立候选直接基线与具身效用验证。

详细设计见 `docs/architecture/cheh-first-hidden-event-vertical-slice.md`。

## 当前边界

Step 1 提供的是可替换的 A0 参考实现，尚不包含生产数据库、ROS 2、分布式消息系统，也不宣称 M13–M20 的领域存储、推理和查询服务已经完成。

上面的 Step 1/A0 描述只代表早期基础纵切，不再是整个仓库的当前推进边界。结构二已经进入多人、
访客污染、交接、变化检测、可逆修订和行动效用开发，但这些结果仍属于 D0 开发证据；D1/D2、
外部强基线原生复现和独立托管确认尚未完成。结构二当前状态统一以
`docs/结构二/README.md` 为入口，旧复审文件只保留历史证据语义。

详细设计见 `docs/architecture/step1-a0-foundation.md`。
A0 阻断修复与复审候选证据见 `docs/reviews/step1-a0-review-closure.md`。
F0 评价底座与 A0 回放阻断修复及复审证据见 `docs/reviews/f0-evaluation-foundation-blocker-closure.md`。

方向结构三的独立定义、契约和可运行基线见 `docs/结构三/项目方向结构三_模糊语言联合后验主动确认与具身闭环_v1.0.md`。当前已推进到 `s3-2_controlled_noise_semantics_corrected`：17 个确定性真值情境与 3 个组合 probe 已覆盖五维真值、主动观察、六类执行结果和 `not_found` 再规划；统一 episode contract 隔离评价器真值、记录 observation selection probability（观察选择概率）并阻断跨 split 泄漏。S3-2 已明确分离 known-out-of-support（已知但不在支持集）与 true unknown，通道缺失按 episode/channel 采样；扩展扫描为 198 个有效配置 cases，其中只有随机 missingness 臂使用多种子区间。FindingDory adapter 已接受 `task_41` 字符串格式，但仍只是 fixture-validated（样例验证），真实官方 rows/parquet 尚未接入。Prediction cache 在读取时会重新绑定当前 dataset、split、model versions、calibration domains 和 inference config。详见 `docs/experiments/direction_three_s3_1_oracle_suite_v0_1.md`、`docs/experiments/direction_three_s3_2_controlled_noise_v0_2.md` 与 `docs/experiments/direction_three_findingdory_metadata_audit_v0_2.md`。

S3 common pipeline（公共管线）现会在规范日志写入前重验证 request、可替换 fusion result（融合结果）和 provider action/observation/model/domain/outcome/candidate coverage（候选覆盖），将 query/model、候选落地、后验支持集与硬约束绑定回 request，强制具体 schema name/version 与时序绑定，并通过 `GroundedTaskExecution（落地任务执行包）` 绑定所选候选、实体、位置、实际动作、执行机会和反馈；失败更新保持零写入。该结果仍依赖 executor/provider/fusion（执行器/提供器/融合器）诚实报告；当前没有可信 provider/model registry，active verification 的机会 ID 也尚未绑定完整机会 envelope，因此不构成来源认证或硬件 attestation（硬件证明）。

</details>
