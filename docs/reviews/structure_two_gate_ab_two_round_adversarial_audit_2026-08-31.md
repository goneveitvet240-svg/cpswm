# 结构二 Gate A / Gate B 两轮对抗审核

日期：2026-08-31  
范围：v0.4 fresh-world Gate A（新世界任务有效性门）、Gate B（实验臂实质可区分性门）及其授权链  
证据等级：仓库内实现、构造攻击与确定性复算；没有生成 v0.4 validation world，没有打开 sealed holdout

## 结论

两轮审核后，Gate A/B 的仓库内实现与失败关闭边界通过定向验证。Gate B 修复了两项会削弱
科学解释力的问题：仅靠一个输出差异即可通过，以及动作轨迹没有显式绑定模型选择的物理验证。

正式 Gate A/B 仍未运行，也不允许运行。缺少原始 v0.2 holdout seeds、custody salt 和独立
Ed25519 托管密钥时，final manifest、Gate A artifact 和 dual-gate authorization 均不存在。

## 第一轮：来源、授权与伪造攻击

| 攻击 | 预期 | 结果 |
|---|---|---|
| 用 unsigned DRAFT 直接生成验证世界 | 拒绝 | 通过 |
| 篡改 Gate A estimator、world distribution 或阈值 | 拒绝 | 通过 |
| 将 Gate B 分歧阈值降为零 | 拒绝 | 通过 |
| 修改 producer source bundle | 拒绝 | 通过 |
| Gate B trace 绑定错误 Gate A 或错误 manifest | 拒绝 | 通过 |
| 截断、重排、重复 rollout | 拒绝 | 通过 |
| 修改 trace 后自行重算 content hash | 签名失败 | 通过 |
| 使用攻击者自选 Ed25519 key | trust-anchor 失败 | 通过 |
| 十臂来自不同 producer run 或 source bundle | 拒绝 | 通过 |
| seed 与 train / prior validation / holdout 冲突 | 拒绝 | 通过 |

第一轮没有发现可绕过授权顺序进入方法比较的路径。

## 第二轮：统计与语义有效性攻击

### S1：单 token 差异可伪造“方法不同”——已修复

旧 Gate B 的绑定条件只有“预测序列不完全相同”。两个方法即使只在一个位置不同也能通过。

修复后同时要求：

- 每一对申报实验臂的 prediction disagreement rate（预测分歧率）至少为 `0.01`；
- 至少 `0.20` 的回合出现不止一种完整实验臂轨迹；
- 任何完全相同的实验臂仍直接失败。

构造攻击确认：`100` 个预测中只改 `1` 个、门槛为 `0.02` 时，Gate B 失败；把差异限制在
`2` 个回合中的 `1` 个、回合覆盖门槛为 `0.75` 时，Gate B 失败。

### S2：轨迹遗漏 physical verification——已修复

旧 token 只有 `put_back > search_head`。如果一个方法执行 physical verification（物理验证）
但验证没有改变两个端点的 top-1，Gate B 会把外部行动差异漏掉。

当前每步 token 固定为：

```text
verify={0|1}|put_back_location>search_head_location
```

`verify=1` 只在模型选择并实际执行物理验证时记录。内部 promote / escrow 账本操作不冒充外部
行动。验证计数每步只能保持或增加一；倒退或一次增加超过一会失败关闭。

### S3：external-neighbor adapter fidelity——未解决且必须保留

签名、source bundle 和 Gate B 只能证明“冻结适配器确实产生了这些不同轨迹”，不能证明
BrainCTL、Active Dreaming、O-STaR 等 matched adapter 忠实复现官方完整实现。正式论文证据仍需
独立 adapter review、官方实现复现或作者确认。当前 Gate B 不得被描述为外部方法有效性门。

### S4：阈值的外部依据——未解决但已披露

`0.01` 与 `0.20` 沿用 corrected-instrument validity audit，是作者选择的 materiality threshold
（实质性阈值），不是文献或真实机器人数据给出的自然常数。正式冻结前可由用户保留或修改；
一旦签署，不得依据 validation 结果回调。

## 复验

- Gate A/B 相关完整定向套件：`76 passed`；
- 修改文件：`ruff check` 通过；
- rolling train reference 确定性复算保持通过：search top-1 outer mean gain `0.045221`，
  worst-fold gain `0.037706`；
- sealed holdout：未读取；
- v0.4 validation world：未生成；
- method comparison：仍为 forbidden。

当前 producer/custodian source bundle SHA-256：

`5c0240d16ad24d8cad2dd4d96263615f1e9890ba510fd131491057e45a48064d`

当前 unsigned validation DRAFT SHA-256：

`8093c7631678d471be65e1b5ae3917a69a0a3901e90b8c55fd437ecc84b9cdad`

## 最终判定

1. 仓库内 Gate A 实现、训练参考复算和授权边界：通过本轮审核。
2. Gate B 完整性、实质分歧和外部验证动作绑定：修复后通过本轮审核。
3. 正式 Gate A/B：尚未运行，结果未知。
4. external-neighbor adapter fidelity：仍未建立。
5. 托管材料缺失：继续阻断 final manifest 和任何正式比较。
