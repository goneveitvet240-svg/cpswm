# CPSWM 结构二 W1 最新交付独立审计与受限复现

审计日期：2026-09-12  
审计方：PC-B  
范围：只读审核 W1 最新交付与实际生产源码；只新增本目录中的审计证据，不修改 W1 生产代码，不修改共享集成分支，不签发科学授权。

## 1. 结论

本轮结论必须同时保留下列四个状态，不能用其中一个覆盖其他状态：

| 状态 | 结论 | 含义 |
|---|---|---|
| `STATIC_DELIVERY_INTEGRITY_VERIFIED` | 通过 | W1 交付提交、实际生产提交、交付清单、历史状态/JUnit/命令记录之间的静态绑定一致。 |
| `WINDOWS_COMPATIBLE_DIAGNOSTIC_PASSED` | 通过（有限范围） | Windows、LF、UTF-8 条件下，23 项可移植诊断通过；生产入口缓存完整矩阵 21/21 通过；缓存抽样 8/8 通过。后两组有重叠，禁止相加成新的测试总数。 |
| `LINUX_W1_INDEPENDENT_REPRODUCTION_BLOCKED` | 阻塞 | 本机没有可用 WSL/Linux；无法公平重跑实际 controller、xdist worker、嵌套审计入口和 pytest 断言重写缓存保护。 |
| `UNIFIED_ACCEPTANCE_NOT_SIGNED` / `SCIENTIFIC_GATE_NOT_PASSED` | 未签收 | 历史绿色记录经静态核验，但不是 PC-B 在 Linux 上的动态复现；五阶段比较还是隔离组合源码，不是新的统一冻结源码验收。 |

因此，PC-B 可以独立确认：

1. `21870b0bcd6c23d43518a27fcc1c4b538b3912b7` 是以 `6fcff45c71eff3f3457d0b6eac6cd872102db89d` 为直接父提交的文档/证据封存交付；
2. 两提交在 `src/`、`tools/`、`apps/`、`configs/`、`tests/`、`pyproject.toml`、`uv.lock` 上没有差异；
3. W1 交付的 `artifact_inventory.json` 共 524 项，逐项从交付 Git 对象读取后 524/524 的 SHA-256 与字节数一致，无缺失、无不匹配；
4. 可移植的真实生产入口缓存边界在 Windows/LF/UTF-8 上通过；
5. 现有证据不足以由 PC-B 宣称“W1 已完成 Linux 独立复现”或“统一验收通过”。

本轮没有发现可在当前平台上归为 W1 生产缺陷的新反例。两个剩余动态失败均发生在测试前提/平台文件系统边界，不能被写成产品缺陷；同样也不能用它们的排除换取完整 W1 签收。

## 2. 固定对象与工作目录

| 对象 | 完整 SHA / 路径 | 说明 |
|---|---|---|
| 最新 W1 交付 | `21870b0bcd6c23d43518a27fcc1c4b538b3912b7` | 提交题目：`Seal W1 R6 runtime-cache repair evidence and handoff` |
| 实际 W1 生产源码 | `6fcff45c71eff3f3457d0b6eac6cd872102db89d` | 提交题目：`fix: compile runtime expectations from the exact hashed source bytes` |
| 交付 tree | `69535bc83081bae01d0698f8278cae696adda7de` | 两个独立 checkout 都绑定该 tree |
| Windows CRLF 对照 | `F:\庞惟\codex\cpswm-w1-audit-20260912` | detached HEAD；独立 `.venv`；工作树保持干净 |
| Windows LF 对照 | `F:\庞惟\codex\cpswm-w1-audit-lf-20260912` | detached HEAD；以 checkout 时 `core.autocrlf=false`、`core.eol=lf` 生成；工作树保持干净 |
| PC-B 审计输出 | `docs/reviews/pc_b/w3_five_boundaries_fix_2026-09-12/w1_audit/` | 仅新增报告、收集器、原始日志和 JUnit |

`git merge-base --is-ancestor 6fcff45c71eff3f3457d0b6eac6cd872102db89d 21870b0bcd6c23d43518a27fcc1c4b538b3912b7` 退出 0。交付提交的父提交正是生产提交。

`git diff --name-status 6fcff45... 21870b0...` 共 509 个路径，全部位于 `docs/`。限定生产路径的差异命令输出为空且退出 0。完整机器记录见：

- `raw/audit_delivery_ancestry.command.json`、相邻双流日志；
- `raw/audit_production_diff.command.json`、相邻双流日志；
- 最终权威元数据中的 `delivery_commit`、`production_commit` 和 `delivery_vs_production`。

两个 detached worktree 的建立命令如下；建立动作发生在原始命令记录器启用之前，因此这里逐字保留命令，建立后的实际列表由 `raw/audit_worktree_list.*` 独立记录：

```text
git worktree add --detach "F:\庞惟\codex\cpswm-w1-audit-20260912" 21870b0bcd6c23d43518a27fcc1c4b538b3912b7
git -c core.autocrlf=false -c core.eol=lf worktree add --detach "F:\庞惟\codex\cpswm-w1-audit-lf-20260912" 21870b0bcd6c23d43518a27fcc1c4b538b3912b7
```

未执行 `reset --hard`、未覆盖已有工作树、未向 W1 分支写提交。

## 3. 交付清单与实际源码摘要

交付内 `docs/reviews/pc_a/w1_cache_repair_2026-09-12/artifact_inventory.json` 的 Git blob SHA-256 为：

```text
f70492348d0ec5c7a8cb51305efadd90462d0a6928fe60fd63b4291783c2fdda
```

清单声明 `code_sha=6fcff45c71eff3f3457d0b6eac6cd872102db89d`。PC-B 没有信任工作树副本，而是对清单内每个相对路径执行等价于 `git show 21870b0:<path>` 的对象读取并重新计算 SHA-256 和字节数，结果为：

| 预期项 | 匹配 | 缺失 | 摘要/字节不符 |
|---:|---:|---:|---:|
| 524 | 524 | 0 | 0 |

以下是 W1 核心实现、正式入口和测试选择的 Git blob/LF 字节摘要。两提交对应 blob 完全相同：

| 路径 | SHA-256 |
|---|---|
| `tools/structure_two_pytest_runtime.py` | `b89095f757467cfe017865eace1e2f8ecead33979e2adaf22d0ac1fd7ad882ff` |
| `tools/structure_two_unified_acceptance.py` | `31f7e0177aad246d703ea55b7938ab24a07e738c0b4199f76adaffc9576c2747` |
| `apps/evaluation_runner/run_structure_two_engineering_audit_receipt.py` | `51707945e6fde4a2b8d20758f8748c730d7c7a814301ed7a7985ae50132e5d96` |
| `tests/test_structure_two_runtime_cache_identity.py` | `39cf43a64d1c0496e5f83be28e263eef2b979e45c88d25b6fbe8286e16208877` |
| `tests/test_structure_two_engineering_trust_checkpoint.py` | `98ad83d0587b419dd1b70e4b6867029e5e3b9d471d564946877db1781ec34941` |
| `tests/test_structure_two_evidence_versions.py` | `c60ea10510ca20d4b151564f2f9f995050bdaca74800b67dd7963c73b217e15f` |
| `tests/test_structure_two_evidence_supplement.py` | `9c3977c7cf2d1a6b5b9dc55a4ff6a572e6480241f3bf677efd8b6fadfa43b24c` |
| `tests/test_structure_two_entry_portability.py` | `2b227a32728bc038a40d16bc58d563a23a948d356302b2cd2cc945835bf4326e` |
| `pyproject.toml` | `6fb202d1ca629d7256cb8759f70e64991e6e7993cb159cc8039c265288d95f18` |
| `uv.lock` | `8ff0275d2b10eef8c258f14c82a050358ceee6443a5d0fa4c9ddfcc3832291b1` |

W1 自身最终环境文件只明确报告前五个核心文件；这五个报告摘要全部与 Git blob 匹配。其余路径由 PC-B 独立记录 Git blob、生产 blob、工作副本摘要和 EOL，不将“报告未声明”误写为“报告声明匹配”。

## 4. Windows/LF 对照与实际加载来源

本机 Git 配置查询结果：

- `core.autocrlf=true`，来源为 Codex bundled Git 配置；
- `core.eol` 未显式设置，查询退出 1；
- `core.safecrlf` 未显式设置，查询退出 1；
- 相关文件没有额外属性输出。

CRLF checkout 的 `git ls-files --eol` 为 `i/lf w/crlf`；因此工作副本字节摘要和 Git blob 摘要不同。LF checkout 为 `i/lf w/lf`，上述文件工作副本与 Git blob 逐字节一致。初次 25 项对照中的多项失败正是原字节断言看到 CRLF，不是生产 blob 漂移。

独立导入探针均退出 0：

| checkout | `cpswm.__file__` | W1 编排模块 |
|---|---|---|
| CRLF | `F:\庞惟\codex\cpswm-w1-audit-20260912\src\cpswm\__init__.py` | 同一 CRLF worktree 的 `tools\structure_two_unified_acceptance.py` |
| LF | `F:\庞惟\codex\cpswm-w1-audit-lf-20260912\src\cpswm\__init__.py` | 同一 LF worktree 的 `tools\structure_two_unified_acceptance.py` |

LF 测试使用 `PYTHONPATH=F:\庞惟\codex\cpswm-w1-audit-lf-20260912\src`；需要跨子进程保留中文路径时另设 `PYTHONUTF8=1`。`PYTHONUTF8=1` 只修正 Windows 子进程对中文 Git 路径的编码解释，不禁用缓存、不改变断言、不更换被测源码。

## 5. 解释器、依赖与公平性

当前独立环境：

| 项 | 当前 PC-B |
|---|---|
| OS | `Windows-11-10.0.22631-SP0` |
| Python | CPython `3.13.5`，MSC v.1944 64 bit |
| 可执行文件 | `F:\庞惟\codex\cpswm-w1-audit-20260912\.venv\Scripts\python.exe` |
| 可执行文件 SHA-256 | `6dc19cff73c8d7d162cd72bdcebd1ecfbe93a7086520e2503c5a68ea64fb8cbe` |
| pytest | `9.1.1` |
| pytest-xdist | `3.8.0` |
| Git | 版本原始输出见 `raw/audit_git_version.stdout.log` |
| uv | `where.exe uv` 退出 1；本环境没有可调用 uv |
| 依赖健康 | `python -m pip check` 退出 0 |

独立环境建立命令及结果：

| 标签 | 结果 | 时长 |
|---|---:|---:|
| `create_independent_venv`：以 PC-B 现有 Python 调用 `virtualenv --copies .venv` | exit 0 | 9.79 s |
| `install_w1_dev_dependencies`：W1 独立 Python 执行 `pip install -e .[dev]` | exit 0 | 138.54 s |

本机不是历史锁环境的逐包复刻。因为 uv 不可用，本轮采用当前 pip 解析；完整分发包列表写入最终权威元数据。关键差异包括：

| 包 | 历史 W1 | 当前 Windows |
|---|---:|---:|
| `ast_serialize` | 0.8.0 | 0.11.1 |
| `numpy` | 2.5.2 | 2.5.3 |
| `scipy` | 1.18.0 | 1.18.1 |
| `ruff` | 0.16.3 | 0.16.7 |

历史 W1 报告环境为 CPython 3.13.5、Clang 20.1.4、解释器 SHA-256 `3e96a8b2f541b3d5ded271fb6e2bc83aea0557e863d0a4c472fd4679d1983fec`，路径 `/private/tmp/cpswm-pc-a-w1-cache-runtime-r6/.venv/bin/python`，并将三个数学线程变量固定为 1。当前 Windows 环境不能被称为这个 Linux/macOS 环境的二进制复刻。

所有当前测试运行都保持普通 Python/pytest 缓存行为：

- 没有 `-B`；
- 没有设置 `PYTHONDONTWRITEBYTECODE`；
- 没有 `-p no:cacheprovider`；
- 没有在运行前清理 `__pycache__` 或 pytest 缓存；
- 负例断言缓存字节在拒绝后仍原样存在，随后合法 file 入口在同一坏缓存仍存在时成功。

## 6. WSL/Linux 可用性

| 命令 | 退出码 | 实际输出 |
|---|---:|---|
| `wsl.exe --status` | 50 | stdout/stderr 均为空 |
| `wsl.exe --list --verbose` | 1 | 只返回 WSL 用法帮助，没有发行版列表或运行状态 |

因此，本机没有可用于本次任务的 WSL/Linux 执行面。原始双流见 `raw/wsl_status.*` 和 `raw/wsl_list_verbose.*`；后者 stdout SHA-256 为 `283fb42e56fb93bda81201dc3ceb37a98da8ee47db115c17829b43c0fa2fc6ab`。

不能直接在 Windows 上冒充正式链，原因来自被测合同本身：

- `tools/structure_two_unified_acceptance.py` 固定检查 `root/.venv/bin/python`；
- 工程回执命令固定使用 `.venv/bin/python`；
- 运行时夹具复制/检查 POSIX venv 和 shebang；
- 编排器使用 `os.killpg`、`SIGTERM`、`SIGKILL` 与 `start_new_session=True`；
- 历史正式命令和临时根位于 `/private/tmp`。

这些是 controller、进程组、worker 与嵌套入口身份合同的一部分。将路径改写成 `Scripts\python.exe`、绕开进程组或删缓存，会改变被测对象；本轮没有这样做。

## 7. 历史 86、115、history 与五阶段链静态复核

本节只称为“交付内历史证据静态复核”，不称为 PC-B 独立动态重跑。

### 7.1 当前选择数量复核

在当前 Windows 独立环境中用原测试路径执行 `--collect-only`：

| 选择 | 结果 |
|---|---|
| runtime86 四个选择 | exit 0，精确收集 86 项 |
| W1 三文件 payload | exit 0，精确收集 115 项 |

完整命令和收集清单分别位于 `raw/windows_collect_runtime86.*` 与 `raw/windows_collect_w1_payload.*`。

### 7.2 历史状态与 JUnit

| 历史记录 | 源码 HEAD | manifest SHA-256 / 文件数 | 阶段结果 | JUnit SHA-256 |
|---|---|---|---|---|
| `r6_runtime86_protected` | `6fcff45...` | `7d9c0682fc6662d3cb62ae1af2ee95da6fc2667de01d60cd718708cb732abdcf` / 1780 | 86/0/0/0，exit 0 | `f9c2060051bab584b1d48ccc604411e594c2bca4552581f670d712eb9204670d` |
| `r6_native115_accepted` | `6fcff45...` | 同上 / 1780 | 115/0/0/0，exit 0 | `213d045377f9d022b292ffef4b9a74da24a29e9aeaeedfe1d064973519ce5e73` |
| `r6_history_trace_accepted` | `6fcff45...` | 同上 / 1780 | 1/0/0/0，exit 0 | `7bfc56e2542b474e2055b48b98cfd8a61ae155bfacae51626f7e1e6437044f7` |
| 隔离 `r6_comparison_accepted` | `07fc56983ae93d2d3abd63736abd78201b9c34fa` | `cfcdd457726024b9858ae5a9aed78922ccad75c340167cf9204ccf43600e9abb` / 1492 | 五阶段 exit 均 0；消费者 77/0/0/0 | `cf1ea12d56cc0ac43a60ff9fc53d77d2e1526fdd28c66443b6532d8e27cdbb3c` |

前三项 `source_before == source_after`，状态均为 `STAGES_COMPLETED_NOT_AUTHORIZATION`。隔离比较同样来源前后一致，但其实际 HEAD 是 `07fc569...`，不是 `6fcff45...` 或完整 W1/W2/W3 统一源码；所以只能保留为限定范围的隔离比较链。

历史外层命令记录也逐文件重新哈希并读取：

| 命令记录 | exit | 外层时长 |
|---|---:|---:|
| `runtime86_accepted.command.json` | 0 | 101.72 s |
| `runtime86_protected.command.json` | 0 | 75.35 s |
| `native115_accepted.command.json` | 0 | 4274.39 s |
| `history_trace_accepted.command.json` | 0 | 552.56 s |
| `comparison_accepted.command.json` | 0 | 3893.96 s |

对应的完整 `argv`、`cwd`、UTC/本地时间、环境和 SHA-256 已包含在最终权威元数据。上述数据说明交付包内部自洽，不说明 PC-B 已在当前机器重新执行这些长链。

## 8. Windows 公平动态复现结果

### 8.1 结果总表

| 运行 | 平台/checkout | 结果 | JUnit SHA-256 | 解释 |
|---|---|---:|---|---|
| `windows_w1_fair_subset` | Windows / CRLF | 25 tests：12 passed，13 failed，exit 1 | `bfe7c7eba4852ac6b6efa5956dacdb09d3b72379bf87a991ab545d47ab496444` | 原字节 Git 比较被 CRLF 改写；中文路径在子进程中乱码。保留为 Windows/CRLF 对照。 |
| `windows_lf_w1_fair_subset` | Windows / LF | 25 tests：21 passed，4 failed，exit 1 | `402610955e9c5cc5846d7b9854dda7ff07f6e472cc7774603f8a2a111ccb2156` | LF 消除字节差异；剩余 3 个 formal-entry 与 1 个 sources-only 路径受默认代码页影响。 |
| `windows_lf_utf8_platform_diagnostic` | Windows / LF / UTF-8 | 4 tests：2 passed，2 failed，exit 1 | `de2f39f899bd053ceb5c2744ca2fe7c8d35104d2062b1abe3e981117b47d07b9` | 合法无缓存/合法缓存通过；两个失败分别为 Windows 换行写回改变字节数、Windows 长路径 tar 解包失败。 |
| `windows_lf_utf8_fair_compatible_subset` | Windows / LF / UTF-8 | 23 passed，exit 0 | `9527ca6e2ca772b1cccf26a1f228572414990788574862fb6bfa98620762eeda` | 只排除上述两个在 Windows 上不能满足原测试前提的节点；是可移植子集，不是 115 项签收。 |
| `windows_lf_utf8_cache_boundary_subset` | Windows / LF / UTF-8 | 8 passed，exit 0 | `bfc59621beb988bc09d635c0b9042b930d0d73465874d86e4c5f5a4007418cef` | 合法 timestamp/unchecked 及旧 timestamp/unchecked 的直接/子进程边界抽样。 |
| `windows_lf_utf8_entry_cache_matrix` | Windows / LF / UTF-8 | 21 passed，exit 0 | `d94511764c67fb59a6ced6fe533ee1211ac8b1e425765250b251a298d129e773` | 完整生产入口缓存矩阵，详见下一节。 |

`windows_lf_utf8_cache_boundary_subset` 的 8 项是 21 项完整入口矩阵的子集，禁止将 8 和 21 相加。`windows_lf_utf8_fair_compatible_subset` 与其他两组也存在测试重叠；这些计数用于呈现不同诊断切面，不是累计测试数。

### 8.2 完整生产入口缓存矩阵

被测实际入口：

- 文件：`apps/evaluation_runner/probe_structure_two_execution_source.py`；
- 模块：`apps.evaluation_runner.probe_structure_two_execution_source`；
- 入口政策：`frozen-source-and-entry-compile@2`。

合法正例 15 项：

| 缓存状态 | 启动方式 | 期望 | 实际 |
|---|---|---|---|
| 无缓存 | file / module / runpy / spawn_file / spawn_module | 加载当前语义并生成 source binding | 5/5 通过 |
| 合法 timestamp | 同上 | 不因合法缓存误拒绝；加载阈值 0.5 | 5/5 通过 |
| 合法 unchecked-hash | 同上 | 不因合法缓存误拒绝；加载阈值 0.5 | 5/5 通过 |

子进程正例还核验 `pid != parent_pid`，不是把同进程调用冒充 spawn。

反例 6 项：

| 缓存攻击 | 启动方式 | 期望 | 实际状态后果 |
|---|---|---|---|
| 旧 unchecked-hash | module / spawn_module | 在 source claim 前拒绝 | 2/2 通过 |
| 同大小同 mtime 的旧 timestamp | module / spawn_module | 在 source claim 前拒绝 | 2/2 通过 |
| 携带外来 `co_filename` 的缓存 | module / spawn_module | 在 source claim 前拒绝 | 2/2 通过 |

每个反例都验证：

1. 被测进程非零退出，stderr 包含 formal bootstrap/entry 拒绝；
2. stdout 中没有 `source_binding`；
3. 没有生成 `benchmarks/**/current_v0_4/*.json`；
4. 生产入口源码字节和攻击缓存字节均保持原样；
5. 同一坏缓存仍在时，合法 file 入口随后成功并读取当前语义。

这是公开生产入口的真实子进程验证，没有直接修改 W1 内部 journal 状态。测试夹具只构造真实 pyc 与临时源码副本，并通过实际 Python 启动形式进入生产入口。

### 8.3 两个平台前提失败

1. `test_formal_entry_uses_actual_frozen_semantics_despite_bytecode_cache[stale_same_size_mtime]` 在准备攻击时即失败：`Path.read_text()/write_text()` 在 Windows 将 LF 写成 CRLF，目标从 20,752 字节变为 21,274 字节，`same size` 前提不成立。它没有进入 W1 拒绝逻辑。21 项矩阵使用原始字节写入，已独立覆盖同大小同 mtime 的生产入口旧缓存，但不能替代这个“嵌套被导入源码”节点的 Linux 复现。

2. `test_sources_only_history_report_honestly_records_no_recomputation` 在 Windows 临时目录解压历史 Git tar 时遇到长路径 `FileNotFoundError`，没有进入历史报告语义断言。

这两个失败保留在原始 JUnit 和 stdout 中。它们既不被改为 xfail，也不从历史记录删除。

## 9. 四类缓存与进程身份逐项判断

| 要求 | PC-B 当前动态结果 | 能否独立签收 |
|---|---|---|
| 合法缓存正例 | 真实生产入口无缓存、合法 timestamp、合法 unchecked-hash，五种启动方式 15/15 通过 | 可签收此入口的 Windows/LF/UTF-8 可移植范围 |
| timestamp 旧缓存 | 生产 module 与 spawn_module 2/2 按合同拒绝，拒绝无输出副作用，缓存保留，后续 file 正例通过 | 可签收此入口的 Windows 可移植范围；不能替代 controller/xdist |
| unchecked-hash 旧缓存 | 生产 module 与 spawn_module 2/2 按合同拒绝，状态后果同上 | 可签收此入口的 Windows 可移植范围；不能替代 controller/xdist |
| pytest 旧断言重写缓存 | 交付内历史 runtime86 JUnit/状态静态匹配；本机未动态运行正式 runtime fixture | 不可签收 |
| controller 身份 | 历史 protected state 静态匹配；Windows 正式编排要求 POSIX venv/进程组 | 不可签收 |
| xdist worker 身份 | 历史状态含实际运行时观测，但本机没有公平动态重放 | 不可签收 |
| 嵌套 `p0_adversarial_tests` / `core_pytest` 入口 | 历史记录静态匹配；Windows fixture 固定 `.venv/bin/python` | 不可签收 |

特别说明：21 项矩阵中的 `spawn_*` 是真实子进程，但不是 xdist worker；不能用它替代 worker 身份证明。23 项绿色可移植子集也没有启用 W1 runtime 插件，不能冒充 `-p tools.structure_two_pytest_runtime` 保护链。

## 10. 完整命令、日志和 JUnit 索引

每个记录标签均有三件套：

- `raw/<label>.command.json`：完整 argv、cwd、开始/结束、时长、退出码、允许列出的环境变量；
- `raw/<label>.stdout.log`：原始标准输出；
- `raw/<label>.stderr.log`：原始标准错误。

关键标签：

| 类别 | 标签 |
|---|---|
| 环境建立 | `create_independent_venv`、`install_w1_dev_dependencies` |
| 环境核验 | `audit_python_version`、`audit_git_version`、`audit_uv_availability`、`audit_pip_check` |
| Git/工作树 | `audit_worktree_list`、`audit_delivery_ancestry`、`audit_production_diff` |
| WSL | `wsl_status`、`wsl_list_verbose` |
| 收集数量 | `windows_collect_runtime86`、`windows_collect_w1_payload` |
| Windows/CRLF | `windows_w1_fair_subset` |
| Windows/LF | `windows_lf_w1_fair_subset` |
| 平台诊断 | `windows_lf_utf8_platform_diagnostic` |
| 可移植子集 | `windows_lf_utf8_fair_compatible_subset` |
| 缓存抽样 | `windows_lf_utf8_cache_boundary_subset` |
| 完整入口矩阵 | `windows_lf_utf8_entry_cache_matrix` |
| 最终元数据 | `collect_w1_metadata_authoritative_final_utf8` |

六份当前 JUnit 位于本目录根部，文件名与运行标签一致。历史四份 JUnit 的路径和摘要包含在最终元数据 `historical_junit` 字段中。

逐项机器可读矩阵为 `MACHINE_MATRIX.json`（SHA-256 `c436c719ba2c05fb4f67e815f8d109671fac72b4acc49b91f666058f076f26cd`）。其中有 7 行平台/运行矩阵和 21 行逐入口缓存矩阵，逐项记录入口、前提、信任假设、期望、实际结果、状态后果及证据路径；WSL 两个退出码、CRLF/LF/UTF-8 对照、合法 timestamp/unchecked 正例和 stale/foreign 反例均为独立字段。

最终权威元数据：

```text
raw/collect_w1_metadata_authoritative_final_utf8.stdout.log
SHA-256 88434fd56aa9f9988eb16e37c41631ccc36dda12529166ffda221e407087e6f6
```

其命令记录：

```text
raw/collect_w1_metadata_authoritative_final_utf8.command.json
SHA-256 b30afdd5ab72353676c0e672489d562f781cbbbe6d8eaf586f552355902a3569
exit 0
stderr 0 bytes
```

该元数据包含：

- 交付/生产 commit 与 tree；
- 交付差异摘要；
- 524 项交付清单的逐项复核结果；
- 当前与历史解释器/依赖；
- CRLF 与 LF checkout 的 Git/EOL、工作副本和 Git blob 摘要；
- 两个 checkout 的实际导入路径；
- 历史 state、外层命令和 JUnit；
- 当前命令与 JUnit；
- WSL 原始日志摘要；
- 缓存公平性声明。

更早的 `collect_w1_metadata*.stdout.log` 是收集器迭代过程，原样保留，不覆盖历史；其中无 `authoritative_final` 后缀的文件均被最终元数据取代。最早一份受终端输出编码影响出现路径乱码，不能作为权威路径记录。

## 11. 尚需在 Linux/WSL 完成的独立验收

要解除本报告的阻塞，需在新的 Linux 源码目录、固定 `21870b0b...` 交付和 `6fcff45c...` 生产源码上完成：

1. 使用 Python 3.13.5 和 `uv.lock` 精确同步依赖，记录解释器/依赖/加载路径；
2. 保留合法缓存，分别构造 timestamp 旧缓存、unchecked-hash 旧缓存、pytest 旧断言重写缓存；
3. 通过实际 `tools.structure_two_pytest_runtime` 插件运行 controller、`-n 2` xdist worker、嵌套 `p0_adversarial_tests` 和 `core_pytest`；
4. 运行报告所列 86 项、115 项和完整历史重放；为每次运行使用新的证据目录，不能覆盖 R6；
5. 若运行五阶段消费者链，明确其实际 source HEAD；隔离 `07fc569...` 只能称隔离 comparison，不可写成统一冻结验收；
6. 全程不得用 `-B`、`PYTHONDONTWRITEBYTECODE`、清缓存或禁用 pytest cacheprovider 代替安全验证；
7. 保存每次完整命令、双流、退出码、JUnit、runtime contract、controller/worker 观测、source_before/source_after 和缓存攻击原件。

完成这些之前，最终交接应保留“交付完整性已验证、Windows 可移植入口边界通过、Linux 全链独立复现阻塞、统一验收未签收、科学门未通过”五个事实。
