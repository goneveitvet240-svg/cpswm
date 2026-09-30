# Raw factor 修复验收建议

2026-10-01，电脑 A 辅助只读分析。本代理参与位置残差模型及 numeric diagnostic 实现，不是 B 独立验收。本文件是**修复要求与待执行矩阵，不是修复已实现或通过的报告**。

分析版本：`493e05720f066c5db7173502d03b245bf74b6d43`，工作树 `/private/tmp/cpswm-pc-a-soft-position-factor-20261001`。只读了冻结源码、R2 脚本和实际结果；没有重新执行攻击、修改源码或运行真实数据。修复作者后续改动须另绑定 SHA；本文件不评价尚未看到的最终实现。

## 已有证据与根因

R2 原件：`R2/test_complete_raw_factor.py`、`complete-raw-factor-result.json`、`legal-versus-forged.json`。

攻击保留原 dependency binding、真实 checkpoint/q 和原条件统计，将 base receipt 的 `observation_log_likelihood` 从 `-11.344546775287176` 改为 `-9.344546775287176`，同步更新 proof.base_candidates 与 materialize 后的完整 receipt。原生 stage 接受，workspace 改变，core marginal 可读：known 权重由 `0.09777783569501329` 变成 `0.44468660136150007`；ledger 未改变。故这不是只改名字或触发外层异常的攻击，而是实际目标后验错误。

`native_neural_production.verify_neural_evidence` 重算 q；`proposal_view` 不由 RGB-D 重算目标观测密度；`materialize` 保留 base 内的 LL。当前 `validate_neural_input_body` 核对 base.statistics 与 body.statistics、base.aggregate 与 body.aggregate 的一致性，但没有独立预期值。调用者同时修改两处仍自洽。implementation/model hash 证明声明依赖相同，不能证明提交的目标数值确由该依赖产生。

另有 `R2/context-future_cutoff.json`：使用未来 cutoff 生成完整真实网络包后，直接 core stage 被接受；旧 cutoff 已因不可见 raw 被拒绝，伪造 parent statistics 的现有 probe 也被拒绝。因此 cutoff 修复不能仅检查 capture<=caller cutoff。

R2 的跨进程脚本当前失败发生在重新 `scenario(...)` 后断言新 config/models 等于旧 config/models，尚未进入 `ContinuousEvidenceInput.resume`。不能将这个 harness 失败写成产品恢复失败，也不能算 fresh resume 已通过。应加载原保存 configuration/models/pins 构建依赖后再测试。

## 最小修复合同

### 1. 验证完整目标计算，而非新增自签摘要

对于配置了 raw position candidate model 的 Native 路径，消费者必须能从原 owner 输入、固定模型/实现及真实 prior 重算预期候选包，比较全部有后果内容：

- known 与 unknown 的 raw LL、完整 normalizer、aggregate unresolved 继承权重及其新 LL；
- prior、transition、constraints，候选/未知支持及 proposal/particle/cluster 身份；
- 六维 Gaussian Λ/η、位置之外的 alpha/a/b、全部 cluster/source lineage；
- 原 observation、局部 reference、R/H/bias、information_weight、模型外部 pin，以及该步骤是 active 还是 neutral；
- source、snapshot、semantic revision、父 batch/粒子与 ledger anchor。

只比较 base 与最终 receipt，或给现有 base 新加“verified/hash”字段，不能关闭本攻击。若只修 ControlledPositionProducer，报告明确适用范围；不能据此宣称所有任意 candidate model 的 raw likelihood 都有传感证据。

**proof 必需性属于冻结的 producer/profile 绑定。**在这个 profile 下，删除 raw proof、清空 catalogue、把字段设为 None、改成旧格式或“无 raw 验证”标志，都必须失败；不得降级到原来的 q-only 校验。该要求也适用于历史 body 与 SQLite 恢复，不能只在新调用时检查。相反，原先显式配置的其他 legacy/fixture profile 是否受支持，应由既有绑定和明确兼容合同决定，不能由提交者给本次包换标签决定。

### 2. Raw ownership 必须来自 owner

`NativeJointContext.visible_prefix` 在 neural proposal view 中被置空，原 raw 输入没有由当前 workspace verifier 重新取得。修复应通过 owner 的受控注册/重建接口，取得**当次实际 admitted 原件和当次 cutoff**；生产者不能凭完整自签 packet/config 向 catalogue 注册来源。

需要同时检查 envelope+payload+capture receipt+scope/action/scene、原 admission 时间、在原 cutoff 的可见性、配置 pin。仅 camera capture/arrival 早于一个任意未来 cutoff 不充分。把相同 bytes 复制进另一 runtime，也不自动获得原 owner 的 source/父链权限。

当前与历史验证都要到达这一约束：首次 core stage、workspace.state_payload/location_marginal、current_joint_decision_view、下一次更新、完整 replay 及 SQLite fresh resume。原件缺失时失败关闭，不能拿缓存的 world point/LL 或新的 metadata 补出成功。

### 3. 历史 prior 与状态化 producer

历史 input body 要沿真实父 cluster 图恢复当时 previous_batch/records，不用当前最新 workspace.batch，也不用字典插入顺序。重算使用更新前 prior；后验作 prior、重置 I6、漏掉 neutral 步或换父源都应拒绝。

重算不得消耗线上 producer 的 consumed_keys/RNG/call count；可用明确的纯验证器，或从 owner 保留且可验证的状态重建隔离实例。调用者提供的任意“pre-state”不能成为信任根。重试、读取、恢复、验证和失败回滚都不得增加观测信息。

### 4. 清洁重启与实现身份

原配置与模型内容/pin 必须足以在新 Python 进程重建验证依赖；不能依赖旧进程全局缓存/注册对象仍在。StateCodec 类型须通过运行时显式导入可用，checkpoint 内容不能请求动态导入或执行。模型/加载函数/验证器替换后，缓存命中也须拒绝。

复核 owner 的输入/验证依赖重绑定须在任何可消费读取前完成。producer checkpoint、input body、owner catalogue 与 core anchors 组成完整闭包；完整公有字段重签不能修改原接受锚或外部 pin。

## 最小回归矩阵

每个攻击先跑完整合法路径，攻击后检查 **Native weights/Λ/η/alpha/a/b/全部 journal/proof catalogue/producer state 未变、ledger 未变、合法恢复仍可发布**。仅出现 ValueError 或仅 ledger 未变不够。

| 组 | 合法先行与完整攻击 | 必须观察的后果 |
| --- | --- | --- |
| A 原始阻塞 | 原 R2 LL+2 脚本另存新输出重跑，原 binding、真实 q 不变 | 修复前接受证据保留；修复后 stage 拒绝，无 Native 变更，合法原包仍成功 |
| B 其余目标项 | 分别改 unknown LL、aggregate +2、neutral 步非零 LL、transition/constraint；同步改 base/最终包/所有公开摘要 | 每项拒绝；aggregate 不能单独绕过；无因子/后续 neutral 合法包仍保留原权重 |
| C 条件统计 | 修改合法 PD 的 Λ 或 η；另改 alpha/a/b 或 orientation 块；同步更新 statistic_state_ref、完整候选、真实重新执行 q 与 materialize | 不因 shape/类型不合法才失败；应因与 raw 模型重算不符拒绝；证明不允许凭真实 q 注入虚假位置或其他 RB 块信息 |
| D 原件与时间 | 深度/相机完整改写并重签 packet、换 owner/scope/action、缺 raw；真实 q 下 future cutoff、另一个合法 cutoff、晚 admission 提前可见 | 首次与历史消费者拒绝，保持原始 owner chronology；合法原 cutoff 可恢复 |
| E 模型/来源 | 替换另一合法 bias/R 或 affinity checkpoint，连同内层/外层摘要全部重签；原外部 pin/owner profile 不变 | 两模型分开攻击均拒绝；当前绑定不接受新自签依赖；错误 source/reference/domain 不能混入 |
| F 历史 body | 至少 selected_index=1 并有后续 neutral 步，重签非当前 input body 的 LL/统计/aggregate/截止；重建后代公开指纹和 batch | workspace 历史验证与 owner current read 均拒绝；不能仅靠最新 proof 检查掩盖旧错误 |
| G prior 图 | 真父链合法；换同 shape 的另一合法父状态、用当前最新 prior/后验当 prior、删/重排父项 | 换父与错误更新次序拒绝；仅 dict 顺序倒置必须保持合法；真实继承、q 与积分抵消不变 |
| H fresh/replay | 原 configuration/models/pins 新进程构建；publish→neutral→SQLite→新进程→重复→下一步；retract→full replay→再次 fresh | 精确 view/统计/权重/消费状态一致；重复零增量；撤回等于无因子，旧 raw 保留但不重挂其他 semantic 来源 |
| I atomic/compat | 验证器在注册前/后、计算中抛异常；删除 proof/换旧格式/降级 profile、缺失或替换验证器及 loaded helper；旧 projection 重复源攻击、旧 classification/clarification 与 owned visual 正路径 | proof catalogue 与 producer/core 一同回滚；proof 必需性不降级；原接受锚保留；投影防重不放松；旧明确支持的合法对照不误拒绝 |

历史攻击分两层记录：workspace 自身只校验内部重建闭包时的结果，以及保留原 core/owner acceptance anchors 后公开消费的结果。若第一层因缺乏独立 raw 重算可接受而第二层靠旧指纹拒绝，报告应明确边界，不能写成历史 raw 数学已复核。强完整攻击不修改实际可信 owner 接受锚或外部 pins；若任意内存/数据库所有信任根都允许被一起覆盖，那已越出此本机工程绑定模型。

## 修复后建议执行的测试目标

第一层：新增 repair tests，加 `test_native_position_production.py`、`test_native_neural_production.py`、`test_position_observation_model.py`。须保留原 R2 失败原件，新的 probe/log 使用新目录，不能覆盖 R2 证据。完整统计伪造如改变 q 的输入，必须真正重算 q，不能以 stale q 导致的拒绝冒充 raw 验证通过。

第二层：`test_native_neural_recovery.py`、`test_native_joint_full_replay.py`、`test_native_joint_producer_binding.py`、`test_owned_visual_neural.py`、`test_owned_rgbd_support.py`，以及 `test_structure_two_w3_native_posterior_projection.py`、`test_structure_two_w3_round6_prepared_boundary.py`。这些覆盖重启、回放 generation、loaded implementation、owner 来源、投影防重、原子 rollback 和已有极值算术边界。

第三层：`test_run_soft_position_development.py`、`test_position_factor_diagnostic.py`、`test_soft_surface_position.py`、`test_soft_position_dataset.py` 与 root 冻结的完整定向集合，确认 consumer 修复没有改变既定 96 帧协议/四模型/VOID 与失败保留。数量以实际收集结果为准，不预报“已通过”数。

推荐环境：`OPENBLAS_NUM_THREADS=1 PYTHONPATH=src:tests:tools`，Python `/private/tmp/cpswm-pc-a-camera-checkpoint-fixture-20260930/.venv/bin/python`。每次命令保留 argv、退出码、日志和绑定 SHA；fresh worker 用原持久化配置，不重新随机生成等价 fixture。

修复重新冻结后，旧 493e057 的 R1 不能覆盖新代码；须重新顺序两审。完成此前，真实 96 帧 run 继续暂停。本修复仅补当前 raw-factor 消费的可信计算闭包；owner 同 semantic 多 capture 的新事务/replay 调度仍属于下一轮，不偷偷并入本轮实现或把真实邻帧当独立样本。
