# 结构二窗口二：比较合同与动态生产路径开发诊断（2026-09-12 14:15 批次）

状态：**PARTIAL——完整机制、实际环境执行、公平性及科学收益未建立**。本轮两个正式入口重放及 77 项工程回归均通过，详见第 8 节；不能用该结果替代科学门。

## 1. 固定来源与本轮边界

- 工作树 `/private/tmp/s2-comparison-audit-window2-20260911`；分支 `codex/s2-comparison-audit-window2-20260911`。
- 开始实际 HEAD 与审查起点一致：`45850dc680cb83169c3108d6a1a5455f7e069457`，开始无未提交修改。无 reset、覆盖或合并。
- 本轮最终实现提交：`d611248`（初始实现 `7202416`，另有序列化修复提交），准确完整 SHA 见本批 `source_version.json`。源码修改只有主审计接入、窗口二公平性检查和新动态模块；新增一份测试。两个 CLI 和执行来源保护文件均未修改，生产七算子、正式方法 adapter、配置、阈值、数据划分均未修改。
- 原生解释器 `/Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/.venv/bin/python`，Python 3.13.5。声明根和实际执行根相同；正式入口输出完整已加载模块路径、源码/编译码摘要和解释器身份。本次共绑定 401 个源码/配置/历史依赖。补充乱序测试提交 `e8b5cee` 只改测试，运行时绑定仍为 `d611248` 的同一字节；准确测试 SHA 同在 source_version.json。
- 完整阅读第四轮复核、完整框架、P5/路由决策记录、最终效用冻结协议。未加载任何窗口三外部工作树；本轮测的是本分支固定生产实现，不声称测试了窗口三最新交付。复核中窗口三快照的结论只作为问题背景。
- 旧诊断及 benchmark 共 332 个受保护文件逐字节不变；见 `preservation_before.json`、`preservation_after.json`。旧包没有改来源字段以“修绿”。

下文证据目录统一记作 `E = docs/reviews/data/structure_two_comparison_dynamic_window2_2026-09-12T1500`。正式新包是 `E/bundle_v5`。首批 `structure_two_comparison_dynamic_window2_2026-09-12T1415/exploratory_scenes_v3.json` 是早期构造调试产物，不是最终包；其小模型参数与最终独立验证选择不同，不能混合比较。

## 2. 比较合同是否明确

**部分明确。** 不能把开发三臂配置中的“combined utility 不聚合”扩张为最终效用尚未决定。最终 PCT（惩罚完成时间）及污染、恢复、安全、隐私护栏和重放容差已经冻结。

| 项目 | 合同分类 | 真实路径及当前差异 | 影响／处理 |
|---|---|---|---|
| 公共地图或因果前缀支持集 | 尚未决定具体权限 | `project_two_action_benchmark._locations` 在 `known_location_ids` 为空时扫描整集；旧 D0 1040 步带未来支持；三臂相同 | 新开发场景显式向所有臂提供同一完整公共目录，仅是本次受控条件，不授权正式改协议 |
| 缺失 owner 时先验 | 尚未决定统一规则 | P5 均匀；AMG 无 owner 估计时回退最后检测；真实 missing-owner 触发独立重放 | 保留原结果与共同均匀先验诊断，差额仍为 17 步；没有修改冷启动算法 |
| 可见证据／特征权限 | 已冻结共同可见输入；实际特征消费有差异 | 同一个 packet 和 typed visible step；`fairness_execution.consumer_probe` 记录实际特征值、actor likelihood 和属性读取，不能只看配置 | P5 消费 transition/actor/mechanism/role，learned 用 12 个特征和历史计数，AMG 用其既有状态规则；权限匹配不等于表达或容量匹配 |
| 数据划分和访问时序 | 已冻结 | 20 train / 20 validation / 60 opened test；640 训练行；TRAIN 拟合，VALIDATION 独立选择，动作提交后才评分 | 保留上一轮修复的实际 `SplitAccess` 消费入口。原历史入口提前读取验证真值的问题未被历史文件重写 |
| 公共类型化解码、平局与任务语义 | 已冻结 | 同一 decoder；UUID 字典序平局；SEARCH=current location；PUT_BACK=owner habit | 新增目标实例检查。没有改共同解码器或通过新读出替代正式结果 |
| 目标物体绑定 | 实现违反合同的边界被发现 | 换同类别物体 ID 时，P5 核心拒绝；两个基线原 adapter 仍以 episode 首物体为目标输出 | 本窗口在实际解码／提交检查中拒绝不匹配后验，不能将其计为正确比较。未修多实例路由或基线内部状态 |
| CIAV 候选、时序、成本、隐私 | 已冻结 | 每步一个外生预提交 micro_verify；共享观测结果先于动作；五项成本为 0，隐私预算 1；真实 packet/receipt 对账 | 不改变合同。独立同／异位置探针明确在原单 packet 比较之外；零成本不能解释真实净效用 |
| 参数／训练／推理／延迟 | 框架匹配要求已明确；具体数值预算尚未决定 | learned 64 个活跃 logit 参数，9 格位置头；P5、AMG 不同状态规模和计算；保留 fit、在线范围与硬件记录 | 不能以信息匹配推断等算力；本批并行回归墙钟不作算法优势证据 |
| 最终科学效用 | 已冻结，未运行 | `structure_two_final_utility_guardrail_external_validation_protocol_v0_1.json` 的 PCT、护栏、full-rerun equivalence 原文进入机器清单 | D2 pilot 的具体时长待合法获得；不重选指标、不启动密封确认 |

机器清单 `E/contract_matrix.json` 给出逐项依据、选项、影响与最小区分实验。执行取证在正式包的 `fairness_execution`、旧 D0 行和新动态逐行 visible/packet/arms 中，不以清单自述代替执行。

还需用户决定的只有真正未决规则：

1. 支持集选显式公共地图，或共同因果前缀。最小区分实验：固定早期可见前缀，仅替换后续地点，检查早期支持与动作变化；先明确权限再作新的比较。
2. 缺省先验采用共同显式先验，或保留方法默认并报告冷启动分层。现有 53 步开发对照已能区分，不需新开确认集。
3. 具体参数／训练／推理／延迟数值预算：同预算独立调参，或沿已冻结 PCT–online-compute Pareto 设计多档预算；需在隔离资源条件下运行，不能用并行窗口的墙钟替代。
4. 恢复原生 SEARCH 差异的适配契约：可以共同声明因果模型后验加同一观测更新规则，或把直接可见与遮挡 SEARCH 分开报告；**公共 typed decoder 和共享 CIAV 合同保持**。这是未来修改建议，不是本轮已批准切换。

## 3. 场景、非空条件与真实结果

`structure_two_comparison_dynamic.PLANS` 在最终代码版本中固定输入序列、路径、应变项、应不变项和非空条件。六个主场景统一为 14 个输入，避免不同 episode 长度影响 context 归一化。早期不同长度场景用于构造调试；统一长度是为了控制比较条件，未挑种子、改阈值或按通过率择优。

全部输入经真实 `ProjectTwoReplayStep` / `ProjectTwoReplayEpisode` 模型重新验证。时间、record/source detection/opportunity 和 actor evidence 引用来自显式构造；无私有状态写入。公共地图和带不确定性的 actor prior/posterior 同时发给所有臂。未在 P5 内部塞入 committed state，也未用额外 P5 专属预热。动态场景的 split 标为 development TRAIN；未重新包装成确认数据。

原三臂用原已独立调参结果（learned width=8、lr=0.1、l2=0、smoothing=0.25；AMG=0.2），不在这六条轨迹上选参数。此处是公开开发敏感性挑战，**不是已针对新分布独立调优后的科学排名实验**。

此外，每个场景建立单独的 **ordinary 兼容生产入口参考**，同一份可见输入从空状态运行。它不是第四个排名臂，不给 direct P5 预热，不向任何比较臂转移其状态；其非空提交不能计作纯 P5 通过。

| 开发场景 | 输入／三臂完整输出 | 纯 P5 最大长期提交 | ordinary 最大提交 | full/fast PUT_BACK 差异 | 路径与边界 |
|---|---:|---:|---:|---:|---|
| 稳定 owner | 14 / 14 | 0 | 14 | 0 | 合法 ordinary 长期贡献确实非空；纯 P5 非空条件失败 |
| 一次未检测再验证 | 14 / 14 | 0 | 13 | 0 | CIAV negative closure，不伪造 before→after transition；原冻结负观测规则允许 carry-forward |
| guest 接续移动 | 14 / 14 | 0 | 12 | 0 | actor/prior 改变，物体及地图不变；测试的是人物条件移动，不是完整有序交接证据链 |
| unknown actor | 14 / 14 | 0 | 12 | 0 | unknown 概率输入；没有测试从图像识别未知人物的能力 |
| owner 习惯变化再返回 | 14 / 14 | 0 | 14 | 0 | ordinary 新阶段后返回 stable；纯 P5 仍只有快路径贡献 |
| 同类别另一实例 | 14 / 13 | 0 | 13 | 0 | 最后一条输入三臂输出均被拒绝；没有测试视觉外观相似度或多实例生产路由 |

对应 `E/scenario_matrix.json` 与主包 `dynamic_development.scenes[].rows`。合计 84 个输入，83 个合法三臂动作输出步骤；错误输入不是“任务失败率”样本。所有场景 `complete_mechanism = MISSING_PRODUCTION_CAPABILITY`，判据要求长期非空、行动区分和真实执行均非空，不接受空集合的 all() 成功。

原始场景中的普通场景和强基线都保留。习惯变化脚本中 P5 PUT_BACK 命令 14/14、两基线各 10/14；**P5 与 fast-only 动作依然完全相同**。这四步只能说明此输入下快速读出的反应差异，不能称为长期记忆或七算子联合收益。

## 4. 敏感性、长期贡献与反馈后果

受控对照 `E/controlled_contrasts.json` 逐步报告 current/habit 总变差（TV）、SEARCH 次序和 PUT_BACK 是否改变：

- guest/unknown 对照 owner 习惯变化，位置和时间序列相同，只改变人物证据／先验；所有 14 步长度相同。
- 稳定序列与负观测序列，只改变第 7 步是否检测到物体。
- 前 6 步的后验对照相同有回归断言；干预后的非零后验差异有真实数值断言，不能只产生不同 hash。
- 这些是合法输入敏感性对照，不是要求干预后仍等价的重放容差测试。

真实长期贡献取自 `_committed_events` 的 location、owner mass、statistical owner weight 和真实 hybrid alpha；只读，不注入。报告逐行 `nonhabit_long_contribution_mass`，不拿当前位置错误当污染。它是脚本标签下的非习惯位置存留质量，不自动等于正式 C1/C2/C3：正式机会分母、跨会话身份污染、恢复时间和高风险独立样本量仍未满足。纯 P5 的零长期提交也不能叫“污染护栏通过”。

为什么 full/fast 动作不分：生产 `_latest_owner_event_component` 给合格最新 owner 事件点质量，所选权重 fast=0.7、surviving=0.2、regime=0.1、pooled=0。存在该点质量时，其他质量最多 0.3，不能把另一个位置变成 top1；无合格 fast 或更复杂读出时不据此推广。加上本次纯 P5 实际零存活提交，原 1920 步和新场景均不能检验长期行动收益。没有改权重制造差异。

独立 CIAV 生产接口探针把 primary 观测和后续验证观测分开：

| 验证结果 | 实际反馈 closure | 解释 |
|---|---|---|
| 同位置 | `same_location_fast_verification` | 真实快验证路径 |
| 异位置 | `full_transition` | 真实新增反馈 transition；非换用评估器算法 |
| 未检测 | `none` | 有真实未检测 receipt；不是完整负反馈记忆更新的成功证明 |

三种情况下 primary 的七算子 trace 均经过验证。此探针超出原 one-packet adapter 的“primary 后位置就是 CIAV 检测位置”约束，明确是生产接口开发诊断，没有替换原三臂 CIAV 结果或科学预算。

真实 `process_execution_feedback`，未注入 policy：

- 成功反馈使 presence posterior 到 0.9949753844592194，执行 `reinforce`，真实长期 hybrid 总质量增加约 0.15490060516956206。
- `NOT_FOUND` 反馈使 presence posterior 到 0.5092707045735477，执行 `quarantine`，长期质量不增加。
- 两者重复相同反馈，已报告的 readout / committed contribution / alpha 均不重复改变。

likelihood、decision context、metadata 由开发传感器 fixture 显式建立，绑定当时真实 snapshot；**不是从真实机器人执行产生的反馈，也不证明正式感知标定与上下文托管可信**。只证明这个公共 core 接口有非空信念／统计后果。

## 5. 反证、纠正与实现缺口

`E/handoff_boundary_probes.json` 从普通生产入口生成真实历史，再把实际第四条已提交 revision 交给公共 `apply_event_revision_outcome`。没有私有状态注入，没有伪造 committed 对象。

- RETRACT：真实提交和长期质量减少；重复调用拒绝，报告的语义状态不变。
- CORRECT：API 返回 `correct`，原 revision 不再提交，而新 revision **既未提交，也未隔离**。这复现第四轮复核的公开接口问题。回归明确登记为缺陷，不能把“调用返回”当完成纠正。
- 重复 transition、旧时间 transition：主包中的旧时间案例同时使用了已见 ID，不能独自证明乱序保护。因此另增完全新 detection ID 的旧时间输入回归：真实核心拒绝 `automatic regime observations must be strictly chronological`，14 个原提交及已报告统计/读出不变，见 `E/dynamic_tests/fresh_identifier_late_input.json`。该补充测试不是新的 CLI 重放证书。完整内部事务结构及所有来源图不变性未在本窗口穷举。
- correction outcome 是调用者提交的外部声明。这里没有把一次晚到的检测自动转为合格旧事件反证；当前完整自主纠正入口仍是 **MISSING_PRODUCTION_CAPABILITY**。此探针也不证明纠正证据与旧事件的因果资格。

缺失能力及窗口三交接：

1. `structure_two_production_system.py:1136` 的 direct-P5 primary 显式 `force_long_term_write_blocked=True`；本固定版本未在纯 P5 常规后续路径形成可用长期提交。不得通过手动授权或降阈值修成非零。
2. ordinary 路径能新建和复活阶段，不能代替 direct P5 证据；未来修复需要同一公共输入和真实授权资格下的 direct-P5 非空正例。
3. 迟到反证的自主资格认定→正式纠正→撤回/反复纠正→长期统计/行动恢复，未完成。当前公开 revision 入口可复现上述丢失新记录问题。
4. 多人物有序交接、身份变化与真正习惯变化的全链辨别、视觉相似实例、跨实例隔离、完整持久 joint particles/近似后验块，本次未充分测到；不能以明确 actor 概率输入和 object UUID 边界替代。
5. 真实动作环境 `TaskSeparatedActionEnvironment.issue_runtime_readout` 只接受其自身的 `TaskSeparatedLearnedInteractionRuntime` 类型及内部签发能力，不能接收当前三臂 typed decoder 的结果。没有可用于三臂共同闭环的公共执行适配入口。

因此 SEARCH top1／PUT_BACK 命令正确性、执行成功与环境状态改变分别报告。后两项为 `null`／MISSING，绝不以解码位置相等代替物体被正确搬动。

最小复现（固定本轮源码、原生 Python，完整输出写新文件）：

```bash
PYTHONPATH=src /Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/.venv/bin/python -m pytest -q -o addopts='' tests/test_structure_two_comparison_dynamic.py -k 'current_production_revision_defect or real_long_term_positive or actual_same_different or real_feedback'
```

生产问题修复后，应更新这里“保留已知失败行为”的诊断断言，增加期望修复后正路径，再重新生成完整包；不能把现有缺陷断言通过称作窗口三验收通过。

## 6. 容差、信息及性能的边界

最终冻结协议的 belief TV p95≤0.05、max≤0.1、行动一致率与 consequential action exact、效用 TOST 双容差、离散身份／提交／权限精确一致，都原文导出。正式两个入口在本次确定性数值重放中仍作严格相等比较，没有为近似结果放宽原检查。

新动态单元测试两次新建真实状态，数值语义严格相同；两个正式 CLI 会从当前源码重建包括动态诊断在内的整个 payload。其结果仅称“当前源码新鲜重放一致”。PCT、D2 时长、效用 TOST、真实执行机会和污染/恢复护栏未运行，不能据严格重放一致宣称正式 full-rerun 科学条件全部满足。

原观察消费／学习资源仍记录于新包：640 TRAIN 行、12 特征、selected active logits=64、条件位置头 9 格；模型只在 train fit，两个基线独立 validation 选择，selected learned 参数如上。代码和参数容量不是等值计算量。动态 fixture 没有新训练预算搜索。

硬件为 Apple M5、Mac17,3、24 GiB 内存、10 个逻辑 CPU，macOS 26.4 arm64、NumPy 2.5.2。sandbox 内型号查询未获值，补充只读 sysctl 结果单独保存在 `E/hardware_supplement.json`，未回填或修改 bundle。生成阶段设置 OMP / OPENBLAS / VECLIB 线程为 1，并记录实际硬件和计时范围。验证阶段多进程并行只用于正确性；没有隔离全机器其他窗口，本轮不输出速度或净效用优越性结论。timing 重复数 3、2 个固定 episode，按重复轮换臂顺序；先完成整套开发诊断，计时使用全新逐 episode 状态，不丢弃预热步骤（全机文件/代码缓存未冷启动隔离）。范围为 consume、状态摘要、trace 验证、后验和公共解码；不含初始化、packet 构造、训练、数据加载、truth、评分、磁盘 IO、真实观测和机器人执行。范围定义沿原工具，不把训练或外部传感器成本隐去后称作整体推理效用。

## 7. 原始结果与共同规则对照保全

新 v5 与 v4：逐步语义 hash、完整 D0 summary、独立选择结果、attribution 全部相同；历史逐 episode/arm 对账无不一致。

- P5 / AMG / learned PUT_BACK 错误仍为 85 / 102 / 533（1920 步）。
- 53 个无 owner 估计步骤中，AMG 原错误 53，共同均匀规则为 36；全局 102→85，17 步差额归零。触发由真实 AMG 状态决定，不由 P5 正确性或真值挑选。
- P5 长期提交仍 1920 步全部为 0，full/fast PUT_BACK 差异 0，三臂 SEARCH 分布一致 1920 步。
- 原信号门 0.02 未降低。原 P5 对 AMG 0.008854 的改善及其 CI 没有因此获得新的确认性解释。

见 `E/numeric_reconciliation.json`。旧 v4 在新来源下被正常拒绝（`SOURCE_BINDING_MISMATCH`），日志保留在 `E/logs/old_v4_rejection.log`；这不是旧数值结论被推翻。

## 8. 命令、回归与证据验收

完整命令、解释器、环境、cwd、起止 UTC 和退出码写入 `E/*_command.json`；完整 stdout/stderr 位于 `E/logs`。可重复入口：

```bash
/Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/.venv/bin/python docs/reviews/data/structure_two_comparison_dynamic_window2_2026-09-12T1500/run_validation.py generate
/Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/.venv/bin/python docs/reviews/data/structure_two_comparison_dynamic_window2_2026-09-12T1500/run_validation.py verify
```

脚本拒绝覆盖已有运行日志和 bundle；重跑先复制这个诊断驱动到**新的同级证据目录**，保留其相对根布局，再执行。直接运行原两个 CLI 的完整 argv 也在 command JSON 内。

验收结果见 `E/validation_summary.json`：主生成、归因生成、全量主验证、独立归因验证、全部回归五条命令均 exit 0。**77 passed，0 failed / errors / skipped，985.21 秒（并行正确性测试耗时，不是算法性能测量）**。原始 21 类、原公平性 6 类、新动态 4 类完整伪造均逐包 REJECTED，各批合法包均 CURRENT_SOURCE_FRESH_REPLAY_MATCH。来源矩阵 16 项（含两个完整新鲜正例）按预期通过。

首批目录 `docs/reviews/data/structure_two_comparison_dynamic_window2_2026-09-12T1415` 完整保留。首批全量包在两正式入口均因 `dynamic_development.ciav_interface_probes.different.detection_outcome (type)` 被拒绝：内存 StrEnum 与留存 JSON string 类型不同。严格验证器正确失败关闭。发现共同根因后终止其剩余 pytest 子进程树（exit -15，见 termination.json），不把未完成回归宣称通过。修复只把新增诊断返回值在源头规范为 JSON 基本类型；补真实输出写盘类型一致回归，17 项单元通过，在本节新目录完整重算，未修改首批 bundle。

其余保留失败过程：初次 typed fixture 的 metadata 多余字段、UUID 类型、recorded_time、负观测 detection_time/strength 校验拒绝；最后一次整理中配置路径意外多空格导致 1 failed / 15 passed，修正后 16 passed。没有改变生产合同让坏输入合法化。提交钩子只重排 rationale 字符串括号；未绕过钩子。

新增 19 项中包括真实非空普通生产正例、纯 P5 非空拒绝、两次语义新建重放、合法实例和完整重封错误目标、场景路径及 4 类动态依赖全伪造真实 CLI 攻击。原 58 项及原 21 类完整伪造、6 类公平性伪造、执行来源攻击断言均保留。攻击包来源来自新 v5，重新计算 attribution，不靠旧 source binding 失效拦截。

## 9. 五个问题的最终回答与整合要求

| 问题 | 回答 |
|---|---|
| 比较合同是否明确？ | 部分。共同 decoder/CIAV、split 时序、最终 PCT 已冻结；地图权限、缺省先验和具体预算还有未决项 |
| 实际执行是否符合合同？ | 窗口二已检查范围可重放；新增跨实例错误输出被拒绝。原 adapter 多实例路由、纠正链和完整权限/资源匹配不能称为全面符合 |
| 完整机制是否非空触发？ | 否。ordinary 提交、阶段和反馈统计非空，但纯 P5 长期提交与 full/fast 行动贡献条件仍失败 |
| 是否产生正确行动后果？ | 解码命令可评分；没有三臂共同生产执行入口，真实 SEARCH/PUT_BACK 执行和环境状态变化未测 |
| 公平性与科学收益是否建立？ | 否。来源可信和数值可重算只在各自边界成立；不授权路由校准、七算子科学消融或密封确认 |

整合顺序：先审窗口二代码/测试 → 窗口三修复上述真实接口缺口并提供固定版本 → 用户决定未决比较规则和具体预算 → 在最终整合源码下重新生成窗口二完整诊断 → 窗口一重算依赖证明和门控回执。

失效产物：本轮新源码使旧 v2/v3/v4 的 current-source 声明过期；历史事实保留。未来合入窗口一／三改变任何绑定源码时，v5 及其主验证、归因、动态场景和本批来源攻击正例也过期。必须重算主审计 60/1920、独立归因、冷启动对照、全部 77 项（随真实修复更新已知缺陷断言）、窗口三受影响的 revision/feedback 链及窗口一相应 manifest/工程 receipt/P0 等依赖证据。全局 manifest/checkpoint 本窗口不编辑，也不以本报告签发替代其真实重算。

实现提交及文件清单见 `E/implementation_commits.json`，按 `7202416` → `d611248` → `e8b5cee` 审查（后两者依赖前者）；证据提交在其后。`bundle_v5` 是诊断目录版本，不是新科学协议。

本分支不自动合并、不推送；完整能力范围继续保留。当前来源保护仍不覆盖恶意修改 Python/stdlib、同进程任意执行或 OS 级篡改；也不是独立历史托管证明。未测项和待决定项不写成通过。
