# 窗口一：跨窗口变更影响与统一版本验收准备

本文件为只读影响分析，记录时间 2026-09-12T06:01:08Z。已完整阅读主工作区 `docs/reviews/structure_two_three_windows_round4_adversarial_review_2026-09-12.md`，并核对窗口二、三实际工作树、差异、交付报告、验证脚本与测试文件。没有合并分支、修改其他窗口、运行长实验或替用户选择科学协议。

**统一版本状态：WAITING_UNIFIED_SOURCE。** 本文件中的命令是统一工作树明确指定且实际源码固定后的验收要求；本轮没有运行这些完整矩阵，不把旧报告的通过数字记成本轮通过。不把诊断可重放、工程检查点通过或脚本 exit 0 当作方法有效、完整公平性或科学门通过。

## 1. 实際读取的三个来源

| 窗口 | 实际工作树与 HEAD | 本次读取状态 |
|---|---|---|
| 一 | `/private/tmp/cpswm-s2-evidence-repair-window1`；`2a5f45947952e8d725009141716b42ac879434f3` | 已审核封存起点；本轮新准备目录是工作中的未跟踪新增，不把它解释为旧源码被修改 |
| 二 | `/private/tmp/s2-comparison-audit-window2-20260911`；`45850dc680cb83169c3108d6a1a5455f7e069457`；分支 `codex/s2-comparison-audit-window2-20260911` | `git status --short` 为空；与 R4 审核 HEAD 相同 |
| 三 | `/private/tmp/s2-w3-native`；`281e88894fca527df1d54018b5053469e8c422d5`；分支 `codex/s2-backbone-operators-w3` | 有已存在的修改/未跟踪源文件、测试和报告；还出现 `docs/reviews/data/w3_repair_r5_20260912T055846Z/`。HEAD 不能代表实际实现，不能把 R4 快照自动视为最终来源 |

读取时窗口三的 tracked 修改为：`src/cpswm/system/prototype_spine.py`、`src/cpswm/system/structure_two_production_system.py`、`tests/structure_two_backbone_wiring_probe.py`、`tests/test_project_two_revision_action_trace.py`、`tests/test_structure_two_backbone_operator_wiring.py`、`tests/test_structure_two_execution_interface.py`、`tests/test_structure_two_formal_revision_lineage.py`。未跟踪生产/测试文件为 `src/cpswm/system/structure_two_semantic_identity.py`、`tests/structure_two_revision_oracle.py`、`tests/test_structure_two_w3_operator_acceptance.py`、`tests/test_structure_two_w3_revision_acceptance.py`、`tests/test_structure_two_w3_supplement.py`。R4 报告与 R4/R5 data 目录也未提交。本窗口不清理、不提交这些修改。

为避免把 HEAD 当作全部来源，本次读取还将每个窗口 `src/tests/apps` 下 Python 与 `configs` 下 JSON（实际脚本遍历四个目录并选择 `.py/.json`）映射为相对路径→SHA-256，再对按键排序、紧凑 JSON 的整个映射计算摘要。窗口二 752 文件，映射摘要 `2f6bdbd239b40f9ca73b4218620c0bd5f46adba8c1d1525669af7854031accde`；窗口三 756 文件，映射摘要 `4d58fa94dba1da3913bde07782fbfa1c4f8b9adb47e83e72e93866f8ebca57f3`。这是一次只读观察的标识，**不是完整环境清单、冻结授权或统一来源**，也不同于 R4 报告中只覆盖 558 个 src/tests 文件的摘要；窗口三后续工作会令此观察过时。

复查来源命令：在各自目录执行 `git rev-parse HEAD`、`git status --short`、`git branch --show-current`、`git diff --name-only 09eb4d48e1c11082e90ca18332d04333e6b5b47a`、`git ls-files --others --exclude-standard`。下面的重叠集合取后两个命令的并集，含未提交/新增代码，而非只比较两个已提交分支。

## 2. 变更文件 → 受影响结果 → 必须重跑的验证

命令组在第 5 节完整列出。任何实际来源清单变化都先使旧工件的“对应当前源码”身份失效；这不否定其历史实验事实。数值是否发生变化，必须由新鲜重放判断，不能由 Git diff 大小或算法文件未直接相交推断。

| 变更文件/依赖位置 | 直接影响与传递影响 | 统一树必须重跑 |
|---|---|---|
| W2 `src/cpswm/system/evaluation_operations/structure_two_comparison_audit.py`；新增 `structure_two_comparison_fairness.py` | 真实 train/validation 访问次序、匹配消费回执与实际 packet 核对、消费探针、公平性字段；主包 schema 4 的当前身份改变。该源码也在 W1 全 src 清单内，令 W1 五类旧 current 与工程绑定过时，即使它们科学数值最后不变 | W2 新目录生成、主 CLI 全重放、归因 CLI 全重放；原 42＋新增 16 所在全部四测试文件，完整 21＋6 伪造矩阵逐包拒绝和同批合法包接受；W1 五类、P0、工程矩阵与 fresh checkpoint |
| W2 `apps/evaluation_runner/summarize_structure_two_comparison_audit.py` | 缺失 owner 的 uniform 开发归因只改 habit，要求 SEARCH 顺序不变；完整 attribution 与状态重放绑定。绝不将共同先验对照替换正式 AMG 规则 | 归因生成与 `--verify`；主包与归因的合法全量包、错误 pyc 两个公开入口正例及伪造负例；五类当前来源重建 |
| W2 `_structure_two_audit_source.py`、`run_structure_two_comparison_audit.py`（相对共同起点新增/改变，本轮公平性增量未改） | 两个入口实际加载代码、预加载、陈旧入口/pyc、声明 root、本地依赖位置和执行期漂移约束。W1 guard 与它不是同一个验证状态实例 | W2 执行来源测试、两个真实 CLI；由新鲜独立子进程运行，不在 W1 已加载 cpswm 的进程内导入它们来取得来源身份 |
| W3 `src/cpswm/system/prototype_spine.py` | 写资格、正式纠正父链、修订事务/回滚、共享反馈 engine、统计重建、身份概率输入、公开低层/高层修订的行为。直接改变 P5 与 W2 实際执行核心；非空授权、修订后语义和 oracle 初态仍需补齐新缺口 | W3 原 16 文件、三个新增验收文件、邻接组与 automatic-regime 组；R4 新缺口扩展矩阵；五类 P5 重放；W2 主包/归因/全部伪造；P0/工程/fresh checkpoint |
| W3 `src/cpswm/system/structure_two_production_system.py` | 装配实例与实际成员身份、共享依赖、P0/direct/debt/legacy/多轴反馈入口、恢复前装配核验；与 W1 文件级重叠 | W1 来源/发布/历史回归；W3 五公共路径×方法替换、额外实例、正负接线及故障恢复；五类与 W2 完整生成/重放；P0/工程/fresh checkpoint |
| W3 `src/cpswm/system/structure_two_execution.py`、`src/cpswm/world_model/grounded_search/ciav_opceu_loop.py` | 执行反馈与 CIAV/OPCEU 交互，负观测、same-location、identity-switch 证据送入下游。改变 W2 逐步状态/归因及各 P5 路径 | execution-interface、CIAV negative layers、operator causal/coverage、P0 fault、direct/debt 路径；全部新当前结果与比较包，不用原 1920 步状态冒充新实现 |
| W3 新 `src/cpswm/system/structure_two_semantic_identity.py` | 运行标识和语义标识区别；纠正授权 `basis_sha256` 中随机内部 ID 的传递映射。当前 R4 已知纠正后不稳定反例 | 同/异位置、连续纠正、撤回后的跨运行等价；错误引用、真实质量/位置变化不等价；原始账本/授权完整性先验证，不能删除授权字段求稳定 |
| W3 新 `tests/structure_two_revision_oracle.py` 与 revision-acceptance、operator-acceptance、supplement；已有 wiring probe/lineage/revision trace 测试变更 | 独立参考的已修订初态、冻结资格与父链、故障检出；测试更改本身不能证明生产问题已解决 | 冻结前已合法纠正、多代纠正后冻结正例；授权人失效、伪造父链负例；八类既有故障继续检出；完整核心测试重新实际执行并绑定最新测试清单 |
| W1 `structure_two_evidence_versions.py`、五个 P5 模块 `DEFAULT_OUTPUT`、聚合/历史 CLI、工程回执/检查点消费者与 P0 排除配置 | 统一版本须使用新证据版本/目录；当前 v0.4 目录已经封存，旧默认路径不能写入。版本号是证据产物版本，不改科学协议 | 先将新路径与消费者作为整合实现固定，再执行 W1 原保护测试、五类真实生成和逐类验证、两条历史审核入口及跨目录完整重放 |
| `pyproject.toml`、`uv.lock`、解释器/虚拟环境或敏感环境改变 | W1 装配传递绑定含全部 src/cpswm 和两份锁；工程回执绑定真实 Python/工具/关键模块/分布/环境。W2 较窄 source_bindings 不能单独充当环境证明 | 新冻结环境中的原生核心/静态/工具链矩阵、新 P0、真实回执、fresh checkpoint 生成和 fresh 验证；不得复制其他树的环境指纹 |

只改测试也会使工程测试证据失效；只改入口也会使执行来源失效；只改结果/报告也可能使 P0 或检查点绑定失效。不能把以上三类变化都简化成“实验科学数值没变，所以原绿灯可继续使用”。

本轮新增 `tools/` 中的验收编排及对应 `tests/` 回归也属于新实现。现有 P0 的 code scope 是 `src/**/*.py`、`apps/**/*.py`，**不直接包含 tools**；其 test contract 则覆盖全部测试/fixture 与根 conftest。因此本轮新增测试会令旧 P0、旧真实工程回执和旧 checkpoint 的当前性失效，编排自身还必须由本轮明确的源码前后清单直接绑定，不能宣称旧 P0 已替它背书。旧 v0.4、历史、P0、回执、checkpoint、日志保留原字节；本轮只准备统一验收，**不重新生成本分支 P0/工程回执/checkpoint**，也不把旧检查点当前性失效误说成旧数值被推翻。

## 3. 文件级重叠与实际加载注意事项

相对共同起点 `09eb4d48e1c11082e90ca18332d04333e6b5b47a`，在 `src/apps/tests/configs` 和根 `conftest.py/pyproject.toml/uv.lock` 的已变更与未跟踪集合中：

- W1/W3 唯一同名交叉为 `src/cpswm/system/structure_two_production_system.py`。
- W1/W2、W2/W3 暂无同名文件交叉。此结论是上述时刻的文件集合交集，**不是运行依赖互不影响**。
- W1 在该重叠文件的增量仅是装配清单传递源码必须是工作树内本地普通文件、路径各级拒绝符号链接，以及 `pyproject.toml/uv.lock` 拒绝符号链接。W3 改动是装配/实例/恢复前行为。整合冲突处理必须同时保留两者，不能整文件选 ours/theirs。
- W1 的 bootstrap 库不读取旧 pyc，校验实际入口及 bootstrap 的 code object 与冻结源码，包含全 `src/cpswm`、`configs/**/*.json`、`apps/**/*.py`、环境锁及 `conftest.py`。W2 自有 guard 也在项目导入前编译冻结源码，校验其两个入口与实际 import selection。不要无证据地统一/重写这两套已通过 guard；编排应逐个新进程调用现有入口。
- W1 支持的 file/module/runpy/spawn 启动与 W2 入口来源测试都必须保留。新编排不应自行构造一个普通库调用然后把外层文件哈希叫“正式入口已执行”。
- W1 根 `conftest.py` 有已审核的 `PYTEST_DONT_REWRITE` 启动例外；普通测试断言仍重写。整合后 W2/W3 测试会在该实际启动环境运行，不能用 `--confcutdir` 绕过根入口、替换导入或关闭保护求通过。
- W2 老复跑脚本使用主工作区解释器与 `PYTHONPATH="$PWD/src"`，W3 老脚本类似。它们是历史运行命令；统一验收使用明确统一工作树自身 `.venv/bin/python` 与匹配环境。不要把它们的 `PYTHONPATH` 搬进 W1 检查点阶段。最终收据记录的环境与 fresh/checkpoint-currentness 执行环境必须一致。

新版本路径准备是尚待统一源固定前完成的整合工作，不是绕过保护：`run_structure_two_evidence_repair.py` 只有 `--generate-current/--verify-current/--verify-history`，**没有 `--output-dir`**；五类结果由模块 `DEFAULT_OUTPUT` 和 `evidence_versions.CURRENT_DIRECTORY` 固定，安全发布拒绝已有目标。历史 report、receipt、checkpoint 与 P0 的消费者及循环排除项也有固定路径。应先在统一树中明确新证据版本、路径和所有消费者引用，保全被替代的可变索引字节，固定代码后再生成。不能在生成中临时猴子补丁默认值，或通过覆盖旧 v0.4 来节省整合修改。

## 4. R4 明确尚未关闭的范围

窗口一证据链修复是**限定通过**，本轮不据此重构 guard/历史/publication。窗口二诊断/检查限定通过，但比较公平性和科学有效性未建立。窗口三的 R4 已有 252、105、82、44 等组可保留为原范围执行事实，不能合为全系统通过；三个新增反例必须由窗口三补修并给统一树补上正负断言：

| 新缺口 | 统一验收不可缺少的真实正负后置条件 |
|---|---|
| 低层公开 `core.apply_event_revision_outcome` 返回 CORRECT，但父子长期贡献都消失 | 在合法 legacy 十二条历史中至少含已知第四条异位置反例；直接公开入口的成功必须对应新记录存活、资格及 Hybrid/统计生效；拒绝恢复原状态；如延期则有明确可追踪结果。扩展 legacy/direct/debt、同/异位置、owner mass、重复/乱序、失败/中断/重试。不能删除写资格门强制提交 |
| 冻结前已有合法纠正，零后续操作却被 oracle 误拒 | 合法纠正后冻结新 journal、零变更验证通过；多代纠正后再冻结通过；冻结完整原资格、父链、既有操作与证据；授权人失效及伪造父链拒绝。不能从被测最终成员集合补参考 |
| 两次相同纠正后语义摘要不同 | 相同外部 feedback/action/输入和各自合法 snapshot，纠正后语义相同、执行随机 ID 可不同；同/异位置、连续纠正、撤回都覆盖；授权派生摘要内部身份映射一致；错误引用/真实语义变化应不等价，原授权/账本完整性仍严格核验 |

`w3_new_boundary_probes.py` 如实输出 JSON，**它 exit 0 不是通过**：当前 R4 反例字段包含 `new_committed=false`、`oracle_accepts_unchanged_corrected_state=false`、`after_semantic_equal=false`。统一验收必须检查成功/拒绝/延期的真实后置条件或新增失败会退出非零的生产测试，不能将该脚本整体 exit 0 作为 W3 验收绿色阶段。

此外继续保留 G1/G2/G5/G6/G7/G9 未完成项：纯 adaptive-only 同位置/负观测通用慢写、完整粒子持久状态与后缀修订/全回放、神经全输出与 log-q、每粒子条件统计、默认自主修订策略和所有算子数学分支均不能由现有用例代替。G5 已选字段、持久父/快照/统计引用管理、真实 evidence→typed interface、生产后验与反馈接线有**可直接推进的工程**，不得把全部欠项推给用户。

科学待决由用户决定，本窗口不冻结：地图/地点权限及未知位置评分、正式共同缺省先验、SEARCH 动作时机/原生读出/观测预算、可用信息字段与强对照能力、训练/容量/推理总预算及多目标选参、普通与长记忆/歧义/隐藏事件/未知人物/迟到反馈挑战分布；完整 proposer 架构与训练工件、条件统计聚合、正式 resampling/rejuvenation、adaptive-only 证据独立性/候选寿命、默认自主修订证据或行动损失模型。科学未定不阻止已授权工程修复，也不授权打开新确认集。

## 5. 统一来源固定后的真实命令矩阵

以下均从**明确指定的统一工作树**执行，使用该树 `.venv/bin/python`。命令文件/参数已对照当前入口源码；`OUT`、`HISTORY_REPORT`、`CHECKPOINT` 只是编排提供的全新路径变量，不是当前存在的统一目录。先完成第 3 节所列新证据版本和消费者引用的整合，然后冻结源。每一阶段完整保存 argv、cwd、环境、前后来源清单、stdout/stderr 和真实退出码；不得把命令摘录当原始完整日志。阶段失败或中断立即保留失败状态，后续绿灯不能覆盖它；再次执行必须新 attempt/新产物路径，不复用半成品。

### W1 入口、历史与发布保护

```sh
.venv/bin/python -m pytest -o addopts= -q --confcutdir=. \
  tests/test_structure_two_evidence_versions.py \
  tests/test_structure_two_evidence_supplement.py \
  tests/test_structure_two_entry_portability.py
```

这三个已存在文件覆盖原 79＋36；其中真实跨目录用例为 A 生成、B 完整验证、B 源码改变后完整重放拒绝，并包含错误/身份/数量/完成声明篡改。统计必须记录统一树本次实际数量，不以“115”作为强行凑齐目标。

### W2 比较、归因和完整伪造矩阵

```sh
.venv/bin/python apps/evaluation_runner/run_structure_two_comparison_audit.py \
  --repository-root "$PWD" --output "$OUT/comparison" \
  --timing-repeats 3 --timing-episodes 2
.venv/bin/python apps/evaluation_runner/summarize_structure_two_comparison_audit.py \
  --bundle "$OUT/comparison"
.venv/bin/python apps/evaluation_runner/run_structure_two_comparison_audit.py \
  --repository-root "$PWD" --output "$OUT/comparison" --verify \
  --timing-repeats 1 --timing-episodes 1
.venv/bin/python apps/evaluation_runner/summarize_structure_two_comparison_audit.py \
  --bundle "$OUT/comparison" --verify
```

正式归因验收必须看到 `verification_mode=CURRENT_SOURCE_FRESH_REPLAY`、`fresh_replay_performed=true`、合法包 `CURRENT_SOURCE_FRESH_REPLAY_MATCH`。`--check-file-consistency` 不可替代它。

```sh
S2_AUDIT_BUNDLE="$OUT/comparison" \
S2_AUDIT_EVIDENCE_DIR="$OUT/w2_complete_forgery" \
S2_SOURCE_EVIDENCE_DIR="$OUT/w2_execution_source" \
S2_FAIRNESS_EVIDENCE_DIR="$OUT/w2_fairness_forgery" \
.venv/bin/python -m pytest -o addopts= -q --confcutdir=. \
  tests/test_structure_two_comparison_audit.py \
  tests/test_structure_two_comparison_audit_verification.py \
  tests/test_structure_two_comparison_audit_execution_source.py \
  tests/test_structure_two_comparison_fairness.py
```

四文件均已存在于窗口二实际树。生成的新包必须传入，不能让环境回落到历史 v2/v3 包。原完整伪造 21 类＋公平性完整伪造 6 类需逐条状态核对，不能只要求混合批次 exit 1。真实合法包与两入口投毒旧缓存的合法全量正例必须继续通过。并行回归中的耗时不作性能比较；如保留性能描述，计时生成与并行矩阵分开，环境/线程限制原样记载，不凭本机争用结果排名。

### W3 正常/异常修订与主干协作矩阵

以下文件均已在窗口三实际树中核实存在。当前集合只能覆盖 R4 已声明的范围，**还必须添加第 4 节三个新缺口的测试**；不虚构尚未交付的新文件名，不把 R4 旧集合当新缺口关闭。

```sh
.venv/bin/python -m pytest -o addopts= -q --confcutdir=. \
  tests/test_structure_two_backbone_operator_wiring.py \
  tests/test_core_prototype_spine.py \
  tests/test_structure_two_production_system.py \
  tests/test_structure_two_execution_interface.py \
  tests/test_structure_two_adaptive_runtime.py \
  tests/test_structure_two_adaptive_runtime_adversarial_round1.py \
  tests/test_structure_two_adaptive_runtime_adversarial_round2.py \
  tests/test_structure_two_p5_direct_trace_probe.py \
  tests/test_structure_two_p5_debt_replay_confirmation.py \
  tests/test_structure_two_backbone_counterexample_regressions.py \
  tests/test_structure_two_late_counter_evidence_chain.py \
  tests/test_structure_two_operator_causal_matrix.py \
  tests/test_structure_two_ciav_negative_observation_layers.py \
  tests/test_structure_two_p0_maintenance_fault_injection.py \
  tests/test_structure_two_formal_revision_lineage.py \
  tests/test_structure_two_operator_coverage_matrix.py
.venv/bin/python -m pytest -o addopts= -q --confcutdir=. \
  tests/test_structure_two_w3_revision_acceptance.py \
  tests/test_structure_two_w3_operator_acceptance.py \
  tests/test_structure_two_w3_supplement.py
.venv/bin/python -m pytest -o addopts= -q --confcutdir=. \
  tests/test_project_two_feedback_revision_loop.py \
  tests/test_project_two_revision_action_trace.py \
  tests/test_orrer_event_revision.py \
  tests/test_ccrr_context_conditioned_regime.py \
  tests/test_hybrid_ledger_durable_log.py \
  tests/test_project_one_automatic_regime_loop.py
```

窗口三必须以其新交付指明新缺口 node IDs、实际正路径与拒绝断言，并纳入统一测试清单后，才可完成此阶段。所列旧数量 252/105/82/44 是历史报告范围，统一运行记录实际 passed/failed/skipped/xfail 数；缺关键正负场景为 `BLOCKED_REQUIRED_MATRIX`，不能由核心总数掩盖。

### 五类当前结果、历史失败重放与跨目录

```sh
.venv/bin/python apps/evaluation_runner/run_structure_two_evidence_repair.py --generate-current
.venv/bin/python apps/evaluation_runner/run_structure_two_evidence_repair.py --verify-current
.venv/bin/python apps/evaluation_runner/audit_structure_two_evidence_history.py \
  --output "$HISTORY_REPORT" --recompute-first-failure --recompute-failed-replay
.venv/bin/python apps/evaluation_runner/audit_structure_two_evidence_history.py \
  --verify "$HISTORY_REPORT"
.venv/bin/python apps/evaluation_runner/run_structure_two_evidence_repair.py --verify-history
```

跨目录真实完整重放由 W1 portability 用例执行，不能用仅规范化字符串测试替代。五类必须全部生成、发布前复核并再次完整新鲜重算；同一来源快照贯穿。历史仍有 11 个固定 Git 字节记录、4 个可恢复源快照、1 次指定 `4103bea` 失败结果数值重放；最早 `557…` 的真实 `ImportError/RegimeStage` 保留，不能补现代依赖冒充恢复成功。不能由可变 ID/覆盖数决定是否省略必需重放。

### P0 → 完整工程矩阵 → fresh checkpoint

```sh
.venv/bin/python apps/evaluation_runner/generate_p0_checkpoint_manifest.py
.venv/bin/python apps/evaluation_runner/run_structure_two_engineering_audit_receipt.py
.venv/bin/python apps/evaluation_runner/generate_structure_two_engineering_trust_checkpoint.py
.venv/bin/python apps/evaluation_runner/generate_structure_two_engineering_trust_checkpoint.py \
  --verify "$CHECKPOINT"
.venv/bin/python -m pytest -o addopts= -q --confcutdir=. \
  tests/test_structure_two_engineering_trust_checkpoint.py
```

这里默认路径必须已在最终统一源码中指向新版本。真实 engineering-audit CLI 自身承担 P0 对抗、完整核心、mypy、Ruff lint/format、compileall、uv frozen/offline、git diff 及当前/历史 P5 矩阵；不能把预先填好的 passed 行代替运行。生成和再次验证 checkpoint **不传 `--no-fresh-recomputation`**。完整 fresh 均完成后可再做只读当前性检查，且明确它不是第三次全量重算。若统一树仍需 compatibility audit 等其他 P0 绑定输入更新，按原依赖顺序先做完再生成 P0。

外层编排只记录与约束原生阶段，不能新增自签授权、改变 `CURRENT_LOCAL_TOOLCHAIN_STATE_ONLY` 或将汇总状态传递为 Task 10 消融授权。它应要求全部必需阶段实际完成且前后来源/环境清单不漂移；旧 P0/receipt/checkpoint、不同树的结果、未完成重放或中断残留均不得形成整体通过。

## 6. 统一整合的保全与交接清单

1. 保留 W1 v0.2/v0.3/v0.4、11 份历史记录、所有历史报告、P0 原字节备份、工程回执、检查点与完整原始日志。R4 核验的 210 项是 208 原路径＋2 个可变索引明确备份路径，不夸大为 210 原路径从未改变。
2. 保留 W2 v1/v2/v3/v4 以及 122 份原字节和既有开发归因；新包使用独立目录，不能修改旧来源字段续期。
3. W3 当前为 HEAD＋未提交工作，必须由其负责窗口交付实际修改与来源清单，再由明确的统一树固定实现。文件复制/合并顺利不是验收证据。
4. 固定统一树时先解决 production_system 同文件增量、新结果目录/消费者、P0 循环排除、实际虚拟环境；将三个新增缺口的矩阵加入必需清单。任一项尚未到位，保持等待/阻塞状态。
5. 三个窗口合并会让旧结果的当前来源身份、旧 P0、旧工程回执和旧 checkpoint 失去整合版本适用性。统一版本需要全部五类、W2 两入口、历史与跨根、W3 事务/主干矩阵、完整工程矩阵和新 checkpoint 的 fresh 生成及 fresh 验证。
6. 命令中断、阶段失败、重放未完成必须保留原始日志和 attempt 状态；之后的成功是新的执行记录，不抹掉失败。不得用旧绿色结果填补中断阶段。

本窗口准备工作与统一版本最终验收分开：此文件完成变更影响、真实入口参数与待补矩阵核对；**统一验收仍 WAITING_UNIFIED_SOURCE，科学门未通过**。本文件不推翻 R4 对 W1 已通过保护的有界结论，也不宣称全 CPSWM 已穷尽审核。
