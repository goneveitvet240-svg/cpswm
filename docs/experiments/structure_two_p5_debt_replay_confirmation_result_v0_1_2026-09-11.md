# 结构二 P5 production debt replay 确认结果 v0.1（2026-09-11）

> 2026-09-11 证据版本勘误：本文保留历史实验叙述，不能据此声明当前源码通过或首次未见已证实。旧三臂 v0.1 路径是 `4103bea` 失败重放的兼容引用；真正首次失败另存。历史源码缺失、首次 D0 来源不匹配及当前 v0.2 重放边界见 [窗口一证据链修复报告](../reviews/structure_two_evidence_repair_window1_2026-09-11.md)。

协议：`structure-two-p5-debt-replay-confirmation@0.1-development`

协议与实现 checkpoint：`80d0457`

状态：`PRODUCTION_DEBT_REPLAY_SEMANTIC_EQUIVALENCE_CONFIRMED`

证据等级：test-opened-split engineering confirmation（测试集已打开的工程路径确认）

## 1. 结论

在 60 个 test episodes 的全部 1,243 个 positive detected transitions（正检测转移）上，以下两条
状态连续积累的路径逐步语义一致：

1. evaluation-only direct `P5_FULL_EAGER`；
2. normal production router 先选 `P0_SAFE_DEFERRED`，生成一张绑定原转移的 debt certificate
   （欠账证书），到期后由 `replay_adaptive_debt` 强制执行 `P5_FULL_EAGER`。

12 项必要检查在 1,243/1,243 个转移上全部通过，失败转移为 0。由此可确认：当前 isolated
single-debt（隔离单欠账）的生产回放路径，会消费修复后的 PCHMP→CIAV sequential actor posterior
和 v0.6 dual-timescale readout，并产生与 direct P5 相同的 PUT_BACK 位置。

这消除了“direct P5 只在评估旁路有效、生产 replay 接线不同”的当前候选原因，但不改变科学结论：
post-hoc P5 相对 AMG 的绝对 PUT_BACK 改善仍只有 0.01354，未达到冻结的 0.02 门槛；严格 P5
action signal 仍为 false，Task 8 仍未通过，adaptive-router calibration 仍不启动。

## 2. 覆盖与逐项结果

- test episodes：60；
- 正检测转移：1,243；
- 每条路径都按原 episode 顺序持续积累状态，不是逐步重置；
- 被明确排除的 negative-observation steps：677；
- evaluator truth 访问次数：0；
- required checks：12；
- 每项通过数：1,243；
- failed transitions：0。

每个正转移均检查：

- normal router 先选 `P0_SAFE_DEFERRED`；
- 恰好生成并登记一张与原 transition hash 绑定的 pending debt；
- 到期 replay 选择真实 `P5_FULL_EAGER`；
- replay trace 消费原欠账证书并调用全部七个 primary operators；
- replay 后欠账结清且无 pending remainder；
- direct/replay primary PCHMP actor posterior 一致；
- direct/replay CIAV actor posterior 一致；
- direct/replay owner-habit location distribution 一致；
- direct/replay typed PUT_BACK location 一致；
- 两条路径消费相同 A1 action、outcome 与 detected location；
- 两条路径都执行 same-location fast verification（同位置快速验证）。

semantic comparison chain SHA-256：
`71e6d1387ef1f9ac8223fe1f76641686268f334658f38da245978b3a3314f071`。

## 3. 没有覆盖的边界

本结果没有覆盖，也不能外推为已经解决：

- negative-observation replay；负观测没有 `before/after` 转移，因此没有伪造 `PrototypeTransition`；
- detected location 与 transition-after 不同的 full feedback transition replay；
- concurrent multiple debts（并发多欠账）；
- debt 后长期 router utility、fallback 与跨系统持久原子性；
- SEARCH/PUT_BACK 科学信号重测、组合效用、长期污染、外部有效性或七算子消融贡献。

production adaptive readiness 中更宽的 `debt replay/eager-reference equivalence` blocker 因而只得到
一条重要正向子证据，不能整体删除。

## 4. 可复算性

工件：`benchmarks/structure_two/structure_two_p5_debt_replay_confirmation_v0_1.json`

- content SHA-256：`2451fad079b91fcb8b264bc391dc16e2a566dfd2feef8850fb7a7ba7e8186cb9`；
- file SHA-256：`bf2016f8d5e038f158aae590aa0401bc231ac46a3e005193865007acb841f8f6`；
- 第二次 full fresh recomputation 与工件逐字段一致；
- production assembly manifest SHA-256：
  `7459376cc4a2c0bb0e7f9f852bee9518cc0aa09de0c40b6c2da38268b979982c`。

与 direct-P5 post-hoc 工件相同，实际 production assembly 仍包含三份未提交的结构一依赖改动；干净
checkpoint 会因缺少 `RegimeStage` 定义在导入阶段失败。因此工件绑定实际运行时 source bytes，
但在结构一依赖由其所有者单独提交前，不能宣称 clean-checkout reproducibility。

复算命令：

```bash
PYTHONPATH=src .venv/bin/python \
  apps/evaluation_runner/run_structure_two_p5_debt_replay_confirmation.py \
  --verify benchmarks/structure_two/structure_two_p5_debt_replay_confirmation_v0_1.json \
  --fresh-verify
```

## 5. 下一决策点

`A1 + B1`、direct P5 上界定位和生产 replay 确认已经完成。若要重新判断 P5 行动信号，下一步不能
继续复用当前 test split；需要项目所有者在以下证据强度之间选择：

1. 冻结两个修复后，生成并密封一套从未打开的新 D0 development holdout，成本较低，但仍不是独立
   托管或外部有效性；
2. 直接准备 independent-custody confirmation split（独立托管确认集），证据更强，但需要先补齐
   账户、种子、签名密钥、trust-anchor enrollment 与结果回传制度。

在新的未见数据重现足够信号前，继续保留固定解析阈值为 baseline（基线），不启动
validation-only adaptive-router calibration。完整七算子与结构二全部能力范围保持不变。
