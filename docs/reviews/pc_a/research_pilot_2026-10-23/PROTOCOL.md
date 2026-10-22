# E0/E2 加速开发批次：运行前协议

用户授权按研究推进方案书加速实施；排期压缩，验证要求保留。

- 方案书：CPSWM研究推进方案书_v1.0_20261023.pdf；SHA256 `c69776bea76bea9a37f2764276bda7c182831842b50fc6e0aac185751421dc37`。
- 分支：`codex/pc-a-e0-e2-research-pilot-20261023`。
- base：`e0043f23a1c3fa62fde5bf73389cdeba2ce735a6`（PR118）。
- 已 fetch；共享集成仍为 `19ddf26830348a2f0b33f0af54d6ba702c5cfb1c`。本分支堆叠 PR118，不自动合并。
- 本批为开发诊断，沿用既有模型、先验、24 粒子、读出及开发数据；不作新科学胜负判据、样本量或确认性检验决策。

## E0：两层参考

1. 重跑已有 finite-world exact falsifier（24 粒子、既有 bootstrap seed 8701），明确它不是生产模型。
2. 为 `CurrentEventRuntime` 增加仅诊断的单步支持集枚举：在相同输入粒子云下，对 `_candidates` 返回的全部 parent/candidate 计算 prior × normalized transition × observation likelihood × posterior projection × constraints。枚举不除 proposal q；采样估计则除 q。保留当前 unresolved 规则。
3. 固定使用现有 `sparse32` validation 第一 episode 前 4 步、原生联合及六势消融、systematic/independent_strata_v1 两种既有采样方式。该 episode 实际来自既有 validation seed 7；传入 test seed 67001 不代表使用新测试世界。先 observe 做参考比较，再执行既有 predict/feedback 形成下一步共同前缀。
4. 输出角色/机制/身份/原因/制度边际 TV、未采样的参考支持质量、共享 pre-ledger 读出排序、ESS 和枚举/采样目标评估次数及耗时。记录候选截断：这是 proposal 支持内、给定近似父粒子的局部精确参考，不是完整历史或所有潜变量的精确后验。
5. 枚举与生产共享模型打分函数和动作读出，因此检验近似/重要性算术，不能独立证明生成模型或读出正确。测试用可手算模型检查 q、transition、constraints 与重复抽样处理。

## E2：四条件修订开发矩阵

沿用 `make_scenario(delayed_attribution/identity_correction, seed=7)` 的证据及语义值，构造无修订、正确迟到修订、错误修订、错误后再纠正四条明确标注的受控轨迹。正确/错误仅指与该 fixture 的最终真值一致性，不代表自然传感器可靠性。

比较 native_joint、native_factorized、source_replay、ordinary_memory，并为每个修订点从当前有效证据从头重建同模型参考。逐点检查读出、原生状态、账本、三个 RB blocks、来源数及后续既有任务读出；记录全历史重建次数/目标打分次数/时间。不同 source ID 引起的随机差异必须与同 source ID 重放等价分开。三个 follow-up 为共享受控位置输入，不作独立统计样本。

SimulationMemory 目前全部有效历史重建；本批不能据此声称增量修订效率优势。普通记忆忽略修订，是不同信息消费规则的消融。source_replay 是不同读出基线，不是相同生成模型的 full rerun。

## 全计划映射和退出条件

| 阶段 | 本批工作 / 下一依赖 |
|---|---|
| E0 | 精确参考桥接与误差报告；数值不一致先定位，不调权强造动作差异 |
| E1 | 依赖 E0 结果；完整任务族与强基线仍保留，正式样本/效用定义待确认 |
| E2 | 四条件正确性和成本实测；真正局部重算、长期保持与统一回放仍待实现/复核 |
| E3 | 稳定/周期/新习惯/访客/实例/路线与组合完整保留；接入强变点/制度基线待做 |
| E4 | oracle/受控噪声/自然图像分层；新标注/校准和组件选择待做 |
| E5 | 同初始环境闭环策略比较待做；离线相同日志不声称主动感知收益 |
| E6 | 保留已有官方 π0.5/LIBERO/SAM；完整操控成功、固定正确目标上限及目标匹配的成功判据待做 |

工程通过、局部诊断、B 独立复核、统一验收、科学收益分开；完整框架 H/R/I/C/Z/r/V、三个 RB blocks 和七算子不缩小。交付代码、原始 JSON、运行环境/源码 SHA、报告和可复制命令；交 B 独立复核，新增数据/主要效用/确认性样本量由用户决定。
