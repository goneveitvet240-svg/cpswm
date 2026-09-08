# 结构二 Route C：完整联合状态回放反馈环 v0.1

日期：2026-09-07  
协议：`structure-two-stateful-full-joint@0.1-development`  
证据等级：**D0 development only（仅 D0 开发证据）**

## 结论先行

Route C 已经不再用 3×3 九分类代理冒充 joint（联合模型）。每个存活粒子跨时间联合维护
`event chain / ordered actor roles / instance association / change cause / habit regime /
run length / revision lineage` 七个离散状态轴，并按 `(actor, regime)` 维护 Dirichlet、ridge/RLS
natural statistics（岭回归/递归最小二乘自然统计）和 information-form belief（信息形式信念）
三个 Rao–Blackwellized blocks（拉奥–布莱克韦尔化统计块）。

工程结论是：完整状态能贯穿提议、重要性校正、反馈修订、读出和可逆账本，matched
full-state factorized（匹配的完整状态因式分解）对照也已建立公平比较条件。科学结论仍是负面：
joint 与 factorized 的行动遗憾完全打平，并比独立调参 AMG 差 `+0.072917/step`。联合交互只在
`13/62` 个可读出步骤造成非零动作后验差异，平均 total variation（总变差）仅
`0.0004586`，最大 `0.0044314`，最终动作分歧为 `0/62`。

当前环是 **frozen replay action-bound revision loop（冻结回放、动作绑定的修订环）**：最终
Route-C 动作被写入修订轨迹，修订后的联合状态会影响后续动作；但环境轨迹不会因该动作重新生成，
所以尚未建立 interactive environment closed loop（交互环境闭环）。

## 当前开发数据与比较口径

- 2 个 validation seeds（验证种子）只用于从 `{0.2, 0.33, 0.5}` 选择 AMG 参数；三个候选的
  validation action regret（验证行动遗憾）均为 `0.09375/step`，按冻结 tie-break 选 `0.2`。
- 4 个 development holdout seeds（开发保留种子），共 64 个行动步；不是确认性实验。
- 完整 D0 数据共 6 个 synthetic episodes（合成 episode）、96 步、70 条反馈；观测覆盖率
  `70/96 = 0.729167`，26 步缺观测。
- 真实传感器校准、机器人位姿协方差、动作后目的地观测均为 `96/96` 缺失，因此数据审计的
  `ready=true` 只表示 schema/replay（模式与回放）可用，不表示外部科学证据可用。

| 方法 | 放回错误率 | 搜索错误率 | 行动遗憾/步 | 搜索遗憾/步 | owner contamination | unknown Brier |
|---|---:|---:|---:|---:|---:|---:|
| stateful full joint | 0.0625 | 0.421875 | 0.244792 | 0.182292 | 0 | 0.202267 |
| matched full-state factorized | 0.0625 | 0.421875 | 0.244792 | 0.182292 | 0 | 0.202298 |
| independently tuned AMG | 0.0625 | **0.140625** | **0.171875** | **0.109375** | 0 | **0.152500** |

`joint - factorized` 的行动遗憾为 `0`；`joint - AMG` 为 `+0.072917/step`，正数表示 joint 更差。
joint 的 unknown Brier 只比 factorized 低约 `0.0000313`，在 4 个同生成器开发保留 episode 上
没有可解释为优势的证据。

## 公平环境现在建立到了什么程度

joint 与 matched factorized 两臂现在逐步共享：机器人可见输入、七轴状态访问、完整正质量
proposal support（提议支持集）、训练好的 neural proposal（神经提议器）、`K=24` 粒子预算、
每步实际 `24` 次 target-score evaluation（目标评分）、共同随机数、重采样次数、反馈流、RGRC
策略和 action readout（动作读出）。唯一预期差异是 cross-axis interaction potentials（跨轴
交互势）是否置零。

旧实现把每父粒子的候选截为 top-96，首步会丢掉约 `7.21%` 提议质量；现在改为枚举全部正支持。
当前回放每步总支持规模为 `468–13,032`，每父粒子为 `312–543`，但只对共同随机数抽到的
24 个候选计算目标分数。公平回执现在记录实际评分数，不再用“父粒子数 × 96”虚报计算量。

公平审计区分两种哈希：support schema（支持模式）必须相同；support content（支持内容）保留
溯源但不被误当成前处理公平条件，因为处理产生的后验状态和修订身份本来可以不同。当前两臂的
可见输入、支持模式、预算、模型与随机数逐步匹配，fresh replay（新鲜源码回放）也通过。

这只证明 joint 与 full-state factorized 的机制比较公平。AMG 没有获得同构的完整内部状态，仍是
独立调参的外部行动基线，不能称为 state-access matched（状态访问匹配）对照。

## 七算子能运行，但尚不能说七者都贡献了动作

开发保留运行中，两臂七个算子都有回执且都至少执行过一次；联合臂共有 370 条算子回执，其中
280 条标记执行、252 条标记状态变化。CIAV 执行并改变状态 10 次；RGRC 执行 45 次、改变隔离账本
17 次。

但是 RGRC 的 17 次变化全部是 `quarantine`，`promote=0`、`corrected_revision=0`，4 个 episode
终态都没有 active long-term memory（活跃长期记忆）。因此：

- 可以说算子调用、输入输出类型、哈希链和状态转移能正常运行；
- 可以说三个 RB blocks 都进入读出，单元因果测试表明分别改变它们会改变分布；
- 不可以说七算子已分别对最终动作形成贡献；
- 不可以用 contamination=0 证明 RGRC 成功挡住污染，因为本轮根本没有长期 promote，这个零值
  部分是 vacuous success（空洞成功）。

## 为什么科学上仍会输

1. **决策间隔没有被跨过。** joint 改变了少量概率，但 TV 最大只有 `0.0044314`，没有改变
   argmax 或搜索排序，因而付出了联合建模难度却没有得到行动收益。
2. **交互势仍是手工系数。** 当前六个 cross-axis coefficients（跨轴系数）没有从独立训练数据
   学出，也没有经过预注册选择；“完整状态”已实现，“有效联合机制”仍未实现。
3. **粒子预算对高维联合空间偏紧。** 支持规模最高 13,032，而每步只抽取和评分 24 个候选。
   虽然重要性校正现在数学上有完整支持，有限样本方差仍可能抹掉联合优势。
4. **D0 对联合关系的压力不足。** 只有 7 个 handoff truth events（交接真值事件），且两个
   family 标签分别绑定 validation/test 生成分区；该数据足以查接口和回放，不足以检验多主体、
   身份歧义、复发 regime 与行动反馈的联合收益。
5. **长期闭环没有真正激活。** RGRC 没有 promote，环境也不会响应动作，所以完整结构的长期状态
   收益在这次 D0 中没有被调用出来。

## “污染”在这里的准确含义

owner-habit contamination（主人习惯污染）指 guest、unknown actor、身份错配或错误机制的事件被
错误写入 owner 的长期习惯统计，随后把动作读出推向访客/未知事件的位置。当前三臂该指标都是 0，
只能说明这批回放没有观测到这种错误结果。由于 Route C 的 RGRC 没有一次正式写入，这个零值不能
区分“门控正确”与“根本未学习”。科学上需要同时报告 contamination、正确 owner 写入的 recall
（召回）以及动作效用，不能只追求零污染。

## 两轮对抗审核后的声明边界

允许声明：完整七轴联合状态和三个 RB blocks 已被实现；回放反馈能修订完整状态并被后续动作消费；
joint 与 full-state factorized 的前处理比较条件已匹配；两轮 25 项定向测试、全仓工程审核和两次
checkpoint fresh recomputation 通过。

不允许声明：joint 优于 factorized、结构二优于 AMG、RGRC 长期收益成立、七算子贡献成立、交互环境
闭环成立、Task 8 正式通过、真实家庭或机器人外部有效性成立。

详细攻击矩阵见 `docs/experiments/structure_two_stateful_full_joint_two_round_adversarial_audit_2026-09-07.md`。

## 复现

```bash
PYTHONPATH=src uv run python apps/evaluation_runner/run_structure_two_stateful_full_joint.py

PYTHONPATH=src uv run python apps/evaluation_runner/run_structure_two_stateful_full_joint.py \
  --verify benchmarks/structure_two/structure_two_stateful_full_joint_v0_1.json

uv run pytest -q \
  tests/test_structure_two_stateful_full_joint.py \
  tests/test_structure_two_stateful_full_joint_adversarial.py
```
