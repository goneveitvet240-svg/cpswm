# 匹配过渡死亡测试报告（2026-10-09）

## 结论

本轮死亡测试 **FAIL**。PR99 的持续对象重识别工程链路可以确定性重放、拒绝显式双候选歧义、隔离晚出生轨迹，但在一组真实 Mask R-CNN RGB-D 连续观测中，两次把首帧锚定到 `Kettle|surface|2|6` 的轨迹错误重识别为 `CounterTop|2|0`。在相同任务、相同冻结输入和相同三动作预算下，旧版与候选版均为身份 `7/9`、严格未扩张 AABB 位置 `6/9`、联合成功 `6/9`；候选版没有任务收益。

因此本轮不启动完整 S1 fixed/active/no-update 与 retain/withdraw 矩阵，不把 PR99 当前重识别方法提升为已通过方案，也不把产生坐标输出等同于目标恢复。结果只覆盖单屋、三帧 `30°→5°→5°` 开发序列，不能外推为整个 CPSWM 或完整统一研究框架失败。

## 公平比较和隔离

- 旧版源码：`6e9c953a81e2fc072f4d079d7a19194b1324ea64`；候选生产源码：`a5385ddaf6724d2d346fc222866edc2b7ec9407c`。
- 一次真实捕获产生三组 RGB、depth、自位姿、原生 post-NMS 候选和概率 mask；Mask R-CNN 只执行一次。冻结输入摘要为 `91d0863e83ea97afa7b9b79d895a1bc57a0f6edc234744d72a2bf01277919f13`。
- 两臂均从同一 manifest 读取逐字节相同输入，重放不再调用检测器且不产生物理动作。每臂执行两次，输出逐字节一致。
- SDK `objectId`、实例 mask 与未扩张三维 AABB 只由离线评分和诊断命令读取，没有进入检测、关联、更新或报告生成。
- 查询固定为首帧 `bottle:0`、`bottle:1`、`bowl:0`。目标 ID 复用此前 S1 已冻结映射，未根据本轮结果替换。UNKNOWN、LOST、晚出生和全部失败均保留。

## 预声明门结果

| 门 | 结果 | 证据 |
|---|---:|---|
| 两臂确定性重放 | PASS | baseline A/B、candidate A/B 文件 SHA 各自相同 |
| 自然 LOST 后身份＋位置联合恢复 | FAIL | 0 次正确联合恢复 |
| 查询级联合成功净增益 | FAIL | 旧版 `6/9`，候选 `6/9` |
| 错误重识别为零 | FAIL | step 1、step 2 共 2 次错误接受 |
| 接受的重识别均可评分 | PASS | 2/2 有 SDK 身份和 AABB 真值 |
| 原本成功的查询无退化 | PASS | 0 个查询槽从成功降为失败 |
| 完整双候选歧义保持 UNKNOWN | PASS | 操控帧输出 `UNKNOWN_AMBIGUOUS_REIDENTIFICATION` |
| 晚出生不劫持首帧 ordinal query | PASS | sports-ball 轨迹 `query_eligible=false`，未进入三个查询 |

完整机器可读结果见 [`evidence/summary.json`](evidence/summary.json)。该文件 SHA-256 为 `44ed475fb17c7de72fbc84230cba65265f0dc144f75f79960e18ea306730d6f5`。

## 为什么失败

失败不是事务丢帧、两臂输入不一致、重复计证据或非确定性引起。问题发生在实例身份表征：系统把 detector 的语义类别一致当作候选兼容条件，又用 8-bin RGB 直方图和单个表面点距离形成未校准开发能量。它能判定“当前只有一个候选胜过 UNKNOWN”，但这个唯一候选可能根本不是原实例。

本轮首帧所谓 `dining table` 锚点的选点在 SDK 真值中实际落于 `Kettle|surface|2|6`。后两帧被接受的 `dining table` 概率 mask 分别含 32,340 和 37,182 个阈值内像素，其中真实 `CounterTop|2|0` 占 `67.30%` 和 `74.07%`，目标 kettle 只占 `7.28%` 和 `6.63%`。两次最大概率选点都落在 countertop。候选能量分别为 `-0.04995`、`-0.30543`，高于既有 UNKNOWN logit `-2.0`，于是唯一性门稳定而错误地接受。

这说明当前粗语义 mask 跨越了桌面及其多个物体，RGB 直方图与 0.5 m 几何尺度无法提供实例级排他证据。对抗双候选测试通过只证明“两个完全相同候选会拒绝”，不能防止单个错误候选。逐实例像素构成、选点真值和能量明细见 [`evidence/false-reidentification-diagnostic.json`](evidence/false-reidentification-diagnostic.json)，SHA-256 为 `d51afe0f35b3348ee0913e9dd3e444edac900aed2c4550bb5b74c983980c294b`。

## 工程覆盖和验证

新增驱动支持冻结捕获、精确源码 SHA 绑定、两臂重放、严格 AABB 评分、完整候选复制歧义攻击、门汇总和离线 mask 成分诊断。验证器拒绝原始 payload 替换、mask 替换、candidate/native-index 乱序、即使重新计算外层哈希的 mask 替换，以及错误源码 SHA。相关 4 个测试文件共 48 项通过；Ruff check/format、Python 编译和 diff check 通过。

仓库证据含 69 个被清单约束的文件、10,010,310 bytes，覆盖原始 RGB-D、native masks、动作账本、SDK 离线真值、两臂重复重放、评分、对抗控制、诊断和日志。逐文件大小与 SHA-256 在 [`evidence/evidence-files.json`](evidence/evidence-files.json)。不包含模型权重；Mask R-CNN 权重 SHA-256 固定为 `73cbd0190fcbe3ba339921fbce2c3a0b6bb9126c9a133c85e43a2a8e060a109e`。

## 下一主干门

推荐下一轮先加入 **reference-feature geometric verification（参考特征几何核验）**：对 LOST anchor 保存最后有效帧的局部特征与深度几何，在候选 mask 内要求可追溯的跨帧对应支持，再允许现有外观—几何能量进入接受分支。首轮可直接复用已有 `min 4` 前后向一致特征和 `FB ≤ 1.5 px` 条件，不新调评分指标或 AABB 容差。修复后先重跑本冻结死亡测试；必须做到两次错误接受归零且出现至少一次正确联合恢复，才进入多屋、多动作 S1 矩阵。

较轻的 mask-conditioned appearance descriptor（掩码条件外观描述子）仍可能继承宽语义 mask 污染；learned instance embedding（学习式实例嵌入）潜力更强，但会引入新模型、校准和算力变量。三条路线都保留，本文只给出基于当前反例的优先建议，不改变隐藏事件、多人物、开放世界、可逆归因、具身反馈、H/R/I/C/Z/r/V、三个 RB blocks 或七算子总体范围。电脑 B 对最终 SHA 的独立复核和共享集成均仍待执行。
