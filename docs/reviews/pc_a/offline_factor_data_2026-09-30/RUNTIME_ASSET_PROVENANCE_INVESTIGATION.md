# 固定 AI2-THOR 版本的资产来源与位置语义调查

结论：**本批空 assetId 全部具有固定引擎源码可解释的来源；可以实现严格的来源解析，区分程序建筑、已知 prefab 子部件与真正未知资产。不能直接删除 unknown 门禁，也不能把解析后的子部件自动变成训练目标。** 同时，当前把源 house 的 position 与 SDK transform.position 直接比较并解释为初始化运动，是字段语义错误，应先修正语义。

本调查只读 `collection-attempt01`，未修改其原件、仓库代码、训练模型或监督资格。调查输出不是新的采集验收结论，不能抹掉首批十二屋因高度契约不适用而被拒绝的记录。

## 来源与固定版本

- 官方引擎版本：`allenai/ai2thor`，commit `f0825767cd50d69f666c7f282e54abfe58f1e917`。
- 从官方 raw.githubusercontent.com 固定提交下载五个原文件，保存于 `pinned-engine-source-f0825767/`；`sources.json` 记录 URL、字节数和 SHA256。
- `ProceduralTools.cs` SHA256：`877589b9ed6b7dba31aa860d1dc8469e7ff0f415d1a3cdf29582d936212dc877`。
- `BaseFPSAgentController.cs` SHA256：`4d6109b05132bb93a58241c12b53b7c41f56adcf73e33e57665e43015583520b`。
- `SimObjPhysics.cs` SHA256：`536145dfb36495a2eee72ae94f032e7f77d80765176f85706f026550e9585a60`。
- 下列行号均来自下载原文件的实际 `nl -ba`，不是网页解析器压缩空行后的行号。

## 空 assetId 的语义

`SimObjPhysics.assetID` 的默认值为空串；SDK 元数据直接复制该属性，而不会自动从 transform 父对象补齐资产身份。因此空字段并不自动意味着又加载了一个身份未知的独立库资产。[默认值](https://github.com/allenai/ai2thor/blob/f0825767cd50d69f666c7f282e54abfe58f1e917/unity/Assets/Scripts/SimObjPhysics.cs#L21)、[SDK 元数据赋值](https://github.com/allenai/ai2thor/blob/f0825767cd50d69f666c7f282e54abfe58f1e917/unity/Assets/Scripts/BaseFPSAgentController.cs#L1698-L1700)。

创建一个源 house 对象时，生成器按其 assetId 查 prefab，实例化根对象，只向根 SimObj 写入 assetID；随后枚举实际 prefab 层级的 SimObj，跳过根，按从零递增的编号产生 `源根ID___编号`。这是该版本明确实现的 ID 生成契约，不是根据英文名称猜测家具关系。[根资产赋值](https://github.com/allenai/ai2thor/blob/f0825767cd50d69f666c7f282e54abfe58f1e917/unity/Assets/Scripts/ProceduralTools.cs#L1743-L1749)、[子部件编号](https://github.com/allenai/ai2thor/blob/f0825767cd50d69f666c7f282e54abfe58f1e917/unity/Assets/Scripts/ProceduralTools.cs#L1786-L1794)。

这里必须区分两种“子”：house JSON 中的 `children` 会递归独立生成源对象；prefab 自带的抽屉、架板等才使用上述编号。二者不能混为同一个父子标签。[源对象递归](https://github.com/allenai/ai2thor/blob/f0825767cd50d69f666c7f282e54abfe58f1e917/unity/Assets/Scripts/ProceduralTools.cs#L1522-L1535)。

程序墙体保留源 wall.id，并创建 Wall 类型的 SimObj。每个房间按其 floorPolygon 生成地板，并使用 room.id 创建 Floor 类型的 SimObj；另有全屋地板根，其 ID 为非空 house.id，否则使用默认 Floor。它们由源几何生成，不能为方便分区而虚构独立 prefab assetId。[墙体 ID](https://github.com/allenai/ai2thor/blob/f0825767cd50d69f666c7f282e54abfe58f1e917/unity/Assets/Scripts/ProceduralTools.cs#L1020-L1028)、[墙体类型](https://github.com/allenai/ai2thor/blob/f0825767cd50d69f666c7f282e54abfe58f1e917/unity/Assets/Scripts/ProceduralTools.cs#L862-L888)、[房间地板](https://github.com/allenai/ai2thor/blob/f0825767cd50d69f666c7f282e54abfe58f1e917/unity/Assets/Scripts/ProceduralTools.cs#L1219-L1264)、[地板根](https://github.com/allenai/ai2thor/blob/f0825767cd50d69f666c7f282e54abfe58f1e917/unity/Assets/Scripts/ProceduralTools.cs#L1192-L1217)。

## 首批实际目录核对

逐屋检查原始 house 与全部十二个 SDK event，结果保存在 `RUNTIME_ASSET_PROVENANCE_COUNTS.json`，每个空资产实例均有记录。

| 空资产来源 | 唯一 house/object 实例数 | 匹配证据 |
| --- | ---: | --- |
| 程序墙体 | 358 | 源 walls 中精确 ID，SDK 类型 Wall |
| 房间地板 | 45 | 源 rooms 中精确 ID，SDK 类型 Floor |
| 全屋地板根 | 12 | 本批 house 无非空自定义 ID，符合默认 Floor；SDK 类型 Floor |
| prefab 自带部件 | 179 | 唯一源父 ID、父 SDK assetId 与源 assetId 一致，子 ID 符合固定生成契约 |
| 未解释项 | **0** | 本批观察结果，不能泛化为以后永远没有未知项 |

共 594 个空资产实例；SDK 总实例数为 1618。空字段的 SDK 类型分别为 Wall 358、Floor 57、Shelf 88、Drawer 75、SinkBasin 10、DiningTable 6。类型名不承担来源识别作用，例如某个 TVStand 子部件的 SDK 类型是 DiningTable。

179 个部件属于 52 个源 prefab 根；每组编号均完整覆盖 0 至 n−1；源显式对象 ID 均不与 `___` 命名空间冲突；所有房屋的十二个 SDK event 中 `(objectId, assetId, objectType)` 目录保持一致。另有 78 个有明确 assetId 的门／窗等非 objects 项，原始全 house 资产遍历已经能够纳入它们；不能仅遍历 objects 忽略这些资产。

元数据 `parentReceptacles` 不是 prefab 结构父指针。本批抽屉等经常只列出 Floor；不得用它替代生成契约或父源实例绑定。

## 能否解除全局 unknown gate

**工程上可行，但须以“来源已解析”替代“字段非空”的判定，而非豁免某些名称。** 适合当前固定版本的最低约束为：

1. 引擎、worker、原始完整 house 和动作序列保持可信 pin；所有事件完整登记，解析结果不能反过来改变在线输入。
2. 程序建筑只认精确源记录和预期类型，记录源 JSON 指针、几何／材质描述及引擎版本；它们不是新增可监督 prefab 目标，也不生成假的 assetId。
3. 子部件只在父源实例唯一、父 SDK 资产匹配、命名空间无冲突、编号合法且完整、全事件目录一致时，将其**资产曝光来源**归于已有父 prefab。保留原始空 assetId 与派生来源字段，不能覆盖原件。
4. 子部件、程序建筑仍不因为来源解析成功就取得实例训练／位置校准目标资格。无法满足契约的任何项仍是真正未知，继续关闭全局资产曝光完整性。
5. 保持所有上下文资产参与跨分区曝光；不能只删除标签来隐藏训练 RGB 中的已见资产。
6. 增加完整伪造测试：伪装 wall／room、不存在父根、错误父资产、编号空洞、额外／缺失子部件、源命名空间冲突、改类型、跨事件变化，以及通过已解析上下文偷授目标资格。

上述推论证明的是该固定引擎和固定源下的**根 prefab assetId 级来源解释**，不是每个子部件独立语义身份或几何签名。没有读取每个实际 prefab 子层级清单，不能声称编号本身证明了子部件的具体名称、尺寸或独立校准真值；不同 assetId 是否复用网格／纹理也不在当前 assetId 隔离保证之内。同机整套原件一起伪造的外部真实性问题仍未解决。

## 源 position 与 SDK position 不是同一参考点

SDK `metadata.objects[].position` 取对象 `transform.position`，即变换原点；AABB 的 center 是另一字段。[元数据位置](https://github.com/allenai/ai2thor/blob/f0825767cd50d69f666c7f282e54abfe58f1e917/unity/Assets/Scripts/BaseFPSAgentController.cs#L1608-L1612)、[AABB 输出](https://github.com/allenai/ai2thor/blob/f0825767cd50d69f666c7f282e54abfe58f1e917/unity/Assets/Scripts/BaseFPSAgentController.cs#L1714)。

源 house 的对象生成明确启用 `positionBoundingBoxCenter`。引擎先取实例当前 AABB 的中心，再根据源旋转和源 position 计算新的 transform 原点；因此源 position 是该放置算法的中心参数，不能当作 transform 原点。[调用参数](https://github.com/allenai/ai2thor/blob/f0825767cd50d69f666c7f282e54abfe58f1e917/unity/Assets/Scripts/ProceduralTools.cs#L1629-L1652)、[变换公式](https://github.com/allenai/ai2thor/blob/f0825767cd50d69f666c7f282e54abfe58f1e917/unity/Assets/Scripts/ProceduralTools.cs#L1730-L1737)。

生成时的 AABB 也不能无条件等同于最终事件的 AABB：该实现会依姿态和部分状态更新包围盒，从有效非 trigger collider 与 visibility points 汇总，计算时还临时分离其他子 SimObj。[缓存条件](https://github.com/allenai/ai2thor/blob/f0825767cd50d69f666c7f282e54abfe58f1e917/unity/Assets/Scripts/SimObjPhysics.cs#L179-L227)、[包围盒构造](https://github.com/allenai/ai2thor/blob/f0825767cd50d69f666c7f282e54abfe58f1e917/unity/Assets/Scripts/SimObjPhysics.cs#L230-L314)。

本批 946 个源对象均能按 ID 匹配 SDK；源 position 到 SDK transform 原点**没有一个**在 1 mm 内。改成与 SDK 最初事件 AABB center 比较，也只有 345/946 在 1 mm 内；最大差约 0.75414 m，来自 house 8 的 `Pillow|6|0|1`。这些差值混合了参考点、姿态／包围盒和初始化状态差异，本调查没有逐物体因果分解，不能全称为物理运动，也不能全称为噪声。

应保留三种字段：源放置参数、SDK transform 原点、同事件 AABB 中心。源→SDK 跨语义残差应标记为诊断量，不能用直接相等门禁误杀全部对象；同时不能把原门禁直接删除后改称“源位姿已经验真”。若需要复算源放置结果，需补齐生成时 prefab 参考变换／边界数据并按固定公式重建。已有 SDK event0→Pause 及 Pause 后同定义位置／姿态稳定检查仍应保留。

## 相机初始高度差的来源

生成器实际读 `metadata.agentPoses[agentMode]`，设置给定位置后调用 CharacterController 的重力移动，再设置方向／horizon／standing。因此源高度不是 CreateHouse 结束后的强制精确高度。[固定实现](https://github.com/allenai/ai2thor/blob/f0825767cd50d69f666c7f282e54abfe58f1e917/unity/Assets/Scripts/ProceduralTools.cs#L1476-L1518)。本批十二屋 `metadata.agent` 与 `agentPoses.default` 逐值一致；以后不能默认它们总是等价。

这支持明确记录源→SDK 初始高度差，并用实际 event0 相机／agent 位置约束后续纯旋转不平移的修复方向。源码并不承诺所有地形都恰好产生 −4.9000 cm，因此不能把这一批的差值硬编码成普遍规律。

## 交付边界

调查已给出固定源码、实际目录映射及明确限制；没有修改门禁实现。来源解析与位置语义修复仍须代码实现、两轮顺序对抗审查和 fresh 固定矩阵采集。首次失败批次应保留为协议适用性诊断，不追改为成功训练数据。
