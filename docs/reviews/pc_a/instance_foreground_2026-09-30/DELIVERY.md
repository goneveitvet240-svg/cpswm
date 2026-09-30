# 实例像素亲和度开发基线交付

已推送并以[草稿 PR76](https://github.com/goneveitvet240-svg/cpswm/pull/76)叠加 PR74 交接，未合并。文档/原件交付 `837c1dc776dbd448999b4a06abd45b087eae9987`；实际双审/训练源码 `0a8a2384c321c3a2dc14cf218854754161af9ffd`，后续交接记录不改变冻结功能字节。

实际双审/训练源码 `0a8a2384c321c3a2dc14cf218854754161af9ffd`，base/父 PR74 `d698792a8e3750af284a2c991a28aff2453b0729`。分支 `codex/pc-a-instance-foreground-20260930`；后续文档/证据提交与实际源码分开记录，src/tests/tools/依赖保持冻结字节。

完整原件 **5,112 文件 / 332,673,503 字节**，压缩 **21,047,249 字节**，无文件排除；所有成员从压缩包逐件读回并重新核对原件不变。包 SHA256：`4ae753a03fd1237e86fa548db7290143daa7ee73d0a51b36055cb504865e324e`。

- [完整包](evidence/instance-foreground.tar.gz)
- [逐文件清单](evidence/inventory.json)与[封存元数据](evidence/archive.json)
- [结果报告](REPORT.md)、[复现说明](REPRODUCE.md)、[独立数值复算](DATA_REVIEW.md)
- [第一轮](ADVERSARIAL_ROUND1.md)、[第二轮](ADVERSARIAL_ROUND2.md)

包包含674个实际训练输出、完整命令/日志/模型、全部公开对及VOID分数、两审合法路径/完整伪造、首次开发失败、独立复算首次Git超时、复核脚本、环境/源码及报告。旧采集原件和前端缓存继续使用PR73/74已封存输入，不在本包重复改签；两个外部pin及取得方式见REPRODUCE.md。本机原件位于 `output/instance-foreground-20260930`，封存后未改。

解压到全新目录后，按REPRODUCE.md以匹配历史来源及本轮源码执行训练/fresh verify。文档中的 `independent_result_check.py.txt` 是复核脚本的逐字节展示副本；完整包内保存可执行的原名 `independent_result_check.py`。原Mac环境和二进制约束如实保留，不声称Windows重建通过。

固定12屋96帧，训练38,993对、开发验证35,735对；验证BCE 0.445967→0.298310、Brier 0.135510→0.087341。实际run和另进程完整fresh重训2/2 exit0，674输出一致，原件独立数值复算一致。顺序两审344/344定向测试通过，角色及受控替代披露；非B独立、非全仓CI或科学验收。

78.8%公开对为VOID，58/96帧没有监督损失，验证负例几乎集中于两屋，训练屋4/6出现退化。模型输出未校准同帧亲和分数，尚不构成完整mask、跨视角身份、位置/朝向观测、联合似然或任务收益。下一项为固定RGB/几何信息对照与公开软实例支持，完整框架及原对照保留。
