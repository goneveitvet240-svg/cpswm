# 结构二 Task 7：conditional-target 窗口回春 v0.4

协议：`structure-two-windowed-late-correction@0.4`
冻结配置：`configs/project_two_experiments/structure_two_task7_windowed_rejuvenation_v0_4.json`
正式工件：`benchmarks/structure_two/backbone_b_repairs_2026_09_04/task_7_windowed_rejuvenation_v0_4.json`

## 结论

**FAIL。** 阈值仍为逐 belief axis TV（信念轴总变差）`<= 0.1`、action TV（行动总变差）
`<= 0.1` 且 Bayes action（贝叶斯行动）一致；owner contamination（所有者污染）门未删除。

- 完整 `2x2x2x2` 场景因素矩阵共 16 cells，四种 correction treatments（纠正处理）逐 cell
  配对覆盖。
- same conditional target（同一条件目标）参考验证及 runtime check 均通过；参考值直接比较同一
  corrected observations、相同 window 外链及左右 boundary 下的
  `chain_log_target(proposed)-chain_log_target(current)`。
- terminal responsible actor（末端责任人）已进入充分状态缓存；action readout 不读取长后缀。
- suffix 长度 `8/64/256` 时窗口 target work 均为 `54`、live items 均为 `37`、reachable
  overlay bytes 均为 `314`，suffix read/copy/rehash 均为 `0`。
- 但 local-vs-full 的 mean/worst max-axis TV 为 `0.244625/0.750140`；action TV 为
  `0.112464/0.398628`，selected-action match rate 为 `0.9375`，均未满足冻结等价门。
- local-minus-full contamination 为 `+0.00291836`，污染非劣门亦失败。

任何 non-self proposal 缺失、不可桥接、非有限密度或 conditional-target mismatch 都产生显式
fallback receipt（回退回执）并执行 full replay（完整重放）；fallback 不能被计为窗口实现通过。

本文与 v0.4 工件不授权可信七算子消融，也不选择 Task 12 kernel。v0.3 历史文件未覆盖。
