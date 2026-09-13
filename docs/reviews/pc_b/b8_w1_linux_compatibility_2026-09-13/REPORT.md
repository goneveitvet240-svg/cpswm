# B8：W1 Linux 独立兼容性复核

## 结论

本轮完成了 W1 冻结交付的来源核验、Linux 环境前提定位、可执行的协调器/入口缓存子集和
CPython 3.13 移交包。结果是 **部分完成、环境阻塞**，不是完整 Linux 动态复现：

- GitHub 交付 SHA 为 `21870b0bcd6c23d43518a27fcc1c4b538b3912b7`，其父提交也是交付报告登记
  的实际代码 SHA `6fcff45c71eff3f3457d0b6eac6cd872102db89d`，tree 为
  `69535bc83081bae01d0698f8278cae696adda7de`。
- 独立目录中 10 个 W1 关键源/测试/锁文件的 Git blob 与该 tree **10/10 精确匹配**；这是关键
  文件核验，不冒充完整 2,370 条 tree 的本地物化核验。
- 当前执行环境是 Linux x86_64 原生容器路径，不是 Windows，也未证明 WSL2 已在电脑 B 启用。
  只有 CPython 3.12.14；W1 生产协调器明确要求 3.13.x，并按
  `.venv/lib/python3.13/site-packages` 核验 pytest 来源。
- 3.12 上能真实执行且不绕过版本保护的协调器、JUnit、工件冻结、合法生产—消费和入口缓存子集
  **22/22 通过**。
- W1 新增的真实 controller/xdist worker/断言重写/项目与 helper 缓存身份文件收集 **20 个节点**，
  但 20/20 均在行为测试前被 `native Python 3.13 required` 拦截。因此这些节点本轮是“未评价”，
  不能记成保护逻辑失败，也不能记成通过。
- 完整原生 115 项和真实五阶段合法生产者—消费者链未运行：除 3.13 不存在外，本目录只物化了
  关键 W1 文件，不是完整冻结工作树，且完整项目依赖缺失。

本轮未修改 W1 生产实现、科学指标、缓存保护、阈值或 A 分支代码；未签发统一验收或科学结论。

## 被测身份

| 项目 | 结果 |
|---|---|
| 交付提交 | `21870b0bcd6c23d43518a27fcc1c4b538b3912b7` |
| 实际代码提交 | `6fcff45c71eff3f3457d0b6eac6cd872102db89d` |
| Git tree | `69535bc83081bae01d0698f8278cae696adda7de`，远端递归 tree 未截断，共 2,370 项 |
| 本地目录 | `/workspace/scratch/b158d995e8cc/cpswm_b8_snapshot` |
| 本地关键文件 | 10 个，Git blob 10/10 匹配、0 不匹配 |
| 生产源改动 | 无 |

逐文件 Git blob、SHA-256、解释器身份、命令结果和 JUnit 哈希见 `audit_results.json`。

## 平台与依赖

| 项目 | 实际值 |
|---|---|
| 系统 | Linux 6.18.35，x86_64，glibc 2.39 |
| CPU | 9 个逻辑 CPU |
| Python | CPython 3.12.14，cache tag `cpython-312` |
| venv | 本目录独立 `.venv`，`sys.prefix` 指向本目录；解释器是运行时的 3.12.14 符号链接 |
| uv | 0.12.11 |
| Git | 2.51.1 |
| pytest | 9.1.1 |
| pytest-xdist | 3.8.0 |

独立环境现有 distribution 只有 `pytest`、`pytest-xdist`、`execnet`、`pluggy`、`packaging`、
`iniconfig`。冻结离线检查明确显示还需安装 50 个包并替换 1 个版本；其中项目运行和开发关键缺项
包括 `cpswm` editable、cryptography、hydra-core、matplotlib、networkx、numpy、pydantic、scikit-learn、
scipy、hypothesis、mypy、pre-commit、pytest-cov、ruff。完整拟变更清单由该命令原始输出给出。

首次不设 `TMPDIR` 的离线检查因本容器没有 `/tmp` 而退出 2；设置本任务私有 `TMPDIR` 后才得到
上述真实环境差异。这个 `/tmp` 条件是本容器前提，不归因于 W1。

尝试 `uv python install 3.13.5`，13.465 秒后因平台对
`astral-sh/python-build-standalone` 发布包返回 HTTP 403 而退出 1。系统也没有现成 `python3.13`。
未通过修改协调器版本判断、伪造 site-packages 路径或改锁文件绕过。

## 动态结果

### 可运行的 3.12 非验收子集

以下均加载冻结 W1 的协调器原字节，使用真实子进程、Git 临时工作树、真实 pytest/JUnit 和工件
文件，不是重新实现的测试替身：

| 集合 | 覆盖 | 结果 | 墙时 |
|---|---|---:|---:|
| portable engine | 两阶段顺序与完整日志、旧绿色不可跳过、零退出不掩盖不完整 JUnit、真实 pytest JUnit 正例、skip/xfail 拒绝、工件重写/删除/新增拒绝、合法冻结包生产—消费 | 14/14 passed | 1.526 s |
| entry cache | 5 种危险环境拒绝、file/module 两种合法 unchecked-hash 入口缓存、旧 unchecked-hash 入口缓存拒绝 | 8/8 passed | 0.814 s |
| `py_compile` | 两个生产工具、工程回执入口及四个相关测试文件 | 退出 0 | <1 s |

这 22 项说明协调器的可移植基础路径在本 Linux/Python 3.12 上可执行；它们不包含 W1 明确要求的
3.13 controller/worker 来源证明，不能替代原 86、原生 115 或真实五阶段链。

### 受版本门阻塞的正式缓存身份文件

完整收集到 `tests/test_structure_two_runtime_cache_identity.py` 的 20 个节点，并真实启动每个用例。
结果为 20 failed、退出 1、pytest 1.83 秒。共同首因是：

```text
ValueError: native Python 3.13 required
```

8 个“预期拒绝”用例先捕获了这个环境异常，随后因阶段尚未开始而看到 journal 仍为 `STARTING`；
其他用例直接显示版本异常或没有缓存拒绝记录。这些是同一个前置环境阻塞的次生断言，并非 20 个
独立产品缺陷。JUnit 保留所有节点、堆栈和次生表现。

因此以下要求均为 **未运行到被保护行为**：真实 pytest controller、两个 xdist worker、项目/helper
timestamp 与 unchecked-hash 缓存、pytest/conftest 断言重写缓存、后台线程吞异常、外来
`co_filename`、同份字节 hash/compile 竞争和嵌套 P0/core 正负入口。

## 精确命令

可运行子集：

```bash
env PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest \
  -p xdist.plugin -o addopts= --noconftest -q \
  tests/test_structure_two_unified_acceptance.py::test_legal_stages_execute_in_order_and_preserve_complete_hashed_logs \
  tests/test_structure_two_unified_acceptance.py::test_preexisting_green_artifact_does_not_skip_real_subprocess \
  tests/test_structure_two_unified_acceptance.py::test_zero_exit_cannot_hide_absent_or_incomplete_required_test_matrix \
  tests/test_structure_two_unified_acceptance.py::test_real_pytest_junit_positive_has_actual_nonempty_test_count \
  tests/test_structure_two_unified_acceptance.py::test_real_pytest_zero_exit_with_incomplete_matrix_is_rejected \
  tests/test_structure_two_unified_acceptance.py::test_downstream_green_stage_cannot_replace_frozen_artifact_bundle \
  tests/test_structure_two_unified_acceptance.py::test_legitimate_frozen_bundle_is_usable_by_later_actual_stage \
  --junitxml=docs/reviews/pc_b/b8_w1_linux_compatibility_2026-09-13/portable_engine_subset_py312.junit.xml

env PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest \
  -p xdist.plugin -o addopts= --noconftest -q \
  tests/test_structure_two_unified_acceptance.py::test_real_cli_refuses_environment_that_can_suppress_required_verification \
  tests/test_structure_two_unified_acceptance.py::test_real_cli_entry_accepts_current_code_and_legal_unchecked_cache \
  tests/test_structure_two_unified_acceptance.py::test_real_cli_stale_unchecked_entry_cannot_claim_restored_source \
  --junitxml=docs/reviews/pc_b/b8_w1_linux_compatibility_2026-09-13/entry_cache_subset_py312.junit.xml
```

正式缓存身份文件的阻塞复现：

```bash
env PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest \
  -p xdist.plugin -o addopts= --noconftest -q \
  tests/test_structure_two_runtime_cache_identity.py \
  --junitxml=docs/reviews/pc_b/b8_w1_linux_compatibility_2026-09-13/runtime_cache_identity_py312.junit.xml
```

环境命令：

```bash
uv python install 3.13.5
env TMPDIR=/workspace/scratch/b158d995e8cc/cpswm_b8_snapshot/tmp \
  uv sync --frozen --offline --check --extra dev --no-cache
```

另有一次以 `/usr/bin/time` 包装的初始尝试因该程序不存在而退出 127，pytest 没有启动；其空 stdout
和 stderr 原件保留在 `raw/`，不与真正测试结果合并。

## 证据索引

- `audit_results.json`：平台、解释器、来源、依赖与全部有效命令结果；
- `portable_engine_subset_py312.junit.xml`：14 个可移植协调器用例；
- `entry_cache_subset_py312.junit.xml`：8 个入口/环境缓存用例；
- `runtime_cache_identity_py312.junit.xml`：20 个被 3.13 前提阻塞的完整节点和堆栈；
- `TRANSFER_RUNBOOK.md`：在具备 CPython 3.13.5 的 Linux/WSL 新工作树复跑说明；
- `raw/runtime_cache_identity_py312.stderr.log`：不存在 `/usr/bin/time` 的初始启动器失败原件。

## 下一接收方

电脑 B 或 A 在可提供 CPython 3.13.5、完整冻结 checkout 和 `uv.lock` 对应离线缓存的 Linux/WSL
环境执行 `TRANSFER_RUNBOOK.md`。先跑 20 个缓存身份节点；通过后串行跑完整原生 115 和真实五阶段
链，保存 controller/worker runtime JSON、来源前后清单和所有双流。新冻结 SHA 出现时重新绑定，
不得用本报告的部分结果签署新版本。

当前没有从本 Linux 3.12 子集发现新的 W1 生产缺陷；“未发现”仅限实际到达的 22 个基础用例。
