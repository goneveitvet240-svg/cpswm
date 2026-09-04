# 结构二 Task 7：严格窗口回春 v0.3 注册复算

日期：2026-09-05
协议：`structure-two-windowed-late-correction@0.3`
证据级别：D0 synthetic deterministic rerun（D0 合成确定性复算）
冻结配置：`configs/project_two_experiments/structure_two_task7_windowed_rejuvenation_v0_3.json`
配置 SHA-256：`a2fb032a4fc5f67d64f43a3ab946756092b9af3623b89e35ae31f93f9dd2e2dc`
结果工件：`benchmarks/structure_two/backbone_b_repairs_2026_09_04/task_7_windowed_rejuvenation_v0_3.json`

## 结论

严格 `O(window)` 工程子门通过，但注册的 belief/action equivalence（信念/行动等价）失败，因此 Task 7 总门失败：

- `strict_window_complexity_passed = true`
- `local_cost_passed = true`
- `no_fallbacks_in_registered_run = true`
- `nonself_move_passed = true`
- `belief_equivalence_passed = false`
- `action_equivalence_passed = false`
- `window_implementation_passed = false`
- `contamination_not_expanded = false`
- `task_7_passed = false`
- `seven_operator_efficacy_authorized = false`

这不是把工程实现失败和科学等价失败混为一谈：持久化窗口机制已满足复杂度合同；失败来自其输出没有落入预注册的多轴与行动等价界限。

## 冻结设计

- `G=12`，修订位置 `2`，`W=3`，两次 rejuvenation sweeps（回春扫描）。
- `384` particles（粒子）。
- 5 个 scenario seeds × 3 个 replicate seeds，共 15 个 paired units（配对单元）。
- 每次实际 proposal（提案）必须是 non-self move（非自身移动）；自提案从条件分布中剔除，正反 Hastings density（黑斯廷斯密度）均重新归一化。
- 信念等价逐一覆盖 `mechanism/giver/receiver/instance/cause/regime_move/regime_target/regime_state/run_length` 九个轴，每轴 TV 上界均为 `0.1`。
- 行动等价要求 terminal embodied action distribution（末端具身行动分布）TV 不超过 `0.1`，并且 Bayes action（贝叶斯行动）完全一致。

## 严格窗口复杂度证据

校正前的基线链、边界和 checkpoint（检查点）允许随历史长度增长；校正到达后的新增工作与新增可达存储不得随 untouched suffix（未触碰后缀）增长。

实现采用：

- constant-depth persistent window overlays（常深度持久化窗口覆盖层），不再用 tuple 拼接整条 gaps/timeline/runs/boundaries；
- analytic blocks（解析统计块）的 bounded copy-on-write（有界写时复制），只克隆窗口影响的 cell；
- 校正后 resampling（重采样）共享不可变基线历史；
- 校正前预计算的 position-bound XOR digest（位置绑定异或摘要），接受后只重哈希窗口位置；
- unresolved target（未解析目标）用单观测差分更新；
- terminal action（末端行动）由缓存充分状态读取，不重扫历史。

长后缀探针结果：

| suffix 长度 | 校正前 checkpoint bytes | window target work | persistent nodes | window items written | reachable overlay bytes | suffix read/copy/rehash |
|---:|---:|---:|---:|---:|---:|---:|
| 8 | 1,272 | 36 | 19 | 58 | 314 | 0 / 0 / 0 |
| 64 | 4,520 | 36 | 19 | 58 | 314 | 0 / 0 / 0 |
| 256 | 15,817 | 36 | 19 | 58 | 314 | 0 / 0 / 0 |

另有 poisoned-suffix attack（毒化后缀攻击）：测试序列一旦读取窗口外元素即抛错，`W=3` 热路径仍可完成。该测试覆盖了逻辑计数可能撒谎的情形。

## 注册科学结果

local rejuvenation（局部回春）相对 full rerun（全量重跑）的多轴距离如下：

| 轴 | mean TV | max TV | 预注册上界 |
|---|---:|---:|---:|
| mechanism | 0.137723 | 0.544494 | 0.1 |
| giver | 0.030259 | 0.404349 | 0.1 |
| receiver | 0.005209 | 0.018230 | 0.1 |
| instance | 0.292682 | 0.829293 | 0.1 |
| cause | 0.199287 | 0.537757 | 0.1 |
| regime_move | 0.357223 | 0.919299 | 0.1 |
| regime_target | 0.396499 | 0.975308 | 0.1 |
| regime_state | 0.317373 | 0.758681 | 0.1 |
| run_length | 0.373475 | 0.751143 | 0.1 |

行动分布 mean TV 为 `0.308012`、max TV 为 `0.640442`，Bayes action 匹配率为 `0.8`，未达到冻结标准。污染差为 `+0.00520833`，也未达到 non-expansion（不扩张）要求；窗口范围 recovery rate（恢复率）比全量重跑高 `+0.20`，但该量按冻结协议只报告、不覆盖前述失败。

## 工件与边界

- Artifact content SHA-256：`0c5531896bdade5765007f05e793b70a70ace02113604f440d17d52df01156e3`
- Artifact file SHA-256：`dd842e6c107c20b9834af7845510c30fec22db21b7351907e5deb69ddf97daf2`
- Deterministic result SHA-256：`05c79eafb7a91ec2652973793f5550368448a1efc7df6751d155ac880a7b5e9d`
- Task-specific source bundle SHA-256：`9bb17b2620fffe862fa06c172167dc8c6d6938b23772297472242263e5a9d87e`

工件还逐路径登记了全部 `66` 个正向布尔输出；每条均绑定 artifact content、任务专用
source bundle、冻结配置、由原始指标重算的语义门和 fresh task-specific recomputation。

runner 已做第二次独立进程内 fresh recomputation（新鲜复算）并逐字段比较。它仍不是 independent-custody formal receipt（独立托管正式回执），不选择 Task 12 kernel（Task 12 内核），也不授权七算子消融。
