# 2026-10-03 方法与代码对照检索

问题：在自然RGB-D、持续同一目标、连续观察更新和同预算效用的约束下，已发表系统的哪些机制解释其成功，我们S1的哪些限制可由代码与失败记录直接确认？分析不改变原科学指标、先验或完整研究范围。

| 概念 | 同义/邻接检索词 |
|---|---|
| 持续对象身份 | instance association / object-centric mapping / re-identification；实例关联、重识别、三维物体地图 |
| 主动观察 | active perception / next-best-view / frontier exploration；主动感知、下一最佳视角、前沿探索 |
| 持久记忆 | lifelong navigation / persistent scene memory / episodic memory；终身导航、场景记忆、情景记忆 |
| 半静态变化 | semi-static mapping / probabilistic object change detection / map maintenance；半静态地图、物体变化检测、地图维护 |
| 可比效用 | object-goal navigation / instance localization / success SPL action budget；物体导航、实例定位、成功率和动作预算 |

代表查询：`"Where Did I Leave My Glasses" robot code`；`GOAT GOAT-Bench lifelong navigation memory github`；`ConceptGraphs 3D scene graph mapping github object merging`；`具身智能 物体导航 长期记忆 主动探索 开源 GOAT`；`"3D-Mem" github "GOAT" navigation`。

已访问：公开网页搜索、作者项目页、arXiv、CVF/RSS论文入口与官方GitHub。没有检索付费WoS/Scopus、CNKI/Wanfang或专利库，也未将第三方解读作为技术结论。不是穷尽性系统综述。阅读全文/代码核查与本机实测严格分开；本轮不因阅读论文宣称复现其成功率。

核心候选：ConceptGraphs（持续对象地图）；3D-Mem（记忆与探索联动）；GOAT/GOAT-Bench（后续任务记忆和评价协议）；Where Did I Leave My Glasses（POCD到半静态维护的最邻近系统）。逐一确认公开代码可用性，未公开部分标记缺口。
