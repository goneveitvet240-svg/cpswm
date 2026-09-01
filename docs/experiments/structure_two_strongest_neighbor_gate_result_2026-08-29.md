# 结构二 CARE-WM strongest-neighbor gate 结果

日期：2026-08-29  
协议：`structure-two-strongest-neighbor-gate@0.1`  
artifact：`artifacts/project_two_v04_development/structure_two_strongest_neighbor_gate_v0_1.json`  
content SHA-256：`21347c71d3a327641d901f8b98d3385e481e5fe8e180ca98aae4441a95483e49`

## 结论

**CARE-WM strongest-neighbor gate 未通过。** 这不是审计失败或边缘统计结果，而是明确的
行动效用失败。四个公开邻近系统的 semantic-faithful matched adapters（语义忠实匹配适配器）
中，validation 选择 `brainctl_matched` 为最强者；在全新 sealed holdout 上，CARE 相对它的
`true_environment_regret_per_step` 高 `+0.543836`，paired-cluster 95% CI 为
`[+0.522267, +0.567480]`，而负值才表示 CARE 获益。

按照预注册规则，当前证据要求停止把 CARE-WM 描述为结构二的核心方法创新。该判定只否定
当前的 future embodied action-regret escrow（未来具身行动遗憾托管）机制主张，不删除结构二
完整范围：actor / identity / hidden-event cause / regime 四轴、多主体、开放世界 unknown、可逆
归因和具身反馈闭环均继续保留。

## 主要冻结比较

| 比较（CARE − 对照，负值有利） | 均值 | paired-cluster 95% CI | 判定 |
|---|---:|---:|---|
| validation-selected strongest published neighbor | +0.543836 | [+0.522267, +0.567480] | 失败 |
| sequential no consolidation | +0.552124 | [+0.529132, +0.576473] | 失败 |
| CARE without action regret | +0.525651 | [+0.503906, +0.549219] | 失败 |
| full rerun | +0.391594 | [+0.349175, +0.437543] | 失败 |
| oracle upper bound | +0.850593 | [+0.820833, +0.881525] | 仅作上界 |

validation 选择的关键参数为：`brainctl_matched=0.75`、
`sequential_no_consolidation=responsive`、`care_no_action_regret=0.85`、`care_wm=1.25`。

## 分场景结果

下表仍使用 CARE − `brainctl_matched`，负值才有利。

| 场景族 | 差值 | 冻结角色 | 结果 |
|---|---:|---|---|
| high_multi_actor_contamination | +0.762266 | required gain | 失败 |
| delayed_identity_correction | +0.918550 | required gain | 失败 |
| open_world_hidden_event | +0.707771 | required gain | 失败 |
| clean_recurrent_habit | +0.279898 | non-inferiority guardrail | 失败 |
| low_consequence_location | +0.296267 | non-inferiority guardrail | 失败 |
| misspecified_consequence | +0.298264 | non-inferiority guardrail | 失败 |

三个必胜族没有一个获益，三个 guardrail（护栏）也全部越界。因此不存在“总体失败但目标难例
成功”的可保留子结论。

## 失败机制拆解

CARE 在 144 个 holdout episodes 上总计执行：

- `verify=576`：每个 episode 都用满 4 次物理核验预算；
- `promote=144`、`escrow=237`；
- `retract=1313`、`corrected_revision=1313`，显示活动粒子签名导致高频账本改写。

相对 `brainctl_matched` 的平均 `+0.543836/step` 可按冻结计分拆为：

| 部分 | CARE − brainctl |
|---|---:|
| information-cost difference | +0.081032 |
| repair-cost difference | +0.437905 |
| action-only remainder | +0.024899 |

最后一行是事后诊断，不是新的确认性检验：即使把 CARE 的核验成本和全部账本修复成本都设为
零，CARE 的纯行动结果仍更差；六个 family 的 action-only difference 均为正
（`+0.00547` 至 `+0.05191`）。原始 action metrics 也显示 CARE 的 put-back error 没有稳定
下降，search success 在各族均不优于 `brainctl_matched`。因此根因不是单纯“成本惩罚太重”，
而是早期核验加频繁活动写入没有转化为后续行动收益。

## 外部转移

| 外部回放 | episodes | CARE − brainctl | 状态 |
|---|---:|---:|---|
| D1 simulator-annotated replay | 20 | +0.395039 | 确认性护栏失败 |
| D2 real-perception example | 3 | +0.411944 | 方向性失败 |

D2 有 28 项与同一 `evidence_cluster_id` 绑定的相关轴标注进入 quarantine（隔离）。这是为了
遵守 CHEH exactly-once（恰好一次）约束，对所有臂统一执行；D2 样本量只有 3，不作显著性主张。

## 审计与执行期修正

以下机制/完整性门全部通过：四轴均被实际消费；非 oracle 决策均未提前读取 evaluator truth；
所有臂消费相同 visible stream；CARE 账本可精确重放、无重复 promotion；五类账本操作均被触发；
raw holdout seeds 未写入 artifact；content/protocol/commitment/provenance 静态验证通过。
随后执行完整 deterministic recomputation（确定性重算），新旧报告的 content SHA-256 均为
`21347c71d3a327641d901f8b98d3385e481e5fe8e180ca98aae4441a95483e49`。

第一次执行在完成 D0 计算但尚未输出或查看任何结果时，于 D2 发现共享 evidence cluster 会被
当作多条独立证据。随后冻结加入 visible-only information-gain canonicalization（仅可见信息增益
规范化），并完整重跑。修正没有改变 D0/D1 数据、参数、seed、指标或阈值；该事实已同时写入
预注册执行记录和 artifact 的 `execution_amendment`。

## 证据边界与后续规则

- 外部系统是 semantic-faithful matched adapters，不是作者官方代码复现；所以本结果不能证明
  CARE 弱于这些系统的官方完整实现，只能证明它没有通过当前共同结构二接口上的最强邻近门。
- 但 CARE 同时显著输给 repository-native no-consolidation 和自身去 action-regret 消融，因此
  “适配器不够官方”不能挽救当前核心机制主张。
- D0 是 synthetic，D1 是 simulator-annotated development replay，D2 仅三个方向性样例；没有
  D3 长期家庭数据或 D4 真实机器人执行。
- 当前 v0.1 sealed set 已使用完毕，不得再用于调参。若提出实质不同的新机制，必须在 validation
  上完成最低成本 falsifier（证伪器）后，另建新协议、新 seed commitments 和新 sealed set。
