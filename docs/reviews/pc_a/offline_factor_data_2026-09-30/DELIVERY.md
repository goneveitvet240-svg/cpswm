# 离线数据入口交付

已批准方案1：仿真实例／掩膜／位置可用于离线训练和校准，线上仍仅RGB-D与相机自位姿。本轮完成数据入口及固定新批采集，尚未导出监督、训练或接通自然观测因子。

实际审查与第二批采集源码：`e88f50752ca50843fc5382b853c65abe134f1281`；base：`0ce10502e8c2292c6d7b34dcbf62f795133ad4c4`。文档／证据提交不更改src/tests/tools源码。第一批失败使用cd51415源码，保留其原始判定；不能用第二批成功覆盖第一批失败。

2103个原始文件共663159971字节，全部纳入；压缩113738082字节，每件文件已解压读回对照外部inventory。整包SHA256：`6264e670f4a848918285f04ec0c1f6ca98a28f52027313c525e9e2cfce43db29`。

## 获取完整原件

为适配GitHub单文件上限，完整压缩包按40MiB顺序分卷，见evidence/archive.json。按01、02、03顺序连接后校验整包SHA；不要只解压第一卷。

```sh
cat evidence/offline-factor-data.tar.gz.part01 evidence/offline-factor-data.tar.gz.part02 evidence/offline-factor-data.tar.gz.part03 > /absolute/new/path/offline-factor-data.tar.gz
shasum -a 256 /absolute/new/path/offline-factor-data.tar.gz
```

分卷仅改变传输形式，连接后摘要已复核等于完整压缩包。每卷摘要、整包摘要及文件inventory均随Git交付。Windows可用二进制读取/写入顺序连接，避免PowerShell文本拼接。解压后按REPRODUCE.md运行；本轮Mac身份核验与Windows独立采集应分别记录。

## 当前证据与剩余工作

- 本轮160项测试、两个顺序A辅助对抗审核通过；含完整合法路径、重签伪造、资产暴露与最终资格后果。
- 第二批12/12房屋采集verified、12个进程exit0，96公开帧、144 SDK事件；外部pin CLI复核exit0。
- 503个合格源对象（训练411／验证92），实际可见159个（118／41），253是对象帧次；96个不同输入组合仍依赖12个房屋cluster。
- 两组目标资产隔离；全场景共有126种跨分区资产，它们不自动具备监督目标资格。程序墙／地板／部件和594个空assetId实例全部留档。
- 线上输入权限、原对照、完整研究框架与正式任务效用保持。B独立验收、自然实例／位置因子训练校准、自然后验与动作收益仍未完成。

下一主项：在这批固定数据上复跑既有公开前端，记录全部候选覆盖与位置参照差异，再实现匹配状态定义的自然观测因子；不得把不同参照的距离直接当测量噪声。
