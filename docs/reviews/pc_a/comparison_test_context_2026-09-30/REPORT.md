# 当前比较测试上下文与完整重放（2026-09-30）

实际被测源码 `fa4dc032c9ef843d8ec0975810c010cd1c5ca7d6`，base `3e030d2345d53f0fa4a4e9b41795a038dca10dc2`；分支 `codex/pc-a-comparison-test-context-20260930`。交付时只同步自己父分支已完成文档，测试/生产/工具/依赖字节与被测源码相同。两轮均为 A 自审，B 独立验收未完成。

## 改动和原因

仅改两个测试文件。当前生产 CORRECT 未获 CCRR 准入时必须拒绝并完整回滚；旧测试仍要求已修复的部分写入缺陷。本次验证非空更正目标、精确拒绝原因、前后完整状态一致，以及 RETRACT 实际执行和提交数下降。

覆盖率 tracer 已占用父进程时，消费观测测试在实际子进程执行同一个测试节点，保留所有真实特征/证据/似然读取断言；必须恰好执行一项、零失败/错误/跳过，并保持父 tracer 不变。已有外来 tracer 时生产 ConsumerProbe 仍拒绝，未修改该保护，也未跳过测试。

## 冻结源码的顺序两轮审查

第一轮：14 passed、0 skipped，185.62 秒。包含两个修改节点、完整正式修订谱系测试，实际启用覆盖率。

随后当前 CLI 从既有受控 D0 生成 60 段 / 1,920 步，891.17 秒；归因文件生成本身标为 UNVERIFIED。第二轮使用另一 hash seed，实际重新运行两次完整 CLI：2 passed、0 skipped，1881.01 秒。两次合法正路径均 CURRENT_SOURCE_FRESH_REPLAY_MATCH，4 类动态依赖及 6 类公平性完整重封装伪造全部拒绝。实际数据、重新计算哈希/归因的伪造原件和原始 CLI 输出全部保存；不是仅名称或负例测试。

Ruff 和格式通过。每阶段前后核验 HEAD 与源码文件摘要保持不变；没有用文档提交 SHA 替代被测源码。

## 当前方法结果与限制

语义步骤摘要 `a14419c97cc848dfb60610d1df88fd4f7bdc3a87146c396c1741104752756d4e`，retained_score_mismatches 为空；与前版本受控诊断的语义步骤一致，但各自源码身份独立。

现有协议仍标 comparison_fairness / scientific_validity = NOT_ESTABLISHED，dynamic scientific_acceptance = false。1,920 步中直接 P5 长期提交全为 0，搜索结果三臂相同；1,040 步存在未来支持、53 步 AMG 缺 owner。这些真实缺口没有用重签、改名称或修测试抹掉。该批只证明当前比较执行和伪造识别可重放，不证明自然闭环、长期记忆/搜索收益或方法优越。

全仓 CI 仍未完成。更早源码远端失败不能全部记在当前源码上；当前源码也不能因这 16 项通过就宣称全仓通过。旧 P0 与旧比较材料保持历史身份，未自动刷新。RGB/分类/澄清对照、完整七轴/三个 RB blocks/七算子及用户尚未答复的离线标签用途选择保持。

## 原件

本机 `output/comparison-test-context-20260930`。封存 72 个常规文件 / 106435466 原始字节，压缩 21790329 字节，SHA256 `2aa7b5a739445dc4bb8dddba2aea4fcc2a9b745a1cad5ecc63bc72678cc7d88a`。全部成员逐文件读回与 inventory 核对。排除派生 Python/pytest 缓存、pytest 便捷符号链接；完整数据和伪造副本保留。此封存不等于独立 custody 认证。

见 [双审](REVIEWS.md)、[复现](REPRODUCE.md)、[归档清单](evidence/archive.json)。
