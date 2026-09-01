# 结构二序贯粒子持久化＋可逆巩固机制门：结果

日期：2026-08-29  
协议：`structure-two-sequential-consolidation-gate@0.1`  
证据等级：D0 synthetic mechanism evidence（D0 合成机制证据）  
最终裁决：**机制门失败。**

## 主要结果

| 配对比较（左−右） | 每步净行动损失差 | 95% paired cluster interval | 判断 |
|---|---:|---:|---|
| 序贯粒子＋可逆巩固 − 逐步粒子投影 | **+0.0590** | **[+0.0460, +0.0720]** | 稳定变差 |
| 序贯粒子、无巩固 − 逐步粒子投影 | −0.0052 | [−0.0174, +0.0052] | 未证明收益 |
| 序贯粒子＋可逆巩固 − 序贯粒子、无巩固 | **+0.0642** | **[+0.0477, +0.0816]** | 巩固层稳定造成伤害 |
| 序贯粒子＋可逆巩固 − corrected AMG | **+0.4205** | **[+0.3628, +0.4754]** | 仍明显落后 AMG |
| 旧完整系统 − corrected AMG | **+0.4856** | **[+0.4278, +0.5375]** | 旧系统差距更大 |

负数表示左侧行动损失更低。区间按 12 个封存 seeds 跨 4 个场景族聚类。

本轮最重要的拆分结论是：temporal particle persistence（时间粒子持久化）没有稳定击败逐步投影，但也没有出现明确整体伤害；显著负作用来自当前 particle-driven consolidation（粒子驱动巩固）层。

## 冻结通过条件

| 条件 | 结果 |
|---|---|
| 主要区间上界 `< 0` | 失败 |
| identity-decoy family 平均改善 | 失败：`+0.0104` |
| long-recurrence family 平均改善 | 失败：`+0.0347` |
| role-chain guardrail `≤ +0.02` | 失败：`+0.0833` |
| cause-collision guardrail `≤ +0.02` | 失败：`+0.1076` |
| 七算子运行时保留 | 通过 |
| 序贯 ancestry 运行时覆盖 | 通过 |
| promote / exactly-once ledger 门 | 通过 |

所以失败不是因为序贯或账本代码没有执行。每个序贯 episode 都产生了跨时间 ancestry；巩固臂每个 episode 至少执行一次晋升，没有重复晋升，并在主导修订改变时执行撤回和 corrected revision（修正修订）。

## 场景族分解

| 场景族 | 巩固−逐步投影 | 局部判断 |
|---|---:|---|
| `sequential_identity_decoy_swap` | +0.0104 | 身份诱饵未被序贯机制转化为行动收益 |
| `sequential_long_recurrence_delayed_feedback` | +0.0347 | 长期复现下巩固造成轻度滞后 |
| `sequential_role_chain_guardrail` | +0.0833 | 明显破坏既有收益 |
| `sequential_cause_collision_guardrail` | +0.1076 | 破坏最严重 |

序贯无巩固臂在 role-chain 场景有局部改善，但在 identity、long-recurrence 中与逐步投影基本一致，在 cause-collision 中略差，因此总体区间跨零。

## 实现与审计证据

本轮实际加入：

- `K=24` persistent typed particles（持久类型化粒子）；
- 每一步显式 `parent_particle_id` 和 ancestry trace（祖先轨迹）；
- belief-conditioned transition weighting（信念条件转移加权）；
- deterministic revision-aware resampling（确定性修订感知重采样）；
- append-only particle ledger（追加式粒子账本）；
- quarantine、promote、retract、corrected-revision；
- exactly-once promotion 检查和哈希链；
- identity decoy routing receipt（身份诱饵路由收据）；
- actor、identity、cause、regime 四轴行动轨迹；
- 两个完整系统新增臂继续保留 OPCEU、ORRER、PCHMP、CF-BOCPD、RGRC、CCRR、CIAV。

身份诱饵首次运行暴露了单对象 prototype spine 会拒绝另一实例。修复方式不是删除诱饵，而是增加可审计 target-object routing adapter：原始错误身份先进入 identity 轴，再把事件路由至当前目标对象的单对象主干。该适配边界已记录，但它仍不是完整 multi-object runtime（多对象运行时）。

## 失败机制判断

直接证据是：序贯无巩固与逐步投影的差异接近零，而相同序贯后端加入巩固后稳定恶化 `+0.0642`。当前账本将已晋升位置分布以固定 `0.28` 权重混入后续行动；在角色、原因或阶段改变后，这个分布会在新修订达到稳定晋升条件之前继续影响行动。

因此，“stale consolidation lag（过期巩固滞后）是主要伤害来源”是由臂间差异和当前实现共同支持的机制推断。它不是完整因果证明，下一版必须在新的 development seeds 上单独比较：

- fixed stale blend（固定旧分布混合）；
- revision-conditioned compatibility gate（修订条件兼容门）；
- uncertainty-decayed ledger influence（不确定性衰减账本影响）；
- immediate quarantine on actor/cause/regime conflict（人物／原因／阶段冲突时立即隔离）。

本轮 holdout 已经打开，不能据此回调混合权重、晋升阈值或稳定步数。任何修改必须进入新协议和新 sealed seeds。

## 科研裁决

本轮不支持：

- 序贯粒子持久化具有稳定行动收益；
- 当前粒子驱动可逆巩固有效；
- identity decoy 或 long recurrence 已经解决；
- 进入 neural amortized proposer 的确认实验；
- 完整结构二击败 corrected AMG。

本轮支持的工程事实是：跨时间 ancestry、可逆粒子账本和完整七算子路径已经能够联合运行并被行动 evaluator 消费。但“能运行”与“有方法贡献”必须分开；当前巩固策略的行动贡献为负。

这不构成删除 Neural Amortized Proposal + Rao–Blackwellized Typed Particle Revision + Reversible Consolidation 路线的决定。下一次有价值的实验应是全新开发／封存分割下的 consolidation compatibility gate（巩固兼容门），而不是直接训练神经提议器。

## Artifact 与验证

- manifest：`configs/project_two_experiments/structure_two_sequential_gate_manifest_v0_1.json`
- sealed seeds：`configs/project_two_experiments/structure_two_sequential_gate_sealed_seeds_v0_1.json`
- artifact：`artifacts/project_two_v04_development/structure_two_sequential_consolidation_gate_v0_1.json`
- artifact content SHA-256：`bac1c1b5117de4bbd3bf9e9fc003f3bc7bf042e180f615afbe30fb0a05bb847d`
- artifact byte SHA-256：`0b34679c2d29b915234f0de24521c6f01671b6e9e4f0e9eda06a5848dcdb6fb4`
- benchmark source SHA-256：`ae2919081a6eb529395530452a4e3b6a3d0a6442580c13dcb3a8abbf6fcaa6e3`
- quick verify：通过；
- full deterministic recomputation：通过。
