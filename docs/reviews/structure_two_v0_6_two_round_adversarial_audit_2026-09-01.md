# Structure Two v0.6 两轮对抗对立审核（2026-09-01）

## 结论（独立复审后更正）

审核结论：不通过。

Gate B v0.6 和外部方法忠实度门的 fail-closed 协议草案及基础校验已实现，现有目标测试通过；但协议尚未冻结或执行，外部方法忠实度尚未通过，并且独立对抗审核发现规范绑定、证据可验证性和组合授权漏洞，协议级修复尚未闭环。

此前记录的 Round 1 `12 passed` 与 Round 2 `12 passed` 只覆盖当时已有攻击测试，不能支持“门控修复完成”的结论。当前仍为 `v0_6_gate_b_scored=false`、`v0_6_gate_b_passed=false`、`external_fidelity_gate_passed=false`，v0.5 失败结果保持不变。

## Round 1：证据真实性与运行完整性

运行命令：

```bash
.venv/bin/pytest -q \
  tests/test_structure_two_signed_gate_b_v0_6.py \
  tests/test_structure_two_external_adapter_fidelity_v0_2.py
```

结果：`12 passed`。

攻击面与防线：

1. 修改 mechanism event（机制事件）后重算普通内容哈希：Ed25519 签名验证拒绝。
2. 候选方生成同名 key 自签冒充 custodian/reviewer（托管方/审查者）：预注册 public-key hash（公钥哈希）拒绝。
3. 不同 producer run（生产运行）的臂混合：run identity（运行身份）一致性检查拒绝。
4. 重放 mechanism invocation receipt（机制调用回执）：唯一 invocation ID 检查拒绝。
5. 仅给出 64 位伪哈希而无独立签名：不能形成 independent review（独立审核）。
6. 审核后修改 adaptation contract（适配契约）：签名不再匹配。
7. 只复现部分 native components（原生组件）：exact component set（精确组件集合）检查拒绝。
8. native reproduction（原生复现）通过但 adaptation parity（适配等价性）缺失：跨域效果授权仍为 false。

## Round 2：科学语义与范围对立审核

运行命令：

```bash
.venv/bin/pytest -q \
  tests/test_structure_two_stratified_gate_b_v0_6.py \
  tests/test_structure_two_adapter_input_coverage_v0_6.py \
  tests/test_structure_two_gate_b_protocol_v0_6.py \
  tests/test_structure_two_v0_6_readiness.py
```

结果：`12 passed`。

攻击面与防线：

1. 因无关、跨域臂输出相同而让全对全 Gate B 失败：改为预注册 same-question pair（同问题比较对），不再把无科学意义的跨域相等当失败。
2. 只让 wrapper 输出不同动作、没有核心机制状态转移：结构化 mechanism receipt 与激活阈值拒绝。
3. 删除困难臂、比较对或核心机制事件：canonical protocol（规范协议）校验拒绝。
4. 结果出来后降低 action disagreement（动作分歧）或 mechanism activation（机制激活）阈值：精确规范阈值校验拒绝。
5. 外部方法输入缺失仍生成 trace（轨迹）：adapter-input coverage preflight（适配输入覆盖预检）阻断。
6. 用 native-domain（原生领域）复现替代 cross-domain adaptation（跨域适配）证据：三阶段忠实度门拒绝。
7. Gate B 的签名轨迹通过后直接宣称外部方法有效：独立 efficacy authorization（效果授权）仍固定为 false。
8. 借修复 v0.6 覆盖 v0.5 失败：readiness 只读取并验证旧结果内容哈希，保持历史失败。

## 外部方法证据状态

六个方法的 source identity（来源身份）已登记并绑定论文/仓库版本；这只完成来源定位，不等于实现忠实度：

| Arm | 来源检查 | 官方实现 | 当前忠实度状态 |
|---|---|---|---|
| corrected_amg | full text checked | v0.2 不强制官方代码 | blocked |
| o_star_matched | full text checked | v0.2 不强制官方代码 | blocked |
| active_dreaming_matched | full text + official repository checked | commit `9c05baf41673d10e92c076ba7db18b1b6553a60d` | blocked |
| auto_dreamer_matched | full text checked | 检查文本中未识别到发布代码 | blocked |
| trustmem_matched | full text checked | 检查文本中未识别到发布代码/权重 | blocked |
| brainctl_matched | whitepaper + official repository checked | commit `c6348087dd07e54583f762e07bf960ac982019e6` | blocked |

必须补齐每个外部 arm 的：native protocol recheck（原生协议复核）、component parity receipt（组件等价性回执）、adaptation contract（适配契约）、adaptation parity receipt（适配等价性回执）与独立 reviewer 签名，之后才能冻结并交给外部 custodian 运行。

## 审核边界

本审核确认的是 fail-closed 性、不可静默缩小十臂范围、以及 native/adaptation/efficacy 三类主张不混淆。它不证明任何外部方法的经验效果，也不把缺少真实数据、实现、算力或独立审查者的问题包装成通过。

## 下一阶段实现后的复审

新增实现：六臂 typed adaptation input contract、六臂 executable reference core、reference-core transition 到 Gate B mechanism receipt 的内容绑定，以及 Active Dreaming/brainctl pinned-official-code component parity。

Round 1 重新运行：

```bash
.venv/bin/pytest -q \
  tests/test_structure_two_signed_gate_b_v0_6.py \
  tests/test_structure_two_external_adapter_fidelity_v0_2.py \
  tests/test_structure_two_external_reference_cores_v0_6.py
```

结果：`22 passed`。新增攻击覆盖不完整 AMG ordered-role support、O-STaR 缺 opportunistic observation、Active Dreaming 未执行 scenario 即提交、Auto-Dreamer replacement 未绑定 provenance、TRUSTMEM 缺 WRITE/REVISE/PRUNE、brainctl embedding 维度和 source-trust class 不一致。

Round 2 重新运行：`12 passed`。readiness 明确记录六个 component core，但固定 `external_reference_cores_are_native_reproductions=false`；当时对 Active Dreaming/brainctl 的 `component_parity_passed=true` 表述后来被独立反例推翻，见下节更正。

## 独立审核不通过后的漏洞回归（第三版草案）

独立审核发现此前测试集不足，结论改为“不通过”。本轮仅声称五类已知反例已被固化并由当前代码拒绝，不声称协议已经冻结、执行或完成外部忠实度闭环。

整改内容：

1. 外部 fidelity 与 input coverage 默认要求精确的规范六臂；单独 fidelity gate 永远返回 `external_method_efficacy_comparison_allowed=false`。新增 combined authorization gate，从原始输入、artifact paths、reviewer evidence 和十臂 signed traces 重新计算所有前置门。
2. `comparison_id`、`right_arm`、`domain`、threshold 和 fidelity protocol ID 使用精确规范映射；交换目标、改写 domain 或替换协议号均失败。
3. 忠实度证据必须解析真实文件/目录并重算 SHA-256；component/native/adaptation receipt 必须指向存在的 execution log，包含非空命令、`exit_code=0`、实现 bundle hash 和成功语义。每份执行 receipt 还必须由与 reviewer 不同的预注册 executor key 签名；可信 reviewer 签名覆盖虚构哈希时仍失败。
4. mechanism receipt 必须匹配规范 event-to-component 映射、连续 execution-state chain、连续 sequence index、同 invocation 的 execution-log entry，以及可读取 core-transition payload 的哈希。
5. source identification 改为逐臂验证方法名、URL、primary-source hash、evidence level 及所需官方代码 URL/commit。当前 Active Dreaming 与 brainctl 缺 primary-source content hash，因此整体仍为 false。

修复后 Round 1：`21 passed`；Round 2：`29 passed`。Ruff 与 strict mypy 通过。当前状态仍为 `DEVELOPMENT_NOT_FROZEN`、`v0_6_gate_b_scored=false`、`external_fidelity_gate_passed=false`，所以本轮结果是“已知绕过的代码级回归关闭”，不是“协议级修复完成”。

## Component-core 对抗审核不通过后的整改（第四版草案）

后续独立审核再次判定“不通过”，并给出 brainctl 负相似度、Active Dreaming 虚构执行、Auto-Dreamer ghost provenance（幽灵来源）、TRUSTMEM 自报 verifier 分数及旧回归不同步五类反例。本轮整改如下：

1. brainctl novelty（新颖度）与固定官方实现一样，将 `max_similarity` 下限固定为 `0.0`；反向邻居不再把 novelty 推高到 `1.0` 以上。
2. 撤回整体 `component_parity_passed`，改为 `selected_fixture_parity_passed`；报告固定输出 `component_parity_passed=false`，并加入负相似度等四个差分 fixture（样例）。
3. Active Dreaming 不再产生 `counterfactual_scenario_executed` 事件；字段、事件和输出均明确它只是根据 `externally_asserted_execution_success`（外部声明执行成功）进行 commit gating，reference core 本身未执行 payload。
4. Auto-Dreamer 输入契约验证 frozen memory bank（冻结记忆库）ID 唯一性、trajectory source（轨迹来源）存在性、replacement ID 新颖性以及 `supersedes` 引用完整性。
5. TRUSTMEM 删除调用者提供的 coverage/preservation/faithfulness 分数，改为从内容绑定的前后状态、required evidence（必需证据）、protected memory（受保护记忆）和 evidence reference（证据引用）直接计算三个 verifier，并拒绝 no-op（无变化）状态转移。

边界保持不变：以上只关闭本轮已知 reference-core 反例。Active Dreaming 的真实 scenario execution、六臂 native reproduction、完整输入域 component parity、adaptation parity、外部 fidelity 和 Gate B 正式执行仍未完成，因此仍不得冻结或授权 efficacy comparison。

### 第四版草案整改后的两轮对抗对立审核

Round 1（组件语义、引用完整性与官方差分 fixture）：重新从 Active Dreaming `9c05baf...` 和 brainctl `c634808...` 两个干净固定 checkout 生成 artifact，得到 `selected_fixture_parity_passed=true`、`component_parity_passed=false`、`native_protocol_reproduction_passed=false`、`adaptation_parity_passed=false`；reference-core 攻击回归为 `13 passed`。

Round 2（规范六臂、签名证据、Gate B 组合授权与主张升级）：运行 fidelity、efficacy authorization、input coverage、signed Gate B、规范映射、分层门及 readiness 测试，结果 `40 passed`；额外 machine assertion（机器断言）确认 selected fixture 不能升级为 component/native/adaptation parity，且 `external_fidelity_gate_passed=false`、`v0_6_gate_b_scored=false`、`v0_6_gate_b_passed=false`、`ready_to_freeze=false`。

静态检查：本轮涉及文件 Ruff 通过，五个相关 source file 的 mypy strict 通过。完整仓库回归没有全绿，最终有 3 个与本轮目标文件无关的证据冻结/内容清单失败：P0 checkpoint content manifest 漂移、旧 v0.1 corrected-instrument preservation hash 失配、冻结 v0.5 source bundle 的登记文件数 `245` 与当前 `255` 不一致。本轮没有重写这些历史冻结证据来掩盖失败。

本阶段结论仍为“不通过”：本轮已知反例的代码级回归已关闭，但完整仓库回归未全绿，真实外部执行与完整忠实度证据链也未闭环。
