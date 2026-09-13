# PC-B B4–B9 接续审核记录

更新时间：2026-09-12T18:07:08Z。本文记录当前隔离执行环境实际完成的只读核验与诊断；不是 Windows B 实机结果，不是统一验收，也不签科学收益。

## 远端冻结与所有权

GitHub 连接器成功解析仓库 `goneveitvet240-svg/cpswm`。下列分支 HEAD 与任务登记完全一致，未发现新提交：

| 任务 | 分支 | 冻结 SHA |
|---|---|---|
| 集成 | `codex/dual-pc-handoff-20260912` | `bdec3ee21b7db361e390496d97ff2eb30390dc6c` |
| B4/B5 | `codex/pc-b-w3-five-boundaries-fix-20260912` | `c366cad0a92593bb2c4c44db7e8d3408a2b5cc9c` |
| B6 | `codex/pc-a-native-joint-consumers-20260912` | `2a7a547fba30412d9349605aff3a7df7c60d6b3a` |
| B7 | `codex/pc-a-data-preflight-20260913` | `6e07ab682a9ec15e959e1a50001e237877bc4773` |
| B8 | `codex/pc-a-w1-cache-runtime-r6-20260912` | `21870b0bcd6c23d43518a27fcc1c4b538b3912b7` |
| B9 | `codex/pc-a-w2-acceptance-prep-20260912` | `329787241996631a6abb4fcd3b12d2c13a135777` |
| A 活动 | `codex/pc-a-proposal-scheduler-20260913` | `ac8bab46c2eeec46de89288199c5c6ce1edc6a10` |

B6 的实际代码 `1d24099a025c9d7c00a59e4c78c593703924b0eb` 到交付 SHA 仅增加 `STATUS_A.md`；B7 的实际代码 `57e8576c7dd48203839cdd0ae3a4cdb295db7185` 到交付 SHA 同样仅增加 `STATUS_A.md`。B 原窗口的五项边界分支已经交付，故本窗口没有与其并发生产写入。

当前连接只有读取权限，不能推送分支或创建可用 PR。终端 `git clone/fetch` 被运行平台策略以 HTTP 403 拒绝；这不是仓库不可读。未修改 A 分支、`STATUS_A.md`、`TASK_BOARD.md` 或共享集成分支。

## 执行环境

- Ubuntu 24.04.3 LTS 隔离容器，Linux 6.18.35，x86_64；不是 Windows，也不是可验证的 B 实机 WSL。
- 9 个在线逻辑 CPU；约 21.14 GiB 可用内存、32.03 GB 可用工作区磁盘；采样时轻载。
- CPython 3.12.14、Git 2.51.1、uv 0.12.11；无 GPU、无 Windows/WSL 挂载。
- 基础环境无 pytest/xdist。`uv pip install` 访问 PyPI 返回 403，所以不能原样复跑 47、812、85、43、W1 或 W2 pytest 矩阵。
- 通过 GitHub 连接器逐文件物化 B4 冻结快照的 311 个 `src/` 文件和 11 个相关测试/配置文件；本地 322/322 个文件的 Git blob SHA-1 与 `c366cad0…` 远端树一致，0 缺失、0 漂移。绑定清单见 `REMOTE_TREE_MANIFEST.json`。

## B4：旧修复与锁问题

已独立读取并解析交付报告、命令、结果 JSON 与 JUnit，而非只接受摘要：

- 原六项修后 6/6；增强矩阵 seed 0/1/8675309 各 47/47。此处属于旧修复方证据复核，不是本窗口重跑。
- 首轮 `2350602…`：CRLF 800/812，LF 804/812。CRLF 九项由四个冻结文件的 LF→CRLF 原始字节变化解释；LF 后剩余五项暴露 Windows `str(Path)` 反斜杠与冻结 POSIX 路径直接比较的单一根因。
- 锁修复后 `ccf2cf0` 的完整 CRLF `-n 4` 仍为 800/812；三项锁耗时 1.687、1.825、1.936 秒，仍违反 1 秒合同。其余九项仍为 CRLF 原始字节身份前提。
- JUnit 证明锁失败停在 `caller.is_alive()`，没有走到正常回滚指纹断言；因此不能从该失败单独判断锁等待、前置计算或调度竞争各自占比。

新增 `tools/b4_lock_timing_probe.py`，使用真实冻结生产实现和真实测试构造器，但不依赖 pytest runner。Linux/Python 3.12 单进程轻载三轮结果：core/wrapper/ccrr 共 9/9 均在 1 秒内结束，总耗时约 403–584 ms；其中进入 sink 前约 398–573 ms，worker 接锁约 0.17–0.26 ms，sink 返回到失败结束约 3.8–7.2 ms。工作区磁盘 SHA 单次约 0.028–0.064 ms，完整 `_check_particle_workspace_binding()` 通常约 0.116–0.213 ms，单个观测离群值 0.886 ms。原始结果见 `lock_timing_linux_py312.json`。

该对照说明本 Linux 环境没有等待外来锁释放，且单次磁盘读取/工作区绑定检查不是这里的主耗时；约 98% 时间发生在 sink 前的正常事务、追踪与身份链。它不能解释 Windows `-n 4` 的额外 1.2–1.5 秒，也不能替代同解释器、同平台、同负载的受控分解。因此目前不修改三个生产文件，避免在证据不足时引入新回归。

后续在完全独立的 profiled 三例中进一步定位了 sink 前耗时。每例
`bind_runtime_callable()` 调用 61 次，累计约 374–391 ms；其下
`_source_code_objects()` 61 次、内建 `compile()` 61 次，`compile()` 自耗时约
339–353 ms。内容哈希 569 次累计约 143–150 ms；`deepcopy` 累计约
31–33 ms；单次工作区磁盘 SHA 仍仅约 0.029–0.070 ms。profile 会增加观测
开销，因此这些累计值不能与无 profile 墙钟直接相加，但三个锁目标均显示
同一排序。原始结果见 `lock_timing_profile_linux_py312.json`。

该受控分解排除了“等待外来锁”和“单次磁盘读取”为本 Linux 样本的主因，
并把 1 秒余量风险定位到锁交接前重复的 callable 源码解析/编译及身份哈希。
`_source_code_objects()` 位于 `structure_two_execution.py`，超出本次 B4 的三个
生产文件范围；本窗口只交最小复现和修复建议，不顺手缓存或绕过运行时篡改
检查。建议 A 在保持每次来源真实性校验的前提下，消除同一不可变源码在一次
事务内的 61 次重复 AST 编译，并在 Windows 3.13.5 的 `-n 0/-n 4` 冻结环境
复测 1 秒合同。

另做四个独立进程的受控资源竞争对照（每进程依次运行 core/wrapper/ccrr，
不是同时运行其他项目重负载）。无竞争九例墙钟约 `424–475 ms`；四进程组的
十二例约 `478–621 ms`，全部仍在 1 秒内结束，外来线程接锁均小于
`0.32 ms`。Linux 上受控并行增加了约几十到一百余毫秒，但没有复现 Windows
`-n 4` 的 `1.687–1.936 s`。因此“并行资源竞争”是可测放大项，却不足以单独
解释历史 Windows 超时；需要在 Windows 3.13.5 以相同 profile/无 profile
配对复跑。原始结果见 `lock_contention_linux_py312.json`。

## B5：覆盖审核

现有 47 项已覆盖合法初代/二代、未知与未决质量、地点-alpha 配对重排、同一输入重放、世界支持替换、完整重封伪谱系、统计闭包、重复粒子/proposal、跨 runtime 移植、实例数据篡改、持久账本交叉关系、异常中断回滚和内容式状态复制。

仍缺独立长状态机证据：延期、晋升、纠正、撤回、取消、恢复的同一连续历史；陈旧整批重放；proposal/统计/投影来源分别缺失和多余的全组合；实例/类方法替换的完整正负对；长历史下账本、动作后果、时间和内存增长。详细矩阵见 `B5_COVERAGE_MATRIX.md`。因 pytest 不可用，本轮只建立覆盖表，没有用重复绿色案例凑数。

## B6–B9

| 任务 | 已核验证据 | 本窗口结论 | 阻塞 |
|---|---|---|---|
| B6 | A 交付日志为 85 passed；代码/交付 SHA 关系成立 | 组件交付不能证明默认完整联合主干；prepared 接缝与默认生产路径必须分开 | 无 pytest；未独立运行 85 项及同边缘不同联合的新增数学对照 |
| B7 | A 交付日志为 43 passed；报告登记 24 世界、144 轨迹、49,428 步 | 可见前缀已声明双时间与泄漏边界；真实统计仍需独立重算 | 本环境没有授权训练数据、原工作树和 pytest；不得以合成样例替代盘点 |
| B8 | W1 报告登记 86 短矩阵、115 原生保护及五阶段链 | 当前 Linux 容器不等于 B 实机 WSL，不能签跨平台复现 | W1 完整源码/运行包、pytest/xdist 与 controller 环境不可用 |
| B9 | A 准备矩阵明确 `unified_comparison=BLOCKED`；历史 31 项登记为非 no-op | 只能记验收准备；未取得单一统一冻结 SHA，不能拼接多分支签公平/科学结论 | 无新统一源码、新包和实际 31 类重放；公开支持/共同或原生先验仍属用户决策 |

## 接收方与下一步

1. 在可运行 Git/PyPI 的 B Windows 工作区，以同一冻结 SHA 建立 CRLF 与 LF 两个干净工作树；先独占复跑三锁和完整 812，再加入阶段时间戳，分离 sink 前计算、锁恢复、重复来源校验、磁盘读取、历史递归与 xdist 调度。
2. 将本探针移交 Windows 3.13.5 环境运行；比较 `-n 0`、`-n 4` 且不并行其他重负载。阈值保持 1 秒。
3. A 发布单一统一冻结 SHA 后，B6/B7/B8/B9 才进入真实独立运行与新包重算。
4. 当前 GitHub 身份需获得 push 权限，或由有权限的 B 工作区接收本报告与探针后推送 `codex/pc-b-*` 分支并创建草稿 PR。
