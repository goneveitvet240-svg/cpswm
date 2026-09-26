# A：VISOR 候选—人工掩膜逐帧对齐开工（2026-09-27）

独立分支 codex/pc-a-visor-candidate-alignment-20260927，目录 /private/tmp/cpswm-pc-a-visor-candidate-alignment-20260927。base/开工代码 ced69a60c2e81d37f7b9012276451a6778b78020。fetch 已核验共享集成19ddf26830348a2f0b33f0af54d6ba702c5cfb1c、B fd4ca6ef5e81c90d7cf7987b42c0b2810d8a810a，均未变。

本轮固定上一轮P01_01全部485帧，以现有FasterRCNN和MediaPipe全图+人物区域默认配置推理；RGB输入与监督离线分离。保存全部前端候选及每个候选对每个适用作者掩膜的几何量，不选匹配阈值、不以最高重叠自动授予接触标签。记录无候选、无重叠、多重重叠及跨区域重复可能，分母保留全部帧/作者关系。零新增正式训练、语义发布、记忆写入和动作；不推断稀疏帧释放时间或跨帧身份。

先冻结Python并顺序执行两轮不同设计的A局部自审，覆盖合法正路径、完整重封伪造、标签隔离、同帧来源与重试；再跑真实全部帧并源绑定复核。证据 docs/reviews/pc_a/visor_candidate_alignment_2026-09-27/。尚无本轮测试结果；B未验收、共享分支不合并、旧自动接续保持暂停，完整研究范围保持。

