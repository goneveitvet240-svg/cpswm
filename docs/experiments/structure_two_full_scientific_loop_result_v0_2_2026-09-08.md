# 结构二 Route C：动作响应完整科学闭环 v0.2

日期：2026-09-08  
协议：`structure-two-full-scientific-loop@0.2-development`  
证据等级：**D0 action-responsive development only（仅动作响应合成开发证据）**

## 结论先行

本轮在没有删除任何结构二能力的前提下，补齐了四个工程缺口：

1. action-responsive environment（动作响应环境）：执行的 location action（位置动作）会改变环境隐藏状态，下一步观测来自改变后的状态；每一步同时保留共享随机数下的 factual/counterfactual potential outcome（事实/反事实潜在结果）。
2. learned cross-axis interaction（可学习跨轴交互）：六个交叉特征在 train seeds（训练种子）上学习，L2 只在 validation seeds（验证种子）上选择，随后冻结并在未见过的 development evaluation seeds（开发评估种子）上运行。
3. RGRC 正反例激活：正例真实走过 `quarantine → promote → retract → corrected_revision → retract`，负例覆盖 guest、unknown、identity mismatch 和不稳定 owner。
4. seven-operator neutralization ablation（七算子中和消融）：每次仍实例化并执行完整框架，只把一个算子的作用替换为注册的 neutral element（中性元）；其余六个算子、七轴状态、三个 RB blocks、神经提议、粒子预算、种子和潜在结果随机数全部保留。

工程闭环已经成立；科学优势仍未成立。joint（联合臂）和 matched full-state factorized（匹配的完整状态因子化臂）在 3 个新评估种子、27 步上的 action regret（行动遗憾）均为 `0.555556/step`，owner-habit contamination（主人习惯污染）均为 `0.333333`。学习式联合项在 `27/27` 步改变动作后验，但平均 TV（总变差距离）只有 `0.00001273`、最大 `0.00026848`，没有改变任何一步最终动作。

因此本轮可声明“完整对象可运行、动作真正回写环境、学习式交互进入推断、RGRC 正反例可达、七个中和臂可审计”，不能声明“joint 胜过 factorized”“七算子均有行动贡献”或“结构二已经胜过强基线”。

## 1. 完整范围没有被缩小

每个闭环臂继续维护：

- 七个联合状态轴：`event_chain / ordered_actor_roles / instance_association / change_cause / habit_regime / run_length / revision_lineage`；
- 三个 Rao–Blackwellized blocks（拉奥–布莱克韦尔化统计块）：Dirichlet location、ridge/RLS natural statistics、information-form belief；
- 七个算子：OPCEU、ORRER/CHEH、PCHMP、CF-BOCPD、RGRC、CCRR、CIAV；
- open-world unknown（开放世界未知人物）、multi-actor ordered roles（多人物有序角色）、recurrent regimes（复发阶段）、reversible attribution（可逆归因）和 embodied feedback（具身反馈）。

中和不是删除算子，也不是让其他模块少拿输入。每个中和臂仍产生该算子的 executed receipt（执行回执），但把它的独有作用改为中性元：

| 中和算子 | 被替换的独有作用 | 注册中性元 |
|---|---|---|
| OPCEU | 观测统计写入 RB cells | 不更新统计量，保留事件/实例输入路径与回执 |
| ORRER/CHEH | 反馈似然重加权与修订 lineage 扩展 | 消费并校验反馈，但似然取 identity（恒等）且不改状态 |
| PCHMP | actor/mechanism/role/identity 主势与跨步保持项 | 对应势取 1，保留候选与完整轴读取 |
| CF-BOCPD | cause/run-length 证据与 cause persistence | cause 势取 1，去除其转移加成 |
| RGRC | 隔离、晋升、修正、撤回与读出混合 | 不改账本、不把账本分布混入动作读出 |
| CCRR | regime 决策势与 active-regime persistence | regime 势取 1，去除其转移加成 |
| CIAV | 验证证据对 actor posterior 的更新 | 记录验证动作，但观测后验保持原值 |

## 2. 动作响应环境与公平比较

环境协议为 3 个 evaluation seeds × 9 步。每个 episode 有三处 owner/guest/unknown 或 identity/regime 外生变化，并对每个位置动作使用同一 `action-success` 随机数。动作成功率冻结为 `0.85`。

逐步证据链检查了：

- 选中动作必须是动作分布的确定性 argmax；
- 成功时 `post_action_location == selected_action`，失败时保持原位置；
- 同一个成功随机数下换成另一动作会得到不同 post-action state（动作后状态）；
- 下一步 `observe()` 从动作后的隐藏状态读取；
- 每一步反馈产生唯一 correction revision（纠正修订），完整 joint/factorized 状态在后续动作前消费该修订；
- 环境 trace、算子 receipt chain（回执链）、RGRC ledger chain（账本链）、汇总指标和消融差值都由原始记录重算。

joint 与 matched factorized 共享初始隐藏状态、外生事件日程、潜在结果随机数、七轴状态访问、K=24 粒子预算、完整正支持候选、神经提议器、六个交叉特征计算和学习模型读取。唯一注册差异是 joint 使用学到的 cross-axis log potential（跨轴对数势），factorized 把最终系数置零。

这是机制识别所需的 matched comparison（匹配比较）；它不等于与 AMG 等外部强基线完成状态访问匹配，也不等于独立托管。

## 3. 可学习跨轴交互

六个预注册特征为：

1. actor cause × handoff；
2. identity cause × instance mismatch；
3. habit cause × regime change；
4. handoff × receiver binding；
5. owner × target instance × habit；
6. unknown actor × regime change。

数据划分严格分离：train seeds=`811,821,823`，validation seeds=`827,829`，evaluation seeds=`839,853,857`。评估真值不进入训练或选择。L2 网格为 `{0, 0.01, 0.1}`，validation loss 最小者为 `L2=0`；冻结权重为：

```text
[0.597470, 0.242539, 0.617689, 0.584972, 0.613792, -0.001935]
```

train loss=`0.4448856219`，validation loss=`0.4546639835`，样本数分别为 `10530/7020`。第二次对抗审核发现旧版不同 seed 只替换位置 UUID，训练/验证样本实质同构；现已让证据强度随 seed/step 确定性变化，并用不读取任务真值的 deterministic coverage cycle（确定性覆盖循环）推进训练环境。训练/验证样本哈希现在不同，验证器会从源码重建样本并核对哈希与数量。它修复了无效划分，但仍不是泛化优势证据。

## 4. RGRC 正反例及主闭环激活

独立状态机夹具的正例序列为：

```text
quarantine, quarantine, promote, quarantine, retract, corrected_revision, retract
```

四个负例全部拒绝正式写入：guest actor、unknown actor、identity mismatch、仅出现一次的不稳定 owner。稳定性按 RGRC 自己拥有的 `(owner, target instance, regime, location)` 连续签名计算；完整粒子的 cause 变化不会再错误清空这个门，但只出现一步仍只能 quarantine，不能 promote。

主动作闭环不再是“永远进不了 RGRC”：3 个评估种子在 joint 和 factorized 两臂都出现了正式 `promote`。中和 RGRC 后账本保持 `GENESIS` 且不参与读出。

这说明正路径已可达，但仍未证明 RGRC 带来最终行动收益：本批次 RGRC 中和使 mean posterior TV=`0.1083219`、max TV=`0.1857614`，却仍没有改变任何一步 argmax 动作，行动遗憾差为 0。

## 5. 闭环结果

| 方法 | put-back error | search regret/step | action regret/step | owner contamination | unknown Brier |
|---|---:|---:|---:|---:|---:|
| stateful full joint | 0.555556 | 0 | 0.555556 | 0.333333 | **0.00225362** |
| matched full-state factorized | 0.555556 | 0 | 0.555556 | 0.333333 | 0.00225462 |

这里的 contamination=`0.333333` 不是数据脏或代码串线。它表示 guest/unknown/identity 等非 owner 事件把当前物体位置推向非 owner-habit location，而最终动作继续选择该位置；也就是行为层面已经出现“把他人/异常轨迹当作主人习惯来行动”的污染后果。joint 与 factorized 同样发生，说明当前学习交互没有解决这个科学问题。

本环境的 search regret 为 0，是因为两臂总能把当前物体位置排在第一；但 put-back policy（放回策略）没有把物体恢复到 owner habit，故行动遗憾仍高。不能用搜索成功掩盖放回与污染失败。

## 6. 七算子中和消融

下表全部为 27 个配对动作步；TV 比较中和臂与完整 joint。所有中和臂都保留七个算子，且其余六个算子在每个 seed 中实际执行。

| 中和算子 | mean action-posterior TV | max TV | TV>0 步数 | argmax 分歧 | Δ action regret | Δ contamination |
|---|---:|---:|---:|---:|---:|---:|
| OPCEU | 0.0228342 | 0.1238178 | 27/27 | 0 | 0 | 0 |
| ORRER/CHEH | 0.0003131 | 0.0036222 | 24/27 | 0 | 0 | 0 |
| PCHMP | 0.0734557 | 0.1828417 | 27/27 | 0 | 0 | 0 |
| CF-BOCPD | 0.0005698 | 0.0056113 | 27/27 | 0 | 0 | 0 |
| RGRC | **0.1083219** | **0.1857614** | 21/27 | 0 | 0 | 0 |
| CCRR | 0.0000151 | 0.0003157 | 25/27 | 0 | 0 | 0 |
| CIAV | 0.0232948 | 0.1583636 | 5/27 | 0 | 0 | 0 |

这张表证明每个中和开关都进入了决策后验，其中 RGRC、PCHMP、CIAV 和 OPCEU 的分布影响最大；但所有 argmax、行动遗憾和污染均不变。因此 `all_seven_operator_contributions_established=false` 仍是唯一诚实结论。后验敏感性不是行动贡献，更不是效用贡献。

## 7. 两轮对抗审核

第一轮针对内部科学语义：完整范围、三划分防泄漏、动作后状态消费、潜在结果配对、RGRC 可达性/拒绝性、单算子中和掩码、其余算子执行和汇总重算。

第二轮针对 forged-but-complete（伪造但字段完整）的正路径：重签顶层哈希后篡改环境 transition、算子回执、RGRC 账本、指标、消融总结和论文级正声明，均被本地验证器拒绝；另构造调用方自洽但替换了 common-random-number receipt（共同随机数回执）的样本，本地验证仍允许、fresh-source replay（新鲜源码重放）会拒绝。这明确保留了 self-consistency（自一致性）与 independent custody（独立托管）的边界。

用户要求的第二次两轮对抗又覆盖了中和语义冒充、纠正状态链伪造、RGRC 原始负例账本、非有限数、布尔值冒充整数、训练/验证样本同构与伪造但不同的样本哈希。发现项均已修复，详见 `structure_two_full_scientific_loop_second_two_round_adversarial_audit_2026-09-08.md`。定向回归现为 v0.2 `29 passed`，与 v0.1 Route C 回归合并为 `54 passed`；P0 对抗和全仓 pytest/mypy/ruff/compileall/git-diff 审计全部退出码 0。最新 checkpoint 已 fresh-verify，content hash 为 `37074fdd82a747493c5fe8cd10913db5dfcc6f72ece536eff75acb633fbfcfae`；`seven_operator_ablation_authorized=false` 不变。

## 8. 当前允许与不允许的结论

允许：

- 完整结构二状态、三个解析块和七个算子仍在同一闭环内；
- 动作会改变环境，动作后观测和纠正反馈会回到后续联合状态；
- 跨轴交互参数已经训练、验证选择、冻结，并非手工系数；
- RGRC 正例、负例和撤销路径都可执行，主闭环也出现正式 promote；
- 七个算子都能在保留完整框架时做逐一中和，并产生可审计的后验差异。

不允许：

- joint 优于 matched factorized；
- 七个算子分别产生最终行动或效用贡献；
- 当前污染得到解决；
- 当前种子足以证明泛化；
- 已完成 AMG 等强外部基线在同一动作响应环境下的比较；
- 真实机器人外部有效性、论文级优越性或独立托管成立。

## 9. 复现入口

```bash
PYTHONPATH=src .venv/bin/python \
  apps/evaluation_runner/run_structure_two_full_scientific_loop.py

PYTHONPATH=src .venv/bin/python \
  apps/evaluation_runner/run_structure_two_full_scientific_loop.py \
  --verify benchmarks/structure_two/structure_two_full_scientific_loop_v0_2.json

PYTHONPATH=src .venv/bin/pytest -q \
  tests/test_structure_two_full_scientific_loop.py \
  tests/test_structure_two_full_scientific_loop_adversarial.py \
  tests/test_structure_two_full_scientific_loop_second_adversarial.py
```

最核心文件：

- 配置：`configs/project_two_experiments/structure_two_full_scientific_loop_v0_2.json`
- 实现：`src/cpswm/system/evaluation_operations/structure_two_full_scientific_loop.py`
- 可复算结果：`benchmarks/structure_two/structure_two_full_scientific_loop_v0_2.json`
- 正向与对抗测试：`tests/test_structure_two_full_scientific_loop.py`、`tests/test_structure_two_full_scientific_loop_adversarial.py`、`tests/test_structure_two_full_scientific_loop_second_adversarial.py`
