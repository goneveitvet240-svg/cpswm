# PR128 第三方视角审计：3 项缺陷仍开放

2026-10-26，电脑 A 执行。采用第三方审计的反例方法，但本机也是先前实现方，**不冒称电脑 B、独立机构或全面验收**。

**结论：当前候选存在可复现的执行状态机缺陷，以及两处证据核验漏洞；不能认定为可靠、可验收的完整闭环。** 新增审计工具和证据，生产代码保持不变。三个问题没有在本轮修复。

## 版本与证据身份

- fetch 成功，审计目标：PR128 / `90e6c60009e17226b1a58f31245dcd04b810b23a`。
- 共享集成仍是 `19ddf26830348a2f0b33f0af54d6ba702c5cfb1c`；B 分支仍为 `fd4ca6ef5e81c90d7cf7987b42c0b2810d8a810a`。候选与集成分别记录，不把 PR128 称为已集成。
- 审计分支：`codex/pc-a-third-party-audit-20261026`；独立工作树 `.local/simulation-stack/cpswm-third-party-audit`。
- 新 smoke 实际执行于开工文档提交 `770bd7c`（完整 SHA 在 evidence/source_binding.json），其所有既有 src/tools/configs 与被审计版本一致。
- 可重复审计工具提交：`d6aa33464f7117e465722f5cd4353ebc026a8683`。该版本仅比目标多审计工具及开工文档，既有生产代码、核验代码和配置不变。
- 原复验数据仍绑定 `a5f3b024f23f870753b8f8ac78da18def04e4f47`；来源核验实现继承 `2ea1e97b7f0848569186cd72a3246e71af1bb4e5`。不把旧数据声称为本次重新运行了全部推断状态。

## A1 / P1：原生来源合法撤回后，已执行动作无法结算

位置：[goal_control.py:217–230](../../../../src/cpswm/simulation/goal_control.py)，关联同文件 181–186、204–207；[structure_two_memory_action.py:214–246](../../../../src/cpswm/system/evaluation_operations/structure_two_memory_action.py)。

触发序列使用公开方法，无篡改内部粒子：

1. 从已有 D0 生成器建立四步合法原生状态，接入 `NativeGoalMemory` 和控制器；取得计划。
2. `record_step(plan, 101)` 记录已经完成的一步。
3. 来源拥有者调用合法的 `revise_location_source(source_id, expected_digest)` 撤回已支付位置来源。调用成功，`verify_internal_contracts()` 通过，live memory revision 改变。
4. `feedback(plan, valid_feedback, 1)` 因旧 revision 被拒绝；`record_step` 同样被拒绝；`plan(102)` 又要求先结算旧段。pending 保留、step_ticks 为 `[101]`、completed_commands 为 0。

合法对照把相同撤回放在 feedback 之后：旧段完成、新计划 ready。只有发生顺序改变就会卡住；不是伪造命令、错误对象或无效撤回。

影响：原生 live API 在执行中收到合法纠正/撤回时，缺少“停止继续执行，但保留并结算已发生动作”的路径。安全拒绝旧动作是必要的，但不能同时拒绝已发生事实的结算。当前固定三步前缀的 CLI worker 没有更新 RPC，所以**没有声称之前的固定前缀物理实验已经触发它**；它直接阻碍后续持续更新闭环。

修复要求：把继续执行授权与已执行段的事实结算分开；或者在原生更新入口统一排队，在结算后应用更新。不得通过恢复已撤回错误来源、清空 receipts 或重执行物理动作来“解锁”。加入执行前、一步后、整段后撤回/恢复/新观测的状态机测试。

证据：[state-result.json](evidence/state-result.json)。本反例只模拟执行器回执时序，不把该状态机测试冒充真实机器人执行；真实五步物理实验属于 A2。

## A2 / P1：原生核验可将 smoke 错标为 π0.5，并接受不存在的源码身份

位置：[verify_native_pi05_probe.py:9–79、94–104、119–123](../../../../tools/verify_native_pi05_probe.py)。

执行真实 LIBERO + SAM 的 **5 步 SmokePolicy**，1 次 smoke 推理、6 帧视频，任务未成功。合法原件分别通过 core 和 physics。然后仅复制实验目录，在副本改四项：

- manifest.sha → 40 个零（不是有效运行提交）；
- manifest.sources → 空字典；
- manifest.policy → `pi05-local`；
- summary.pi05_inference_executed → `true`。

保留真实相机、动作、输入/输出数组、EEF、反馈和视频；没有 π0.5 metadata 文件，也没有调用 π0.5。这个完整副本仍通过 **core 和 physics 两个核验**，physical_replay=true、actions=5、video_frames=6。

原因：core 不读取运行 manifest；physics 只比较两个可同时修改的策略标签，并对本地 checkpoint 清单做 hash 比较。Smoke runner 本来也记录相同模型清单 hash，因此模型文件存在不等于执行过模型。两者都没有验证 manifest 的实际源码 SHA、必需文件清单及运行源码绑定，也没有验证保存的输出来自所声明策略。

影响：核验成功最多证明所存动作与重放物理一致、核心请求可重放，不能独立证明“某源码运行过 π0.5”。**这是核验漏洞，不是发现以前 π0.5 实验造假；也没有构造虚假的任务成功。** 已提交原件的外部 Git/归档 hash 校验仍能检出文件被改；本反例证明 standalone 核验无法承担来源声明的完整验收责任。

修复要求：先验证受信预期提交、必须的源码/模型/分词器/配置清单与实际执行字节；绑定原始运行来源，检查非空合法策略和必要 metadata。若要独立确认模型输出，需保存推理随机性并进行固定输入/权重的可重复推理核对，或由受信运行器提供可核查执行证据。补 metadata 的格式检查本身不够。在做到之前，把物理一致性和策略来源未验证分别报告。

证据：[native-result.json](evidence/native-result.json)、[smoke-physics.json](evidence/smoke-physics.json)、[forged-physics.json](evidence/forged-physics.json)，原件与副本完整保存在 `evidence/native-evidence.tar.gz`。

## A3 / P2：冻结配置未绑定 Git 协议，篡改统计规则仍获核验通过

位置：[analyze_reliability_replication.py:101–117、277–284](../../../../tools/analyze_reliability_replication.py)，[verify_reliability_evidence.py:27–37、79–82](../../../../tools/verify_reliability_evidence.py)。

先对原始 source.json 的 frozen 内容与运行 SHA 下的 FROZEN.json 做逐字段比较，确认原件相同；重新分析和来源核验均通过。随后仅在副本把 `bootstrap_draws: 10000` 改为 `1`，原始 768 点 gzip 字节完全不变，源文件清单与其中 FROZEN.json 的 hash 也不变。

重新分析后，联合候选对最近主人基线的描述性 95% 区间从 **[-39, -15]** 变成 **[-23, -23]**。完整来源核验仍通过：750 文件、768 输入/真值重生成、配对统计、36 前缀和 109 中断记录比较均通过。原始负收益计数仍为 69 对 42、修正 3 / 损害 30、净 −27。

原因：`verify_sources` 验证声明清单里的 Git blob，但没有将 manifest.frozen 与已验证的 FROZEN.json 内容比较；分析器直接消费可改写的 frozen 字段。最后的 summary 校验只比较 errors/paired，没有独立校验 uncertainty 和其他展示字段。

影响：冻结的统计规则可以被意外改写或后改后算，核验输出仍呈现通过。本次没有把负收益改成正收益，也不推翻原始报告的计数和原始区间；漏洞是缺少可执行的协议绑定。

修复要求：从受信版本的 FROZEN.json 读取/验证实际配置，要求精确匹配并核对必需清单；对声明已验证的全部 summary 字段独立重算，或明确列出未验证字段。测试须包括改 bootstrap 次数、bins、种子/条件、直接改 summary 和删除 manifest 必需条目。

证据：[protocol-result.json](evidence/protocol-result.json)、`evidence/protocol-evidence.tar.gz`。完整输入原件引用 PR128 已提交归档及本轮 manifest 中的原件 hash，不复制或覆盖原始实验。

## 已知工程阻断与科学结果

当前目标 SHA 的 GitHub static-quality **FAILURE**：Ruff 通过，mypy **130 errors / 8 files / 430 checked source files**。原始日志：[pr128-static-quality.log](evidence/pr128-static-quality.log)，[失败 job](https://github.com/goneveitvet240-svg/cpswm/actions/runs/40209825473/job/121218474190)。这是现存类型/工程债务，不等于 130 个运行时 bug，也不是本次只读审计引入的问题。current-inputs 在本轮读取状态时仍运行，完整 test 尚无本次通过证据；不得签署全仓验收。

上一轮候选净多错 27 是科学/效果上的阴性结果，本轮原件重算再次一致。它与以上三个程序缺陷分别成立：即使修完核验和状态机，也不能推断科学收益自动转正；仍需原有等预算冻结比较。正确支持被错误习惯覆盖的归因尚需机制干预验证，本轮不擅自选择新权重/先验或缩减路线。

## 覆盖和未覆盖

| 检查 | 本轮证据 | 边界 |
|---|---|---|
| 原生记忆/目标/来源已有回归 | 45 passed，exit 0 | 三文件定向套件，不是全仓 |
| 合法正路径 | 撤回前先结算可继续；原 smoke 核心/物理；原冻结协议来源核验 | 局部合法对照 |
| 完整伪造路径 | smoke→π0.5 重标、无效源码身份；改冻结配置并完整重算 | 证明两个核验漏洞仍开放 |
| 依赖与工程门 | 当前 CI 原始失败日志，环境和源绑定记录 | 没重跑全部模型/七算子依赖矩阵 |
| 账本和状态机 | 合法来源撤回、内部契约通过、已执行段卡住 | 未穷尽所有取消/恢复/中断组合 |
| 动作后果 | 新 smoke 五步实际 LIBERO、独立物理重放 | 无新 π0.5 推理/训练/多臂收益实验 |
| 统计 | 768 输入/真值及算术重生成；原区间与副本区间 | 推断状态仍仅既有 137 唯一重复点；无第二次全量状态复跑 |

对象绑定的初步怀疑已被 `SimulationMemory.ingest` 的 `object_id == target` 检查及已有测试挡住，不列为缺陷。没有将低收益、缺类型标注或未覆盖路径全都当作代码 bug。

建议修复优先级：A1 已执行事实结算；A2 源码/策略来源核验；A3 冻结协议/统计绑定；同时清理现存 CI 阻断。然后在新源码上重新审计，再谈统一验收。全部 E0–E6、H/R/I/C/Z/r/V、三个 RB blocks、七算子、隐藏事件、多人物、开放世界、可逆归因及具身反馈范围保留。**本次为部分覆盖、3 项 OPEN，不是“没有更多问题”的结论。**

[复现命令](COMMANDS.md) · [证据清单](MANIFEST.json)
