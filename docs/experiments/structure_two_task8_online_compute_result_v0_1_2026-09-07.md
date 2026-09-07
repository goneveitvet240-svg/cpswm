# Structure Two Task 8 Learned Online-Compute Result v0.1

**运行日期：** 2026-09-07  
**工件：** `benchmarks/structure_two/structure_two_task8_online_compute_v0_1.json`  
**协议：** `structure-two-task8-learned-online-compute@0.1-development`  
**证据层级：** D0 development pre-death test（开发预死亡测试）

## 一句话结论

equal-compute fairness gate（等算力公平门）通过，但 learned joint（学习式联合）在三个冻结算力点都没有优于 learned matched two-stage（学习式匹配两阶段）；Task 8 没有出现严格开发信号。按照预注册处置，当前停止扩大昂贵外部实验，先重做 joint mechanism（联合机制）。这不删除结构二的任何能力。

## 主结果

成本越低越好。差值定义为 `matched two-stage cost - joint cost`；正值才代表 joint 更好。

| 基础宽度 | 每臂有效参数 / 单样本推理乘加 | joint 平均成本 | matched two-stage 平均成本 | 差值 | 校正后单侧下界 | joint 相对改善 | 严格信号 |
|---:|---:|---:|---:|---:|---:|---:|---|
| 8 | 64 | 0.241944 | 0.215607 | -0.026337 | -0.035848 | -12.22% | false |
| 16 | 128 | 0.238819 | 0.205125 | -0.033695 | -0.044877 | -16.43% | false |
| 32 | 256 | 0.171358 | 0.143572 | -0.027786 | -0.036772 | -19.35% | false |

三个点的有效参数、训练乘加数和推理乘加数均逐臂完全相等；`fairness_gate_passed=true`。所有 arm × width 的 validation-only（仅验证集）选参都选择了 learning rate 0.1、L2 0.0，选择回执在确认结果前冻结并绑定哈希。

## 辅助诊断

information-restricted factorized（信息受限因式分解）相对 joint 的平均成本差在三个宽度分别为 `+0.008663`、`-0.064949`、`+0.000765`，方向不稳定，不能支持稳定的 interaction necessity（交互必要性）主张。全 ambiguity + delayed feedback + open-world actor（高歧义、延迟反馈、开放世界参与者）单元上，matched two-stage 的平均成本在三个宽度也都低于 joint。

因此本轮不能把失败归咎于“two-stage 获得了更多参数或更多在线计算”。在当前 D0 学习器、分组标签、特征投影和动作端点下，结构化 two-stage 的归纳偏置更有效；这只是当前实现的诊断，不是对所有联合模型的普遍不可能性证明。

## 执行处置

- 已执行：冻结工作区检查点 `81e5015`；
- 已执行：阻止 Task 8 正式通过、外部有效性、全系统护栏完成和七算子消融授权；
- 已执行：把下一状态设为 `DEFAULT_METHOD_REDESIGN_BEFORE_EXPENSIVE_EXTERNAL_SCALEUP`；
- 暂停：基于当前 joint 机制继续扩大 Task 10–13、ProcTHOR 大规模采集或 D2 正式确认；
- 保留：D2 timing pilot（真机时序试跑）的设备、同步和记录格式准备可以并行；
- 下一方法决策仍需明确选择，不在本轮悄悄替用户选定：可比较 structured joint parameterization（结构化联合参数化）、shared-trunk interaction residual（共享主干交互残差）或 stateful joint inference（有状态联合推断），然后重新冻结同等算力测试。

## 验证与审核

- runner 先进行逐样本语义复算，再进行 fresh-source replay（当前源码重放）后才写入工件；
- 定向测试：`10 passed`；
- 覆盖攻击：重复种子、重签名但非优胜的验证选参、预算映射伪造、确认行缺失、动作成本伪造、完整正向前沿伪造、正式晋级伪造、源码包替换；
- 本轮仍是 partial adversarial coverage（部分对抗覆盖），没有独立历史 custody（保管链）、D1 回放、D2 真机或完整 owner-contamination / recovery / safety / privacy（主人污染、恢复、安全、隐私）护栏。

所以：`any_strict_development_signal=false`，`task_8_formal_passed=false`，`seven_operator_ablation_authorized=false`。

## 运行后范围复核

运行后科学设计复核确认：本轮精确匹配的是乘加量，没有实测物理延迟；确认集高压因子单元也不是真正的分布偏移干预；9 格分组标签不是完整结构二状态空间。因此本轮只否证当前 direct joint 的便宜等乘加切片，不能外推成完整 Task 8 或联合建模的普遍失败。详见 `docs/reviews/structure_two_task8_online_compute_postrun_audit_2026-09-07.md`。
