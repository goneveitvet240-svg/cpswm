# 数据入口

- `datasets/`：现有数据集的便捷入口。
- `artifacts/`：原 artifacts 的实体存储，包含数据生成产物与归档。
- `outputs/`：原 output 的实体存储。
- `runs/`：仿真运行记录、日志、录像与结果。
- `models/`：π0.5、SAM2 模型权重。
- `benchmarks/`、`review_evidence/`、`worktrees/`：原位保留的配置、证据和各分支数据入口。

数据、模型、输出和本机链接不提交到 Git。已冻结的样例和审计证据仍由原分支管理。
`datasets/d1_storage` 沿用既有 iCloud 数据入口，不代表数据已完整离线下载。

完整目录约定见 [目录导航](../DIRECTORY_LAYOUT.md)。
