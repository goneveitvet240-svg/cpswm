# CPSWM 双机交接入口

建立日期：2026-09-12（Asia/Shanghai）。A = 原 macOS 电脑；B = 新 Windows 电脑。不同 Codex 账号各自运行，无法直接共享本地会话；代码、状态、报告通过 GitHub 交接。

## 共享版本与阅读次序

仓库：https://github.com/goneveitvet240-svg/cpswm
当前集成分支：`codex/dual-pc-handoff-20260912`。
本次交接前，本地主工作树是 `checkpoint/structure-two-2026-08-22`，SHA `09eb4d48e1c11082e90ca18332d04333e6b5b47a`；实时 fetch 后仍领先同名远端 24 个提交。远端默认 `main` 为 `f28920c21154a1f344634f3fb44ad8b66189370d`，不能当作最新研究进度。

每次开工先 fetch，读取远端集成分支的本文件及 TASK_BOARD、双方 STATUS，再查看任务分支。GitHub 上明确登记的分支和完整 SHA 决定该任务最新共享状态；不能仅按日期、默认分支或本地记忆判断。未推送/未提交快照不等于已集成、已验收。某任务分支比集成分支更新时，两者分别记录。

读取顺序：AGENTS.md → 本文件 → TASK_BOARD.md → STATUS_A.md / STATUS_B.md → SNAPSHOTS.json → docs/结构二/README.md → 对应源码版本的最新报告。

## Windows 首次启动

完整配置、推荐 WSL2 路径与验收命令见 [WINDOWS_SETUP.md](WINDOWS_SETUP.md)。下面的原生 Windows 步骤为备选路径。

先安装 Git、Python 3.13；使用 PowerShell，在新的工作目录克隆，不覆盖备份：

```powershell
git clone --branch codex/dual-pc-handoff-20260912 https://github.com/goneveitvet240-svg/cpswm.git cpswm
cd cpswm
git fetch origin --prune
git rev-parse HEAD
Get-Content AGENTS.md -Encoding utf8
Get-Content docs/collaboration/TASK_BOARD.md -Encoding utf8
git switch -c codex/pc-b-r6-independent-review-20260912
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e '.[dev]'
.\.venv\Scripts\python.exe -m pytest --version
```

上面仅初始化集成分支工作目录；B 的第一次审计应按任务板另建目录，从 SNAPSHOTS.json 指定的 W1/W3 分支及 SHA 分别开始。禁止在缺少窗口三源码的集成基线直接跑窗口三验收。

若已有 uv，可用 `uv sync --frozen --extra dev` 从 uv.lock 重建环境；失败须记录锁文件/平台不兼容，不随意改依赖或删除锁文件。pip 路径不是锁定环境复现，应记录实际依赖列表。

含 `/private/tmp`、`.venv/bin/python`、POSIX shell 的旧验收入口需要适配或在 WSL2（Windows 的 Linux 子系统）中执行。使用 WSL2 时重新在 Linux 文件系统克隆，并用 Linux Python 3.13/uv 重建环境；不要混用 Windows 与 Linux 虚拟环境。先验证平台适配对来源校验、解释器绑定和统计结果的影响，再跑昂贵矩阵。GPU/模拟器任务须等确认 B 的硬件资源后分配。

把本项目目录添加到另一账号的 Codex，粘贴 `PROMPT_FOR_PC_B.md` 即可接手。私有仓库要先给该电脑使用的 GitHub 身份读写权限；用该身份登录，不复制本机凭据。

## 传输包与恢复边界

完整包包含主目录（含 .git、隐藏文件、依赖环境、数据/工件/缓存）、所有当前存在的已登记工作树、可移植 Git bundle（离线仓库包）、路径映射与归档校验报告。已删除/不存在的工作树只保留登记信息，无法恢复从未保存的文件。范围不包括项目之外未登记的目录、外部下载缓存、Codex 历史对话或系统账户凭据。

主目录放在 `CPSWM-transfer/project/`，其他工作树在 `CPSWM-transfer/worktrees/`；原路径映射在 `worktree_inventory.json`。历史报告里的绝对路径按该映射定位。工作树内 .git 文件仍是旧机器指针，仅作为历史快照保留；不要直接在其上 commit。完整包不能直接替代 Windows 的 GitHub 新克隆工作目录。

包用 `.tar.gz`；Windows 可用解压工具或 WSL 中的 `tar -xzf` 解开。先核对旁边 `.sha256`（PowerShell：`Get-FileHash <文件路径> -Algorithm SHA256`）。需要保留符号链接/权限时在 WSL Linux 文件系统解压。

GitHub 上保存代码、报告、进度及必要小型证据；环境和全量归档不上传 Git。完整备份是用户自行在两台电脑间传输的私有快照。没有网络时可以从 `repository.bundle` 克隆，但不得称为最新远端进度。

## 日常工作循环

1. fetch → 核对最新集成分支/任务分支及双机状态；工作树不干净先保全，禁止 reset --hard。
2. 在本人独立任务分支登记任务、基线 SHA、改动边界；推送状态，检查另一方是否在做相同内容。
3. 实现或独立审计；记录实际解释器、依赖、源码 SHA/文件哈希、完整命令、退出码、证据路径。移植环境使用 Python `-m pytest`。
4. 提交、推送本人分支及 STATUS；通过 PR 交接。未经重新复核的新 SHA 不继承旧验收。
5. A 在集成副本审核/整合；B 复核集成后的新源码，重生成比较包并验证真实生产者—消费者链。更新验收状态后再推进下一关。

不同账号的 Codex 不会自动看到彼此未推送的内容；用户在另一台启动后，本分工才实际开始执行。双机不是不同机构的独立托管科学确认。
