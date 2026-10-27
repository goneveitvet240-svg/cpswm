# 外部接入模块

| 目录 | 模块 | 源码与权重 |
|---|---|---|
| `pi05/` | π0.5 动作策略 | `openpi/` 是官方源码，`weights` 指向统一模型目录 |
| `sam2/` | SAM2 分割/跟踪 | `source/` 是官方源码，`weights` 指向统一模型文件 |
| `libero/` | LIBERO 仿真基准 | `source` 复用 OpenPI 内的 LIBERO，`config` 指向本机配置 |

第三方源码保留自身 Git 仓库和原始目录结构；本机环境位于 `.local/simulation-stack/envs/`。
CPSWM 接口适配代码仍由各独立工作树的 `src/cpswm/` 管理。
π0.5 接入工作树为 `.local/simulation-stack/cpswm/`，启动器为其中的 `tools/simulation_python.py`。

完整约定见 [目录导航](../DIRECTORY_LAYOUT.md)。
