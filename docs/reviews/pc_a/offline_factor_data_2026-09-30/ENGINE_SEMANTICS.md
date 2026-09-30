# 固定引擎语义核对与第二次完整采集计划

第一批使用 cd51415ced36b16f2e7ebcb743fdda5ca8a9b7ab：12个进程均退出0，保存96个公共帧和144个SDK事件，但初始agent高度与配置值不同，原核验记12项失败。该批及失败状态保持原件，不覆盖为通过。第二批仍尝试同一index1–12、同一8视角日程，不替换房屋、不按观测效果选视角。

官方固定引擎 f0825767cd50d69f666c7f282e54abfe58f1e917 源码已下载留SHA证据。不是通过放宽误差容差解决：

- [CreateHouse的agent重力移动](https://github.com/allenai/ai2thor/blob/f0825767cd50d69f666c7f282e54abfe58f1e917/unity/Assets/Scripts/ProceduralTools.cs#L1480-L1503)读取metadata.agentPoses.default并执行重力Move。新清单要求该实际字段与agent别名一致；保留请求y与SDK实际y的差，不再断言两者相等。实际公开自位姿用于几何，初始化xz/yaw/horizon以及后续全部位置和旋转日程仍核验。
- [预制体放置](https://github.com/allenai/ai2thor/blob/f0825767cd50d69f666c7f282e54abfe58f1e917/unity/Assets/Scripts/ProceduralTools.cs#L1629-L1652)使用positionBoundingBoxCenter；[变换计算](https://github.com/allenai/ai2thor/blob/f0825767cd50d69f666c7f282e54abfe58f1e917/unity/Assets/Scripts/ProceduralTools.cs#L1730-L1737)说明source placement与SDK transform pivot是不同参照点。仍同时记录放置参数、实际pivot和实际AABB中心，距离仅作描述；不将它称为运动或校准噪声，不自动选择正式训练位置目标。物体运动只比较同一种SDK字段跨事件变化。
- [子部件ID生成规则](https://github.com/allenai/ai2thor/blob/f0825767cd50d69f666c7f282e54abfe58f1e917/unity/Assets/Scripts/ProceduralTools.cs#L1786-L1794)结合已匹配的source/SDK父资产解释预制体子部件。墙与地板必须绑定原房屋的完整有效建筑字段与确切ID/type，未知仍保留。解析结果只说明资产曝光来源；不修改原assetId，也不把部件或建筑变成监督目标。

本轮原始1618个SDK实例含946个源对象、78个额外带assetId实例、594个空assetId实例。空字段可解释为358个墙、45个房间地板、12个全屋地板和179个父预制体组件。所有原始缺失字段仍单列。源实例资格还必须经过训练/验证/旧场景资产隔离与运行时检查。

归档结构重验不是外部真实性证明。CLI重验现在必须提供外部记录的inventory SHA256；低层不带pin的接口仅保留用于结构攻击检查。若SDK真值和全部证据同时被重写并替换可信外部pin，单机档案不能提供独立验真。B验收及自然模型/任务收益仍未完成。

本轮不改变在线RGB-D/自位姿白名单、原先验、任务效用、正式阈值或完整七算子/三个RB blocks。源参考位置语义尚未对应到正式学习目标，数据入口不等于模型训练、自然观测因子或闭环收益。
