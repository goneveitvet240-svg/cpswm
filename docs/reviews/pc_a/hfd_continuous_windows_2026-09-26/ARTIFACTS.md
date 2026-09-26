# 本机完整备份与来源

完整备份：`/Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/output/hfd-continuous-windows-20260926/closed/`。891 文件、300,184,812 字节，全部与冻结工作目录输出逐字校验一致；包含初始夹具失败、第一次沙箱崩溃、两次完整源重建包、最终全部运行观测/候选/手物记录、原始拼图和 11 帧角色重复检测证据。

[逐文件 SHA256 备份清单](evidence/backup-manifest.json)；主仓同份索引为 `output/hfd-continuous-windows-20260926/backup-manifest.json`。Git 保存代码、报告、聚合/失败案例 JSON、命令与源指纹日志；大体积像素/候选不提交到 Git。移除临时工作目录不会丢失这些本机原始输出；B 须从公开来源和锁文件独立复跑。

原始 HFD 数据来源：[作者 Zenodo 10708763](https://zenodo.org/records/10708763)，CC BY 4.0。训练归档仍位于主仓 `output/datasets/hfd-full-training-20260926/raw/training_set.verified.tar.gz`，原作者 MD5 `14232fcd1b34030b77db48d8c771710d`，SHA256 `d515b35e9c6cc2a9af717395247eda0a914118d368a09d5b00b7b8da9aded5a4`。原始 9.2GB 包未重复复制到本轮备份。

完整 intake 根、模型位置和命令见 [COMMANDS](COMMANDS.md) 与最终 `commands.json`；模型哈希见 [环境记录](evidence/final-02/environment.json)。复跑时必须使用本轮冻结的 imported-at 与摘要（重建原包），或生成全新导入包并从原来源验证其新摘要，不把旧摘要直接填到新内容。
