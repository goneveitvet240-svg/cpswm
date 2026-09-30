# 下一轮：同帧软亲和度的自然视觉历史接口调查

只读调查绑定 PR76 源码 `ffcaa7b292c73201d799f6631688387409c21cb7`。这些是建议，尚未接线；没有运行训练或 Unity，也没有修改旧输出。

现有实际链：`ContinuousEvidenceInput._reconstruct_native_visual_source` → `owned_visual_support.reconstruct_visual_support` → `OwnedVisualFrame` → `NativeVisualSource.pixels` → `ProposalPixelObservation` → `NativeJointContext/proposal_view`。最小扩展位置是在同一个拥有者视觉支持中加入可选 affinity 数据，由已拥有的原始 RGB-D、公开框和显式固定的模型重新推理；不能另外接受调用方提交的分数缓存作为事实。

完整支持保留像素对、各候选来源、模型/输入绑定、有效性与未校准分数。它不授予世界实例 ID、聚类接受阈值、对象中心/朝向、观测似然或记忆写入权。若新增外部模型依赖，需接入构造绑定、`_persist` 句柄排除与 pin 保存、`resume` 显式重绑定、`_verify_native_visual_sources` 读前重算及 `particle_workspace._validate_neural_implementation` 的新增模块/别名检查；新类型应由正常运行时导入，测试 fresh-process StateCodec 注册。

两个接口限制必须明示：

1. 运行时目前每个 RGB 对应一个 VisualFrame；当前离线配对来自 Faster R-CNN 与 SSDLite 并集。单前端接线只可标为接口诊断；保持原双前端协议需要显式、可核验的公开候选来源 bundle，不能伪装成单个 model_id。
2. `typed_proposal_networks.leaves` 编码全部 JSON 叶，旧 `max_nodes=4096` 且禁止截断。单个 64 点框的 2016 对，仅坐标与分数已超过节点预算。完整支持进入历史并不等于已进入 proposal 网络；真实网络消费需要另行明确有界公开表示或专用编码，不能静默删对。

`replay_joint_posterior` 撤回受影响后验并建立新代，原始 action/delivery 保留；支持随历史与 cutoff 重算，旧代可复核。当前没有任意删除原始观测的 API，不能把重新评分说成已经撤销语义事实。相机刚体运动保持两点欧氏距离，因此不能要求每次转向都改变 affinity 值，也不能把同分数变成跨视角身份。

最小正路径与攻击测试锚点：`test_owned_rgbd_support` 的完整 owner/SQLite 恢复、完整几何伪造、重签 pose 替换和实现变更；`test_owned_visual_neural` 的实际输入消融、完整重签 context/q/receipts 伪造、source catalogue 在动作读出前重算、未来 cutoff、失败回滚、完整代际 replay、fresh-process 注册及相机移动关联边界。攻击后必须核对 workspace/账本/动作后果没有污染，随后合法输入仍可发布。若启用网络消费，应固定权重与候选做 affinity-only 消融，并保留精确枚举的目标密度不变断言。

仍属 fixture 的内容：`JointFixture` 的先验、观测似然和六维位姿测量；`DurableFixtureProducer/OracleProducer` 的语义事件；原 proposal checkpoint 的单样本两步诊断训练；相机策略里的手工 outcome likelihood。本轮特征组对照或下一轮公开支持接线，都不能据此宣称自然目标密度、完整前景 mask、跨视角身份或动作闭环收益已验证。
