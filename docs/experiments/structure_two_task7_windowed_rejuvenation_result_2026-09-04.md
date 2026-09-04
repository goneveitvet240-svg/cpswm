# 结构二 Task 7：真正窗口式回春实现与重跑结果

日期：2026-09-04
协议：`structure-two-windowed-late-correction@0.2`
证据等级：**D0 synthetic development evidence（D0 合成开发证据）**
冻结配置：`configs/project_two_experiments/structure_two_task7_windowed_rejuvenation_v0_2.json`
产物：`benchmarks/structure_two/backbone_b_repairs_2026_09_04/task_7_windowed_rejuvenation_v0_2.json`

## 结论先行

旧的“从纠正点重跑完整后缀”已被替换。当前 `local_rejuvenation`（局部回春）在原始前向阶段保存
左右边界 checkpoint（检查点）；纠正到达后先做 constant-cost likelihood-ratio reweighting
（常数成本似然比重加权），并在解析块中撤回旧观测、加入修正观测，
只在冻结窗口内做 single-site Metropolis-within-Gibbs（单点吉布斯内 MH）提议。候选窗口必须重新
接回完全相同的右边界状态，窗口外 gap 不被提议或重放；解析块只对受影响 cell 做精确
`downdate/update`（撤销／更新）。不可桥接或非有限比率会写入回执并显式回退 `full_rerun`。

因此，**窗口实现门通过**；但协议 Task 7 的完整科学门仍失败：注册运行中局部臂的平均 owner
contamination（所有者污染）比完整重跑高 `0.0048784`，且真链 revision recovery（修订恢复率）
低 `0.20`。不得把“实现完成”写成“Task 7 整体通过”。

## 冻结运行

- `G=3`，纠正索引 `1`，窗口宽度 `1`；
- 5 个 scenario seed × 3 个 replicate seed，共 15 个配对重复；
- `adaptive_typed_rbpf`，`K=384`；
- actor marginal TV（行动者边缘总变差）容差 `0.10`；
- artifact content SHA-256：`42dca579df64fdfa32ffb17f163a53e8d9d2b73fdc05b647c106aede4ba74c88`。

| 指标 | local rejuvenation | full rerun | 判定 |
|---|---:|---:|---|
| 平均 actor marginal TV（对 full） | `0.009068` | `0` | 通过；单次最大值 `0.027911 < 0.10` |
| 平均 marginal elementary evaluations | `69,082.7` | `128,014.7` | 通过；约为 full 的 `54.0%` |
| 注册运行 fallback rate | `0` | — | 通过 |
| 平均 owner contamination｜resolved | `0.013542` | `0.008663` | **失败；差 `+0.004878`** |
| revision recovery rate | `0.1333` | `0.3333` | **低 `0.20`，保留为失败信号** |

`window_implementation_passed=true`，但 `task_7_passed=false`，最终 verdict 为
`WINDOW_IMPLEMENTATION_PASS_CONTAMINATION_NONINFERIORITY_FAILED`。

## 成本与完整性口径

- `initial_*` 是纠正到达前不可省略的原始前向成本；
- `marginal_*` 只记录纠正到达后触发的工作；
- checkpoint bytes（检查点字节数）属于初始阶段；
- 固定窗口从 `G=3` 增至 `G=10` 的攻击测试中，局部核窗口目标更新不超过 `2K=128`，且不访问
  固定后缀；完整重跑的基础似然工作则随 `G` 线性增长；
- checkpoint 内容、源观测或解析状态不匹配时 fail closed（失败关闭）；checkpoint 只是进程内源绑定，
  不是外部历史真实性锚点。
- 对抗测试覆盖“窗口位于长序列中部且固定后缀改变最终 regime state（阶段状态）”的情况；局部核
  必须令 live terminal state、完整链和最终 boundary checkpoint 三者一致，不能停在窗口右边界。

## 主张边界

Task 7 只定义修订窗口、checkpoint、窗口外不变、重加权和 fallback 语义。这里采用的单点 MH
只是 Task 12 的候选核，**不等于 Task 12 已选择 rejuvenation kernel（回春核）**。本结果也不证明
外部有效性，不授权可信七算子系统消融。
