# D0 漂移原因配对基准

版本：`d0-shift-scenarios@0.3`  
日期：2026-08-14  
成熟度：`contract_tested_diagnostic_benchmark`  
范围：方向结构二统一论文的公共可证伪底座；不是 CF-BOCPD、OPCEU、RGRC 或 CIAV 的完成实现

## 1. 本轮推进结果

D0 首轮基准已经把三个变化原因固化为可复现、单因素干预的配对场景：

| 场景 | 唯一改变的真值因子 | 机器人可见变化 | 正确原因 |
|---|---|---|---|
| D0-O | observation process（观察产生过程） | 变化点后日志 propensity 从 1.0 变为 0.25 | `observation_policy` |
| D0-A | actor mixture（人物构成） | 变化点后物体由访客放到沙发；当前可见日志不含人物证据 | `actor_mixture` |
| D0-H | owner habit regime（主人习惯阶段） | 变化点后主人把物体放到沙发 | `owner_habit_regime` |

每个场景包含 control run（对照运行）和 shifted run（变化运行）。`D0ShiftCaseTruth` 通过五个 factor fingerprint（因子指纹）强制验证每个配对只改变与真因对应的一项，避免场景生成器把多个因素同时改变而制造捷径。

### 1.1 共同随机数与身份防泄漏修复

`run_paired(..., paired_noise_seed=...)` 现在把 selection draw（选择抽样）和 detection draw（检测抽样）的外生 \(U_t\) 与 `observation_policy_sha256` 解耦。相同 sensing clock（感知时钟）下，只改 `policy_id` 不会改变随机选择；低 propensity 下被选中的机会必然也是同一 \(U_t\) 的高 propensity 潜在结果。所有 paired runs 共享一个规范化 session/trace，D0-O 的前后拼接不再产生“两段 session/trace”标签捷径。

## 2. 真值隔离

候选模型只允许读取 `D0ShiftCaseInput`：

```text
case_id
change_time
target_person_id
control_run.robot_visible_records
shifted_run.robot_visible_records
optional actor_responsibility_evidence
```

其中 `D0VisibleSimulationRun` 仅包含：

- 观察机会及已记录 propensity；
- 检测结果；
- 机器人实际检测到的物体和位置；
- 时间、来源、任务和观测上下文。

它不包含 `true_cause`、人物真值、习惯阶段真值、事件类型、变化类型或完整 ground truth trajectory（真值轨迹）。模型完成推断后，benchmark side（基准侧）才用 `D0GeneratedCase.bind_prediction()` 将预测和隐藏真值绑定。

## 3. 首个可识别性反例

在当前 M29 可见接口中没有人物在场、人物轨迹或人—物接触证据。因此 D0-A 和 D0-H 被有意构造成：

```text
D0-A shifted visible log hash
== D0-H shifted visible log hash
```

两者产生完全相同的物体位置观测，但真实原因分别是“访客移动”和“主人习惯改变”。这证明的是结构不可识别性，而不是要求模型猜中 simulator latent label（模拟器潜在标签）：

> 仅使用物体位置、可见性和标准变化点检测，无法从被动日志中可靠区分人物构成漂移和主人习惯漂移。

因此后续不能只给 BOCPD 增加容量。CF-BOCPD 至少需要接入以下一种识别来源：

- M12 人物在场/身份/交互后验；
- CHEH/PCHMP 的人物责任假设；
- CIAV 的低打扰人物或容器微验证；
- 具有重叠支持的外生路径变化或其他可说明的识别条件；
- 无法识别时输出 `unresolved_shift`。

`D0ShiftCaseTruth` 因而新增 `identifiability_status`、`acceptable_cause_set` 和 `intervention_available`。无人物证据的 D0-A/D0-H 被标为 `non_identifiable`，其可接受潜因等价类为 `{actor_mixture, owner_habit_regime}`，同时评估器把 `UNRESOLVED` 作为认识论正确输出。报告新增 Log Loss（对数损失）、Brier Score（布里尔分数）、正确/错误弃权和 Risk–Coverage（风险—覆盖率）；旧 latent accuracy 只保留为诊断，不能单独支持创新主张。

## 4. 三条人物证据轨与诊断基线

`LoggedPolicyThenLocationBaseline` 执行透明规则：

1. 如果已记录 observation propensity（观察倾向概率）变化，预测观察策略漂移；
2. 否则，如果变化点后检测位置分布变化，预测主人习惯漂移；
3. 否则输出未决。

版本化场景上的结果：

| 指标 | 值 |
|---|---:|
| shift-cause accuracy | 0.6667 |
| macro-F1 | 0.5556 |
| observation-to-habit leakage | 0.0 |
| actor-mixture-to-owner leakage | 1.0 |
| false owner-habit change rate | 0.5 |

这个结果不是新方法成绩，而是把当前缺失的人物识别信号量化为一个明确的失败模式：访客变化被 100% 错写为主人习惯变化。

`ActorResponsibilityEvidence（人物责任证据）` 随后增加了显式、机器人可见的人物后验，但契约中不存在 `true_actor` 字段：

- `no_actor_evidence`：不提供人物证据，使用位置-only 基线；
- `controlled_noise`：正确人物概率 0.8、另一个人物 0.1、`unknown_actor` 0.1；
- `oracle`：真值人物概率为 1.0，且轨道标签明确声明为 oracle。

三条轨使用完全相同的 D0 真值因素和物体位置日志。`LoggedPolicyActorLocationBaseline` 在人物证据存在时先比较目标人物与非目标人物后验质量，再判断位置变化。

| 轨道 | accuracy | actor→owner leakage | 含义 |
|---|---:|---:|---|
| no actor evidence | 0.6667 | 1.0 | D0-A/D0-H 不可识别 |
| controlled-noise actor posterior | 1.0 | 0.0 | 当前小型场景中，带不确定性的人物证据足以解除等价 |
| oracle actor | 1.0 | 0.0 | 信息上界 |

这仍然是 **diagnostic baseline（诊断基线）**，不是 CHEH/PCHMP 创新结果。GESTO/HUMEMBR 等已有项目已覆盖人—物活动或人物身份功能，因此“增加人物标签”本身不能作为创新。下一步必须在更加困难的多候选、交接、人物缺失和身份切换场景中证明人物责任竞争、来源约束消息传递和可逆巩固优于普通 actor posterior（人物后验）接入。

## 5. 代码与版本化资产

- 场景、真值防火墙和因子校验：`src/cpswm/system/evaluation_operations/d0_shift_scenarios.py`
- 透明诊断基线：`src/cpswm/system/evaluation_operations/shift_baselines.py`
- 漂移原因指标：`src/cpswm/system/evaluation_operations/shift_attribution.py`
- 单流未知变点任务：`src/cpswm/system/evaluation_operations/online_shift_attribution.py`
- 版本化配置：`benchmarks/d0_shift_attribution/d0_scenario_config_v0.1.json`
- 可执行入口：`apps/evaluation_runner/run_d0_shift_attribution.py`
- 回归和防泄漏测试：`tests/test_d0_shift_scenarios.py`

运行：

```bash
.venv/bin/python apps/evaluation_runner/run_d0_shift_attribution.py
```

## 6. 下一工程依赖

最小 M12 robot-visible person evidence（机器人可见人物证据）三轨已经完成。下一步不是删除 D0-A 或把“同屋多人”降级，而是从普通人物标签基线进入 CHEH/PCHMP 的新方法：

1. 把单步 `PLACE` 扩展成 `pick-up → carry → handoff → place` 隐藏事件链；
2. 在同一观察间隙保留主人、访客、机器人和未知人物的互斥责任假设；
3. 增加人物部分可见、handoff（交接）、身份切换与相似实例噪声；
4. 实现 CHEH 的 `branch/revise/retract` 契约和 top-1 事件图直接基线；
5. 将人物责任后验接入 RGRC 隔离区，但暂不允许它直接巩固进主人习惯。

该接口是 CHEH、PCHMP、CF-BOCPD 和 RGRC 的共同依赖。

## 7. D0 与在线任务的严格边界

D0 三对继续作为 paired causal diagnostic（配对因果诊断），不再被称为在线归因成绩。独立 `online-shift-suite@0.1` 已新增：候选模型只读取一条 observation stream（观察流），看不到 control run、真实 change time（变点）、family、split 或 latent cause；当前生成 6 seeds × 5 families = 30 个案例，跨 household/object，包含 observation、actor、habit 与 observation+actor、observation+habit 同时变化，并使用加盐乱序的 opaque UUID（不透明 UUID）防止 case ID 编码标签。当前只是任务/评估基础设施完成，CF-BOCPD 算法和 BOCPDMS 匹配对照尚未完成。
