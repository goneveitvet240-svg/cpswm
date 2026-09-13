# PC-B B4–B9 最终本地交接报告

日期：2026-09-13。本文是本次本地交接的权威摘要；同目录较早报告和失败日志作为历史证据保留，但不应覆盖本文结论。当前成果尚未形成 Git commit，也尚未推送 GitHub。

## 身份、环境与边界

| 任务 | 冻结交付 | 实际被测代码 |
|---|---|---|
| B4/B5 | `c366cad0a92593bb2c4c44db7e8d3408a2b5cc9c` | 该 SHA 加本报告列出的 B 有限修复 |
| B6 | `2a7a547fba30412d9349605aff3a7df7c60d6b3a` | `1d24099a025c9d7c00a59e4c78c593703924b0eb` |
| B7 | `6e07ab682a9ec15e959e1a50001e237877bc4773` | `57e8576c7dd48203839cdd0ae3a4cdb295db7185` |
| B8/W1 | `21870b0bcd6c23d43518a27fcc1c4b538b3912b7` | `6fcff45`（报告登记的实际代码） |
| B9/W2 | `329787241996631a6abb4fcd3b12d2c13a135777` | 历史代码 `d6112489`、保全 `de2c04c3`；本轮无新统一 SHA |

运行平台为 Linux 6.18.44 x86_64、CPython 3.12.14、LF 工作树；这不是 Windows B 实机结果，也不是 WSL2 复现。未修改 A 分支、`STATUS_A.md`、`TASK_BOARD.md`、共享集成分支、科学阈值或验收规则。GitHub 写权限不可用，因此计划分支 `codex/pc-b-adversarial-audit-fix-20260913` 尚未创建。

B4/B5 最终三个生产文件 SHA-256：

- `prototype_spine.py`: `f9a0bc926b1d28e37b364db96dee1fe0d5aa9fa6b8ebd6dcdd543808546f4a67`
- `structure_two_particle_workspace.py`: `7d7de3eae09d9c6c8dd12b287da96b34680e5bcd366c8bdaf9386fa87d568905`
- `structure_two_semantic_identity.py`: `1b7d75ceaafc845bee37029e41e10a93f899c03d98fb87b7b3549f52be29b680`

## B4/B5：两轮审核、修复与回归

确认并在允许的三个生产文件内修复：

1. 公开 `NativeParticleWorkspace.advance()` 可把与 runtime history 不一致的完整重封来源链写入持久状态。修复在写入前校验运行时来源，并保存脱离 caller 别名的链；拒绝后无 records/journal 副作用，合法重试成功。
2. 已持久 workspace 输入可连同 body/journal/source/fingerprint 一起完整重封而逃过三层校验。修复新增 core-owned 输入锚，并在 stage、readout、semantic identity 和 observable-state 边界复核。
3. staged cancellation restoration 和已发布 cancellation 记录可完整重封。修复增加内容拓扑校验、接收时摘要锚、checkpoint/rollback 持久化，并在统一序列化写入口持锁后、任何具体变更前复核；拒绝不会追加 replay receipt 或改变派生状态。
4. 长历史重复来源递归校验开销过高。修复只在单次事务内部复用已经验证的 persisted record/body 结果，每次公共调用仍重新做运行期篡改检查。

最终源码回归：

| 集合 | 结果 | 墙时 | 证据前缀 |
|---|---:|---:|---|
| 受影响集（含两轮、B5、native、47 边界、27 cancellation） | 103/103 | 59.584 s | `b4_b5_affected_final2_linux_py312_seed0` |
| 原六项 | 6/6 | 2.742 s | `b4_original_six_final_linux_py312_seed0` |
| 47 项增强矩阵 seed 0 | 47/47 | 10.428 s | `b5_matrix_final_seed0_linux_py312` |
| 47 项增强矩阵 seed 1 | 47/47 | 10.772 s | `b5_matrix_final_seed1_linux_py312` |
| 47 项增强矩阵 seed 8675309 | 47/47 | 10.475 s | `b5_matrix_final_seed8675309_linux_py312` |
| exact-812 最终运行 | 808 passed / 4 failed / 0 errors / 0 skipped | 721.667 s | `b4_exact_812_final3_linux_py312_seed0` |

锁分解在 Linux 轻载 9/9 低于 1 秒，外来线程接锁小于 0.31 ms，磁盘读取小于 0.08 ms。profile 显示每例 `_source_code_objects()`/`compile()` 重复 61 次，编译自耗时约 339–353 ms；四进程受控竞争 12 例约 478–621 ms，仍低于 1 秒。Linux 未复现历史 Windows `-n 4` 的 1.687–1.936 秒，故不能把历史失败归因于“Windows 慢”。优化点位于越界文件 `structure_two_execution.py`，本次没有修改，也没有提高 1 秒阈值或跳过来源验证。

长历史独立 recurrence（seed 7）在 N=4/8/12/16/20 的最终性能阶段墙时为 2.179/5.155/9.132/13.288/18.636 秒，最大数值误差不超过 `1.11e-16`，质量和为 1；N=20 为 40 records、深度 20、RSS 115,532 KiB。该 JSON 早于后续 cancellation 锚，必须按其记录的源码摘要理解，不冒充最终 cancellation 版本的性能复跑。

两个越界未修问题：

- 全新解释器冷导入 `prototype_spine` 受 `evaluation_operations.__init__` eager re-export 循环阻断；最小修复点不在允许的三个文件内，交 A。
- exact-812 最终 4 个失败均为 Ed25519 回滚快照问题：两个 verifier-key swap、PCHMP delegate replacement、authority mutation。失败发生在 `structure_two_production_system.py` 对 cryptography Rust public key 做 `deepcopy`。本环境为 cryptography 46.0.0，锁文件为 47.0.0，而 `pyproject` 声称 `>=46,<48`；应由 A 收紧依赖下限或实现安全的项目级 checkpoint，不可让 verifier deepcopy 返回自身。最终 JUnit 为 812 tests / 4 failures / 0 errors / 0 skipped，完整 stdout、stderr、JUnit 和结果 JSON 均已归档。

## B6：联合消费者与三个解析块

冻结 85 项通过直接兼容运行器等价展开为 85/85（明确不是原生 pytest）；25 个随机数学对照和 6 个非法矩阵负例通过。相同边缘、不同联合的合法分布产生任务 EVSI 0.4 对 0.0；原因 IG 都为 0，而完整联合 IG 都为 0.8 bit，证明两种信息增益不能混称。

确认问题：冷启动循环导入（高）；value object 可接受 caller 自选 runtime/source-frame，若升格授权 receipt 则为高风险；planner 不绑定 belief source snapshot digest（中）；空动作集合误报 privacy blocked（低）。静态扫描未发现组件进入默认生产路径，因此 prepared seam 通过不等于默认闭环实现。未修改 A 生产代码。

## B7：数据预检与泄漏

冻结 43 项直接等价执行为 43/43；真实训练盘点独立得到 24 世界、144 轨迹、49,428 步，与 A 登记一致。method-free：未运行方法臂、未训练、未读取 validation/confirmation。

确认三个高风险缺陷：语义相同但 UUID 不同的 actor evidence cluster 可重复计权；重复 JSON key last-wins 可把 confirmation 覆盖成 development 且 exit 0；允许 action 下的嵌套 `evaluator_truth.true_actor` 可进入方法侧产物。另有双时间合同风险：`received_at <= cutoff < metadata.recorded_time` 仍进入前缀。B 审核工具已修正退出语义，复跑结果为 delivery 43、defenses 3、vulnerabilities 4、probe errors 0，进程 exit 1；未吞掉 finding，未修改 A 实现。

## B8：W1 Linux 复现

关键文件 10/10 Git blob 匹配；Python 3.12 portable engine 14/14、entry cache 8/8，共 22/22 通过。正式 runtime-cache identity 收集到 20 个节点，但全部在 Python 3.13 前提处停止，应记环境阻塞/未评价，不能记为通过或产品失败。当前无 Python 3.13、完整冻结 checkout/controller/xdist 依赖；原生 115 和五阶段链未运行。证据包明确保留初始 launcher 失败原件，不把它冒充有效 pytest 双流。

## B9：W2 公平性准备

31/31 历史伪造见证均有 `before_sha256 != after_sha256` 和字段差异；30 项保持 source binding，1 项来源攻击改变 binding。它们只是历史结构核对，本轮 fresh replay 为 0、无新 JUnit，不能签动态验收。

公共地图/支持集、owner 先验、消费特征、预算/停止、解码、长期账本和实际动作等九个维度已追溯。future-location、AMG owner-prior 等旧结论只适用于对应历史版本。公开地图、共同/原生先验等六项仍需用户科研决定。没有 A 的单一统一冻结 SHA，结论保持 `PARTIAL / ACCEPTANCE PREPARED / UNIFIED ACCEPTANCE BLOCKED`。

## 分层结论与接收方

| 层次 | 结论 |
|---|---|
| 修复方工程回归 | B4/B5 Linux LF 受影响集、原六项、三 seed 通过；exact-812 见最终证据，不等于 Windows 验收 |
| 独立审核 | B6/B7 找到可复现问题；B8 只完成 3.12 子集；B9 只核对历史见证 |
| 默认能力 | 联合组件尚未进入 core 默认路径，真实动作—世界反馈闭环仍缺 |
| 统一验收 | 阻塞：缺单一统一冻结 SHA、Windows/WSL 3.13 复现与 W2 fresh replay |
| 科学收益 | 未训练、未跑正式方法臂或统一比较，不作收益声明 |

A 下一步：独立复核 B4/B5 三文件修复；处理冷导入、越界锁编译/Ed25519 checkpoint、B6/B7 finding；集成后发布单一冻结 SHA。具备 Windows/WSL 3.13.5 的接收方还需跑 CRLF/LF、三锁 `-n0/-n4`、exact-812、W1 正式 20 节点/115/五阶段链。用户只需裁定 B9 科学公平规则，不需要为工程缺口背书。
