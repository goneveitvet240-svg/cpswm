# 真实归档 Native 桥接与裸采样点对照：运行前协议

父轮草稿PR78，功能源码1bd6c204d349024196c23df12cca61dbcea91e6c（895 Python），交付df8e30b；完整case ledger外部pin9b9ed2d9208c1907d8295d5edc5aeb2f48af7b9b3625108b9642430a06780efc。父run324.36s/fresh326.64s、302产物完全相同，独立算术通过。新分支codex/pc-a-archive-native-bridge-20261001，父doc合入ced6aa1439b2cd23018042e0c6453300c74d8390；后续实际功能SHA另冻结。

本轮两个并行开发问题：实际训练残差模型是否真正进入Native目标权重与RB统计；在同一seed/标签/参考/分区下，邻域聚合相对于直接深度点的误差如何。后者是描述性对照，不由验证误差选择正式模型或阈值。先新源码两轮顺序对抗，再运行桥接与裸seed的实际run/fresh。分离输出路径可并行运行，两者输入只读、每次都使用原位置源码全量历史重训校验。没有新的Unity启动或检测器推理。

## 桥接

严格固定首个公开有效frame/candidate/seed，原12屋96帧顺序，candidate按method/id、像素按(u,v)。只读预检查确定frame000、house01/SDK004、SSDLite候选de8a15ab-6a24-503c-87e3-f3dbd7646311、seed[21,33]，64个完整支持点。此帧来自训练屋；不称held-out识别或任务成功。原RGB/depth/相机自身位姿、envelope/payload/UUID/采集回执/sampling/depthunit均不变，完整支持/系数映射重推，full和single候选集合导致的不同合法ID分别保留，不重写成相同ID。

原typed_factor_graph_transformer提议checkpoint仅作为历史工程载体，manifest外pin4f17225e73bf40b0aca9c996c1803dfc03918bfa5972a66a785be871417114f4；原三种提议备选保留，不按当前收益选型。原checkpoint为合成语义训练，不能称自然提议训练。Bridge只让BackboneProbe seed171的全部合成语义上下文适配真实scope/time；固定关联、reference原点0、known六维N(0,I)、unknown/aggregate世界N(0,100I3)、初始三分支等权都显式保留。未知模型/世界身份/正式先验未校准；极小known概率可由原点与实际世界坐标相距远造成，不能解释为识别正确率。

soft_affinity/uniform × SDK pivot/AABB四个成功拟合模型各比较active/no-factor两臂；fit_failed保留unavailable，不人工代入。一个capture只消费一次，无相关seed连乘。更新前预测LL、完整6D统计、原始log权重/显示权重、重复不增量、三步neutral继续、两次新进程SQLite恢复、撤回实际published after revision并replay到no-factor都核验。没有新owner发出的物理相机命令，use_owned_visual_context=False；原离线命令作为历史输入，不伪造成在线执行。

## 裸seed

单独schema和CLI，不修改原ESTIMATORS或把裸点伪装成uniform。沿每个原neighborhood的完整grid找到每个seed原world_points_m[index]，同UV不同完整grid仍按原seed保留，另报unique(action,u,v)。所有公开点先生成；仅原train 1–8屋唯一合格seed标签拟合bias/full3×3 ddof1 covariance，少于4、rank<3、非PD显式失败，不加epsilon。全部公开校正先于validation标签读取。两参考均保留。soft/uniform两个label必须除estimator外完全一致，每个seed计一次。96帧、VOID/无候选/无监督均保留。逐split/house/对象帧/对象/seed分母与父模型一致，强相关和曝光验证明确披露，不做p-value或正式赢家选择。

## 验收和边界

R1/R2由未参与本轮六个Python文件实现的A辅助审核人顺序执行；作者旧轮重合单列，不等于B独立。冻结后任何功能修改重启两审。真实运行再由外部SciPy logpdf/Kalman形式重算Native数值、独立残差矩和bare误差/分母校验；完整DB的authority/replay仍依实际恢复测试，不用算术脚本代替。记录源码、模型、父包、完整输出和命令外pin；不执行ledger中任意argv。复核在DB临时副本上恢复，保留原DB字节。

主线剩余：同一语义来源后续新raw观测尚缺逐观测事务/逐cluster重放；自然跨视角身份、正式位置参考/未知模型、朝向、长时程闭环和行动收益未关闭。完整H/R/I/C/Z/r/V、三RB块、七算子、原分类与主动澄清保持，不用本工程桥接代替自然闭环验收。
