# 结构二双时间尺度可逆行动读出：开发性记录（2026-08-28）

## 证据边界

本轮发生在旧 D0 sealed test 已经参与根因诊断之后，因此所有新结果均标记为
`post-diagnostic development; not confirmatory`。旧的 60-episode 失败产物不覆盖、
不重命名，也不作为本轮新方法的封存证据。

开发协议使用 20 个新 validation seed（12000--12019）和 60 个互斥 holdout seed
（13000--13059）。四个方法在每个证据 cell 中各自获得三个调参点，并共享相同可见
流、反馈流、行动预算和冻结 evaluator：

1. matched open-world AMG；
2. PCHMP latest-owner 强控制；
3. v0.3 surviving-owner-revisions 慢读出；
4. dual-timescale reversible 快慢可逆读出。

## 方法变化

`CorePrototypeSpine` 新增独立 fast-action ledger。PCHMP owner posterior 可以立即影响
下一步行动，但该 ledger 没有 Dirichlet/RLS/Hybrid 写权限。ORRER 反馈在下一次 planner
读取前替换 fast lineage head；RGRC/CCRR 继续单独管理长期统计与阶段记忆。

这实现了行动权限和长期学习权限的分离，并将 latest-owner 从隐含启发式改为显式强基线。

## 20/60 开发结果

数值均为 60 个新 holdout episode 的均值，越低越好。

| actor evidence cell | 方法 | put-back error | regret | contamination | recovery |
|---|---|---:|---:|---:|---:|
| clean | AMG | 0.0594 | 5.067 | 0.0000 | 0.000 |
| clean | PCHMP latest-owner | 0.0594 | 5.067 | 0.0000 | 0.000 |
| clean | slow reversible | 0.1417 | 7.700 | 0.0000 | 0.658 |
| clean | dual-timescale | 0.0594 | 5.067 | 0.0073 | 0.000 |
| ambiguous | AMG | 0.0594 | 5.067 | 0.0000 | 0.000 |
| ambiguous | PCHMP latest-owner | 0.0594 | 5.067 | 0.0000 | 0.000 |
| ambiguous | slow reversible | 0.1365 | 7.533 | 0.0000 | 0.658 |
| ambiguous | dual-timescale | 0.0594 | 5.067 | 0.0073 | 0.000 |
| 15% symmetric misattribution | AMG | 0.1073 | 6.600 | 0.0255 | 0.897 |
| 15% symmetric misattribution | PCHMP latest-owner | 0.1568 | 8.183 | 0.0688 | 1.572 |
| 15% symmetric misattribution | slow reversible | 0.2443 | 10.983 | 0.0432 | 1.757 |
| 15% symmetric misattribution | dual-timescale | 0.1510 | 8.000 | 0.0792 | 1.297 |

开发结论：双时间尺度读出在 clean/ambiguous cell 追平 AMG 和 latest-owner；在错归因
cell 中比 PCHMP latest-owner 略低 0.0057 put-back error，恢复成本下降 0.275，但仍明显
输给 AMG，且 contamination 更高。它闭合了“慢读出造成行动迟滞”的工程缺口，尚未闭合
“错误高置信归因下的鲁棒行动”论文缺口。

## 失败的时间确认探针

在相同新种子的 symmetric-misattribution cell 中，又测试了“最近位置需要两个连续
owner 事件确认，否则快通道折扣”的候选。validation 选择的配置为 fast=0.7、
surviving=0.2、regime-local=0.1、未确认折扣=0.5；holdout 结果为：

- put-back error：0.1776；
- regret：8.850；
- contamination：0.0953；
- recovery：1.783。

该候选比第一版双时间尺度读出更差。原因诊断是：慢记忆也读取同一组被错归因的证据，
等待第二次同源证据不是独立验证。该探针不进入默认搜索空间，但实现保留为后续 CIAV
消融的时间确认控制。

## 下一证伪门

下一版不能继续只调静态混合或确认次数。必须接入一个具有独立结果模型和真实成本的
CIAV micro-verify action，并与 never-act、always-verify、random、max-entropy 在相同
action set 和 privacy gate 下比较。只有扣除观察成本后，dual-timescale + CIAV 同时：

1. clean cell 不劣于 AMG；
2. misattribution cell 的 action utility 优于 AMG；
3. contamination 和 recovery 不恶化；

才值得冻结新的 confirmatory protocol。

机器可读产物：`artifacts/project_two_v04_development/dual_timescale_v0_1.json`。
