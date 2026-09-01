# 任务非平凡性门与实验臂可区分性门：首轮结果

日期：2026-08-30
协议：`task-nontriviality-and-arm-distinguishability-gates@0.1`
artifact：`artifacts/project_two_v04_development/task_nontriviality_gates_v0_1.json`
content SHA-256：`b46386b6234c329321f522d82d57996a6bb325c0c5c5834337c646e89b3e4bba`
证据等级：**method-free instrument diagnostic（方法无关的仪器诊断）；不是方法结果，也不是确认性证据**

两道门都不运行、不调参、不评分任何研究方法。Gate B 会重放已冻结的结构二实验臂，但只记录它们
预测了什么，不计算任何 endpoint、成本模型或比较。因此这两道门在结构上无法被朝任一方向操纵。

结构二部分只使用 validation seeds（`310101–310108`）；**没有打开任何 sealed holdout**。

## 1. 结论

| 目标 | 门 | 结果 |
|---|---|---|
| `project_two.true_owner_habit_location`（放回靶） | Gate A | **失败**（A1/A2/A3） |
| `project_two.true_location`（搜索靶） | Gate A | **失败**（A1/A3） |
| 结构二 strongest-neighbor 实验臂集合 | Gate B | **失败**（3 臂预测逐位相同） |
| `project_one.shift_cause_set`（结构一漂移原因靶） | Gate A | **通过** |
| 结构三 oracle 情境套件 | Gate A | **不适用**；签名报告通过 |

一句话：**结构二的两个行动靶都不具备可被方法改进的结构，而结构一的漂移原因靶具备。**

## 2. 门的定义与阈值

Gate A 的四条状态跟踪判据与一条分类判据：

| 判据 | 含义 | 本轮阈值 |
|---|---|---|
| A1 `trivial_ceiling_leaves_headroom` | 最好的可见平凡规则仍须留下足够误差 | `≥ 0.10` |
| A2 `update_law_is_not_trivial` | 在规则可执行的步上，两行更新律不得几乎完全复现靶 | `≤ 0.98` |
| A3 `target_carries_context_structure` | 按上下文分桶必须优于无上下文规则 | `≥ 0.01` |
| A4 `task_is_more_than_trigger_inference` | 剩余误差不得几乎全部来自触发器推断 | `≤ 0.90` |
| A5 `target_is_not_a_single_feature_lookup` | 单一可见特征的在线查表不得逼近零误差 | `≥ 0.10` |

状态跟踪靶绑定 A1–A4，分类靶绑定 A1 与 A5；两类靶都完整报告全部统计量。

**阈值是作者选定的，没有外部依据，必须在每个正式协议中重新论证。** 它们只编码两个直觉：
"方法要有可去之处"和"靶不能是一行规则"。本文所有判定都同时给出原始数值，读者可用自己的
阈值重读。

平凡规则集合（全部无学习参数）：`constant_first_candidate`、`global_mode_observed`、
`last_observed_value`、`sticky_visible_trigger_law`、`per_context_mode_observed`。另有三条
标注为 evaluator-side 的探针：`sticky_true_trigger_law`（同一更新律但给定真实触发器）、
`persist_previous_target`（自相关探针）、`single_visible_feature_lookup`（单特征在线查表）。

## 3. 结构二：放回靶

| 规则 | 误差 |
|---|---:|
| `constant_first_candidate` | 1.000000 |
| `global_mode_observed` | 0.354167 |
| `per_context_mode_observed` | 0.331597 |
| `last_observed_value` | 0.165799 |
| **`sticky_visible_trigger_law`** | **0.042535** |
| `sticky_true_trigger_law`（真值触发器） | 0.042535 |
| `persist_previous_target`（真值历史） | 0.125000 |
| `single_visible_feature_lookup`（真值历史） | 0.244792 |

更新律复现率（分三桶）：

| 桶 | n | 复现率 |
|---|---:|---:|
| 触发且被观测（`on_trigger_observed`） | 732 | **1.000000** |
| 触发但未被观测 | 220 | 0.918182 |
| 未触发（应保持） | 192 | 0.958333 |
| **规则可执行的全部步（`observed_step_rate`）** | **924** | **0.991342** |

判定：A1 失败（0.042535 < 0.10）、A2 失败（0.991342 > 0.98）、A3 失败
（上下文增益 **−0.289062**，按星期分桶反而更差）、A4 通过。

### 三个交叉验证与一处重要更正

1. `sticky_visible_trigger_law` 的误差 **0.042535**，与 corrected AMG 在同一批 validation seeds 上
   的 put-back 误差 **完全相等**。也就是说，corrected AMG 在这个靶上恰好等于一条四行的平凡规则，
   不多也不少。
2. `last_observed_value` 的误差 **0.095486** = `1 − 0.904514`，与恢复 search pin 后所有方法
   逐族相同的搜索成功率完全一致。两个门内数值独立复现了 8-29/8-30 两轮诊断的结论。
3. **`sticky_true_trigger_law` 与 `sticky_visible_trigger_law` 误差完全相等，
   `trigger_inference_share = 0.000000`。**

第 3 点更正了此前的解释。此前（包括 8-29 讨论与 8-28 接口审计的常见读法）认为"这个任务被还原成
判断这次动作的人是不是主人"。**这是错的。** 可见 actor posterior 的 argmax 在每一个可执行步上都
与真实 actor 一致，给定真值触发器带来的改进精确为零。这与 8-29 upper-bound 诊断中
`true_actor_oracle` 没有收益（`+0.013021`）互相印证，并给出了当时未能给出的机制解释。

因此该靶的剩余 `0.042535` 误差既不是世界建模难度，也不是人物归因难度，而是
**观察缺失下的不可达误差**：主人在未被观测的日子移动物体时，任何仅依赖可见证据的规则都无法跟随。
`on_trigger_unobserved` 桶的 0.918182 正是这部分。

## 4. 结构二：搜索靶

| 规则 | 误差 |
|---|---:|
| **`last_observed_value`** | **0.095486** |
| `sticky_visible_trigger_law` | 0.095486 |
| `per_context_mode_observed` | 0.316840 |
| `global_mode_observed` | 0.453993 |

该靶没有潜在触发器：更新条件就是"这一步是否存在检测"，完全可见，所以两条 sticky 规则
与 `last_observed_value` 恒等。

复现率：`on_trigger_observed = 1.000000`（n=838），`off_trigger = 0.774510`（n=306），
`observed_step_rate = 0.939685`。

判定：A1 失败（0.095486 < 0.10）、A3 失败（上下文增益 −0.221354）、A2 与 A4 通过。

A2 通过是有意义的：未观测步上真实位置有 22.5% 会改变，这是真实的、平凡规则够不到的动态。
但它同时是不可见的，只有带习惯先验的模型才可能部分利用；8-29 upper-bound 中 top-2 oracle 的
搜索误差 `0.0625` 相对 pin 的 `0.095486` 就是这部分可达空间的上界，约 `0.033/步`。

## 5. Gate B：实验臂可区分性

对每个臂在 6 族 × 8 seeds 共 48 个 validation episodes 上的完整有序预测序列
（`put_back>search_head`）取内容哈希。

- 申报臂数：10（不含 oracle）
- 可区分臂数：**8**
- 判定：**失败**

逐位相同的一组：

```text
active_dreaming_matched, brainctl_matched, care_no_action_regret
```

这三个臂在全部 48 个 episode 的每一步都输出了完全相同的动作。含义有三层：

1. "validation 选出 brainctl 为最强已发表邻近方法"实际含义是"brainctl 是这一组同一策略中
   收费最低的包装"，不是方法层面的最强对照；
2. sealed holdout 上的 `CARE − CARE-without-action-regret = +0.525651` 是 CARE 与一个
   **改名后的 brainctl** 的比较，其差值只能来自成本记账，**该消融从未检验过 action-regret 机制**；
3. `auto_dreamer_matched` 与 `trustmem_matched` 在完整预测序列上是可区分的。这修正了
   8-29 讨论中"六族里五族逐位相同"的说法——该说法基于汇总指标，过强；Gate B 给出的
   精确答案是 10 臂中 3 臂碰撞。

本结果基于 validation seeds。sealed holdout 上的碰撞结构可能不同，但由于三臂的决策规则在
可见状态上恒等，预期一致。

## 6. 结构一：漂移原因靶

生成 40 个 seeds × 6 族 = **240 个 case**，六类标签严格均衡。

| 规则 | 误差 |
|---|---:|
| `constant_first_candidate`（多数类天花板） | 0.833333 |
| `single_visible_feature_lookup` | 0.833333 |
| `per_context_mode_observed` | 1.000000 |

判定：**通过**（A1、A5 均通过）。

单特征在线查表使用的可见摘要是刻意粗糙的三比特：前后半段检测率变化、模态观测位置是否改变、
主导 actor 是否改变——正是审稿人会最先尝试的平凡检测器。它相对多数类**没有任何增益**，
各主要分桶的标签纯度只有 0.31–0.56。

这是本轮唯一的好消息：**结构一的靶在结构上是健康的**，平凡规则吃不掉它，同时分桶纯度显示
存在真实可学结构。

限制：这是**一个**特征集合，不是穷举搜索。低误差可以证明平凡，高误差不能证明非平凡。

## 7. 结构三：Gate A 不适用

结构三 oracle 套件是 17 个确定性情境 + 3 个组合 probe 的**手工编写一致性套件**，不是抽样
基准。在其上计算平凡规则误差率没有抽样解释，因此本轮**不给出 Gate A 判定**，而报告一致性
套件的对应量：

- 情境数：20
- 不同决策签名数：**20**（无碰撞）
- 决定性维度覆盖：`identity / location / person / event / habit` 各 **3**

签名由 `decisive_dimension`、附加决定性维度、初始信念、验证动作、终止动作、终止结果、
unknown 标志、`not_found` 重规划与期望终止条件共同构成。签名门通过。

尚未检验的是**必要性**：套件证明了每个情境提出不同要求，没有证明每个情境的正确答案确实
依赖其声明的决定性维度。对应的下一道门应当消融声明维度并要求正确答案随之改变。

## 8. 这些结果不支持的主张

- 不支持"结构二方法优于或劣于任何基线"——两道门不计算任何方法比较；
- 不支持推翻或挽救任何已归档的 sealed holdout 结论；
- 不支持"结构一方法有效"——Gate A 只说明该靶留有空间；
- 不支持"结构三套件充分"——只说明它无重复情境；
- 不支持任何关于真实感知、家庭数据或机器人执行的外推。

## 9. 复现

```bash
python apps/evaluation_runner/run_task_nontriviality_gates.py --stage gate-a
python apps/evaluation_runner/run_task_nontriviality_gates.py --stage arm-traces
python apps/evaluation_runner/run_task_nontriviality_gates.py --stage finalize
```

`arm-traces` 阶段按臂写独立缓存文件，可分批运行后再 finalize。连续两次 finalize 复现同一
content SHA-256 `b46386b6234c329321f522d82d57996a6bb325c0c5c5834337c646e89b3e4bba`。

- 实现：`src/cpswm/system/evaluation_operations/task_nontriviality_gates.py`
- 适配器：`src/cpswm/system/evaluation_operations/task_nontriviality_adapters.py`
- 运行器：`apps/evaluation_runner/run_task_nontriviality_gates.py`
- 测试：`tests/test_task_nontriviality_gates.py`（11 项通过）
