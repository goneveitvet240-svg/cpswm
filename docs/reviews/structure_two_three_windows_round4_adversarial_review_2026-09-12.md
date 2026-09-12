# 结构二：三个窗口最新修复的独立对抗审核

审核日期：2026-09-12。本次列出的独立审核与长重放均已结束；这是有界审核，不是全系统穷尽证明。本次只审核，不修改三个原窗口的实现，不合并、推送或签发授权。

## 1. 当前判断与固定版本

| 窗口 | 本次实际审核对象 | 判断 |
|---|---|---|
| 一 | `2a5f45947952e8d725009141716b42ac879434f3`，实现提交 `05c78af2a38e07e0171c5352bf4ab9b9da3124d2`；副本 `/private/tmp/s2-review4-w1.p5JONv` | 本轮证据链修复限定通过：89 项、五类完整重算、真实跨根历史审核及原生检查点当前性通过。不是科学门通过 |
| 二 | `45850dc680cb83169c3108d6a1a5455f7e069457`，实现提交 `9b58d7e93e8646c869bfd856be0dff5c6229d82b`；副本 `/private/tmp/s2-review4-w2.pdinJv` | 本轮诊断检查修复限定通过：58 项独立通过；公平性仍未建立 |
| 三 | `281e88894fca527df1d54018b5053469e8c422d5` **加本轮未提交交付**；副本 `/private/tmp/s2-review4-w3.cwwAVs` | **不能验收通过：三个矩阵外反例**。已有纠错、授权、接线修复部分有效 |

窗口三不是按旧 HEAD 空审：原工作树、独立副本与交付 manifest 的 **558 个 src/tests Python 文件**逐一比较，零差异；完整文件哈希映射摘要 `9c069ee040b14d12a643ed7fc64644131d7843e3c6640c801aacad35cd2b5761`。原报告 manifest 自身摘要 `47b480bf994ebc4a9543c6df207830c49fd33133a868bc67c0518b41a0dce893`。详见 [快照绑定](/Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/docs/reviews/data/structure_two_three_windows_round4_review_2026-09-12/snapshot_binding.json)。

## 2. 窗口三的新反例

三个反例都在固定副本中直接运行；不替换生产方法，不关闭生产保护，不手工改动统计状态。脚本和原始结果：

- [复现脚本](/Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/docs/reviews/data/structure_two_three_windows_round4_review_2026-09-12/w3_new_boundary_probes.py)
- [本轮结果](/Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/docs/reviews/data/structure_two_three_windows_round4_review_2026-09-12/w3_new_boundary_probes.json)
- [公开修订接口在旧提交的对照](/Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/docs/reviews/data/structure_two_three_windows_round4_review_2026-09-12/w3_direct_revision_previous_source.json)

### P1：公开低层修订接口仍会返回 CORRECT，但新旧长期记录都消失

路径为 `core.apply_event_revision_outcome`，不是本轮已补偿的 `process_execution_feedback`。真实 legacy 十二条历史，选择第四条已提交记录，提交合法类型的异位置纠正，owner mass 不变。结果：

```text
returned_operations = ['correct']
old_still_committed = false
new_committed = false
new_quarantined = false
ccrr_conclusion = 'stay'
```

[prototype_spine.py:3287](/private/tmp/s2-review4-w3.cwwAVs/src/cpswm/system/prototype_spine.py:3287) 在重建之前设定 CORRECT，重建后没有检查新记录是否仍存活，直接返回。外层同步反馈入口的回滚检查挡不住直接调用这个公开方法；`PrototypeRevisionResult` 也没有一个能明确表达本次拒绝/延期的状态字段。

此反例在旧 `281e888` 也成立，因此是**尚未封闭的旧路径**，不指称本轮新引入。原 44 项自动阶段测试也通过，说明这些正负后置条件仍未被现有集合覆盖。报告关于上层同步反馈八个目标显式回滚的结论可以保留；不能推广到所有同步修订入口。

修复要求：统一公开接口的结果后置条件与事务原子性。成功必须对应实际生效；拒绝应恢复原状态；确需延期应返回显式可追踪的延期结果。内部可隔离而外层延期的机制可以保留，但不能让公开成功结果掩盖贡献消失，也不能删写入资格门强制提交。

### P2：独立参考不支持从已合法纠正的状态重新开始审核

真实 legacy 两条记录 → 公共反馈成功纠正一条 → **此时才冻结新 journal** → 不再做任何操作就调用检查器。系统状态完全未变，实际 committed 为 2，参考却只推导出 1，报 `live revision membership mismatch`。

根因见 [structure_two_revision_oracle.py:133](/private/tmp/s2-review4-w3.cwwAVs/tests/structure_two_revision_oracle.py:133)：冻结资格的 `eligible()` 只理解原始未阻断资格和 `ccrr_habit_change_promotion`，不理解冻结时已存在的 `formal_correction_transaction` 及其父链。已有连续纠正测试在第一次纠正之前冻结 journal，不能覆盖这个不同的起始状态。

这是参考检查器的**误拒绝**，不是证明生产统计又算错了。新参考已不再用最终成员集合定义预期，八类故障检出仍有价值；但 B 项只能按原测试起始状态限定接受，不能称任意合法修订历史均可复核。

修复要求：冻结完整必要的原始资格、历史父链、既有操作及证据，独立验证已有纠正授权；增加“冻结前已纠正”“多代纠正后再冻结”“授权人失效及伪造父链”的真实正负用例，不从最终被测结果补参考。

### P2：相同输入做相同纠正后，语义摘要仍不可复现

两次运行各建立相同两条 legacy 历史，纠正前语义状态相同；固定相同 feedback record ID、action ID、目标、位置、质量和策略，只允许各运行使用自身合法 snapshot binding。两次纠正均成功，但纠正后语义摘要不同。完整语义结构的**唯一差异**是：

```text
.qualifications.correction:0.authorizations[0].basis_sha256
```

[structure_two_semantic_identity.py:107](/private/tmp/s2-review4-w3.cwwAVs/src/cpswm/system/structure_two_semantic_identity.py:107) 重新计算了语义化 parent/outcome 摘要，却遗漏授权行 `basis_sha256`；该值仍含本次随机 corrected revision ID 的原始哈希。单纯观察/direct/debt 的无纠正复现测试都能通过，不能覆盖修订后的摘要。

修复要求：在验证原始授权/账本完整性后，对所有指向内部身份的派生摘要一致地构造语义对应值，不能删除授权信息或关闭原始校验。增加同/异位置纠正、连续纠正、撤回后的跨运行等价与错误引用应不等价测试。G6 保持部分完成。

## 3. 窗口三：本轮确实修好的部分

独立重跑四组，均无失败或跳过：原 16 文件 **252 passed / 171.57s**；本轮新增 **105 passed / 613.86s**；报告列出的邻接组 **82 passed / 24.67s**；本审核追加的 `test_project_one_automatic_regime_loop.py` **44 passed / 6.67s**。不将这些数字合成为完整系统通过。

原独立脚本的四种公共反馈纠正（legacy/direct-P5 × 同/异位置）如今均有新 revision 真正 committed、资格存在、Hybrid 活跃贡献；旧反例的 legacy `12 → 11` 已变为 `12 → 12`。direct-P5 异位置会同时重分类其他记录，总数 `3 → 1` 不能替代逐 revision 检查，新纠正项确实在其中。

原 journal 脚本现在检查的是一个真实成功的纠正；八类控制故障测试通过。混合公共授权正例不再空跑：五条稳定 legacy → 一条被明确阻断的 direct-P5 → 下一条 legacy 触发 CCRR HABIT_CHANGE → 被阻断项实际获授权并提交；撤回授权人、重复、失败回滚/重试等断言通过。

31 天原纯 direct-P5 输入仍 `grant_found=false`；另一条混合正例不能关闭该输入下纯自适应固化缺口。原独立脚本输出分别保存在本次 data 目录的 `w3_original_additional_probes.json`、`w3_original_journal_probe.json`。

| 接口/能力 | 本次可接受的证据 | 仍不能声称的内容 |
|---|---|---|
| G1 慢写/固化 | 已证明现有合同内非空混合解禁；原始阻断不被纠错重建越权提升 | 纯自适应同位置、负观测的通用慢写路径完成 |
| G2 主干—反馈循环 | 共享真实 engine/message passer；新增入口实际 ingest/infer/revise_actor/stat apply，去重/回滚/重试测试通过 | 所有反馈轴、完整粒子后缀修订与全回放闭环完成 |
| G4 身份证据 | identity-switch 概率实际进入 CCRR observe/decide；固定其余输入的干预改变授权 | 概率估计/校准本身正确 |
| G5 完整生产主干 | 缺口被明确列出，没有偷偷删功能 | 持久完整粒子、神经提议、条件化 RB 统计已生产接通；其中仍有已确定但未做的工程 |
| G6 语义一致性 | 无纠正的所列三条运行路径可复现 | 修订后也稳定；本轮新反例直接反驳 |
| G7 实例/方法绑定 | 25 个路径×方法替换、同类外来额外实例等测试通过 | 七算子全部数学分支及每种时序已验证；七条声明回执等于七算子全部执行 |
| G9 自主修订 | 显式 caller-policy 和多轴反馈能产生修订 | 默认自主撤回/纠正策略已完成 |

本轮报告保留 G1/G2/G5/G6/G7/G9 的未完成项是可靠且必要的。主要不足是它的有界修复声明仍漏掉上述公开入口、已修订初态和修订摘要组合。

## 4. 窗口二：诊断执行可信度提高，完整公平性仍未建立

本次独立 **58 passed / 1089.62s，无失败或跳过**：原 42 项执行来源/完整伪造回归及新增 16 项公平性检查。包含四条完整合法包重放（原完整伪造同批、两个错误 pyc 入口正例、新公平性伪造同批）。真实完整 CLI 的合法包 `CURRENT_SOURCE_FRESH_REPLAY_MATCH`（60 episodes / 1920 steps），同批六个重算自哈希、摘要与归因的完整伪造均被拒：未来支持集、缺失 owner、实际资源、选择期访问、消费特征、公平性 PASSED 假声明。不是仅看批处理 exit 1；每一个条目均核对。

[六类完整伪造结果](/Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/docs/reviews/data/structure_two_three_windows_round4_review_2026-09-12/w2_fairness_forgery_matrix.json) 为本次产出的紧凑摘录，保留完整原始工件路径；实际加载 162 个 cpswm 模块。

源码核对：train/validation split 包装接到实际训练和选择；validation 改成真实 posterior decode 后读取真值，保持原 12 次训练、24 个 learned 候选、3 个 AMG 候选及选择规则；17280 次验证评分访问发生于该承诺步骤之后。测试期三臂动作提交后才评分。消费回执与真实 packet 重构核对，不只是三臂互相一致。没有因此声称旧模型一定作弊。

独立重放支持的诊断结论仍为：

- P5/AMG/learned PUT_BACK 错误数 **85/102/533**。53 个 AMG 尚无 owner 估计的实际触发步骤，用同一均匀缺省规则替换 habit 读出，保留 SEARCH 不变，错误 **53 → 36**；总数 **102 → 85**，原 17 步差额消失。这是已打开开发数据上的局部控制，不是新基线注册或普遍因果证明。
- P5 在 **1920/1920** 步长期 committed 数为零，full 与 fast 的 PUT_BACK 选择差异为零。当前实验没有在检验“七算子完整长期联合机制带来优势”。
- SEARCH 三臂分布在 1920 步完全相同；1040 步的候选支持集含当前可见前缀之外的地点。若是公共先验地图可能合法，若是因果前缀约束则不合法，权限必须明确，不能因三臂都看到而自动称公平。
- 180 条历史动作链匹配；不等于 baseline 的特征利用、容量、训练/推理预算已经公平。资源来自共享数据包且零成本，不是完整具身任务 utility（效用）比较；本机并行审计耗时不用于性能排名。

因此 `comparison_fairness=NOT_ESTABLISHED`、`scientific_validity=NOT_ESTABLISHED` 的结论可靠。窗口二本轮可以证明诊断/检查的改进，不能宣布公平对比完成或结构二方法有效/无效。需要保留用户对地图权限、共同缺省先验、原生搜索头与预算、信息权利、容量/算力以及长记忆挑战分布的选择权。

## 5. 窗口一：入口、历史可移植性及检查点

独立定向测试 **89 passed / 1371.93s，无失败或跳过**（36 个本轮入口/跨根用例 + 53 个既有补修用例）。真实支持 file、module、runpy、spawn 的正例与旧 unchecked/same-size-mtime/foreign-filename 入口、bootstrap 执行后漂移等负例；不把支持范围扩展到任意不可信解释器/进程内篡改。

跨根历史测试真实执行 A 生成、B 完整验证、B 源码替换后完整重放拒绝，均按预期完成。每份完整报告分别保留 11 份 Git 字节记录、4 个可恢复源码快照和 1 次指定失败数值重放，不能将最早无法导入的源码计作数值通过。报告字段的九类变异通过实际 fresh 报告与生产比较器检验，但不是每种变异重新执行一遍数值实验。已知异常栈帧/来源路径只在采集时规范化，原 ImportError/RegimeStage、源码 commit、覆盖数和真实失败内容保留；没有在验证时删掉输入异常字段。

本次五类当前结果逐一实际重算，最终 exit 0：三臂 `P5_ACTION_SIGNAL_NOT_DETECTED`；事后读出 `POSTHOC_READOUT_DEGENERACY_REMOVED`；延期重放 `PRODUCTION_DEBT_REPLAY_SEMANTIC_EQUIVALENCE_CONFIRMED`；因子实验 `DEVELOPMENT_FACTORIAL_COMPLETE`；内部 D0 留出 `INTERNAL_UNSEEN_D0_SIGNAL_NOT_DETECTED`。全部保持 `POST_OPEN_CURRENT_SOURCE_REPLAY`、非 confirmatory、非首用/未见已建立，不重置历史身份。实际重算一致不等于算法优势或科学门通过。

原窗口自己的 `.venv`、移除额外 `PYTHONPATH` 后，封存检查点 `--verify ... --no-fresh-recomputation` **exit 0**。这是当前性复核，**不是本审核重新跑完完整 fresh checkpoint 或全部 3944 项工程测试**。本次首次启动少传 `--verify` 路径，argparse exit 2；补齐真实路径后通过，不混进修复失败统计。

封存回执报告 3944 passed/1 skipped/1 xfailed、P0 121 等，保留为实现者对应环境的执行记录；skip 后续宿主复跑、xfail、十个工程命令与本审核新增运行分开，不靠绿色总数扩大结论。

检查点当前仍是 `CURRENT_LOCAL_TOOLCHAIN_STATE_ONLY`：工程记录当前一致、所绑定 D0 结果允许称可重算；Task 7/8 科学门仍 FAIL，Task 10 不获得正式授权，Gate-B 执行/七算子有效/外部方法优势均未建立。消融授权、外部有效性、独立托管、执行真实性、密闭工具链均为 false；整合后需要新 checkpoint。

## 6. 证据保全、复跑与验收边界

旧工件独立按 Git 字节复核：窗口一 **210 项零差异**（208 项原路径，2 项可变索引保留原字节到明确备份路径）；窗口二 **122 项零差异**。并非仅信任清单内的 matches 布尔值。原窗口一、二仍干净；窗口三仍为原交付的未提交修改，未由本审核提交。所有新增审计脚本、输出都在主工作区的新 data 子目录，旧审计证据未覆盖。

复跑三个矩阵外反例：

```sh
cd /Users/pangwei/Documents/ai/continual-personalized-semantic-world-model
.venv/bin/python docs/reviews/data/structure_two_three_windows_round4_review_2026-09-12/w3_new_boundary_probes.py /private/tmp/s2-review4-w3.cwwAVs
```

测试命令、日志与快照检查脚本见同目录 `commands.md`。测试含并行进程，耗时只用于记录，不作为算法资源优势。日志有意区分完整运行结果与终端输出摘录。

下一步顺序：先封闭窗口三公开 CORRECT 后置条件、已有修订历史的独立参考及语义摘要；继续 G5 已确定工程并列出真正待决科学接口。窗口二针对用户批准的比较权限与任务设计推进，不能反复把未激活慢记忆的比较当作完整方法检验。保留完整统一框架，不删隐藏事件、多 actor、open-world unknown、可逆归因与具身反馈。

这次不是全系统穷尽证明。仍未覆盖任意 Python/标准库/第三方包篡改、全部竞态和全部科学假设；完整修复需要统一源码和环境上的再验收。三窗口各自通过的日志不能拼成整体通过，任何整合都会要求重建受影响的来源、结果、P0、工程回执与检查点。
