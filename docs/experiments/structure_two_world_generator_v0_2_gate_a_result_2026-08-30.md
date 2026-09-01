# 结构二世界生成器 v0.2：Gate A 结果

日期：2026-08-30  
协议：`structure-two-world-generator-gate-a@0.2`  
manifest SHA-256：`88fbf4a47601401b0b95642c99d2bf0644a8d97ac5ae03171cd60bbfabc62cd4`  
artifact content SHA-256：`e1dd5ad4be7d01102755417d86f8e0f653c3af8a9d4fecf4d824df08a2898764`

## 判决

**Gate A 未通过；method comparison（方法比较）继续冻结。**

12 个 validation worlds（验证世界）全部不同，共运行 72 条 method-free rollout（无方法轨迹）。11 项冻结判据中 10 项通过，唯一失败项是 search contextual fallback（搜索情境回退）相对 last observed location（最后观测位置）的增益不足。

验证和 deterministic recomputation（确定性复算）得到相同的 content SHA-256。sealed holdout（封存留出集）没有打开，train worlds（训练世界）没有生成，任何 CPSWM 或邻居方法都没有运行。

## 世界等权指标

| 靶 / 指标 | 数值 |
| --- | ---: |
| put-back sticky error | 0.674439 |
| put-back rolling global-mode error | 0.656919 |
| put-back rolling context-mode error | 0.597820 |
| put-back aggregation gain | 0.076619 |
| put-back aggregation gain 95% world-bootstrap CI | [0.036489, 0.112596] |
| put-back context gain | 0.059098 |
| put-back context gain 95% world-bootstrap CI | [0.014340, 0.100276] |
| owner-observed target recurrence | 0.424905 |
| search last-observed error | 0.485902 |
| search contextual-fallback error | 0.472514 |
| **search contextual-fallback gain** | **0.013388** |
| search contextual-fallback gain 95% world-bootstrap CI | [0.004846, 0.023249] |
| unobserved location-change rate | 0.822337 |

冻结阈值要求 search contextual-fallback gain 至少为 `0.020000`。实测为 `0.013388`，少 `0.006612`，所以该项失败。虽然它的置信区间下界大于零，说明这条平凡规则有稳定的正增益，但这不允许在结果出来后把冻结门槛降低。

## 通过的结构修复

v0.2 已经修掉旧基准最关键的两类退化：

- world diversity（世界多样性）：12 / 12 个 validation world hash 不同，不再把不同 observation mask 当成不同世界。
- habit as distribution（习惯作为分布）：看见一次主人放置与习惯众数相同的比例只有 0.424905；sticky 规则不能再复现 put-back target。

放回靶上，rolling aggregation（滚动聚合）和 calendar context（日历情境）均产生了冻结标准要求的 action-relevant information（行动相关信息），且最佳平凡情境规则之后仍保留 0.597820 的误差空间。

## 唯一失败的机制解释

当前 search target（搜索靶）是所有人物和未知事件共同决定的“此刻真实位置”，但冻结的情境回退只总结 owner habit（主人习惯）。主人习惯对不可见时的搜索有一点帮助，却无法充分预测 guest relocation（访客移动）和 open-world hidden event（开放世界隐藏事件）。因此：

- 搜索确实不是 last-observed 可吃掉的平凡任务：其误差为 0.485902，未观测位置变化率为 0.822337；
- 但本轮冻结的候选 action-relevant context（行动相关情境）只带来 1.34 个百分点的增益，没有达到预注册的 2 个百分点。

这不是方法失败，因为方法尚未运行；它是 v0.2 search target / frozen trivial-rule pair（搜索靶与冻结平凡规则配对）未过预注册门。

## 当前边界

v0.2 manifest 和本次失败结果必须保留，不能原地调参后覆盖。如果继续，下一版必须叫 v0.3，并在运行前明确选择一种可证伪的修改：要么给搜索回退加入真正与访客和未知事件相关的可见情境，要么重新论证“情境回退至少提升 0.02”是否属于搜索靶必要条件。两种做法代表不同科学主张，不能在本结果之后偷偷代替用户选择。

在新的预注册版本通过 Gate A 以前，结构二方法比较仍不恢复。
