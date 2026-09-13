# CPSWM 双机协作入口

当前共享集成分支仍为 `codex/dual-pc-handoff-20260912`。本轮整理只归并文档；完整运行候选仍在 #15，尚未验收。

1. 每次先 `git fetch origin --prune`，核对 [GitHub 工作导航](GITHUB_INDEX.md) 和目标 PR 完整 SHA。
2. 读取 [任务板](TASK_BOARD.md)、[A 状态](STATUS_A.md)，以及 [B 当前状态（#17 分支）](https://github.com/goneveitvet240-svg/cpswm/blob/codex/pc-b-adversarial-audit-fix-20260913/docs/collaboration/STATUS_B.md)。本分支 STATUS_B 为旧初始化记录，不能据此认为 B 未开工。
3. 读取 [结构二完整框架](../结构二/README.md) 和任务所绑定源码的报告。
4. 各任务在独立 pc-a/pc-b 分支与工作目录推进；A 集成、B 独立复核，不覆盖其他窗口。

Windows/WSL 环境按 [WINDOWS_SETUP.md](WINDOWS_SETUP.md) 重建；旧包、虚拟环境和工作树指针不得覆盖新 fetch 的源码。

[原交接说明全文](history/2026-09-13-organization/integration_START_HERE.md)保留首次设置、传输归档和日常工作规则。旧报告的日期和结论保持原样，由 GitHub 工作导航区分当前与历史。
