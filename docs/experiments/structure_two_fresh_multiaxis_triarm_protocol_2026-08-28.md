# 结构二 fresh multi-axis 三方行动比较协议 v0.1

日期：2026-08-28  
协议：`structure-two-fresh-multiaxis-triarm@0.1`

## 冻结顺序

本协议、四个 fresh scenario families（新场景族）、4 个 validation seeds（验证种子）、12 个 holdout seed commitments（留出种子承诺）、`K=24` 和搜索空间在首次 benchmark run（基准运行）前写入。

这是 repository-local freeze（仓库内冻结），没有外部时间戳机构，不能称公开预注册。封存文件对 runner 的 evaluator 路径可见，但 tuning path（调参路径）只接收 validation episodes；报告不得泄露 holdout 原始种子，只记录承诺及封存文件哈希。

## 新场景族

四个场景族不复用旧 16 格 factorial（析因）配置：

1. `fresh_role_chain_shift`：跨人物角色链、较高归因混合、阶段恢复；
2. `fresh_identity_occlusion_reentry`：低身份置信度、遮挡后重现；
3. `fresh_cause_collision_short`：短阶段与原因碰撞、较强反馈翻转；
4. `fresh_long_recurrence_open_actor`：长周期恢复与多次未知人物事件。

完整参数与 seed commitments 固定在 `configs/project_two_experiments/structure_two_fresh_triarm_manifest_v0_1.json`。

## 三个比较臂

1. `corrected_amg`：现有 prior-corrected odds（先验修正赔率）AMG matched replay adapter；
2. `old_full_multiaxis`：旧完整七算子系统，使用新的多轴行动表面，但不使用联合类型化粒子复苏；
3. `joint_revision_multiaxis`：完整七算子系统，加 `actor × identity × cause × regime` 类型化粒子联合复苏，`K=24`。

七个算子在两个完整系统臂中全部开启。新模块不得删除 OPCEU、ORRER、PCHMP、CF-BOCPD、RGRC、CCRR 或 CIAV。

## 多轴行动读出要求

旧完整系统与联合复苏系统必须在每一步生成审计记录，证明行动分布实际消费：

- actor posterior（人物后验）；
- identity confidence（实例身份置信度）；
- cause posterior（原因后验）；
- active regime / regime-change belief（活动阶段／阶段变化信念）。

任一轴缺失不得静默当作确定值；必须使用显式中性／未知质量并写入 trace。对任一轴进行可见输入扰动，至少存在一个注册构造使行动分布改变，否则多轴消费门失败。

## 公平性

- 三臂使用相同 visible replay（可见重放）、反馈、行动空间、CIAV 成本和 evaluator；
- 每臂每场景族独立使用 3 个 validation candidates（验证候选）调参；
- 调参函数不得接收 holdout truth、holdout episodes 或原始 holdout seeds；
- 三臂在相同 family × seed 对上配对评分；
- corrected AMG 明确标记为 matched replay adapter，不冒充原论文忠实复现。

## 终点与比较

主要终点：`net_action_loss_per_step = (cumulative_action_regret + verification_cost) / steps`。

冻结三项 paired differences（配对差值，负数表示左侧更好）：

1. joint revision − old full；
2. joint revision − corrected AMG；
3. old full − corrected AMG。

按 holdout seed 跨四个场景族聚类，报告均值和 95% paired cluster bootstrap interval（配对聚类自助区间）。posterior/support 指标只作机制诊断。

## 证据边界

无论结果如何，本轮仍是 D0 synthetic fresh-family evidence（D0 合成新场景族证据）。它可以推翻或支持继续集成，但不能单独建立 ICLR 优越性、真实家庭外部有效性、忠实 AMG 复现或 neural amortized proposer（神经摊销提议器）有效性。
