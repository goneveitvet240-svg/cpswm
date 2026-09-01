# 逐方法最强对手可证伪测试门：Round 2

日期：2026-08-27  
状态：已执行；2 条路线在 D0 封闭实验内存活，1 条路线被推翻，15 条路线继续阻塞。

## 1. 先说结论

本轮没有证明“整套 CPSWM 已经超过基线”。本轮只回答三个更小、但可核验的问题：

1. 结构一的 leave-one-out layered habit（留一分层习惯）是否优于会重复计算证据的直接对手；
2. 结构一的 four-layer placement semantics（四层放置语义）是否真的能处理权限冲突；
3. 结构三的 multi-parse posterior（多解析后验）是否优于 top-1 parse（只取第一条解析）和 self-consistency vote（自一致投票）。

统一门最终输出为：

| 决定 | 数量 | 含义 |
|---|---:|---|
| `survived` | 2 | 在冻结的 D0 场景、输入和预算内，同时满足行动不劣且路线机制更强 |
| `falsified` | 1 | 至少一个直接对手在行动或机制端点上明确推翻候选路线 |
| `inconclusive` | 0 | 本轮没有落入统计区间跨门槛的提交 |
| `blocked` | 15 | 没有合格的完整提交，不能把模块存在当成路线胜利 |

这里的 `paper_claim_allowed=true` 只表示“通过当前 v0.1 封闭测试门”，不表示真实数据外部有效性、完整论文创新或整套系统优越性已经成立。

## 2. 冻结办法

- 注册表：`cpswm-method-falsification-registry@0.1`
- 注册表 SHA-256：`2e31d804d76194ca0bf0ebcfc8180241d19029e06cfc5f14f273094c6fc94163`
- Round 2 配置：`configs/method_falsification/round_two_v0_1.json`
- 验证集只用于各方法独立调参；测试集种子与验证集不重叠。
- 同一比较中的候选与对手读取相同可见输入，使用相同行动预算。
- 95% 区间按冻结的独立簇单位 bootstrap（自助抽样）计算，重复 2000 次。
- 一个路线必须面对注册表内的每一个直接对手；缺一个就不得提交为通过。

## 3. 结构一：留一分层习惯

候选：`s1.leave_one_out_layered_habit`  
直接对手：additive hierarchical Dirichlet（相加式分层狄利克雷）和 nested back-off habit（嵌套回退习惯）。

冻结场景为单一情境重复、跨情境迁移、家庭与个人冲突。20 个验证种子独立调参，100 个封存测试种子作家庭级比较。

| 方法 | 平均错误放置代价，越低越好 |
|---|---:|
| leave-one-out layered habit | 0.2575 |
| additive hierarchical Dirichlet | 0.4021 |
| nested back-off habit | 0.2575 |

候选相对 additive 对手的行动优势为 `+0.1446`，95% CI `[+0.1292, +0.1604]`；相对 nested back-off 的行动差为 `0`，95% CI `[0, 0]`。候选的证据重复倍数为 1，对手为 3，因此两组机制优势均为 `+2.0`。

决定：`survived`。

准确解释是：留一分层在这个合成家庭实验中，至少没有为“去掉重复计数”付出行动代价，并且明确胜过相加式对手。它没有在行动上胜过正确调参后的 nested back-off，只是以同样行动结果避免了重复证据。因此这是一条值得接真实数据继续检验的路线，不是已经完成的论文结论。

## 4. 结构一：四层放置语义

候选：`s1.four_layer_placement_semantics`  
直接对手：collapsed placement memory（合并式放置记忆）和 authority-agnostic rule resolver（不看权限的规则解析器）。

冻结场景为行为与偏好冲突、访客与主人冲突、硬安全规则撤回。100 个测试种子乘 3 个场景，共 300 个 episode（回合）。

| 方法 | 错误放置代价 | 语义层违规率 |
|---|---:|---:|
| four-layer placement semantics | 0.3333 | 0.3333 |
| collapsed placement memory | 0.3333 | 0.0000 |
| authority-agnostic resolver | 0.3333 | 0.3333 |

候选相对 collapsed 对手的机制效应为 `-0.3333`，95% CI `[-0.3867, -0.2800]`；相对 authority-agnostic 对手，行动和机制都完全打平。

决定：`falsified`。

根因不是“四层数据结构没有建立”，而是当前 `PlacementDecisionResolver` 选择偏好时只看实例具体性、时间和记录 ID，没有把 `authority_level`（权限等级）放进最终选择。结果是更新更晚的未验证访客意见可以压过主人意见。也就是说，项目保存了权限信息，但行动时没有真正使用它。

本轮不在看到测试结果后修改规则再重跑，否则会污染已经封存的结果。修复应进入下一版本，并使用新的 preregistration（预注册）和新种子。

## 5. 结构三：多解析后验

候选：`s3.multi_parse_posterior`  
直接对手：top-1 LLM parse 和 LLM self-consistency vote。

冻结场景为时间指代、人物指代、功能与关系指代。20 个验证种子和 100 个测试种子分离；测试共 300 个 episode。

| 方法 | 平均具身任务效用，越高越好 |
|---|---:|
| multi-parse posterior | 0.2533 |
| top-1 LLM parse | 0.2533 |
| self-consistency vote | 0.0533 |

候选相对 top-1 的行动差为 `0`，95% CI `[0, 0]`，但保留多解析覆盖的机制优势为 `+0.45`。候选相对 self-consistency 的行动优势为 `+0.20`，95% CI `[+0.10, +0.3133]`，机制优势为 `+0.502`，95% CI `[+0.4927, +0.5127]`。

决定：`survived`。

准确解释是：在确定性的语义夹具里，多解析没有胜过 top-1 的行动结果，但也没有变差；它胜过自一致投票，并保留更多候选解释。因为本轮没有调用真实 hosted LLM（托管大模型），所以这只能证明融合逻辑在受控输入下值得继续，不能证明真实语言噪声下仍然有效。

## 6. 没有执行而继续上锁的路线

### 结构一 mobility（移动性）

当前 five-axis mobility（五轴移动性）输出的是对象画像和派生标签，还没有绑定一个能产生搜索路线与 search-path cost（搜索路径代价）的正式策略。拿画像分类准确率代替行动对比会偷换问题，因此 `s1.five_axis_mobility` 继续为 `blocked`。

### 结构二 ORRER

现有结构二全链 D0 结果仍是重要反证：完整候选的累计行动后悔为 7.3333，matched AMG（匹配输入的 AMG）为 4.2333，候选相对效应为 `-3.10`，95% CI `[-3.50, -2.7333]`。它说明当前完整链在该实验上输给 AMG，但这份旧实验没有逐路线隔离 ORRER，也没有 fixed-lag smoother（固定滞后平滑器）直接对手，因此不能冒充 `s2.orrer` 的正式提交。

仓库现在没有一个将 fixed-lag 的状态、迟到修订和污染面积绑定到 ORRER 真实 event/ledger（事件/账本）接口的 runner。重新写一个简化状态机虽然能跑出数字，却只会比较两个代理模型。因此本轮把真实缺口登记为阻塞，不制造假胜负。

### 结构二其余路线

OPCEU、PCHMP、CF-BOCPD、RGRC、CCRR、CIAV 和统一组合 A 都缺少“真实候选入口 + 两个冻结直接对手 + 独立调参 + 行动端点”的完整提交，继续为 `blocked`。模块测试、契约存在和旧的全链结果都不能替代逐路线证据。

### 结构三其余路线

概率动态实例图、修订感知证据图、CO-CIP、HCS 和 coverage-derived unknown mass（覆盖度派生未知质量）仍缺各自的直接对手行动实验，继续为 `blocked`。

### OAM-PHM

当前只有 WP0 baseline floor（基线地板）。O-STaR、STREAK 等外部系统仍是 equation-core only（只具公式核心）或 external reimplementation required（需要外部重实现），独立家庭簇也只有 1 个。因此 `oam_phm.full_loop` 继续为 `blocked`。

## 7. 下一轮必须做什么

1. 为四层放置语义做新的、预注册后的权限参与决策修复；旧失败结果永久保留。
2. 把 five-axis mobility 接到真正的 next-location/search policy（下一位置/搜索策略），再与 binary stationarity 和 three-bin rigidity 比路径代价。
3. 给 ORRER 暴露统一的逐事件候选接口，让 reversible revision、AMG 和 fixed-lag 在同一事件流、同一写入权限和同一污染面积指标下运行。
4. 将结构三多解析实验替换成真实 LLM 输出缓存和真实语言数据；保持验证/测试划分、prompt hash（提示词哈希）和 provider version（供应商版本）冻结。
5. OAM-PHM 在外部强系统忠实复现与多个独立家庭完成前，不进入“完整比较已完成”叙事。

## 8. 机器可读产物

- `output/method_falsification/round_two_structure_one_v0_1.json`
- `output/method_falsification/round_two_structure_one_placement_v0_1.json`
- `output/method_falsification/round_two_structure_three_v0_1.json`
- `output/method_falsification/round_two_submissions_v0_1.json`
- `output/method_falsification/current_method_audit_v0_1.json`

复现入口：

```bash
.venv/bin/python apps/evaluation_runner/run_round_two_falsification.py
.venv/bin/python apps/evaluation_runner/run_method_falsification_audit.py \
  --submissions output/method_falsification/round_two_submissions_v0_1.json \
  --force
```

## 9. 回归核验

- Round 2 与测试门定向集合：63 passed。
- 结构一此前登记的 7 个合并后测试文件：157 passed。
- 全量 pytest：2495 passed、1 xfailed、1 failed。
- 唯一失败：`test_p0_checkpoint_manifest_is_current_and_self_consistent`。原因是当前大量未提交代码使 P0 content manifest（内容清单）过期；本轮没有为整个脏工作区重新盖章。
- Ruff lint：全仓通过。
- 本轮 3 个 Python 文件 Ruff format：通过。
- 全仓 Ruff format 仍有 8 个既有文件待格式化；其中包括其他任务的 runner 和 Markdown 代码块，本轮未改写。
- `git diff --check`：通过。
- `./check.sh` 不能作为本机成功证据：第一次被用户级 uv cache 权限阻断，第二次在临时缓存中因网络受限而不能下载 `setuptools>=75`；更严重的是脚本在这些子步骤失败时仍返回退出码 0。全量 pytest 和 Ruff 因而改为直接调用现有 `.venv` 完成。
