# 完整本机备份

完整运行包 `/Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/output/hfd-observation-alignment-20260926/closed`，159文件、74,018,060字节，逐文件SHA256与冻结工作目录输出比对相同。包含32原始模型NPY、信封/回执、隔离作者行、8段完整候选/context、全部初始/失败/正式日志、前后源清单和8张视觉核查拼图。旧失败没有覆盖或删除。

索引：`/Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/output/hfd-observation-alignment-20260926/backup-manifest.json`；精确条目也提交在 [evidence/backup-manifest.json](evidence/backup-manifest.json)。公开原始9.2GB归档和337试次完整包仍在PR44记录的位置，本轮没有重复复制它们。

Git中仅保存代码、报告、摘要和审查日志；大体积像素与候选文件通过此本机备份和公开来源重建。临时工作目录移除不会丢失原始实验输出。B应从原始来源复跑，不能直接依赖macOS虚拟环境或绝对路径。
