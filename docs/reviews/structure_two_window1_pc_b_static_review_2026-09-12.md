# 结构二 W1：电脑 B 独立静态审核

审核日期：2026-09-12

审核对象：`b6202bec015679461b06056571bd47a5446045b8`（远端 `origin/codex/snapshot-w1-20260912`）；父提交 `f5089d94ba217b377f88067bc36fdb976e12a4cf`，tree `1a1d384fbf1ddf7380dc80b8f1b388b355511337`。

结论：**STATIC REVIEW COMPLETE / EXECUTION BLOCKED / NOT ACCEPTED**。该提交是 WIP 快照，不是包含 W1+W2+W3 的统一验收提交。B 已独立核对本次代码变化及依赖闭包，但当前原生 Windows 环境不能等价执行其 POSIX 运行时合同；提交自身也缺少统一执行所声明的 W2/W3 依赖，因此不能把历史测试结果当作本 SHA 的验收证据。

本报告及其命令/对象摘要随 W3 交接包提交：`docs/reviews/data/pc_b_w3_r6_independent_20260912/metadata.log`。W1 的信任边界是只读 Git-object 静态检查：没有运行 W1 acceptance，没有 checkout 后修改其内部状态，也没有把电脑 B 当前环境伪称为 W1 的通过环境。

## 精确差异

相对父提交仅有五个文件：

- 新增 `AGENTS.md`；
- 新增 `docs/collaboration/SNAPSHOT_SCOPE.json`；
- 新增 `tests/test_structure_two_unified_dependencies.py`；
- 新增 `tools/structure_two_pytest_runtime.py`；
- 修改 `tools/structure_two_unified_acceptance.py`。

三份本轮 Python 文件均可解析，提交差异通过 `git diff --check`。远端引用、提交父子关系及 SNAPSHOT_SCOPE 文件摘要已核对。

五个 delta 的 Git-object SHA-256 为：

- `AGENTS.md`：`aa6b2fca7fd6ad3c1ab06ea0ec0aa93045a197cb84f2eaaca304fdffca1726ae`
- `docs/collaboration/SNAPSHOT_SCOPE.json`：`2564b774a9b2eefd23200ac5a693e2000cbb38067f9bd84d0dc24b955b658182`
- `tests/test_structure_two_unified_dependencies.py`：`b2aed0837d499e1086e55ad9141c67a379c3b302b9ccb2808379b62a531eb6c8`
- `tools/structure_two_pytest_runtime.py`：`876b54448c8fa39dd5fd526dbc1ac06882cfa8297dbcc0d34b6ca741f8030cdb`
- `tools/structure_two_unified_acceptance.py`：`0e38a3e85a3300b7db18e2780c648034307f8491a7030dba487a7f3c497a8fae`

W1 提交内 `uv.lock` SHA-256 是 `8ff0275d2b10eef8c258f14c82a050358ceee6443a5d0fa4c9ddfcc3832291b1`；它与电脑 B 集成基线环境的 `uv.lock` 不同，故本报告不把当前已安装的 56 个不同包名作为 W1 执行证据。

## 正向静态结论

1. `comparison_plan` 已把窗口二过程明确为生成比较包 → 独立复算/验证 → 归因生成 → 归因复算/验证 → 消费测试，并通过 `requires`、冻结输出和“新 run 不得预置结果”等约束阻止跳过生产者直接消费旧绿色文件。
2. pytest 矩阵不再依赖 shebang 启动，而是要求实际 `.venv/bin/python -m pytest`。新增 runtime plugin 记录 controller/xdist worker 的 PID、解释器、pytest/cpswm 源码路径和测试阶段，只接受完整、实际执行且全通过的节点。
3. 协调器保留失败 journal、拒绝外来解释器/模块、隐藏过滤、缺失节点、空收集、skip/xfail 和中断等路径；这些设计方向与“实际运行绑定而非自报通过”一致。

## 执行阻塞 1：原生 Windows 不是该提交的等价运行环境

`tools/structure_two_unified_acceptance.py` 在多处硬编码 `.venv/bin/python` 和 `.venv/lib/python3.13/site-packages`，进程清理使用 `os.killpg`、`SIGTERM`、`SIGKILL`；`tools/structure_two_pytest_runtime.py` 也要求解释器精确等于 `.venv/bin/python`。Windows 虚拟环境实际路径是 `.venv\Scripts\python.exe` 和 `Lib\site-packages`，且没有等价的 POSIX process-group 语义。

因此 B 不会为“跑通”而关闭这些来源/进程校验，也不会把 Windows 路径替换后的非等价结果写成 W1 通过。此部分需要 WSL2/Linux 文件系统中的独立克隆和独立 `.venv`。

## 执行阻塞 2：该快照不是统一依赖闭包

W1 工具声明的五个窗口二测试在 `b6202bec...` 中全部缺失，对应的比较生产/汇总入口也不完整。窗口三声明的 29 个测试中有 14 个不在该 SHA。故即使进入 WSL，完整 `--execute` 也会先因 required test/producer 缺失而拒绝；这不是测试失败，而是被测快照没有形成统一来源树。

精确缺失清单已写入 `metadata.log`：W2 的 5/5 tests 及 2/2 producer/summary 入口全部缺失；W3 缺少 `backbone_operator_wiring`、`backbone_counterexample_regressions`、`late_counter_evidence_chain`、`operator_causal_matrix`、`ciav_negative_observation_layers`、`p0_maintenance_fault_injection`、`formal_revision_lineage`、`operator_coverage_matrix` 和六个 `w3_*` acceptance/boundary/native 文件，共 14/29。

需要电脑 A 先发布一个明确的统一提交：包含 W1 `b6202bec...`、真实 W2 生产/复算/消费链、W3 R6、冲突处理和输入摘要。B 将只对这个新的精确 SHA 执行统一验收。

## 历史证据不能证明本提交

仓库中的 `status_report.md` 记录过 `40 passed`，但该证据绑定的 `tools/structure_two_unified_acceptance.py` SHA-256 是：

`cf003e23d7984ba9f616854b146ed9c942fa404e00c36432b8ba27fdb38e8e95`

W1 最新快照中该工具的 SHA-256 是：

`0e38a3e85a3300b7db18e2780c648034307f8491a7030dba487a7f3c497a8fae`

最新 delta 还新增了实际 pytest runtime plugin 与相应测试，但没有提交绑定这些最新文件的新运行报告。因此旧 `40 passed` 只能作为上一版本历史，不能升级为 `b6202bec...` 已执行或已接受。

## 静态审核主机与 Git 换行边界

只读审核主机为 Windows 11 10.0.22631、Git 2.53.0.windows.3、CPython 3.13.5、pytest 9.1.1；这只是审核工具环境，不是 W1 runtime acceptance。便携 uv 为 0.12.13，实际入口 `F:\庞惟\codex\tools\uv-0.12.13\uv.exe`，不在普通 PATH。

Git 的 effective `core.autocrlf=true` 来自 Codex runtime Git config；仓库没有 `.gitattributes`，W1 五个变化文件的 `text`/`eol` 属性未指定。W1 静态结论使用提交内 Git object 内容及其摘要，而不是把 Windows checkout 的 CRLF 字节当成规范源。实际命令、AST parse 结果、`git diff --check` 和配置来源均保留在 `metadata.log`。

## 后续最小动作

1. 获得统一 SHA 后，在 WSL2 Ubuntu 24.04 的 Linux 文件系统重新克隆，并用 CPython 3.13.5、`uv sync --frozen --extra dev` 建立环境。
2. 先执行 W1 的来源保护、证据补充和入口可移植性测试，再执行 unified acceptance/dependencies 两文件。
3. non-execute 计划必须先形成新的 HEAD/input digest；只有全部生产者、工件、测试节点在同一来源树内，才允许创建全新 run-dir 执行 `--execute`。
4. 每次源码提交变化都使旧审核失效；B 只报告实际命令、退出码和精确提交，不汇总历史计数冒充本次通过。
