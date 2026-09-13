# 结构二窗口一：独立对抗复核

日期：2026-09-11。对象：`codex/s2-evidence-repair-window1-20260911`，最终提交 `91dbdc57968071be29976d1a7b99de51d9288cdd`，共同起点 `09eb4d48e1c11082e90ca18332d04333e6b5b47a`。

## 1. 验收判断

窗口一对历史结果恢复、当前结果分版、缺失测试依赖补齐和检查点当前性的修复有实质进展。五类当前 v0.2 结果已全部通过独立完整重算，历史审核也通过；原检查点在其声明的工作树和环境中通过当前性检查。本次独立定向测试合计 169 项通过。

但新增保护仍有三类可复现缺口：**源码身份检查不能排除较早导入的旧模块及陈旧字节码；历史审核可以遗漏应核验条目甚至跳过要求的重算而报成功；输出目录检查不能阻止硬链接覆盖历史文件。** 建议保留有效修复与证据，但补齐这三项后再关闭本窗口，不能称“保护已完整”。

这些反例并不证明原始实验数据造假，也不等于既有检查点已被本次攻击整体绕过。必须把正常路径可复现、验证入口的拒绝能力和独立历史真实性分别评价。

## 2. 独立复核范围与结果

- 独立工作树：`/private/tmp/s2-review-w1.S2iE8o`，固定上述最终提交。源码、测试、配置及原始产物均未修改。
- 原窗口工作树：`/private/tmp/cpswm-s2-evidence-repair-window1`。只在这里运行路径/环境绑定的检查点只读验证和 15 项定向测试，没有重新生成或覆盖检查点。
- 独立工作树使用项目原生 Python 3.13.5：`/Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/.venv/bin/python`；原窗口的路径敏感检查使用它自己的 `.venv/bin/python`。没有语法降级、替换导入或修改实验算法。
- 原报告：[窗口一修复报告](/private/tmp/cpswm-s2-evidence-repair-window1/docs/reviews/structure_two_evidence_repair_window1_2026-09-11.md)。

| 复核项目 | 本次结果 |
|---|---|
| 新增证据版本测试、P0 清单、post-hoc、factorial 定向测试 | 56 passed，87.02 秒 |
| 三组既有 P0 授权/正式执行/比较协议安全测试 | 98 passed，19.21 秒；与前项 23 项清单测试合计覆盖原 P0 121 项矩阵 |
| 原窗口工程检查点测试 | 15 passed，26.86 秒 |
| 原检查点 `--verify --no-fresh-recomputation` | 退出 0；仅当前性/绑定核对，不冒充本次重新生成检查点 |
| 五类当前 v0.2 结果完整新鲜重算 | 全部通过，聚合进程退出 0；三臂、post-hoc、债务重放、四组合析因、D0 开启后重放分别由独立子进程执行真实验证器 |
| 历史来源与可恢复失败重放的完整审核 | 退出 0；11 份 Git 副本核验；`4103bea` 失败重算整个工件相等；早期导入失败及其他来源不匹配如实保留 |
| 五个独立反例模式 | 均复现；具体证据见第 4 节 |

本次读取并核对留存审计日志：10 条命令均记录退出 0；核心 pytest 日志符号计数为 3855 passed、1 skipped、1 xfailed，总计 3857，与报告一致。**本次未重新执行整套 3857 项，也未重新执行全部 mypy/Ruff/环境封闭性检查，不把留存日志视为本次独立执行。**

独立完整重算仍保留以下状态，不新增科学通过：

| 当前结果 | 重算核对后的状态 |
|---|---|
| 三臂 | `P5_ACTION_SIGNAL_NOT_DETECTED` |
| post-hoc | `POSTHOC_READOUT_DEGENERACY_REMOVED` |
| 债务重放 | `PRODUCTION_DEBT_REPLAY_SEMANTIC_EQUIVALENCE_CONFIRMED`；1,243 个正转移，677 个负观测步骤被排除，不能外推负观测 |
| 四组合析因 | `DEVELOPMENT_FACTORIAL_COMPLETE`；60 个 episode 的已开启开发数据 |
| D0 开启后重放 | 兼容状态字符串 `INTERNAL_UNSEEN_D0_SIGNAL_NOT_DETECTED`；生命周期仍明确为开启后重放，非新的未见确认 |

五份产物的 `confirmatory`、`previously_unseen_established`、`independent_custody_established` 均为 false。全部后台复核进程已结束，没有遗留运行中的重算任务。

## 3. 可以保留的修复与结论

1. 旧 v0.1 三臂路径恢复为 `4103bea` 的被引用失败重放，post-hoc 固定期望哈希没有被直接改成后来开发结果的哈希；最早失败、后续失败重放和修复后开发结果分别保存。这个处理正确区分了历史引用与当前结果。
2. 11 份原始历史副本可逐字节对照其 Git blob，不能据此证明真实首次执行时间或独立托管。原报告保留这一区分。
3. 早期 `557ff9c` 等快照因缺少 `RegimeStage` 无法导入；本次也复现最早失败快照的导入失败，没有用新依赖代替旧依赖后称“历史复现成功”。
4. D0 初次记录的来源绑定不完整，不能再将它无条件叫作首次未见确认。当前 v0.2 生命周期为 `POST_OPEN_CURRENT_SOURCE_REPLAY`，`confirmatory`、`previously_unseen_established` 等均为 false；旧状态字符串保留也不能推翻这一边界。
5. 恢复的部分测试工件有共同起点固定哈希，另一些只有当前本地开发工件身份。原报告对后二者作了降级，不应把它们误读成已证实的历史执行或真实外部感知数据。
6. checkpoint 明确设置 `integration_requires_new_checkpoint=true`。其工程通过只表示当前本地记录一致，不表示执行真实性、封闭工具链、独立托管或科学通过。
7. 检查了相关科学配置和主干文件差异：本轮没有更改所检查的科学种子配置、三臂/holdout 协议或 `prototype_spine` 算法。生产系统改动集中在来源文件/锁文件的符号链接检查。

## 4. 新发现

### W1-R1〔高优先级〕磁盘清单与真实加载实现可能不一致

定位：[导入期清单与运行前检查](/private/tmp/s2-review-w1.S2iE8o/src/cpswm/system/evaluation_operations/structure_two_evidence_versions.py:28)、[P5 来源绑定调用](/private/tmp/s2-review-w1.S2iE8o/src/cpswm/system/evaluation_operations/structure_two_p5_three_arm_death_test.py:1495)。

当前 `_RUNTIME_INVENTORY` 在 evidence_versions 模块导入时读取磁盘；`require_execution_source` 比较之后的磁盘清单与该快照。它没有证明所有已经加载的模块都来自这份快照，也没有证明 Python 字节码缓存对应当前源码。

反例 A：在一次新启动的测试进程中，先导入 `PrototypeLoopConfig`，随后在隔离副本中将源码 `owner_evidence_threshold` 从 0.5 改为 0.9，之后才导入 evidence_versions，再调用实际 P5 `_source_binding`。

```text
guard_accepted = true
p5_source_binding_accepted = true
cached_runtime_threshold = 0.5
fresh_runtime_threshold = 0.9
binding_matches_current_disk_manifest = true
```

因此较早缓存的旧实现可被绑定到新磁盘清单。既有测试只覆盖 evidence_versions 已先导入、随后改源码的顺序，未覆盖此顺序。

反例 B：先产生旧源码的正常 Python 字节码缓存，再在副本中进行同长度源码修改并保留原 mtime，启动全新进程导入实际 P5 模块。新进程仍读取旧缓存，而来源绑定接受新源码哈希。另用独立的新缓存目录加载同一源码进行对照。

```text
fresh_process_with_existing_pyc_threshold = 0.5
fresh_cache_threshold = 0.9
p5_source_binding_accepted = true
```

这说明“重新启动进程”本身不能完整解决所声明的缓存身份问题。反例 B 显式保持文件时间/长度来固定触发条件；本次没有发现原始运行实际遭遇这种缓存污染，也没有修改真正的实验文件。

修复验收：在任何项目依赖导入前固定执行来源，并让本次执行使用与该来源一致的隔离源码/缓存或经过验证的加载代码。不能只重新散列磁盘或只依赖重启。覆盖提前导入、正常导入后改盘、陈旧字节码、新缓存合法重放四条路径，检查实际加载语义与来源一致。无需借此建立新的庞大签名体系。

### W1-R2〔高优先级〕历史清单可删改，要求的重算由可变 ID 决定

定位：[历史清单加载](/private/tmp/s2-review-w1.S2iE8o/src/cpswm/system/evaluation_operations/structure_two_evidence_versions.py:73)、[按 ID 触发重算](/private/tmp/s2-review-w1.S2iE8o/apps/evaluation_runner/audit_structure_two_evidence_history.py:141)、[无条件成功消息](/private/tmp/s2-review-w1.S2iE8o/apps/evaluation_runner/audit_structure_two_evidence_history.py:182)。

`historical_entries` 只拒绝重复 ID，没有检查必需 ID 集合及它们的固定来源映射。重算分支再按这些可变字符串判断是否执行。两个真实命令行入口都可受影响。

反例 A：在隔离副本将 `entries` 改成空列表，提供同样为空的相容历史审核报告：

```text
run_structure_two_evidence_repair.py --verify-history
exit_code = 0
historical_local_git_audit = []

audit_structure_two_evidence_history.py --verify <empty-report>
exit_code = 0
historical source audit and recoverable failed replay verified
```

反例 B 更强：保留全部 11 份文件、合法 Git 引用和唯一 ID，只将 `three_arm_failed_replay_4103bea` 改名为 `three_arm_failed_replay_4103bea_unchecked`。使用真实历史审核脚本生成并验证相容报告：

```text
record_count = 11
renamed_record_git_bytes_verified = true
numerical_recomputation_count = 0
exit_code = 0
historical source audit and recoverable failed replay verified
```

这绕过了要求执行的可恢复失败重算，且“条目总数为 11”也不足以发现问题。最早版本导入失败仍如实存在；关键是本应可执行的 `4103bea` 重算被跳过了。

范围：这是独立历史验证入口的覆盖与成功语义缺口。修改 config 会改变 P0 配置摘要，原完整 checkpoint 的当前性比较不能直接沿用；本次未证明这些修改能绕过未改动的完整 checkpoint。原始固定 11 条清单仍应按正常路径单独核验。

修复验收：固定必需 ID、Git 提交、原路径和生命周期的对应关系；删项、改名、替换或缺少指定成功重算必须拒绝。成功状态必须依据实际执行结果而非仅循环结束。保留“历史不可导入已记录”与“可恢复失败重算完成”的区别，不把本地 Git 身份升级为独立历史真实性。

### W1-R3〔中优先级〕硬链接可穿透历史覆盖保护

定位：[输出路径保护](/private/tmp/s2-review-w1.S2iE8o/src/cpswm/system/evaluation_operations/structure_two_evidence_versions.py:61)、[CLI 最终写入](/private/tmp/s2-review-w1.S2iE8o/apps/evaluation_runner/run_structure_two_p5_three_arm_death_test.py:61)。

在隔离副本建立历史样本文件，再在允许的 current 目录内建立指向同一 inode 的硬链接。`require_current_output` 只检查目录和符号链接，允许该输出。随后使用与 CLI 相同的 `write_text` 写入原语，历史样本字节也被覆盖。

```text
output_guard_accepted = true
is_symlink = false
hardlink_count = 2
historical_bytes_overwritten = true
```

本反例运行了真实路径保护与真实写入原语，未为复现覆盖问题重复执行昂贵的整套实验；没有覆盖原仓库任何历史文件。触发条件是 current 目录已存在这样的硬链接，并非普通新建文件必然损坏历史。

修复验收：将保护落实到最终写入方式，使用新文件和安全原子发布等机制避免截断共享 inode，或明确拒绝不安全别名；同时考虑检查到写入期间的路径替换。对五个 CLI 和聚合生成器使用同一安全写入规则。测试真实历史样本字节在合法写入、硬链接、符号链接和失败路径后保持不变。

## 5. 与窗口二、三的关系

本次没有合并或执行窗口二、三新修复。窗口一的 checkpoint 仅对它自己声明的代码/工作树/环境有效；窗口二新增审计源码、窗口三修改生产接线，都会改变全量来源绑定。

整合顺序仍应是：完成源码/测试修复 → 统一代码版本 → 重算当前实验产物 → P0 清单 → 真实审计回执 → 工程 checkpoint → 当前性和对抗复核。不能把三个分支各自通过拼成统一通过。

科学结论没有因此改变：窗口一的工程修复不证明结构二的方法收益，也不取代窗口二对冷启动差额的归因或窗口三对真实协作链的验证。完整框架能力保留，不由证据链审核擅自缩小研究方向。

## 6. 复现与覆盖边界

反例脚本：[counterexamples.py](/Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/docs/reviews/data/structure_two_window1_adversarial_review_2026-09-11/counterexamples.py)。脚本仅在自动清理的隔离副本中更改源码、清单、缓存或样本文件；Git 调用仅为读历史，不改用户分支。

调用格式：

```bash
/Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/.venv/bin/python /Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/docs/reviews/data/structure_two_window1_adversarial_review_2026-09-11/counterexamples.py /private/tmp/s2-review-w1.S2iE8o late_import
```

将最后参数替换为 `stale_pyc`、`empty_history`、`renamed_history`、`hardlink`，分别复现其余四种模式。工作树若被清理，以固定提交重新建立隔离工作树，再传入其绝对路径。

正常当前结果重算：

```bash
cd /private/tmp/s2-review-w1.S2iE8o
PYTHONPATH=src /Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/.venv/bin/python apps/evaluation_runner/run_structure_two_evidence_repair.py --verify-current
```

正常历史来源与失败重放核验：

```bash
cd /private/tmp/s2-review-w1.S2iE8o
PYTHONPATH=src /Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/.venv/bin/python apps/evaluation_runner/audit_structure_two_evidence_history.py --verify benchmarks/structure_two/evidence_repair_2026_09_11/historical_source_audit.json
```

未覆盖：全仓所有正向授权输出、真正外部独立托管、恶意解释器/第三方原生扩展、所有并发文件替换，以及完整 CPSWM 运行状态机。既有本地记录明确不证明执行真实性，因此不能仅凭可改写本地回执这一事实另行宣称其承诺的独立托管被绕过。本报告也是有限范围的对抗复核，不是“没有更多问题”的声明。
