# 结构二结构化联合复苏阻断门 v0.2

日期：2026-08-28  
协议：`structure-two-structured-rejuvenation-gate@0.2`

## 目的与边界

本门只检验 **Rao–Blackwellized Typed Particle Revision（Rao–Blackwell 化类型化粒子修订）** 的局部失败：在 high attribution ambiguity（高归因歧义）与 adverse delayed feedback（不利延迟反馈）同时出现时，单字段复苏的 truth support（真值支持率）只有 `0.50`。

这不是完整结构二、七算子系统或论文优越性的检验。七个算子全部保留；本轮不删除或替代任何算子。Neural amortized proposer（神经摊销提议器）在没有已冻结训练 artifact 前继续 fail-closed（失败关闭），本轮仅使用确定性的结构化提议核。

## 冻结比较

所有方法使用 v0.1 的同一 360 状态有限世界、同一 16 格 `2^4` 析因设计、同一可见证据和同一粒子预算 `K=24`：

1. `single_field_typed_revision`：v0.1 单字段复苏；
2. `structured_joint_typed_revision`：新增联合复苏；
3. `full_rerun_beam`：每次反馈后完整重跑的强参考线。

主要压力子集在运行前固定为：

```text
high_attribution_ambiguity = true
adverse_delayed_feedback = true
```

## 联合复苏核

联合核不枚举任意笛卡尔积，只从每个初始粒子生成以下 typed moves（类型化移动）：

- 所有 v0.1 单字段邻居；
- `mechanism + actor_path` 角色链：延迟帧观测对，以及由跨人物/未知人物路径触发的 `HANDOFF + actor_path`；
- `cause + regime`：保留父原因并采用延迟阶段，以及采用延迟原因与延迟阶段；
- `identity + cause`：采用延迟身份并分别配父原因或延迟原因。

候选统一经过结构约束与权重归一化，最终仍只保留 `K=24`。候选生成无真值访问。

## 预注册阻断门

以下条件必须全部成立，才允许进入 corrected AMG（修正 AMG）连接实验：

1. 压力子集 truth support 不低于单字段复苏；
2. 压力子集 truth support 至少达到完整重跑；
3. 压力子集 posterior TV（后验总变差）不高于单字段复苏；
4. 压力子集 action regret（行动遗憾）不高于单字段复苏；
5. 全部 16 格平均 posterior TV 不高于单字段复苏；
6. 全部 16 格平均 truth support 不低于单字段复苏；
7. 平均候选评估量不超过完整重跑的 `90%`。

任何一项失败，都记录为阻断门失败，不得事后改阈值。即使全部通过，也只能说明联合复苏修复了这个有限合成反例，不能声称击败 AMG 或获得论文级收益。

## 来源完整性

正式 JSON artifact 必须记录本 v0.2 源码、v0.1 冻结源码、选择方法源码、选择回执和本协议的 SHA-256，并包含 content hash（内容哈希）。v0.1 源码与结果不在本轮修改。
