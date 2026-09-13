# 结构二：窗口一二轮修复、窗口二三三轮修复对抗审核

审核日期：2026-09-12。本次为独立、限定范围的源码与运行审核，不是全系统穷尽证明，不授予科学门或消融授权。未修改、合并或推送三个原窗口的实现。

## 1. 固定版本与结论

| 对象 | 审核 HEAD | 独立工作树 | 结论 |
|---|---|---|---|
| 窗口一二轮 | `816a88b242c24b9c6ace6021bba23e4b5b8b526e` | `/private/tmp/s2-review3-w1.BPdcNo` | 本轮 R1/R2/R3 限定通过；保留可信入口与历史报告可移植性边界 |
| 窗口二三轮 | `bbb9c819f464bd2c62af199fb04e4091ade7232b` | `/private/tmp/s2-review3-w2.NPchtE` | 本轮执行源码保护修复限定通过；不代表比较公平性通过 |
| 窗口三三轮 | `281e88894fca527df1d54018b5053469e8c422d5` | `/private/tmp/s2-review3-w3.UygOrM` | 不通过：发现正式 CORRECT 正路径的新回归；其余修复部分有效 |

三个原工作树审核前后均干净且 HEAD 未变。主工作区既有未跟踪文件保留；这里只新增审核证据。跨窗口结论不能拼成一个已经通过的统一系统。

## 2. 新发现：P1，纠正返回成功，但纠正后的记忆被重建移出长期账本

### 复现与影响

使用真实 `process_execution_feedback` 公共入口及项目文档支持的调用方校准策略；不替换生产方法，不手工修改统计状态。分别在 legacy 十二天历史和正式 direct-P5 十天历史中，纠正一条已提交记录到同位置/不同位置，共四种情形。

| 检查量 | 上轮 `d17e88a` | 本轮 `281e888` |
|---|---|---|
| 返回操作 | `correct` | `correct` |
| 原 revision 移除 | 是 | 是 |
| 新纠正 revision 仍 committed | 是 | **否，四种情形全部如此** |
| 新纠正 revision 的 Hybrid 有效记录 | 1 | **0** |
| 新 revision 写入资格 | 旧版无此机制 | **缺失，查询返回 null** |
| 新 revision 进入 quarantine | 否 | **是** |
| 系统内部完整重跑等价检查 | true | **仍然 true** |

最干净的差分是 legacy 情形：提交数原先 `12 → 12`，本轮 `12 → 11`。正式 direct-P5 也丢失纠正 revision；其总提交数会混入其它历史提升，不能只看总数。本轮该情形是 `3 → 4`，但新的纠正项并不在四条提交之中。旧版 direct-P5 仍有此前的未授权提升问题，绝不能为了修 CORRECT 恢复旧版全套重建行为。

这不是“默认策略尚不自主纠正”的既有研究缺口：本反例已经由合法调用方策略明确发出 CORRECT，并被正式接口接受。问题是已接受的纠正未保住应有的长期贡献。

### 根因

`src/cpswm/system/prototype_spine.py:3162` 创建新 corrected revision；3185–3189 替换观测记录，3200 发布新绑定，3205 返回 CORRECT，3206 触发重建。但这条路径没有为新 revision 建立/转移有依据的 observation write eligibility（观测写入资格）。

新增重建门在 `prototype_spine.py:4827` 对缺失资格的 revision 拒绝提交。这条新门本身用于阻止此前的越权提升，不能删掉；应补齐纠正的合法资格与证据谱系，然后让同一门验证它。

### 修复验收要求

- 在正式纠正事务内定义并记录新 revision 的授权来源、父 revision 和纠正证据关系；不能将所有缺失资格默认设为可写。
- 覆盖 legacy/direct-P5/debt-replay 后的同位置、不同位置、owner 权重纠正，以及纠正后再次撤回、重复反馈、事务回滚。
- 分别断言新旧 revision 的 membership（集合归属）、资格、Hybrid/Dirichlet/RLS/动作及 ledger（账本），不能只断言返回 CORRECT 或内部等价检查。
- 保持十条原写入阻断观测不被撤回/纠正重建间接提交。

证据脚本：`docs/reviews/data/structure_two_three_windows_review_2026-09-12/w3_additional_probes.py`。
本轮与上轮结果：同目录 `w3_current_all_paths.json`、`w3_previous_all_paths.json`。四种纠正路径都以同一脚本、同一解释器、seed 7 复核。

## 3. 窗口三：已修好的部分与仍不充分的证明

独立重跑其 16 个指定测试文件：**252 passed，151.41 秒**。独立执行封存证据脚本，实际确认：

- 四类错误维护依赖载荷，以及“不同运行实例但同状态头”替换均拒绝。
- 真实 P0 中的冒名 callable、错误载荷、字段完备但本次未产生的载荷，均拒绝；不提交 trace，不遗留 pending debt，维护上下文关闭。后两种为隔离上下文层而按脚本显式暂时关闭第一层绑定检查，不能写成生产默认关闭该检查。
- 合法 P0 仍成立：七条状态回执，五个 executed、两个 deferred；不是七算子全部执行。
- 两个正式撤回目标下，原十条写入阻断观测均未提交并仍在隔离区。第一目标 `3 → 4`、新增两条来自未阻断历史；第二目标 `3 → 2`、无新增。未阻断历史能否被重放重新分类的判据仍未定。
- 原本有效的 B 反馈在无关 A 撤回后，可以经 B 自身历史发布绑定定位并撤回；伪造 foreign snapshot 被拒。pending-debt 阻断仍有效。
- 正式 direct-P5 与 debt-replay 的 CIAV planner/executor/operator 各调用一次；CF 输出与 CIAV 实际输入对象/摘要一致；各有十三条验证回执。legacy 对照的 CIAV 调用数仍为零，没有拼接成七算子全运行。

新鲜输出保存在 `w3_round3_evidence_fresh.txt`。其中 `r3_prerepair_*` 是实现者脚本在本轮源码中隔离旧资格门行为的故障注入对照，**不是独立检出旧 commit 的运行**；本审核的真实旧 commit 差分另见 `w3_previous_all_paths.json`。

### P2：独立参考仍不完整

`tests/test_structure_two_formal_revision_lineage.py:115` 虽在修改前保存 journal，但 `:153` 的期望 Hybrid 仍遍历被测系统修改后的 `_committed_events`；`:155` 对 journal 中不存在的项甚至回退读取被测系统当前值。这加强了旧记录权重检查，却没有独立确定“到底哪些记录应该存活”。

本次纠正回归恰好说明危险：纠正记录消失后，内部 `hybrid_equivalent=true`。进一步直接调用新增测试的 `_assert_reconciled_against_journal`，它也在这个真实公共 CORRECT 反例上通过，且未替换任何生产方法。独立脚本与输出为 `w3_journal_oracle_probe.py`、`w3_journal_oracle_result.json`。应从事前原始输入、批准的操作/授权记录推导期望存活集合与统计量；对缺少参考的项失败关闭，而不是取被测结果填补参考。

### P2：被阻断记录获合法授权的正路径没有被实际覆盖

`test_a_write_blocked_observation_is_promotable_once_it_is_authorized`（同文件377–405）没有要求 `blocked_with_grant` 非空；只证明有未阻断提交授权，循环可能零次执行。

本审核将同一正式 direct-P5 历史延长至31个观测日，仍为 `grant_found=false`。这不证明所有输入下该路径不可达，也不证明授权撤销有 bug；它证明现有证据不足以将“阻断不是永久禁令、合法解禁路径已验证”列为已完成。应构造真正触发合法解禁的非空公共正路径，或如实保留未实现/未覆盖状态。

### 其余仍开放

非 P0 节点的 `require_declared_member` 未全面启用；完整粒子/神经提议/RB 主干、额外实例身份、跨运行状态摘要、默认自主撤回/纠正等 G1/G2/G4/G5/G6/G7/G9 未闭合。报告自己保留这些缺口是正确的；252 项全绿不能关闭它们。记录授权基础、事务谱系、正常纠正存活属于工程正确性，不能都转化为让用户选择是否修复的问题；科学阈值、重分类规则和反馈年龄上界才需要保留用户决策权。

## 4. 窗口二：限定接受本轮修复，不扩大科学结论

独立运行三份测试文件，最终 **42 passed，828.33 秒**，无失败/跳过。包含：

- 原21类字段完备伪造与一个真实合法包同批审核；检查每个条目的结果，而不是只看批处理退出码。
- 跨树 A 入口/B 计算代码、mixed bundle（混合包）、预加载旧/外来下游模块、下游源码符号链接、声明 root 不同、绑定后源码漂移、旧 entry code 等14个新拒绝场景。
- 两个正式入口各在错误 unchecked `.pyc` 存在时完成真正的训练/选择/重放正路径。连同21攻击同批里的合法包，本次共执行三条完整正路径；没有提供伪造“期望结果”或跳过重放。

代码绑定包含实际入口 code object 检查、捕获源编译、模块实际 origin/loader/实例跟踪、全过程 checkpoint 与发行前来源核对。此前“执行 B，却声明 A”的主要反例在本轮被挡住。独立按 Git 原字节复核37个旧工件，零差异。

但它证明的是开发诊断的执行来源和重算一致性，不证明公平对比，更不证明方法优越。P5/AMG 的17步差额仍由冷启动规则解释；共同均匀规则下 AMG 也到85。长期提交仍为 `0:1920`，full/fast 动作差异仍零，共同 SEARCH 分布仍1920步相等。支持集的未来信息暴露、信息权限、容量/训练/计算预算以及共同 detected-location SEARCH 的问题都没有由本轮保护代码解决。

已打开数据只能用于开发诊断；不能重新包装为未见测试。不在本次并行负载下用墙钟耗时宣称计算性能胜负。

## 5. 窗口一：源码、历史覆盖、输出保全与检查点

独立执行正式 `run_structure_two_evidence_repair.py --verify-current`，五类存盘结果全部经实际完整重算，最终 exit 0：

| 实验 | 实际状态 | 允许的结论 |
|---|---|---|
| 三臂比较 | `P5_ACTION_SIGNAL_NOT_DETECTED` | 未检出 P5 动作优势 |
| 事后读出 | `POSTHOC_READOUT_DEGENERACY_REMOVED` | 开发性读出退化问题移除 |
| 延期重放 | `PRODUCTION_DEBT_REPLAY_SEMANTIC_EQUIVALENCE_CONFIRMED` | 所测重放语义等价 |
| 因子实验 | `DEVELOPMENT_FACTORIAL_COMPLETE` | 开发性实验完成，不等于科学门通过 |
| 内部 D0 留出 | `INTERNAL_UNSEEN_D0_SIGNAL_NOT_DETECTED` | 未检出内部留出优势；不恢复未见/首用声明 |

再独立执行 `--verify-history`：exit 0，11份 Git 字节、4份源码可恢复、指定 `4103bea` 失败重放实际完成1次且完整工件匹配。最早 `557ff9c` 因缺少 `RegimeStage` 无法导入的事实保留，不以另一个版本的成功替代。对应完成输出为 `w1_five_replays_completion.txt`、`w1_history_replay_completion.txt`；它们保存最终输出段，不是各进程从启动开始的逐字完整终端日志。

两份定向测试文件 **79 passed，2073.09秒**，无失败/跳过；其中新增补修文件单独复核 **53 passed，43.98秒**，两集合有重叠，不相加。覆盖预导入/源码漂移/旧依赖缓存、双历史入口的空表/删除/改名/重复/身份替换、硬链接与符号链接、发布中断和受控竞态、旧版本伪装当前等。输出见 `w1_targeted_tests.txt` 与 `w1_53_supplement_tests.txt`。

数值伪造单元测试先真实计算 genuine，再临时返回该 genuine 隔离比较边界；因此不将单元测试中的这一步误称为第二次完整重算。上面的正式五类入口另行进行了实际重算。结合源代码审查，窗口一原三项根因在其“可信本地解释器/标准库/正式文件入口”范围内可接受；下面的两个边界不应被省略。

已独立逐条比较保全清单19份工件的当前字节、Git `91dbdc5` 字节和摘要，零差异。

在原工作树自己的 `.venv` 执行最终检查点 `--verify ... --no-fresh-recomputation`，**exit 0**。首次人为加了 `PYTHONPATH=src` 被拒；指纹差分只涉及该变量及派生摘要。移除该额外变量后正常通过。这是正确的环境绑定，不是修复失败。此项是当前性复核，不冒充第二次完整 fresh checkpoint 生成；3908项全套工程测试、mypy、Ruff 等封存执行记录不冒充本审核重跑。

检查点自身仍明确保留 Task 7、Task 8 的 FAIL，不建立 Gate-B 已执行、七算子有效或外部方法优越的结论。不能把 `engineering_trust_gate_passed` 解释为这些科学门通过。

### 入口边界补充：不是所有 Python 启动形式都获得“无旧字节码”保证

另建隔离副本 `/private/tmp/s2-review3-w1-entry.sdfpXd`，将来源诊断 CLI 的旧版本预编译为 unchecked `.pyc`，再把磁盘源码恢复为精确 HEAD，正常 `python -m apps.evaluation_runner.probe_structure_two_execution_source` 会执行旧入口标记，同时返回 `frozen-source-compile-no-pyc@1` 来源声明。依赖 cpswm 实际由新启动器编译，但初始 apps 入口 code object 没有像窗口二那样核对。

这不构成本文已验证的五类正式文件路径 CLI 的伪造数值通过反例；窗口一明确把“可信正式入口”列为前提。因此不将它升级为窗口一 R1 修复失败，但必须把保证限定到该前提，不能推广成任意 `python -m`/runpy 启动形式都拒绝旧入口缓存。若要支持那些启动方式，应补入口身份检查及相应正负测试。

同副本以 `python apps/evaluation_runner/probe_structure_two_execution_source.py` 正常文件入口运行，不出现旧标记；两种入口返回的 inventory SHA 相同。原始输出分别为 `w1_stale_module_entry.json`、`w1_trusted_file_entry.json`，磁盘入口 `git diff --exit-code HEAD` 为0。

### 同源码异目录的历史报告可移植性不足

将本次真正完成的历史重放输出交给原 `verify_history_report` 与封存报告比较，会拒绝。`audit_structure_two_evidence_history.py:107` 只归一化历史解包路径，没有归一化错误堆栈中启动器自身的工作树绝对路径。原报告是 `/private/tmp/cpswm-s2-evidence-repair-window1/apps/...`，本次相同源码独立副本是 `/private/tmp/s2-review3-w1.BPdcNo/apps/...`。

仅在内存中将原报告的这一启动器栈帧路径替换为当前目录，原比较器即通过；没有改动磁盘工件、错误类型、数值、覆盖数或源码身份。证据 `w1_history_relocation_boundary.json`。这不否定原目录验证与本次实际完整重放，但说明封存历史报告目前不能直接跨同源码工作树验证。若要支持独立副本核验，应结构化/规范化这类执行本地路径，同时继续绑定真正的错误与来源内容；不能笼统删除所有错误字段。它是可移植性问题，不是已复现的伪造历史通过。

## 6. 总体进展、研究边界与后续顺序

本轮主要提高了证据与执行链可信度；没有把算法效果变好，也没有解决完整比较公平性。保留整个统一研究范围，不因当前失败删减隐藏事件、多人、开放世界未知、可逆归因或具身反馈能力。功能接通/与既有实现重合，本身也不是方法创新证明。

当前先修窗口三的纠正谱系和正路径参考；不要删除写入资格门恢复旧越权行为。对未阻断历史重分类、迟到反馈年龄、其它合法解禁权威等规则，列出明确选项后由用户决定。

所有代码整合后，旧三个分支的证据身份均会变化。必须在统一源码、环境、配置和数据权限上重新运行并使用新版本输出：五类当前结果、窗口二主审计与归因及对抗矩阵、窗口三正常/异常事务链、P0 manifest、工程回执、完整 fresh checkpoint。不可改旧哈希、覆盖旧结果或拼接各分支绿色日志。

本审核未穷尽任意进程内篡改、Python/stdlib/第三方库、OS/所有竞态、独立历史托管以及全部科学门。任何“全部问题已修完”或“七算子与系统主干已全面正常配合”的结论，现有证据均不支持。
