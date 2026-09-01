# 结构二序贯粒子持久化＋可逆巩固机制门：预注册

日期：2026-08-29  
协议：`structure-two-sequential-consolidation-gate@0.1`  
证据等级：D0 synthetic mechanism evidence（D0 合成机制证据）

## 冻结目标

本实验不检验 neural amortized proposer（神经摊销提议器）。它只检验当前逐步粒子行动投影之上，temporal particle persistence（时间粒子持久化）和 particle-driven reversible consolidation（粒子驱动可逆巩固）是否产生独立行动收益。

完整结构二七算子在四个完整系统臂中保留。corrected AMG（修正 AMG）只作为第五个外部锚点。

## 冻结场景与数据边界

- 4 个 validation seeds：只用于每臂独立调参；
- 12 个 evaluator-only sealed seeds：以 SHA-256 commitment 绑定；
- `sequential_identity_decoy_swap`：注入可见但错误的高置信身份实例；
- `sequential_long_recurrence_delayed_feedback`：长期阶段复现、未知人物和延迟矛盾反馈；
- `sequential_role_chain_guardrail`、`sequential_cause_collision_guardrail`：保护上一轮已有收益；
- holdout 文件只能在所有场景族、所有臂调参结束后打开。

本地封存只提供过程隔离，不等于 independent custodian blind test（独立托管盲测）。

## 冻结实验臂

1. `old_full_multiaxis`：旧完整七算子＋因子化四轴行动读出；
2. `per_step_particle_projection`：当前每步重建的 `K=24` 类型化粒子行动投影；
3. `sequential_particle_no_consolidation`：跨时间 ancestry、transition weighting 与确定性修订感知重采样，但不写粒子巩固账本；
4. `sequential_particle_reversible_consolidation`：序贯粒子＋append-only quarantine/promote/retract/corrected-revision ledger（追加式隔离／晋升／撤回／修正账本）；
5. `corrected_amg`：匹配重放适配器外部锚点，不冒充 AMG 原方法忠实复现。

所有粒子臂固定 `K=24`，每臂、每场景族均搜索 3 个 profile（配置档），主要 endpoint 为每步净行动损失。

## 冻结通过条件

主要比较为：

`sequential_particle_reversible_consolidation - per_step_particle_projection`

同时满足才通过：

1. 12 个 seed cluster 上的 95% paired interval 上界 `< 0`；
2. identity-decoy 与 long-recurrence 两个 required families 的平均差都 `< 0`；
3. role-chain 与 cause-collision 两个 guardrail families 的平均差都 `≤ +0.02`；
4. 每个序贯 episode 都产生非空 ancestry trace；
5. 巩固臂执行 promote，并在主导修订改变时执行 retract/corrected revision；同一 revision exactly once promotion；
6. actor、identity、cause、regime 四轴均进入行动轨迹；
7. 所有完整系统臂保留七算子运行时收据。

若主要门失败，结论是“当前序贯持久化／巩固实现没有证明行动贡献”，而不是删除结构二中的相应能力。若通过，下一轮才允许冻结 deterministic proposal 与 neural amortized proposal 的匹配比较。
