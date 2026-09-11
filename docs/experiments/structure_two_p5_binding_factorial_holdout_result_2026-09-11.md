# 结构二 P5 精确绑定、2×2 析因与未见 D0 留出结果（2026-09-11）

## 结论

本轮完成了 debt→CIAV exact binding（债务到 CIAV 的精确绑定）、异位置反馈时间分辨率修复、四类对抗测试、verifier/dataset gate（验证器/数据门禁）加固、Structure One 传递依赖与环境锁绑定，以及开发集 `2×2` 析因。

修正后的 direct P5（直接 P5）在新的内部 D0 留出集上没有通过冻结 signal gate（信号门）。PUT_BACK 优于 learned two-stage，但相对最强匹配 AMG 只获得 `0.008854` 绝对错误率改善，低于预设 `0.02`。SEARCH 三臂完全相同。因此 Task 7/8/9 仍不能判为通过。

## 工程与信任链修复

- `AdaptiveInferenceDebtCertificate@0.2.0` 现在包含 `deferred_ciav_input_sha256`；P0 创建 debt 时冻结完整 CIAV 输入，replay 同时核对调用方输入、ledger（账本）快照和证书承诺，执行时只使用 runtime-owned（运行时自有）快照。
- CIAV opportunity time（观测机会时间）由主观测后 `1µs` 改为 `1ms`，为不同位置 full-transition feedback（完整转移反馈）的 CHEH 隐事件链提供足够的可表示时间点。
- dataset gate 会把完整对象图重新 `model_validate`；`model_copy(update=...)` 不能再绕过 visible/evaluator hash、join 和 split binding（可见/评估哈希、连接和划分绑定）。
- 三类 P5 artifact verifier（工件验证器）不再提供 hash-only（仅哈希）成功路径，必须 fresh recomputation（完整重新计算）。
- production assembly manifest（生产装配清单）现在绑定全部 `src/cpswm/**/*.py`，并绑定 `pyproject.toml` 与 `uv.lock`。Structure One 的 regime/habit（机制/习惯）实现因此进入 Structure Two 的传递源码身份。
- 新增四类 adversarial tests（对抗测试）：CIAV 替换、异位置正反馈、重签后的工件数值伪造、Pydantic dataset model-copy 伪造。

## 开发集 2×2 析因

数据是此前已经打开的 `project-two-d0-multiseed-readout@0.5`，60 episodes、1920 steps；该实验只用于诊断，不能作为新的确认性结果。

| action readout（动作读出） | sequential prior（顺序先验） | SEARCH error | PUT_BACK error | 非均匀 owner-habit steps |
|---|---:|---:|---:|---:|
| old | old | 0.089063 | 0.684896 | 0 |
| new | old | 0.089063 | 0.684896 | 0 |
| old | new | 0.089063 | 0.684896 | 0 |
| new | new | 0.089063 | 0.040104 | 1870 |

两个单独修复对 PUT_BACK 的改善均为 `0`；联合改善与 interaction synergy（交互协同）均为 `0.644792`。这说明两项修复是联合必要条件，不是可以二选一的替代方案。SEARCH 与 normalized search regret（归一化搜索遗憾）在四格中都不变。

工件：`benchmarks/structure_two/structure_two_p5_readout_prior_factorial_v0_1.json`；`content_sha256=9757b9887acdcbc8c54d2ebc7536b5c577db03a730324babd8d3bd45a59a02cb`。

## unseen D0 holdout（未见 D0 留出集）

选择 unseen D0 而不是 independent-custody split（独立托管确认集），因为当前仓库没有独立托管方、访问控制 split service（划分服务）或外部保管证据。将本地文件称为独立托管会形成虚假声明。

协议、修复和 `12001–12060` test seeds 在提交 `df5bd6b` 冻结后才首次打开。结果如下：

| arm（方法臂） | SEARCH error | PUT_BACK error | normalized search regret |
|---|---:|---:|---:|
| corrected direct P5 | 0.080208 | 0.044271 | 0.055382 |
| learned matched two-stage | 0.080208 | 0.277604 | 0.055382 |
| independently tuned AMG | 0.080208 | 0.053125 | 0.055382 |

- 对 learned two-stage 的 PUT_BACK 改善为 `0.233333`，95% paired-episode bootstrap CI（配对情节自举区间）为 `[0.223958, 0.242708]`，通过单项门槛。
- 对 AMG 的 PUT_BACK 改善为 `0.008854`，区间为 `[0.002083, 0.017708]`；虽然方向稳定且相对改善为 `0.166667`，绝对改善没有达到 `0.02`，因此冻结规则判为失败。
- SEARCH 对两种 comparator（比较方法）的改善都是 `0`。
- 1276 个 positive full-transition steps 全部有七算子 primary trace；另有 644 个 negative CIAV/OPCEU closures，总计覆盖 1920 steps。

首次打开工件保留为 `benchmarks/structure_two/structure_two_p5_unseen_d0_holdout_initial_open_v0_1.json`，`content_sha256=9320c4388aa1435284e9163a6d8dfebab72d1a61147c541b5be659e90c88963b`。

## 首次打开后的 verifier 事件

首次工件生成后，强制重算发现 direct-P5 的 `typed_action_chain_sha256` 与 `ciav_receipt_chain_sha256` 混入 run-local random UUID（运行期随机 UUID），使完整 JSON 无法跨运行逐字段相等。数值指标、动作选择和 signal gate 没有漂移，但这两个链哈希不适合作为跨运行身份。

因此：

1. 首次打开工件原样保留，没有用修复后重跑覆盖；
2. 链哈希改为只绑定 consequential action（后果动作）和 CIAV packet/outcome/cost/closure（数据包/结果/成本/闭环）语义，排除 run-local state IDs；
3. 同一 episode 连续两次完整执行已经逐字段一致；
4. 在已打开数据上的 post-open numeric replay（打开后数值重放）与首次工件的 status、三臂汇总、pairwise gate、validation selection、readout diagnostic 和执行计数完全一致；该重放不重新声称 unseen。

## 仍然成立的边界

- production debt replay 在 1243 个正转移上通过全部 12 项语义等价检查，失败转移为 0；677 个负观测不在这份正路径等价声明内。
- 当前证据支持“联合修复消除了 PUT_BACK 退化，并且 direct/replay 正路径一致”。
- 当前证据不支持“P5 已通过死亡测试”“七算子具有 SEARCH 优势”“Task 7/8/9 已通过”“具有外部有效性”或“可以缩小结构二范围”。
