# CPSWM 结构二 W2 公平性与 31 类伪造独立审计

审计时间：2026-09-12（UTC 取证窗口 15:03–15:13）  
审计角色：PC-B 独立审查  
结论状态：**BLOCKED / 不得发布正式科学结论**

## 1. 结论先行

W2 原始证据包在其历史快照内具备可核验的工程完整性：三批命令均以一个非空合法参考包开头；31 个历史伪造包均改变了被选中的结论依赖；历史检查器能够逐个拒绝全部 31 个反例；本次 Windows 局部复跑为 `71 passed` 和 `19 passed`。这些结果支持“历史 R6/W2 证据包的检查器和若干公平性护栏在原快照上工作”，但不支持算法优劣或公平科学比较。

正式 W2 验收仍被阻塞。远端截至本次取证时没有由 A 发布的、已统一审查且包含五项边界修复后的单一冻结 SHA。当前分别存在 W2 验收准备提交 `329787241996631a6abb4fcd3b12d2c13a135777`、W2 原始快照 `de2c04c3e690dba674850af9c4f7e126dbab910e`、A 的 R7 提交 `62870a3a38fce882b25d8d77f1d0526cca6fbc14`、A 的 W1/交叉审查提交，以及 PC-B 修复提交；它们不能在本审计中拼接为一个虚构的验收对象。因此：

- 不给出 `PASS` 或科学排名；
- 不把历史 31 个伪造见证自动视为对未来统一版本仍然有效；
- 不把 Windows 局部测试称为完整 CLI fresh replay；
- 等待 A 发布统一、冻结、可复跑的审查后 SHA，再从该 SHA 生成新的合法参考包和 31 个非 no-op 反例。

## 2. 固定对象与隔离方式

本次只读审计使用两棵互不拼接的 detached worktree：

| 对象 | 远端引用 | 完整提交 SHA | tree SHA | 本地路径 |
|---|---|---|---|---|
| W2 验收准备 | `origin/codex/pc-a-w2-acceptance-prep-20260912` | `329787241996631a6abb4fcd3b12d2c13a135777` | `ab3ea1d707df80934ae5348e5dcb066fcaf12203` | `F:\庞惟\codex\cpswm-w2-audit-20260912` |
| W2 原始保存快照 | `origin/codex/snapshot-w2-20260912` | `de2c04c3e690dba674850af9c4f7e126dbab910e` | `0e452a576eeece0e0b49660bd1179907d0aa82aa` | `F:\庞惟\codex\cpswm-w2-audit-original-20260912` |

两棵 worktree 均保持 clean；没有修改生产代码，没有 cherry-pick、merge、rebase 或复制代码来拼接不同分支。验收准备提交并不包含原始 W2 对比运行时代码，因此检查器/归档审计在准备树上运行，公平性局部测试在原始快照树上运行，两者的结果分别归属各自完整 SHA。

原始证据包的版本链必须区分：

- 审计元数据中的 `base_commit=09eb4d48e1c11082e90ca18332d04333e6b5b47a` 是较早的算法基线，不是最终运行时代码身份；
- 公平性实现先落于 `9b58d7e...`，动态/目标实例修订落于 `72024164a52db6b70c263a332543cf424f017252`；
- `source_version.json` 记录实际运行时代码提交为 `d6112489d0a09f7086286e223741be60051b99a5`、测试提交为 `e8b5cee9601a35bb1220480ebe60b0c74f3c4799`；
- 证据包提交为 `aa9690146e5261d826b642c7bc4c54d2c43be31b`，交接文档为 `a5f3dec...`，最终保存快照为 `de2c04c...`。

因此所有复现陈述均绑定到明确 SHA，不把元数据中的早期 base 当作实际执行源码。

## 3. 公平性十项审查

### F01 公共地图、支持集来源与时间

实现的 `_locations` 优先采用 `known_location_ids`；缺省时会扫描完整 episode 的 source、attempted 与 destination。D0 catalog 为空。三臂获得同一支持集和顺序，这满足“同权输入”的工程一致性；但 1,920 个测试步中有 1,040 步的支持集包含未来才会显现的位置，而且 adapter 持有完整 episode。因此它不是已经证明的 causal-prefix public map。是否允许预先公开全局位置目录是协议决定，当前状态为 **USER_DECISION_PENDING / BLOCKED**。

### F02 owner 先验

P5 与 learned 在 cold start 使用均匀分布并经共同解码器按 UUID 字典序破同分；AMG 在 owner 缺失时通过 encounter-first `_argmax` 形成点质量。原始测试中 AMG owner 缺失 53 步。开发用共同均匀先验后，AMG put-back 错误从 53 降为 36，整体 AMG 错误从 102 降为 85，正好消除 P5 与 AMG 的 17 步差距。这是强混杂信号，不是排名证据。必须由协议明确“原生先验”还是“三臂共同先验”，状态为 **USER_DECISION_PENDING / SCIENCE_BLOCKED**。

### F03 三臂实际消费特征

三臂共享 packet、可见字段、候选结果和成本接口，但实际消费并不等价：

- P5 `_transition` 消费 actor reference prior，并结合 actor、mechanism、ordered role、context；
- learned 的 12 个原始特征压缩 actor posterior、mechanism、visibility/confidence/history/time，没有保留 ordered role/reference-prior 的同等细节；
- AMG 消费 posterior/reference ratio、mechanism 与 ordered role。

`ConsumerProbe` 只对第一个固定 episode 提供受限的 opcode/call 证据，并非完备的数据流污染证明。结论只能是“接口权利相同、实际消费不同且已有局部可观测证据”，不能写成“三臂看到完全相同信息”。状态为 **PARTIAL / SCIENCE_BLOCKED**。

### F04 训练、验证与测试访问时序

原始证据显示：训练 640 行；访问事件为 1 个 visible 加 20 个 `training_truth`；验证选择为 1 个 visible 加 17,280 个 `score_after_commit`，合计 17,281；测试 ID 未进入选择 receipt；测试 truth barrier 在三臂动作提交后才开放。本次安全路径局部测试通过。

但旧基线 `_validation_selection/_evaluate_single_state` 在循环前先取得 truth envelope，W2 审计运行依靠 safe wrapper 避开该路径。统一版本必须直接采用安全路径并重新生成证据，不能靠“本次恰好未走旧函数”完成正式验收。状态为 **ENGINEERING_PARTIAL / UNIFIED_SHA_REQUIRED**。

### F05 独立调参

learned 使用 24 个候选（3 widths × 2 learning rates × 2 L2 × 2 smoothing）及 12 次 fit；AMG 使用 3 个候选；两者都在同一验证 PUT_BACK 目标上选择且未读取测试集。P5 是预先存在的 v0.6 手工方法，其历史开发/选择预算未知。动态场景复用已选参数。故“各自独立选择”有工程证据，但“调参预算公平”没有证据。状态为 **PARTIAL / NO SCIENTIFIC RANKING**。

### F06 容量

learned 选中 width 8、12 个输入特征、64 个活跃 logit 参数、9 个条件 cell；其 head-only 训练为 2,457,600 MACs，全部 12 次 fit 总计 68,812,800 MACs。P5 与 AMG 是符号状态/规则系统，参数个数不能直接对应其状态容量、代码容量或先验知识。当前没有用户冻结的等容量、等计算或 Pareto 比较规则。状态为 **BLOCKED_USER_DECISION**。

### F07 在线预算

历史 timing 仅是开发诊断：2 episodes × 3 repeats，且为非独占 macOS 环境；测量 consume、hash、trace、posterior 与 decode，排除了初始化、训练、数据/IO、truth、scoring 与机器人执行。没有匹配的总计算、延迟、内存、功耗和历史调参预算，不能据此排序。状态为 **NOT_COMPARABLE / SCIENCE_BLOCKED**。

### F08 SEARCH 解码

共同 decoder 对合法 posterior 的变化是敏感的，但 adapter 给三个 current-location head 都填入同一 latest detection/carry。learned joint head 未路由进 SEARCH；AMG 原生 SEARCH 排序也被 adapter 丢弃。结果是三臂 SEARCH 错误完全相同，且 1,920/1,920 步的当前/搜索分布相同；AMG 原生 SEARCH 排名有 1,634 步不同。该实验只验证“共同 detected-current adapter”，不代表各方法的原生 SEARCH 预测。状态为 **ADAPTER_DIAGNOSTIC_ONLY / SCIENCE_BLOCKED**。

### F09 CIAV 成本与信息天花板

packet/receipt 精确核对通过；每臂每步同为 1 次 microverify、1 次 outcome、1 次 cost；五项计费字段均为零，privacy 从 1 保持为 1。它支持信息天花板/调用次数的工程合同，但没有生产净效用、动作依赖环境、真实观测价格或机器人执行成本，不能称为现实成本公平。状态为 **ENGINEERING_PASS / SCIENCE_NOT_ESTABLISHED**。

### F10 长期污染

P5 在全部 1,920 步的 committed-event 直方图均为 `0:1920`，full-vs-fast action difference 为 0；1,276 个 full P5 same-location fast verification 闭合，644 个为明确无新 transition。因此不存在可用于 C0–C3 的 eligible 分母，也没有长期贡献质量样本。

现有 `owner_habit_contamination` 只是动作代理：当真实 actor 非 owner 且预测 put-back 等于真实当前位置时递增，并不衡量已提交 contribution ledger 的污染。最终 C0–C3 协议虽已冻结但未运行。状态为 **C09_NOT_MEASURED / BLOCKED**。

## 4. 31 类伪造见证审计

归档审查对象：review commit `97e1d2c1e83a4532e2b3bab3bf87cc6a2927f274`；归档 SHA-256 `bdfc801b602a5ed55efe2502f3596010f372ab4b4f6e626a64a7f3e52137f17c`。

三批历史 CLI 矩阵均先包含一个非空合法参考：`bundle_v5`，60 episodes、1,920 steps、状态 `CURRENT_SOURCE_FRESH_REPLAY_MATCH`；随后分别包含 21、6、4 个反例。检查器要求合法参考先通过，并要求每个攻击包被拒绝且含具体 reason。

本次归档值级检查结果：

- 31/31 个 before/after 选定结论依赖摘要不同；
- 31/31 个记录具有具体 `first_changed_value`；
- 30 个结论依赖变更保持 `source_bindings` 不变；
- 1 个 `source_binding` 是刻意的 `source_metadata_attack`；
- 在历史合法参考快照上未发现 no-op。

31 类依次为：`r1_commits_999`、`fast_slow_memory`、`actions_scores_groups`、`learned_joint`、`truth_and_labels`、`support_and_input`、`step_missing`、`step_duplicate`、`step_reorder`、`step_replacement`、`episode_missing`、`episode_duplicate`、`episode_reorder`、`data_hash`、`config_selection`、`seed_split`、`source_binding`、`source_rebound_state`、`source_version`、`attribution_only`、`forged_verification_receipt`、`future_support`、`missing_owner`、`costs`、`selection_access`、`consumer_features`、`fairness_claim`、`nonempty_commit`、`action_consequence`、`corrected_memory`、`contract_freeze`。

重要限制：这是对历史归档的完整性审计，不是对未来统一修复版的 fresh attack generation。五项边界修复后，`corrected_memory`、`action_consequence`，以及可能的 `nonempty_commit`，可能已经成为合法参考中的真值；旧 mutation 届时可能 no-op。正式验收必须从统一冻结 SHA 新生成非空合法参考，再逐个确认 31 个反例确实改变依赖并被拒绝；若某个旧攻击成为 no-op，必须重新构造同类别的非 no-op 反例，而不是沿用历史绿色状态。

完整逐项值证据见 [windows_archived_mutation_values.json](windows_archived_mutation_values.json)。

## 5. Windows/LF 对照

系统 Git 配置为 `core.autocrlf=true`，目标文件未由 attributes 强制工作树换行，因此 `git ls-files --eol` 显示 `i/lf w/crlf`。Windows 工作树原始字节 SHA 与历史 bundle 的 LF SHA 不同；把 CRLF 规范化为 LF 后，关键文件全部与 bundle 记录一致。例如：

| 文件 | Windows raw SHA-256 | LF 规范化 SHA-256 / bundle | CRLF 数 |
|---|---|---|---:|
| `comparison_audit.py` | `b6de6a86e09d925ede6d315ce301d1426a09f8cb5defa811c8634677ff5ff910` | `3082f9f60945e8fd82a51dd8894dbf05e3b03aee28475fbed85e70285b3098f5` | 784 |
| `fairness.py` | `4331c54a9937a4fd1cd798fa59593d59a530eaa524bb1af529ab82264543c34c` | `7ac8ab746e7874e1a75031aa3b254727d58f364d25f9ae88a78c7f601bb433bd` | 393 |
| `dynamic.py` | `b1d98b872757d8cf6587f7f231161ec49038ebba292e2db011b392de17fdd23c` | `9745f4b3285439e49ed5cfe3dd43786e94d0e0ff1fd6dce5bf3cb6280b2e1d32` | 890 |
| `death_test.py` | `e8e1adeec57d42396c556dfcd1d8b4001d89f3dc23d174f3b9c22bb5049f7e42` | `9707a73acf16bd7c7be42184f3283645c7bb2ae98e59cc9cdf3fc8c4546c58ff` | 1,676 |
| `project_two_action_benchmark.py` | `34f9b8e659aa838ceb5ca0deb44555f93c757cf9c01c33acd7a48ac7d554f202` | `e9ff226b107cbecb0aa67fa687a7afc20cbfe715bbfe4968f7569483c1a3931a` | 2,623 |
| death-test config | `7b39c5e397723837befea582c11511ad0ea7335848390fc9dd42285e6c37d7e2` | `4c9f146d42660d144c2f97f7f8af17fad9a1a38ca32260dfc55c39706268bfc8` | 86 |
| dataset config | `51edd7d8089fb8a937c826de5415cc1b34efa6fe3c120c121f2fe83c414d7589` | `c2ce79d46ef9aa1335b092ca06dde0ce170e8c766dce68db63b7b04dde716cb8` | 31 |

准备树的审计工具和测试也呈同样模式：raw SHA 分别为 `869ef9a82e4ca070a7359ba0d90e072e0e76a5efb1bf25490da91c8481ff9ae6`、`1602b872d0f0bf9b23062b7c744000f1a121e96cac8cee35871c22aaa2a3fb0c`，LF 规范化后分别为 `4978aa1860d30a7db04895c989a7c03a27679ca657c642033f206a3b8eacd4de`、`b0be543b14d047276a4c1ab325cdebc4eaa7412a799ffea6963482f00ec51cf1`，与历史 validation summary 一致。

旧 bundle 的 source guard 对原始文件字节取 hash，故普通 `core.autocrlf=true` checkout 会因 CRLF 被拒绝。此次 19 项 Windows 局部测试未调用完整 CLI/bundle source-binding guard，不能标记为历史 fresh replay。若要正式复现旧包，应使用 LF checkout；对新的统一 SHA，应在同一冻结树和明确 EOL 环境中重新生成、再验证 bundle。

## 6. 本次可公平复跑的局部验证

解释器环境：CPython 3.13.5（MSC x64），Windows 11 `10.0.22631`；pytest 9.1.1、numpy 2.5.3、pydantic 2.13.5、scipy 1.18.1。解释器位于 `F:\庞惟\codex\cpswm-w3-five-boundaries-fix-20260912\.venv\Scripts\python.exe`。

| 运行 | 归属 SHA | 结果 | 边界 |
|---|---|---|---|
| 归档 mutation 值级检查 | `329787...` + 只读历史 reference | exit 0；31/31 非 no-op | 归档检查，不生成新攻击 |
| checker witness | `329787...` | exit 0；`71 passed in 1.82s` | 检查器单测，不是运行算法 |
| 公平性局部测试 | `de2c04c...` | exit 0；`19 passed in 73.47s` | 原快照局部工程回归，不是完整 CLI fresh replay |
| 环境采集 | `329787...` | exit 0 | 只读环境记录 |

每项完整 argv、cwd、环境覆盖、起止 UTC 与 exit code 均保存在对应 `*.command.json`；stdout、stderr 和 JUnit XML 未被报告文字替代：

- [windows_environment.command.json](windows_environment.command.json)、[stdout](windows_environment.stdout.log)、[stderr](windows_environment.stderr.log)
- [windows_archived_mutation_inspection.command.json](windows_archived_mutation_inspection.command.json)、[stdout](windows_archived_mutation_inspection.stdout.log)、[stderr](windows_archived_mutation_inspection.stderr.log)
- [windows_checker_71.command.json](windows_checker_71.command.json)、[stdout](windows_checker_71.stdout.log)、[stderr](windows_checker_71.stderr.log)、[JUnit](windows_checker_71.junit.xml)
- [windows_fairness_local_subset.command.json](windows_fairness_local_subset.command.json)、[stdout](windows_fairness_local_subset.stdout.log)、[stderr](windows_fairness_local_subset.stderr.log)、[JUnit](windows_fairness_local_subset.junit.xml)

## 7. 原始结果的可陈述范围

历史 bundle 的 put-back 错误为 P5 `85/1920`（0.0442708333）、AMG `102/1920`（0.053125）、learned `533/1920`（0.2776041667）。SEARCH 三臂均为 `154/1920`（0.0802083333），且分布逐步相同。以上数字仅是被审计对象的原始记录，不构成公平排名，原因包括 owner prior、SEARCH adapter、特征消费、容量、调参和预算均未形成统一科学协议。

CIAV 与长期提交结论也只能按工程边界陈述：全部五项成本为零、privacy 1→1；P5 长期提交为零，故污染贡献质量没有可测分母。

## 8. 正式验收的最小下一步

1. A 发布一个包含已审查五项边界修复的单一冻结 SHA，并给出 tree SHA；不得由 PC-B 本地拼接。
2. 在该 SHA 上冻结公共地图/causal-prefix、owner 先验、容量/计算预算、SEARCH 是否保留原生 head 等用户协议选择。
3. 从该 SHA 重新生成非空合法 reference；记录完整解释器、依赖、Git/EOL、源码摘要和命令。
4. 对新 reference 逐个生成 31 类非 no-op 伪造包；每批先执行并验证合法正例，之后再执行反例。
5. 运行完整 CLI、检查 source binding，并在 LF 与 Windows/CRLF 条件之间明确可比规则。
6. 只有在统一 SHA、完整运行和协议决定都具备后，才可把工程状态升级为正式公平性验收；在此之前保持 `BLOCKED / SCIENCE_NOT_ESTABLISHED`。

机器可读逐项状态见 [fairness_acceptance_matrix.json](fairness_acceptance_matrix.json)。
