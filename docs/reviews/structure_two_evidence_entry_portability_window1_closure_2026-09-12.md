# 窗口一第二轮补修封存闭环（2026-09-12）

本轮只处理实际入口身份与历史报告跨目录边界，保留此前源码保护、固定历史覆盖和安全发布机制。已审核起点为 `816a88b242c24b9c6ace6021bba23e4b5b8b526e`；补修源码与测试固定于 `05c78af2a38e07e0171c5352bf4ab9b9da3124d2`。工作树 `/private/tmp/cpswm-s2-evidence-repair-window1`，分支 `codex/s2-evidence-repair-window1-20260911`，实际 `.venv` 为 Python 3.13.5。本文件是检查点生成之后补齐执行结果的交付记录，不是检查点所绑定的前置报告；前置报告为同目录 `structure_two_evidence_entry_portability_window1_2026-09-12.md`，生成检查点后不再修改。

## 两项补修与真实正负路径

| 问题 | 修改前真实入口结果 | 修复 | 修改后真实入口结果 |
|---|---|---|---|
| 旧入口 unchecked pyc 获得当前来源 | 磁盘恢复精确当前入口后，`python -m apps.evaluation_runner.probe_structure_two_execution_source` exit 0，执行旧标记并返回旧策略来源证明；正常文件入口无旧标记 | 签发前将实际入口帧和启动器自身完整代码对象与冻结源码重新编译结果比较，检查支持入口身份；依赖仍从冻结字节编译 | 相同攻击 exit 1，stdout 为空，报 `formal bootstrap executing entry differs from frozen source`；合法文件和合法 unchecked 模块 spawn 均 exit 0，实际默认语义 0.5，策略 `frozen-source-and-entry-compile@2` |
| 完整历史重放后因根目录不同而拒绝报告 | 同源码独立根目录执行历史 `--verify`，完成历史输出后 exit 1，报 `historical source audit differs from fresh snapshot/replay checks` | 仅在采集时规范化已知 traceback 文件路径及已知 ImportError 来源尾部，保留真实异常正文、堆栈及历史 commit；报告绑定审计源码并严格 JSON 比较 | 目录 A 完整生成与目录 B 完整验证均 exit 0；9 项报告字段攻击、实际源码替换、重哈希历史记录替换均 exit 1 |

前后复现完整原始输出在新证据目录 `validation_logs/before_reproductions_complete.stdout.log.gz`、`after_entry_reproductions.stdout.log.gz`；跨目录逐子命令输出在 `cross_root_full_raw.stdout.log.gz`。子命令 argv、cwd、stdout、stderr、exit_code 均保留。跨目录完整执行日志包含 13 个真实子进程（2 个正例、11 个预期拒绝），实际完整失败数值重放 3 次：A 生成、B 合法验证、B 换源验证；后者数值仍相等，来源不同必须拒绝。9 项报告篡改经过真实子进程调用正式报告比较实现，输入是已真实完整重放的报告；它们不声称各自重复完整数值实验。实际换源和换历史记录攻击经过完整历史 CLI。

历史报告不删除 traceback，不忽略错误字段。异常类型/正文、堆栈行内容、来源摘要、历史 commit、覆盖数量、重放完成布尔值、整数与布尔混淆以及无关路径变化均有拒绝回归。11 份记录 Git 字节核验完成，4 份记录来源可恢复，指定 `4103bea` 数值重放完成 1 次；最早 `557ff9c` 仍真实导入失败，保留缺失 `RegimeStage` 的完整诊断。本工作树新报告与独立目录参考报告字节相等。

## 回归覆盖和原保护保留

原 79 项加新增 36 项实际 **115 passed，0 failed / skipped / xfailed**。新增覆盖文件、模块、runpy、文件与模块 spawn；无缓存、合法时间戳缓存、合法 unchecked 缓存；错误 unchecked、同长度同 mtime 旧缓存、包含不同代码的外来缓存；外来/字符串直接启动、执行期间改盘、启动器执行后冻结前改盘；全部九个正式入口逐一旧模块拒绝和合法文件通过。程序不删除 pycache 以取得通过。

原五个反例及写入边界继续由原回归执行：late_import（提前导入再改盘）、stale_pyc（陈旧依赖缓存）、empty_history、renamed_history、hardlink。两个历史 CLI 同时覆盖清空、删除、改名、替换来源、重复/冲突的清单与相容报告；安全写入覆盖合法新建、已有目标、硬链接、文件/目录符号链接、逃逸、检查后替换、校验/发布失败清理，且逐样本检查真实历史字节前后相等。五个生成 CLI 和聚合器均继续调用原共用安全发布实现。本轮没有重写它，也未放宽上述断言。

开发过程中的失败同样保留：首次旧版本复现副本缺少冻结别名文件而失败；早期缓存夹具构造及启动测试适配有 4 项失败，修复后才固定源码并进行 115 项整组验证。探索日志单独注明记录完整性限制；不能将其代替正式完成日志。最终完整重算均在固定源码之后。

## 版本、保全与消费者

五份新产物位于 `benchmarks/structure_two/evidence_entry_portability_2026_09_12/current_v0_4/`，分别为 `structure_two_p5_three_arm_death_test_v0_4.json`、`structure_two_p5_readout_posthoc_diagnostic_v0_4.json`、`structure_two_p5_debt_replay_confirmation_v0_4.json`、`structure_two_p5_readout_prior_factorial_v0_4.json`、`structure_two_p5_unseen_d0_holdout_v0_4.json`。新历史报告为同级上层 `historical_source_audit_v0_3.json`；科学协议版本未变，v0.4 仅表示证据产物版本。

五份正式生成（发布前各自完整再算）与发布后统一完整再算均 exit 0。剔除根级 source_binding、evidence_context、content_sha256 后，科学字段与已审核 v0.3 严格 JSON 相等。`confirmatory=false`、`previously_unseen_established=false`、`first_execution_established=false` 和非独立托管边界保持，D0 为开启后重放；其旧状态枚举不建立新的未见证明。

保全清单为新证据目录 `preserved_reviewed_evidence.json`，210 条均对 Git 816a88b 核验：**208 条保留原路径原字节，2 条可变当前索引另存原字节**。后两条是 P0 清单和 v0.5 兼容性审核，分别保存在 `reviewed_p0_manifest.json`、`reviewed_v05_compatibility_audit.json`；原当前路径按原生顺序更新。旧 v0.2、v0.3、11 份历史记录、旧报告、旧工程回执及旧检查点未覆盖。旧结果可作为对应源码的历史结果，不能冒充新源码当前结果或仅手改摘要。

新工程链位于 `benchmarks/structure_two/engineering_trust_checkpoint_2026_09_12_v0_3/`，包含 `engineering_audit_receipt.json`、`engineering_audit_logs/` 和 `engineering_checkpoint.json`。消费者需要更新五个 DEFAULT_OUTPUT、聚合器的 CURRENT_DIRECTORY、历史报告及回执/检查点路径；这些代码引用已在本分支调整。

| 新结果 | content_sha256 |
|---|---|
| `structure_two_p5_debt_replay_confirmation_v0_4.json` | `33f3cef0121dbc8de6ca53cbab51d36f70c5cfc985e7cce62a6c0fd78bebc820` |
| `structure_two_p5_readout_posthoc_diagnostic_v0_4.json` | `8d43504dc17a4a74f091257896dbbc78ca79ac3d46cf355839a60c76899991fd` |
| `structure_two_p5_readout_prior_factorial_v0_4.json` | `1ce276245a79e9dc6731d2115fcabab348687960a383d1a527a3d66134af71b4` |
| `structure_two_p5_three_arm_death_test_v0_4.json` | `08b91336062c50b09c047286774f2b616709ca4684003de8106a23ac68865ef2` |
| `structure_two_p5_unseen_d0_holdout_v0_4.json` | `e89647a61000fb10633c1972de47018251fda57f2adf414355d15d919a1656b3` |

## 依赖绑定与验证记录

执行源码清单：`d845c1216cd7ddb5295c6e311dcec5ccc826c3d4990788478c8bb448a2dea1a4`。生产装配清单覆盖全部 src 和环境锁，摘要：`914b77705a89e389b8800d56ba33e17bb54222b8e5924930ef87374e69abd1b8`。P0 manifest 摘要：`c87357cee49ff7a712f615773ed66b422cd2e506a810483a412898e0d155af12`。真实工程回执内容摘要：`9b7aa855ac1c9d4f39c888b4372019dc1b899b4b128b032cf43066bbec236338`。审计前后环境相等，摘要：`bba78a7a15b6c7549995038d89482580b105b702aeaa1775b5e5118eb60b563d`。没有用摘要一致替代实际加载语义检查，也没有伪造根目录或环境指纹。

实际命令及完成结果见新证据目录 `validation_logs/commands.jsonl`，原始 stdout/stderr 是同目录无损 gzip；原生工程审计另保留 20 个原始流。可用 `gzip -dc 路径` 阅读。完成命令的 argv、cwd、起止 UTC、返回码、耗时、流摘要均记录；命令表及完整修改文件清单在同目录交付。随机运行标识用于区分运行，不被当作科学数值或稳定语义身份。

原生审计十个命令全部 exit 0。核心测试实际 **3944 passed、1 skipped、1 xfailed**；P0 对抗 **121 passed**；mypy 310 个源码文件、Ruff lint/format（664 个文件）、compileall、冻结离线环境与差异检查通过。原核心命令依既有顺序排除下游检查点测试文件，生成后另行完整执行。沙箱限制导致的一项 skip 在宿主权限下以同一虚拟环境和原始断言重跑通过；同时复核既有 RLS xfail，得到 **1 passed、1 xfailed、0 skipped**。该 xfail 不被隐藏或计作通过，也不改变科学结果。

最终强制 fresh 检查点生成 **exit 0**，2026-09-12 04:42:28–04:50:47 UTC，499.09 秒；对已生成文件再次完整 fresh 验证 **exit 0**，04:50:55–04:59:25 UTC，509.72 秒，两次均没有禁用重算。检查点文件 SHA-256 为 `8a657e219807d68eed4b6a4e8150d1aef4464e74aee6cab59ede2cc99f898793`，内容摘要为 `2694ce984d278dbcb06080581126696ca276c81ae8d3b7b546b9cdc46d9386cc`。

下游检查点测试实际 **15 passed，0 failed / skipped / xfailed**（10.31 秒），覆盖重哈希授权、失败命令冒充成功、环境/可执行文件替换、旧回执配新清单、禁用 fresh 生成以及当前性正例。完整 fresh 验证之后，快速当前性 **exit 0**；已审核旧检查点冒充当前 **exit 1**，报 `engineering checkpoint drift or forged positive output`。这里的快速检查只追加检查当前性，不代替已经完成的两次完整重算。

最终保全与科学字段复核 exit 0；日志完整性命令 exit 0，检查此前 24 条完整记录的 48 个压缩流及原生审计的 20 个流。包括该检查命令自身后，当时命令账本共 25 条、50 个 gzip 原始流，已逐项核对其解压后摘要。两次开发失败与预期的旧检查点拒绝均如实记录，没有混入最终正向通过统计。文件与摘要仅支持本地字节完整性，不建立独立执行或托管真实性。

新检查点 `engineering_trust_gate_passed=true`，但 Task 7、Task 8 的 task_gate_passed 均 false，`seven_operator_ablation_authorized=false`、`external_validity_established=false`、`recorded_execution_authenticity_established=false`、`independent_custody_established=false`，`integration_requires_new_checkpoint=true`。所有被绑定源码/测试自 05c78af 后保持不变，前置报告摘要与封存文件相符。本轮两个补修项及规定的验证均已完成。

封存时第一次 git commit 被 Ruff 提交钩子拒绝（exit 1）：六份未绑定的日志辅助脚本存在导入顺序、换行/分号与长行格式问题。修复格式后重新检查通过，没有跳过钩子。实际执行过的七份辅助脚本原文（包括未改动的记录器）保存在 `validation_logs/executed_helper_sources_before_format.tar.gz`，文件 SHA-256 `afbee71231c2832a830bb841965e0350b1c8f556a4f377993fa4b72497ca5a99`。逐份去除顶层 import 后 AST 完全相等；导入整理没有修改任何实验或验证断言。`post_format_boundary_check` exit 0，真实检查辅助脚本 Ruff、历史字节/科学字段、完整日志、检查点当前性以及检查点字节未变。生产源码、测试、配置、P0、回执及绑定报告均未变化，所以没有用旧回执搭配新清单。辅助脚本属于执行日志附件，不是 P0 的代码/测试输入。最终账本共 **26 条完成命令、52 个 gzip 原始流**，逐项摘要核验通过，另有原生审计 20 个原始流；首次提交钩子失败在此保留，不视为验证通过。

## 整合后的失效与重算清单

本轮改变共用启动器、历史审核入口、证据版本模块、五个 P5 默认输出路径、诊断入口、P0/回执/检查点生成器、根 conftest 及四个测试文件。完整路径清单另附。未修改科学配置、七算子实现、比较算法、动作语义、种子、阈值、正式基线或长期提交准则。

与窗口二、三的潜在重叠在 `apps/evaluation_runner/structure_two_source_bootstrap.py`、证据版本模块、上述默认路径、根 conftest 和工程生成器/测试。整合时需保留双方功能并重新测试，不直接覆盖。源码或测试/工具链输入变化会使本轮当前来源、P0、回执和检查点失去对整合版本的当前性；旧文件仍保留为对应分支证据。三个分支绿色结果不可拼接为整体通过。

在统一代码版本和匹配真实环境上，依次重跑：相关入口/历史/写入回归与各窗口新增测试；五类当前结果生成及完整重算；固定历史记录与指定失败重放及跨目录验证；P0；完整核心与真实工程审计矩阵；强制 fresh checkpoint 生成及完整 fresh 验证；当前性与检查点对抗测试。整合后任何被绑定输入再次改变，都需重建受影响的下游链。本窗口不自动合并、推送或签发消融授权。

## 剩余边界

来源核对以可信 Python 解释器、标准库和进程完整性为前提，不是独立执行认证，不覆盖任意进程内替换 guard、伪造帧、解释器/操作系统控制或外部托管真实性。受支持入口的通过不为任意外部调用代码提供来源认证。跨目录保证针对同源码与同语义诊断，仅规范化明确已知的路径；不同环境导致的真正错误内容变化会拒绝。最早历史依赖确实不可导入，不能借当前依赖声称恢复；本地 Git 仍不足以证明首次、未见或独立托管。

没有需要用户选择的新增科学问题；保留已有科学失败与 xfail。工程通过不表示方法有效、科学门通过、全部七算子有效或 CPSWM 已被穷尽审计。
