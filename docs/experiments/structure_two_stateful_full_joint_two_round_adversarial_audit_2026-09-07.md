# 结构二 Route C 两轮对抗审核（2026-09-07）

审计对象：`structure-two-stateful-full-joint@0.1-development`  
审计口径：代码、配置、D0 数据、逐步公平回执、算子/账本状态机、结果工件和 fresh replay  
结论等级：**工程审计通过；科学优越性与外部闭环未通过**

## 技术摘要

两轮审核把 Route C 从“可以跑的完整状态原型”推进到了“可重复、可追溯、能抵抗常见伪造与状态机
攻击的 D0 回放实现”。第一轮发现并修复了会改变科学解释的真实问题：top-96 截断破坏 proposal
support（提议支持）、评分回执虚报、RLS/information blocks 未进入动作、RGRC 稳定门与撤回主体错误、
反馈重放/替换、异常后的半提交状态，以及随机 UUID 导致的新鲜回放不确定性。

第二轮针对 forged-but-complete（伪造但字段完整）正向路径，补上原始回执、逐 episode 分布、状态机
reachability（可达性）、来源路径、严格 JSON、派生指标重算、正向声明 trust chain（信任链）和新鲜源码
回放。25 项定向测试、全仓 pytest、格式检查、静态类型检查、编译检查、差异检查与 fresh replay
均通过。全仓第一次审核曾准确抓到历史 v0.5 compatibility audit（兼容性审计）相对当前源码漂移；
重新生成该审计后，对应失败测试和第二次完整工程审核均通过。

但审核同时否决三种过度结论：`all operators executed` 不等于 `all operators contributed`；
`contamination=0` 不等于门控有效；`replay feedback loop` 不等于交互环境闭环。RGRC 在当前 4 个开发
保留 episode 中 0 次 promote，联合与因式分解行动效用打平，且 joint 仍输给 AMG。

## 审计范围、数据和判定定义

- 机制对照：`stateful_full_joint` 对 `matched_full_state_factorized`；两臂只有跨轴交互势不同。
- 外部行动基线：independently tuned AMG（独立调参 AMG），不属于完整状态访问匹配对照。
- 数据：6 个 D0 synthetic episodes，96 步；2 个 validation seeds + 4 个 development holdout
  seeds；70 条反馈，观测覆盖 `70/96`。
- 公平通过：逐步可见输入、支持模式、提议器、粒子预算、实际目标评分数、共同随机数、重采样、反馈、
  RGRC 策略和动作读出一致。
- 工程闭环通过：完整七轴状态可更新、反馈修订可被后续动作消费、状态机异常原子回滚、产物可由当前
  来源 fresh replay 精确复现。
- 科学通过：本轮未定义为 true；仍需预注册的新数据、新种子、长期记忆激活、行动收益和外部环境。

## 第一轮：状态、算子、公平与反馈闭环攻击

| 攻击/检查 | 审核前结果 | 修复或当前结论 | 状态 |
|---|---|---|---|
| 完整 proposal support | 每父粒子只保留 top-96；受控首步丢约 7.21% 提议质量 | 枚举全部正支持；单元场景 351 项，当前回放每父粒子 312–543 项 | 已修复 |
| 实际 target-score 计数 | 回执按 `parents × 96` 声称评分，实际只评分 24 个抽样粒子 | 回执绑定实际 24 次评分及 `24 × 32` 操作预算 | 已修复 |
| 公平哈希 | 反馈后随机修订 UUID 不同，被误判为输入不公平 | 支持模式与可见输入必须一致；处理后内容哈希只作溯源 | 已修复 |
| common random numbers（共同随机数） | 随机反馈 UUID 进入谱系，fresh replay 不确定 | Route-C 私有谱系使用 episode + feedback record + 顺序的确定性别名 | 已修复 |
| 完整状态校验 | 只检查部分历史长度 | 新增角色、实例、cause、regime、run、revision head/parent、retired regime、RB 维度一致性 | 已修复 |
| 三个 RB blocks 进入动作 | 仅 Dirichlet 真正被读出，ridge/information 近似装饰 | 联合读出显式消费三块；分别扰动 ridge 和 information 会改变分布 | 已修复 |
| RGRC stability（稳定门） | 使用历史 run length，单次高分事件可能提前 promote | 要求 owner×target×regime×location 连续稳定并同时满足 run 条件 | 已修复 |
| RGRC retract（撤回）主体 | 替换长期记忆时，撤回记录错误写入新粒子来源 | 撤回记录绑定旧 active source；账本验证可达状态转换 | 已修复 |
| feedback replay/substitution | 只按 corrected revision 去重；同 feedback record 换 ID 可重放 | 同时绑定 feedback record、corrected revision 和已接纳 superseded source | 已修复 |
| duplicate/sparse/nonfinite feedback | 重复 key 会被 dict 静默覆盖 | 重复 key、NaN、Inf、负概率、零质量拒绝；合法稀疏后验归一化 | 已修复 |
| 异常后的半提交 | revise 早期已消费 update，后续异常会留下部分回执与状态 | revise/feedback 改为 transactional rollback（事务回滚） | 已修复 |
| 闭环措辞 | “closed loop” 容易被理解成环境响应动作 | 明确为 frozen replay action-bound revision loop；环境交互标志固定 false | 已修复声明 |

第一轮通过的可执行测试覆盖：完整支持、不截断、逐步两臂公平、异常输入、可变字典 TOCTOU、事务
回滚、反馈重放与错误目标、RGRC 连续稳定、旧主体撤回、三 RB 读出、算子回执篡改，以及单 episode
七算子整合运行。

## 第二轮：证据、来源、伪造正路径与声明升级攻击

| 攻击/检查 | 审核前风险 | 当前防线 | 状态 |
|---|---|---|---|
| 只改汇总再重哈希 | 汇总可与 episode 明细脱节 | 从 per-episode rows 重算全部 summary 和 paired differences | 已封堵 |
| 删除/替换动作分布 | TV 诊断可脱离真实 runtime trace | paired distribution 与 episode、连续 trace index、runtime count/hash 交叉绑定 | 已封堵 |
| 改算子回执再重哈希 | 顶层自哈希无法发现内部语义改写 | 原始回执链逐条重算，验证 `changed ⇒ executed`、axis 和 step 顺序 | 已封堵 |
| 伪造 RGRC 完整链 | 自洽哈希不保证 promote/retract 可达 | 验证 quarantine→promote、active→retract、retract→corrected_revision 状态机 | 已封堵 |
| 来源文件替换 | 只给一个新哈希可能把其他文件冒充实现 | 配置、路线决定、实现、神经提议器使用精确路径 + SHA-256 | 已封堵本地替换 |
| config/结果额外正向字段 | 可追加 `paper_ready=true` 一类未审字段 | 配置和结果顶层 exact schema（精确模式），多余声明失败关闭 | 已封堵 |
| 重复 JSON key | 后写 `true` 可覆盖前写 `false` | runner 使用 duplicate-key rejecting parser | 已封堵 |
| NaN/Infinity | 比较和聚合可能静默绕过范围检查 | parser 与递归数值检查双层拒绝 | 已封堵 |
| 自洽但伪造的支持哈希 | 攻击者可同时改值和本地内容哈希 | fresh-source replay 与确定性摘要必须一致 | 已封堵于正式 verify |
| 正向输出无 trust chain | 过去只核对若干布尔结果 | 完整状态、RB、数据 ready、回放环、公平、七算子覆盖、正 TV 均有逐路径来源 | 已修复 |
| 本地哈希冒充独立托管 | 自一致性被误当真实性 | `independent_custody=false`、`historical_authenticity=false` 固定并验证 | 已封堵声明 |
| 执行覆盖冒充贡献 | 七个算子出现过即被理解为都有用 | 输出 effect counts；`all_seven_operator_contributions_established=false` | 已修复声明 |

一个重要边界仍保留：如果攻击者能同时改代码、配置、结果和本机验证器，本地 SHA-256 与 fresh replay
无法证明 historical authenticity（历史真实性）或 independent custody（独立托管）。这需要外部只读
registry、签名发布或独立执行方，不是继续叠加本地哈希能解决的。

## 当前定量结果说明 joint 为什么没有收益

| 量 | joint | matched factorized | AMG | 解释 |
|---|---:|---:|---:|---|
| action regret / step | 0.244792 | 0.244792 | 0.171875 | joint 与公平对照打平，较 AMG 差 0.072917 |
| search regret / step | 0.182292 | 0.182292 | 0.109375 | 联合状态未改变搜索排序 |
| owner contamination | 0 | 0 | 0 | 三臂全零，不能构成 Route-C 独有优势 |
| unknown Brier | 0.202267 | 0.202298 | 0.152500 | joint/factorized 微小差异无充分样本支持；AMG 更低 |
| joint-vs-factorized TV | mean 0.0004586 | — | — | 仅 13/62 步非零，最大 0.0044314 |
| action disagreement | 0/62 | — | — | 没有跨过决策边界 |

joint 在高维支持上每步只抽取 24 个候选，cross-axis potentials 仍是手工系数，数据中 handoff truth
只有 7 次，RGRC 又没有 promote。因此当前失败不是“联合状态没维护”，而是“联合关系没有被学习成
足以改变动作且产生效用的机制”。

## 算子输入输出与相互牵制的准确判断

- **接口和状态机层面：通过。** 七算子回执按顺序成链，声明消费的状态轴受校验；反馈、账本、完整
  世界状态和三个 RB blocks 可被独立攻击测试。
- **系统路径层面：部分通过。** OPCEU→PCHMP→CF-BOCPD→CCRR→joint particle update→action，
  ORRER-CHEH→revision lineage→later action 的路径已执行；CIAV 在联合臂执行并改状态 10 次。
- **长期牵制层面：未显现。** RGRC 只有 quarantine，没有长期 active distribution，因而没有对动作
  形成长期记忆牵制。
- **独立贡献层面：未审核完成。** 尚无七算子逐一 removal/neutralization ablation（移除/中和消融），
  所以不能从“执行”推出“每个算子必要或有效”。

## 为什么这些问题之前没有被发现和改善

此前测试重点是负例、聚合指标和“算子名字是否出现”，没有把每个正向结论反向展开成完整 trust
chain，也没有系统攻击 forged-but-complete positive paths（字段齐全但语义伪造的正路径）。因此：

1. top-96 看起来是性能优化，没有检查被丢弃的 proposal mass；
2. 计算公平使用配置推导的声明数，没有对真实评分函数调用计数；
3. “输入输出正常”只覆盖类型与调用，没有检查 RLS/information 是否真的进入动作；
4. 哈希审计检查自一致性，没有验证账本状态可达性、主体真实性和独立托管；
5. aggregate pass（汇总通过）掩盖了 RGRC 只有 quarantine、没有 promote 的空洞路径。

本次把这些缺口固化成回归测试；不是用解释覆盖旧问题。

## 剩余科学阻塞与下一门

1. 在 validation-only（仅验证集）上学习或选择 interaction/readout，而不是直接放大已看过数据上的
   手工系数；随后冻结。
2. 扩大 `K` 并做 particle-budget sensitivity（粒子预算敏感性），至少判断 24 粒子是否限制 joint。
3. 建立能触发 RGRC promote 的正例和应拒绝 unknown/guest 的负例，同时报告正确写入 recall、污染、
   撤回正确率和行动效用。
4. 使用多 family、新 household、fresh seeds 的数据；补真实传感器校准、位姿不确定性和动作后环境
   观测。
5. 建立 action-responsive simulator/robot（动作响应模拟器/机器人）后，再声称交互环境闭环。
6. 用外部只读保管或独立执行签名建立真实性；本地 fresh replay 只证明当前工作区自一致。
7. 在不删除完整结构二任何能力的前提下做七算子 neutralization ablation，判断谁真正贡献效用。

## 验证命令与结果

```text
ruff check: PASS
mypy Route-C module: PASS
targeted Route-C tests: 25 passed
fresh artifact verification: PASS
full-repository engineering audit: PASS
engineering checkpoint fresh generation + independent verify: PASS
engineering checkpoint content SHA-256:
ade6124bacfe397f581eeef36d093e26a2e43bff941f519110686a9fb763ed0e
```

全仓第一遍审核发现 1 个真实证据漂移：当前源码 bundle 已变化，但历史 v0.5 compatibility audit 仍保留
旧的当前树摘要；同时失败日志中的 pytest 对齐空格触发 `git diff --check`。更新 compatibility audit 并
清理日志格式后，第二遍审核的 `p0_adversarial_tests`、`core_pytest`、`mypy_src`、`ruff_lint`、
`ruff_format`、`compileall`、`git_diff_check` 七项退出码全部为 0。工程 checkpoint 随后经过两次
fresh recomputation。该通过仍明确不建立 independent custody（独立托管）或 external validity
（外部有效性）。

复现命令：

```bash
uv run ruff check \
  src/cpswm/system/evaluation_operations/structure_two_stateful_full_joint.py \
  tests/test_structure_two_stateful_full_joint.py \
  tests/test_structure_two_stateful_full_joint_adversarial.py \
  apps/evaluation_runner/run_structure_two_stateful_full_joint.py

uv run mypy src/cpswm/system/evaluation_operations/structure_two_stateful_full_joint.py

uv run pytest -q \
  tests/test_structure_two_stateful_full_joint.py \
  tests/test_structure_two_stateful_full_joint_adversarial.py

PYTHONPATH=src uv run python apps/evaluation_runner/run_structure_two_stateful_full_joint.py \
  --verify benchmarks/structure_two/structure_two_stateful_full_joint_v0_1.json

PYTHONPATH=src uv run python apps/evaluation_runner/generate_p0_checkpoint_manifest.py
PYTHONPATH=src uv run python apps/evaluation_runner/run_structure_two_engineering_audit_receipt.py
PYTHONPATH=src uv run python apps/evaluation_runner/generate_structure_two_engineering_trust_checkpoint.py
PYTHONPATH=src uv run python apps/evaluation_runner/generate_structure_two_engineering_trust_checkpoint.py \
  --verify benchmarks/structure_two/engineering_trust_checkpoint_2026_09_05/engineering_checkpoint.json
```
