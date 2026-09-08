# 结构二 Route C v0.2：第二次两轮对抗审核

日期：2026-09-08  
对象：`structure-two-full-scientific-loop@0.2-development`  
结论：**发现并修复 6 类证据与实验语义问题；29 项 v0.2 定向测试通过。科学收益门仍关闭。**

## 审核边界

本次不是重跑第一次审核，而是从第一次审核已经接受的正向输出继续攻击：训练/验证隔离是否只有名字
不同、动作反馈是否真的被下一步联合状态消费、RGRC 负例能否从原始账本重算、单算子中和是否可能由
“自然没变化”冒充，以及重签顶层和内部链后能否用类型混淆或合法 UUID 替换绕过验证。

本审核仍不建立 independent custody（独立托管）、真实机器人 external validity（外部有效性）、
同环境 AMG/外部强基线胜利、joint 行动收益或七算子效用贡献。

## 第一轮：科学语义与闭环因果攻击

| 攻击 | 审核发现 | 修复与失败关闭 | 结果 |
|---|---|---|---|
| train/validation 只换 seed | 旧环境的证据强度不随 seed 变化，位置 UUID 虽不同但学习样本实质同构，train/validation loss 完全相同 | 证据强度改为 seed/step 条件化；训练环境由不读取任务真值的 deterministic coverage cycle 推进；样本哈希必须不同 | FIXED/PASS |
| 伪造两个不同的训练/验证哈希 | 只检查“哈希不同”不能证明来自注册样本 | 验证器从配置和源码重建两组样本，核对哈希及 `10530/7020` 样本数 | FIXED/PASS |
| 自然不变冒充 neutralization（中和） | 旧计数把 executed 且未变状态都算成中和 | 七算子分别注册唯一 neutral detail；严格核对执行日程、`changed_state=false` 和中和语义，且禁止泄漏到其他算子 | FIXED/PASS |
| 汇总布尔值声称纠正状态被消费 | 旧工件没有逐步 pre/post-feedback 状态哈希，无法从原始 trace 重算 | 每步嵌入 pre-observation、pre-feedback、post-feedback 状态哈希及变化位；下一步必须从上一纠正后状态开始 | FIXED/PASS |
| 删除 unstable-owner 原始负例记录，再同步改计数和账本头 | 旧负例只有 operations/count/head，缺少原始 ledger rows | 每个 RGRC 负例嵌入完整账本；操作、数量、头哈希、终态与拒绝结论全部从记录重算 | FIXED/PASS |
| 训练 action policy 改成 oracle owner habit | 训练轨迹会读取评估者真值 | 配置只接受 `deterministic_coverage_cycle_without_truth`；漂移立即拒绝 | PASS |

第一轮修复后，train loss=`0.4448856219`，validation loss=`0.4546639835`；训练与验证样本哈希分别为
`70ae56ce6b9288ceb44f39855f0c673bb1b7563fa09ddb954f97eb903559e8c2` 和
`6d5cb7fa7b94af810f21e49a2678b12cc7fee74dff5764166725bfe0e6857d1e`。这只证明划分不再是同构副本，
不证明泛化。

## 第二轮：重签、自洽链与类型混淆攻击

除 NaN 攻击外，以下载荷均重新计算顶层 deterministic/content hash；涉及算子回执和 RGRC 账本的攻击
还重新计算整个内部 hash chain（哈希链）和 head（链头）。

| 伪造对象 | 伪造方式 | 拒绝来源 | 结果 |
|---|---|---|---|
| 中和回执 | 把 RGRC neutral detail 改成“碰巧没变化”，重算全部回执链 | 注册中和语义与精确执行日程 | PASS |
| 纠正状态链 | 用合法 64 位哈希替换下一步 pre-observation state，并重算 trace/top hash | 前一步 post-feedback 与下一步 pre-observation 的因果连续性 | PASS |
| RGRC 位置支持 | 换入另一个合法 UUID，重算七条账本记录及链头 | 环境注册位置支持 + 严格账本状态机 | PASS |
| RGRC 负例 | 删除 quarantine 原始记录，同时把 count/operations/head 改成空账本 | 负例结论从原始记录与状态机重算 | PASS |
| 非有限数 | validation loss 注入 NaN | 顶层递归 finite-number（有限数）检查 | PASS |
| trace 索引类型 | 用 `false` 冒充 JSON 整数 0 并重签 | strict JSON type（严格 JSON 类型）检查 | PASS |
| fairness receipt 类型 | 用 `true` 冒充 step 1 并重签 | 公平回执整数类型、顺序与预算恒等式 | PASS |
| 划分证据 | 让 train/validation hash 相同并重签 | 非同构划分约束 | PASS |
| 划分证据 | 换成两个不同但伪造的 64 位 hash 并重签 | 源码重建样本证据 | PASS |

## 修复后的数据结论

- joint 与 matched full-state factorized 的 action regret 都是 `0.555556/step`，contamination 都是
  `0.333333`；仍没有科学胜利。
- 学习交互在 `27/27` 步改变 action posterior（动作后验），mean/max TV 为
  `0.00001273/0.00026848`，但 `0/27` 改变最终动作。
- 主闭环 3/3 evaluation seeds 在两臂都出现 RGRC `promote`；RGRC 中和的 mean/max TV 为
  `0.1083219/0.1857614`，仍然 `0/27` 改变最终动作。
- 七个中和臂都有非零后验影响，但所有 `Δ action regret=0`、`Δ contamination=0`。因此只能说
  operator pathway activation（算子路径激活）成立，不能说 operator utility contribution
  （算子效用贡献）成立。

## 执行结果

```text
v0.2 original positive/adversarial tests: 17 passed
v0.2 second two-round adversarial tests: 12 passed
v0.2 targeted total: 29 passed
v0.1 + v0.2 Route-C targeted total: 54 passed
v0.2 fresh-source replay: passed
P0 adversarial tests: passed
full-repository pytest/mypy/ruff/compileall/git-diff audit: all exit 0
engineering checkpoint fresh verification: passed
engineering checkpoint content sha256: 37074fdd82a747493c5fe8cd10913db5dfcc6f72ece536eff75acb633fbfcfae
seven_operator_ablation_authorized: false
```

## 最终边界

- `action_responsive_engineering_loop_verified = true`
- `training_validation_examples_source_regenerated = true`
- `corrected_state_consumption_trace_derived = true`
- `rgrc_positive_and_negative_raw_ledgers_verified = true`
- `seven_operator_registered_neutralization_verified = true`
- `all_seven_operator_action_contributions_established = false`
- `scientific_superiority_established = false`
- `independent_custody_established = false`

主结果见 `docs/experiments/structure_two_full_scientific_loop_result_v0_2_2026-09-08.md`；第二轮专用测试见
`tests/test_structure_two_full_scientific_loop_second_adversarial.py`。
