# 方向结构三 S3-1 多情境 Oracle Suite v0.1

日期：2026-08-25
成熟度：`s3-1_multi_scenario_oracle_suite`
证据级别：确定性 oracle（真值）契约与闭环测试，不是真实感知或机器人证据

## 1. 本轮目标

在不缩小结构三六项完整能力、不引入真实模型训练的前提下，把单个 M29-L0
闭环扩展为成套、可回放、可机器读取的 S3-1 情境评价。该套件专门回答：

1. 多人物、相似实例、隐藏移动、容器、跨时间和未建图目标能否进入同一公共契约；
2. 身份、位置、人物、事件、习惯五个上游维度能否分别注入真值并审计；
3. 询问、移动视点、微观察、开容器、安全触觉和停止/拒答是否均被覆盖；
4. 六类执行结果能否保持概率语义并进入规范日志；
5. `not_found` 是否能够触发下一候选再规划，而不是把目标直接删除。

## 2. 实现

```text
src/cpswm/system/evaluation_operations/direction_three_oracle_suite.py
  17 个确定性情境
  3 个独立组合真值 probe（2、3、5 维联合注入）
  五维真值载荷
  公共 pipeline 驱动
  汇总与逐情境 JSON 指标

apps/evaluation_runner/run_direction_three_oracle_suite.py
  直接运行与原子 JSON 输出

tests/test_direction_three_oracle_suite.py
  13 项覆盖、manifest、组合真值与语义测试
```

运行：

```bash
.venv/bin/python -m pytest -q \
  tests/test_direction_three_grounded_search.py \
  tests/test_direction_three_oracle_suite.py

.venv/bin/python \
  apps/evaluation_runner/run_direction_three_oracle_suite.py \
  --output output/direction_three/s3_1_oracle_suite_v0_1.json

.venv/bin/python \
  apps/evaluation_runner/run_direction_three_oracle_suite.py \
  --combinations \
  --output output/direction_three/s3_1_oracle_combinations_v0_1.json
```

## 3. 情境覆盖

| 组 | 覆盖 |
|---|---|
| 单维真值探针 | identity、location、person、event、habit |
| 组合真值探针 | identity+location、person+event+habit、五维全联合 |
| 场景语义 | 多人物、相似实例、隐藏移动、关闭容器/遮挡、跨时间、未建图目标 |
| 主动动作 | ask_user、move_viewpoint、micro_verify、open_container、touch |
| 停止语义 | 无正价值动作时 stop；未知目标时 abstain |
| 执行结果 | success、not_found、grasp_failed、object_slipped、partial、unknown |
| 恢复 | not_found 降低错误位置候选并切换到真实目标 |

所有接触与开容器动作仍必须经过授权、安全、校准域和风险门控。oracle provider
只能通过现有公共契约返回观察或反馈，不能直接写入世界事实。

## 4. 本轮结果

```text
原结构三测试                     77 passed
新增 oracle suite 测试            13 passed
S3-1 定向合计                     90 passed
情境数                            17
独立组合 probe                     3
expected_behavior_met_rate       1.0000
failure_recovery_success_rate    1.0000
wrong_object_pickup_rate         0.0000
clarification_rate               0.0588
task_success_rate                0.6875
```

`task_success_rate=0.6875` 是全部已知目标情境的原始比例，其中故意包含 stop 和四个
失败反馈情境；这些情境的验收目标不是伪造成功，而是正确停止或规范写入失败。因此本轮
主要通过条件是 `expected_behavior_met_rate=1.0`，不能把它解释成真实任务成功率。

成本是符号 oracle 动作成本，不是真实路径测量：

```text
total_motion_cost        0.14
total_time_cost          0.14
total_interruption_cost  0.05
```

## 5. 尚未完成

- 已完成 2、3、5 维联合注入的 3 个组合 probe；尚未把主动观察动作嵌入同一组合轨迹；
- `grasp_failed / object_slipped / partial / unknown` 已验证规范写入，但尚未形成多步恢复；
- 尚未报告 Recall@k、MRR、真实路径长度、真实搜索时间和不必要询问率；
- 17 情境基线已冻结为可复用 scenario manifest；组合 probe 当前保持独立轨道；
- 没有 FindingDory、真实 VLM/RGB-D/re-ID、仿真器或机器人硬件证据；
- 当前结果不改变 S3-1 仍在进行中，也不解除总项目 F0 审核门。

## 6. 下一边界

下一步应把本套件变成 S3-2 的冻结输入：先抽出机器可读 scenario manifest 和统一
episode schema，再对六通道分别注入缺失、相关性、误校准、身份噪声、actor/event/habit
错误、召回漏失和遮挡漏检。HCS、coverage-derived unknown mass 和 CO-CIP 仍作为后续
独立方法臂，不覆盖当前 weighted log-opinion pool（加权对数意见池）基线。
