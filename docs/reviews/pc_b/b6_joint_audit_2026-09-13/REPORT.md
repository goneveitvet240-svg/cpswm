# B6 联合消费者与条件解析块独立审核

## 结论

冻结交付的局部算术和 prepared 接缝在本环境复核通过，但 **不能签署默认生产闭环**。
六个交付测试模块经明确标注的直接兼容运行器展开为 85 个用例，结果 85/85；25 组独立随机
数学对照也全部一致。对抗审核同时确认四项问题，其中冷启动公共操作失败是实际可用性缺陷，
另外两项表明当前值对象/规划器不能承担生产来源授权。

本审核没有修改 A 的三个生产文件，也没有修改 `STATUS_A`、`STATUS_B` 或共享集成分支。

## 冻结对象和环境

- 分支登记：`codex/pc-a-native-joint-consumers-20260912`。
- 交付提交：`2a7a547fba30412d9349605aff3a7df7c60d6b3a`；GitHub 显示该提交只改
  `docs/collaboration/STATUS_A.md`。
- 实际代码提交：`1d24099a025c9d7c00a59e4c78c593703924b0eb`，提交信息
  `feat(structure-two): add joint CIAV consumer and conditional block components`。
- A 报告登记的生产基线：`62870a3a38fce882b25d8d77f1d0526cca6fbc14`。A 原始运行清单中的
  `base_sha` 是提交前工作树 HEAD `69c4b8b9379bff618f288070d1a12770ed44bc00`，但三个被测源的
  SHA-256 与本次冻结提交逐字节一致。
- 本地冻结：递归远端树 313 个 `src/` 文件全部物化，313/313 Git blob SHA-1 匹配，0 漂移。
- 平台：Linux x86_64，kernel 6.18.35；Python 3.12.14；NumPy 2.3.5；Pydantic 2.13.5；
  `PYTHONHASHSEED=0`，`PYTHONDONTWRITEBYTECODE=1`。
- A 原始交付环境是 macOS/Python 3.13.5；因此本次是不同平台和解释器的独立执行，但不是
  Windows 复现。
- 三个交付源 SHA-256：
  - `structure_two_conditional_updates.py`：
    `e9f878a51141db95df240b0b79f27b19eab1d13fad4c3992a16cfd388b6291b9`
  - `structure_two_joint_consumption.py`：
    `ad603f17ed9c94f95fc8a4be126ea843c41174b34a3db4f4277a8038f6b18dbc`
  - `active_verification.py`：
    `76b2cd8fe54393c6a306411aa4fa423b0b34669712ed7802383e9a71d7478ba8`

终端 `git fetch origin --prune` 无法在 scratch 执行，因为这里不是 Git 工作树；GitHub 连接器
只读核验了上述两个提交和完整树。此报告不声称终端 fetch 成功。

## 执行结果

| 检查 | 命令结果 | 解释 |
|---|---:|---|
| A 原始 pytest 命令 | exit 1，未收集 | 当前解释器没有 pytest；原始输出已保留 |
| 冻结用例直接执行 | 85/85 passed，137.760 s，exit 0 | 等价展开当前六个模块的参数和模块 fixture；不是 pytest |
| 解析块独立数学对照 | 25/25 随机组匹配 | 独立计算 Dirichlet、RLS、Lambda/xi，不从系统输出反推答案 |
| 非法数值/维度矩阵 | 6/6 rejected | 覆盖奇异、非对称、错维、NaN、Inf、重复簇 |
| 独立对抗运行 | 0 runner error，4 findings，exit 1 | JUnit 将确认问题保留为失败，避免绿色误报 |

完整命令见 `COMMANDS.md`；直接执行原始 JSON/JUnit 在 `run_direct_01/`，最终对抗原始
JSON/JUnit 在 `run_adversarial_03/`。

## 数学与语义复核

### 三个解析块

随机对照直接使用定义式：

- Dirichlet：`alpha' = alpha + location_mass`；
- RLS：`A' = A + w x x^T`，`b' = b + w x y`；
- information：`Lambda' = Lambda + w H^T R^-1 H`，
  `xi' = xi + w H^T R^-1 z`。

25 个随机种子、3 维状态、2 维相关观测和 4 个位置全部在 `1e-12` 容差内匹配。两次累计、
从保留输入撤回、修正一个观测以及回到父贡献均恢复五个块和证据簇序列。实现的数值计算本身
未发现公式错误。

需要维持已声明的边界：`ConditionalAnalyticState` 只保留数值块和 cluster ID。使用相同
cluster ID、相同数值贡献但不同 `source_record_ids`/`observation_model_id` 会得到相同 reference。
这是本提交声明的“纯计算、非长期授权”限制；后续生产账本必须另行绑定完整测量来源，不能把
这个 reference 当作来源证明。

### 完整联合消费和 CIAV

独立构造了两组合法分布，角色、实例及原因边缘完全相同，仅角色—实例相关性不同：

| 分布 | 手算 EVSI | 实现 EVSI | 原因 IG | 完整联合 IG | 净值 | 动作 |
|---|---:|---:|---:|---:|---:|---|
| 相关 | 0.4 | 0.4 | 0.0 | 0.8 bit | 0.3 | 执行 |
| 独立 | 0.0 | 0.0 | 0.0 | 0.8 bit | -0.1 | 不执行 |

这证明任务效用确实在完整联合原子上求期望，而没有退化成边缘乘积。它也明确说明 CIAV 的
`expected_cause_information_gain` 是原因边缘信息增益，不是完整联合信息增益；完整联合 IG
相同并不意味着任务 EVSI 相同。

真实 prepared 视图保留了 `0.19522184894644604` 未决质量；纯未决质量输入合法且选择不动作，
空 posterior 被拒绝。

## 确认问题

### B6-F4 — 高：模块冷导入测试漏掉首次公共操作

冻结测试只执行 `import cpswm.system.structure_two_conditional_updates` 和 joint 模块，因此通过。
在新解释器中进一步执行任何依赖 workspace 的公共操作则失败：

- 导入 `ConditionalAnalyticState` 失败；
- 首次调用 `rebuild_conditional_state` 在延迟导入处失败；
- 首次读取 `JointDecisionView.content_sha256` 同样失败。

链路是 `structure_two_particle_workspace.py:26` → `evaluation_operations/__init__.py:262` →
`project_two_action_benchmark.py:94` → `prototype_spine.py:121` → 尚未初始化完成的 workspace。
因此特殊测试导入顺序掩盖了公共 API 的冷启动不可用。建议 A 将公共契约/选定方法类型移到不
执行宽包初始化的中性模块，或消除 `evaluation_operations.__init__` 的 eager benchmark 导出；
新增子进程测试必须调用公共函数/属性，而不只 import 模块。

### B6-F1 — 若升格生产授权则为高：view 接受外来 runtime 和未验证 source hash

`JointDecisionView.from_batch` 在 `structure_two_joint_consumption.py:55-121` 接受 caller 提供的
`runtime_id`，且只是复制 `record.source_frame_sha256`。合法 prepared batch 的控制组通过；将
runtime 换成新 UUID、或把一个正质量 record 的 source-frame hash 改成 64 个零，构造仍成功。
缺失粒子则正确拒绝，说明攻击确实改变的是来源绑定而不是 no-op。

该类文档明确称自己是 value object、不是 authorization receipt，所以这是已声明信任边界，
不是把局部组件算术判错。然而默认生产方若直接使用它，会把“caller 自称的 runtime/hash”
误当来源身份。建议由 runtime owner 提供构造入口，在构造前验证当前 workspace、record 原始
source frame、运行身份、batch cluster 和完整谱系；不要从 caller 接收 runtime ID。

### B6-F2 — 中：belief digest 对 planner 是未消费字段

`JointParticleVerificationBelief.source_snapshot_sha256` 声明 tables 应绑定该 snapshot
（`active_verification.py:402-412`），但 `select` 从 `:468` 开始没有读取该字段。仅更换 digest，
同一 action 和 utility tables 得到完全相同计划。`JointDecisionView.expected_utilities` 的
`source_belief_sha256` 也只是 caller 传入字符串；action 本身没有对应 digest 字段。

建议把 action likelihood 与两个 utility table 包装为携带来源 digest 的不可变对象，并在
planner 入口与 belief digest 强制比较。仅要求相同 atom key 集不能识别同一粒子集合上的陈旧
测量模型或 utility 表。

### B6-F3 — 低：空动作被误报为隐私封锁

`active_verification.py:536-546` 将 `not eligible` 一律返回
`privacy_hard_constraint_blocked_all_actions`。当原 action tuple 本来就是空的时，blocked IDs 也
为空，但仍得到该原因。选择结果“不动作”正确，审计/停止原因错误。建议先区分
`not actions` 与 `actions and not eligible`。

## prepared 接缝与默认能力

prepared 接缝的真实 posterior → batch → view → CIAV 只读消费已执行并通过，包括缺粒子、陈旧
snapshot、可变容器、重复动作和来源投影攻击的冻结用例。但静态扫描所有 `src/**/*.py` 后，
除组件自身外没有任何 `JointDecisionView` 或 `rebuild_conditional_state` 生产引用。

因此结论必须分开：

- 工程回归：A 原交付报告 85 passed；B 直接兼容运行 85/85。
- 独立数学审核：解析公式、累计/撤销/纠正及联合相关性消费通过。
- 独立对抗审核：确认 B6-F1 至 B6-F4；不能无条件签收。
- 默认能力：新组件仍未接入 core 默认调度或同一连续历史。
- 统一验收/科学收益：未运行，也不能由本组件测试推导。

下一接收方是电脑 A：先修复 B6-F4；在接入默认生产路径前解决 F1/F2，并补 F3 的停止原因回归。
新提交需给出唯一冻结 SHA 后再交 B 独立复核。
