# 主线接线约束核对

来源：PR73 head 5a2a963d7f3b9fc8c3084e0b50d1696b2a7314f2 的只读代码追踪；A辅助子任务，未使用私有标签训练。不是自然模型完成证明。

1. 用户已选择 C（位置＋朝向），见 pose_local_dev_2026-09-13/REPORT.md。structure_two_pose.py 使用世界系米制平移与参考对象局部旋转向量。当前未定义对象位置对应SDK pivot或AABB中心，不能把坐标系选择当成参考点已选择。
2. pose_observation_model.py / fit_pose_observation_model.py 已有6D bias+完整协方差拟合及可撤回历史，要求真实6D观测/标签、同chart、足够样本和满秩。本批只有框表面点，没有朝向观测，不能填0或单位噪声凑6D。
3. structure_two_conditional_updates.py 支持矩形H，可用三维观测H=[I3,0]更新六维状态，并保留朝向未观测；它只提供算术，尚须对象/参考点/时间/坐标系/模型/协方差的来源绑定。
4. 两前端沿用各自固定Torchvision COCO_V1词表，无既定COCO→THOR objectType映射。measurements()保留全类别；decode()才归约apple有/无。本轮只调用measurements()。
5. proposal_perception.py 的pixel_causal_readouts遇相机几何变化重置局部IoU associator。本批每次45度转动均不能直接继承局部track作为跨视角实例证据。
6. 真正模型接线点为NativeJointContext.visual_source、NativeJointProducer.produce()及ParticleRevisionReceipt.observation_log_likelihood。run_history_action_loop.py当前仍用OpenWorldJointFixture；改变神经proposal q不等于替代目标密度。

本轮顺序：全部公开推理→全部候选×实例私有诊断→按固定训练/验证与房屋分组报告→根据自然候选前景/混合/跨视角覆盖决定工程缺口。标签用途已批准，不重复询问。正式对象参考点与新成功阈值不能被本诊断隐式决定。
