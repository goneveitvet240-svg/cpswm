你是 CPSWM 的电脑 B（Windows），与电脑 A（原 macOS）协作。请立即先 git fetch origin --prune；以 GitHub 仓库 goneveitvet240-svg/cpswm 的 codex/dual-pc-handoff-20260912 分支及其登记的任务分支/SHA 为最新共享进度，不以默认 main、本地旧文件或记忆替代。读取 AGENTS.md 与 docs/collaboration/START_HERE.md、TASK_BOARD.md、STATUS_A.md、STATUS_B.md、SNAPSHOTS.json。

你的分工：独立复现、比较与验收。先 B0 新克隆/环境与实际源码来源自检，再 B1 在独立目录对 SNAPSHOTS.json 中的最新窗口一/窗口三实际修复快照做独立复核。不能只审核 281e888 的旧 HEAD，不能在缺少修复的集成基线上验收，也不能把 R5 旧缺陷结论直接套给 R6。完整备份仅用于恢复工件和历史路径映射。macOS 虚拟环境不得复用；按交接说明新建 Windows 或 WSL 环境。

保留完整框架和用户已作决定。每个问题同时核验合法正路径、原始反例、完整伪造、数值/状态机边界及账本/动作副作用。没有覆盖完要说部分覆盖，不按测试总数宣称全面验收。你负责新独立测试和报告，以及后续窗口二比较模块；主干和统一编排修复交电脑 A，避免同时编辑同一文件。先在 codex/pc-b-* 分支写明任务和起点，推送状态；交付独立审核报告、精确代码 SHA、命令和证据，再推送。A 给出统一版本后，重生成比较包、更新旧预期缺陷断言并复核真实生产者—消费者链。不要改科学指标、门槛或擅自缩小方向。立即完成已能执行的工作。
