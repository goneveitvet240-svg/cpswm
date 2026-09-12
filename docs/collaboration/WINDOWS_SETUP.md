# 第二台 Windows 电脑环境配置

核对日期：2026-09-12。项目 `.python-version` 和 Ubuntu CI 固定 Python 3.13，本机实际解释器是 3.13.5；`pyproject.toml` 的最低 >=3.11 不等于当前验收环境。为首次对齐建议使用 **CPython 3.13.5 + uv + 仓库 uv.lock 的 dev 依赖**。

## 推荐配置

| 项目 | 配置 |
|---|---|
| 系统 | Windows 11 + WSL2 + Ubuntu 24.04 LTS；Windows 10 是否支持取决于版本，见微软安装要求 |
| 必需软件 | Git、curl、编译工具、uv、Python 3.13.5；Codex 使用你在第二台已登录的账号 |
| Python 依赖 | `uv sync --frozen --extra dev` 安装锁文件中依赖；不要手工逐个装最新版 |
| GitHub | 对 `goneveitvet240-svg/cpswm` 有读写权限的身份；在第二台独立认证，可用 gh 或 Git 凭据管理 |
| 硬件建议 | 16 GB 内存可先做小矩阵，32 GB 更适合并行复核；预留约 60 GB 磁盘用于全量备份解压、环境与新实验。这是初始建议，不是已实测最低要求 |
| 初期算力 | CPU 即可完成本次分配的普通契约/数值/来源复核；先限制 pytest 为 2 个 worker（工作进程），按内存和负载调整 |
| 后续按需 | CUDA、PyTorch 感知栈、AI2-THOR/ProcTHOR、ROS2、Docker 不作为本次 B0/B1 的安装前置；具体模拟器/训练任务另行核对硬件和版本 |

WSL 在 Windows 上提供 Linux 环境。安装要求和命令依据 [微软 WSL 安装文档](https://learn.microsoft.com/en-us/windows/wsl/install) 与 [Ubuntu WSL2 文档](https://ubuntu.com/wsl/docs/latest/howto/install-ubuntu-wsl2/)。WSL2 有助于执行现有 POSIX 工具，但不自动修复硬编码的 macOS 绝对路径。

## 1. 安装 WSL（管理员 PowerShell）

```powershell
wsl --install -d Ubuntu-24.04
```

按提示重启，打开 Ubuntu，设置 Linux 用户名和密码；然后在 PowerShell 核对：

```powershell
wsl --list --verbose
```

Ubuntu 对应 VERSION 应为 2。若已有 WSL 环境，可复用已有合适发行版，先记录版本，不必重装。

## 2. 在 Ubuntu 终端准备工具

```bash
sudo apt update
sudo apt install -y git curl ca-certificates build-essential
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
uv --version
uv python install 3.13.5
```

uv 安装和 Python 管理依据 [uv 官方安装文档](https://docs.astral.sh/uv/getting-started/installation/) 及 [Python 管理文档](https://docs.astral.sh/uv/guides/install-python/)。这里安装脚本来自 uv 官方域名。若网络/代理阻断，记录错误后处理第二台网络，不复制本机 127.0.0.1 代理配置。

配置该电脑自己的 Git 提交身份（用真实姓名/昵称及本人 GitHub 邮箱替换示例）：

```bash
git config --global user.name "YOUR_NAME"
git config --global user.email "YOUR_GITHUB_EMAIL"
```

完成 GitHub 的独立认证。若仓库私有且使用不同 GitHub 账号，需要仓库所有者先添加该账号的访问权限；不是更换 Codex 账号就自动获得权限。

## 3. 克隆当前集成分支并锁定环境

在 WSL 的 Linux 用户目录工作，避免将工作环境建在解压的 macOS 备份或混用 Windows 环境：

```bash
mkdir -p ~/projects
cd ~/projects
git clone --branch codex/dual-pc-handoff-20260912 https://github.com/goneveitvet240-svg/cpswm.git cpswm
cd cpswm
git fetch origin --prune
cat AGENTS.md
cat docs/collaboration/TASK_BOARD.md
uv sync --frozen --extra dev --python 3.13.5
```

`--frozen` 使用已有锁文件，不重新求解依赖；依据 [uv 同步文档](https://docs.astral.sh/uv/concepts/projects/sync/)。若安装失败，保留命令/错误/平台信息，先核查所需包是否支持该平台，不能静默改锁文件。Windows/WSL 的锁定安装尚未在第二台执行；下列自检完成后才算环境可用。

## 4. 环境验收

```bash
git rev-parse HEAD
uv --version
.venv/bin/python --version
.venv/bin/python -c 'import sys, platform, cpswm; from importlib.util import find_spec; print(sys.executable); print(platform.platform()); print(find_spec("cpswm")); print(find_spec("pytest"))'
uv pip check --python .venv/bin/python
.venv/bin/python -m pytest --version
mkdir -p output/pc-b-environment
uv pip freeze --python .venv/bin/python > output/pc-b-environment/requirements.actual.txt
.venv/bin/python -m pytest --collect-only -q > output/pc-b-environment/collection.log
```

确认 Python 是本工作目录的 `.venv/bin/python`，cpswm 源码来自当前克隆的 `src/cpswm`，不存在原 Mac 的绝对路径。把命令、退出码和源码 SHA 写入 STATUS_B。collect-only（仅收集）只检查导入/用例发现，不等于测试通过。

按 TASK_BOARD 和 SNAPSHOTS.json 为 W1/W3 分别新建审计克隆、固定 SHA，并各自 `uv sync --frozen --extra dev --python 3.13.5`。从最新报告中选择正确的已绑定命令。窗口二部分用例必须先生成本次比较包并设置所需证据路径；不要把缺少准备输入的 pytest 失败算作生产缺陷。完整套件和模拟器测试不要作为第一次安装命令盲目启动。

## 5. 只能使用原生 Windows 时

先按 [uv 官方文档](https://docs.astral.sh/uv/getting-started/installation/) 安装 Windows 版 uv，再在独立新克隆目录用 PowerShell 执行：

```powershell
uv python install 3.13.5
uv sync --frozen --extra dev --python 3.13.5
.\.venv\Scripts\python.exe --version
.\.venv\Scripts\python.exe -m pytest --version
```

原生 Windows 可用于编辑和平台支持的普通 Python 测试；POSIX 编排、绝对 shebang、权限和来源检查需要逐项适配并复核，不能仅为跑通而关闭校验。`check.sh` 等 shell 脚本用 WSL 路径执行。Codex 如在 Windows 终端启动测试，应明确通过 WSL 调用 Linux 工作目录中的 Python；若应用不能直接操作该目录，先将终端输出与报告带回当前会话，不假设自动跨环境。

## 启动第二个 Codex

把新克隆项目交给第二台 Codex，发送 `PROMPT_FOR_PC_B.md`。它先 fetch 最新 GitHub 状态，再做 B0/B1。代码审计可在 CPU 上开始；待你提供 CPU、内存、显卡型号/显存后，再分配大规模并行实验或仿真任务。
