# 受控缺失与迟到反证：真实 P5 机制诊断

本轨道是 **CONTROLLED_ORACLE_NOT_NATURAL**。`tools/run_controlled_semantic_mechanism.py` 复用明确位于 tests 的 `BackboneWiringProbe` 家庭情景，注入场景语义及假定似然；空白 RGB 只是 raw delivery 的占位字节，不经过视觉识别。不读取 HO-Cap 作者标注，不建立自然角色能力、经验校准、实物操作、全轴神经提议生产或科学收益结论。

实际调用同一 `GroundedTransition → ContinuousEvidenceInput(execution_lane="registered_p5_first") → StructureTwoProductionSystem.process_p5_first_transition`，不直接填后验，不调用 legacy lane，也不使用 evaluation-only direct P5。观测机会、似然、效用及反馈解释策略仍是受控设定。其证据级别是完整注册算子路径的 D0 机制检验。

## 输入与应答

两个场景使用同一种子 7、前 12 个情景日：

- `oracle_complete`：完整 oracle 证据，共 12 次 P5。
- `missing_and_ambiguous`：第 2、5 个零起算输入，producer 返回 None，表示**缺少合格语义**；不制造 NOT_OBSERVED 负观测。第 3、6 个输入移除 actor/mechanism/role 证据，保留位置/机会/原始先验，不人为硬设后验；共 10 次 P5。

每次真正执行包含七个 selected_path 算子及六个 feedback_closure 算子。CIAV 请求由真实规划器处理，模拟回执由显式 oracle realizer 提供；有模拟反馈，不等于外部真实相机或物理执行。原始来源 ID、每步路径、候选解释数、actor posterior 与所有 trace 保留在输出。

缺失输入检查核心状态哈希不变，不写记忆、不执行 P5。移除证据后 actor posterior 保留歧义：owner 约 0.3951、guest 与 unknown_actor 各约 0.3024，与完整证据轨区分。

迟到反证在 12 日输入之后到达，预先绑定此前选定位置下各个已提交 revision 的原快照/位置。负搜索似然及 RETRACT 阈值来自受控 policy；类名中 Calibrated 不代表本轮完成经验校准。随后用公开 `consume_feedback` 回到原核心处理。动作指标是 `prepare_habit_placement` 的建议位置变化，**实物执行次数为 0**。

## 实际发现的修前缺口

修前证据完整保留在 `output/controlled-semantic-v4/`。该运行的 source_unchanged=false，故只是缺陷发现运行，不是最终冻结签收。

oracle 场景 3 条反证均消费，committed 从 4 变 1，位置 A 概率 0.6680 变 0，位置 B 变 1，下一位置 A→B。

缺失场景原有 6 条 committed，预绑定 4 条目标反证。前三条被消费，第四条在 `_apply_event_revision_outcome` 原第 3665 行抛 `KeyError('superseded revision is not a committed prototype event')`。该目标 `21c0fcef-ffb5-5e08-bf74-a025e855a2f6` 已不在 committed，但仍在 observed，write eligibility active=true。这不是可以忽略的“同一条反证重复”，是重算降级后仍有效观测的迟到反证不能消费。诊断如实记录拒绝、目标资格、核心状态未变化，`all_feedback_consumed=false`；不能将“目标不再 committed”改称全部撤销成功。

最小重现：种子 7，12 个情景日，缺失索引 (2,5)，移除角色证据索引 (3,6)，在第 12 日后的同一阶段，按原提交顺序为当时建议位置的四个 revision 依次提交预绑定反证。后面的目标被先前重算降级，触发以上拒绝。

主实现者据此修复共同核心：RETRACT 可处理有真实历史发布绑定、仍在 observed 的降级观测；CORRECT 权限不放宽；派生链覆盖归档/观测/提交集合；只对现存 committed 贡献撤销 Hybrid 统计。此工具仅负责复现和验证，没有直接修改核心。

## 恢复对照与冻结要求

同一输入历史完成后，使用 SQLite backup 复制一致性快照；原对象继续处理反证，第二个对象从快照 resume 后处理同一反馈。比较实际 committed/quarantine/observed、位置分布、建议动作与 feedback operations。再关闭恢复对象、从反证后的数据库重新 resume，显式重建个性化模型，确认撤销目标不在 observed、write eligibility active=false，不能在重建时复活。

输出分别记录恢复前后相等、重建相等、全部反证消费、目标撤销资格；Hybrid full rerun 比较也是独立字段。运行源码清单记录每个 src Python 文件、CLI、复用 probe 和依赖锁的哈希。该磁盘哈希清单**不等于**解释器 code-object 证明或整体两轮独立对抗审核。并行开发期间 source_unchanged=false 的运行必须保留为开发结果，等共同源码冻结后重新运行。

```sh
PYTHONPATH=src PYTHONPYCACHEPREFIX=/private/tmp/cpswm-controlled-frozen-cache \
  /private/tmp/cpswm-pc-a-real-semantic-input-20260915/.venv/bin/python \
  tools/run_controlled_semantic_mechanism.py --output output/controlled-semantic-frozen

PYTHONPATH=src PYTHONPYCACHEPREFIX=/private/tmp/cpswm-controlled-frozen-test-cache \
  /private/tmp/cpswm-pc-a-real-semantic-input-20260915/.venv/bin/python -m pytest \
  tests/test_controlled_semantic_mechanism.py -q \
  --junitxml=output/controlled-semantic-frozen-tests.xml
```

修前失败不删除。自然几何/语义结果由其它轨道单独报告；本轨道不得用于替代自然感知校准或真实连续能力验收。

## 修后实际结果

2026-09-16 修后运行 `output/controlled-semantic-v5-repaired/` 完成，运行前后源码清单一致：

- source bundle SHA256：`2ba4434681dc64800439f5f4818dd1c062043f95b7f9b55dd6b00fb3acf1e545`。
- prototype_spine.py SHA256：`99e040da480e3409e0bf9c21a017bb1cbea3935d83dcc64324805bc95ca1173d`。
- 两个场景均 `all_feedback_consumed=true`，原第四条迟到反证合法消费。
- oracle 完整轨 12 次 P5，3 条迟到反证；缺失歧义轨 10 次 P5，4 条迟到反证。
- 两轨均后验行动分布改变、下一建议位置改变；中断恢复前后及再次恢复重建一致，全部目标从 observed 移除且资格 inactive，Hybrid full rerun 等价。
- 两个回归测试实际通过（0 failure/error/skipped）；运行时间约 61.524 秒。XML：`output/controlled-semantic-v5-repaired-tests.xml`。Ruff 两个新增 Python 文件检查通过。

这只是修复后的受控机制轨证据。父任务后续如修改共同源码，仍须在最终固定源码上整体重跑；本执行者是实现/复现者，不算用户要求的两轮独立审核。

额外边界覆盖复用上面的同一 P5 历史数据库，仅恢复实例，不重新生成五组场景：

1. observed 仍有目标但没有 published binding history，RETRACT 必须拒绝且状态不变。
2. 目标已有历史绑定但已从 observed 删除，新 RETRACT 必须拒绝且状态不变。
3. 目标降级为非 committed，CORRECT 仍拒绝且状态不变。
4. 两层仅存归档的 suspended 派生后代，在父项撤销后必须全部 tombstone，重建不能恢复。
5. Dirichlet 重建中故障，回滚必须恢复核心哈希、父项与两个派生生命周期。

后两项的归档链是明确人工构造的机制边界输入，与前面的实际 P5 正路径分开。首次边界测试 6 通过、1 失败来自故障注入测试的基线采集位置：实例 runtime identity 包含属性名，注入 `_revision_fault_hook` 自身改变身份；逐字段比对只有该 runtime_configuration 差别。测试改为安装故障钩子后采集基线，仍严格断言故障前后完整状态哈希相等，未修改核心或放松回滚标准。最终边界结果见后续 XML。

最终新增套件实际 **7 passed / 0 failure / 0 error / 0 skipped**，耗时 45.606 秒。证据：`output/controlled-semantic-boundary-fixed-tests.xml`。新增工具和测试 Ruff 检查通过；至此本轨道代码停止修改，等待父任务最终源码冻结重跑。

## 本批共同冻结复验

共同源码 `47e307d97100c7fc1f04cb64fd1a05e926355c7e` 再次运行至 `output/controlled-semantic-frozen/`，报告source_unchanged=true，3/4条反馈全部消费，两轨全部恢复/重建无复活字段为true。冻结7例测试0failure/error/skipped，用时46.675s。最终证据在`evidence/controlled_frozen_*`及`controlled-semantic-frozen-tests.xml`。这仍是实现方受控复验，非最终整体独立审核。

开发测试另有一次6通过/1失败：故障注入测试在插入hook前计算基线，而runtime配置哈希包含实例属性名，导致hook本身改变哈希。最终将基线移到hook安装之后，回滚检查未放松；原失败XML保留为`controlled_boundary_development_failure.xml`。这是测试基线错误，与上述生产KeyError缺口分开。
