# 结构二骨干尺度证伪器：仪器搭建结果（2026-09-02）

> **取代声明（2026-09-02，三轮对抗审核后）**
>
> 本文件 §4 的四臂比较结论（含两处「8/8」计分）**已作废**：当时的度量有三个缺陷——
> 报告的 total variation 恒等于提议覆盖率（粒子权重被丢弃）、ESS 在最后一次重采样之后
> 测量（退化臂反而报满分）、typed 臂逃逸分支的提议密度漏乘 $\varepsilon$。
> §2 的枚举边界与 §3 的三处失败关闭仍然成立。
>
> 修复后的结果见 `structure_two_backbone_falsifier_result_2026-09-02.md`；
> 审核记录见 `../reviews/structure_two_backbone_falsifier_three_round_adversarial_audit_2026-09-02.md`。
> 本文件原文保留、不改写，与本项目对旧粒子证伪器的处理一致。
>
> 另有三处已确认的事实错误：§5 的「8 个 $G{=}1$ cell」应为 4 个；§4 的「16–45 倍提议生成」
> 按同 cell 对照口径实为 5.2–22.6 倍；§6 记录的源码 SHA-256 是 bring-up 运行时刻的版本，
> 之后代码已加入扫描入口。

---

协议：`structure-two-backbone-falsifier@0.1`
证据等级：**instrument bring-up（仪器搭建）；不是方法收益证据**
artifact：`artifacts/project_two_v04_development/structure_two_backbone_falsifier_bringup_v0_1.json`
源码：`src/cpswm/system/evaluation_operations/structure_two_backbone_falsifier.py`
源码 SHA-256 前缀：`22dfbb49ff605723128be1c7ac42eeca`
测试：`tests/test_structure_two_backbone_falsifier.py`，26 项通过；ruff、ruff format、
strict mypy 均通过。

旧的 `structure-two-exact-enumeration-falsifier@0.1` 未被删除或改写，继续保留为审计链。

## 1. 结论先说

本轮**只**证明：协议第 1、2、3、6 节要求的仪器可以运行，并且旧仪器的三处结构性缺陷
在新仪器里失败关闭。它**不**证明 RB 化有收益、类型化修订有收益，或结构二优于任何基线。
粒子预算固定为 24、只用了 1 个种子、4 个场景格，所有 TV 都很大——这是仪器判别力的证据，
不是方法质量的证据。

## 2. 实测枚举边界（协议 §1.2）

不预设任何 $G$ 不可枚举，边界由实测决定，state budget = 2,000,000：

| $G$ | 枚举状态总数 | 其中 admissible | 预算内可枚举 | 计数耗时 | 精确后验耗时 |
|---:|---:|---:|:---:|---:|---:|
| 1 | 990 | 948 | 是 | 0.001 s | 0.010 s |
| 2 | 988,200 | 901,008 | 是 | 0.95 s | 14.3–17.2 s |
| 3 | > 2,000,000 | — | **否** | 2.00 s（触顶） | 未运行 |
| 4 | > 2,000,000 | — | **否** | 2.00 s（触顶） | 未运行 |

分支不是干净的幂：reactivation 目标只有在阶段退役后才存在，所以 $G$ 增加时分支因子本身
也在增长。$G=1 \to 2$ 的增长约 998 倍。

## 3. 三处旧缺陷的失败关闭

| 旧仪器缺陷 | 新仪器的处理 | 验证 |
|---|---|---|
| "近似"方法内部对全部 360 个状态排序 | `exact_posterior` 带 `caller_role`，非 `EXACT_ORACLE` 直接抛 `FullEnumerationForbiddenError` | 两项负向测试（`APPROXIMATE_ARM`、`LADDER_DIAGNOSTIC`）通过 |
| `statistic_state_ref` 是占位字符串，$S_t$ 不存在 | `AnalyticBlock` 真实维护 $(\alpha,A,b,\Lambda,\xi)$，由观测触发更新，$\theta$ 与类别参数解析边缘化 | 移除解析更新使 `log_marginal` 改变；RBPF 与 sampled-$\theta$ PF 的后验 TV > 0 |
| 状态静态、$r_t$ 由场景标志硬编码 | $\chi_t$ 的七个分量随 $G$ 真实增长 | `test_every_particle_variable_grows_with_gaps` 逐项断言 |

成本口径的翻转是本轮最直接的证据：

| 臂 | $G=2$ 唯一状态评分数 | 提议生成次数 | 墙钟 |
|---|---:|---:|---:|
| exact oracle | **901,008** | 0 | 14.3–17.2 s |
| sampled-$\theta$ PF | 3–6 | 48 | 0.001 s |
| RBPF | 7–23 | 48 | 0.001 s |
| typed RBPF | 14–21 | 761–1084 | 0.033–0.047 s |

旧仪器里两个"近似"方法的评分数（744、502.6）都 ≥ 全枚举本身（360）。新仪器里近似臂的
评分数比精确臂低四到五个数量级，而**提议生成成本被单独记账**——这正是协议 §3.4 要求的
accuracy–compute curve 的两个横轴。

## 4. 四臂在 $G=1,2$ 上的判别力（不是结论）

固定粒子预算 24、种子 11、四个场景格（高归因歧义 × 恶劣迟到反馈），共 8 个 cell：

- **B → C（RB 的位置）**：RBPF 的 TV 在 8/8 个 cell 中不劣于 sampled-$\theta$ PF；
  未决质量的校准差距更明显（例如 $G{=}2$ 的 `0011` 格：`0.9979` vs `0.2725`）。
- **C → D（类型化修订的位置）**：typed RBPF 在 8/8 个 cell 中 TV 最低
  （$G{=}1$：`0.1974–0.8267`；$G{=}2$：`0.6057–0.9360`），代价是 16–45 倍的提议生成次数。
- **真值覆盖**：$G{=}1$ 时 typed 臂在 2/4 格保留真值，另两臂 0/4；$G{=}2$ 时三臂
  全部 0/4——预算 24 对 901,008 个状态本来就不够，这条只说明真值覆盖是本仪器的
  主要压力指标。

**这些数字不构成任何方法主张。** 它们说明四臂在同一仪器上会分开，可以被测量。

## 5. 已知不足（必须在下一轮修）

1. **行动读出在 $G=1$ 上没有判别力**：`chain_action` 取 OWNER cell 的 Dirichlet 预测 bin，
   单次观测下几乎所有链给出同一动作，8 个 $G{=}1$ cell 的 action regret 全为 0。
   $G{=}2$ 开始判别（sampled-$\theta$ PF 在一个 cell 上 regret `0.9431`）。
   这是 2026-08-28 审核指出的"读出缺乏判别力"问题的同一形态，须在 $G$ 更大时复核，
   并考虑让读出同时消费 actor、instance 与 cause。
2. **协议任务 7（迟到纠正四臂）尚未实现**：`local_rejuvenation` / `full_rerun` /
   `reweight_only` / `append_only` 的对照还没有运行。
3. **协议任务 8（$H_t\times C_t$ 联合性死亡测试）尚未实现。**
4. **粒子预算、重采样策略、回春核、可微策略仍为 `unresolved`**，本轮没有触碰。
   typed 臂当前用 0.10 的先验逃逸混合保证支持覆盖，这个数字是实现默认值，不是冻结选择。
5. 只有 1 个种子；正式运行需要多种子、方差和失败种子清单（协议 §4）。

## 6. 下一步

按协议 §8 的顺序，下一步是任务 10 的粒子预算扫描（$K=8,16,24,48,96$），
在 $G=1,2$ 上画出第一条 accuracy–compute curve；这也是判断
"RB 是否降低方差或计算成本"的第一份真实数据。$G\ge3$ 需要在另一台机器上跑
枚举边界与大预算实验。
