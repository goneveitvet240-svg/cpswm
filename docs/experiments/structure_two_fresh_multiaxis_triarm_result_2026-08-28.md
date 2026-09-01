# 结构二 fresh multi-axis 三方行动比较：结果

日期：2026-08-28  
协议：`structure-two-fresh-multiaxis-triarm@0.1`  
证据等级：D0 synthetic fresh-family development evidence（D0 合成新场景族开发证据）

## 结论

新增的 per-step typed-particle action projection（逐步类型化粒子行动投影）在行动级显著改善了旧完整七算子系统，但仍没有击败 corrected AMG matched replay adapter（修正 AMG 匹配重放适配器）。它还不是完整的 sequential Rao–Blackwellized typed particle revision（序贯 Rao–Blackwell 化类型化粒子修订）运行时。

| 配对比较（左−右） | 每步净行动损失差 | 95% paired cluster interval | 判断 |
|---|---:|---:|---|
| 联合复苏 − 旧完整系统 | **−0.1344** | **[−0.1521, −0.1146]** | 稳定改善旧系统 |
| 联合复苏 − corrected AMG | **+0.3313** | **[+0.2938, +0.3671]** | 仍明显落后 AMG |
| 旧完整系统 − corrected AMG | **+0.4656** | **[+0.4315, +0.4991]** | 旧系统落后更大 |

负数表示左侧损失更低。区间按 12 个封存 holdout seeds（留出种子）跨四个场景族聚类计算。

四个场景族平均每步净行动损失：

- corrected AMG：`0.3563`；
- 旧完整多轴系统：`0.8219`；
- 联合复苏多轴系统：`0.6875`。

因此，新机制收回了旧完整系统与 AMG 差距中的约 `28.9%`，但剩余差距仍很大，不能支持整体优越性主张。

## 新场景族分解

| 新场景族 | 联合复苏−旧系统 | 联合复苏−AMG | 局部判断 |
|---|---:|---:|---|
| `fresh_role_chain_shift` | **−0.2500** | +0.3920 | 角色链下明显改善，但仍输 AMG |
| `fresh_identity_occlusion_reentry` | 0.0000 | +0.2381 | 与旧系统打平 |
| `fresh_cause_collision_short` | **−0.2875** | +0.3295 | 原因碰撞/短阶段下明显改善 |
| `fresh_long_recurrence_open_actor` | 0.0000 | +0.3654 | 与旧系统打平 |

改善集中在 role-chain shift（角色链切换）与 cause collision（原因碰撞）两类场景；身份遮挡重现和长周期未知人物场景没有产生行动级增益。这与联合约束当前重点编码 `actor–cause`、`identity–cause`、`cause–regime` 相一致，但也暴露出身份和长周期记忆连接仍不足。

## 多轴行动读出验证

行动层现在显式消费：

- actor posterior（人物后验）；
- identity target probability（目标实例概率）；
- cause posterior（原因后验）；
- active regime 与 regime-change probability（活动阶段与阶段变化概率）。

注册的 8 项轴扰动门全部通过：旧完整系统和联合复苏系统分别对四个轴的扰动产生不同的行动分布。四个场景族 × 两个完整系统臂的 8 项 runtime trace coverage（运行时轨迹覆盖）也全部通过。

联合臂在每一步重新生成 `K=24` typed action particles（类型化行动粒子），位置分布作为 Rao–Blackwellized analytic block（Rao–Blackwell 化解析块）在每个粒子下计算。当前没有跨时间 particle ancestry（粒子祖先链）、persistent SMC state（持久序贯蒙特卡洛状态）或由粒子修订驱动的 consolidation ledger（巩固账本），因此不能把本实验写成完整联合修订与可逆巩固已经集成。

## 七算子与 CIAV 闭环

两个完整系统臂均保留：OPCEU、ORRER、PCHMP、CF-BOCPD、RGRC、CCRR、CIAV。

运行前审核发现多轴 wrapper 最初缓存了 CIAV 更新前的位置分布，使主动观察付费却不进入当前行动。现已改为在 `predict` 时读取最新 fast-action snapshot（快速行动快照），随后重新运行全部实验。两个完整系统臂在每个场景族的验证成本相同，因此联合−旧系统的改善不是 CIAV 计费差异造成的。

corrected AMG 不具备 CIAV；其验证成本为零。这是系统能力差异的一部分，但也意味着联合系统相对 AMG 的净效用比较已经计入完整系统主动观察的实际成本。

## 冻结与公平性

- 四个场景族不复用旧 16 格 factorial 配置；
- 4 个 validation seeds 用于独立调参；
- 12 个 holdout seeds 以 SHA-256 commitments 公开绑定；
- 所有场景族调参完成后，runner 才打开 evaluator-only sealed seed file；
- 每臂、每场景族搜索预算均为 3；
- 三臂使用相同 family × seed 可见重放、反馈和 evaluator；
- 每一行同时记录源 replay hash（重放哈希）与各臂实际消费的 transformed visible stream hash（变换后可见事件流哈希），三臂均一致；
- 七算子保留由运行时对象收据验证，不再只依赖静态声明；
- 正式 artifact 不披露原始 holdout seeds；
- corrected AMG 继续标记为 matched replay adapter，不冒充原论文忠实复现。

## 执行中发现并修复的问题

1. active-regime cause posterior 未显式包含 `noise` 零质量键，导致完整类型枚举 fail-closed；已补全四原因支持。
2. 低观察覆盖下，evaluator truth 可能出现可见轨迹从未观察的位置；旧评分器对该位置直接 `KeyError`。已改为仅在 evaluator 内计数，同时不把该位置加入模型可见行动空间。
3. CIAV 更新后多轴读出读取旧缓存；已改为行动时读取最新 snapshot。
4. 确定性验证器最初把 JSON list 与内存 tuple 直接比较，产生假性不一致；已改用 canonical content identity（规范内容身份）。

5. 第一轮对抗审核发现“同一输入”和“七算子保留”主要依赖自声明；已增加实际消费事件流哈希与运行时算子收据。
6. 第二轮对抗审核发现 paired differences（配对差值）、seed commitment 顺序与汇总 gate 可被局部篡改后重新签名；验证器现从逐臂损失重算差值，并强制唯一顺序与底层/汇总一致。

这些修复后，正式 artifact 已通过快速验证和一次完整独立重算，content hash 完全一致。

## 科研边界

本轮支持的有限主张是：

> 在四个运行前冻结的新合成场景族中，确定性逐步类型化粒子行动投影稳定改善了旧完整七算子系统，主要收益来自角色链切换与原因碰撞场景。

本轮不支持：

- 完整结构二击败 AMG；
- neural amortized proposer（神经摊销提议器）有效；
- 序贯粒子修订、粒子祖先追踪或粒子驱动的可逆巩固已经实现；
- 身份遮挡或长期未知人物问题已经解决；
- corrected AMG 是原论文的忠实复现；
- 结果可外推到真实家庭、RGB-D 或机器人执行。

## Artifact 与完整性

- manifest：`configs/project_two_experiments/structure_two_fresh_triarm_manifest_v0_1.json`
- sealed seeds：`configs/project_two_experiments/structure_two_fresh_triarm_sealed_seeds_v0_1.json`
- artifact：`artifacts/project_two_v04_development/structure_two_fresh_multiaxis_triarm_v0_1.json`
- content SHA-256：`5481995aef02586c7144ef8f89f322593ea1e55acbeb683af0236b28763fa47f`
- benchmark source SHA-256：`d5c0b97b0e940c3970581fd5abff77b8d0c607ab3381d835b19a7d7e0c15c596`
- action evaluator source SHA-256：`babdf2cfb57a4a0875e8dbcab53ab8f458a7c174499016af0ac6e1008a9c8c88`
- manifest SHA-256：`3eb2380e0536c29f3283ad96c392dba5c2c3d63cbbeeda9f14b3ada03aff7972`
- sealed seed file SHA-256：`33326c76c63cf8cac671b8e1ee8918564e77773bd0acdf69737d0da636cce3a7`
- artifact byte SHA-256：`4d25e1db04d2272cee6d3525e8a793a396135beae2afdbfbf6c96de28728fe5b`
