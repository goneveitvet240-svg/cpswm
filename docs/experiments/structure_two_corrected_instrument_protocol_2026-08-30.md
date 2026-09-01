# 结构二校正评测仪器 v0.2 协议

日期：2026-08-30  
协议：`structure-two-corrected-evaluation-instrument@0.2`

## 目的

本协议只修复评测仪器，不修改结构二方法，也不改写 v0.1 已封存结果。它是
post-hoc validation-only diagnostic（事后、仅验证集诊断），不能形成新的密封留出集结论。

## 固定边界

- 复用 v0.1 的 8 个 validation seeds（验证种子）、六类场景、24 步长度和已选参数；不重新调参。
- 不读取或计分 sealed holdout（密封留出集）。
- 保留结构二完整的 actor、identity、cause、regime 四轴和可逆修订链。
- v0.1 源码、manifest（清单）和报告按 SHA-256 固定，任何字节变化都使 v0.2 拒绝运行。

## 四项修复

1. Dual-task readout（双任务读出）：search（搜索）从最后可见位置开始；put-back（放回）仍由主人习惯位置后验决定。
2. Bayesian physical verification（贝叶斯物理验证）：将验证结果作为带可靠度的 likelihood（似然）乘到原先验上，不再硬重置为 0.90/0.10。
3. External-execution cost boundary（外部执行成本边界）：只有存在唯一、真实执行且需要回滚的 action execution receipt（行动执行凭据）才收环境维修费；账本内部 `retract` 和 `corrected_revision` 只作审计，不计环境成本。
4. Validity gates（有效性门）：强近邻必须产生足够不同的行动；CARE 不能在几乎所有回合机械地用满验证预算。

## 预先固定的有效性门槛

- 已发表近邻平均成对行动分歧率至少 0.01。
- 至少 20% 回合中，已发表近邻产生不止一种完整行动轨迹。
- 每个已发表近邻至少与一个同伴存在非零行动分歧。
- CARE 用满全部物理验证预算的回合比例不得超过 0.95。

只有 instrument integrity（仪器完整性）和 comparison validity（比较有效性）都通过，结果才允许进入方法优劣判断。

