# 结构二 Task 7/8 P0：两轮自我攻击记录

日期：2026-09-05
范围：仅 Task 7 窗口回春与 Task 8 相对概率交叉耦合；未运行七算子系统消融。
证据边界：D0 synthetic deterministic rerun（D0 合成确定性注册复算），不是 independent-custody formal receipt（独立托管正式回执）。

## 结论

- 第一轮 runtime/kernel attack（运行时/内核攻击）：`8/8 passed`。
- 第二轮 artifact/verifier attack（工件/验证器攻击）：`15/15 passed`。
- 两个测试文件的任务专用回归：`90/90 passed`。
- Ruff format/check 与 strict mypy 均通过。
- 两个落盘工件均在写入后再次从冻结配置做 fresh recomputation（新鲜复算）并逐字段通过。
- Task 7 仅工程复杂度子门通过，belief/action equivalence（信念/行动等价）失败，因此正式注册结论仍是 `FAIL`。
- Task 8 的 belief/action/utility（信念/行动/效用）严格合取在五 seed 注册总体上为 `PASS`；没有签名和独立 custody，不能据此打开七算子消融。

## 第一轮：热路径与端点因果性攻击

覆盖八项：

1. 修订后的 terminal state（末端状态）与 analytic block（解析统计块）一致；
2. checkpoint/source-stream（检查点/源流）被篡改时拒绝执行；
3. poisoned long suffix（毒化长后缀）在任何越窗读取或 slice 物化时抛错；
4. `W=3`，suffix=`8/64/256` 下窗口工作量、持久层节点、live storage（活跃存储）与 reachable overlay bytes（可达覆盖层字节）保持恒定；
5. Task 7 明确产出九轴 belief 距离与末端 action 分布/选择等价；缓存 action readout 与物化 readout 一致；
6. self proposal（自身提案）被返回时不能偷算成功，必须显式触发 replay fallback（重放回退）；
7. 不可桥接的边界提案必须记录原因并执行全量重放回退；
8. Task 8 构造两个 `(H+Z)` 与 `C` 边缘完全相同、仅交叉 cell 不同的 belief，离散 `verify/proceed` 行动分布必须不同。

结果：`8/8 passed`。

Task 7 长后缀实测如下；checkpoint 基线存储随历史增长是校正前成本，不计入校正到达后的 marginal repair（边际修复）成本。

| suffix | checkpoint bytes | target work | persistent nodes | items written | live items | reachable overlay bytes | suffix read/copy/rehash |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 8 | 1,272 | 36 | 19 | 58 | 37 | 314 | 0 / 0 / 0 |
| 64 | 4,520 | 36 | 19 | 58 | 37 | 314 | 0 / 0 / 0 |
| 256 | 15,817 | 36 | 19 | 58 | 37 | 314 | 0 / 0 / 0 |

该探针同时以对象身份断言 repair overlay（修复覆盖层）的 base 正是毒化的原历史引用；若热路径先复制或物化完整后缀，此断言会失败。因此证据不只依赖实现自行上报的逻辑计数器。

## 第二轮：阳性伪造与验证器攻击

覆盖十五项，包括：

- 把 Task 8 的原始 utility failure（效用失败）字段改成完整阳性并重算外层哈希，fresh recomputation 仍拒绝；
- instrument-only pass（仅仪器通过）不能提升为 Task 7/8 总门通过；
- action shift（行动变化）而无方向性 utility benefit（效用收益）不得通过；
- 调用者谎报 `endpoint_consumes_interaction` 时由验证器构造性重算并拒绝；
- 结果试图降低已冻结 action threshold（行动阈值）时拒绝；
- complexity pass（复杂度通过）不能隐藏任何 suffix read（后缀读取）；
- non-self claim（非自身提案声明）必须从原始 proposal counters（提案计数器）重算；
- task substitution（任务替换）、重复 JSON key、非有限数、配置漂移和代码/配置阈值不一致均失败闭合；
- 未改动结果可由任务专用 fresh recomputation 正常接受。

结果：`15/15 passed`。

## 注册结果与不可越界解释

Task 7：

- strict window complexity：`PASS`；
- belief equivalence：`FAIL`；
- action equivalence：`FAIL`；
- 总门：`FAIL`。

Task 8：

- primary belief TV：`0.08171805188286488`，冻结门槛 `0.01`；
- consequential action TV：`0.040859025941432606`，冻结门槛 `0.01`；
- factorized-minus-joint cost：`+0.013339969268529595`，冻结门槛 `0.001`；
- belief/action/utility 严格合取：`PASS`。

编码后、注册总体运行前的单 seed 预览曾给出 utility difference `-0.005174329692319523`。它不是注册总体，也没有用于换端点、换阈值或筛 seed；冻结五 seed 总体才是注册结论。

## 冻结哈希

共同源码：

- `structure_two_backbone_falsifier.py`：`093dc522689bebc522e0c3cb893c352c47d27b43b687e4af6b2caf7393c40bbf`
- `run_structure_two_backbone_b_repairs.py`：`2485dd09824ecece89e25671facdd48424e88a1f572462c8caee68ae8fe74f34`

Task 7：

- config：`a2fb032a4fc5f67d64f43a3ab946756092b9af3623b89e35ae31f93f9dd2e2dc`
- source bundle：`5fd1e98ca676e5c45613b56754811db5069b052e7aafe004aa76f5b54b13f7d3`
- deterministic result：`05c79eafb7a91ec2652973793f5550368448a1efc7df6751d155ac880a7b5e9d`
- artifact content：`32f0930976efdcbdbdcc81210c625007317d45a424e0a1553db9f9735786b6aa`
- artifact file：`14ea3c8a8e3e2e3ccc007cdbe07143a61e39e674a3013a317e87e42243e640ca`

Task 8：

- config：`e89f4d8f25080843c20b526b5541d060071d4cd1e2dc227329a799dcfb962772`
- source bundle：`29ac3aeef4bca3621d0650a92f86e38a74d92903bfa1ef8fef3ea078d59291a8`
- deterministic result：`a5ee0ff075d81834dc9c721dd6731d30688d4654a292686d49a3f06314bc14a2`
- artifact content：`c7aa36ddf04f3dc2558dd67dfded19af8d38658b2cb4fbf8d36d5bb0c0ab6c6b`
- artifact file：`dc8dbac400fb49e1ccd5e65c1c1a559e8956f2a1806e33a9b11db55d4b17797f`

这里的 source bundle 是 task-specific provenance（任务专用来源证明），不是全局 source-bundle/manifest（源码包/清单）冻结。全局哈希须等待并行的 B/D 写入停止后统一重算。
