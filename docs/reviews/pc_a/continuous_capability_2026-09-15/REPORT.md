# 连续能力接续：提议解码与默认后验采集连接

本阶段已推送：[草稿PR25](https://github.com/goneveitvet240-svg/cpswm/pull/25)，接续PR24；未合并共享集成，非完整任务签收。

日期：2026-09-15。**本轮为部分实现交付，用户四项结果未全部取得；完整真实运行未签收。**

## 源码与范围

- 分支：`codex/pc-a-continuous-capability-20260915`；base `238e5daf8c1f6a28c25ef616c37a26035c321f83`（草稿PR24）。
- 冻结生产／工具／测试 SHA：`26808e61f8291ec1704a3638ada23d154751e730`。后续文档提交不改变此源码。
- 开工fetch验证：共享集成`19ddf26830348a2f0b33f0af54d6ba702c5cfb1c`，B`fd4ca6ef5e81c90d7cf7987b42c0b2810d8a810a`。未合并共享集成，未改B专属比较代码。
- 完整七轴、三个RB块、七功能算子、六修订操作、既定架构／日程选择协议及本地预算保持不变。

## 对用户四项结果的逐项核对

| 结果 | 本轮取得 | 仍缺／不能声称 |
|---|---|---|
| 自然语义入口 | 核查新的作者公开数据来源，明确不能把已分割标签当作感知输入 | 未取得合格连续多人片段和独立角色／事件／位姿标签；NaturalVisionEvidenceProducer仍未输出GroundedTransition，未连接真实测量历史；真实新增候选为0 |
| 提议训练闭环 | 拆出无监督元数据的ProposalContext；共用完整九因子解码／评分／采样，支持六操作并可生成原生NeuralParticleProposal；回归验证训练评分和采样回执一致 | 尚无从真实可见证据自动生成完整合法支持的生产者；未实现三架构实际评分模型／训练器／预算执行；未取得原生真实六操作监督，没有正式训练 |
| 默认后验行动路径 | 实际Unity采集程序默认走posterior模式，调用共用collect_posterior_step；策略读取同一后验、原始前缀和真实历史执行回执；执行后调用同一stream.advance；旧扫描须显式transport-probe | 仍需合格的仓库内runtime factory提供自然语义生产者、P5上下文和已校准观测／效用模型。目前没有这种完整工厂，所以没有启动本轮真实Unity后验策略运行；更改默认入口不等于交付可用真实策略 |
| 同次纠错与恢复 | 合成工程正例验证保存READY动作恢复后单次执行、未知外部效果禁止重发、失败回执可令下次策略停止重复动作 | 该失败回执正例不是迟到语义反证；未完成同次真实人物运行的撤销错误记忆和应变化任务上的下一动作变化；未取得真实恢复对照 |

## 提议的实际数据流

`ProposalContext + runtime_candidates + scorer → TypedProposalDistribution → training_terms / sample → DecodedProposal + JointProposalProbability → native_proposal`。

运行时上下文只含可见记录、父假设、修订谱系和合法实例／人物／地点支持；不接收完整训练样本。运行候选和监督都复用原有原生约束，保留unknown和rejuvenation的实际后缀／重放字段。评分器取得完整候选语义图，同时取得operation、parent、H/R/I/C/Z/r/V的规范键，避免只让模型看到不具语义的哈希值。

全部条件分布只前向计算一次，训练项和采样使用同一组log-softmax结果；不会只对真值候选重新归一化、截断历史或加概率下限。显式调用方RNG可复现采样序列。未实现RNG接入完整生产训练器／运行恢复，也未赋予神经输出任何账本写权限。原生提议对象与完整事件／后缀效果均返回，但没有替代下游原生消费校验。

## 采集的实际数据流

`同一stream.advance → 当前原生联合后验 + 可见前缀 + observation_history → 配置模型问题 → prepare_posterior_observation → 同一execute_observation → 同一stream.advance`。

待恢复READY命令优先使用已保存的完整模型问题，执行前仍由原有核心锁内重新选择并绑定方向／角度／来源。未知结果必须通过既有transport reconciliation解决。观测模型、校准数据和效用定义的ID／摘要随命令持久化；这些字段是配置来源声明，不是独立校准真实性证书。参数或来源变化会拒绝恢复旧动作。

实际入口为`tools/run_continuous_unity_camera.py`：默认需要`--runtime-factory module:callable`，返回`ContinuousRuntimeComponents`，且工厂必须属于本源码src树；提供的模型必须遵循新的执行历史输入协议。没有该依赖时启动前明确报错，不启动Unity、创建输出或回退固定扫描。`--mode transport-probe`仅保留原工程扫描用途，不能同时混入posterior factory。

## 验证与证据

- 最终同一冻结源码：**254 passed，0 failures，0 errors，0 skipped，0 xfail**，覆盖15新增案例及相邻模块；[精确命令／计数](regression.json)、[JUnit](regression.xml)、[日志](regression.log)。
- 新缓存运行、解码器导入路径属于本工作树；`source_before.json`与`source_after.json`相同。
- mypy通过340个源码文件；本批9个生产／工具／测试文件ruff和格式检查通过；[静态检查记录](quality_checks.json)。
- wall35.235秒、子进程CPU34.671秒、macOS峰值RSS482082816字节，仅工程检查成本，不能代替真实全生命周期成本。
- 专项正例：六操作解码、逐项原生概率回执绑定、总概率质量1、兼容集梯度、明确RNG复现、未决分支保留、READY恢复单次执行、无信息停止、失败回执驱动停止。负例含训练信封混入、越界监督／来源、非法后缀、非有限logits、未知副作用重发和恢复效用来源更换。
- [开发中的失败与修复](DEVELOPMENT_FAILURES.md)保留测试曾发现的实际漏接。全部新能力验证使用明确合成夹具及诊断可训练logits，未把它们称为自然输入、选定架构训练或真实记忆纠错结果。

## 完整任务仍需完成的工作

1. 取得并独立核查小规模自然多人标注；实现可校准接触／释放、身份／角色和位姿生产，并使同一自然生产者返回GroundedTransition及保留测量历史。
2. 从这些可见输入和实际原生修订轨迹生成完整提议支持／监督，接注册架构评分模型、采样消费和训练／预算执行；数据条件齐备后按已授权CPU小预算运行。
3. 提供上述完整runtime factory及经过独立验证的观测／效用模型，在实际Unity或其他已授权动作响应环境运行默认采集路径；不能用预录视频替代动作反馈。
4. 同次真实运行取得晚反证→重算→撤错记忆→改变下一动作，并比较中断／不中断结果。然后冻结实际最终源码，进行两轮独立整体对抗审核；本轮没有启动或冒充这两轮最终审核，B跨机验收仍待完成。

[本轮数据来源核查](DATA_SOURCE_RECHECK.md)。实现缺口与外部数据依赖分别保留，不能把所有剩余工作归因于等数据。
