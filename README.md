# Continual Personalized Semantic World Model

当前代码阶段：`Step 1 A0` 与首个 F0 纵切已实现，审核状态为 `BLOCK`；仅保留 `implemented_vertical_slice`，不标记为 `accepted`。

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

当前只修复复审阻断项并提交复审证据；在外部复审放行前，不进入多人物、访客污染、交接或变化检测扩展。

详细设计见 `docs/architecture/step1-a0-foundation.md`。
A0 阻断修复与复审候选证据见 `docs/reviews/step1-a0-review-closure.md`。
F0 评价底座与 A0 回放阻断修复及复审证据见 `docs/reviews/f0-evaluation-foundation-blocker-closure.md`。

方向结构三的独立定义、契约和可运行基线见 `docs/research/项目方向结构三_模糊语言联合后验主动确认与具身闭环_v1.0.md`。当前已推进到 `s3-1_oracle_closed_loop_baseline`：M29-L0 真值轨道可以运行主动观察、重新后验、执行反馈规范写回和失败后再规划；它仍不代表 S3-1 全部完成，也不代表真实 VIO、VLM、触觉、MPC 或机器人硬件已经验证。

S3 common pipeline（公共管线）现会在规范日志写入前重验证 request、可替换 fusion result（融合结果）和 provider action/observation/model/domain/outcome/candidate coverage（候选覆盖），将 query/model、候选落地、后验支持集与硬约束绑定回 request，强制具体 schema name/version 与时序绑定，并通过 `GroundedTaskExecution（落地任务执行包）` 绑定所选候选、实体、位置、实际动作、执行机会和反馈；失败更新保持零写入。该结果仍依赖 executor/provider/fusion（执行器/提供器/融合器）诚实报告；当前没有可信 provider/model registry，active verification 的机会 ID 也尚未绑定完整机会 envelope，因此不构成来源认证或硬件 attestation（硬件证明）。
