# 学习对象映射、同前端记忆对照与观测驱动修正

本轮推进用户指定的三个流程：接入外部对象特征/跨视角关联；固定前端比较普通记忆与 CPSWM；根据观测修正并复测。独立分支 `codex/pc-a-object-memory-integration-20261010`，base `2b99bbd53bfdb622f171eca9572b58e8df67e6a6`，[草稿 PR103](https://github.com/goneveitvet240-svg/cpswm/pull/103) 堆叠 PR102，不自动合并。

核心实现先冻结于 `290f629531daa75b3f21939b60f018f83d5d778c`；历史边界修复与最终生产源文件为 `d3e1d448261f0fef456aab4db32277cec6e6b938`；对照驱动的 JSON 规范比较修复为 `9480c489a22036e1980a813eb83b28b5149d8c1f`。各输出的 `code_sha` 包含当时的文档提交，实际感知/owner源文件相同。来源与模型见 [SOURCES.json](SOURCES.json)、[MODEL.json](MODEL.json)，过程失败与调整见 [ADJUSTMENT.md](ADJUSTMENT.md)。

## 结果与含义

原三帧三查询保持同输入、同查询、同预算和严格身份＋未扩张 AABB。下面是9个相关槽，并非9个独立实验；不估计显著性。

|方案|身份|位置|联合|固定初始身份的额外轨迹联合诊断|
|---|---:|---:|---:|---:|
|当前参考特征系统|7/9|6/9|6/9|10/15|
|CG组件对象地图（IoU＋ViT-H-14）|7/9|6/9|6/9|7/15|
|CG地图＋参考特征读点 hybrid|7/9|6/9|6/9|10/15|

纯地图在一个混合掩码中把原参考水壶点替换成台面点。用同candidate中的原特征支持读点修正后恢复当前水平，但没有原查询净收益。额外轨迹的身份固定来自**当前系统首帧像素**，不能让每个方法按自己的首帧点重新定义身份；否则纯CG会得到误导性的10/15。该额外诊断不替代原9槽门槛。

历史16帧来自同一屋、两个以前已经开发过的采集，不是盲测，也不是跨场景泛化。缺少实例mask，只能对旧的首帧2D框参考对象做几何命中检查，不能报身份/联合任务成功。

|历史检查|当前系统|CG组件对象地图|hybrid|
|---|---:|---:|---:|
|1°序列，11帧×5条初始轨迹|28/55|37/55|33/55|
|5°序列，5帧×5条初始轨迹|11/25|14/25|14/25|
|合计，参考AABB内|39/80|51/80|47/80|

变化主要来自台面的持续读出；WineBottle几何命中为当前14/16、CG与hybrid15/16。Bowl仍三者0/16。hybrid在1°台面记录低于纯CG；没有隐藏此代价，也不依据历史分数继续调参。宽大mask内的实体绑定、碗表面点和自然事件/动态场景仍是未解决问题。

机器结果：[summary.json](evidence/summary.json)。独立算术脚本仅依赖stdlib/numpy，复核27查询、45初始轨迹和240历史几何记录，共312条一致；它使用相同annotation，不是第二感知实现或B独立验收。

## 已接入的实际边界

- 固定 [ConceptGraphs源码](https://github.com/concept-graphs/concept-graphs/tree/93277a02bd89171f8121e84203121cf7af9ebb5d) 的13个官方函数/类，函数体逐字散列核对、保留MIT许可；原OpenCLIP **ViT-H-14 / laion2b_s32b_b79k**、20px框padding、归一化image/text特征、点云去噪/下采样、IoU与视觉相似度相加、原贪心匹配和对象融合真实运行。
- 固定原Mask R-CNN检测器以隔离关联模块；Unity RGB-D和授权理想相机自身位姿投影，无目标GT输入、无作者4mm随机点云抖动。初始参数见PLAN。worker运行Python3.11/Open3D，owner运行Python3.13；未替换原运行环境。
- 新 `object_frontend` opt-in进入已有 `MaskSurfaceSupportProducer`，默认路径保留；raw capture由实际owner记录并重算。持续表面支持仍是相关支持集合，`log_ratio=0`、不虚构独立物体中心精度或已校准身份似然。
- 同前端普通基线保留完整原始历史，收到相同撤回信息后完整重建；不是no-update弱对照。比较有效前端完整规范JSON与报告，仅排除owner额外的审计计数和报告view hash。元组/列表差异属于JSON持久化容器变化，不能误判为语义不一致。
- 当前视角未观察到的map对象仍在map内保留历史，但报告不把旧点标成当前观测。后出生对象不会取得首帧query权限。

这属于 **ConceptGraphs核心组件适配**，未复现Grounded-SAM/SAM全前端、LLM关系图、导航策略和作者整套任务协议，不能称完整ConceptGraphs强系统基线或已赢过最近邻。可选`overlap_aabb`并非本轮选优/验收路径，本报告只评价IoU和明确的hybrid。

## 记忆、撤回与恢复

第一冻结版本CG-only已完成实际CPSWM owner与普通来源记忆对照：3个观测前缀相同，中间来源撤回后相同，有效动作3→2、账本仍3；冷启动恢复完整状态相同；替换运行期helper被拒。最终hybrid（9480c489）同样完成3前缀和中间撤回的完整规范JSON一致检查：有效来源3→2，物理账本仍3，9个查询读点逐一与冻结hybrid相同，RGB/深度字节也逐帧相同。最终冷启动完整state相同，运行期helper篡改被拒，恢复原helper后状态与账本未变。[owner结果](evidence/owner-result.json)、[冷启动](evidence/owner-fresh.json)、[输入/读出等价](evidence/owner-public-equivalence.json)、[原SQLite/检查点/交付原件包](evidence/owner-state.tar.gz)。

语义层使用明确的受控bootstrap和既有神经测试夹具；相机只是把冻结RGB/深度/位姿重新封装为owner命令的时间/来源，不是新物理采集，不是机器人自主行为。所有新增物理动作计数为0。这个局部比较没有展示隐藏事件、多人物、个性化长期记忆或CPSWM统一框架的科学优势。

## 实际修复和验证范围

历史5°frame3暴露旧重识别代码的真实异常：几何核验可以从四邻域选择mask内像素，而tracker对原浮点光流种子取整后可能在mask外。新增种子支持筛选；不足既有4点时显式UNKNOWN，继续序列。没有膨胀mask、移动feature ID或放宽tracker校验。修复后19帧三组全流程完成。另在无SDK文件的public-only目录、全新worker重跑三个采集的三组方案，9组逐步payload全部精确一致；耗时和仅含文档差异的HEAD不参与相等比较。[重跑摘要](evidence/repeat-checks.json)。

最终源码47项聚焦检查通过，含新外部来源/配置/读点/边界测试、原自然mask、surface policy、实际owner重复/预算/完整伪造聚合回滚/依赖篡改、匹配过渡和对照检查；Ruff与3源码文件mypy通过。没有跑全仓或完整S1矩阵。跨进程/恶意外部解释器、所有完整伪造正路径、全状态机矩阵、B独立复核与共享集成仍未完成，不能从本次局部通过推为全面验收。

权重校验的重复4GB散列开销已用按文件identity/size/mtime/ctime失效的进程内缓存缓解；worker启动仍独立完整核验。本机并发检查时，19帧三臂driver总耗时91.82秒（共享前端，未重新运行Mask R-CNN，不是各臂公平耗时比较）；hybrid完整owner试验477.11秒、冷启动检查119.22秒，包含bootstrap、重复来源验证和重放，不等于纯模型延迟。实时性能尚未优化。未训练或微调模型；当前观察首先暴露mask/实体绑定、几何读点和协议覆盖问题，后续微调需要明确训练/验证/测试边界。

保留H/R/I/C/Z/r/V、三个RB blocks、七算子、隐藏事件、多人物、开放世界、可逆归因与具身反馈的完整范围。原9槽收益门仍未通过；本轮结果支持继续研究组件接入和实例绑定，不能包装成论文创新或全框架科学收益已经成立。
