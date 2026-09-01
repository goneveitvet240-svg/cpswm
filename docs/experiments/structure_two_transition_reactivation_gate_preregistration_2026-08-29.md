# 结构二原因／阶段转移＋账本再激活门：预注册

日期：2026-08-29  
协议：`structure-two-transition-reactivation-gate@0.1`

## 冻结问题

前一轮证明 immediate conflict quarantine（冲突立即隔离）可以消除固定旧账本分布造成的主要伤害，但 adaptive consolidation（自适应巩固）没有优于序贯无巩固，并在 cause/regime guardrail 上失败。

本轮使用全新的场景族和封存种子，检验两个未解决机制：

1. conflict-aware transition proposal（冲突感知转移提议）：当当前 cause/regime 证据与粒子祖先冲突时，降低同状态持久奖励，并显式增加与当前原因／阶段一致的转移候选权重；
2. historical regime reactivation（历史阶段再激活）：账本保存已晋升 signature 的历史位置分布；同一 signature 复现并稳定后，以 `reactivate` 操作恢复历史分布，而不是把它当作全新阶段。

所有带巩固的候选都保留冲突立即隔离。仍不训练 neural amortized proposer。

## 冻结实验臂

1. corrected AMG 外部锚点；
2. 逐步粒子投影；
3. 原序贯无巩固；
4. 原序贯＋冲突立即隔离；
5. 冲突感知转移提议、无巩固；
6. 原序贯＋历史阶段再激活；
7. 冲突感知转移＋历史阶段再激活联合臂。

每臂、每场景族独立搜索 3 个 profile；所有粒子臂固定 `K=24`，完整系统臂保留七算子和四轴行动读出。

## 冻结通过条件

联合门同时要求：

1. `joint transition reactivation - sequential no consolidation` 的 95% paired interval 上界 `< 0`；
2. cause-regime 与 long-reactivation 两个 required families 的平均差都 `< 0`；
3. identity 与 role guardrail 的平均差都 `≤ +0.02`；
4. 冲突感知臂产生非空 conflict transition proposal receipt；
5. 再激活臂产生非空 `reactivate` ledger receipt；
6. ancestry、exactly-once、七算子、同一实际消费流门全部通过。

若仅 transition-no-consolidation 改善而联合臂不改善，说明账本再激活仍无正价值。若联合臂通过，才允许把可逆巩固标记为候选正贡献；它仍不足以直接验证 neural proposer 或真实机器人外推。
