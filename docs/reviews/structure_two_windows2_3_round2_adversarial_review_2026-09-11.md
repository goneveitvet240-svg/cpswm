# 结构二窗口二、三修复后的独立对抗审核

日期：2026-09-11。状态：PARTIAL_AUDIT（限定范围的独立对抗审核，不是整个系统穷尽审计）。

**验收判断：两个窗口均有实质修复，但现在都不宜整体关闭。** 窗口二在正确源码加载条件下的 R1 回归成立，仍能通过跨工作树加载让 999 次提交伪造包被认证为当前源码结果；窗口三的 R2 依赖检查、R3 正式修订及 R4 联合因果证据仍有未闭合项。原始开发比较结论仍受正确源码的新鲜重放支持，不能由这些验证器缺口反推原始数据造假。

## 1. 固定对象与执行边界

| 对象 | 审核提交 | 独立工作树 |
|---|---|---|
| 窗口二 | `f022f1901f07bc0afa43b7c2b3fc5397d6367517`；代码修复 `f6d960d` | `/private/tmp/s2-review2-w2.7Ri3Jk` |
| 窗口三 | `d17e88af2c625a62cea95a86482d6dbffdbfff03`；代码修复 `77724e8` | `/private/tmp/s2-review2-w3.adyJ2U` |
| 共同起点对照 | `09eb4d48e1c11082e90ca18332d04333e6b5b47a` | `/private/tmp/s2-w3-src-09eb4d4` |

使用项目原生解释器 `/Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/.venv/bin/python`。标准回归的 `PYTHONPATH=src` 指向各自检出。没有语法降级、跳过测试或用模拟重放代替真实重放。

没有修改、合并窗口一/二/三原工作树中的实现，没有覆盖留存 benchmark、检查点或历史产物。主工作区只增加本报告及其复现证据。故障注入只作用于独立审核进程；跨源码检查另用专门临时副本，明确不把它当作正常运行环境。

## 2. 本次实际运行

| 检查 | 本次独立结果 |
|---|---|
| W2 原有 20 项 + 新增 6 项 | **26 passed**，424.15 秒 |
| W2 真实归因 CLI 完整新鲜重放 | 60 episodes / 1920 steps；真实包 `CURRENT_SOURCE_FRESH_REPLAY_MATCH`，21 个完整攻击包全部 `REJECTED` |
| W2 跨工作树源码加载、另一轮真实 CLI 完整重放 | 60 episodes / 1920 steps；真实包被拒绝、原有 999 次提交伪造包被标 `CURRENT_SOURCE_FRESH_REPLAY_MATCH`，见 §10 |
| W3 新增四文件 + wiring | **92 passed**，33.74 秒 |
| W3 其余七个指定回归文件 | **121 passed**，21.60 秒 |
| W3 core prototype 测试 | **1 passed**，0.48 秒 |
| W3 上述指定集合并集 | **214 passed = 150 原指定项 + 64 新增项** |
| W3 runtime identity / adaptive predeath 两个门测试文件 | **59 passed、4 failed、9 errors**，51.76 秒 |
| 同两个门在共同起点上的对照 | **59 passed、4 failed、9 errors**，50.97 秒；完整失败/错误节点名称相同 |
| 新增独立 W3 反例 | 完整载荷语义遗漏、正式 P0 错误证据链、正式撤回的隔离提升、反馈时序、CIAV 真实调用计数；见下面 |

因此，“指定 214 项通过”和“这两个门没有新增失败节点”的描述可信；**它们不等于这两个门通过**。本次没有重跑窗口三所述整个 9 文件邻域，也没有重跑全仓库几千项测试，不把他人的留存日志算作本次执行。

W2 本次独立原始日志与完整矩阵：

- [真实 CLI 输出](data/structure_two_windows2_3_round2_review_2026-09-11/w2_adversarial_cli.log)
- [21 项完整攻击矩阵](data/structure_two_windows2_3_round2_review_2026-09-11/w2_adversarial_matrix.json)
- [弱自洽检查明确降级的输出](data/structure_two_windows2_3_round2_review_2026-09-11/w2_r1_file_consistency_only.log)

W3 本次独立反例：

- [可执行复现脚本](data/structure_two_windows2_3_round2_review_2026-09-11/probes.py)
- [实际结果](data/structure_two_windows2_3_round2_review_2026-09-11/w3_probe_results.json)

## 3. W3-R2 仍未闭合：字段齐全的错误依赖仍可通过

优先级：P1。定位：`prototype_spine.py:1175` 的 PCHMP 字段要求、`:1200` 的 CCRR 字段要求；实际检查在 `_adaptive_rgrc_debt_guard`。

修复确实拒绝了上一轮的 `observation_count=-999`、`posterior_advanced=True`、错误快照等反例。这部分有效。

但如下完整载荷仍全部被接收：

| 攻击 | 本次结果 |
|---|---|
| PCHMP `evidence_content_sha256s` 改为一条不存在的 `f…f` 哈希 | 接收 |
| 同字段改为整数 `-999` | 接收，类型也未检查 |
| CCRR `consumed_cf_bocpd_maintenance_sha256` 改为 `f…f` | 接收 |
| 同字段改为 `None` | 接收 |
| 另一个独立运行实例、相同零观测/空快照状态的 CF 载荷 | 接收 |

前四项都只改变 `consumed_*` 回执哈希，RGRC 的非哈希语义返回体不变。它检查了字段集合及部分状态，但没有验证证据哈希集合是否等于本次转移，也没有验证 CCRR 所称消费的 CF 哈希是否来自本次真实上游。

进一步通过故障注入让 PCHMP 实际返回错误证据哈希，再运行**正式 P0 入口**：

```text
selected_path = P0_SAFE_DEFERRED
verified_operator_rows = 7
expected evidence SHA = ad80fb1c90a1f6a401b1d9110744375444fbfb946263d2fadbda8d477331d124
received evidence SHA = ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff
committed = 0
pending_debts = 1
```

这些回执是正式入口自行生成、由现有验证器检验，不是审核脚本手工伪造。故障注入本身是内部数据流健壮性测试，不声称普通外部调用者天然具有改写私有方法的权限。零提交保护仍生效；**失败的是“来源与依赖检查已完成”的声明，不能把它扩大为已发现 P0 越权提交。**

报告所称“任何不一致都失败关闭”“跨执行载荷不能通过”仍过强。相同语义状态是否允许跨实例复用可以另行约定，但现在既没有执行身份绑定，也不能声称所有来源字段都检查过。

验收需要覆盖完整字段的类型、真实转移/债务/执行身份及跨算子传递关系；不只增加上述几个常量黑名单。

## 4. W3-R3 仍未闭合：正式撤回有大范围新增提交副作用

优先级：P1，已披露但未解决的生产行为，不冒充本次新引入回归。

本次用 10 天真实 direct-P5、不同位置 CIAV 闭包形成历史，然后经公开的 `process_execution_feedback` 撤回一个已提交事件。仍使用其公开 `policy=` 接缝，调用方提供撤回策略；不是默认系统自主判断。

```text
committed:     3 -> 19
quarantined:  17 -> 0
目标事件移除: true
新增提交:     17，全部来自原 quarantined 集合
总 Hybrid alpha: 2.2904373204180026 -> 17.533654496790184
内部账本重放 equivalent: true
```

与窗口三报告的 `3 -> 18、新增 16` 不矛盾：它选择多数位置的目标，本次选择第一个已提交事件；撤回目标不同。两种运行都表明一次撤回会重新分类整段历史。

根因路径是 `_rebuild_personalized_models` → `_recompute_active_regime`：重新执行 CCRR 后重建 committed 集合，未把原自适应通道的写入阻断身份作为持久约束。**内部重放一致不等于这次新增提交经过了符合预期的授权。**

必须区别两个问题：用户决定长期提升的科学判据；实现必须保留并验证原始权限、后续授权与状态转换的依据。当前不能证明这些提升符合预期，所以 R3 不能整体关闭。若决定允许重建提升，也需明确记录提升的依据和来源；不能靠把它命名为重建就跳过来源/权限验证。

正对照：在真正 P0 待还债状态下调用公开反馈写入口，会被 `pending adaptive debt blocks legacy and direct-core mutation` 拒绝，committed 不变。本次**没有**发现通过该入口绕过 pending-debt 写阻断。

### 独立对账的边界

新增测试的参考是“遍历当前 `_committed_events`，求和它的 `statistical_owner_weight`”。它独立于 Hybrid 缓存，却不独立于实现刚刚决定的提交集合与权重，不能发现“两个账本同步纳入了不该纳入的事件”。上面的反例正好同时满足这类对账和内部重放。

`test_structure_two_late_counter_evidence_chain.py:168` 还有恒真断言：

```python
assert set(core._committed_events) <= before_committed | set(core._committed_events)
```

`A <= B | A` 永远成立，不能验证“只删除一个谱系、其他成员不变”。需要从事先保存的原始输入/授权/修订历史构造预期成员与统计量，明确区分严格删除、后代删除和获准提升，不以被测对象的最终集合定义正确答案。

## 5. W3-R3 的另一个时序缺口：正确的迟到反馈绑定会被替换

优先级：P2，尚未验证完整的迟到反馈兼容性，不称新引入缺陷。

本次在 12 天 legacy 历史上，先为两个不同的 committed 事件各自准备与其真实快照绑定的反馈。第二条反馈在第一条执行前，通过 `_validate_feedback_revision_binding`。随后撤回第一事件；第二事件仍然 committed，但其快照绑定被重建改写。再提交原来正确的第二条反馈，会得到：

```text
ValueError: feedback revision snapshot does not match the committed event
```

新修复解决了“重建后快照为空、任何后续反馈都不可用”，但当前测试每轮重新制造绑定，不证明已经发出、合法绑定到旧快照的迟到反馈仍可处理。已有“拒绝旧快照”负例不能代替这个先验证有效、再经历无关修订的正向时序。

需要显式定义保持历史绑定、验证后重定位或返回可恢复过期状态的行为；不能偷偷把迟到反馈能力删除，也不能简单取消所有快照检查。

## 6. W3-R4 部分证据仍被放大：旧入口不等于完整七算子协作

优先级：P2。

新版表把 binding / 等价 / 分布 / 解码动作 / 收益分开，明显优于第一轮；CIAV 的 likelihood 干预确实能改变实际 top-1。可是 OPCEU、ORRER、PCHMP、CCRR 的多项干预测试经 `_legacy_run` 直接调用 `core.process_transition`。尤其 CCRR 测试注释 `test_structure_two_operator_causal_matrix.py:307` 声称两臂都运行完整七算子路径。

本次不替换任何算子，用 Python 调用跟踪检查实际 CIAV 规划器和执行器：

| 场景 | CIAV planner 调用 | CIAV executor 调用 |
|---|---:|---:|
| CCRR confirmation_window=2、18 天旧入口 | 0 | 0 |
| CCRR confirmation_window=3、18 天旧入口 | 0 | 0 |
| 正式 direct P5 单步正对照 | 1 | 1 |

因此，这些数值变化证明旧主干中的局部因果作用，不能与另一条路径的七份身份回执拼成“同一生产车道七算子联合协作已验证”。

此外，`test_cf_bocpd_output_is_the_snapshot_ciav_later_reads` 的名字/注释说验证真实对象身份，但断言仅检查 callable 名称、当前快照非空、CIAV 回执非空，没有比较实际传递对象、内容或受控干预。这是测试证据缺口；本次没有据此断言实际 CF→CIAV 接线一定错误。

建议按“入口 × 算子 × 上游扰动 × 下游数值 × 解码动作 × 空对照 × 独立参考”逐格登记。未覆盖保持未覆盖，不把 legacy、独立滤波器和正式 direct/debt 证据互相替代。

## 7. 可以保留的修复和结论

- W2 在正常、正确源码加载的运行条件下，弱自洽入口与强新鲜重放入口确已分开；现有 21 项完整伪造包均被拒绝，包括 999 次提交、同步重算归因、重新绑定当前源码、伪造成功回执。强入口没有退化为信任攻击者自供参考。
- W3 上一轮的明显矛盾维护载荷现在拒绝；正式反馈撤回入口、回滚及重复反馈测试比私有 Hybrid 撤回证据有实质进展。
- CIAV 负观测确实计算局部 Bayes 后验，`target_distribution_id` 改成 `ciav-local-actor-posterior:*` 更真实。这一局部回执语义修复可以保留，不意味着已打通负观测的持久化、动作和长期反馈闭环。
- W3 把旧 direct/debt 产物登记为当前源码绑定失效、不混称当前有效，是正确纠偏。本次独立复跑的两个门仍失败，且共同起点上失败节点相同。R5 的状态纠正不等于已经产出最终组合源码下的新证据；本次未重新复验所有历史版本。
- 报告承认默认策略不会自主 RETRACT/CORRECT、第二套 feedback revision loop 未接入所测路径、CCRR 身份输入恒为零、完整粒子/神经提议/条件化 RB 主干未接入生产。这些缺口不能因为回归测试绿而消失，也不能据此缩小结构二范围。

## 8. 比较公平性与科学结论

正确源码条件下的 W2 新鲜重放支持：60 episodes / 1920 steps，PUT_BACK 错误 P5=85、AMG=102、learned=533；17 步差额全部可由 53 个 AMG 尚无 owner 估计步骤的冷启动规则差异解释。共同均匀规则下 AMG 错误也为 85。

P5 的 `_committed_events=0` 覆盖 1920 步；完整 P5 与 fast 读出的 PUT_BACK 选择差异为零；三臂 SEARCH 分布在 1920 步相同。原改善约 0.008854，仍未达到原 0.02 门槛。

这支持开发诊断，不支持七算子方法优越性。源码重放验证修复不消除未来支持集暴露、公共 detected-location SEARCH 读出、信息权限和计算/容量/训练预算差异等原比较设计问题；也没有补齐真实动作影响后续观测、长时巩固与迟到反证能力的确认实验。

三个窗口仍不是同一组合提交。合入任何源码都会影响宽来源绑定；以后需在最终同一源码树、同一解释器/配置下重新生成新版本证据。**不能拼接不同分支的绿色测试，声称验证门或系统整体通过。**

## 9. W3 独立复现

```sh
cd /private/tmp/s2-review2-w3.adyJ2U
/Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/.venv/bin/python \
  /Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/docs/reviews/data/structure_two_windows2_3_round2_review_2026-09-11/probes.py \
  /private/tmp/s2-review2-w3.adyJ2U
```

脚本的四类维护载荷攻击、时序及撤回是独立断言/观察，不调用实现者的回归测试函数或以它们返回的 pass 作为证据。共享 scenario harness 只负责构建已登记场景与合同输入，边界如上。没有训练新路由器、启动七算子消融或打开新的测试分布。

## 10. W2-R1 的剩余来源缺口：实际导入源码不等于声明源码

优先级：P1。定位：`summarize_structure_two_comparison_audit.py:16` 导入审计模块，`:278` 从 CLI 文件位置确定声明根目录；`structure_two_comparison_audit.py:554` / `:594` 只绑定这个目录的磁盘字节。没有证明实际已加载的本地模块来自这些字节。

本次另建隔离副本 `/private/tmp/s2-review2-w2-source-root.YhHH9K`，同为 `f022f19`，只修改其诊断模块 `_p5_readouts` 的一行，把 `_committed_events` 的诊断读数固定为 999。没有改正式 A 工作树、真实包、留存 R1 伪造包、Python 解释器或第三方库，也没有向验证器传入预计算参考。

随后使用 A 工作树的原始 CLI，但让 `PYTHONPATH` 指向 B 的 `src`。声明绑定的 A 文件 SHA 为 `83e02ea5ae86bf1244312d654ce73df7b88f65c4bf242d63c82a7f8128b438f3`；实际导入 B 文件 SHA 为 `86be7f7fbded88b9dba98ae234b995526cf8a24246e01812b274a717aa666f96`。

真实 CLI 再次从头执行 60 episodes / 1920 steps，结果发生反转：

| 输入包，保持原字节 | 正确 A 源码加载 | A 脚本 + B 源码加载 |
|---|---|---|
| 真实 v2 包，commits=0 | 通过 | `REJECTED`，state_counts 不匹配 |
| 留存 R1 完整伪造包，commits=999 | 拒绝 | **`CURRENT_SOURCE_FRESH_REPLAY_MATCH`** |

批处理因含被拒绝的真实包而整体 exit 1；本次没有把 exit 1 说成整个批次通过。漏洞是**伪造包获得了逐包肯定认证**，而且该肯定声明指向 A 的源码绑定。原始结果和完整条件保存在 [跨源码反例结果](data/structure_two_windows2_3_round2_review_2026-09-11/w2_cross_source_result.json)。

这是来源错配条件下的反例，不是正常正确 `PYTHONPATH` 下 21 项测试失效，也不证明历史执行采用过这种错配。它不需要恶意替换解释器或第三方库；多个开发窗口串用本地源路径已足够。若选择把本地模块加载完全当作可信外部前提，成功声明必须明确此条件，不能说这些本地源码字节本身已经受验证。

复现命令（B 是上文专门故障注入副本，不要用于正常实验）：

```sh
cd /private/tmp/s2-review2-w2.7Ri3Jk
PYTHONPATH=/private/tmp/s2-review2-w2-source-root.YhHH9K/src \
/Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/.venv/bin/python \
  /private/tmp/s2-review2-w2.7Ri3Jk/apps/evaluation_runner/summarize_structure_two_comparison_audit.py \
  --bundle /private/tmp/s2-review2-w2.7Ri3Jk/docs/reviews/data/structure_two_comparison_audit_window2_r1_2026-09-11/bundle_v2 \
  --bundle /private/tmp/s2-review2-w2.7Ri3Jk/docs/reviews/data/structure_two_comparison_audit_window2_r1_2026-09-11/counterexamples/r1_current_source \
  --verify
```

建议修复必须覆盖两个 CLI 的真实加载根、已加载模块/代码与源字节关系，不只再加磁盘哈希。主 CLI 还提供 `--repository-root`，也需定义它是数据根还是执行源码根并验证一致性。本次没有独立攻击此参数、陈旧字节码及所有加载竞态，不把这些未测试分支宣称已覆盖。后续与窗口一的来源修复应在同一最终提交整合验证。

## 11. 交付状态与下一次验收条件

| 原事项 | 本次判断 |
|---|---|
| W2 R1 | 正常路径已修，跨源码肯定认证仍可绕过；**部分完成，不能整体关闭** |
| W3 R2 | 命名反例已修，完整错误字段及同状态跨执行遗漏；**部分完成** |
| W3 R3 | 正式撤回接缝与非空绑定有进展，但新增提交、原始参考、迟到反馈时序未闭合；**部分完成** |
| W3 R4 | 表格分层纠偏有效，部分局部干预真实；完整七算子同车道因果覆盖**未完成** |
| W3 R5 | 旧证据失效声明已纠正；最终整合版本的重新生成/验证**未完成** |
| W3 R6 | 局部 Bayes 与回执目标语义修复可保留；不升级成负观测完整闭环 |

应先补齐源码身份和维护依赖验证，再明确修订/提升/迟到反馈的合法状态转换并增加独立原始参考；随后在同一正式生产车道补因果矩阵，最终统一源码与证据重新验收。科学门、比较公平性和方法收益分别判定，不由上述工程修复代替；用户保留科学判据与完整研究方向的决定权。
