# 结构二 P5 readout + sequential-prior post-hoc 诊断结果 v0.1（2026-09-11）

> 2026-09-11 证据版本勘误：本文保留历史实验叙述，不能据此声明当前源码通过或首次未见已证实。旧三臂 v0.1 路径是 `4103bea` 失败重放的兼容引用；真正首次失败另存。历史源码缺失、首次 D0 来源不匹配及当前 v0.2 重放边界见 [窗口一证据链修复报告](../reviews/structure_two_evidence_repair_window1_2026-09-11.md)。

协议：`structure-two-p5-readout-posthoc-diagnostic@0.1-development`
实现 checkpoint：`d0bd9c1`
状态：`POSTHOC_READOUT_DEGENERACY_REMOVED`
证据等级：test-opened-split post-hoc development diagnostic（测试集已打开的事后开发诊断）

## 1. 结论

两个接线问题修复后，direct `P5_FULL_EAGER` 的 owner-habit location posterior（主人习惯位置后验）
不再恒定均匀：1,920 个 test steps 中有 1,870 个非均匀步骤，60/60 episodes 都出现非均匀读出；
PUT_BACK 动作相对 v0.1 的均匀平局行为改变 1,285 次。v0.1 的退化读出已被排除。

P5 的 PUT_BACK error 从 0.68490 降到 0.04010，优于 learned matched two-stage 的 0.27396，也优于
independently tuned AMG 的 0.05365。不过相对 AMG 的绝对改善只有 0.01354，低于冻结门槛 0.02。
所以严格结论是：

- readout degeneracy removed（读出退化已排除）：`true`；
- P5 是本次事后 D0 PUT_BACK 点估计最优臂：`true`；
- 描述性重用 v0.1 signal rule：`false`；
- 新的预注册/确认性 P5 行动信号：**没有建立**。

SEARCH 三臂继续完全相同。A1 把当前物体位置的同一外生检测结果共享给三臂，而三臂 SEARCH 都直接
消费该 current-location posterior；本诊断没有虚构 SEARCH 差异，也没有事后聚合 SEARCH/PUT_BACK。

## 2. 两个已披露修复

### 2.1 action readout（动作读出）

v0.1 direct adapter 使用默认 `HYBRID_ALPHA`，而 P5 评估执行阻断 long-term write；因此池化长期计数
不更新。修正版显式使用此前 validation-only 选定并已冻结的 v0.6
`DUAL_TIMESCALE_REVERSIBLE`：fast `0.7`、surviving `0.2`、regime-local `0.1`。

### 2.2 PCHMP→CIAV sequential actor prior（序贯人物先验）

readout-only 单 episode preflight 仍有 0/32 个非均匀步骤。进一步追踪发现 primary PCHMP 将示例
owner mass 从 0.3333 更新到 0.7614，但 CIAV 将中性 actor likelihood 错误地乘在原始均匀 transition
prior 上，把 fast owner mass 重置为 0.3333。

生产实现现以 `primary_result.actor_posterior` 作为 CIAV actor prior，并在异位置 feedback transition
中同时用它作为新 transition prior 与 actor evidence reference prior。新增回归证明：

- 同位置 fast verification 下，中性 CIAV likelihood 保持 primary PCHMP posterior，且不产生伪变化；
- 异位置 full transition 下，CIAV posterior 等于 primary posterior 与新 likelihood 的归一化乘积；
- trace raw input 显式携带 `primary_actor_posterior`。

## 3. 完整三臂结果

数据与 v0.1 相同：20 train、20 validation、60 test episodes，test 共 1,920 steps。learned 与 AMG 的
validation-only 选择完全保持：

- learned：`base_width=8`、`learning_rate=0.1`、`l2=0.0`、
  `location_smoothing=0.25`；
- AMG：`parameter=0.2`；
- 选择回执继续为 `test_episode_ids_seen=[]`。

| arm（臂） | SEARCH error | normalized SEARCH regret | PUT_BACK error |
|---|---:|---:|---:|
| corrected direct P5 | 0.0890625 | 0.0616319 | **0.0401042** |
| learned matched two-stage | 0.0890625 | 0.0616319 | 0.2739583 |
| independently tuned AMG | 0.0890625 | 0.0616319 | 0.0536458 |

PUT_BACK 按 `comparator error - P5 error` 的 paired episode bootstrap（配对 episode 自助法）：

| comparison | absolute improvement | relative improvement | 95% CI | v0.1 rule |
|---|---:|---:|---:|---|
| learned − P5 | 0.2338542 | 85.36% | [0.2218750, 0.2453125] | true |
| AMG − P5 | 0.0135417 | 25.24% | [0.0062500, 0.0229167] | **false** |

AMG 对比的置信区间下界为正、相对改善超过 10%，但绝对改善小于注册的 0.02；而 per-task rule 要求
P5 同时击败两个 comparator 并满足全部效应量门。因此 PUT_BACK signal 仍为 false。SEARCH 两项对比
均为 0，signal 也为 false。

## 4. 退化与执行诊断

- owner-habit posterior：1,870/1,920 steps 非均匀；
- 每个 episode 非均匀步数范围：27–32；零非均匀 episode：0；
- 相对 v0.1 均匀字典序平局行为改变 PUT_BACK：1,285 steps；每 episode 范围 5–32；
- 各 episode unique distribution 数量之和：141；
- 1,243 个 detected steps 执行真实七算子 `P5_FULL_EAGER`；
- 677 个 negative steps 消费真实 CIAV→OPCEU 负证据并显式 `no_new_transition`；
- exact three-arm matched CIAV receipt：true；
- action commit 前 truth 可见：false；
- fabricated transition：0。

## 5. 可复算性

工件：`benchmarks/structure_two/structure_two_p5_readout_posthoc_diagnostic_v0_1.json`

- content SHA-256：`d96bd7ed2c47c3b3130adbabff329ab2bb1a569975a46ef4f60b499c2e2c6fc9`；
- file SHA-256：`6ad677dee1086182af261cecd292e0ed82971ab4a6d1f31a256378cc9dc20f49`；
- 独立第二次 full recomputation 与工件逐字段一致。

结果只序列化可复算的 semantic episode metrics（语义 episode 指标）。运行时生成的 revision/action/
receipt UUID 会让链哈希跨运行不同，因此没有把这些随机 ID 派生哈希伪装成 deterministic evidence
（确定性证据）；单次执行的 exact receipt matching 仍由运行时验证。

与 v0.1 一样，当前 production assembly 仍包含三份未提交的结构一依赖改动；干净 `d0bd9c1`
checkout 会因缺少 `RegimeStage` 定义而在导入阶段失败。因此本工件绑定实际运行时 source bytes，
但在结构一依赖由其所有者单独提交前，不能宣称 clean-checkout reproducibility。

## 6. 下一步与边界

下一步按已冻结顺序运行 production debt replay，确认 P0 债务升级到 P5 时消费同一 primary PCHMP
posterior、CIAV sequential prior 与 v0.6 readout。该确认只回答生产路径一致性，不能把本次 post-hoc
结果升级为预注册行动信号。

如果之后要重新判定 P5 行动信号，应先冻结这两个修复，再使用未见过的新 development holdout 或
独立托管 confirmation split。由于当前严格门仍为 false，不启动 adaptive-router validation-only
calibration；固定解析阈值继续保留为基线。

本结果不聚合 SEARCH/PUT_BACK，不通过 Task 7/8/9，不授权七算子消融、科学优越性、外部有效性或
缩小结构二完整范围。
