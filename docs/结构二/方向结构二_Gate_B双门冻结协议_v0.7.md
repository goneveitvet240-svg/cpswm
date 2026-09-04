# 结构二 Gate B 双门冻结协议 v0.7

协议号：`structure-two-stratified-mechanism-dual-readout-gate-b@0.7`
冻结日期：2026-09-04
状态：**`INVALIDATED_SUPERSEDED_FOR_FUTURE`（已失效，仅供历史取证）**
失效日期：2026-09-05
未来替代协议：`structure-two-comparator-typed-dual-gate-b@0.8`

> P0 失效声明：v0.7 把所有对照都强制为“belief 差异 AND action 差异”，无法正确
> 表达 action-regret 与 full-rerun 所需的等价关系。无论 v0.7 trace、签名或本地
> 诊断多完整，都不得产生 Gate B 正式通过或任何七算子授权。

机器可读配置：
`configs/project_two_experiments/structure_two_gate_b_v0_7.json`。

实现：
`src/cpswm/system/evaluation_operations/structure_two_dual_gate_b_v0_7.py`。

## 1. 历史冻结裁决（已失效）

Gate B 冻结为 **dual gate（双门）**，正式逻辑为：

\[
GateB = B_{belief}\land B_{action}\land B_{mechanism}.
\]

这里的“双门”指 belief readout（信念读出）与 action readout（行动读出）必须同时通过；
mechanism activation（机制激活）是第三个不可省略的必要条件。它不表示 Gate A 与 Gate B 的
组合，也不表示 belief/action 二选一。

- belief 差异不能替代 action 差异；
- action 差异不能替代 belief 的因果链；
- 只打印机制事件不能替代任何读出差异；
- 三项中的任一项失败，Gate B 均失败。

选择双门的原因是：v0.5/v0.6 的 top-1 action token 会丢失已存在的数值信念差异；反过来，
仅看信念又允许一个对任何具身决策都没有影响的机制开门。双门把“内部机制确实改变共同信念”
与“这种改变确实到达行动端”分开检验，再用 AND 合并。

## 2. 与历史协议的关系

v0.7 只取代**未来运行**的
`structure-two-stratified-mechanism-action-gate-b@0.6` 草案，不改写下列历史事实：

- `structure-two-world-arm-distinguishability-gate-b@0.5` 已运行且失败；
- v0.6 是 `DEVELOPMENT_NOT_FROZEN` 草案，没有正式结果；
- 过去 action-only token、签名 trace 和诊断产物不能转登记为 v0.7 belief trace；
- external fidelity gate（外部忠实度门）仍独立存在，Gate B 本身不证明外部方法复现忠实或
  效果优越。

## 3. 规范读出

### 3.1 完整 belief distribution（信念分布）

每一步必须按
`structure-two-common-joint-belief-readout@0.7` 输出**同一个冻结公共本体**上的完整数值分布。
本体不是由 trace 调用者命名，也不能随步骤变化。v0.7 将 resolved 状态冻结为以下七轴的笛卡尔积：

- `location`：`location_0` 至 `location_5`；
- `instance_identity`：target / decoy / unknown instance；
- `object_state`：stationary / in-use / carried / stored；
- `responsible_actor`：owner / family / guest / robot / unknown；
- `event_class`：direct observation、pickup-carry-place、pickup-carry-handoff-place、other hidden event；
- `regime_state`：stay / create / reactivate；
- `change_cause`：observation / actor / identity / habit / noise。

七轴共产生 21,600 个 resolved 标签，再加一个全局 `unresolved` 标签，故完整 support 固定为
21,601 项。其 manifest SHA-256 冻结为
`ea40b7f59c20d1d3229a02ed27d5d446ecb40993a34ea2cb951c19879e139265`；摘要同时绑定 schema、
轴定义和逐项 support。两条臂即使共同使用完全相同的任意标签，也不能冒充这个本体。

“完整”具有可执行含义：

1. support 必须逐项等于上述 21,601 项冻结清单，并按词法规范顺序排列；
2. 每个 support 标签都有显式概率，零质量标签也不能删除；
3. 概率必须有限、非负，并已在 `1e-9` 绝对误差内归一化；
4. scorer 不补缺失项、不替调用者归一化；
5. 同一比较步的两条臂必须使用逐项相同的 support。

belief 子门对每个预注册臂对计算逐步 total variation（TV，总变差距离）。同时要求：

- 每步实质差异阈值：`TV >= 0.01`；
- 全部对齐步骤平均：`mean TV >= 0.01`；
- 至少 `5%` 的步骤达到每步实质阈值。

### 3.2 完整 action policy（行动策略分布）

每一步必须按
`structure-two-common-action-policy-readout@0.7` 输出完整行动概率分布，并另外登记规范
`selected_action`。验证、询问或保持未决可以是行动，但必须在读取其结果之前登记。

行动本体也冻结而非由调用者自报，共 39 项：6 个位置乘 5 个责任人物形成 30 个
`put_back` 行动，6 个 `search` 行动，以及 `verify:physical`、`ask:user`、
`hold:unresolved`。其 manifest SHA-256 为
`ac47bc0707b938c239b111c3b934eeb62fe9a11d9425f6b4d95ce6370e05a43d`，输入分布必须逐项覆盖
该清单。

`selected_action` 不是一次随机 rollout 抽样。Gate B v0.7 冻结唯一 readout policy
（读出策略）为 **deterministic argmax with lexical tie-break（确定性最大概率、词法序破同分）**：
选取最大概率行动；若并列，选词法序最小者。随机抽样、调用者自选 RNG、不同 seed 或未登记
tie-break 均直接拒绝。这样，selected-action disagreement（选中行动分歧）只能来自行动分布本身，
不能来自两个随机样本。若未来要评估随机执行策略，其执行效用必须另建匹配 seed/common-random-number
实验，不能拿随机选择差异满足本门。

action 子门同时要求：

- 每步行动分布 `TV >= 0.01` 才算实质差异；
- 全部对齐步骤 `mean action TV >= 0.01`；
- 至少 `1%` 的步骤达到行动 TV 阈值；
- 至少 `1%` 的步骤同时满足行动 `TV >= 0.01` 且规范 `selected_action` 不同。

因此，增加小数位产生的微小分布噪声不能开门，也不能从另一个只有尾部 TV 差异的步骤“借用”
materiality（实质性）；只改变分布尾部而从未改变行动选择也不能开 action 门。Gate B 只检查
可区分性和作用链，不判断哪条臂更优；效用优越性必须由后续匹配实验独立检验。

### 3.3 Mechanism receipt（机制回执）

沿用完整十臂及 v0.6 的机制事件集合，但每次命中必须绑定：

- 预注册 event；
- 预注册 component ID；
- 输入状态 SHA-256；
- 与输入不同的输出状态 SHA-256。

每个事件至少覆盖 `0.1%` 的步骤和 `5%` 的 episode。wrapper 名称、日志字符串或无状态变化
的自报事件不能计为机制激活。

## 4. 对齐与真值防火墙

任何数值评分之前，所有十臂必须逐项满足：

1. episode ID 与 step ID 数量、内容、顺序完全一致；
2. `visible_input`、`visible_history` 与 observation policy 的内容摘要一致；
3. compute、active observation、physical verification、action cost、privacy cost 的预算上限一致；
4. belief/action 的 schema、冻结本体 manifest 和完整 support 逐项一致；
5. 读出阶段严格为 `pre_action_pre_evaluator_truth`；
6. `evaluator_truth_accessed=false`。

任一不一致直接拒绝整个评分，而不是把该步删除后继续。物理验证动作本身可以在 pre-truth
时刻参与 action 比较；读取验证结果后的预测不能回填到此前的比较位置。这样可以阻止 v0.5 中
“一条臂先读真值，再用 post-truth 输出制造分歧”的路径。

## 5. Metadata 与浮点攻击模型

scorer 只对结构化数值分布、实际行动、信息集、预算、时序和机制回执计算 semantic hash
（语义摘要）。文件名、显示名、生成时间、注释等 caller metadata（调用者元数据）被明确排除。

所以：

- 两个文件 SHA 不同不等于行为不同；
- 改名、增加注释或改变 JSON 排版不能满足 belief/action 子门；
- 两臂共同改用任意同名 support 不能满足本体约束；
- 两臂从同一或不同随机策略各抽一次行动不能制造可计分的 selected-action 分歧；
- `1e-6` 是独立数值噪声下限，所有 TV 门槛必须严格高于它；
- 非有限数、负概率、未归一化概率和稀疏删项全部失败关闭。

## 6. 冻结比较集合

保留十臂，只比较 `care_wm` 与九条预注册 same-question（同科学问题）对照：

1. corrected AMG；
2. O-Star matched；
3. sequential no-consolidation；
4. ActiveDreaming matched；
5. AutoDreamer matched；
6. TrustMem matched；
7. Brain-Controller matched；
8. care without action regret；
9. full rerun。

比较 ID、domain、右臂、双读出阈值以及每臂 event/component 精确集合均由机器可读配置冻结；
loader 对配置做完整对象相等校验，不能由运行者临时删臂、换关系或降低阈值。

## 7. 当前状态与授权边界

当前 v0.7 已失效；即使以后出现新的 v0.7 canonical trace set（规范轨迹集）或
独立 custodian attestation（保管者认证），也不得重新开启该版本。因此：

- `new_trace_set_present=false`；
- `formal_gate_b_passed=false`；
- `seven_operator_ablation_authorized=false`。

实现中的 scorer 只返回各子门的 historical diagnostic result（历史诊断结果）。即使单元测试构造的合成 trace
同时满足 belief、action 和 mechanism，正式 `gate_b_passed` 仍被硬置为 `false`。未来正式运行
必须另建受信执行和签名验证路径；调用者不能把本地 diagnostic boolean 转写为正式通过。

旧 `structure_two_external_confirmation_gate_v0_9.py` 只验证 v0.6 action-only（仅行动）草案。
v0.7 冻结后，该路径保留用于历史取证，但其 chain verification（链验证）和 combined
authorization verification（组合授权验证）均固定返回
`gate_b_v0_7_receipt_required` 的失败关闭回执。即使旧 v0.6 链全部签名有效，也不能再产生当前
`gate_b_passed=true` 或通用外部比较授权。

所以 v0.7 现在只保留**历史语义与诊断重放**。未来 Gate B 只能按 v0.8 的
comparator-typed（比较器类型化）关系和逐 episode 公共本体运行；未完成正式运行与攻击前，
可信七算子系统消融持续被阻塞。
