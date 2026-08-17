# F0 / OAM-PHM 首个长期纵切

实现状态：`implemented_vertical_slice`  
审核门：`BLOCK`  
验收状态：`not_accepted`  
日期：2026-08-14  
对应阶段：M31-v0 + M30-v0 + M29-L0 + M32-v0 的第一次共同迭代

## 1. 本轮实现的闭环

```text
BenchmarkManifest（基准清单）
├→ RoutineGenerationConfig（日程生成配置）
│  → RoutinePlan（可复现日程）
│  ├→ public simulator + task trajectory/frustum（公共仿真器 + 任务轨迹/视锥）
│  │  → IncidentalObservationContext（主任务途中的顺带观察上下文）
│  │  → ObservationOpportunityRecord（观察机会）
│  │  → ObservationDetectionResult（机器人可见检测结果）
│  └→ capability-gated gt.GroundTruthHabitTrajectory（能力门控真值，仅评价器可见）
└──────────────────────────────────────────────────────────────→ EvaluationReport（评价报告）
```

公共观察支路不读取或物化真值轨迹；评价器才同时取得公共结果、可信 manifest 和能力门控真值。

固定样例是：机器人执行“寻找昨天喝水的杯子”时，连续三天经过相关位置；书通常位于书桌，第二天出现于沙发，第三天返回书桌。第二天是 `isolated_anomaly（孤立异常）`，不是习惯覆盖。

## 2. 第二轮阻断修复后已实现但未外部验收的约束

1. 同一日程配置、清单、策略和随机种子产生完全相同的日程、真值、观察和评价报告；
2. `IncidentalObservationPolicy` 显式保存 primary-task robot trajectory（主任务机器人轨迹）、camera pose/frustum（相机位姿/视锥）与 location geometry（位置几何）；`IncidentalObservationContext` 保存主任务、视野覆盖、遮挡、额外动作成本、选择概率和似然模型；
3. `ObservationOpportunityRecord` 与顺带观察上下文的时间、选择概率和似然模型必须一致；对象身份、实现位置和检测时间只允许出现在成功的 `ObservationDetectionResult` 中；
4. observation opportunity（观察机会）严格由任务轨迹采样生成，不按 truth event（真值事件）逐条生成；检测位置只查询观察时刻或更早的状态并通过 camera frustum intersection（相机视锥相交）判断；`field_of_view_coverage=0` 或视锥外目标不能被检出；
5. opportunity 中的 visibility（可见度）是策略校准参数，不是隐藏目标实际视锥相交结果；未检出时，同一目标的隐藏迁移与未来未知目的地不能改变公共序列化输出；
6. 公共 `SymbolicSimulationResult` 不含 ground truth、routine plan ID/hash；在已覆盖的隐藏事件基数、未检出迁移和未来未知目的地反例中，公共序列化输出保持不变。评价器必须显式取得 capability-gated privileged view（能力门控特权视图）。CPSWM 内只有 M29 仿真器和 M32 评价模块可以导入 `cpswm_gt`；
7. M32 在计算指标前重新验证 manifest、完整 simulation、ground truth（真值）和嵌套记录；核验场景长度、计划、真值运行、策略、预算、版本、机会—结果双射及跨 household/session/trace/time 绑定；leakage detector（泄漏检测器）扫描完整 visible result（可见结果）的顶层与嵌套承载字段，`test_leakage_detector_scans_visible_result_top_level_carriers` 覆盖了顶层 `UUID.hex` 反例，但该检测器仍只声明 exact-reference detection（精确引用检测），不是通用信息流证明；EvaluationReport（评价报告）自身还会重算 evaluation/metric ID 并验证指标范围和身份继承；
8. checked-in manifest（版本库内基准清单）作为 benchmark authority（基准权威），保存完整预期 simulation content hash（仿真内容哈希）；同步篡改输出并重算 self-hash 仍会被拒绝；
9. recall（召回率）使用 maximum-cardinality matching（最大基数匹配）完成唯一真值事件的一对一匹配；重复检测不能重复命中，零分母返回 `null/NA, n=0`；`anomaly` 在本固定样例中仅评价 temporary exception（临时异常），不包含 contextual、gradual 或 abrupt change；
10. `declared_primary_task_additional_action_cost_total` 只汇总已选择观察动作的策略声明成本。固定策略声明值为零，但这不证明实际主任务没有中断或延迟；真实干扰必须等 M23–M27/E1 提供 execution trace（执行轨迹）后评价；
11. F0 manifest 只保留能由机器人侧记录核验的 `max_selected_observation_actions` 与 `max_selected_verifications`。尚未进入本纵切的 query result（查询结果）和 user question（用户询问）不再配置伪预算；
12. emitted message（发出消息）在 runtime 出口重新进行完整契约验证，payload/hash、schema、序号、枚举、身份与 session 边界不能通过 `model_copy` 绕过。
13. detection result ID（检测结果身份）绑定完整实现内容；不同 outcome/object/location/time 不会复用 ID，检出对象必须等于计划观察目标。

## 3. 运行方式

```bash
.venv/bin/python apps/evaluation_runner/run_f0_vertical_slice.py
.venv/bin/python -m pytest
```

阻断发现基线（2026-08-13）：`76 passed`，CLI SHA-256 为 `7315c3c497b275f894a4ff9f420b30b24ae3b7eeb039905506f6fd1aab8b4b35`。该结果仅证明当时任务可运行，不构成验收通过。

第一轮修复证据是 `106 passed`，CLI SHA-256 为 `2882b0b76ebf6bc416a01074766006721aa09b0e5766183858cab1647d28cf6d`；后续复审又发现真值驱动观察、常量 leakage 结果、非最大 recall 匹配、runtime 契约绕过及未检出目标的 visibility side channel（可见度侧信道）。本页不再把早期证据描述为当前结论。当前稳定快照为 `306 collected / 306 passed`；CLI 连续两次输出逐字节一致，SHA-256 均为 `7386c2e6e6e7b686a74e6be6f64af8e90fbecce593cdf587a910abf652a740d8`。资产链为 manifest v0.4、routine v0.2、policy v0.3，实现版本为 `synthetic-routines@0.2 / symbolic-simulator@0.8 / f0-evaluator@0.9`。无论本地测试是否通过，外部复审前仍保持 `BLOCK / not_accepted`。

## 4. 当前边界

这次提交只代表 F0 的第一个可运行纵切，不代表 Step 2 已整体完成：

- M30 当前执行的是可复现 `PLACE（放置）` 事件主路径；交接、并发人物和活动展开尚未进入执行器；
- M29 已用显式任务轨迹、位姿与视锥生成顺带观察，并以 capability-gated API（能力门控接口）隔离真值；仍是离散符号几何，尚未实现真实 VIO/SLAM、相机标定误差、观测延迟、实例混淆和反事实分支；
- M31 已固定首个样例、任务族、预算和指标接口，但尚未形成多家庭、多难度数据集；
- M32 当前输出四个纵切诊断指标；声明成本不是实际主任务干扰指标，尚未实现完整基线、回归比较和失败案例存储；
- M28-v0 的权限、删除和审计契约尚未进入本纵切；
- O-STaR faithful reproduction（忠实复现）和增强组合基线尚未接入；
- 观察还没有进入 M13–M19 的规范记忆、习惯阶段和抗污染巩固闭环。

## 5. 复审前的唯一工作入口

当前只修复评价底座和 A0 回放阻断项，并提交可复现的复审证据。下列原定扩展工作全部暂停，直到外部复审放行：

1. M30：多人物、访客、交接、渐变和突变的事件执行；
2. M29：遮挡、漏检、实例混淆、延迟与固定随机审计；
3. M31：把上述因素组织成版本化难度矩阵和数据划分；
4. M32：增加人物污染、异常误固化、变化适应和主任务干扰指标；
5. M03/M04：把日程、有限观察和评价运行接入追加式日志与严格回放；
6. M28：加入 oracle 通道授权、家庭隔离和审计记录。

完成这些 F0 共同能力后，沿现有执行步骤进入 B0 双观察入口和 M13–M16 规范记忆与当前信念投影。
