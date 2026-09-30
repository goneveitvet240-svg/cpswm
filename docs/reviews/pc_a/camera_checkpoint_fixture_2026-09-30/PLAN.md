# A：相机模型测试默认材料修复开工（2026-09-30）

分支 codex/pc-a-camera-checkpoint-fixture-20260930，base175a54baf91b782907518906b56f28acc84541be；前轮fa4dc03的顺序14/2双审已完成，原件封存并推送。重新fetch核对集成19ddf26830348a2f0b33f0af54d6ba702c5cfb1c，B当前审查分支codex/pc-b-adversarial-audit-fix-20260913为fd4ca6ef5e81c90d7cf7987b42c0b2810d8a810a。

当前远端出现8个CPSWM_CHECKPOINTS缺失准备错误。本轮仅在环境变量未设置时使用仓库已经登记的三个受控开发checkpoint；显式覆盖路径必须照常验证，错误路径/损坏模型不得回落。保留三个真实网络、所有完整伪造和公平对照断言，不训练/重写模型。先留修前错误，冻结后两轮顺序审查：默认目录真实正路径及完整伪造；搬移覆盖路径的正路径、全部矩阵攻击及错误覆盖不回落。原件output/camera-checkpoint-fixture-20260930。全仓/B独立/自然闭环不升格。

