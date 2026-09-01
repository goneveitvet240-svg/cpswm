# Structure Two 外部适配器独立复现忠实度审核

日期：2026-08-31  
审核对象：Gate B 中的 BrainCTL、Active Dreaming、O-STaR，以及尚未完成独立审核的其他外部方法臂。  
审核问题：当前适配器是否忠实复现官方完整方法，而不只是产生不同轨迹？

## 结论先行

当前 Gate B 可以检验 `behavioral distinguishability`（行为可区分性），但不能据此授权外部方法效能比较。三项已逐一对照官方论文或白皮书及官方代码：

| 适配器 | 当前判定 | 已核实内容 | 关键缺口 |
|---|---|---|---|
| Active Dreaming | `non_faithful_proxy` | 官方预印本；官方仓库提交 `9c05baf41673d10e92c076ba7db18b1b6553a60d` | 当前臂没有失败片段检索、DBSCAN 聚类、LLM 规则抽象、反事实可执行场景生成与实际执行、成功后写入语义记忆的完整链路 |
| brainctl | `non_faithful_proxy` | 官方白皮书；官方仓库提交 `c6348087dd07e54583f762e07bf960ac982019e6`；五个顶层权重数值相符 | 当前臂没有来源信任类别、类别先验、向量新颖度、scope/recall/arousal/valence、两级写入门、tier 路由、Bayesian confidence、合并/替代/拒绝/巩固生命周期；还把记忆控制门改成了具身状态 promote/escrow 决策 |
| O-STaR | `non_faithful_proxy` | 官方论文/海报；仓库已有独立方程核心及单测 | Gate B 实际实例化 `_CountMethod(mode="o_star")`，连仓库内的 `OStarReferenceBelief` 方程核心也没有调用；更缺少 LLM Day-0 先验、3D 几何剪枝、Dirichlet hit/miss、Stay+Leak、松弛转移推断、成本感知搜索、多目标顺路感知和论文协议复测 |

所以，当前三项都不是 `faithful reproduction`（忠实复现）。另外，corrected AMG、Auto-Dreamer、TrustMem 尚未做完相同强度的官方源与官方代码逐组件审核，状态是 `not_independently_audited`（未独立审核），也不能继承通过。

## 官方方法对照证据

### Active Dreaming

官方材料：

- 预印本：<https://engrxiv.org/preprint/download/5919/9826/8234>
- 官方代码：<https://github.com/KasimVali2207/active-dreaming-memory>

官方 `dreamer.py` 的关键语义链是：取近期失败 episode，至少两个样本后用 DBSCAN 聚类；调用 LLM 抽象失败规律；再调用 LLM 生成新的、可执行的 Python 反事实场景；实际执行场景；只有执行成功才把规则写入 semantic memory（语义记忆）。当前适配器只计算 confidence、entropy、coverage 的乘积并阈值化，而且直接记录 `local_verifier_executed=True`，没有运行上述官方验证链。因此不是缩小规模但语义等价的复现，而是不同算法。

### brainctl

官方材料：

- 白皮书：<https://www.brainctl.org/whitepaper>
- 官方代码：<https://github.com/TSchonleber/brainctl>

当前适配器确实复制了白皮书五因素公式的权重：utility 0.15、confidence 0.15、novelty 0.20、recency 0.10、type prior 0.40。但官方写入路径还有来源信任、按类别先验、embedding 近邻新颖度、scope、历史 recall、arousal/valence，以及 pre-worthiness 与 deeper write-decision 两级门和多档 tier 路由。白皮书也明确把 brainctl 定位为记忆控制层，而不是 planner（规划器）或 reasoning engine（推理引擎）。当前适配器把简化分数直接映射成世界状态 promote/escrow，改变了对象与决策语义，不能称为完整或语义忠实复现。

### O-STaR

官方材料：

- 论文与海报：<https://www.hrl.uni-bonn.de/publications/2026/menon26grc/menon26grc_paper_poster.pdf/@@download/file>

官方方法包含 open-vocabulary 3D dynamic scene graph（开放词汇三维动态场景图）、LLM Day-0 先验、几何候选剪枝、Dirichlet-Categorical 位置信念、正/负观测更新、Stay+Leak 转移、稀疏观测下的 relaxed transition inference（松弛转移推断）、opportunistic multi-target perception（顺路多目标感知）与 cost-aware active search（成本感知主动搜索）。当前 Gate B 臂是普通计数衰减与命中加一，因此不是 O-STaR 完整方法。

## 已落地的防误用修复

1. 新增机器可检查的 `structure-two-external-adapter-fidelity-gate@0.1`，逐臂登记官方来源、固定代码提交、已验证组件、缺失或改变组件和判定。
2. 把 Active Dreaming、brainctl、O-STaR 的 receipt 从“semantic faithful”或笼统 matched adapter 改为 `reduced_proxy_not_faithful_external_reproduction`。
3. Gate B 报告新增 `external_fidelity_gate_passed`。`method_comparison_allowed` 现在要求 Gate A、Gate B 和外部忠实度门同时通过。
4. 未审核外部臂 fail closed（失败关闭）；不会因另外三个臂被检查过就自动获得忠实度。
5. v0.4 草案的授权转换已改成三门制，并重算包含新忠实度门代码的 producer source bundle。

## 尚未完成，不能冒充完成的工作

这轮完成的是独立的 `semantic/code fidelity audit`（语义/代码忠实度审核）和授权修复，不是三套官方系统的端到端复现实验。要把任一外部臂升级为 `faithful_reproduction`，仍必须：

- 实现或直接封装官方完整执行链，而不是只保留一个打分公式；
- 对每个官方关键组件建立可执行的 component parity test（组件等价测试）；
- 冻结论文所需的数据、prompt、模型、环境、超参数与随机性；
- 独立调参，重跑论文协议或等价协议，并保存 content-bound（内容绑定）结果；
- 最后再做一次不参与实现的独立审核。

在这些条件满足前，Gate B 只能说“这些代理臂行为不同”，不能写成“CARE-WM 优于/不劣于 Active Dreaming、brainctl 或 O-STaR 官方方法”。
