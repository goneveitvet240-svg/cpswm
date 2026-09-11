# 窗口二第三轮：执行来源约束与真实 CLI 对抗复验

日期：2026-09-11。工作树 `/private/tmp/s2-comparison-audit-window2-20260911`，分支 `codex/s2-comparison-audit-window2-20260911`。起始 HEAD 正是审核提交 `f022f1901f07bc0afa43b7c2b3fc5397d6367517`，工作区干净；没有后续用户修改需要迁移，没有 reset、覆盖、合并或推送。已完整读取主工作区独立第二轮复核报告及 `w2_cross_source_result.json`。

**范围状态：PARTIAL_SOURCE_THREAT_AUDIT。** 本轮实现和验收针对声明 A 源码而通过 Python 导入 B 实现的漏洞，以及下述具体来源攻击。Python/stdlib、进程完整性和独立历史托管等未覆盖边界仍保留，不写“全部来源威胁已解决”。本轮不修改生产七算子、数据划分、冷启动规则、比较预算、0.02 科学门槛，不进行 router calibration，不打开新种子数据。

**指定矩阵实际通过：42 passed，0 failures / errors / skipped，809.32 秒。** 修复代码与测试提交为 `bf48fd3aacf31e8da62dcd17596a644f49167031`。两个 CLI 的完整正路径均 exit 0；14 个新增来源异常场景全部失败关闭；正确来源下，旧 21 种完整伪造攻击仍全部拒绝，真实包通过。完整审计仍按上述边界标 PARTIAL，而不是把本轮回归绿等同于全部来源安全。

## 1. 修改前真实反例：exit 1 中藏着伪造包通过

从本窗口 A 原始 CLI 启动真实完整重放，`PYTHONPATH` 指向专门建立的 B 副本 `/private/tmp/s2-w2-round3-cross-source-B/src`。B 只将诊断 `_p5_readouts` 中 `_committed_events` 的读数改为 999；A 的原真实包和旧 R1 完整伪造包保持原字节。

| 项目 | 本轮修改前实际观察 |
|---|---|
| 声明 CLI 根 | `/private/tmp/s2-comparison-audit-window2-20260911` |
| 相同环境的加载探针 | 模块 `__file__` 与 `_p5_readouts.__code__.co_filename` 均位于 B |
| A 诊断文件 SHA | `83e02ea5ae86bf1244312d654ce73df7b88f65c4bf242d63c82a7f8128b438f3` |
| B 诊断文件 SHA | `4cdad9cbee851f7f5b492867ffd62ec512854baf429e11313a1c529024180444` |
| 实际重放 | 60 episodes / 1920 steps，三臂；没有提供参考答案或 mock 重放 |
| 真实包 | `REJECTED`，提交计数与错误加载的实现不符 |
| 完整伪造包 | **`CURRENT_SOURCE_FRESH_REPLAY_MATCH`** |
| 批处理退出码 | 1；它不代表伪造被拒绝 |

[修改前实际结果](data/structure_two_comparison_audit_window2_round3_2026-09-11/evidence/cross_source_before_result.json) 保留完整 argv、解释器、PYTHONPATH、加载探针、两侧源码摘要、逐包状态及运行前后文件摘要。[原始 CLI 日志](data/structure_two_comparison_audit_window2_round3_2026-09-11/evidence/cross_source_before.log) 是直接调用 A CLI 的输出；加载路径探针是同一环境的独立进程，未冒称为 CLI 内部记录。修改后日志则由可信入口直接记录执行模块身份。B 的 SHA 与复核者 B 的 SHA 不同是副本修改文本不同，不影响本轮仅改变该诊断读数的反例。

这再次证实的是来源验证缺口，不是历史实验采用过 B，也不证明原始开发诊断数据造假。

## 2. 根因与代码修改

旧入口先按 Python 导入规则加载 `cpswm`，再对从 CLI 路径推导出的根目录做磁盘绑定。正确运行的强重放只能证明“实际加载实现”的输出一致；磁盘绑定不能单独证明该实现就是被声明的 A 字节。

新增 `apps/evaluation_runner/_structure_two_audit_source.py`，由两个 CLI 在任何项目模块导入之前，从各自旁边的明确路径读取字节并直接编译加载。它只依赖 Python 标准库，不通过 `cpswm` 导入自己的保护逻辑，也不问已经错载的模块是否可信。

执行链如下：

1. 检查实际入口 code object 的文件位置与源码编译结果；拒绝入口位置错配及已编译旧入口与当前声明源码不一致。
2. 拒绝启动前已在 `sys.modules` 的任何 `cpswm` 模块，包括仅预导入下游依赖、或者同一路径旧模块已导入而磁盘恢复成新源码的情况。复用已预加载模块不是正式 CLI 的支持模式；描述性 `analyze` 仍可独立导入，但不能调用强验证签发通过。
3. 捕获 `src/**/*.py`、`configs/**/*.json`、两个 CLI 和保护模块的源字节。符号链接源码失败关闭，不允许单个下游文件跳出该源码树。
4. 安装优先的本地导入保护，对每个 `cpswm` 模块检查 PathFinder 实际解析的 origin 是否是当前根目录对应文件；不是检查 PYTHONPATH 的字符串内容，也不是只检查顶层诊断模块。
5. 不执行解析器返回的缓存 loader；所有本地模块都从捕获的字节直接 `compile` / `exec`。即使 `.pyc` 是 Python 通常信任的 unchecked-hash 缓存，也不用它。每个模块记录源文件 SHA 和实际编译的 code object 摘要。
6. 在输入绑定后、重放结束及签发结果前检查来源文件集合/字节、加载模块集合、对象身份、spec/loader/origin 和 package path。来源漂移、未跟踪模块或替换 loader 都不能退回文件自洽检查。
7. **重放声明的 source_bindings 必须逐项等于加载器捕获并执行的字节摘要。** 该对账由 CLI 侧保护器做，独立于 `cpswm` 自报的绑定；避免把几个时点的磁盘检查误当作实际执行字节与声明的关系。
8. 来源条件成立后仍执行上一轮完整步骤、状态、动作、评分、audit 和 attribution 的新鲜重放比较。两个 CLI 在输出肯定结果时附带 `execution_source` 身份清单；来源异常时不输出任何逐包肯定认证。

主入口 `--repository-root` 的语义是**当前 CLI 的执行源码根兼数据根**，规范化路径必须与 CLI 所在检出相同，不是另一个可自由指定的数据根。另一个副本即便文件相同也不能用该参数声称执行来自那里；应明确运行那个副本自己的 CLI 并使用相应 `src`。

本轮沿用原始比较算法。仅修改两个诊断 CLI、独立来源保护、诊断来源绑定/验证 schema（3），新增来源攻击测试。没有直接合入窗口一保护、修改窗口三或假定其他窗口已通过独立审核。

## 3. 测试矩阵与肯定路径

新增测试通过真实 Python subprocess 调用生产 CLI。故障注入只操作 pytest 的独立副本/进程，不改主工作区、原始 bundle 或生产七算子算法。新源攻击包使用最终第三轮源码重新构造，使用并重新核对最终 A 的 source_bindings，重算步骤、summary 和 attribution；不会拿旧 v2 的来源过期来代替语义攻击。

| 新测试 | 数量 | 验证重点 |
|---|---:|---|
| A CLI + B 修改诊断 | 3 | 主 CLI 的伪造包；归因单独伪造包；归因真实/伪造混合批次；逐包不得肯定 |
| 仅下游文件指向修改后的异树实现 | 2 | 两 CLI 在顶层诊断未变时拒绝源码符号链接 |
| repository-root 错配 | 1 | 主 CLI 检查的根与执行的根不得不同 |
| 同路径已导入旧诊断，随后恢复当前源码 | 2 | 不只比较导入模块的路径或当前磁盘 SHA |
| 仅预加载异树的修改版下游实现 | 2 | 顶层诊断尚未导入，也必须拒绝 |
| 运行中来源漂移 | 2 | 用 profile 在真实输入绑定返回后修改副本来源；不是 mock 重放或注入答案 |
| 已编译旧 CLI 对应磁盘新源码 | 2 | code object 与声明入口字节的关系 |
| 合法新鲜包 + 故意放入恶意 unchecked-hash pyc | 2 | 两 CLI 实际完整重放通过，并证明执行当前源字节、未使用陈旧缓存 |
| 原有 26 项 | 26 | 原 20 项 + 上轮 6 项；其中仍含 21 种同步重算依赖的完整伪造攻击和合法正包 |

共 42 个 pytest 项目，其中来源新增 16 项；最终执行结果见本报告的完成记录。不能把批次 exit 1 单独算作攻击通过或拒绝：每个来源攻击都检查输出中没有逐包 `CURRENT_SOURCE_FRESH_REPLAY_MATCH` 或主入口 `verified`。上一轮混合矩阵应是合法包单独通过、21 个攻击单独拒绝，整体 exit 1；合法包单独验证则必须 exit 0。

实际结果与可审阅入口：

| 实际运行 | 结果 | 证据 |
|---|---|---|
| 主 CLI 完整新鲜正路径，包含陈旧 pyc 干预 | exit 0；1920 步；161 个本地模块从当前源字节编译 | [逐条命令、身份与输出](data/structure_two_comparison_audit_window2_round3_2026-09-11/evidence/source_tests/full_positive_stale_pyc_main.json) |
| 独立归因 CLI 单独合法包，包含陈旧 pyc 干预 | exit 0；`CURRENT_SOURCE_FRESH_REPLAY_MATCH`；60 episodes / 1920 steps | [逐条命令、身份与输出](data/structure_two_comparison_audit_window2_round3_2026-09-11/evidence/source_tests/full_positive_stale_pyc_attribution.json) |
| A 主 CLI + B 修改源码 + 当前绑定伪造包 | exit 1；`LOCAL_IMPORT_ORIGIN_MISMATCH`，无肯定记录 | [main.json](data/structure_two_comparison_audit_window2_round3_2026-09-11/evidence/source_tests/main.json) |
| A 归因 CLI + B 修改源码，单独伪造 / 混合输入 | 均 exit 1；项目模块加载前拒绝，无逐包肯定 | [单包](data/structure_two_comparison_audit_window2_round3_2026-09-11/evidence/source_tests/attribution_single.json)、[混合](data/structure_two_comparison_audit_window2_round3_2026-09-11/evidence/source_tests/attribution_mixed.json) |
| 其余 11 个来源异常场景 | 均拒绝；错误分别定位下游链接、预导入模块、入口 code、根目录或运行中源路径 | [16 项来源结果索引](data/structure_two_comparison_audit_window2_round3_2026-09-11/validation_and_source_version.json) |
| 旧 21 种攻击在当前源码重新构造 | 21 拒绝；真实包肯定；该混合批次整体 exit 1 | [完整矩阵](data/structure_two_comparison_audit_window2_round3_2026-09-11/evidence/r1_matrix/adversarial_matrix.json) |
| 原有 26 + 新增 16 | 42 passed；0 skipped | [测试日志](data/structure_two_comparison_audit_window2_round3_2026-09-11/evidence/tests_final.log)、[JUnit XML](data/structure_two_comparison_audit_window2_round3_2026-09-11/evidence/pytest.xml) |

所有成功记录中的实际加载源 SHA 已逐项核对为修复提交中的源字节。完整肯定路径记录 161 个模块；这表示来源身份覆盖，不表示 161 个模块或七算子均被证明具有方法收益。ruff check / format（5 个 Python 文件）、诊断模块 mypy 与提交钩子检查均通过，日志位于 evidence。

修改前使用的原包输入也在最终代码下再次跑了同一跨源命令：exit 1、`LOCAL_IMPORT_ORIGIN_MISMATCH`，见 [原输入修改后日志](data/structure_two_comparison_audit_window2_round3_2026-09-11/evidence/cross_source_after_original_inputs.log)。这条日志用于前后对照；当前重构包的三个来源攻击和当前 21 项语义攻击才是排除“仅旧绑定过期”的最终证据。

陈旧缓存正路径的 A 副本与最终代码树源字节完全相同，只有诊断 `.pyc` 被替换成执行即抛错的旧缓存；随后源文件恢复为当前字节。真实完整通过及加载身份记录共同说明当前源码确实被执行。该测试不修改解释器或第三方库，也不伪造新鲜参考。

## 4. 产物版本与实际命令

本轮统一使用 `/Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/.venv/bin/python`（Python 3.13.5）。最终目录：`docs/reviews/data/structure_two_comparison_audit_window2_round3_2026-09-11/`。

首次 `bundle_v3` 在加入“执行字节对声明绑定”的额外直接检查前生成，1920 步语义与旧包一致，但不是最终源码验收包。它及原日志保留；最终源码重新生成 `bundle_v3_final`，不修改先前来源字段使旧包变绿。两次都使用原固定配置/种子/模型选择和相同比较预算。

最终 [audit.json](data/structure_two_comparison_audit_window2_round3_2026-09-11/bundle_v3_final/audit.json)、[attribution.json](data/structure_two_comparison_audit_window2_round3_2026-09-11/bundle_v3_final/attribution.json)、[逐步包](data/structure_two_comparison_audit_window2_round3_2026-09-11/bundle_v3_final/steps.jsonl.gz) 的 399 项 source_bindings 全部与 `bf48fd3` 提交字节一致；元数据在 [validation_and_source_version.json](data/structure_two_comparison_audit_window2_round3_2026-09-11/validation_and_source_version.json)。生成发生在代码提交前，但源字节已经固定，提交钩子没有改写它们；随后文档/证据提交不在此绑定集合中。

前两轮目录内的 **37 个留存文件** 与 `f022f19` 原字节完全一致，见 [保全清单](data/structure_two_comparison_audit_window2_round3_2026-09-11/preserved_previous_artifacts.json)。最终代码拒绝旧 v2 及初版 v3 的记录见 [过期包拒绝日志](data/structure_two_comparison_audit_window2_round3_2026-09-11/evidence/previous_bundles_final_source_rejected.log)。旧包的拒绝本身不证明跨源攻击已经修复。

新源攻击使用过的完整 R1 输入另存于 `counterexamples/current_source_r1/`，与真实测试输入字节相同；`counterexamples/foreign_diagnostic.patch` 是 B 修改副本相对最终 A 的精确差异。它们是**故意伪造的测试材料**，不是合法结果。源码摘要和包摘要都在上述验证索引中。`reproduce_before.py.txt` 保留本轮实际执行的修改前脚本原文，需在 f022f19 的独立副本与新的 B 路径复现，不能把它当作当前版本肯定路径。

```sh
cd /private/tmp/s2-comparison-audit-window2-20260911
AUDIT_PY=/Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/.venv/bin/python
R="$PWD/docs/reviews/data/structure_two_comparison_audit_window2_round3_2026-09-11"
export PYTHONPATH="$PWD/src"

"$AUDIT_PY" apps/evaluation_runner/run_structure_two_comparison_audit.py \
  --output "$R/bundle_v3_final" --timing-repeats 1 --timing-episodes 1
"$AUDIT_PY" apps/evaluation_runner/summarize_structure_two_comparison_audit.py \
  --bundle "$R/bundle_v3_final"

S2_AUDIT_BUNDLE="$R/bundle_v3_final" \
S2_AUDIT_EVIDENCE_DIR="$R/evidence/r1_matrix" \
S2_SOURCE_EVIDENCE_DIR="$R/evidence/source_tests" \
"$AUDIT_PY" -m pytest -n 3 -q -o addopts='' \
  --junitxml="$R/evidence/pytest.xml" \
  tests/test_structure_two_comparison_audit.py \
  tests/test_structure_two_comparison_audit_verification.py \
  tests/test_structure_two_comparison_audit_execution_source.py
```

生成器拒绝覆盖；复现时换用新的空输出目录，环境变量指向那个包。两个 CLI 的逐条实际 argv、解释器、PYTHONPATH、cwd、退出码与输出分别保存在来源测试证据目录。重放从头重新训练及验证选择；没有提供外部参考、硬编码原有错误数或以攻击常量黑名单拒绝输入。

## 5. 未覆盖边界与科学结论

- 本地原始 CLI、Python/stdlib、第三方库和进程完整性是信任前提。没有防御能够任意 monkeypatch 编译器、内存中函数/对象、guard、自报模块 metadata 或直接伪造 stdout 的敌手；这不是一个沙箱或独立认证服务。也未对非 `cpswm` 名称下的第三方/stdlib 遮蔽攻击做完整审核。
- 捕获源码及检查磁盘并非 OS 级原子快照。短暂改写后在检查之间恢复的每次文件事件，不保证都被发现；本地模块执行的是捕获的字节，声明绑定必须与它一致。配置/历史数据文件的任意竞态和底层文件系统/内核攻击未穷尽测试。
- 本轮可控漂移测试发生在真实输入绑定之后、昂贵重放之前。代码也在执行结束与签发之前检查，但没有枚举每个七算子内部时点的文件变更攻击，不能声称所有执行时序都已覆盖。
- 不允许正式 CLI 复用预导入项目模块、从任意其他数据根运行或使用链接到另一源码树的源码文件。这是明确的执行来源约束，不是删除结构二研究能力；需要嵌入式/动态插件模式时须另行定义来源协议。
- 当前源码重放不是独立历史托管、正式科学确认或比较公平性证明。未来支持集暴露、共同 detected-location SEARCH、信息权限与容量/训练/计算预算差异仍按原报告登记；完整结构二能力和用户对新分布/目标/预算的决定权保留。

原数据已打开，只能用于开发诊断。[实际新旧对账](data/structure_two_comparison_audit_window2_round3_2026-09-11/semantic_reconciliation.json) 显示全部语义步骤及 summary 相等：P5/AMG/learned PUT_BACK 仍为 85/102/533，17 步差额均由冷启动规则解释，53 个无 owner 估计步骤在共同均匀规则下错误从 53 变为 36，故 AMG 全批变为 85；长期提交直方图仍是 `0:1920`，P5 与 fast 动作差异 0，三臂 SEARCH 分布相等 1920 步，历史动作链 180/180 一致。语义 SHA 仍为 `d32b9d7bd2ff4963d8a71939fe752b260806e8775b692d602ac4588205f70c76`。验证代码不硬编码这些观察值，科学门仍未因来源保护获得通过。

## 6. 窗口一/三交接

- 旧 v2 `audit.json` 的来源绑定、旧归因及其通过记录不能代表当前来源保护版本；旧文件保留，原开发数值不是因此被改写。旧源码跨树 R1 反例及原 21 攻击证据也保留。
- 本轮初版 `bundle_v3` 不代表最终源码；只有最终新目录及与其对应的两个入口/攻击日志用于本轮限定验收。
- 本轮最终包绑定两个 CLI、来源保护、全部本地 src/config 和指定历史文件。合入窗口一/三后，即便不改诊断算法，文件集合或内容变化也会使绑定过期。
- 整合顺序：先代码与测试；完成最终组合源码后，新目录重新生成主审计和归因，两个 CLI 完整新鲜验证，重跑 21 完整攻击与来源矩阵，再更新下游最终证明/报告。不能拼接各窗口的绿色日志或改旧哈希修绿；不自动合并或推送。

代码提交文件清单：

- `apps/evaluation_runner/_structure_two_audit_source.py`：独立、只用 stdlib 的可信启动与捕获源编译器。
- `apps/evaluation_runner/run_structure_two_comparison_audit.py`：启动保护、根目录语义、执行字节对绑定检查、肯定输出身份。
- `apps/evaluation_runner/summarize_structure_two_comparison_audit.py`：同样的启动保护和强验证签发约束，导入式描述分析不获得签发权限。
- `src/cpswm/system/evaluation_operations/structure_two_comparison_audit.py`：仅增加保护文件绑定及 schema 3，没有改生产算子或诊断读数规则。
- `tests/test_structure_two_comparison_audit_execution_source.py`：16 项真实 CLI 来源异常与完整正路径测试。
