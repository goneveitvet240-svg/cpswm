# 结构二 P5 三臂匹配 readiness v0.1

日期：2026-09-10
状态：`PROTOCOL_FROZEN_EXECUTION_BLOCKED`

## 结论

P5、learned matched two-stage、independently tuned AMG 三臂现在已有共同的 typed-location posterior
（类型化位置后验）合同和逐步 CIAV equality receipt（相等回执）合同。任何一臂缺席、改变候选集、
选择动作、观测结果、五类成本、隐私预算或真值释放阶段，验证器都会失败关闭。

但正式三臂运行尚不能诚实开始。fresh readiness（新鲜就绪检查）确认的阻断不是 P5 direct 入口；
而是两项尚未由项目所有者选择的方法定义、三臂 adapter/consumer（适配器/消费者），以及 negative
observation closure（负观测闭环）。

## 已冻结的数据范围

复用 `project-two-d0-multiseed-readout@0.5`，不另造有利数据：

- validation：20 episodes；
- development test：60 episodes；
- 总计：80 episodes、2,560 steps；
- 当前可直接构造 P5 transition：1,674 steps；
- negative 或 incomplete observation：886 steps；
- `confirmatory=false`，没有开启正式确认数据。

每个 episode 的 visible content hash、evaluator envelope hash、step manifest hash 和逐步 evaluator truth
commitment 均写入 readiness artifact；artifact 不向模型暴露原始 evaluator truth。

886/2,560（34.61%）步骤当前不能走 direct P5 正向 transition。忽略它们会把任务缩成“只看检测成功
步骤”，并造成 observation-conditioned selection bias（按观测成功条件选择的偏差），因此不能直接
删掉；必须补 negative-observation P5 closure，或者明确把这轮降格为局部诊断而不是完整死亡测试。

## 已完成的公共接口

### Typed location posterior

每个 arm 必须在相同 location support 上提交两套不同语义的分布：

1. `current_location_distribution` → SEARCH；
2. `owner_habit_location_distribution` → PUT_BACK。

随后只能调用同一个 `decode_task_separated_actions`。arm-specific decoder、tie-breaking 或动作后处理
不允许存在。

### Matched CIAV receipt

每一步必须有且只有三张回执，按 P5、learned two-stage、AMG 顺序覆盖；以下字段必须逐项完全相同：

- shared CIAV packet；
- candidate set；
- selected observation action；
- realized observation；
- motion/time/interruption/privacy/safety cost；
- privacy budget before/after；
- truth release phase。

测试已经覆盖重新签 hash 后的成本替换、privacy delta 伪造、缺失 support、缺臂和 action type 错配。

## 当前实际能力检查

已存在：

- evaluation-only direct P5 入口；
- P5 原生 PUT_BACK location distribution；
- shared SEARCH/PUT_BACK decoder；
- typed location posterior 与 exact three-arm CIAV receipt verifier。

尚不存在：

- P5 → 公共 typed-location posterior adapter；
- P5 → shared CIAV packet adapter；
- learned two-stage 的 location posterior 和 CIAV consumer；
- AMG 的 location posterior 和 CIAV consumer；
- negative-observation direct P5 closure。

## 需要项目所有者选择的两项方法定义

### A. shared CIAV scheduler

1. `exogenous_precommitted_schedule`：在运行前按 step commitment 固定动作，三臂均不得影响选择。
   这最干净地隔离推断与读出差异，但第一轮不评价各方法主动选观测的能力。
2. `p5_teacher_schedule_shared_to_all_arms`：由 P5 选择，然后三臂接收同一结果和成本。它给对照臂
   一个较强的信息条件，但会把 P5 的观测选择策略输入对照臂，不能把结果解释为独立 active policy
   比较。

建议第一轮采用 1；它与“先定位 P5 信息/行动上界”更一致，且不会把观测选择差异混入模型差异。

### B. learned two-stage location head

1. `shared_conditional_location_head_given_cause_event`：学习
   `p(C|x)p(E|C,x)`，再与三臂共用/配平的 `p(L_habit|C,E,x,history)` 条件位置头组合。它保留
   learned two-stage 的因果结构，并能把比较差异主要限制在联合/两阶段表示上。
2. `direct_current_and_habit_location_heads`：直接学习两个位置头。它可能是强行动基线，但不再回答
   原 Task 8 的 learned two-stage 结构问题。
3. `algebraic_two_stage_from_common_full_posterior`：从共同 full posterior 做严格链式分解。这是很强的
   algebraic falsifier（代数证伪器），但不能称为独立 learned two-stage pipeline。

建议第一轮采用 1；选项 2 可作为额外 action-only baseline，选项 3 可作为机制诊断，但二者不应替代
主要 matched learned comparator。

## 复现

```bash
uv run --frozen pytest -q \
  tests/test_structure_two_p5_three_arm_contract.py \
  tests/test_structure_two_p5_three_arm_readiness.py

PYTHONPATH=src uv run --frozen python \
  apps/evaluation_runner/run_structure_two_p5_three_arm_readiness.py
```

本轮新增合同与 readiness 测试为 9 passed；Mypy、Ruff 和 fresh recomputation 均通过。artifact：
`benchmarks/structure_two/structure_two_p5_three_arm_readiness_v0_1.json`，content SHA-256 为
`286c500925113063e4950326554b3e2a630bfc8d0c30d760eb2cd6635e474291`。
