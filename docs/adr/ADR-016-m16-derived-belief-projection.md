# ADR-016：M16 采用可重建的派生信念投影

状态：Accepted（已接受）  
日期：2026-08-10  
决策者：项目负责人  
适用版本：技术框架 v1.1 及之后版本

## 背景

M13 需要表达 `located_at`、`belongs_to`、`held_by` 等带时间和证据的关系主张，M16 需要表达位置、身份、拥有者、状态和关系的概率后验。如果两者都被定义为当前世界状态的权威存储，会产生双写、更新顺序不一致和查询冲突。

需要明确以下问题：

- 单条关系主张的来源质量保存在哪里；
- 综合多条支持、冲突和负证据后的后验概率保存在哪里；
- 发生数据损坏或更换推理算法时，哪一部分必须能够重建；
- 查询如何判断 M16 是否已经消费最新的 M13–M15 输入。

## 决策

采用方案 `(b)`：M13/M14/M15 保存规范输入，M16 作为 derived projection（派生投影视图）。

规范事实源分别为：

- M13：实体和关系主张的 append-only（追加式）规范记录；
- M14：事件和情景时间线的 append-only 规范记录；
- M15：主张、事件、观测、模型和行动之间的证据谱系。

M16 负责：

- 读取指定 `input_watermark` 以内的 M13–M15 输入；
- 综合观测似然、习惯先验、隐藏事件候选和生命周期状态；
- 生成带版本的 `BeliefSnapshot`；
- 提供位置、身份、拥有者、状态和关系的 `posterior_probability`；
- 支持增量重算和全量重建。

M16 可以物理持久化、缓存和建立索引，但不构成不可替代的原始事实源。删除 M16 后，系统必须能够利用相同规范输入、配置和模型版本重新生成可比较的投影。

## 可靠度与后验概率语义

M13/M14 使用：

```text
evidence_reliability
```

它描述单条观测、主张或事件来源的质量。

M16 使用：

```text
posterior_probability
```

它描述综合全部支持证据、冲突证据、负证据和先验之后，某个世界状态成立的概率。

禁止使用一个无语义的 `confidence` 字段同时表示这两个概念。

## 投影版本要求

每个 `BeliefSnapshot` 必须至少记录：

```text
projection_id
projection_version
parent_projection_id
input_watermark
input_watermark.global_commit_seq
input_watermark.transaction_id
input_watermark.source_local_seq
inference_model_version
habit_model_version
observation_likelihood_model_versions
generated_at
rebuild_from_checkpoint_id
rebuild_cost_estimate
```

单事务日志阶段的 `input_watermark` 使用全局单调 `global_commit_seq`；只有规范输入变为无法共享事务序列的分布式写入者时，才复审是否引入 vector watermark（向量水位）。

同一组规范输入、模型版本和配置必须产生可复现或在声明数值容差内可比较的投影。

## 更新顺序

```text
新观测或行动反馈
→ M13/M14 追加主张或事件
→ M15 记录证据谱系
→ M16 消费新的 input_watermark
→ 生成新的不可变 BeliefSnapshot
→ M20 在指定一致性模式下读取
```

M13/M14 已经超过 M16 `input_watermark` 时，M20 不得把新规范记录与旧投影静默混合为同一个当前状态回答。

## Checkpoint 与重建成本

M16 必须按照事件数、时间或预计重放成本生成 `ProjectionCheckpoint`。重建前生成 `RebuildCostEstimate`，至少包含：

```text
rebuild_from_checkpoint_id
records_to_replay
estimated_wall_time_ms
estimated_peak_memory_bytes
estimator_version
```

用户删除、证据撤回或模型版本失效影响 checkpoint 时，包含相关证据的 checkpoint 及所有依赖后代必须失效。系统只能从最近不含失效证据的有效 checkpoint 重建，并记录实际重建成本。

## 结果

正面影响：

- 消除 M13 与 M16 的双重权威；
- 支持完整审计和历史重放；
- 更换概率推理方法时不需要迁移原始证据；
- 可以并行生成多个推理方法的投影用于公平比较；
- 后验能够回溯到具体输入水位和模型版本。

需要承担的工程成本：

- M16 必须实现增量投影或可接受成本的批量重建；
- 查询必须处理 `projection_lag`；
- 必须维护输入水位、幂等性和投影版本；
- 规范输入与派生投影之间采用明确的最终一致性语义。

## 未采用的方案

### 方案 (a)：M13 保存分布引用，M16 保存权威分布

未采用。该方案会使 M13 在关键概率关系上依赖 M16 解引用，并把不可替代的状态权威放入 M16。

### 方案 (c)：按关系生命周期拆分 M13 与 M16

未采用。该方案需要永久维护快关系、慢关系和习惯关系的分类及跨模块迁移规则，查询层也需要按谓词路由。

## 复审条件

只有在以下情况出现时才复审本 ADR：

- M16 无法在目标数据规模下实现可接受的增量更新；
- M13–M15 规范记录不足以重建必要后验；
- 机器人实时控制要求的延迟无法通过投影缓存和增量更新满足；
- 新研究问题要求将某类信念本身视为不可派生的规范记录。
