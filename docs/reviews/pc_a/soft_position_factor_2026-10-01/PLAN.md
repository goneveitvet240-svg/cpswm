# 六小时主线第二轮：公开表面读出、双参考误差与受控因子消费

2026-10-01开工。用户六小时授权窗为00:18:40–06:18:40上海；第一轮PR77已完成双审、真实三模式run/fresh、独立算术与原件交付。第二轮分支codex/pc-a-soft-position-factor-20261001，base为PR77 head `8623e7890594fce2b3c872bd2484b30138a9f408`。实际功能/审查源码在实现冻结时另记，不把开工SHA当未来结果。

开工fetch成功；共享集成19ddf26830348a2f0b33f0af54d6ba702c5cfb1c、B fd4ca6ef5e81c90d7cf7987b42c0b2810d8a810a未变。工作树/private/tmp/cpswm-pc-a-soft-position-factor-20261001。旧封存包、用户原工作树、STATUS_B保持。

## 主线理由与权限

现有live路径仍由OpenWorldJointFixture提供目标观测项。只增加q输入在精确枚举的importance/integration修正后不一定改变后验；本轮必须检验观测密度、统计与目标权重的实际数值后果。用户已批准离线SDK ID/mask/位置训练校准，以及RGB-D/相机自位姿线上输入。本轮自主决定的是固定开发估计器和既有线性Gaussian族的工程适配，不选择正式位置定义、世界身份接受规则或校准阈值。

保留完整H/R/I/C/Z/r/V、三个RB blocks、七算子、位置+朝向、原分类对照和主动澄清。当前只补位置块的开发测量与消费证据；其他未有测量依据的块不填事实，朝向不补0作为观测。

## 冻结开发协议

输入沿用PR73/74/76/77已pin原件和原房屋分区，所有96帧保留。当前父controls ledger外pin `5eaabaaae15e4ed453c0f84b4f243103e25e5e9c1125f87f23e82e2be352bad2`；父功能源码a6c026963b5fec1503fa0d582fe016eccf60c756（879份Python）。用匹配历史入口fresh核验后，当前新源码从公开RGB-D、相机自位姿与缓存公开框再生成读出，不根据mask选框/seed。

公开估计器固定原combined亲和模型（原inner pin492ae03792fef90f6a1428b80a68da27818df1e595b42f2290ac874079458d22），原因是沿用此前固定依赖，不据本次曝光验证挑胜者。每框原8×8唯一像素网格，每个seed保留；无效深度seed明确不可用，邻域中无效深度不参与平均。两个同样本读出同时保存：uniform有效世界表面点均值；soft使用seed到全部有效邻点的原亲和分数，自项恒1，再归一化计算加权世界表面点。恒1是固定读出定义，不是校准责任度。无有效点、无候选和VOID种子不删除。两者都只称surface representative，不称对象中心/完整mask/世界实例。

同一动作内，具有完全相同规范网格邻域与seed的重复候选只生成一个公共测量，保留全部候选/前端来源；相同seed但不同邻域属于不同读出。像素、完整邻域、有效性、来源、模型pin、输入摘要与坐标域一起绑定。不同视图和seed有强相关性，公共测量去重不等于统计独立。

私有标签在公开读出之后连接：seed唯一属于合格rendered mask且公开深度有效，才提供该对象的SDK transform pivot与AABB center两套标签；否则明确VOID及原因。mask不改变公开读出，rendered归属不保证透明物体深度的物理表面归属。两个参考分别命名保存，不据验证集选正式参考。

每估计器×每参考共4个三维开发残差模型，仅原train(1–8屋)拟合：residual=world representative−truth；bias为经验均值，R为ddof=1完整3×3协方差。至少4行、中心残差rank3、对称正定且有限；不足拒绝并保留结果，不加epsilon、不删困难对象、不虚构六维朝向。全部公开测量先完成，训练只读取train标签；冻结模型用于全部公开修正，之后连接validation(9–12屋)标签评价。过去combined已见train全部8屋，不能把其中两屋改称整链未见校准集。

这是固定seed采样分布、条件于seed正确关联的误差开发模型。报告seed、对象帧、对象、房屋分母，逐屋/对象帧及两参考、原始/去bias残差；相关seed不充作独立校准样本。不做正式校准门槛、未见泛化或科学收益宣告；无合格标签、rank不足、验证退化全保留。

## 受控消费必须证明的后果

沿现有6维局部R³×SO(3)状态，仅使用H=[I3,0]和三维R。z=world representative−关联假设reference的世界平移−bias；reference为显式受控假设，不能在线偷接SDK真值。

从更新前Gaussian prior的Λ/η计算mu/Sigma，预测密度使用S=HΣHᵀ+R和完整三维normalizer/logdet；然后同一measurement进入rebuild_conditional_state，measurement.noise_covariance仍为R。information_weight固定1，location_mass/RLS贡献为0，避免另添责任度。旋转信息增量为0；相关prior可间接改变姿态后验，不能声称旋转后验永不改变。

受控实例关联、prior与未知分支明确标记；只消费一个预先声明的公开seed/证据簇，不堆乘相关seed。receipt必须是合法raw_observation_likelihood；旧posterior_projection_not_likelihood不可直接加非零观测项、不可关闭校验。证明固定其余项与q/integration时公开测量改变observation项、target log weight与归一化后验；同步核对Gaussian自然参数。随后纠正/撤回、原状态重放与落盘恢复应一致，重复来源不能重新计入。若实际动作没有变化，保留该结果，不改效用制造提升。

自然I→Z关联、未决/杂波和跨帧依赖、正式参考/朝向、自然相机结果分布仍未解决。受控consumer证明工程数值接线，不能宣称线上完整自然目标密度或闭环收益。

## 顺序与证据

实现/定向测试→冻结实际源码→顺序R1/R2对抗（完整合法路径、完整自签伪造、来源/模式/参考/训练分区、状态/账本与后验后果）→实际固定96帧运行及新进程完整fresh→独立数值复核→原件封存/报告/草稿PR。任何功能修复重新冻结并使旧审查过期。A辅助不是B独立/全仓CI。工程失败不覆盖、不删除，输出output/soft-position-factor-20261001。

## 实现前的坐标及受控先验补充

公开 domain_id 固定为 `unity-rgbd-world-m-fixed-grid@1`，指传感器/米制世界坐标约定；每个 scene_sha 继续绑定于输入/测量身份，不作为共享残差模型 domain_id。frame_id 保留 camera.world_frame，valid_at 保留公开捕获时间。

受控消费固定 known 的初始六维 mean=0、covariance=I6，显式 reference world translation=0；unknown candidate 与 aggregate unresolved 使用相同世界三维 Gaussian(mean=0,covariance=100I3) 作为开发背景密度，从而所有分支比较使用相同量纲。两个 candidate 与 aggregate 初始未归一化权重均为1；这些为预先明示的测试/诊断条件，不是学习到的自然未知模型。后续步骤继承真实 parent posterior 和 aggregate unresolved 权重，不重置为1。只在预先绑定的 semantic metadata.record_id 上消费固定公开seed，其余步骤只附加零信息的谱系记录；撤回该semantic record后不能把保留的RGB-D移接到其他步骤。诊断和native fixture使用同样的假设，无效公共观测及拟合失败不得根据标签换seed。

原生受控测试中的 P5 CIAV closure 会生成新的 after record ID，因此配置锚点保留原输入 metadata.record_id；只有明确 `structure-two-adaptive-ciav-feedback-closure` 来源类型允许它匹配 native.transition.before.metadata.record_id。普通来源必须匹配 native.after.metadata.record_id。消费诊断同时保存原配置ID及实际native before/after ID，撤回测试精确定位实际published after所对应的事件修订，不宽泛匹配历史中出现过的ID。

## 初版审核阻断后的消费验证修复

初版493e057在728项定向回归及首轮审核后，第二轮发现完整raw LL与aggregate数值替换可保留原model/binding/q并被发布；该版未进入真实96帧实验。原失败与合法后果保留在ATTEMPT_1报告。修复后须新SHA及重新顺序两轮审核，旧首轮不能授权新版本。

新增的是受控位置profile的工程数值核验：canonical producer移至src，tools原入口兼容重导出；原owner固定producer配置、模型/pin、实现及verifier文件原pin，按真实已接收raw原件与cutoff登记context。消费端从固定配置和实际祖先source/prior独立重建完整base，比较所有LL、aggregate、prior/transition/constraints、RB统计、support/cluster/source。重建使用隔离的新producer，已消费测量依据实际祖先来源推导，不相信proof自报pre-state，也不改变线上producer的calls/consumedkeys。

受保护profile由owner配置固定；缺proof、删catalogue、改profile/未来cutoff不能降级为只查q。当前、历史、replay和SQLite路径均复用深层核验。独立新进程测试必须读原持久化configuration/models，不能重新随机生成另一个rawpacket后声称恢复失败。helper实际原文件pin在已锚定的consumer中核对，loaded函数与源代码也核对；这是有界本机实现完整性，不是任意Python内存攻击隔离。

既有未启用该profile的显式fixture保留原合同；本修复不证明任意legacy候选模型的自然likelihood。位置模型科学定义、两参考/两估计器、96帧固定分区、未知先验与所有公开采样规则保持。新相机结果独立于semantic source的事务/replay仍是下一轮，不能把本次owner原件登记误写为多capture实时更新已完成。


## 下一轮只读输入准备（不算本轮Native实数据运行）

公开选择协议已固定并核对：frame ordinal→candidate(method,id)→canonical 8×8 pixel顺序的首个public-valid seed；原第000帧SSDLite候选de8a15ab-6a24-503c-87e3-f3dbd7646311、seed[21,33]，完整64点公开有效。此框很宽，其几何读出仍是表面代表点，不能由框或seed赋自然身份/对象中心。原raw字节、scope/时间/UUID/位姿/回执不修改；后续受控语义时间由原delivery与三通道capture/arrival最大值+1秒确定。外pin与原件清单见ARCHIVE_BRIDGE_PUBLIC_SELECTION_PREPARATION.json（SHA256 0d1a0e2241acb0e41fd93da1896288fc217551162d651ae16ef1b88e893f1538）。未用私有label、检测类别或分数选择，未载入模型/执行Native；此准备不替代下一轮源码冻结、两审、完整soft neighborhood对应和实际执行。
