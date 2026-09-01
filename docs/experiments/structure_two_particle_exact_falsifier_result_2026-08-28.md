# Structure Two particle exact-enumeration falsifier result（2026-08-28）

协议：`structure-two-exact-enumeration-falsifier@0.1`  
证据状态：**finite synthetic development conformance evidence；不是论文收益证据**  
方法回执：`structure-two-nap-rbtpr-rc@0.1`

正式 artifact：

`artifacts/project_two_v04_development/structure_two_particle_exact_falsifier_v0_1.json`

- report content SHA-256：
  `01dc66d05f0e2f3896dc8ece23ed3a13d1311e3c4d8de22bb48bb2c2c1809381`
- artifact byte SHA-256：
  `369c45b1ca2620e5ef73c677054c811cb70fe00d5f155c7f1a5bd553f363ca5a`

artifact 同时绑定 falsifier 源码、所选方法源码、方法选择回执和开发协议四个文件哈希。

## 1. 总体结果

360个精确状态、16个完整 `2^4` 场景、近似状态预算24下：

| 方法 | mean TV ↓ | 真值支持率 ↑ | exact-Bayes action regret ↓ | action match ↑ | 候选评分数 ↓ |
|---|---:|---:|---:|---:|---:|
| incremental beam | 0.3710 | 0.3750 | 0.0666 | 0.7500 | 384.0 |
| full-rerun beam | **0.0745** | **0.9375** | **0.0000** | **1.0000** | 744.0 |
| bootstrap particle filter | 0.7524 | 0.1875 | 0.0507 | 0.8125 | **48.0** |
| typed particle revision | **0.0959** | **0.8750** | **0.0000** | **1.0000** | 502.6 |

类型化粒子修订相对不可复苏增量束搜索：

- mean TV 从0.3710降至0.0959；
- 真值支持率从0.375升至0.875；
- exact-Bayes action regret 从0.0666降至0；
- action match 从0.75升至1.0。

它仍未超过完整重跑束搜索：TV 更高0.0214，真值支持率低0.0625；但平均候选评分数减少
约32.4%。因此当前支持的是“较低评分成本下逼近完整重跑”，不是“后验质量超过完整重跑”。

## 2. 高归因歧义＋恶劣迟到反馈子集

| 方法 | mean TV ↓ | 真值支持率 ↑ | action regret ↓ | action match ↑ |
|---|---:|---:|---:|---:|
| incremental beam | 0.5843 | 0.0000 | 0.1329 | 0.5000 |
| full-rerun beam | **0.1889** | **0.7500** | **0.0000** | **1.0000** |
| bootstrap particle filter | 0.8443 | 0.0000 | 0.0661 | 0.7500 |
| typed particle revision | 0.2497 | 0.5000 | **0.0000** | **1.0000** |

类型化粒子修订在最关键压力子集中恢复了 exact-Bayes 行动，但只在一半场景保留真值状态，
低于完整重跑束搜索的0.75。这是当前最重要的失败信号：单字段邻域 rejuvenation（粒子复苏）
仍不足以稳定恢复同时发生的人物、机制、原因和阶段修订。

## 3. 门禁结果

七项 development gates 全部通过：

- 总体 TV 不差于增量束搜索；
- 总体行动遗憾不差于增量束搜索；
- 总体真值支持不差于增量束搜索；
- 总体 TV 位于完整重跑束搜索0.05以内；
- 候选评分次数少于完整重跑束搜索；
- 压力子集 TV 不差于增量束搜索；
- 压力子集行动遗憾不差于增量束搜索。

这只表示确定性类型化粒子修订没有被第一轮有限模型立即证伪。

## 4. 对新结构二的含义

### 已得到支持的局部判断

1. 显式多假设和迟到证据 rejuvenation 比只重加权旧 beam 更合适；
2. `TypedParticleState → ParticleRevisionReceipt → unresolved normalization` 合同可以执行；
3. 阶段后验已真正进入行动读出，不再出现 CCRR 变量存在但行动完全不消费的假通过；
4. 完整重跑仍是必须保留的强恢复基线。

### 尚未得到支持

1. neural amortized proposal 尚未训练或运行；
2. PCHMP 尚未接成神经提议器或粒子势函数；
3. OPCEU、CF-BOCPD、RGRC、CCRR、CIAV 的真实联合收益未测试；
4. 没有与 corrected AMG adapter 比较；
5. 没有真实感知、家庭或机器人证据；
6. 不能声称完整新路线已经成功。

## 5. 下一道阻断门

下一轮不应直接扩大完整七算子实验，而应先修复压力子集的真值支持缺口：

1. 增加二字段／角色链结构化 rejuvenation kernel；
2. 保留 deterministic PCHMP proposal 作为强后备；
3. 训练真实 neural amortized proposer 后，和确定性提议器使用相同粒子预算独立比较；
4. 在新随机种子下要求高歧义＋恶劣反馈真值支持率不低于完整重跑 beam 的预注册容差；
5. 通过后才接 corrected AMG、旧七算子系统和完整行动级比较。

如果神经提议器不能改善压力子集支持率，或只靠显著增加候选评分数追平完整重跑，则当前
amortized proposal/rejuvenation 设计必须重构。

