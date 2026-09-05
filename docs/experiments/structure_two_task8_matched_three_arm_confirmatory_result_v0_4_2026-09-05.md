# 结构二 Task 8：matched three-arm confirmatory v0.4

协议：`structure-two-relative-probability-joint-coupling@0.4`
冻结配置：`configs/project_two_experiments/structure_two_task8_relative_probability_coupling_v0_4.json`
正式工件：`benchmarks/structure_two/backbone_b_repairs_2026_09_04/task_8_matched_three_arm_confirmatory_v0_4.json`

## 结论

**FAIL。** joint、factorized 与 matched two-stage 三臂共享相同 observations（观测）、完整
posterior table（后验表）、state budget（状态预算）及每臂三个 validation candidates。各臂只用
独立 validation seeds `101/103/107` 调参，均选择温度 `0.75`；选择回执在读取 confirmatory
units 前冻结。

confirmatory seeds 为 `211/223/227/229/233`。每 seed 的 8 个因素 cells 先求配对均值，CI
只在 5 个独立 seed clusters 上 bootstrap，不能把 40 个相关 cells 伪作 40 个独立样本。

- mean(`two_stage_cost - joint_cost`) = `-0.000858330`；
- one-sided 95% paired bootstrap lower bound = `-0.002058701`；
- 预注册严格门要求 lower bound `> +0.001`，因此失败。

matched two-stage 在 temperature `(1,1)` 时以 `p(C)p(H+Z|C)` 代数重构 joint posterior。这是
刻意采用的 strongest falsifier（最强证伪器），不是对经验 learned pipeline（学习管线）效能的
外推。历史 v0.3 文件与工件保持不变；由于它没有 independently tuned matched two-stage 及配对
confirmatory CI，只能标记为当前三臂问题的失败历史，不能沿用其旧 D0 pass。

本结果不授权可信七算子消融。
