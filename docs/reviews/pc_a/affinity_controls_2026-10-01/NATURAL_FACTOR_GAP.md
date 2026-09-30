# 自然实例／位置因子主线缺口与下一开发切片

2026-10-01，A 辅助只读主线调查；读取工作树 `/private/tmp/cpswm-pc-a-affinity-controls-20261001`，源码 `a6c026963b5fec1503fa0d582fe016eccf60c756`，base PR76 `ffcaa7b292c73201d799f6631688387409c21cb7`。此调查不替代正在顺序进行的 R2，不修改源码、旧原件，不训练新模型、不启动 Unity。下文是建议方案，尚未实现或验收。

**下一轮最有价值的有界工程任务：公开锚点软表面读出 → SDK pivot/AABB 两套三维开发残差模型 → 显式关联条件下的受控 joint 似然消费与撤回重放。** 它比把 affinity 附到 q 的输入上更接近缺失主线。保留两套参考，不选择正式位置定义；自然身份关联仍未解决，不能据此宣称完整自然联合推断。

## 当前链路的实际断点

| 已有入口 | 已有能力 | 仍缺什么／不能怎样解释 |
|---|---|---|
| `tools/run_history_action_loop.py:90` 的 `open_joint` | `NeuralNativeProducer(OpenWorldJointFixture(), ...)` 驱动真实相机历史 | 候选、先验、条件测量仍来自测试 fixture；真实像素没有替代该自然测量模型 |
| `native_joint_production.py:34` 的 `NativeJointContext`；`native_visual_source.py:29` | 拥有者签发的可见 RGB-D/候选/几何、时间与 scope 绑定 | 来源可信不等于 I/Z 的经验观测模型已存在 |
| `unity_rgbd.py:195–281` | 框内三种深度排序表面点，公开相机变换 | `object_instance_id/object_centre/orientation/probability=None`，`likelihood_model=None`；表面点不是对象中心 |
| `proposal_perception.py:42/110` | 因果图像框关联与 `perceptual-track:*` 候选键 | 相机几何变化即重建局部分段，未补偿运动；已有 IoU 开发阈值不构成正式 world ID 接受规则。未知和备选必须保留 |
| `native_neural_production.py:126/267/531` | 公开视觉上下文进 q，实际检查点重推；全部候选枚举 | `materialize` 同时写 `proposal_log_probability=log(q)` 与 `integration_log_weight=log(q)`，在目标权重中相消。只改变 q 不会补上目标观测证据 |
| `tests/test_native_joint_production.py:45/109/158` 的 `JointFixture` | 明示受控六维 Gaussian、位置质量及 RLS 更新 | 数字是假定值，`observation_log_likelihood=0`。首个 receipt 另用 `posterior_projection_not_likelihood`，不能在它上面直接加非零观测似然 |
| `structure_two_conditional_updates.py:30/67` | 三块自然参数重算，允许 m×6 的 H；重复证据簇拒绝 | 它只做统计更新，不自动生成 receipt 的观测密度、身份责任度、location_mass 或动作价值 |
| `pose_observation_model.py:48/109/258` | 六维局部位姿误差 bias/full covariance 拟合，修正、撤回 | 不含像素位姿估计器；现有类要求完整六维残差、同 chart、至少7样本及rank6，不能把三维数据补0朝向来复用 |
| `structure_two_particle_workspace.py:996` | 位置边际从 joint particle 权重与 alpha 读出 | 单独改变 Gaussian Λ/η 不会自动改变此位置边际 |
| `tools/clarification_camera_model.py:32` | 已批准的开发澄清效用；逐次相机反馈 | 已有观测结果仍为类别有/无，known/unknown 假设对应固定朝向和假定概率；对象测量似然与动作后的结果分布不是同一模型 |

`ParticleRevisionReceipt.exact_log_weight`（`evaluation_operations/structure_two_selected_method.py:412`）明确组合 prior、transition、observation、projection、constraints、−log(q)+integration。要推进目标密度，必须让合法来源的 measurement 实际改变这里的 observation 项，并保留未决分支及归一化；增加字段、改变 q 或统计 ref 哈希不够。

## 从公开观测到 joint density 缺失的具体依赖

1. **公开对象候选测量。** 当前仅有框、点对亲和度和几何。需要一个固定可重推的表面代表点估计器，绑定 RGB/depth/camera、action/frame、检测候选、网格种子、完整邻域、模型 pin；它输出局部候选，不输出 SDK ID 或正式 world ID。
2. **I→Z 的条件关联。** 必须知道某个公开测量由哪个联合假设的实例解释，哪些测量是杂波、未知或其他对象，以及遮挡/漏检如何保留。离线 seed mask ID 可以监督这一问题，不能在线直接赋给粒子。COCO 类别≠SDK实例，不能拿最近真值点或正确类别给在线候选配 I。
3. **位置定义与测量域。** SDK transform pivot 与 AABB center 是两种真值定义；source prefab placement 又是第三种输入语义。必须为开发模型分别命名，绑定 frame、单位、时刻和局部 reference。六维状态是 `R³ × SO(3)` 局部坐标，平移用世界轴、转角用参考对象局部轴，并非 SE(3) 对数。
4. **经验误差。** 三维公开读出需要各参考对应的 bias、3×3 covariance、估计器/数据 pin、训练范围和残差秩。无效/混物/透明表面/未知的行为需要保留。原 Gaussian 家族可做明示开发假设；训练残差不自动获得校准权威。
5. **conditional measurement 适配器。** 除 z/H/R 外，接口还要求 source records、cluster、model ID、information weight，以及其他两块的 location_mass/RLS 输入。后者不能从 detector/affinity 信心制造；本切片可明确给零贡献并保留已有先验，记录是位置块局部接通。
6. **真正的观测密度生产与来源。** 需要将上述同一模型的预测密度写入 raw-observation receipt，再用同一证据更新 Λ/η，来源只计一次。不能让报表统计和 receipt 分别使用不同 R/参考点，也不能先用观测更新状态、再以更新后状态给同一观测打分。
7. **动作模型。** 当前澄清策略还缺自然对象观测在各相机动作下的结果分布、可见性/未决结果和对应经验依据。受控动作后果可沿旧接口测通，但不能据此宣布真实行动收益。

`conditioned_proposal_runtime.py:62/138` 的 `ConditionalProposalModel.measure`、完整 evidence groups 和可重放 `ConditionedSupport` 可复用；它明确没有 native publication 或 ledger 权利。仍需显式 producer 适配，而不能把该对象的返回值当成已接通 live density。

## 已批准的离线包能提供什么

授权依据 `docs/reviews/pc_a/offline_factor_data_2026-09-30/AUTHORIZATION_AND_PLAN.md` 与 `owned_visual_neural_2026-09-30/CALIBRATION_DECISION.md`：SDK实例ID、mask、位置允许离线训练/校准，线上输入仍只有 RGB-D 和相机自位姿。

- 固定12屋、96公开帧及144个SDK事件，房屋1–8训练、9–12开发验证；同动作 RGB/depth、mask/catalog/SDK metadata 及资格/资产隔离可核对。只有合格且唯一 mask 归属可作实例监督，其余 VOID；完整曝光目录不意味着每个目标都适用或可见。
- 同一像素／种子的 mask 成员关系，可监督同/不同实例或为离线残差表连接该种子对应对象的两套位置。它不保证透明物体深度点属于该渲染实例；软支持可能含其他对象，要作为误差/失败保留。
- `offline_frontend_evaluation.py:128–141` 已同时导出 `sdk_transform_position_m` 与 `sdk_aabb_center_m`，`verify_offline_factor_capture.py:405–456` 绑定两者及 source placement 语义。可复用其 join/资格核验；不将 source placement–SDK差值当作观测误差。
- 原始 SDK metadata 留有对象旋转，采集校验也检查其有限性及静止性；但尚无公开朝向估计器、对称物体姿态定义及完整朝向观测/校准证据。本轮不能把“文件里有rotation”偷换成已授权且适用的六维标签训练，更不能补0。
- 物体静止、相机原地 yaw 的数据能测固定视角下的候选/表面误差；不能验证物体移动、接触/释放/人物身份、平移视差、长期变化。12屋和大量相关种子不能替代独立确认数据。

## 建议的最小开发切片

### A. 一个固定的公开软表面读出

固定沿用原 combined 作为兼容性主支，并保留相同网格的无权重几何读出作开发参照；不根据正在进行的曝光验证结果选择正式胜者。对每个公开框的每个有效8×8种子，保留整行亲和度与全部邻域来源，计算加权世界表面代表点。明确叫 `soft_surface_representative`，不叫对象中心或正式实例。

实现前固定四项：自配对权重（可明示同一点恒1，属于读出定义）、无效深度邻点处理、分母为零的不可用状态、重复框/同seed但不同邻域的测量身份。公开种子不能由mask挑选；无候选、无有效点、VOID种子和多实例混合都保留。权重仅是读出系数，不是已校准的实例责任度或若干独立观测的置信度。

可复用 `instance_affinity.grid_pixels/pixel_pairs/pair_features/predict`，`instance_affinity_dataset.public_frame` 的去重与来源，以及 `CameraSelfPose.world_point`。私有 join 放在独立评价/拟合端，复用 `label_frame` 和 `reconstruct_catalog/_audit_rows` 的同事件、唯一归属与资格核查。

### B. 两套三维训练残差模型，保留失败

每个唯一合格seed离线关联其对象，分别计算“公开代表点 − SDK pivot”和“公开代表点 − SDK AABB center”残差；只用原训练分区拟合两套 bias/covariance。每套模型绑定估计器、参考种类、坐标域、完整训练成员/标签摘要和采样方案。两套都保存，不据validation选择正式参考或接受门槛。

这里可沿 `ConditionalMeasurement` 已有线性Gaussian族做**显式三维开发模型**，复用 `GaussianPoseObservationModel` 的数据身份、有限值、秩和正定检查思路；不能调用六维 fit 并虚构朝向。三维完整协方差至少需要足够非共面残差，秩不足就拒绝；不静默加epsilon、假定对角噪声或删困难对象。

最小版用固定seed采样分布的经验 moments，清楚它描述的是“条件于该seed正确关联”的误差。所有seed保留并不意味着每个seed独立；报告seed、对象帧、对象、房屋四种分母，保留逐屋/对象帧残差与不可用项，不以像素数充作独立校准样本。旧combined已用house1–8训练，因此从其中划出7–8拟合噪声也不能声称整个估计器对这两屋未见过；真正独立校准需后续交叉拟合整个学习链或新增数据。此轮训练残差与曝光开发验证分开陈述即可，不必为此阻断准备实现。

### C. 受控 joint producer 中证明目标后果

最小演示只消费**一个预先固定的公开seed/证据簇**；实例关联及多个位置假设由显式受控 fixture 提供。线上自然 I→Z 仍保持未解决。不要在这一轮新增真实多seed mixture、用亲和度相乘，或自动提升自然候选身份。

现有局部状态用6维theta时，使用 `H=[I3,0]`，但测量必须为：公开世界代表点减去该局部 reference 的世界平移，再减去拟合 bias。不能把绝对 world XYZ 直接当局部delta。使用三维R，不创建观测朝向。信息增量的旋转行/列和自然向量旋转部分应为0；若既有先验含位置-旋转相关项，旋转后验可间接改变，不能泛称所有朝向后验不变。

若沿用当前 Gaussian RB 状态，先从**更新前**的 Λ/η 得到 mu/Sigma，再按既有线性Gaussian模型计算预测观测：创新 `z−H mu`、协方差 `S=H Sigma Hᵀ+R`，包含完整3维normalizer/logdet。然后同一条测量进入 `rebuild_conditional_state`。这只是既有模型族的受控消费算术，不构成新的自然likelihood获准。只用R给更新后均值打分会遗漏状态不确定性并重复使用观测。

注意 receipt 的语义门：`posterior_projection_not_likelihood` 禁止非零 observation 项。应在独立的 raw-observation 更新中以已接受前一步 posterior 为prior，或构造来源完全明示的受控producer；保持语义投影只消费一次，不能关闭校验或重命名旧projection为likelihood。未知分支也须保留其显式受控prior/likelihood，不能在归一化前删除。

### D. 必须观察到的数值后果

交付至少包含一条完整受控正路径：同一关联、同一prior/transition/constraints/q，改变真实公开测量z后，记录不同 `observation_log_likelihood`、目标log weight与归一化particle posterior；q与integration抵消后差异仍存在。同步验证Λ/η与独立闭式算式一致。

随后纠正／撤回该证据，完整重算恢复预期目标权重及状态；落盘恢复与新进程fresh一致；同源seed重复计入必须被拒绝或显式归为同一簇。若用既有受控澄清模型展示动作变化，固定其来源和效用表，展示测量变化→posterior变化→下一动作变化，并明确相机结果模型仍是假定的。没有动作变化也保留，不调效用或阈值制造改善。至少target-weight路径必须有真实数值后果，不能只比较新增字段或hash。

开发失败同样有用：混物使残差大、rank不足、两参考均差、无监督seed、heldout退化、没有决策变化，都能定位是读出、身份、误差还是效用环节未闭合。不得删失败重新选房屋、参考点或阈值。

## 可复用测试与正式决策边界

现成测试入口：

- `tests/test_owned_rgbd_support.py`：真实owner、原件重推、完整几何伪造、恢复及账本/动作保持。
- `tests/test_surface_factor_diagnostic.py`：完整对象矩阵、双位置参考、空/失败/重复帧及私有参考不改公开预测。
- `tests/test_instance_affinity_dataset.py`、`test_run_instance_affinity.py`：同SDK事件、资格/VOID、多框去重、训练与验证隔离。
- `tests/test_structure_two_pose.py`、`test_pose_observation_model.py`：局部坐标、不同RB维度、误差秩、零贡献保持、纠正/撤回。
- `tests/test_conditional_revision_replay.py`、`test_conditioned_proposal_runtime.py`：完整来源分组、同源只计一次、三块重算和完整伪造重验。
- `tests/test_native_joint_full_replay.py::test_replayed_joint_state_recovers_and_drives_one_controlled_camera_action`、`tests/test_joint_camera_feedback.py::test_negative_measurement_changes_next_selected_action`：已有实际决策后果链路。复用控制夹具，不改称自然收益。

可自主推进：固定公开读出实现、全部失败保留、两参考分别导出/拟合开发残差、部分观测维度适配、已声明Gaussian家族的受控算术、receipt来源接线及重放、上述有后果的工程测试。每个实现轮仍冻结后顺序R1/R2再跑真实开发数据。

不能静默决定：正式Z参考点与朝向对称性；自然world身份/跨视角关联接受规则及新建/未知行为；真实多seed/跨帧依赖模型及正常化；正式误差分布/外推域/校准接受门槛和noise floor；新的正式任务效用、成功标准或观测动作模型。此处两套位置开发假设与一个受控关联实验不等于这些决定已作出。

完整H/R/I/C/Z/r/V、三个RB blocks、七算子、隐藏事件、多人物、开放世界和可逆反馈保持。只接通位置块局部开发切片，不能把未有测量依据的其他块填成新事实，也不能把局部通过改称全pipeline闭合。
