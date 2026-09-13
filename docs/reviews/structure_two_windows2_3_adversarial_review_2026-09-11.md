# 结构二窗口二、三：独立对抗复核

日期：2026-09-11。性质：只读实现审查、原生环境复跑、独立反例；不合并、不修复生产实现、不重写历史结果。窗口一仍在进行，不将其未完成项算作窗口二、三已完成，也不假定它会自动解决本报告的问题。

## 1. 总结与验收意见

**窗口二：主体诊断可采信，但独立归因验证入口还有一项实质缺口。窗口三：真实缺口发现有价值，属于有效的部分审计；不能据此验收“主干和七算子已正常协作”，若干通过项与修复声明需要收窄或补证。**

最重要的科研结论：当前批次 P5 对 AMG 的 17 步优势，在仅统一冷启动默认规则后全部消失；这一结果经完整新鲜重放复现。当前比较没有建立长期记忆增益，也没有建立七算子联合方法优势。这不是要求删除任何能力或缩小完整框架，而是要求先修复比较设计与闭环证据，再讨论完整方法的增益。

| 审查维度 | 当前判定 | 边界 |
|---|---|---|
| 窗口二历史结果及主要归因可复现 | 通过本次复核 | 60 个 episode、1920 步、三臂完整重放，限该开发诊断集 |
| 窗口二独立归因验证器能认证输入真实性 | 不通过 | 全量同步伪造状态计数并重算哈希后，独立入口仍打印 verified；完整主入口能拒绝 |
| 窗口三新增测试及选定回归 | 通过 | 原生项目环境共 150 项通过，不等于全仓或全部科学验证门通过 |
| 比较能检验所声称的方法差异 | 尚不成立 | SEARCH 被共同读出规则抹平；PUT_BACK 冷启动差额归零；长期提交为零 |
| 七算子各自影响实际动作 | 仅局部成立 | CIAV 的局部似然干预能改变实际选择；其他算子未逐一隔离证明 |
| 主干与七算子完整协作 | 未证明，且存在断点 | 负观测、长期巩固、身份轴、修订闭环、粒子主干映射仍有缺口 |
| 历史产物对当前代码仍有效 | 不能接受该声明 | W3 的两个留存 P5 产物在当前源码绑定检查失败 |
| 科学优越性、长期效用、完整审计 | 未建立 | 不将工程测试通过升级为科学通过或穷尽性审计 |

## 2. 固定审查对象与环境

共同起点：`09eb4d48e1c11082e90ca18332d04333e6b5b47a`。

- 窗口二：`codex/s2-comparison-audit-window2-20260911`，代码提交 `6f9ca3669cef8476c356fda0d2d07f74079671c7`，最终报告/产物提交 `46ba30fcc9a9b52a46647246382f93eb9d06b3ab`。
- 窗口三：`codex/s2-backbone-operators-w3`，代码提交 `5c45005ca0d37c666cd796bbb11ba1edcc3624d8`，最终说明提交 `d6db421d33b6499ca7dfbead3d4ecb543a371970`。
- 为隔离窗口一和用户工作区，本次在独立 detached worktree 中检查：`/private/tmp/s2-review-w2.ukHjjw`、`/private/tmp/s2-review-w3.sBTeGF`。临时目录可能被清理，提交 SHA 是后续复现的定位依据。
- 使用 `/Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/.venv/bin/python`：Python 3.13.5、numpy 2.5.2、cryptography 47.0.0、pytest 9.1.1、scikit-learn 1.9.0。不做语法降级或导入替换。
- 主工作区源码和三个窗口的实现均未改动；仅新增本审查文档与独立探针脚本。原有 `Claude outputs/` 保留。

原报告：[窗口二](/private/tmp/s2-review-w2.ukHjjw/docs/reviews/structure_two_comparison_audit_window2_2026-09-11.md)、[窗口三](/private/tmp/s2-review-w3.sBTeGF/docs/reviews/structure_two_backbone_operator_audit_window3_2026-09-11.md)。

## 3. 独立执行结果

| 执行 | 结果 |
|---|---|
| W2 新增比较审计测试 | 20 passed，13.77 秒 |
| W2 留存归因独立复核 | 原始 bundle 的 attribution verified |
| W2 完整主入口重新训练/validation 选择/逐步重放/核对 | 60/60 episode，1920 步，retained_score_mismatches=[] |
| W3 新增接线测试及八组相关回归文件 | 150 passed，36.64 秒；其中新增 28 项，相关既有 122 项 |
| W2 完整伪造归因包反例 | 独立归因入口误接受；完整主审计验证器拒绝 |
| W3 非法上游载荷、S8 全状态检查、S4 实际动作检查 | 见后文，反例可复现 |
| W3 两份留存 P5 产物新鲜校验 | 均因源码/绑定漂移失败 |

W2 完整重放的语义步骤摘要：`d32b9d7bd2ff4963d8a71939fe752b260806e8775b692d602ac4588205f70c76`。

W3 原报告在不同 Python/依赖环境中出现的四项失败，本机原生环境没有复现。因此不继续把那四项视为已确认的代码回归。但本次 150 项通过不覆盖所有历史工件验证，更不是整个系统的全量通过声明。

## 4. 窗口二：可采信结论与剩余问题

### 4.1 方法增益解释应撤回，而不只是说“低于阈值”

完整重放确认：P5 PUT_BACK 错误 85/1920，AMG 102/1920，learned two-stage 533/1920。P5 相对 AMG 的步级胜/负/共同错/共同对为 17/0/85/1818；episode 总误差为 6 胜、0 负、54 平。

17 个胜步全部位于 53 个冷启动状态：P5 owner-habit 后验均匀，AMG 尚无 owner 估计。AMG 原生退化选择是支持集首项，而公共解码器对 P5 均匀分布按 UUID 打平排序。这不是两个系统已学到的记忆能力差异。

窗口二的控制干预依据独立重放的 AMG 状态 `amg_owner_location is None` 触发，没有按真值或 P5 胜步挑选。只把这时的 AMG 默认规则换成共同均匀先验，保持观测、支持与公共解码器不变：53 步 AMG 错误从 53 降到 36，与 P5 的 53 个选择完全一致；其他 1867 步本来就没有选择差异。全批 17 步差额归零。

所以该批次的 `0.008854` 差额不能继续被解释成结构二的联合方法或长期记忆增益。该控制是开发诊断，不是新的正式基线优越性检验。

### 4.2 比较环境并未充分测到完整目标

- 三臂 SEARCH current 分布在 1920/1920 步相等，共同 detected/carry 规则主导结果。SEARCH 打平不等于各方法内部推断能力等价。
- P5 1920/1920 步 `_committed_events=0`；完整 PUT_BACK 与 fast-only 读出 1920/1920 相同。1276 个正观测闭环均为同位置验证，644 个负观测没有新转移。不能把结果归因于长期巩固或七算子整体贡献。
- 1040/1920 步支持集含尚未在观测前缀出现的位置；当前转换器未保留先验已知位置目录，而支持集从整条 episode 提取。若声称严格在线发现，这是未来信息边界问题。它为三臂共享，不能直接说某一臂单独偷看答案。
- 原 evaluator 提前读取评分真值是接口隔离问题；审计工具改为先提交动作后评分仍复现历史结果，没有据此发现当前三臂显式利用真值。
- learned 表示信息/有序角色输入及不遗忘计数头的差异是真实诊断线索，但 533 个错误不能全归于某一个已被因果证明的原因。
- 原报告约 73.27 倍 AMG 的耗时包含回执、哈希等运行时开销，样本为三轮各两个 episode；不能直接当成纯算法 FLOPs 比值。本次只用一轮一个 episode 进行验证运行，未独立复现这个精确比值。

### 4.3 R1：独立归因验证器信任可共同改写的依赖（中优先级）

定位：[归因分析输入核对](/private/tmp/s2-review-w2.ukHjjw/apps/evaluation_runner/summarize_structure_two_comparison_audit.py:21)、[独立验证入口](/private/tmp/s2-review-w2.ukHjjw/apps/evaluation_runner/summarize_structure_two_comparison_audit.py:195)。

构造：将每个步骤的 `raw_state.p5_readouts.state_counts._committed_events` 改为 999，同步更新步骤语义哈希，并用同一分析器生成相容的 attribution。真实独立 `--verify` 入口仍输出：

```text
attribution verified
invented_commit_histogram = {"999": 1920}
```

原因：归因入口只检查输入文件彼此自洽，部分 AMG 状态虽有独立重放，但 P5 状态计数等仍信任步骤包。它不能独立认证这批 P5 内部状态确实发生过。

范围限制：完整主审计以新鲜重放为锚，拒绝这个伪造，错误为 `fresh diagnostic differs at semantic_steps_sha256`。因此本次已完整重放的原始结论不因该反例失效，也没有发现完整主验证器被绕过。

验收条件：独立归因入口要求已经通过完整主验证的、绑定源码和步骤包的依赖证明，或执行完整相应重放；增加同步改写全部依赖的正向伪造回归。仅改一个字段而保留旧哈希的测试不够。

## 5. 窗口三：反例与结论边界

### 5.1 R2：P0 修复证明载荷绑定，不证明语义消费（高优先级声明问题）

定位：[CCRR/RGRC maintenance](/private/tmp/s2-review-w3.sBTeGF/src/cpswm/system/prototype_spine.py:1041)、[原报告修复声明](/private/tmp/s2-review-w3.sBTeGF/docs/reviews/structure_two_backbone_operator_audit_window3_2026-09-11.md:304)。

真实改进是：上游输出现在被作为参数传递，哈希被写入下游回执。不能据此称为下游已检查或利用上游判断。

独立注入 `observation_count=-999`、`posterior_advanced=True`、`current_snapshot_sha256="foreign"`，CCRR 不拒绝；再向 RGRC 注入不一致 PCHMP 载荷，也不拒绝。去除新增 `consumed_*` 哈希字段后，前后语义输出完全相同。原测试主要检查函数签名和输出哈希变化，因此会通过。

这不是非法写入漏洞的证明：P0 始终拒绝长期写入，本来就可能是安全空操作。也不能要求每次上游扰动都必须改变动作。问题在于报告把“收到并绑定字节”升级成了“安全维护检查/真实算子消费”。零显式输入参数也不能排除通过 `self` 共享状态的依赖。

验收条件：先按冻结合同明确 P0 是纯回执绑定还是需要校验当前状态一致性；前者收窄完成声明，后者补非法/过期/跨状态上游输入测试和对应检查，不更改或弱化冻结图来使测试通过。

### 5.2 R3：S8 只撤回 Hybrid 子账本，未验证完整迟到反证闭环（高优先级覆盖问题）

定位：[S8 测试](/private/tmp/s2-review-w3.sBTeGF/tests/test_structure_two_backbone_operator_wiring.py:306)、[场景通过表](/private/tmp/s2-review-w3.sBTeGF/docs/reviews/structure_two_backbone_operator_audit_window3_2026-09-11.md:160)。

原测试通过 legacy `core.process_transition` 建立 12 条记录，直接调用私有 `core._hybrid_loop.retract_revision`。它不是从生产反馈入口输入迟到反证，也没有经历完整修订、各统计块同步回滚及债务重放。

按完全相同设置增加检查后：

| 检查 | 结果 |
|---|---|
| Hybrid 对应 live 记录 | 清零 |
| Hybrid full-rerun equivalence | True |
| 全局 committed events | 12 → 12，目标仍在其中 |
| Dirichlet 状态 | 未变 |
| fast event 状态 | 未变 |
| 动作概率分布 | 改变 |
| 实际 PUT_BACK top-1 | 不变 |

因此可以保留“Hybrid 子账本撤回幂等且与该子账本重算一致”，不能据此说全系统迟到反证已经无残留、无重复计数，或实际动作已变化。该反例揭示审计覆盖不足，不单凭它断言尚未测试的公开生产撤回接口损坏。

验收条件：从正式反馈/修订入口构造已提交事件的迟到反证，逐项检查所有应受影响的统计块、快慢记忆、提交记录、地图发布、动作以及重放一致性；明确保留历史记录与保留有效贡献的区别。未覆盖前将 S8 全链路结论标为 partial。

### 5.3 R4：七算子动作影响与算法等价表超出证据（中优先级）

定位：[五类证据表](/private/tmp/s2-review-w3.sBTeGF/docs/reviews/structure_two_backbone_operator_audit_window3_2026-09-11.md:184)。

函数被调用、状态进入下一节点或哈希改变，不能替代逐算子受控干预。S4 确实提供局部正证据：CIAV owner-likelihood 从 0.95 改为 0.05 后，实际 PUT_BACK top-1 从 `44b33099-dee8-2a8b-cc46-e34a555d6659` 切换为 `23a2ff08-fd31-2108-19c8-56bbe1bdd947`。保留这项局部结论。

但该单一干预不能分别证明 OPCEU、PCHMP、CHEH、CF-BOCPD、CCRR 都按预期独立影响实际动作。S8 更明确展示了“动作分布改变而选择不变”。应分别记录调用、数值状态改变、概率分布改变、实际动作改变、任务收益，不能合并。

“算法实现等价”一列主要按直接/复合/外层 callable 绑定判定。直接绑定只证明实现身份，不证明等价于冻结算法；RGRC 没有独立 callable 也不等于算法不等价。建议将该列改称“实现绑定方式”，把真正的算法语义等价另列为待验证。

### 5.4 R5：留存产物“未失效”不成立（高优先级整合问题）

定位：[工件失效登记](/private/tmp/s2-review-w3.sBTeGF/docs/reviews/structure_two_backbone_operator_audit_window3_2026-09-11.md:331)。

原报告一方面承认两个源码文件变化会改变 manifest/source binding，另一方面又称历史 benchmark、全局 manifest、工程 checkpoint、P5 direct/debt 产物“未失效（未触碰）”。未改文件字节不代表产物仍绑定当前代码。

在 W3 最终提交直接加载留存产物并调用各自 `fresh_recompute=True` 验证器：

```text
structure_two_p5_direct_trace_probe_v0_1.json
ValueError: direct P5 trace probe source binding mismatch

structure_two_p5_debt_replay_confirmation_v0_1.json
ValueError: P5 debt-replay result identity, hash, or binding drifted
```

150 项测试通过与此不矛盾：相关测试有创建新结果再验证的路径，并不等于对所有磁盘留存产物做绑定复核。

部分历史漂移在共同起点已经存在，不能把全部失败归因于 W3 新改动。但 W3 的“当前仍有效”声明确实未获支持，源码修改也必须纳入整合失效清单。

验收条件：修订失效表，区分历史文件保留、对旧提交有效、对当前提交有效；待最终源码版本确定后，由证据链工作统一重算受影响证明，保留旧结果，不覆盖历史失败。

### 5.5 R6：CIAV 负观测的“似然未消费”应分层表述（中优先级）

生产实现确实计算 `actor_prior × actor_likelihood` 并归一化；独立重放负观测，owner 后验从 `0.8055113493592428` 变为 `0.970703272855737`。所以不能说局部贝叶斯似然运算不存在。

但此时 `fast_verification_receipt` 和 `feedback_result` 均为空，而消费记录目标标成 `fast-action-owner-posterior:*`。可靠结论是“局部后验已计算，未证明对应快记忆/动作状态获得更新”；记录目标与真实下游写入的语义需要核对。不要把局部计算、持久化、动作消费三件事合并。

## 6. 窗口三仍可保留的真实发现

- 当前生产 P0–P5 以 CorePrototypeSpine 为核心，尚不能认定已实现完整粒子主干、神经提议器、条件化 RB 统计块与七算子的统一运行。既有原型模块存在，不等于生产入口实际使用它们。
- 所测自适应路径中，同位置和负观测 14 步均为 0 committed、14 quarantined；异位置闭包能提交，legacy 对照至少 12 条提交。这是长期巩固可达性缺口，不只是总体分数低。
- 声明的 feedback_revision_loop 使用不同 engine/message-passer，所测 P0/direct/replay 路径未消费该实例。范围限所检查入口，不外推所有公开 API 均不可用。
- CCRR 的身份变化输入被固定为 0.0，不能声称身份轴已经参与其正常判断。
- 个别局部机制确实有效：CIAV 阈值干预可改选择，create/reactivate 可达，Hybrid 子账本撤回幂等。它们应保留为局部证据，不扩张为完整框架有效。

## 7. 后续验收建议与未覆盖边界

1. 窗口二保留主要报告和归因结论，补 R1 的完整依赖验证及反例回归。不要因为归因入口缺陷而推翻已经由完整重放支持的事实。
2. 窗口三先修订 R2–R6 的声明和通过表，再补公开迟到反证入口、状态语义消费、逐算子干预。修复发现的问题与证明整个架构符合预期是不同验收目标。
3. 窗口一完成后，再在同一最终源码版本上统一核对 source binding、manifest、checkpoint 和工程/科学验证门。不把不同提交的绿色结果拼成一个系统的通过结论。
4. 新一轮方法比较应明确在线支持可见性、冷启动默认规则、输入权限、调参/计算预算和真实长期提交场景，并保留完整框架能力；正式未见测试不得继续用于诊断调参。具体实现方向和取舍由用户决定。

本次没有穷尽全仓全部验证器、所有正向授权输出、真实多线程竞争、所有公开修订入口、外部独立托管或真实环境长期效用。W3 的顺序重入/债务拒绝测试不等于真实并发竞争已经被穷尽。单个 seed 的 create/reactivate 也不证明真值阶段识别或收益。

因此本报告同样是明确限定范围的对抗复核，不能称为“没有进一步 bug”或“结构二所有验证门通过”。

## 8. 复现入口

反例脚本：[counterexamples.py](/Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/docs/reviews/data/structure_two_windows2_3_adversarial_review_2026-09-11/counterexamples.py)。脚本 W2 只在自动清理的临时目录构造伪造包，W3 只修改进程内探针状态，不改留存产物。

```bash
/Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/.venv/bin/python /Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/docs/reviews/data/structure_two_windows2_3_adversarial_review_2026-09-11/counterexamples.py /private/tmp/s2-review-w2.ukHjjw w2
```

```bash
/Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/.venv/bin/python /Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/docs/reviews/data/structure_two_windows2_3_adversarial_review_2026-09-11/counterexamples.py /private/tmp/s2-review-w3.sBTeGF w3
```

W2 完整验证（在指定固定提交的独立工作树执行；不是只运行 summarize）：

```bash
cd /private/tmp/s2-review-w2.ukHjjw
PYTHONPATH=src /Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/.venv/bin/python apps/evaluation_runner/run_structure_two_comparison_audit.py --output docs/reviews/data/structure_two_comparison_audit_window2_2026-09-11 --verify --timing-repeats 1 --timing-episodes 1
```

W3 原生回归：

```bash
cd /private/tmp/s2-review-w3.sBTeGF
PYTHONPATH=src /Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/.venv/bin/python -m pytest -o addopts='' -q -p no:cacheprovider tests/test_structure_two_backbone_operator_wiring.py tests/test_core_prototype_spine.py tests/test_structure_two_production_system.py tests/test_structure_two_execution_interface.py tests/test_structure_two_adaptive_runtime.py tests/test_structure_two_adaptive_runtime_adversarial_round1.py tests/test_structure_two_adaptive_runtime_adversarial_round2.py tests/test_structure_two_p5_direct_trace_probe.py tests/test_structure_two_p5_debt_replay_confirmation.py
```
