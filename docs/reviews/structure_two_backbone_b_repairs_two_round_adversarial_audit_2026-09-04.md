# 结构二 B 修复：两轮自我攻击对抗审计

冻结日期：2026-09-04
最终复核：2026-09-05
范围：Gate B v0.7、Tasks 7–9、Tasks 11–13、P5、Task 7/8 证据工件及可能绕回旧 Gate B 的授权路径。

## 总结

> **2026-09-05 后续冻结更新：** 本文主体记录 v0.2 两轮攻击的历史结果；其 Task 7/8
> 科学结论已由预先冻结的新 v0.3 注册复算取代。当前 Task 7 v0.3 仍失败；Task 8 v0.3 在直接
> 消费 `(H+Z,C)` 交叉项的 consequential action/utility endpoint（后果性行动/效用端点）上通过
> 任务专用 D0 门。两者工件现已逐路径登记全部正向输出并要求 fresh task-specific recomputation。
> 这不改变 Gate B v0.8=`FROZEN_NOT_EXECUTED`、七算子授权=false 或外部效能解释禁止。

两轮对抗审计已完成。第一轮和第二轮都发现了实质问题，修复后重新执行定向回归。最终没有把
工程不变量、内部哈希自洽或调用方提交的“完整”对象误写成科学通过：

```text
Gate B v0.7                 = FROZEN_NOT_EXECUTED
Task 7                      = FAILED scientific gate
Task 8 v0.2 historical       = FAILED action/utility gate
Task 8 v0.3 current          = PASSED task-specific D0 gate; no formal receipt
Task 9                      = DEFINED_NOT_RUN
Tasks 11, 12, 13 and P5     = DEFINED_NOT_RUN
trusted seven-op ablation   = NOT_AUTHORIZED
```

“未再发现阻断级代码缺陷”只针对本文件列出的 B 修复面与攻击矩阵，不代表对整个仓库或未来外部
执行环境的穷尽性证明。

## 审计原则

每个正向或后果性输出都按以下链路检查：输入与冻结配置、语义载荷、运行实现、执行身份、独立
托管、重放／新鲜度、状态转换及最终消费者。重点构造字段齐全、自洽重哈希、调用方换身份、跨
版本状态绕行等路径；单纯检查负例或字段存在不算完成。

## 第一轮：实现与测量攻击

### 发现并修复

1. **Task 7 末端状态停留在窗口右边界。** 当窗口位于长序列中部时，局部路径可能没有恢复固定
   后缀后的最终 `current/retired/created`。修复为先拼接完整 boundary checkpoints（边界检查点），
   再从最后一个 boundary 恢复 live terminal state（实时末端状态）。
2. **Task 7 固定观测纠正与解析块不同步。** 旧路径只改 likelihood ratio（似然比），随后可能从
   analytic block（解析块）撤销一个从未加入的修正值。新增 O(1) 的旧观测 downdate（撤销）与
   修正观测 update（更新），并与 full rebuild（完整重建）逐 cell 对照。
3. **Task 8 可把行动分布变化误当成效用收益。** 总门改为同时要求 belief instrument（信念仪器）、
   action posterior distance（行动后验距离）和方向正确的 downstream-cost advantage（下游代价
   优势）；仅 distribution shift（分布偏移）不得通过。
4. **Task 7/8 runner 与配置仅记 hash、没有真正消费配置。** runner 现在严格加载冻结配置、拒绝
   duplicate JSON keys（重复键），从配置传入设计与阈值，并在代码常量与配置漂移时停止执行。
5. **Gate B 可由任意共同标签或随机动作抽样制造差异。** 改为完整冻结 21,601 信念标签和 39 行动
   标签，动作采用 deterministic argmax + lexical tie-break（确定性最大值加字典序破平），且动作
   分歧只能由同一步的实质 action TV 支撑。
6. **Task 9 允许过小／事后人口与调用方声明效应。** 冻结 40 household clusters × 2 seeds、8 个
   validation households、`MDE=0.25`、计划功效 `0.927`，并从原始语义事件重算逐 unit utility 和
   `U11-U10-U01+U00`。
7. **旧证据 envelope 可凭自洽重哈希通过。** Task 7/8 工件验证改为任务专用 fresh recomputation
   （新鲜重算）；旧 D0 checkpoint 明确标记为 superseded（已取代），不能授权七算子结论。

### 第一轮结果

- Task 7 的窗口／解析块／末端状态、前后缀、fallback 和成本攻击均通过回归；但注册科学门仍因
  contamination 与 recovery 失败。
- Task 8 的软耦合在信念层可测，行动／效用层保持失败，没有进行事后阈值放宽。
- Gate B、Task 9、Tasks 11–13/P5 的本地正向字段均不能打开正式门。

## 第二轮：信任链与跨版本状态机攻击

### 发现并修复

1. **HIGH：Tasks 11–13 的伪独立重算。** 两份完全由调用方构造、内容相同而只改变
   `execution_id/producer_id` 的结果，曾可让本地验证器签发正式 binding receipt（绑定回执）。修复
   后本地最多生成 `BindingCandidateDiagnostic`；其 authority、custody、freshness、replay、formal
   resolution 与 seven-operator authorization 均固定为 `false`。`derive_binding_resolution` 和
   `verify_binding_resolution` 对所有本地输入失败关闭，直到外层独立 authority 提供不可伪造的
   opaque handle。
2. **MEDIUM／未来 HIGH：Task 9 的 treatment-specific implementation substitution（按处理臂替换
   实现）。** 攻击者曾可在 cell 10 替换 OPCEU implementation hash 并同步重哈希回执。现在同一
   operator 的运行时 hash 必须跨全部 coupling、cell 与 80 units 一致，且每个回执绑定冻结
   implementation manifest 与 source bundle。当前 implementation manifest 明确为 `NOT_ENROLLED`，
   因而报告只能写“内部一致”，`operator_implementation_identity_verified=false`。
3. **MEDIUM：旧 Gate B v0.6 绕回当前授权状态。** v0.9 external-confirmation 原本仍可能用已废止的
   action-only v0.6 score 生成通用正向状态。其 chain verifier、combined verifier 和正向模型构造
   现在均以 `gate_b_v0_7_receipt_required` 失败关闭；v0.6 efficacy/readiness 路径也增加硬置为 false
   的 current-v0.7 receipt 条件。旧结果仍可作历史取证，但不能重新进入当前授权状态机。

### 第二轮复核矩阵

| 表面 | 反例 | 最终行为 |
|---|---|---|
| Task 7 | 中段窗口、固定后缀改变最终状态；checkpoint/source tamper；无可桥接提议 | 末端与解析块一致；篡改失败关闭；合法 fallback 有回执 |
| Task 8 | 只有 belief TV；只有 action shift；无方向性 utility benefit | 总门保持 false |
| Gate B v0.7 | 任意标签、随机动作、数值噪声翻转、post-truth、预算／信息不齐 | 全部拒绝或仅 diagnostic；正式门 false |
| Task 9 | 事后选 unit、双簇伪确定性、伪效应、cell-specific implementation、换 source bundle | 全部拒绝；本地只算术诊断 |
| Tasks 11–13 | 两份 caller-authored“独立”结果、自洽重哈希诊断、跨任务解析 | 只给无权力候选诊断；正式解析拒绝 |
| P5 | 缺臂／缺阶段／缺轴／缺操作、oracle 泄漏、伪 `passed` | 全部拒绝；只输出互斥瓶颈诊断 |
| 证据工件 | 字段齐全且全部重哈希的假正向 artifact、Task 7/8 对调 | 必须任务专用新鲜重算；拒绝替换 |
| 旧授权状态机 | v0.6 signed Gate B、手造 v0.9 combined object | `gate_b_v0_7_receipt_required`；当前授权 false |

## 最终验证

- Round 1 定向集合：144 tests（核心仪器、Gate B、Task 9、Tasks 11–13/P5）。
- Round 2 定向集合：92 tests（工件新鲜重算、旧 checkpoint、Task 9 旁路、v0.6/v0.9 授权状态机）。
- Task 7 与 Task 8 已存工件均通过任务专用 fresh recomputation。
- B 新增／修改核心文件通过 Ruff；Gate B、Task 9、开放任务与 Task 7/8 核心通过 strict mypy。
- 全局 source bundle 与 checkpoint 未在本轮最终冻结：并行 D 修复仍在写结构二源码，待 B、D 都
  停止后由 A 工程可信门统一重算并跑全量回归。

## 仍然真实存在的阻塞项

1. Task 7 v0.3：多轴/action equivalence 与污染门失败；科学总门仍关闭。
2. Task 8 v0.3：任务专用 D0 门通过，但缺 independent-custody formal receipt（独立托管正式
   回执），不得提升为 Gate B 或七算子授权。
3. Gate B：current v0.8 缺新密封十臂 trace、受信执行、独立托管和 external fidelity。
4. Task 9：正式实现身份清单与独立 trust anchor 尚未登记，80-unit 协议尚未运行。
5. Tasks 11–13/P5：只有独立定义与本地诊断合同，尚无受信正式执行／解析。

因此本审计的通过含义仅为：列出的实现与失败关闭不变量在定向范围内成立。它不意味着科学门
通过，也不允许进入可信七算子系统消融。
