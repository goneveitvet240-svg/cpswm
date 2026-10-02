# 验证矩阵（部分覆盖）

绑定 `d2c3f51b005b49b97812f43b5dc75c3801017807`。A同机顺序检查，不冒称B或全仓独立验收。

|层级|实际覆盖|结果/限制|
|---|---|---|
|合法正路径|RGB-D公开输入、mask读点、真实平移光流、稳定feature ID、旧默认跟踪|R1含89项；实际16帧及old fresh equal|
|完整伪造/输入|完整重签scope/time/camera/重复输入、NaN/越界/错误dtype/shape masks、权重pin错误|拒绝且状态不推进，合法retry通过|
|状态/失败|共享mask、多mask歧义、分割缺失、永久LOST、后续新候选不建anchor、无深度|保留UNKNOWN，不强制匹配；合成覆盖，不声称实际档案覆盖每种攻击|
|局部原子性|第二条track注入异常、第一条已暂存|所有flow回滚，同帧可合法retry|
|评估配对|完整16帧正路径、AABB边界、完整重哈希缺帧/重复帧/错误action/点维度/mask替换、外部pin替换|拒绝错误材料；全部输入不筛选|
|既有Native事务|重复像素/事务幂等、中间撤回注入失败后的tombstone/replay回滚|R2仅2项118.96s；新mask不在Native，旧49项本轮未全跑|
|真实冻结重算|run与fresh分别infer/evaluate|33输出及评分逐字一致，未改旧档案绑定|
|独立算术|原depth/pose、保存mask与flow→选点、投影、AABB|76+49选点、7038成员检查一致；复用模型/flow，不是独立感知|
|静态|mypy src/cpswm；Ruff src/tests/新驱动；format src/tests/新驱动|401 / all pass / 819；938冻结文件未变|
|新Native后果/全账本/动作收益|未接新组件，没有相机动作或新记忆任务|未验收，不以局部合法/攻击测试替代|

R1/R2命令及原始日志在COMMANDS/evidence。合成测试使用可控fake backend检验契约，不将其称为真实权重识别能力；真实权重仅本报告的一屋固定序列。原框默认行为在实际16帧重新推断并比对原公开记录，保持兼容；新功能对原输入不可放宽世界身份权限。
