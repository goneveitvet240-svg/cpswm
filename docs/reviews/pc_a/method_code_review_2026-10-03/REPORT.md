# 已发表方法、官方代码与 CPSWM S1 失败对照

核查日期：2026-10-03。结论针对 **S1 实际执行的自然表面观察支路**，不把它等同于整个 CPSWM 的全部模块。

目前主要差距是：我们接通了观察事务，却尚未接通足够强的持续对象估计和观察决策。别人可供借鉴的是对象新增、重识别、多视图对象表示、可供检索的历史和任务相关探索；不是“加一个更大的模型就成功”。同时，双方任务、输入权限和评分不同，不能直接用论文成功率给我们的 AABB 任务排名。

## 证据与版本

- 我方被审版本：`1c21e4eb4fb998a8fcdc334bb727441052aea4b3`，S1 执行版本 `747ea0187a6a03c4decaa2d3ad05e000a31f1dca`，生产实现内容保持 `745613ef0b804b5da4d1d2afcbba56fd9f78925c`。结果来自[冻结 S1 报告](../system_experiments_s1_2026-10-02/REPORT.md)、主评分和逐帧诊断；本轮没有重新运行仿真。
- 检索范围、关键词和来源缺口见 [SEARCH_PLAN.md](SEARCH_PLAN.md)。核查原文的方法、实验与限制，以及下列官方代码；**没有复现对方论文成功率**，不是穷尽性综述。
- 外部源码按 GitHub 完整 commit SHA 固定，下载内容与官方 Git blob 哈希逐文件核对，见 [SOURCES.json](SOURCES.json)。本仓库仅保存分析与索引，不重新分发外部完整源码/论文。
- 本轮只有文档变化；生产实现、科学指标、先验和完整统一研究范围不变。独立电脑 B 验收仍待执行。

| 对照系统 | 已读官方代码版本 | 核查范围与缺口 |
|---|---|---|
| ConceptGraphs | `93277a02bd89171f8121e84203121cf7af9ebb5d` | 对象建图主循环、关联、点云和特征合并；未实跑 |
| 3D-Mem | `f445e0828a2c5d5845ccdbd0992fc5eed871d19a` | GOAT-Bench 驱动、查询输入、对象更新、导航与配置；未实跑 |
| GOAT / HomeRobot | `ede6a67a2d0c0c8e12ad3b9726f330cea6cf90f5` | 作者项目链接的 HomeRobot 实例记忆实现；未确认它等同于论文完整机器人发布版本 |
| Where Did I Leave My Glasses? | `70285b23f3525b2b4601209cbed997eee938696a` | 官方发布覆盖 IV-A/B/C 感知、场景信念、探索优先图；README 未把 IV-D 完整规划控制列入发布范围 |

## 别人有哪些已经实现的成功机制

### 1. ConceptGraphs：持续建立对象地图，而非只延长首帧轨迹

官方 `cfslam_pipeline_batch.py:261–298` 每帧计算空间与视觉相似度、阈值过滤后关联；`mapping.py:83–102` 将不匹配检测新增为对象，将匹配检测并入现有对象。`utils.py:61–108,153–164,178–219` 从掩码有效深度形成点云、下采样/去噪、合并点云并累积视觉描述。对象有持续几何与语义表示，不要求所有对象在第一帧出现。[官方关联代码](https://github.com/concept-graphs/concept-graphs/blob/93277a02bd89171f8121e84203121cf7af9ebb5d/conceptgraph/slam/mapping.py#L83)；[点云代码](https://github.com/concept-graphs/concept-graphs/blob/93277a02bd89171f8121e84203121cf7af9ebb5d/conceptgraph/slam/utils.py#L61)。

这是我们的对象层基线候选，不是完整主动观察基线。论文也报告小/薄对象漏检、重复对象和描述错误。尤其所读 `utils.py:93–94` 为避免共线加入标准差 4 mm 的随机点扰动，不能照搬到毫米边界敏感的精确表面点报告中。[论文方法、实验与限制](https://concept-graphs.github.io/assets/pdf/2023-ConceptGraphs.pdf)。

### 2. 3D-Mem：决策真正消费历史图像和可探索区域

`query_vlm_goatbench.py:20–112` 将对象裁剪、Memory Snapshots（记忆快照）、Frontier Snapshots（探索边界快照）和目标描述输入 VLM；输出选择记忆对象或探索区域。`run_goatbench_evaluation.py:307–400` 更新地图与快照，再选择导航点。这为“过去看到什么、下一步去哪里看”建立了实际信息通路。[查询代码](https://github.com/UMass-Embodied-AGI/3D-Mem/blob/f445e0828a2c5d5845ccdbd0992fc5eed871d19a/src/query_vlm_goatbench.py#L20)。

论文 GOAT-Bench 实验用 36 场景、278 子任务子集；GPT-4o 版本成功率 69.1%，清空记忆版本 58.6%，SPL 为 48.9/38.5。清空发生在每个后续子任务开始前。成功为最终位置距导航目标 1 m 内，不能与我们的三维表面点入盒率比较。[论文 §4.3](https://arxiv.org/html/2411.17735v2#S4.SS3)。

代码 `run_goatbench_evaluation.py:202–212` 确实清对象记忆并重建 TSDF；`scene_goatbench.py:171–192` 清对象/图像并用指定相机状态取图；`tsdf_planner.py:569–695` 按路径长度计算下一导航位置。配置还提供多朝向观测。因此不能把其一次高层 step 当作我们一次物理转动，迁移比较必须重新对齐动作/取图成本。未对其全工程做真值隔离审计，不宣称仅凭静态阅读完成公平性验收。

### 3. GOAT：后续任务真的有机会利用之前的探索

论文在 9 个真实住宅的 675 个目标上报告 83% 成功率，无记忆版本为 61%；目标之间保留地图与实例图像可以免去重复探索。它也使用 Mask R-CNN，因此现有证据不支持把我们的失败简单归于检测模型年份太旧。图像目标与语言目标采用不同匹配方式，语言细粒度属性仍是弱项。[RSS 论文](https://roboticsproceedings.org/rss20/p073.pdf)。

所读 HomeRobot `instance_map.py:437–470` 将新视图加入持续实例，缺少实例则创建；这支持其对象记忆机制，但不冒称已核实完整 GOAT 发布复现。论文的探索后选择最佳候选等策略也不能不加区分地用于我们允许 UNKNOWN 的任务。[实例记忆代码](https://github.com/facebookresearch/home-robot/blob/ede6a67a2d0c0c8e12ad3b9726f330cea6cf90f5/src/home_robot/home_robot/mapping/instance/instance_map.py#L437)。

### 4. Where Did I Leave My Glasses?：丢失可恢复，变化会影响探索

官方 `scene_belief.py:393–473` 先做不允许位移的关联，再尝试允许位移的关联，维护 missing 对象并重新识别；`object_tracker.py:185–197` 创建新对象，`matching.py:315–345` 有几何/语义门限和冲突处理。丢失不是不可逆终态。[场景更新代码](https://github.com/learnsyslab/perceive_semantix_release/blob/70285b23f3525b2b4601209cbed997eee938696a/perceive_semantix_lib/src/perceive_semantix_lib/core/scene_belief.py#L393)。

它承接 POCD（概率对象变化检测，RSS 2022）与 POV-SLAM（RSS 2023）的研究链，将对象静止信念和查询相关性用于探索优先图。60 个仿真任务中，Known/Novel/Moved 成功率分别 65%/45%/50%；每任务先建图 15 分钟，再搜索 5 分钟，以报告找到且距离 1.5 m 内判成功。它也没有解决所有失败。[论文方法、表 I 与参考文献 8/9](https://arxiv.org/html/2509.19851v2)。

不能直接复制其先验：`object_tracker.py:265–305` 明确通过合成变化使长期未观察对象的静止信念衰减。这是模型设计，不是实际观测到移动。迁移到 CPSWM 必须区分自然证据与预测先验，不能混写证据账本。[衰减代码](https://github.com/learnsyslab/perceive_semantix_release/blob/70285b23f3525b2b4601209cbed997eee938696a/perceive_semantix_lib/src/perceive_semantix_lib/core/object_tracker.py#L265)。

## 我们为什么失败：可以定位的五条链路

以下源码位置均绑定上述我方被审版本。

| 失败环节 | 代码事实 | S1 对应现象 | 能得出的结论 |
|---|---|---|---|
| 首次漏检不能补救 | `mask_surface_sequence.py:76–83` 仅 index=0 创建轨迹；`surface_episode.py:337–348` 只从首帧检测解析查询 | 25°碗首帧未解析，之后有检测仍 unknown | 当前查询和轨迹出生机制把首帧能力变成上限；不能把后来的同类对象随意换成原目标 |
| 光流失效不可恢复 | `visual_target_tracking.py:147–152` 的 lost 包含此前 `_lost`，没有重识别入口 | 35°后续瓶子 LOST_NO_REINITIALIZATION | 缺少有证据、可拒绝的恢复机制；“不强制匹配”不等于“永不重新识别” |
| 主动策略状态不足 | `surface_action_model.py:17–18` 仅 hash(category, ordinal, status)；`surface_episode.py:135–179` 查动作频率并比较净收益 | 三个角度给出相同预测，均第一动作后停止 | 来源绑定哈希不代表策略消费了几何/遮挡/视角信息；本批无新视角澄清证据 |
| 记忆未形成有用的位置更新 | `mask_surface_support.py:160–176` 返回 neutral、log_ratio=0、position_information_added=False；`surface_episode.py:333,357–368` 只报告最后有效帧点 | 保留与撤回中间观察均 5/9 | 账本能保存与重放，不等于对象位置估计或后续任务会受益；这也不是全系统没有记忆 |
| 几何读出脆弱 | `natural_mask_surface.py:84–95` 从有效支持点中选一个掩码概率最高像素，再反投影 | 15 个有报告碗观测均在高度方向出盒约 1.561–2.066 mm | 分割置信度不是几何精度；误差根因未确定，不能凭观察擅自改投影、加偏置或放宽 AABB |

对应源码：[序列](../../../../src/cpswm/perception_mapping/mask_surface_sequence.py)、[光流](../../../../src/cpswm/perception_mapping/visual_target_tracking.py)、[报告与策略](../../../../src/cpswm/system/surface_episode.py)、[动作模型](../../../../src/cpswm/perception_mapping/surface_action_model.py)、[表面更新](../../../../src/cpswm/system/mask_surface_support.py)、[点读出](../../../../src/cpswm/perception_mapping/natural_mask_surface.py)。

主动策略的停止可以直接解释：三个设置 Stop 预测均为 2/3，右转 1°仍 2/3，再减动作成本 0.0001 后净收益为负；右转 5°预测更低。结果 active 6/9 对 fixed 5/9，来自避免后续丢失一次瓶子，不能证明找到了更好的观察角度。状态缺失的影响范围是代码推断，还需要配对消融确认，不能预报换成 VLM 就会成功。

几何方面应分别检查深度定义、像素中心/内参约定、姿态变换、所选像素深度及真值盒与可见网格的一致性。别人的投影公式与我们的 +0.5 不同，并不足以证明我们有半像素错误；不同渲染器可能使用不同约定。应使用独立已知几何校验，不用失败目标真值倒推“正确偏置”。

现有 `tools/surface_pipeline_fixture.py:1–35` 仍依赖受控语义 bootstrap/fixture_models。自然 RGB-D 链路已经运行，但完整自然人物、事件与七算子联合推断不能由这个局部实验代证。

## 为什么当前实验不能充分说明记忆价值

当前 memory-reset 只撤回第二次观察，保留第一次参考，两臂第三次看同一画面并执行同一任务。它检验中间证据的增量作用和撤回一致性，**不等于完整记忆与无记忆对比，也没有检验不同的后续目标**。GOAT/3D-Mem 的收益则来自前面任务探索过的环境在后面任务中继续可用。

此外 no-update 的 0/9 因有效视觉状态/参考被关闭，不是一个仍可消费当前帧的强无记忆方法。该结果能证明此接口的依赖关系，不能证明 CPSWM 胜过合理无记忆基线。首批只有单屋三个相关视角，无跨场景泛化或统计显著性结论。

## 推进次序与最小可证伪比较（建议，尚未改协议）

1. **先使同一目标有持续可用的自然对象表示。** 对同一 RGB-D 流比较当前首帧光流支路与阈值门控的对象地图基线，检查新对象进入、短时丢失与重识别；保留拒识、候选歧义和完整关联证据。原首帧目标不能通过后来随意重命名绕过；如何给晚出现目标定义公开任务引用需要明确协议。
2. **独立校验几何，再改位置融合。** 沿用已批准严格 AABB 评分，先定位已有毫米误差。对象点云表示可借鉴，表面点不能直接作为中心高斯的独立测量；重复帧去重和事务撤回保障应保留。
3. **设置真正能用历史的后续任务，并提供强无记忆对照。** 当前帧对照仍有相同感知器/公开输入权限；记忆臂用前任务历史，reset 臂在后任务边界清历史。先从静态后续目标/遮挡复查检验，再扩展移动与过时记忆；这些是完整范围中的分阶段测试，非删除动态、多人物或隐藏事件。
4. **在同动作预算下检验观察选择。** 对齐初始世界、任务、检测器、RGB-D/位姿权限、物理动作及取图成本；比较固定策略、合理简单探索和对象/视图信息驱动策略。控制 Stop-only 效应，分别报告“早停保住结果”和“新增观察带来澄清”，主指标仍用已批准的身份＋位置成功。新辅助指标/先验/科学协议由用户决定。
5. **优先做最邻近方法的同条件检验，再扩大工程建设。** ConceptGraphs 适合对象层对照；3D-Mem 适合记忆与探索对照；眼镜论文适合半静态信念与主动复查对照。各自开发集公平调整，冻结后评估；不复制其不同任务的阈值、动作单位、合成证据或最优猜测当我们的成功。

从研究贡献看，“对象记忆＋过时变化信念＋主动复查”已经存在，不能再把组合本身作为新颖性。完整 CPSWM 的可逆归因、撤回重放、隐藏事件与多人因素仍可作为待检验差异，但必须证明这些差异在可靠对象层之上改善实际任务。**建议暂停为现有弱策略扩充大规模重复矩阵及论文级成功叙事，先做最强邻近基线的最小配对效用检验。** 若公平对照后差异不能影响成功/动作代价，需要重新评估方法贡献；本报告不替用户作停止或转向决定，也尚未执行这项邻近基线实验。

## 交付核验

本轮验证外部选定源码与官方 tree 中 blob SHA 一致、我方 src/tests/tools 相对 base 无变化、文档本地链接存在、`git diff --check`。文档审查未运行生产回归，不冒用此前通过数量。本轮无新模型训练、收费 API 推理、仿真成功率或第三方完整复现结果。
