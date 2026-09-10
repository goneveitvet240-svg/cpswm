# 结构二 evaluation-only direct P5 联通结果 v0.1

日期：2026-09-10
状态：`D0_ENGINEERING_BRINGUP_ONLY`

## 结论

第一项工作的工程前半段已经通过：现在可以在不改变正常 adaptive router（自适应路由器）的前提下，
用一个显式 evaluation-only（仅评测）回执直接执行生产 `P5_FULL_EAGER`。fresh run（新鲜运行）证明
调用的是同一个生产系统持有的真实算子实例，并得到完整的调用/消费轨迹。

本轮不是三臂行动死亡测试，不能回答 P5 是否优于 learned matched two-stage 或独立调参 AMG，也不能
回答 Task 7/8/9 是否通过。

## 实测轨迹

正常 router 在同一组低风险、零 debt 特征上仍选择 `P0_SAFE_DEFERRED`；direct 入口生成原因固定为
`evaluation_only_direct_p5_ceiling_override` 的独立回执，随后执行真实 P5。

主路径共 7 个调用：

```text
OPCEU
ORRER/CHEH
PCHMP        <- ORRER/CHEH
CF-BOCPD     <- PCHMP
CCRR         <- PCHMP, CF-BOCPD
RGRC         <- OPCEU, PCHMP, CCRR
CIAV         <- CCRR, RGRC
```

CIAV 获得异位置 observation（观测）后，又产生 6 个反馈闭环调用：

```text
OPCEU        <- CIAV
ORRER/CHEH   <- CIAV
PCHMP        <- ORRER/CHEH(feedback)
CF-BOCPD     <- PCHMP(feedback)
CCRR         <- PCHMP(feedback), CF-BOCPD(feedback)
RGRC         <- OPCEU(feedback), PCHMP(feedback), CCRR(feedback)
```

因此总数是 13 条真实 invocation receipts（调用回执），不是只登记七个算子名。每条回执含 runtime
execution ID、operator instance ID、callable symbol、invocation ID、输入/输出 hash、上游 output IDs
和链式 receipt hash；现有 trace verifier 对两段 DAG 都重新计算。

## 新增边界

- direct P5 必须提供 CIAV runtime input；
- authorization、privacy、safety 必须全部通过；
- 不允许 stale feature snapshot；
- 不允许借 direct 入口绕过 pending debt；
- 正常 router 的阈值和选择逻辑未修改；
- direct receipt 与普通 router-selected P5、debt replay P5 可区分；
- SEARCH 与 PUT_BACK 现在可由同一个 deterministic typed decoder 生成，支持相同、确定性的排序与
  tie-breaking。

## 当前尚未通过的门

1. `cross_arm_ciav_matching_established=false`：本轮只有一个 P5 engineering probe，尚不能证明三臂
   获得同一信息并承担同一成本。
2. `action_benefit_established=false`：单步联通不能产生统计行动收益结论。
3. learned matched two-stage 现有输出仍是 `VERIFY/PROCEED`，还没有冻结为与 P5/AMG 同支持集的
   location distributions；不能偷偷用一个新映射替代。
4. production debt replay confirmation 尚未开始；它按用户选定顺序排在 direct P5 上界测试之后。

## 复现

```bash
uv run --frozen pytest -q \
  tests/test_structure_two_adaptive_runtime.py \
  tests/test_structure_two_adaptive_runtime_adversarial_round1.py \
  tests/test_structure_two_adaptive_runtime_adversarial_round2.py \
  tests/test_structure_two_execution_interface.py \
  tests/test_structure_two_production_system.py \
  tests/test_structure_two_action_utility_construct_gate.py \
  tests/test_structure_two_p5_direct_trace_probe.py

PYTHONPATH=src uv run --frozen python \
  apps/evaluation_runner/run_structure_two_p5_direct_trace_probe.py
```

本轮定向回归为 135 passed；Mypy、Ruff 和 `git diff --check` 均通过。fresh artifact 写入
`benchmarks/structure_two/structure_two_p5_direct_trace_probe_v0_1.json`，content SHA-256 为
`025670c35ac74918e2955817ac4d388c24fbc0a4d3772b6113734587d7d0a351`。
