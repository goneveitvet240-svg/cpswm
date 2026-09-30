# 相机 checkpoint 测试准备修复（2026-09-30）

实际源码14409b3beabbd298196ea8f65c4e4f7a0cf719f2，base175a54baf91b782907518906b56f28acc84541be，分支codex/pc-a-camera-checkpoint-fixture-20260930。仅改tests/test_camera_policy_identifiability_artifacts.py：CPSWM_CHECKPOINTS未设置时读取仓库已经保存的三个开发checkpoint；显式路径始终优先，错误输入不得回落。无生产/工具/模型/依赖变动，也没有训练或改写模型。

## 原失败与两轮顺序审查

修前f80ee2f004fb2aaa187a0c1ac63e30b4f16d0b39在本机实体冻结环境重现1准备错误（18.93秒，KeyError CPSWM_CHECKPOINTS），对应fa4dc03远端的8项相同fixture准备错误。

冻结后第一轮，环境变量未设置，完整模块13 passed、零跳过（27.23秒）；包括三种真实网络正路径、7类完整结果伪造及5类完整矩阵选择偏差/不公平攻击。第二轮，三个checkpoint完整搬移、字节逐文件一致，另一个hash seed，同一完整模块13 passed、零跳过（27.41秒）。

第二轮追加显式缺失目录、空路径、完整模型目录内错误arm三类输入；实际pytest各1个准备错误/exit1，分别FileNotFoundError、FileNotFoundError、checkpoint arm differs from method，符合预先声明的拒绝要求。这三次原始FAILED状态原样保存，不改成pytest通过，也不计入13/13。补存三条真实模型运行的输出：每条1次网络调用、1次反馈更新、1次行动。

所有阶段前后源码和原checkpoint字节保持一致；Ruff/格式通过。两轮均为A自审，未声称B、Windows、完整CI或自然任务验收。最新实际源码的完整远端CI尚未完成；不能把本机准备修复先计作远端通过。

## 原件与后续

output/camera-checkpoint-fixture-20260930保留baseline、两轮完整命令与日志/JUnit、三个非法覆盖原件、实际神经输出、目录搬移副本和源文件摘要。封存99个常规文件/78090717原始字节，压缩12295469字节，SHA256 f4ab144cc3bbaac8f8f94d0e14d975c99743b9a144de89af09ae62ee6f8ebf9e；全部成员逐文件读回核验。

最后两批由当前草稿PR统一交接：前批fa4dc032c9ef843d8ec0975810c010cd1c5ca7d6的14/2双审与当前14409b3的13/13双审保持独立源码绑定。当前分支相对PR70只改三个测试文件及文档/原件，不改生产代码。完整自然闭环、当前CI材料准备/旧回执漂移、跨平台数值差异和B独立复核仍未关闭。完整范围、对照、科学选择和待答复离线标签用途保持。
