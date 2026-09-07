# 结构二最终对抗审核第二轮：状态机、依赖链与历史真实性

日期：2026-09-07（Asia/Shanghai）

结论：**本轮状态机与当前工件自查通过；项目总科学门仍未通过。覆盖等级为 partial adversarial coverage（部分对抗覆盖）。**

## 依赖链复核

1. Task 11 对固定 G1/G2 gzip 执行 current-source fresh replay（当前源码新鲜重放）：130 个条件、11,856 条轨迹；原始文件与隔离源 SHA-256 完全一致。
2. Task 12 只选择 K=24：26 个上游条件、104 个 condition-kernel 臂、7,488 条 raw traces；独立 recompute CLI 与主结果逐字一致。
3. Task 13/P5 绑定最终 Task 12 manifest：两者状态均为 `COMPLETED_LOCAL_DIAGNOSTIC_FORMAL_BLOCKED`；P5 诊断为 `MIXED_PROPOSAL_AND_DOWNSTREAM_BOTTLENECK`。
4. P0 manifest 绑定最终源码与清单：content SHA-256 为 `d6c772c82ff1c677c856cbbc4de03c2b74074778c1368d7dc99d708eca315fbb`。
5. Engineering receipt（`562240665957fd7231b0cdfc2c5231139e31bd363bd36876e3fc3642d4054d46`）记录七项真实命令、时间、exit code 及 stdout/stderr SHA-256；全部 exit 0，且 Ruff 同时覆盖 `src/tests/apps`。完整测试集合当前收集 3,508 项，工程回归排除 5 个循环依赖 checkpoint self-tests，后者随后单独 5/5 通过；1 个既有 expected xfail。

## 状态机复核

| 状态 | 当前值 | 审核结论 |
|---|---:|---|
| Local engineering trust gate（本地工程信任门） | `true` | 有 source-bound command receipt 支撑 |
| Task 7 v0.4 / Task 8 v0.4 / Task 10 G1 / Task 10 G2 数值门 | 全 `false` | 不被工程门覆盖或抬高 |
| Per-arm engineering comparison ready（逐臂工程比较就绪） | `true` | 同 visible input、action/replay budget 与非 oracle truth isolation 成立 |
| Paper-level comparison ready（论文级比较就绪） | `false` | 原生复现不全 |
| Native reproductions（原生复现） | `0` | 仅有 6 个 component cores（组件核心），不能称原生强基线 |
| ProcTHOR runtime preflight | `true` | 只证明运行时可用 |
| D1 replay collection | `false` | 无合格采集回执 |
| D2 real collection | unavailable | 无合格真实感知采集回执 |
| Gate B v0.8 | `FROZEN_NOT_EXECUTED / NOT_RUN` | 未登记外部执行链，保持 fail-closed |
| Seven-operator ablation authorized | `false` | 不得运行正式七算子消融或宣称优越性 |
| External validity / independent custody | `false / false` | 本地工件不可替代独立机构、账户或不可变时间锚 |

## 历史真实性与迁移自查

- 旧 Task 11/12 成功目录以及首次失败的 G2 evaluator-support 工件均保存在 `.checkpoint_quarantine/`；没有删除或覆盖。
- 第一轮工程审计真实发现 corrected provenance、v0.5 current-source bundle 和 Ruff format 漂移，失败 receipt 与日志保存在 `.checkpoint_quarantine/engineering_audit_failed_2026-09-07_provenance-and-format/`。
- 最终成功工程 receipt 没有覆盖失败证据；checkpoint 的七项 repair flag 从实际命令结果推导，不再硬编码。
- 工作树仍为 dirty（最终检查有 89 个修改/未跟踪条目）。因此当前可以称为可复算的本地工作树状态，不能称为干净提交、不可变历史快照或独立托管发布。

## 最终可签字边界

可以签字：当前源码上的 trace/输入输出契约、LLM/消融/位置注册测试、Task 11→12→13 本地流水线、逐臂工程计量和工程执行回执均已闭合到可复算的本地证据；强邻 D0 失败结论仍可复算。

不能签字：论文级公平比较环境、原生强基线完成、Gate B 正式通过、D1/D2 外部有效性、独立托管、七算子优越性或“所有未来比较结果必然正确”。这些状态均在最终工件中保持关闭。
