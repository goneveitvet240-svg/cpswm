# 固定特征组对照交付

分支codex/pc-a-affinity-controls-20261001，base/父PR76 ffcaa7b292c73201d799f6631688387409c21cb7，实际双审/运行源码a6c026963b5fec1503fa0d582fe016eccf60c756。当前为本地待推送交付；实际草稿PR及交付提交由后续交接记录补充。879份源码与冻结原件绑定，文档提交不会冒充实际运行源码。

两轮顺序A辅助审查各447通过，真实run/fresh exit0、292文件逐字节一致，独立从已pin父特征的算术检查通过。未重新运行Unity/检测器，非B独立、非全仓CI。见[报告](REPORT.md)、[复现](REPRODUCE.md)、[数据复核](DATA_REVIEW.md)。

完整原件[affinity-controls.tar.gz](evidence/affinity-controls.tar.gz)：11,831文件，331,243,846原始字节，压缩21,520,290字节，SHA256 `47d1d831a0f8025bd22895017b47cc66244dd5642d5b879d02ea207cab8c8893`。所有归档成员逐一读回并与原件比较。仅排除179个已列摘要的派生Python缓存；全部实验/拒绝/失败/合法恢复、受控输入与搬移源码保留。详见[inventory](evidence/inventory.json)及[archive metadata](evidence/archive.json)。原件output/affinity-controls-20261001已封存。

case ledger外pin5eaabaaae15e4ed453c0f84b4f243103e25e5e9c1125f87f23e82e2be352bad2，父ledger原pin32e0dc7cec8fce6dfca5bc36755cfba5cf3551b454c1f746f20ac2076936e842；独立算术结果1ab124f0d83cda109e80d10307f868a89c0edeb49c8e3d77a7e68c6bb3a45060。

交付前fetch核对集成19ddf26830348a2f0b33f0af54d6ba702c5cfb1c、B fd4ca6ef5e81c90d7cf7987b42c0b2810d8a810a、父PR76上述head均未变。未修改STATUS_B、旧封存包或用户主工作树；不合并共享集成。

主线调查发现只改q不会补足目标密度；下一轮公开软表面读出、pivot/AABB双参考3D开发残差和受控raw-likelihood消费仍未实施。本轮不存在完整mask、自然world身份、正式位置/朝向校准、自然目标密度或动作收益验收；完整框架及既有任务保持。
