# 跨机器复现与 SQLite 可移植性核查

2026-10-01，只读、有界核查。产品源码 `82c7a81fba0c3af3688978ce222b1b94e4cc5bd9`，工作树 `/private/tmp/cpswm-pc-a-archive-native-bridge-20261001`；原件目录为本文件所在目录。检查结束工作树 clean。只读取 REPRODUCE、执行 harness、环境记录、相关源码及历史交接；未执行 Windows、模型、Unity、Native、pytest 或数据重算，未联系 B，未修改产品或既有原件。

**结论：现有证据只支持原 macOS 环境的新进程 SQLite 恢复，不支持直接将原 DB 搬到 Windows 恢复。B 可以先做完整原件/hash 静态核验、源码审查与独立受控测试；冻结顶层 CLI 仍有明确的平台耦合，不能承诺换路径即可重建或复现。**以下为静态确认的代码限制，不冒称实际 Windows 失败实验，也不改变当前 A 同环境审核结论。

## 1. 原 DB 为什么不能直接作为 Windows 工作状态

| 精确源码入口 | 已确认约束 | 跨机后果 |
| --- | --- | --- |
| `tools/run_archive_native_bridge.py:604` `run_arm`，`:622–627` | 原 configuration 写入 `str(checkpoint.resolve())`，随后把整个 config 纳入 `source_identity` | Mac 绝对 checkpoint 路径不可直接用于 Windows；修改路径会改变已有 deployment 身份，不是透明迁移 |
| 同文件 `:337` `open_case`，`:351–354` | 校原 config 内容摘要；`dependency_identity=content_sha256(sys.version)` | Windows 的构建/编译器字符串不同，即便都叫 Python 3.13.5 也不能推定身份相同 |
| `src/cpswm/system/continuous_state_store.py:21–68` | checkpoint 与 deployment 同时要求 source/dependency 精确匹配；否则明确要求 migration | 不应编辑 DB 中身份或重签 config 来绕过；“SQLite 文件能打开”不等于 CPSWM 可恢复 |
| `structure_two_continuous_input.py:1491` `resume` | 原 joint binding、implementation、checkpoint state、raw/visual sources 全部复核 | 即便绕过路径，也仍有真实依赖/状态闭包要求 |
| `native_joint_production.py:126–213` `python_dependency_implementation_binding` | 全 MRO 方法、源码字节及 loaded-code 指纹 | 源码相同不自动等于不同解释器上的加载代码相同 |
| `structure_two_execution.py:461–489` | 指纹包含 bytecode、constants、line/exception tables 等 | CPython 版本/编译结果是相关依赖；该 payload **没有**包含 `co_filename`，因此不能把单纯移动源码路径说成一定改变此 loaded-code 指纹 |
| `data_preflight/proposal_inference_session.py:60–75` | 参数、实现、Torch 版本、CPU device、thread count 进入推理绑定 | 新平台不能用“模型文件相同”替代整个原推理环境；同版本也未证明跨平台逐位结果一致 |
| `continuous_state_codec.py:28–37, 130–179` | 只接受当前已经加载的 CPSWM 类型，JSON 对象图恢复 | 无 pickle 不代表任意环境通用；纯 resume 的类型导入闭包仍须验证 |

`runtime-environment.json` 记录 A 为 Python `3.13.5 (main, Jun 12 2025, 12:22:43) [Clang 20.1.4 ]`、macOS 26.4 arm64、NumPy 2.5.2、SciPy 1.18.0、Torch 2.13.0、TorchVision 0.28.0、Pydantic 2.13.4。它记录已使用环境，不是 Windows 已通过环境清单。`pyproject.toml` 的宽版本范围也不是精确复现 lock。

原 DB 保留为证据，只读静态查看或在同匹配环境的副本上恢复。`run_archive_native_bridge.py:776` 的 `verify_saved_consequences` 正是拷贝 DB 再 `open_case(...resume=True)`，且验证原文件 inventory 未改。B 不应直接对原 DB 调用 `ContinuousStateStore`：构造函数本身会执行 schema/PRAGMA/commit，并非只读分析器。

从零建立 B 的新配置、SQLite 和 runtime ID 与恢复 A 的原 DB 是不同实验。CIAV 会生成新的运行时 UUID；当前工具的语义/数值对照不是承诺不同从零运行 DB 逐字节相同。

## 2. 顶层从零运行也不能只换路径

**路径成员名是静态明确的原生 Windows 障碍。**

- `tools/diagnose_offline_frontend.py:45–58` 的 `inventory/source_identity` 用 `str(path.relative_to(root))` 生成键。
- `tools/collect_offline_factor_data.py:42–47` 与 `:383–397` 同样如此。
- `tools/verified_position_parent.py:67–105` 又把得到的键集合与 `frames/000/public.json`、`models/...` 等固定 POSIX 名字及外部 ledger 精确比较。

原生 Windows 的 `Path` 相对字符串使用反斜线；原 Mac 清单使用斜线。因此冻结代码的比较逻辑不是一个已经实现的平台无关归档协议。不能为了通过而修改原清单、source map 或外部 pin。源文件换行也要保持：当前树未发现 `.gitattributes`；所读 STATUS_B 的旧记录提到 `core.autocrlf=true`，只是历史信息，不能推定 B 当前仍如此。B 应在 checkout 前明确禁用自动 EOL 转换并逐文件核验。

**历史 collection verify 绑定了原运行环境，而不只是读数据。**

- `verified_position_parent.py:194–235` 构造白名单历史 `run_soft_position_development.py --verify`，不执行 ledger 任意 argv。
- 该历史链继续到 controls、affinity、frontend，最终 `diagnose_offline_frontend.py:60–98` 启动固定历史 collection verifier。
- `collect_offline_factor_data.py:50–72` 的 `runtime_identity` 会真正启动所给 `sdk_python`，导入 ai2thor，取得完整 `sys.version`、ai2thor/NumPy 版本与全部 SDK Python 文件摘要，并读取解释器可执行文件及 Unity binary 摘要。
- `collect_offline_factor_data.py:376–399` 把这一当前环境身份与原 collection configuration 精确比较。

当前 harness 的 `--sdk-python` 是项目 `.venv-ai2thor/bin/python`，Unity binary 是原 `thor-OSXIntel64-...app/Contents/MacOS/AI2-THOR`。即使只验证旧归档、不启动 Unity，相同 runtime gate 仍要求原 SDK 解释器能执行及原指纹相同。Windows 的新 Python 可执行文件不等于该 Mac executable；把原二进制搬过去只可保留字节证据，不能因此运行它。WSL 会解决部分 POSIX 路径表示，**不会自动消除 Mac Python/runtime 指纹耦合**；当前未测试 WSL，也不推荐把它说成现成解决方案。

`verified_position_parent.py:201` 刻意保留虚拟环境 executable 的绝对路径，避免 `.resolve()` 丢掉 venv，这是同机环境选择的正确处理，但不使 Mac venv 跨平台可执行。macOS `.venv` 和 worktree `.git` 指针均不得搬作 B 环境。

## 3. B 当前可真实执行的最小复核路径

1. **保留原件，先核摘要。**从 GitHub 获取明确冻结 SHA 和交接资料；在独立 `codex/pc-b-*` 工作目录检出，保持 LF 字节。解压副本，不覆盖原目录；逐项核原外部 case-ledger/inventory pins、所有原文件内容、模型/manifest、901 文件 source map、两审绑定和输出完整集合。以 `PurePosixPath` 解释归档成员名并在本地安全定位，检查越界/重名/符号链接；这是独立只读检查，不能改写 frozen CLI 或旧清单。此步骤可在 Windows 用标准库另写审查脚本，但脚本与结果必须单独记录为 B 核验。
2. **独立重建本地环境并运行受控源码测试。**记录实际 Python/Torch/NumPy/平台/EOL；使用 B 的新 venv，安装所需 dev/perception 依赖，确认版本可获得而不预先承诺。候选命令为 `python -m pytest -c pyproject.toml tests/test_verified_position_parent.py tests/test_archive_native_bridge.py tests/test_native_raw_candidate_verification.py tests/test_native_log_weight_continuation.py`。pytest 配置已有 src/tests/tools 路径；Windows 手工设 PYTHONPATH 时用分号，不能复制 POSIX `src:tests:tools`。这些测试可能有路径、耗时或依赖限制；必须记录真实结果，不把 A 的通过数移植成 B 通过。
3. **不要直接宣称端到端归档复现。**在冻结顶层入口的 parent verification 遇到上述 path/runtime gate 时，保留原命令、异常、输出及源码身份，记为“跨平台验证适配未完成”。不得 mock 原 collection verifier、返回 exit 0、重签 ledger 或删 runtime 检查后称原协议通过。
4. **完整 B 从零归档运行需后续独立适配轮。**该轮须把“原采集 provenance 的字节核验”和“当前验证机环境”明确区分，保持原 pins；规范归档路径格式；用新的审查/测试证明没有放松原件与来源要求。数值逐位差异若出现，应单独调查并预先定义工程比较规则，不能事后放宽到通过。然后才在 B 新 output、新 config、新 SQLite 上运行四模型/无因子及裸点对照、fresh verify、独立算术；这是 B 新运行，不能称 A 原 DB 迁移。

静态完整性、受控测试、归档重算、独立仿真采集和科学验收分别记录。B 尚未被本文件调用或执行任何操作。

## 4. REPRODUCE 建议补充的准确措辞

> 当前 SQLite fresh resume 只在所记录的 A/macOS 环境验证。原 DB 含配置路径、完整 Python 环境和实现依赖绑定，不支持直接搬运到 Windows；保留原件，不修改 config/DB/pins 绕过。B 可先独立核完整归档/hash、审查源码并在新环境跑受控测试。顶层历史 verify 仍与 POSIX 清单名称、原 SDK Python executable/runtime 及 Mac Unity binary 指纹耦合，不能承诺换路径即可复现。跨平台端到端复核需要另轮受审适配及实际运行；本轮未完成该适配，也未完成 B 验收。

现 REPRODUCE 已正确写出 A 本机/B 未验收、原 DB 副本验证、原 pins 不可改及新输出目录要求；建议在“按原 argv 换路径复现”附近加入上述限制，避免读者推断 Windows 已可直接运行。产品源码本轮不改。
