# 窗口一补修封存后检输出（2026-09-11）

状态：三项补修和全部验收运行已完成；本报告与匹配的代码、工件、日志一同封存到窗口一分支。

本轮验证跨越本地 2026-09-12；文件名保留 2026-09-11 任务版本标识，真实开始/结束时间以 UTC 原始记录为准。

本文件是固定输入报告 `structure_two_evidence_repair_window1_supplement_2026-09-11.md` 的后续输出，
不作为该轮 checkpoint 的输入，避免自引用。修复根因、原始反例、实际入口正负路径、安全与历史
边界见固定报告；这里只记录最终封存结果、可复现命令和交接。

工作树：`/private/tmp/cpswm-s2-evidence-repair-window1`；分支：
`codex/s2-evidence-repair-window1-20260911`；原生 `.venv` Python 3.13.5。
已审查起点：`91dbdc57968071be29976d1a7b99de51d9288cdd`。
执行源码修复：`3dce0485234f941fc9520e52b1fe9d8f14ded892`。
加强完整审计命令契约测试：`2c2def2f4bcbba855b57cb05f87b731f145ae30a`。
后者只修改测试文件，不改源码、apps、配置、环境锁及五类 v0.3 的来源身份。

## 已保留的历史与未封存候选

旧 11 份 Git 历史副本、五类 v0.2、旧历史来源报告、旧 checkpoint/receipt 共 19 份均与
91dbdc Git 字节相等；旧 P0 原字节另存。核验清单为补修目录的
`preserved_reviewed_evidence.json`，执行记录为 `validation_logs/commands.jsonl` 中
`preserved_and_new_final`。五类 v0.3 排除根级来源、证据上下文和内容摘要后的全部字段与 v0.2
相等。字节比较不是数值重算声明；数值重算对应真实生成及工程矩阵的存盘完整核验。

首轮后检为 221 passed、1 failed：旧断言只查看 xdist 参数位置，未适配前置统计选项。
修复后断言检查完整命令元组，没有删除测试、弱化断言或改变实际执行命令。
首轮候选在 `candidate_before_command_contract_fix/`，并在
`validation_logs/preseal_command_contract_candidate.tar.gz` 中保留原始逻辑路径和全部 24 个文件。
它的 P0、回执、checkpoint 和绑定报告仅作候选历史；不得作为最终当前通过依据。

## 最终验收记录

最终 P0 manifest SHA：`dc7067c2769af765f71ba62f12dd543221905af108eb7ea0121355571ca89fc6`。
最终审计回执 content SHA：`ce51f3f93096d04b8f02584e58a7307ce9a188fd0f20852ce6dee1e26b3b5c79`。
最终 checkpoint content SHA：`bb620a6813f0986a7a0aa7703231280c1bd8fdfe1d0623db542ed4a15b9b2ef1`。

第二轮原生工程矩阵于 2026-09-11 15:24:56–16:03:04 UTC 完成，十条命令均 exit 0；
执行前后 P0 摘要及实际环境指纹相等。原生回执保存每条命令的完整 argv、实际 cwd、执行文件、
环境覆盖、时间及 stdout/stderr 哈希。最终命令复现索引为 `validation_logs/completed_commands.md`，
原始记录为 `validation_logs/commands.jsonl`，两者均在补修工件目录中。

| 最终阶段 | 实际结果 | 原始记录 |
|---|---|---|
| 五类存盘完整重算 | 5 类完成，exit 0；15:24:57–15:37:26 UTC | 原生 `p5_evidence_current` |
| 历史正式审核 | 11 Git 字节、4 来源可恢复、1 次指定完整失败重放；exit 0 | 原生 `p5_evidence_history` |
| P0 对抗矩阵 | 121 passed，0 failed/skipped/xfail | 原生 `p0_adversarial_tests` |
| 完整核心套件 | 3908 passed、1 skipped、1 xfailed、0 failed/errors；1531.81 秒 | 原生 `core_pytest` |
| mypy | 310 个源码文件无错误 | 原生 `mypy_src` |
| Ruff lint/format | 均 exit 0；663 文件格式正确 | 原生 `ruff_lint` / `ruff_format` |
| compileall、冻结离线 uv、Git 差异 | 均 exit 0 | 原生对应三条命令 |
| 真实沙箱及已知 RLS 用例补跑 | 1 passed、1 xfailed、0 skipped/failed；12.62 秒 | `sandbox_and_known_xfail_final` |
| fresh checkpoint | 完整重算 exit 0；16:05:28–16:13:56 UTC，508.24 秒 | `checkpoint_generation_final_fresh` |
| 新 checkpoint 当前性 | exit 0；在完整 fresh 完成之后执行 | `checkpoint_currentness_final` |
| 旧检查点冒充当前 | 已审查旧版及首轮候选均 exit 1，拒绝 drift/forged positive output | `reject_reviewed_checkpoint_final` / `reject_precontract_candidate_final` |
| 历史字节及 v0.3 字段复核 | 19 份旧工件及旧 P0 保留；五类科学字段相等，exit 0 | `preserved_and_new_post_checkpoint` |
| 完整定向后检 | 222 passed，0 failed/skipped/xfail/errors；1038.36 秒，16:14:26–16:31:45 UTC | `targeted_final_after_contract_fix` |
| 全部测试后的历史复核 | 19 份旧工件及旧 P0 原字节保留；五类科学字段相等，exit 0 | `preserved_after_all_tests` |
| 日志和候选归档完整性 | 31 条既有记录/62 个日志流、20 个原反例日志流、24 个候选文件、20 个最终原生审计日志流、11 个绑定报告全部匹配 | `final_log_archive_integrity` |

核心套件按项目原生顺序暂不运行依赖尚未生成 checkpoint 的测试文件；该文件须由 fresh
checkpoint 后的完整定向后检覆盖。核心唯一 skip 为外层沙箱阻止嵌套 macOS sandbox-exec；
随后在同一实际工作树/原生环境，以原测试和既有合成样本执行真实沙箱断言，实际通过。
RLS xfail 保留原有科学不足：残差压缩使打乱后的判别损失未达到预期；没有改阈值、断言或标记。
各行包含重复覆盖，不将不同套件的 passed 数简单相加为独立用例总数。
最终暂存差异检查曾发现新生成命令索引末尾多余空行；仅修复该输出文档排版，实际失败日志保留，
随后对比 91dbdc 的完整暂存差异检查 exit 0。原始日志、数值工件和任何绑定输入均未因此改写。

完整修改文件清单：补修目录 `validation_logs/changed_files.txt`（对比已审查的 91dbdc）。
早期四次试跑的精确命令已从本任务原始执行记录提取到 `validation_logs/early_validation_commands.md`，
原始工具调用无损保存；没有从当前代码猜测旧命令。完整命令索引还包含首轮候选与最终原生矩阵，
候选日志始终标注为候选历史。封存提交 SHA 以本报告所在提交及最终交付消息为准；执行源码和
测试契约 SHA 已在上文固定。

本轮三项根因、修改前五类原反例、修改后真实入口拒绝和合法正路径、53 项新增回归的场景清单，
详见固定补修报告及 `targeted_test_inventory.stdout.log.gz`。本轮没有未解决的 R1/R2/R3 验收失败。
已知边界仍是可信本地解释器/标准库/正式入口、非独立托管的 Git、非连续文件系统监控、逐件而非
全批次原子发布；任意进程内改写和操作系统篡改不在证明范围。最早历史源码导入阻塞和既有 RLS
科学 xfail 仍保留，没有以新的依赖、参数或标记掩盖。

## 交接和失效清单

本轮提交依赖已审查 `91dbdc` 的上一轮窗口一实现。整合应保留从共同起点开始的窗口一完整依赖链，
不能只拣选最终封存工件提交；本轮修改文件清单按已审查提交至最终封存状态列出。

- 新实验产物：`benchmarks/structure_two/evidence_repair_supplement_2026_09_11/current_v0_3/` 的五类 JSON。
- 新历史审核：同目录上级的 `historical_source_audit_v0_2.json`，固定 11 份 Git 字节、4 份可恢复来源、
  1 次要求的 4103bea 全量失败重放；最早版本缺少 `RegimeStage` 仍无法导入。
- 最终工程产物：`benchmarks/structure_two/engineering_trust_checkpoint_2026_09_11_v0_2/` 的
  `engineering_audit_receipt.json`、`engineering_checkpoint.json` 和 `engineering_audit_logs/`。
- P0 消费者路径不变：`benchmarks/p0_checkpoint/content_manifest_v0_3.json`；内容必须匹配本分支最终测试契约。
- 改动包括正式 stdlib 来源启动器、来源诊断 CLI、证据版本/历史审核、共用安全发布器、五个 P5 CLI、
  聚合入口、P0/审计/checkpoint 入口、根 `conftest.py` 及对应回归测试。科学配置没有修改。
- 可能重叠位置：五个 P5 源模块及 CLI、生产装配消费者、证据版本模块、根测试启动器、P0 和
  checkpoint/audit 入口。五个 P5 源模块仅改路径与来源绑定，整合时保留窗口二、三的算法修改。
- 整合若调整原生审计命令，须同步核对完整命令契约测试；测试契约变化也使 P0、回执和 checkpoint 失效。
- 旧 v0.2 不能当作当前源码结果；本轮 v0.3 在合入其他源码后也将失效。旧产物必须保留原字节，
  下轮使用新证据版本或内容寻址路径，调整五个默认输出、CURRENT_DIRECTORY、证据上下文版本及消费者。
- 三个窗口最终整合后，必须在统一源码和匹配虚拟环境上依次重算当前五类结果、历史来源审核、P0、
  真实工程审计回执、强制 fresh checkpoint，再做当前性及对抗回归。三个分支的绿色不可拼接或自动继承。

无待用户选择的科学修改。本轮不改变阈值、种子、基线、长期提交准则、七算子和动作接线；
不打开新确认集或启动路由器训练。confirmatory、previously_unseen_established、
first_execution_established、independent_custody_established 均保持 false；D0 是开启后重放。
工程通过不消除既有科学失败或历史不可恢复，不宣称整个 CPSWM 已穷尽审计。
