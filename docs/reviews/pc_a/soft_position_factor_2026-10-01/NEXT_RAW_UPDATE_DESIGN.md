# 下一轮主线：真实单帧 Native 桥接与逐观测簇更新

2026-10-01，只读接口调查与工程设计，非正式 R1/R2 报告。本代理参与了位置残差模型和纯数值 diagnostic 的实现，属于电脑 A 辅助工作，不是电脑 B 独立验收。

调查工作树：`/private/tmp/cpswm-pc-a-soft-position-factor-20261001`。调查时 HEAD 为开工提交 `0c89fb5b71098d3690d568e9f4ae7a33d5e722e5`；`controlled_position_producer.py`、driver 和相关 tests 尚未提交且 Native producer 正在收尾。**没有最终功能 SHA，本文件不能作为未来冻结代码的通过证明。**只读取了源码和现有 PLAN，没有执行真实归档推理、训练、Unity 或新的实验。本次仅新增本设计文档。

## 推进顺序

1. **先补真实归档单 capture → 实际训练模型 → Native publication。**证明已训练模型确实经过消费者改变真实 Native 权重和条件统计；不再把真实数据 numeric diagnostic 与合成模型 Native 测试并列当作组合证据。
2. **再补 owner 的独立 raw-observation 事务与逐 cluster replay。**保留原 semantic revision/source_id，用两次明示受控 capture 检验重复、恢复、撤回和账本后果。真实相邻帧不默认独立，不连续乘真实 likelihood。
3. **raw-seed depth 反投影基线可小范围并行，非主线前置阻塞。**它回答聚合是否优于原始深度点；soft 比 uniform 只能比较两种聚合，尚不能回答聚合是否有用。本轮两估计器协议和已曝光结果保持不变，下一轮另立固定开发协议。

这些工作不新增正式位置参考、科学阈值、自然实例身份权威或新的任务效用。

## 当前接线的实际边界

- `tools/run_soft_position_development.py:collect_public/build` 从原始 RGB-D、相机位姿及已 pin 的公开候选重建全部 96 帧；train 私有标签用于四个残差模型拟合；模型恢复后先生成全部公开修正，再调用 `position_factor_diagnostic.diagnose`，最后才接 validation 标签。diagnostic 投影只有 house_index、sdk_index、action_id、observations，不接受 labels。
- `tools/position_factor_diagnostic.py:diagnose` 检查真实模型的 predictive density、Gaussian 自然参数、去重和重建，但不创建 native receipt、不调用 owner，不证明 Native 发布。
- `tools/controlled_position_producer.py:ControlledPositionProducer._public/produce` 已能从 `NativeJointContext.visible_prefix` 取得实际 admitted RGB-D，重算公开 seed 读出，调用位置模型，再返回 raw-observation receipts。`tests/test_native_position_production.py` 已覆盖真实 Native 发布/恢复/撤回，但当前 fixture 使用 synthetic residual R=I 和 constant affinity；它不等于实际 96 帧训练模型的消费实验。
- `tools/run_history_action_loop.py:open_joint` 当前仍构造 `NeuralNativeProducer(OpenWorldJointFixture(), ...)`。classification 与 clarification 是既有对照。仅替换 q 的输入或打开 owned visual context，不会自动替换其目标观测密度。

## 一：真实单 capture 桥接的最小独立边界

建议新建独立开发工具及 tests，复用现有模型/producer/Native 路径；第一步不修改 live collector，也不启动新 Unity 采集。

输入必须是原 collection 外部 pin、其经过匹配历史入口 fresh 重算的公开原件、当前四模型产物及外部 pin、固定 combined affinity 原模型 pin，以及 Native proposal checkpoint pin。模型字典自己提供的 SHA 不替代父产物来源证明。fit_failed 模型保持显式不可用，不用人工模型补位。

公开选择沿当前固定 house/frame/seed 顺序，只选择第一个 available seed；四个组合保留，另设 enabled=False 的无因子对照。不能查看 eligible label 再换 seed/框/房屋，也不能据拟合或后验效果选择正式参考。若公开无候选或无有效 seed，保留不可用结果。

实际链条应是：

`原 StateCodec(command, delivery) → 原 observation bytes 经 ContinuousEvidenceInput.admit → 配置冻结的 ControlledPositionProducer → NeuralNativeProducer → produce_joint_posterior → stage_prepared_particle_candidates → NativeParticleWorkspace.advance → current_joint_decision_view`。

必须处理三个具体衔接问题：

1. **scope/time 不可改原件。**现 `run_correction_replay_comparison.build` 固定 `BackboneWiringProbe(seed=171)` 的 scope/年代；真实 archive 每屋 scope 随机、时间不同。应新增可参数化的显式受控 semantic fixture，并使其 scope 与原 capture 一致、语义时序合法。只构造/标注 synthetic semantic 上下文，不重写真实 RGB-D envelope、receipt、UUID 或 capture_time。归档的 `fixed-offline-factor-view@1` command 也不能改名为新 owner-issued camera capability；本步只声称 owner admitted archive raw。
2. **公开 candidate/provenance 要闭合。**当前 producer `_public` 仅接一个配置框，且 provenance.source_sha256 来自 packet_binding；dataset `public_readout` 用全部候选和 public_metadata SHA。完整候选集/provenance 参与 input/seed ID，因此即使同网格数值一致，两者测量 ID 也可能不同。优先使用统一的公开重建 adapter，保留完整 canonical candidate 集、来源及同一 seed/neighborhood。若首步保留单框窄 producer，必须记录“新 consumer readout”与原公开邻域的严格对应，只比较同邻域的数值，不冒称原 seed ID 完全相同。候选来源要从已核验公开前端重建，不能手工声明 fixture 框后称为自然检测。
3. **只使用真训练参数。**由实际 fit 产物 restore 原 bias/R 和 estimator pin；不把本轮 synthetic R=I、constant affinity 混入真实桥接。控制的关联、reference origin、prior、unknown 模型和 ARMS proposal 身份单独列出，仍为显式 fixture 假设。

交付至少保存原件与模型外部 pins、选择 ordinal/框/网格、实际 admitted IDs、配置绑定、更新前后的 Native receipts/归一化权重/Λ/η/均值、无因子结果、SQLite fresh resume、单次重复不增量、撤回后重放与无因子一致。独立矩阵算术与原诊断逐项对照。每个模型只消费一个 capture/seed，不叠乘相关 seed 或邻帧。

## 二：为什么新 camera delivery 目前不会直接更新 Native

已确认的路径：

- `structure_two_continuous_input.py:_accept_observation`（调查时 1207 行）验证 owner capability 对应 delivery、时间和原件后调用 `admit`，保存 `_observation_status`；它不发布 Native 位置更新。
- `continuous_camera_collection.py:collect_posterior_step` 在规划前调用 `produce_joint_posterior`，执行返回后只调用 `advance(cutoff=delivery.received_at)`。若 perception 没有新 semantic transition，`advance` 返回 `INSUFFICIENT_SEMANTIC_EVIDENCE`，仅推进 cutoff。
- `structure_two_continuous_input.py:produce_joint_posterior`（815 行）在当前 snapshot 和 `_joint_published_source_sha256` 不变时直接返回。新 raw delivery 不能使这个条件失效。
- `joint_camera_feedback.py:replay_camera_history` 可依据 owner-issued 分类结果改变 `JointDecisionView`，但它是决策视图重加权，不是 Native Gaussian 条件统计更新。
- 当前 `ControlledPositionProducer._public` 还要求 capture_time 不晚于绑定 semantic detection_time；正常在语义来源之后执行的新相机观测不满足该单帧 fixture 条件。新 raw-update 分支要按实际 command/delivery 时间验证，不能改旧 detection_time 假装满足。

所以不能通过清空 `_joint_published_*`、改 UUID、伪造一次 semantic transition、重置 producer consumed_keys 或重复 PCHMP 投影来“触发更新”。

## 三：最小正确 raw-observation 更新入口

### 两种身份必须分开

`NativePosteriorSource.validate_content/publish_posterior` 把 source_id 固定为 `(workspace runtime, semantic history revision)` 的内容 UUID。这是语义来源锚，保持不变。

另为每次已接受的 owner capture 建立不可变的 **观测更新身份**，至少绑定：

- 原 semantic revision/source body，以及当前 generation；
- owner-issued command/action ID、完整 command/delivery 内容与成功/失败状态；
- RGB-D/相机原 observation IDs、原件内容/receipt、scope、scene/坐标定义；
- 公开 canonical 候选/邻域/seed 选择、真实模型及实现绑定；
- 原 decision/capture/arrival/received/cutoff，实际父 batch/输入簇；
- 本次更新的 disposition（可消费、不可用、失败），及重复处理的既定结果。

推荐入口形式是 owner 方法如 `consume_owned_position_observation(action_id)`；名称仅建议。调用者只提交 action ID，不提交可替换 posterior、receipt、任意观测字典或“已核验”标志。owner 从现有 `_observation_commands/_observation_status/_raw/_observation_native_origins` 重建和核对完整输入。

可沿 `NativeVisualSource/NativeVisualAuthority` 的 owner-only catalogue 做相同权限隔离，但观测 revision 需要明确绑定具体 action/原 cutoff/父 batch，不能只用“截至现在的所有图像”摘要。配置 pin 与可变消费进度分离：模型/选择规则开工冻结，后来接收新 packet 是输入历史，不修改 producer 的配置权限。

### 原生工作区实际可以容纳同语义来源多次 raw 更新

`NativeParticleWorkspace.input_journal/input_bodies` 以 `evidence_cluster_id` 为键；每次新 capture 使用独立 cluster，particle/proposal IDs 独立，父 particle 来自上一次真实 Native posterior。

`consumed_posterior_sources` 的每 source 一次限制仅针对 `posterior_projection_not_likelihood`；raw receipts 必须保持 `source_posterior_snapshot_id=None`。**无需放松原投影防重规则。**raw receipt 的 `TypedParticleState.revision_id` 仍使用真实、仍活跃的 semantic revision，使 `prototype_spine.stage_prepared_particle_candidates` 可以验证其真实事件链。观测更新独立 ID 不伪装成新的事件 revision。

每次仅用更新前 prior 计算新观测 predictive log density 和 Λ/η 增量；不重复加入旧 semantic likelihood，不将父归一化权重重置为 1。原 evidence cluster 相同的重复调用返回原接受结果；原 action/观测内容被改则拒绝；原始输入保留，不发生第二次物理执行。

事务边界保持两层：delivery 接收已独立持久化；Native consume 失败时回滚 producer/core/消费 journal，仍保留合法 delivery，后续只重试计算。成功时 Native batch、输入锚、消费 journal、producer state 一并提交。SQLite 保存失败沿现有 durability-failed 语义阻止继续，不把未确知持久化结果当成功。

正常 raw-update 时间检查应是合法 owner command 的 `decision <= capture <= arrival <= received <= cutoff`，并绑定 command 发出时的原 Native view。若该 semantic anchor 已撤回或 command 的原来源失效，明确隔离，不将旧 observation 自动迁移到新的实例或语义来源。多 capture 首轮仅使用明示静态受控状态模型，不据此假定真实跨时状态不变或观测独立。

## 四：重放不是删除 early-return 一处即可

当前 `native_joint_replay.consumed_schedule`（110 行）沿父 cluster 找出顺序，但输出每批的 **semantic revision UUID**，末尾明确拒绝重复 revision。`prepare_generation`（142 行）又按 revision 合并 schedule，只为每个 revision 调用一次 producer。两次合法 raw capture 绑定同一个 semantic revision 时，当前 full replay 将拒绝或不能保留两次更新。

下一轮应让重放计划保留完整接受更新项，沿父 cluster 顺序处理：

`semantic-source update S → raw capture A anchored at S → raw capture B anchored at S → later semantic-source update ...`

计划项包含独立更新身份、种类、semantic anchor、原接受输入锚、原 cutoff、父项，以及受控 producer 所需的 owner 原件引用。**semantic source catalogue 仍可按 revision 唯一；消费 schedule 不能再按该 revision 去重。**保留每个 raw 项与 source 的依赖，而不是复制一个新的 PCHMP source。

纠正/撤回时：

- `invalidate_revisions` 可继续按真实 semantic revision 使依赖记录不可读；保留全历史后从初始 producer state 重建。
- 若 S 被撤回，S 下的 A/B 都从新 generation 的 retained schedule 排除；原 raw bytes、owner receipt、旧 workspace 和旧更新项仍留档。不能把 A/B 换 anchor 再消费。
- 若 S 仍活跃而其他来源被撤回，A/B 必须按原顺序分别重算，从新 parent prior 计算新 S/LL 和自然参数；不复用旧权重/统计，不借未来 capture 影响前一个更新。
- replay context 应使用每项**原历史 cutoff/可见 prefix**，而非当前 `replay_joint_posterior` 对全部来源共享最终 cutoff。当前 correction basis 和历史观测时点分别保存，沿现有 `ReplayAssessment` 的区分方式扩展。
- 新 generation 中 runtime/父 batch 内容可变，但原 action/raw logical identity 与原 owner acceptance link 必须保留。只由内部 replay 建立旧接受项到新运行时项的映射；调用者不得重签后提供新映射。重放不执行任何新动作。
- 当前 `prepare_generation` 在全部来源均被移除时拒绝空 retained history；如果新矩阵含“唯一 S 与两个 capture 全撤回”，应预先定义显式无当前 Native posterior 的结果，不造空集合上的归一化信念。否则最小合法矩阵保留另一未撤回来源，并明确全空状态尚未覆盖。

## 五：建议的实现文件边界

| 文件/入口 | 最小责任 |
| --- | --- |
| 新独立 archive-to-native 工具与 tests | 真 pins、原件 admission、受控 semantic fixture、单 capture 四模型/无因子、落盘 fresh/retract；不改 live collector |
| `structure_two_continuous_input.py` | owner raw-update 事务、可见性/command/receipt 重建、精确防重、当前 publication 身份、恢复验证 |
| `native_joint_production.py` 及新的纯观测更新契约模块 | 为 context/产物增加可检查的 owner observation-update 描述；与 semantic source 身份分离 |
| `structure_two_particle_workspace.py` / `prototype_spine.py` | 接受输入体绑定新观测描述和 core anchor；保留 raw/projection 语义、父权重/统计谱系、当前 source 校验 |
| `native_neural_production.py` | 将观测描述加入实际 context/proof 的可重算闭包；fresh body 验证从已注册 owner 输入取值，不能仅信任 producer 自签字段 |
| `native_joint_replay.py` | 逐 cluster 的有序完整计划、依赖撤回、原 cutoff 与新 generation 映射 |
| `continuous_state_codec.py` / `ContinuousEvidenceInput.resume` | 新类型的干净进程注册/可加载性与 fresh owner journal 重建；现 SQLite 整图保存本身通常无需加新表 |
| `continuous_camera_collection.py` / `revised_camera_collection.py` | 在合法 delivery 后调用可选的新消费入口；保留原 classification/clarification 分支默认行为 |
| `joint_camera_feedback.py` | 明确当前 capture 已由哪一观测模型消费，避免同图像被分类 likelihood 与位置 likelihood 无声明地再次相乘 |

无需每个文件都增加新机制；现有 StateCodec、SQLite FULL commit、owner capability、Native 原子 stage/rollback 尽量复用。新公开入口不接受任意已归一化数值作为来源证据。

## 六：最小有后果测试矩阵

先提供完整合法链：同一 semantic source，两个不同 owner-issued capture，分别产生独立簇；首个更新后的真实 prior 进入第二个预测密度/统计更新。用明示受控模型独立闭式核对 LL、归一化权重、Λ/η、已消费簇和完整父链；其他两块零信息，账本语义操作数不因纯位置观测增加。

随后必须覆盖：

1. 同 action 重试、相同 packet 重复别名、无观测/失败 delivery、非法将同 packet 换新 action/UUID/seed 重签；不能因别名重复增量，失败不偷偷另选 label/seed。
2. 完整合法 receipt 搬到另一 owner/scope/semantic source/父 batch；单改 raw 深度或相机、连同缓存/模型声明/所有自签摘要一起重签；保留外部 pin 与原 owner catalogue 后拒绝，并验证 Native 状态/账本未改变。
3. 合法 A/B 后 fresh SQLite 新进程恢复，重算 owner/proof/输入 schedule，重复 B 仍不增量，继续 C 仍接真实父链；故障注入在 admission 后/计算中/保存边界，不重发物理动作。
4. 撤回 S 时 A/B 一起失效并保留旧 archive；重放后等于“没有 S/A/B”的完整对照。若只撤回另一来源，保留 A/B 的原顺序、原 cutoff 和两次消费；一次重放后再次纠正/恢复也不能折叠次数。
5. 在 A cutoff 查看不到 B；伪造 cutoff/早到/晚到、重排 A/B、删一项/加一项/孤儿 parent、完全自洽重签 journal，但不改 owner 原接受锚时均拒绝。
6. classification 与 clarification 旧控制流程保持；新位置开发支路不默认为同一图像上的两套 likelihood 条件独立。当前 camera feedback 按原 Native view 匹配，raw publish 会改变 view，因此须明确消费策略，不能让旧分类效果静默丢失或重复计算。

同数据、同参数、同 utility 下动作若不变，保留不变结果。受控多 capture 的状态机通过不代表真实邻帧可以独立相乘，也不证明主动观测收益。

## 七：raw-seed 基线与权限边界

下一轮 raw-seed 使用完全相同的公开 seed、有效性、候选/邻域采样和私有标签；读出直接取 `camera.world_point(u, v, depth[v,u])`。当前 `soft_surface_position.readout_frame` 的 neighborhood 已保存该点，能独立逐项重算。重复 seed 来自不同邻域时仍保留原采样分母和相关性说明。分别报告 raw/去 bias，仍以原 train 拟合两参考模型，不挑验证赢家、不设阈值，不改本轮两个估计器历史身份。此基线不阻塞 Native 主线。

用户已授权离线监督、RGB-D/相机自位姿输入、主动澄清保留原对照，以及持续工程推进。上述原件桥接、owner 事务、去重、replay/SQLite 修复、受控攻击和显式开发基线无需再次索取权限。正式选择 pivot/AABB 之一、自然世界身份接受规则、校准或发布阈值、把真实跨帧 likelihood 当独立证据、修改任务 utility 或宣称科学收益，不由本设计自动决定。

完成实现仍须冻结具体 SHA，再顺序 R1/R2；本调查不替代两轮审核，也不授权提前运行未审核的真实新协议。

## 冻结修复37981c3后的接口补充（仍为只读设计）

当前canonical位置producer已移到`src/cpswm/system/controlled_position_producer.py`，tools仅兼容导出。其cluster由`(semantic source_id, 固定producer binding)`生成，checkpoint只允许零或一个measurement key，`recompute`也只允许祖先中一次原始测量。所以下一轮同来源多capture不能只放开continuous早退或replay重复revision；还要有明确的新观测更新身份和独立多观测producer协议，保持当前单源单seed协议不变。

新`native_raw_verification.profile_for`使用闭合registry，只保护精确canonical NeuralNativeProducer＋ControlledPositionProducer。新多观测producer不能因类型未被识别而走legacy未保护分支后称同等验收；必须同步定义固定profile、拥有者实际command/delivery上下文、从真实父链重算消费状态及完整base结果的同级核验。新增profile的拟合参数/未知分支等仍按既有科学边界显式记录。一次相机执行的通过结果不意味着其返回图像已经更新Native统计。
