# 同语义来源的新观测更新：最小实现设计

2026-10-01。只读设计，基于冻结源码 `82c7a81fba0c3af3688978ce222b1b94e4cc5bd9`，工作树 `/private/tmp/cpswm-pc-a-archive-native-bridge-20261001`。本次没有修改 `src/tests/tools`，没有运行模型、Unity、Native 实验或测试；只读取了当前源码与上一轮 `NEXT_RAW_UPDATE_DESIGN.md`。作者参与当前 archive bridge 及前轮 controlled producer 实现，本文件不是独立 R1/R2，也不意味着当前桥接已通过双审或真实运行。

## 建议与工作量判断

下一主项应让**已经发布的同一 semantic source，在收到随后真实 owner-issued capture 后，产生新的 Native 观测簇和真实权重/条件统计变化**。不能再用新的 synthetic semantic record 驱动旧入口来替代这件事。

删除 `produce_joint_posterior` 的早退判断不是完整修复。当前协议在固定 packet/key、capture 时间、独立 raw 复算、replay schedule 和相机反馈五处都假设一次语义来源只对应一次该 producer 更新。完整 owner 更新、逐簇撤回及 fresh SQLite 恢复需要同时闭合这些边界；**不能可靠承诺 30 分钟内实现并完成有意义验收**，更不包括冻结后双审。

最小完整开发切片建议先做：

1. 在原语义来源 S 发布一个 neutral Native prior；P5、语义账本和 S 的 UUID/record/time 此后保持不变。
2. 用 owner 正常发出的一个 command，接收 capture A；从 A 的原 RGB-D/自位姿重推公开读出，再真正更新 Native 权重和 Λ/η。A 在 S 之后，时间检查按 command/delivery，而不是修改 S 的 detection_time。
3. A 重复消费不增量；之后出现的不同 capture B 原样保留，明确报告此开发 profile 尚不支持第二次测量，而不是再乘一次 likelihood、偷换 A 或假称完成连续更新。
4. 在另一个保留的 neutral semantic source S0 存在的受控 fixture 中撤回 S，逐簇排除 S 与 A，重放到 no-factor 对照；fresh SQLite 子进程恢复并重复 A 仍无增量。

这是工程切片建议，不是缩小统一框架或新增正式科学规则。它能先验证“旧语义不重跑而新图像影响 target density”，并避免在本切片中自动选定真实邻帧的独立性模型。之后允许多个测量，必须增加显式相关性/状态时序协议。主代理已明确同意把该四项作为下一完整工程轮的范围；当前 R2 尚未通过，本文件不启动实现。

重新检查可复用 fixture 后，**不建议为了 30 分钟预算单独交付 replay-only 改造**：`JointFixture.produce` 的 known 分支确实消费 posterior projection，不能简单删该语义来制造同 source 两批的合法路径；当前 canonical position profile 又明确只允许一个固定 source/packet。仅改 schedule 后，虽然能用既有单批来源检验兼容性，尚不能用现有合法 owner 正路径证明新的同 source raw update。新 raw profile 与接受入口本来就是这条正路径的必要部分。若剩余窗口不足以闭合整个切片，应交付当前桥接及本设计，下一完整轮继续，而不是造一个未验证的新分支。

## 当前断点与可复用入口

以下行号以本冻结 SHA 为准。

| 当前位置 | 现有行为 | 下一项必要变化 |
| --- | --- | --- |
| `structure_two_continuous_input.py:396` `advance` | `infer=None` 和重复语义分支已经在真实 cutoff 登记 owner raw context；不会伪造新语义 | 保留；不为观测消费重新执行 P5 |
| 同文件 `:833` `_admit_current_raw_context` | 绑定当前真实 source、batch、prefix、cutoff、原 receipt log-weight evidence | 为明确 observation update 构造带 owner 观测描述的另一 context；不让 proof 选择描述 |
| 同文件 `:881` `produce_joint_posterior`，早退 `:912–918` | snapshot/source 相同就返回 | 保留现语义 publication 幂等；新增显式 owner 观测消费方法，不清空 `_joint_published_*` |
| 同文件 `:1194` `prepare_observation`、`:1247` `execute_observation`、`:1290` `_accept_observation` | issued capability、持久 READY/UNCERTAIN、实际原件 admission 已存在 | 新 profile 在签发时另外锚定 source 与 Native parent；成功 receipt 后可消费，不再执行相机 |
| `controlled_position_producer.py:245/275/356/372` | 固定 measurement key；capture 不晚于 semantic detection；祖先最多一次；cluster 由 source+固定 binding 决定 | 保留旧类和旧协议；新增确切注册的 owner-observation profile，不通过继承/duck typing 绕过保护 |
| `native_raw_verification.py:28/64/125` `profile_for/reconstruct/verify_raw_base` | canonical 单帧 profile；从拥有者 context 和真实祖先完整重算 base | 同时支持新 profile，并从拥有者接受的更新计划重算；不信 producer checkpoint 的 consumed flag |
| `native_neural_production.py:424` | consumer 重建 `NativeJointContext` 后调用完整 raw base verifier | 从 owner catalogue 取得新 typed observation 描述；不能照抄 proof 自报字段 |
| `native_joint_replay.py:110/142` `consumed_schedule/prepare_generation` | 顺父 cluster 回溯，却输出 semantic revision，并拒绝/合并重复 revision | 保留 cluster/logical update 顺序；source catalogue 仍唯一，update schedule 不按 revision 去重 |
| `prototype_spine.py:2960` `rebuild_prepared_particle_history` | 逐 `generation.sources` 调用 producer | 改为逐受信 update 调用；source 只注册一次，semantic 与 raw 更新分别消费 |
| `continuous_camera_collection.py:66` `collect_posterior_step` | 规划前 publication；delivery 后仅 `advance` | 仅新 opt-in profile 在成功 delivery/advance 后消费对应 action；旧默认路径不变 |

## 新身份与 owner 事务

建议新增严格 dataclass `NativeObservationUpdate`（名称可调整），加入 `NativeJointContext` 的可选字段；`None` 不追加 hash 成分，以保留旧 context 身份。它不是一个任意 dict 的 `verified=True`。

至少区分以下三件事：

- **语义锚**：原 revision、source body、object/scope，保持原件不动。
- **逻辑观测身份**：原 action ID、完整 command/delivery 摘要、原 RGB-D/pose IDs 与 receipt/bytes、公开 readout policy/model binding。跨 replay generation 仍指向同一次接受的 capture。
- **运行时 evidence cluster**：由当前 generation、逻辑观测身份、真实父 input body 派生。新 generation 可以有新 cluster，不能据此重新获得消费原图像的权限。

签发 command 时把实际 source、parent batch/input-body、native origin 和 decision_time 纳入 owner 目录；`_observation_native_origins` 当前只是 Native view hash，不能独自替代完整 source/parent 记录。消费入口如 `consume_owned_position_observation(action_id)` **只收 action ID**：从 `_observation_commands/_observation_status/_raw`、原 source anchors 和实际父 body 重建全部值。调用者不能提交 XYZ、一个新 receipt、任意历史 cutoff 或替换模型。

成功 delivery 必须匹配原 capability、原 native origin 和仍有效语义锚；时间需逐项满足 `decision <= capture <= arrival <= received <= cutoff`，camera/self-pose 与原帧配对。等待期间若语义/parent 已变化，先明确拒绝/隔离，不把旧 command 自动移植到新来源。普通直接 `admit` 和 archive 的 `fixed-offline-factor-view@1` 都不能凭内容看似完整冒充 owner-issued command。

消费事务在 `stream._lock` 和 `core._execution_lock` 下执行：

1. 验证原 profile、原目录、当前 ancestry；重复逻辑身份返回原接受结果。相同 raw identity 换 action/seed 别名不能再次消费。单纯像素字节相等不能断定不同真实 capture 是重复，应保留原 receipt/时间身份与像素重复信息，不能任意删样本。
2. 以真实父 `NativePreviousWeightEvidence` 构造新 context，登记 core/工作区双锚；先保存 producer/core/owner update journal 的回滚快照。
3. 执行 canonical producer →真实 q→完整 raw base recomputation→`stage_prepared_particle_candidates`；逐项核对 known/unknown/aggregate、全部 RB 统计和 parent support。
4. 成功后一起登记消费结果、发布 batch/source、更新 cutoff、持久化。delivery 已经持久化，是独立发生的外部效果；计算失败不删除 delivery，也不重新执行相机。
5. stage/重算失败恢复所有新增 catalogue/anchors、producer 和 Native 状态。SQLite 保存失败沿现有 durability-failed 路径停止，不能宣称已经撤销物理效果或确知磁盘结果。

`_capture_revision_transaction/:4025` 与 `_restore_revision_transaction/:4181` 要覆盖新 core 字段；现 stage 自己的内部 transaction 在登记新 owner context 之后才开始，不能误认为它已经包住此前登记。新类必须从固定 canonical 模块导入，纳入 source bytes/loaded code/固定配置绑定，并在纯 fresh resume 前可被 `StateCodec.runtime_types` 发现；不能依赖先建立另一个 stream 来加载类型。

## Producer 与密度后果

旧 `ControlledPositionProducer` 保持原 config/key/时间语义不变。建议新增明确开发 profile，其固定配置只授权模型、公开选择规则和显式受控关联；未来 packet 从 owner 目录进入上下文，不能每次重写 binding 来解除已消费限制。

首版的 S 为 neutral；A 的已配置公开 readout 仅消费一个 seed，保留其他候选/不可用原因，不读取私有 mask 选 A/框/seed。相机返回后没有公开有效 seed 时，不发布 fabricated measurement。受控测试的固定框或 decoder 是 fixture，须明示；自然 decoder/identity 尚未因此解决。

新 A 从真实前一批完整 log 权重继承 mass，保留显示为 0 的 finite-log 支持。known 的 pre-update predictive LL 使用原 prior，`H=[I3,0]` 更新三维信息；未观察朝向仍不更新。unknown/aggregate 继续既有显式受控 world-3D 基准，不把旧语义 posterior projection 再乘一次。新测量必须让公开的 `current_joint_decision_view` 与 Λ/η 在 active/no-factor 间出现可复算差异；不要求更改 utility 或保证动作变化。

当前 raw receipts 的 `source_posterior_snapshot_id=None` 正确，工作区防止同一个 posterior projection 重复消费的规则无需放宽。`TypedParticleState.revision_id` 继续用 S 的真实活跃 revision。不能用改 revision/UUID、“清 consumed_keys”或重跑 P5 制造刷新。

## 逐 cluster replay 的最小改法

1. 新 `AcceptedNativeUpdate` 保存原 cluster、logical key、kind（semantic/raw）、semantic revision/source、原 context key/cutoff、parent cluster。`consumed_schedule` 仍从最终 batch 的父链回溯，检查完整覆盖、无循环/孤儿；输出这些项而非 revision。raw 类型只从完整已接受原件和 profile 导出，不能 proof 自报。
2. `JointReplayGeneration.sources` 保留唯一 source；另加有序 `updates`。不要直接把同一 source 放两次：现 `validate_replay_source` 要求 source 在 generations 中恰好一个匹配。跨 generations 按原 logical key 对齐继承，不能按新 cluster ID 或 semantic revision 合并。
3. `prepare_generation` 根据仍活跃 semantic revision 筛选 updates。S 被撤回时其全部 raw updates 排除；不允许把 A 换到另一个 S。S 保留但其他来源被撤回时，S/A 顺序仍完整保留。
4. `rebuild_prepared_particle_history` 对 source 仅注册一次，按 updates 顺序调用 callback；每项从重建后的真实父 batch 计算，不能复用旧 LL/统计/权重。`ContinuousEvidenceInput.replay_joint_posterior` 当前所有 source 共用最终 cutoff，须改为每项历史 cutoff/prefix；当前 correction basis 与原历史观测时点分开。
5. `verify_raw_base` 当前从所有祖先 record clusters 得到 `predecessor_sources`，已经丢失“同一 source 的不同更新身份”。新 profile 需实际顺父链重建 update 列表及消费 key，而非数 source 次数或信 mutable producer state。legacy 单帧分支保持现契约。
6. 保存原 source/输入目录锚，replay 新 runtime 的 context 仍绑定原 action/receipt，产生新接受锚。恢复验证应检查当前及 archived generation 的完整原件。replay 不执行任何相机或语义动作。

全空 retained-history 当前会拒绝。最小切片保留 S0 并显式不覆盖“唯一语义全部撤回后无 Native posterior”；若目标要求全空情况，则增加明确无当前 posterior 状态和相关 collector 行为，不能造一个无来源均匀 batch 当作通过。

## 分类反馈的重复计数边界

`joint_camera_feedback.replay_camera_history:130` 只重放 native origin 等于当前 base view 的历史 command；raw publication 改变 view 后旧分类反馈会自然不匹配。这是现行为，**不是已经证明没有丢失/重复信息的证据**。

首个开发切片应明确只走位置 target 更新，保留原 classification/clarification 对照作为独立配置；若同一次图像已由 decoder 更新了决策视图，必须记录该 disposition，不能先乘分类 likelihood 再无声明地乘位置 likelihood。不能通过更换 utility 或抹去 `_observation_native_origins` 隐藏问题。完整同图像联合观测模型、自然跨时身份/相关性仍属于后续科学/协议定义。

## 优先验证顺序与可复用测试

1. **完整合法 owner 正路径**：复用 `test_native_position_production.py` 的 `scenario/advance/snapshot/weight_state` 和 `test_owned_rgbd_support.py` 的 `RGBDCamera/collect` 结构（不要直接混用两者 scope/time）。真实 owner 发 command，受控 camera 生成晚于 S 的 packet。publication 后 semantic source/hash、P5 调用数、账本不变；新 cluster、实际 parent、Native logmass/Λ/η 与独立 Gaussian 算术一致。active 与 no-factor 用相同原件与 utility。
2. **重复与限制**：A 重复消费无增量/无相机执行；B 不静默丢弃也不默认相乘；failed/empty/invalid-depth 保留原因。复用 `tests/test_continuous_camera_collection.py` 的 saved READY、uncertain effect 和失败路径。
3. **完整可信形状伪造**：仿 `test_native_raw_candidate_verification.py::test_complete_target_forgery_rejected_without_side_effect_then_legal`，保留真实 q、原外部 model/profile，完整重签 base/stats/proof，或搬运原 packet 到另一 action/source/父批/cutoff；deep direct stage 拒绝且 core/ledger/owner journal 不变，恢复原件后合法发布。
4. **逐 cluster 后果**：S neutral→A active→另一保留来源；撤回 S 后等于 S0/no-factor。撤回其他来源时 S/A 均保留且顺序/cutoff正确。复用 `test_native_joint_full_replay.py::test_partial_generation_failure_restores_all_owned_state` 注入中途异常，保证不会只恢复 producer 忘了 owner journal。
5. **fresh SQLite**：仿 `test_native_raw_candidate_verification.py::test_fresh_process_resume_without_constructing_another_stream`，纯新进程先 resume，核验原目录/已消费 key/后验，重复 A 仍无增量。保存 original DB；验收可操作拷贝，不能用验证过程改写原件。
6. **回归科学边界**：`test_native_log_weight_continuation.py` 的 finite 极小质量与 unknown/aggregate 下溢保留；`test_owned_visual_neural.py` 的完整来源伪造及 full replay；原 `test_native_position_production.py`、`test_native_joint_full_replay.py`、classification/clarification collector 保持通过。不能仅靠缺字段攻击或新 dataclass 测试交付。

## 哪些必须同轮完成，哪些可独立验证

以下必须作为同一功能变更冻结：owner 签发/原件目录及消费事务；typed context 与 canonical profile；deep consumer 原件/祖先完整重算；新的 consumed key/cluster；逐 cluster replay；fresh restore/rollback；新 profile 的 collector 接线及反馈 disposition。任何一块缺失，都不能交付“首条新观测已可靠更新 Native”。不要求整个改动只有一个大函数，但不能分别把部分测试称作总体通过。

可以先独立实现和验收的窄组件只有纯 read-only 的 **owner delivery 描述重建器**：给定 owner 原始 command/status/raw/scope 与签发时 source/parent，输出严格 typed 描述及完整 pins，复用真实 `prepare_observation → execute_observation → _accept_observation` 路径产生合法正样本；完整替换 receipt/command/raw/时间/parent 后拒绝，并验证无状态/账本/动作变化。它能先确认下一轮最容易接错的真实 authority 与时间接口，不涉及新 density、replay 或观测独立性，且会被完整切片直接消费。该组件的验收价值限于“来源适配正确”，不能代替 target 更新。无需为它扩大成通用新框架或单独跑真实 Unity。

逐 cluster schedule 可以在完整轮实现过程中先做，但既有 `JointFixture` 不提供所需新 raw 正路径；不要为拆小而删其 projection、手工 stage 无保护 receipt 或重新签一个 semantic source。完整切片仍须完成上面的优先测试并冻结后顺序 R1/R2。

## 权限与结果表述

原件接线、事务幂等、完整复算、逐簇回滚和显式受控测试可以继续自主开发。实际线上任意对象的关联、正式 pivot/AABB 定义、跨时间 Z 的演化、真实多视图相关性及接受阈值不能从开发 fixture 推定。四种已有 estimator/reference 均保留，不按验证结果选择胜者。

下一轮若只跑受控 camera，应写“owner-issued controlled RGB-D 更新真实 Native；自然身份与真实连续相机目标密度未完成”。只有在可验证的真实 executor/command/delivery链上实际执行后，才可称真实新相机 capture；当前 archive 原件仍只是 owner-admitted archived raw，不能改名冒充新物理动作。
