# CARE-WM prior-art checkpoint

检索日期：2026-08-29  
性质：范围化 prior-art review（现有技术核验），不是 systematic review（系统综述）

## 1. 检索问题与关键词

| 分解 | 中文关键词 | English keywords |
|---|---|---|
| 写入决策 | 记忆准入、巩固门、托管、隔离 | memory admission, consolidation gate, escrow, quarantine |
| 主动核验 | 写前验证、反事实模拟、信息价值 | pre-commit verification, counterfactual simulation, value of information |
| 效用 | 未来行动后果、行动遗憾、下游效用 | future action consequence, action regret, downstream utility |
| 可逆性 | 回滚、来源追踪、精确撤销、信念修订 | rollback, provenance, exact retraction, belief revision |
| 场景 | 具身智能、多主体、持续世界模型 | embodied agent, multi-actor, continual world model |

代表性查询包括：

- `embodied agent memory consolidation verification value of information long-term memory reversible rollback`
- `memory write value of information agent long-term memory`
- `counterfactual memory consolidation agent`
- `future action memory consolidation agent regret`
- `verification cost memory consolidation agent`
- `escrow long-term memory agent consolidation`

已覆盖公开网页索引、arXiv/HTML 全文、OpenReview、PMLR、engrXiv 和项目官方白皮书。
未完整覆盖 Scopus、Web of Science、IEEE Xplore、ACM DL、Google Scholar 全量结果及全球专利库，
所以不得据此声称“从未有人提出”。

## 2. 最强相邻工作

| 工作 | 已覆盖的关键机制 | 与 CARE-WM 的剩余边界 | 证据等级 |
|---|---|---|---|
| Active Dreaming Memory (2025) | 用合成反事实场景验证候选规则，验证后才写入长期语义记忆 | 不以具身未来行动污染、验证/修复成本作统一决策；未见多主体精确归因撤销 | primary preprint full text checked |
| Auto-Dreamer (2026) | 双时间尺度离线巩固、来源轨迹、区域重写、下游任务效用和 counterfactual masking credit | 不是在线 promote/escrow/verify；不针对具身世界状态归因和可逆写入 | arXiv full text checked |
| TrustMem (2026) | 对每次 WRITE/REVISE/PRUNE 转移做 coverage/preservation/faithfulness 验证，并以 verifier 训练写入策略 | 主要是文本记忆可靠性；未以物理行动遗憾或验证成本选择是否核验 | arXiv full text checked |
| ChronoMem (2026) | append-only event log、全局快照、语义定位与确定性 rollback | 是全局版本回滚，不是按证据贡献做局部有符号撤销，也不负责写前行动风险 | arXiv full text checked |
| brainctl v2.4 (2026) | future utility/confidence/novelty/recency/type-prior 写入门、pending queue、来源 DAG、quarantine 与下游撤销 | 官方系统白皮书而非同行评审；未见基于具身 world-model rollout 的预期行动遗憾最优化 | official whitepaper checked |
| RoboMemory (2025) | 物理具身系统的时空/情景/语义多记忆与持续更新 | 未见写前反事实核验、成本敏感托管或精确归因撤销 | arXiv full text checked |
| Robo-Cortex (2026) | 具身 world-model imagine-then-verify 规划与跨回合长期原则记忆 | verify 作用在候选行动计划，不是长期记忆写入决策 | arXiv full text checked |

## 3. 新颖性判定

以下说法已经被现有工作覆盖，不能作为 CARE-WM 的独立创新主张：

- “反事实验证后再把规则写入长期记忆”；
- “用下游任务效用或反事实移除来训练记忆巩固”；
- “对记忆转移做 verifier-based verification”；
- “让 agent memory 可回滚、可追踪、可隔离”；
- “把 future utility 加入写入准入分数”。

截至本次公开检索，没有找到把下面三项作为一个可执行决策机制联合起来的工作：

1. 对候选世界状态写入计算未来具身行动污染的 counterfactual regret；
2. 在 `promote / escrow / physically verify` 之间显式比较验证、等待、错误动作和修复成本；
3. 将多人/多来源证据保存为可撤销充分统计，使迟到纠正能局部撤销而非全局回滚。

这是“未在本次检索范围内找到该联合机制”，不是“前人从未使用”。brainctl 已覆盖 future
utility、pending/quarantine、provenance 和下游撤销的大块功能，因此联合机制的新颖性风险为高，
必须把它作为 strongest non-paper neighbor（最强非论文相邻系统）纳入后续对照。

## 4. 对当前验证的影响

精确反事实门通过只能保留“有限机制有效”结论，不能保留“真正未被前人用过且超过现有
方法”的结论。当前最诚实的总体状态是：

- 效果：synthetic mechanism gate passed；
- 新颖性：absolute novelty claim rejected；joint decision-rule novelty unresolved；
- 超越现有方法：not tested，现有门没有忠实实现上述 strongest neighbors；
- 下一要求：全新封存数据上的 faithful matched-baseline death test，不能复用已经打开的
  CARE holdout 作确认性证据。

## 5. Primary sources

- Active Dreaming Memory: https://engrxiv.org/preprint/view/5919
- Auto-Dreamer: https://arxiv.org/abs/2605.20616
- TrustMem: https://arxiv.org/abs/2606.25161
- ChronoMem: https://arxiv.org/abs/2607.27773
- brainctl whitepaper: https://www.brainctl.org/whitepaper
- RoboMemory: https://arxiv.org/abs/2508.01415
- Robo-Cortex: https://arxiv.org/abs/2605.18729
