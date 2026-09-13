# 电脑 A / 窗口一 R6：实际缓存执行身份修复

## 状态与来源

本轮缓存执行身份修复及要求的限定回归已完成；本轮仅处理 W1 编排、运行时保护及对应测试，包含嵌套工程测试启动路径。不修改七算子、比较算法、阈值、种子、研究框架或科学门。统一验收为 WAITING_UNIFIED_SOURCE；科学门 NOT_PASSED。隔离组装比较回归不构成正式统一验收。

先成功执行 `git fetch origin --prune`，完整读取远端集成分支 `codex/dual-pc-handoff-20260912` 的协作指令及结构二 README；原件保全于 `instructions/`。审核依据为 `97e1d2c1e83a4532e2b3bab3bf87cc6a2927f274` 的 REPORT 和两份原 W1 缓存脚本，原字节在 `review_original/`。

已审核 W1 基线 b6202bec015679461b06056571bd47a5446045b8。旧窗口实际 HEAD e93ea35187e25a4a3ede70f05cf64a2e35216623；逐文件核验 src/tests/tools/apps/configs 完全相同，仅证据和文档有后续差异。旧工作树、审核者工作树均未修改。新工作树 `/private/tmp/cpswm-pc-a-w1-cache-runtime-r6`，独立分支 `codex/pc-a-w1-cache-runtime-r6-20260912`。原生 CPython 3.13.5，使用自身路径的 `uv sync --frozen --offline --extra dev` 环境，不复用其他目录的 editable 安装。

源码固定提交：6fcff45c71eff3f3457d0b6eac6cd872102db89d。起点逐文件 SHA 见 start.json，最终固定代码和环境见 final_fixed_code_and_environment.json；fixed_code_and_environment.json 是保留的中间版本。每次正式阶段 journal 另含完整 source_before/source_after、actual argv、cwd、日志摘要、控制进程/worker 的解释器、模块、实际执行源码观测和测试结果。

## 原缺陷与原样复现

R5 的生产者—消费者顺序、当前 run 比较包绑定、证据输出目录和旧 pytest shebang 已修复；R6 确认这些旧修复有效。本轮保留原 65 项及断言。新问题是：元数据绑定不代表字节码实际执行身份。项目导入器可读取 timestamp 或 unchecked-hash pyc，pytest 也可读取同大小同时间戳的旧 assertion-rewrite 缓存；源文件、节点名称、数量和 JUnit 均不足以识别它们。

`before/` 原样反例：

| 真实案例 | 磁盘来源 | 修复前 |
|---|---|---|
| clean_positive | 版本 0.1.0，断言 0.1.0 | 完成 |
| unchecked_stale | 源码 0.1.0，旧缓存执行 9.9.9 | 错误完成 |
| timestamp_stale | 同大小/同 mtime，旧缓存执行 9.9.9 | 错误完成 |
| clean_negative | 相同源码，断言 9.9.9，清缓存 | 正确失败 |
| seed_real_pytest_cache | 当前通过断言，真实 pytest 生成缓存 | 完成 |
| stale_assertion_accepted（原脚本标签） | 新失败断言源码，旧通过重写缓存 | 错误完成 |
| fresh_assertion_rejected | 与上行同一源码哈希，仅清除夹具缓存 | 正确失败 |

所有案例的源码前后不变。`after_final/` 在最终 6fcff45 使用同两份审核脚本原字节重跑；`after/` 是中间提交的保留结果；正例完成，三个旧缓存路径拒绝；相同失败源码的清缓存对照仍真实失败。原标签不等于结论，状态以 journal 为准。不据此声称以前已经通过的实验被造假。

## 实际修复

`tools/structure_two_pytest_runtime.py` 在初始 conftest 加载前安装进程本地 audit hook（审计钩子）；真实 controller 和 xdist worker 均安装。每次执行本地模块代码前，将实际 code object 与冻结源码直接 compile 的结果、或 pytest 本身从该源码 AST 重写后 compile 的结果比较。预期结果不从 pyc 中读取。普通编译与 AST 断言重写均使用同一份已核验字节，不在摘要检查后重新读取源码来构造预期值；嵌套命令配置也先冻结，再从同份核验字节编译加载。源码摘要和实际代码必须同时匹配；提前执行的本地依赖、没有代码执行观测的模块/测试和不在冻结清单的本地执行均拒绝。

本地范围包括项目包、测试断言、conftest、工具以及影响测试的本地 helper。正确缓存照常可用，pytest assertion rewriting 保持开启；旧缓存被拒绝且原字节留存，不以 -B、不写缓存、全局删除缓存或禁用重写代替身份验证。执行代码观测包括源摘要、实际代码摘要和 plain/rewrite 模式；代码观测是本地诊断，不是外部签名或独立执行认证。

拒绝记录是持久失败状态；测试捕获导入异常或后台线程吞掉异常，不能清除拒绝。伪造重写缓存中的外部 co_filename 也不能利用路径过滤逃过必需测试执行观测。源码及已验证比较包的内容和文件集合冻结规则保持不变，没有扩大排除范围。

同一进程检查不传播到攻击镜像的独立 CLI。W2 在外部源码镜像和恶意缓存中实际执行原生来源保护；本轮真实消费者矩阵验证这些攻击继续运行，而不是删除它们或把其缓存访问关闭。

嵌套审计的 `p0_adversarial_tests` 与 `core_pytest` 原来仍直接调用带 shebang 的 pytest。现在回执的冻结命令明确调用本编排器的 `--native-audit-command`，由相同引擎实际执行本根目录 `.venv/bin/python -m pytest`，保留完整原生测试选择、显式 xdist 插件与 worksteal 调度参数，收集 controller/worker 代码观测和逐阶段日志。版本探测也使用 python -m pytest。旧回执不能证明新命令合同。

只在原生审计明确指定的受控插件策略中允许其既有 suppression=1；普通统一入口仍拒绝未授权的插件抑制与隐藏筛选。本轮的真实嵌套正负回归使用明确标注的最小隔离源码负载，分别通过公开 P0/core 命令，不把它们说成已经运行完整全局工程审计。

## 测试结果与开发过程

最终短矩阵：86 passed、0 failed、0 skipped、0 xfail，pytest 101.14 秒，真实退出码 0，最终缓存/源码/journal 归档含 2233 份文件。包含原 65、新增 20 和 1 项受影响命令合同。原命令记录位于 `r6_execution_records/runtime86_accepted.*`。同 86 项另由正式编排引擎包装完整执行，72.67 秒、退出 0、0 failed/error/skipped，来源前后相同；实际外层运行时观测见 RUN_AREA/r6_runtime86_protected/，不只检查内部子测试的运行时。之前 85 项通过（128.44 秒、2221 文件归档）为单次读取补修前的中间版本，不升级为最终代码证据。最终专属目录在仓库之外，保留仍存在的缓存、代码、日志和 journal；清缓存对照中按测试明确删除的样本不声称仍原样存在。

新增 20 项具体覆盖：

| 回归 | 参数组合 / 数量 | 真实判定 |
|---|---:|---|
| 项目包与本地 helper 旧缓存 | timestamp / unchecked-hash × controller / xdist × 两种位置 = 8 | 同大小同 mtime，旧执行代码拒绝；缓存原字节未删除 |
| 测试断言真实重写缓存 | controller / xdist = 2 | 当前失败源码 + 旧通过缓存拒绝；同源码清缓存仍真实失败 |
| 合法已有项目缓存 | 两种 pyc 模式 = 2 | controller 加两个真实 worker 完成 |
| 测试捕获坏导入 | 1 | 持久拒绝不能被吞掉 |
| 嵌套原生公开入口 | P0 / core = 2 | 各自正常完成与旧重写缓存拒绝 |
| conftest 真实重写缓存 | controller / xdist = 2 | 不同 fixture 行为拒绝 |
| 外来 co_filename、后台线程吞异常、摘要/编译读取竞争 | 各 1，共 3 | 必需执行观测/持久拒绝/同份源码字节检查 |

原 65 中的失败、空矩阵、跳过、隐藏筛选、来源与环境变化、中断、后代进程和重试测试保持原断言并通过；没有把失败/skip/xfail 转换成阶段完成。

115 项原生保护：115 passed、0 failed/error/skipped、0 xfail，4272.18 秒；真实退出码 0，source_before == source_after，源清单 SHA 7d9c0682fc6662d3cb62ae1af2ee95da6fc2667de01d60cd718708cb732abdcf，177 份本地源码执行观测。见 RUN_AREA/r6_native115_accepted/。原 115 项的成功测试输出受 pytest 默认捕获，JUnit 不含子命令输出；为完整保存历史子命令日志，另通过同一正式引擎以 -s 补跑跨目录完整历史测试：1 passed、550.80 秒、退出 0，来源前后相同；原始双流、每个历史子命令的 argv/cwd/exit/stdout/stderr 见 RUN_AREA/r6_history_trace_accepted/。这一补跑不替代或改写原 115 项记录

真实五阶段比较链：五阶段全部 COMPLETED、实际退出码均 0；消费者 77 passed、0 failed/error/skipped，2410.50 秒；全链 3893.96 秒。生成 609.25 秒、比较重算 447.41 秒、归因生成 6.95 秒、归因完整重算 410.49 秒。source_before 与 source_after 相等，最终比较包四个文件及目录集合与冻结清单完全一致；60 个 episode / 1920 steps，语义步骤 SHA a14419c97cc848dfb60610d1df88fd4f7bdc3a87146c396c1741104752756d4e。消费者实际记录了 177 个本地源码执行观测。状态 STAGES_COMPLETED_NOT_AUTHORIZATION，科学门 NOT_PASSED。原目录 r6_comparison_accepted；逐字节封存副本在 RUN_AREA/r6_isolated_comparison_archive/r6_comparison_accepted（RUN_AREA 即 docs/reviews/data/structure_two_unified_acceptance_runs）

三个集合来源/覆盖不同，不将计数相加作为统一通过。真实比较副本基于 W2 `de2c04c3e690dba674850af9c4f7e126dbab910e`，仅叠加本轮两个 W1 工具；自身重新建立原生锁定环境。W2 科学实现不改。比较、归因和测试必须实际消费同一个新包；四类攻击日志在该 run 下，最终再次核验来源、环境以及包内容/完整文件集合。19 个真实攻击夹具归档无错误，其中两份 unchecked-hash 恶意 pyc 保留了 STALE_BYTECODE_EXECUTED 代码字节及 flag=1；只读检查结果见 consumer_fixture_archives/poisoned_cache_preservation.json。其原生 CLI 合法正路径仍完成，未清除攻击缓存。

开发轮失败均保留：一轮原 65 为 64/1，另一轮 84 为 83/1，均在拒绝旧代码后遇到进程退出与 killpg 清理的 PermissionError，不能记为通过。修复清理时先观察/回收 leader，拒绝路径给真实 pytest 有界时间刷新日志；只在已观察到退出后重试信号，仍不可访问或仍存活则硬失败，原中断/后代进程回归继续执行。另有初版新测试 14/4：四个 conftest 样本写了普通 pyc，而 pytest 实际读取的是自己的重写缓存，原测试前提无效；改为真实 pytest 先生成 conftest 重写缓存、同大小/mtime 换成不同 fixture 语义，保留失败原件后重新完整测试。

早期非专属 pytest 临时目录已被全局保留策略清理；一次归档尝试实际 0 文件，原记录保留，不伪装成完整归档。该轮外层双流仍在；最终专属目录重跑的完整内部归档可检查。执行时 helper 字节分别保存在 executed_helpers.tar.gz（中断轮）及 executed_helpers_v2.tar.gz（最终轮），不用格式化后代码冒充原执行脚本。

另补确定性读取竞争反例：`read_race_probe.py` 用当前源码中声明的读取故障注入模拟两次读取之间源内容切换，真实旧缓存仍由 Python 导入。在中间提交 c2e983b，摘要读到新字节，随后预期 compile 读到旧字节，会错误完成；修复后同一真实入口拒绝，源码前后仍一致。这里没有伪造 JUnit、journal 或进程观测。此额外缺口属于本轮自查发现，不倒推旧历史结果造假。为修复它，主动中断两组长验证（真实 subprocess 返回 -2；外层 shell 为 254），保留各自 INTERRUPTED 记录和部分结果，再在 6fcff45 新路径完整重跑。新完成状态只来自后者。

## 保全、失效与交接

原生 115 项夹具以路径清单和 1424 份唯一原字节交付，可还原 57566 个路径文件；文件树中的符号链接单独记录。未装入虚拟环境及 Git 对象目录，未重构测试明确删除的缓存。91 个完整逐夹具原包仍保存在 /private/tmp/cpswm-r6-native115-original-archives，路径和哈希见 native115_fixture_archives/storage.json。

原工作树 e93ea35 和审核工作树未改；本分支旧结果/P0/回执/checkpoint 均保留原字节。final_preservation.json 逐文件核验起点 1554 项：1550 项完全相同，仅 4 个预期旧代码文件改变；另新增一个测试文件。387 份结构二 benchmark 与 4 份 P0 文件均未变化，包含既有版本、历史副本、报告、回执、检查点和原始日志。旧窗口 HEAD 和空工作树状态也已再次核对。

被测完整状态由各 journal 的 source_before/source_after 记录，代码提交固定为 6fcff45。最后追加报告、STATUS_A 和原始证据会改变交付提交及文档清单；不回写旧 journal 的 HEAD/摘要来冒充“最终交付工作树当前性”。这些本地结果证明记录中的被测实现，正式统一源码仍需另行冻结和完整验收。

只有编排、pytest runtime、工程回执的测试启动与对应测试发生代码改变。现有旧证据可按历史来源解释，不能自动成为新源码的当前证据。源清单新增工具/测试及审计启动合同改变后，旧 P0、回执和 checkpoint 不证明新版本；本轮不改旧摘要或 passed 标志。

PR 以审核 W1 快照为比较 base，精确限定本轮差异；不直接向共享集成分支合并。STATUS_A 记录被测源码完整 SHA，报告提交由 Git 历史定位，避免自引用。最终统一版本明确指定后，必须在其固定源码上重算比较/归因和消费者、W1/W3 全矩阵、五类当前结果、历史失败重放及跨目录核验，然后按依赖顺序生成 P0、真实完整工程回执、强制 fresh checkpoint 与 fresh 验证。各分支绿灯不能拼接。

## 精确命令与修改位置

`command_index.json` 汇总外层执行的原始 argv、cwd、环境覆盖、UTC 时间、退出码和双流日志路径。每个 journal 的 state.json 保留真正子阶段 argv、来源前后清单、实际测试运行时观测及日志摘要；负例的非零退出是预期拒绝，外层反例脚本返回 0 仅表示反例收集结束，不等于内部阶段通过。原中断轮的 -2 与 shell 254 分开记录。

长计算均记录 OPENBLAS_NUM_THREADS=1、OMP_NUM_THREADS=1、MKL_NUM_THREADS=1。Python 为本根目录 .venv/bin/python，CPython 3.13.5；pytest 9.1.1，pytest-xdist 3.8.0；逐依赖版本、解释器摘要、pytest 文件摘要与锁文件来源见 final_fixed_code_and_environment.json 和各 runtime contract。未更换科学种子或阈值。

可重复入口为现有 `run_native_protection.py`（原生 115）与 `run_integration.py ... comparison`（真实五阶段）。日志补跑 helper 的实际字节保存在 r6_execution_records/history_trace_helper.py.source.txt。复跑使用一个尚不存在的新 run 名称与匹配工作树环境；禁止以相同目录覆盖封存结果。隔离 W2 底本可由 Git de2c04c3e690dba674850af9c4f7e126dbab910e 恢复，完整源 archive 的本机路径与 SHA 见 isolated_source_archive.json；没有把重复的 460 MB Git 源归档塞入 PR。

| 代码/测试变化 | 影响与整合要求 |
|---|---|
| tools/structure_two_pytest_runtime.py | 所有真实 pytest controller/worker 的本地代码观测；W2 隔离组装已使用同字节工具跑通，合并时保留旧来源/过滤/完成状态检查 |
| tools/structure_two_unified_acceptance.py | 本地源清单、原生审计启动、失败清理；与任何其他窗口的编排修改逐段核对，不覆盖矩阵和依赖顺序 |
| apps/evaluation_runner/run_structure_two_engineering_audit_receipt.py | p0/core 的冻结命令改变；旧审计回执不能用于新版本，统一版本须生成真实新回执 |
| tests/test_structure_two_runtime_cache_identity.py | 新增 20 个真实缓存/worker/嵌套边界；全局 core 原生收集会包含此文件 |
| tests/test_structure_two_engineering_trust_checkpoint.py | 只更新启动合同断言，保留其余检查点断言；整合时与其他窗口的检查点测试差异核对 |

R5 生产者—消费者、环境绑定旧缺陷由原 65 项回归继续覆盖；R6 原始缓存假通过与本轮新增反例已按各自真实入口关闭。它们均是限定范围的工程结论，不是全 CPSWM 穷尽审计。

## 剩余边界

这是源绑定的本地工程执行检查，不是独立进程认证。仍信任 Python/标准库、已安装 pytest/依赖工具链及进程/OS 完整性；没有覆盖任意修改解释器、进程内 hook/原语篡改、所有 OS/存储竞态。对没有本地文件身份的运行时生成代码不单独签发源码证明；必需测试模块仍必须有冻结来源和代码执行观测。保护之前执行的额外本地插件明确拒绝，需要保护时序支持才可作为正式入口使用。

嵌套 P0/core 启动和真实 controller/worker 的最小正负路径已验证；本轮没有重跑完整全局核心工程矩阵并签发新回执/checkpoint。窗口三 R6 的已关闭缺陷不被本轮推翻，其真实投影消费、完整默认联合主干与行动/长期生命周期缺口也不由本轮宣布完成。没有改变科学门或签发消融授权。

交付索引：command_index.json（精确命令）、artifact_inventory.json（本轮逐文件 SHA）、RUN_AREA/r6_execution_records/final_preservation.json（旧文件保全）、final_fixed_code_and_environment.json（被测代码/环境）。PR：https://github.com/goneveitvet240-svg/cpswm/pull/3。
