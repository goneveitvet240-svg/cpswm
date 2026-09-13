# W3 PC-B 七算子—主干真实默认路径工程因果诊断

## 结论

本轮在 Windows 当前真实默认路径上确认：七个算子都被实际执行，已运行连接存在可核验的内容交接和数值后果；但**默认完整联合主干仍未实现，不能签收完整能力，更不是科学验收**。

明确保留的三个非绿色事实：

1. 连续基准 27 个状态步的 `default_joint_particles` 全为 `0`。
2. 普通路径 Dirichlet `Δα` 和 RLS `Δa/Δb` 非零，但 information block 的 `ΔΛ/Δξ` 全为 `0`。
3. CIAV 的实际输入键为 `actions / belief / ...`；`belief` 是 `StructureTwoCauseBelief`，没有完整粒子后验。

能力缺口探针因此按设计返回 **exit 2**。这个退出码表示缺失被真实检出，不是测试通过。类似物理实例、未知地点支持，以及“同一运行覆盖全部要求场景”也仍未建立。

## 被测身份、环境与时间

- 完整证据 HEAD：`23506024213d517ba4bab65d4318663163b00913`
- 最后修改生产源码的提交：`17220e6e22de81508a2e4e34dce81b8dccc9e44f`
- 两者之间 `git diff --name-only 17220e6..2350602 -- src`：空
- 全部 `src/**/*.py` 聚合 SHA-256（前/后）：`1be6317e9a151acd149d6253a97a6d1fae969c29f523bc144be213ba3491dfb5` / 相同
- 并行 W1/W2 审计随后把工作树 HEAD 推进到 `420e52baa50a8d8ca67c7e5b5ef7724c9ea4cfa5`；`2350602..420e52b -- src` 仍为空。因此本结果保留原被测完整 HEAD，不把后来的文档提交静默换成新测试身份。
- 解释器：CPython 3.13.5，`F:\庞惟\codex\cpswm-w3-five-boundaries-fix-20260912\.venv\Scripts\python.exe`
- pytest：9.1.1；平台：Windows 11 `10.0.22631`
- 主驱动：2026-09-12 23:02:49+08:00 至 23:33:03+08:00，1814.12 秒；补充数值采集 42.55 秒
- 旧 R7 连续脚本在 Windows 以系统默认编码写原始 JSON；原始字节未改并按 SHA-256 保存为 gzip。新命令、矩阵和报告为 UTF-8。

## 七算子真实输入、实现与消费链

| 算子 | 实际输入与实现 | 实际输出与下游消费 | 状态/账本/动作/反馈 |
|---|---|---|---|
| OPCEU | `ObservationOpportunityRecord` → `propensity_correction.py:262`，SHA `f6299a52ceccdd93fbceb4b36d544449e2ae1bff661cf8d3c9dfe53db578ad31` | `raw_propensity/applied_weight/clipped` → 事件统计权重 | RGRC 的 `Δα`/RLS、唯一 Hybrid ledger、动作读出 |
| ORRER/CHEH | before/after、actor prior、handoff/unresolved → `engine.py:1144`，SHA `976b5998fcb15e3730201c442805fdaed9869cfaf125f399cd74d459733aa5ae` | 可逆事件历史 → PCHMP；基准 27/27 次内容摘要匹配 | 闭包后的验证 detection 也重新进入 ORRER |
| PCHMP | event history、evidence、independence certificates → `hypothesis_message_passing.py:869`，SHA `3f8a99fc3134e44950a4c60ee40bca620e88c9c7fd2853dd6b020385241368f3` | actor posterior 与原生 posterior source → primary 统计/读出 | 显式投影存在，但默认 workspace 不产生联合粒子 |
| CF-BOCPD | `CauseSignalFrame` → `joint_cause_bocpd.py:406`，SHA `f35bf213f8b533a5be9878b27ac4537af9bf0467b8361aedec2349d2485da528` | cause snapshot → cause router，基准 53/53 次内容匹配 | CCRR 消费；CIAV 后续仅读原因信念，不读完整粒子 |
| CCRR | snapshot、actor/object/context、identity probability → `context_conditioned_regime.py:731`，SHA `0c95612f1dc58279eb93ef16976a88411f00c31f4258d7b0cdf5e04ecffbfc5e` | stay/create/reactivate/unresolved → cause router，5/5 次内容匹配 | 决定隔离/晋升并控制 RGRC 写入 |
| RGRC | `HybridStatisticDelta` + promotion → `hybrid_statistics.py:1036`，SHA `47cfe3b84178e19a308c58e9261b05f4462cc6f922b69e254c0844e140a71310` | 原子更新唯一 `HybridStatisticLedger` | `Δα`、`Δa/Δb` 非零；`ΔΛ/Δξ` 为零；动作从该账本读出，纠正/撤回仍回到同一账本 |
| CIAV | actions、原因 belief、效用、隐私预算 → `active_verification.py:438`，SHA `c15262bf103d0fbc56181075ffad6583bf9f2b255c63505f2007598e9ef92dbd` | plan → 真实执行器 1/1 → detection → ORRER/PCHMP 闭包 1/1 | 反馈修订 1 次并影响后续动作；完整粒子消费者缺失 |

进程内 ID 只用于定位，不能单独证明语义连接。基准跟踪中 OPCEU、ORRER、PCHMP、RGRC、CIAV 各见 1 个进程内实例；CF-BOCPD 与 CCRR 在迟到纠正/状态恢复边界前后见 2 个实例。实例替换、同类外来实例和公共入口 shadowing 的既有回归均通过；完整 phase→ID 明细在机器矩阵中。

## 连续历史、合法对照与公开干预

基准真实调用：OPCEU/ORRER/PCHMP/RGRC 各 27 次，CF-BOCPD/cause-router 各 53 次，CCRR 5 次，CIAV/执行/反馈修订各 1 次。CCRR 序列为 `unresolved, create, unresolved, create, reactivate`；最终 committed 为 27。

| 路径 | 最大动作分布 TV | 最终 TV | 最大 `|Δα|` | 最终 committed | top-1 变化步/最终 |
|---|---:|---:|---:|---:|---|
| 基准 | 0 | 0 | 0 | 27 | 0 / 否 |
| 合法证据重排对照 | 0 | 0 | 0 | 27 | 0 / 否 |
| OPCEU：可见概率 0.35 | 0.579410 | 0.508692 | 11.384222 | 4 | 3 / 否 |
| ORRER：未决概率 0.4 | 0.008034 | 0.004649 | 1.291940 | 27 | 0 / 否 |
| PCHMP：移除机制证据 | 0.003712 | 0.001559 | 0.044844 | 27 | 0 / 否 |
| 身份概率 0.95 → CCRR | 0.187912 | 0.018564 | 2.529827 | 23 | 3 / 否 |
| CIAV：同位置结果 | 0.022239 | 0.022239 | 2.226083 | 24 | 0 / 否 |
| 开放世界未知人物事件 | 0.205099 | 0.112034 | 6.324568 | 23 | 3 / 是 |

分布改变与执行/top-1 后果分开记录；例如 OPCEU 最终 TV 为 0.508692，但最终 top-1 回到基准，只在 3 个中间步改变。ORRER、PCHMP 和连续 CIAV 干预均改变分布，却没有改变该连续历史的 top-1。

补充逐算子数值对照：

- CF-BOCPD 合法平稳 6 帧：change probability `0.000521121`、habit probability `0.319371728`；公开 habit=0.95 输入后分别为 `0.001086797`、`0.694272081`，增量 `0.000565676` / `0.374900353`。这是实际生产类的隔离输入干预；动作后果未被该隔离运行证明。
- CCRR 同一 18 日生产历史，confirmation window 2/3：committed `16/15`、quarantined `0/1`、动作 TV `0.084212761`、最大 Hybrid α 差 `1.264913556`，top-1 不变。重复 window=3 的合法对照要求同分类。
- RGRC 同一公开 transition，负观测合法无闭包对照与异位置反馈：ledger entries `0→2`、committed `0→1`、目标 α `0→0.961169103`、动作 TV `0.75`；均匀分布的确定性 tie-break 已选同一 UUID，因此 top-1 未变。
- CIAV 在 4 步预热后：owner likelihood `0.95` 相对负观测对照 TV `0`、top-1 不变；`0.05` 时 TV `0.7` 且 top-1 改变。两条同位置路径都产生真实 fast-verification receipt。

## 场景覆盖与准确限制

| 场景 | 状态 | 实际证据/限制 |
|---|---|---|
| 稳定习惯 | 已执行 | 连续历史稳定前缀与 CF 合法空对照 |
| 习惯变化/恢复 | 已执行 | 连续历史真实 create/reactivate |
| 多人交接 | 部分执行 | owner/guest/unknown prior、ORRER 双角色 unknown 枚举及错误剪枝后复活；未声称连续历史每个隐藏真值都是交接 |
| 相似物理实例 | **默认路径缺失** | Direction-Three oracle 合同正例通过，但当前默认 probe 只拥有一个 `object_instance_id`；该正例不是默认主干证据 |
| 未知人物 | 已执行 | open-world 连续运行和支持保留正例 |
| 未知地点 | **默认动作支持缺失** | 动作支持只有已登记 UUID 地点；默认联合路径没有消费显式 unknown-location 候选 |
| 负观测 | 已执行但有消费者缺口 | 七个 primary receipts，正确无闭包/无 commit；CIAV actor posterior 与 primary 不同但被丢弃 |
| 迟到纠正 | 已执行 | 连续反馈修订，旧 revision 移除、新 revision 生效，随后动作继续 |
| 延期/债务恢复 | 已执行 | P0 延期、过期重放、exactly-once 拒绝、direct/replay 语义一致 |
| 取消/恢复 | 进程内已执行 | 公共取消、分阶段中断、完整回滚、可重试；不证明跨进程掉电恢复 |
| 同一 runtime 覆盖全部上述场景 | **未建立** | 连续运行覆盖稳定/变化/开放世界/迟到纠正；负观测、债务、取消、相似实例仍是分开的场景运行 |

## 测试与非绿色探针

| 组 | passed | failed/error/skipped | 时间 |
|---|---:|---:|---:|
| 七算子合法对照与公开干预因果矩阵 | 20 | 0/0/0 | 266.78s |
| 默认历史、交接、未知、修订、延期、实例保护 | 14 | 0/0/0 | 84.40s |
| 负观测四层及误编码保护 | 12 | 0/0/0 | 24.45s |
| 延期取消、故障回滚、纠正/撤回后续 | 27 | 0/0/0 | 306.45s |
| 相似实例参考合同（非默认能力） | 1 | 0/0/0 | 1.85s |
| 合计 | **74** | **0/0/0** | 683.93s |

另：`capability_gap_probe.py` exit `2`，检出 3/3 已知缺口。主驱动把 2 登记为该命令的预期非绿色结果，但没有把它计入 74 个 passed。

所有失败尝试也保留：数值脚本首次根目录计算错误 exit 1；汇总命令首次路径拼写错误 exit 1；汇总器首次按 `delta_A` 而非真实序列化字段 `delta_a` 读取 exit 1；最终验证器先把 pytest 生成的合法“无末尾换行”JUnit 当成 authored-text 规则违反，又把并行阶段二收集器的 LF→CRLF 警告当成 `git diff --check` 失败，各 exit 1。最终规则以真实 exit 0 为准并原样保留 EOL stderr。只修了审计脚本/命令及验证规则，没有修改生产源码，也没有覆盖失败记录。

## 交给 PC-A 的具体接线清单

1. **默认候选生产者**：从公开观测生产完整 H/R/I/C/Z/r/V 候选、合法全量 log-q 与父子谱系，进入 `NativeParticleWorkspace`；当前只有显式 prepared 候选和 PCHMP source。
2. **三个 RB blocks**：保留现有同一 Hybrid ledger；为真实证据提供粒子条件 information `ΔΛ/Δξ` 生产者。不得用目前非零的 Dirichlet/RLS 代替第三块。
3. **完整后验消费者**：把默认完整粒子后验接入 CIAV/动作读出并校准；当前 `StructureTwoCauseBelief` 不能冒充完整后验。
4. **默认场景支持**：提供相似物理实例、显式未知地点和同一连续 runtime 的场景生产者/消费者；分别检查质量保留、动作后果与修订。
5. **完整反馈后缀**：在真实默认粒子存在后，验证反馈修订、取消和债务重放会修订完整粒子后缀，而不仅是现有顺序路径/账本。

仍需用户或冻结程序决定的不是本轮工程权限：全轴神经候选最终选择、重采样规则、原因/实例观测模型、information 测量模型、联合读出校准及合法世界/未知地点扩展契约。本轮没有替用户选择，也没有修改科学先验、阈值、预算或模型路线。

## 证据入口

- `connection_and_scenario_matrix.json`：主机器矩阵，含逐算子 I/O、实例、内容交接、RB block、数值与场景状态。
- `environment_and_source_binding.json`：完整 HEAD、生产提交、解释器、平台及运行前后所有源码摘要。
- `commands.json` / `additional_commands.json`：完整命令、退出码、耗时、stdout/stderr 与失败保留。
- `operator_metrics.json`：CF/CCRR/RGRC/CIAV 精确数值对照。
- `capability_gaps.json`：三项默认能力缺失与 exit 2 语义。
- `pytest_*.xml` / `pytest_*.stdout.log`：五组 JUnit 和原始日志。
- `continuous_current_*.json.gz`：八条当前源码完整调用/状态 raw trace。

本报告只能签署“当前默认顺序路径的工程因果诊断已执行”。它不签署默认完整联合能力、公平比较、统一验收、真实机器人成功或科学收益。
