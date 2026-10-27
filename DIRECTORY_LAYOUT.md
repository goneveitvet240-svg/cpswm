# 本地目录导航

2026-10-27 整理：数据集中在 `data/`，接入模块集中在 `integrations/`。

```text
data/
  datasets/       数据集入口（指向 artifacts 中的现有数据）
  artifacts/      数据工件、生成样本和历史归档（实体目录）
  outputs/        本地实验输出（实体目录）
  runs/           π0.5 / SAM2 / LIBERO 仿真记录（实体目录）
  models/         模型权重（实体目录）
  benchmarks/     当前主工作区基准配置与样例的入口
  review_evidence/ 当前主工作区审计证据的入口
  worktrees/      各独立实验分支的已提交数据入口
integrations/
  pi05/openpi/    π0.5 官方 OpenPI 源码（实体目录）
  pi05/weights    指向 data/models/pi05_libero
  sam2/source/   SAM2 官方源码（实体目录）
  sam2/weights   指向 data/models/sam2.1_hiera_tiny.pt
  libero/source  指向 OpenPI 内的 LIBERO 源码
  libero/config  指向现有 LIBERO 本机配置
```

根目录 `src/`、`apps/`、`configs/`、`tests/`、`docs/` 继续分别承载项目源码、运行入口、配置、测试和文档。
`.local/simulation-stack/` 保留独立 Git 工作树、Python 环境、缓存和本机配置。

旧 `artifacts/`、`output/`、`.local/simulation-stack/{runs,models}` 以及
`vendor/{openpi,sam2}` 已改为指向新实体目录的相对符号链接。已有启动器和冻结证据中的绝对路径仍可解析。
不要删除这些兼容链接；新数据按上面的目录归档。不同工作树的数据仍按分支分开，不能相互覆盖。
已提交的基准、测试样例和审计证据保留原位，通过 `data/` 浏览，避免改动历史证据与另一分支源码。

本地布局对应的主目录仍是旧 checkpoint 工作区，并非最新集成代码；π0.5 接入代码位于
`.local/simulation-stack/cpswm/`。源码版本和运行结果须以各工作树的 Git SHA 为准。

`data/` 大文件、外部源码和本机链接均被各自 `.gitignore` 排除。GitHub 只同步目录说明和整理回执。
这些链接描述本机安装；另一台电脑不能只 clone 文档分支就获得数据、权重或运行环境。
新电脑应按现有安装说明重建环境，Windows 创建符号链接需要对应权限。

迁移核验记录：`data/directory-migration-20261027.json`。
