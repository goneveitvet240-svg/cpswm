# Task 8 Learned Online-Compute v0.1 运行后复核

日期：2026-09-07  
覆盖：partial adversarial and scientific-design review（部分对抗与科学设计复核）

## 结论

v0.1 对一个最低成本问题给出了可信负结果：在相同数据、机器人可见输入、有效参数量、训练乘加数和推理乘加数下，当前 direct learned joint（直接学习式联合）没有优于 matched learned two-stage（匹配学习式两阶段）。因此“先停止昂贵扩展、重做联合机制”仍是符合预注册的默认处置。

但 v0.1 不是完整 Task 8，不能写成“联合建模普遍无效”或“完整 action-quality versus compute/latency frontier 已被否证”。

## 运行后发现的三项范围限制

1. **没有实测 physical latency（物理延迟）。** v0.1 精确匹配 deterministic linear multiply-adds（确定性线性乘加数），没有匹配 wall-clock latency、softmax / normalization（归一化）、联合输出乘法和硬件并行调度。因此它回答的是 equal-MAC slice（等乘加切片），不是完整 latency frontier（延迟前沿）。
2. **没有执行真正的 distribution shift（分布偏移）。** 工件中的 `distribution_shift_diagnostic` 是确认集内“高歧义 + 延迟反馈 + 开放世界参与者”因子单元的分层结果；训练、验证和确认仍来自同一生成分布。它只能叫 stress-cell subgroup（高压单元子组），不能叫干预式分布偏移证据。
3. **标签是分组代理，不是完整状态空间。** 原始 `C` 与 `E` 被各自压成 3 组、共 9 个联合格；这适合便宜预死亡测试，但不能代表结构二完整的 hidden event、actor、instance、cause、regime 和 unresolved（隐藏事件、参与者、实例、原因、状态段、未决）联合状态。

以上限制不制造假阳性：本轮结果为负，所有正式晋级字段仍关闭。它们限制的是负结论的外推范围。

## 对抗验证结果

最终定向集合全部通过。验证器从确认样本重新推导动作成本、簇差、Bonferroni 校正 bootstrap 下界、严格信号和处置结论，并拒绝：

- 重复或交叉种子；
- 重新哈希但不是验证集优胜者的选参回执；
- 逐臂参数或算力映射伪造；
- 缺失确认行；
- 动作成本与概率/真值不一致；
- 完整-looking 正向 frontier 与处置伪造；
- 重建外层和结果哈希后的 formal promotion（正式晋级）伪造；
- 当前源码包替换。

fresh-source replay（当前源码重放）与已落盘工件一致。这个验证建立当前源码内的内部一致性，不建立独立历史真实性或第二机器 custody（保管链）。

## v0.2 必补条件

下一轮只有在用户选定 joint redesign（联合机制重做）后才冻结；至少补齐：

- 同数据、有效参数、状态访问、训练算力与推理算力；
- 实测单样本 latency distribution（延迟分布），报告 p50/p95，并把 warm-up、线程数、批大小和硬件固定；
- 明确的 train-to-confirmatory distribution intervention（训练到确认集的分布干预），而不是只看同分布子组；
- full-state readout（完整状态读出）与当前 9 格代理同时报告；
- 仍使用 validation-only 选参、确认前冻结、簇级不确定性和 fail-closed 正向字段；
- 无论结果如何，owner contamination、recovery、safety、privacy、D1/D2、native baselines 和 independent custody 仍不得跳过。

## 当前可执行状态

- 当前 direct joint 路线：停止扩大投入；
- joint redesign：等待用户在明确选项间选择；
- D2 timing pilot：只允许并行准备设备、同步与记录格式，不得替 Task 8 开门；
- Task 10–13 大规模扩展、正式七算子消融和外部确认：保持关闭。
