# 结构二动作响应完整闭环 v0.2：两轮对抗审核

> 本文件记录第一次两轮审核。后续发现与修复见
> `structure_two_full_scientific_loop_second_two_round_adversarial_audit_2026-09-08.md`；最新数字以该报告和
> 主结果工件为准。

日期：2026-09-08  
对象：`structure-two-full-scientific-loop@0.2-development`  
结论：**两轮工程/证据审核通过；科学收益门仍关闭。**

## 审核范围

本审核只确认以下开发性质：完整七轴和七算子没有被缩小；环境真正消费动作；学习交互遵守
train/validation/evaluation 隔离；RGRC 正反例状态机可达；七个单算子中和臂完整；正向结论能回溯到
逐步 trace、算子 receipt chain（回执链）、RGRC ledger chain（账本链）和 fresh-source replay
（新鲜源码重放）。

本审核不确认真实家庭有效性、外部强基线胜利、独立托管、七算子行动贡献或论文级优越性。

## 第一轮：机制、边界与状态机攻击

| 攻击 | 预期失败关闭 | 结果 |
|---|---|---|
| 从配置删除 RGRC 或任一算子 | 完整范围校验拒绝 | PASS |
| 把 evaluation seed 塞入 train seeds | split firewall（划分防火墙）拒绝 | PASS |
| 同一环境、同一潜在结果随机数执行不同成功动作 | 下一步观测必须产生不同位置 | PASS |
| 动作分布与 selected action 不一致 | argmax 重算拒绝 | PASS |
| 伪报 post-action state | 环境确定性重放拒绝 | PASS |
| 单算子中和时删除算子接口 | 七算子 retention（保留）检查拒绝 | PASS |
| 中和一个算子时其余算子未执行 | other-operator execution（其余算子执行）检查拒绝 | PASS |
| guest/unknown/identity mismatch 进入长期 owner memory | RGRC 负例检查拒绝 | PASS |
| owner 只稳定一步就 promote | 只能 quarantine，不能 promote | PASS |
| owner/regime/location 稳定但细粒度 cause 改变 | RGRC 自有稳定签名仍能累计；不再永久阻断正例 | PASS |

第一轮发现并修复了一个机制问题：旧 RGRC 同时要求自有稳定签名和完整粒子 `run_length`，后者包含
更细的 cause 状态，导致 cause 改变时即使 owner/target/regime/location 连续稳定也会清零，主闭环
正式写入接近不可达。修复后只由 RGRC 拥有的稳定签名控制 admission（准入）；不稳定单步仍无法
promote。3 个评估种子中有 2 个在主闭环出现正式 promote，独立正例夹具走通
`quarantine → promote → retract → corrected_revision → retract`。

## 第二轮：伪造但字段完整的正路径

所有攻击都会重新计算顶层 `deterministic_replay_sha256` 和 `content_sha256`，所以测试的不是“忘记改
总哈希”，而是内部证据是否还能重算。

| 伪造对象 | 伪造方式 | 拒绝来源 | 结果 |
|---|---|---|---|
| 环境 transition | 翻转 action success 并重签顶层 | 环境按 seed/action 确定性重放 | PASS |
| 算子 receipt | 改 detail 并重签顶层 | receipt hash chain | PASS |
| RGRC record | 改 owner-target mass 并重签顶层 | ledger record/hash/state-machine 验证 | PASS |
| 单步/总指标 | 把 unknown Brier 改为 0 | 从逐步概率和真值重算 | PASS |
| 消融总结 | 把 RGRC decision effect 改为 false | 从 27 个配对动作后验重算 | PASS |
| 论文级结论 | 把 scientific superiority 改为 true | 固定 claim boundary（声明边界） | PASS |
| 七臂覆盖 | 删除 CIAV 中和运行 | 精确算子集合和 seed coverage | PASS |
| 调用方自洽回执替换 | 把 common-random-number hash 换成另一合法 64 位值并重签 | 本地自一致检查不冒充托管；fresh-source replay 拒绝 | PASS |

最后一项刻意保留了一条边界：调用方可以重签自己掌握的普通字段，所以 self-consistency（自一致）
不等于 historical authenticity（历史真实性）或 independent custody（独立托管）。验证器允许显式的
`fresh_replay=False` 本地诊断，但默认 CLI `--verify` 会执行 fresh replay 并拒绝该替换。独立托管仍须
由另一流程控制的机器、预登记信任锚和不可变原始结果提供。

## 审核中修复的问题

1. RGRC 的完整粒子 run-length 双重门造成合法稳定签名难以 promote：改为 RGRC 自有连续签名。
2. 成功动作反馈不应自动作为 contradiction（反证）撤销刚晋升记忆：反馈增加显式
   `contradictory`，只有失败/矛盾反馈触发撤回。
3. 仅保留汇总计数不足以审核：v0.2 工件现嵌入逐步环境 trace、完整算子回执链、公平回执、RGRC
   账本记录和终态。
4. fresh replay 原先直接比较 Python 对象，会因 JSON 把 tuple 载入为 list 而误拒绝未篡改工件：改为
   canonical content hash（规范化内容哈希）比较。
5. 浮点聚合在不同求和实现下可能出现约 `1e-17` 表示差：逐步值仍精确重算，汇总比较只允许
   `1e-15` 绝对容差，不放宽科学门限。

## 执行结果

```text
tests/test_structure_two_full_scientific_loop.py
tests/test_structure_two_full_scientific_loop_adversarial.py
17 passed

上述测试 + Route C v0.1 正向/对抗测试
42 passed

ruff: passed
mypy (两份 Route C 核心源码): passed
v0.1 fresh-source replay: passed
v0.2 fresh-source replay: passed
full-repository pytest/mypy/ruff/compileall/git-diff audit: all exit 0
engineering checkpoint fresh verification: passed
engineering checkpoint content sha256: 0d6c99ec9f4354f6252261fc521de44e40c2fbf5c81f8f7610f8647c48542460
```

## 最终判定

- `action_responsive_engineering_loop_verified = true`
- `learned_interaction_split_and_freeze_verified = true`
- `rgrc_positive_negative_retraction_paths_verified = true`
- `seven_operator_neutralization_matrix_verified = true`
- `all_seven_operator_action_contributions_established = false`
- `scientific_superiority_established = false`
- `independent_custody_established = false`

主结果与科学解释见
`docs/experiments/structure_two_full_scientific_loop_result_v0_2_2026-09-08.md`。
