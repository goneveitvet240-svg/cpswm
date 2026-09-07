# 结构二最终对抗审核第一轮：正向输出与伪造完整路径

日期：2026-09-07（Asia/Shanghai）

结论：**本轮通过，但覆盖等级仅为 partial adversarial coverage（部分对抗覆盖）。**
当前源码上的 130 个定向攻击测试全部通过；没有发现仍可把字段完整但因果错误的本地对象提升为正向授权的路径。本结论不证明不存在未知缺陷，也不建立独立托管或外部有效性。

## 攻击面与结果

| 攻击面 | 本轮检查 | 结果 |
|---|---|---|
| Trace contract（轨迹契约） | owner mass 与 actor posterior、delta、prediction count/index、最终 wrapper-visible prediction、动作枚举、utility/regret 重算 | PASS |
| Evidence factor trace（证据因子轨迹） | typed source semantics、source payload、record id、derive/commit 重放与重复 materialization | PASS |
| D1/D2 正向资格 | forged-complete receipt、生成数据冒充 ProcTHOR、缺失 D2 实采回执 | PASS；两项均保持 `UNAVAILABLE_EXTERNAL_COLLECTION_EVIDENCE` |
| Task 11→12 文件接口 | full-budget gzip、K=24 子集、错误层级输入、condition/kernel/trace 计数 | PASS；错误地把 Task 11 raw 直接送入 Task 12 recompute 时被 `coordinate` 缺失立即拒绝 |
| Engineering receipt（工程回执） | 命令替换、缺命令、失败 exit code 配正向 aggregate、重算无密钥外层哈希 | PASS |
| Gate B / 七算子授权 | forged-complete diagnostic、回放注册、调用方回填时间、策略/根签名绑定 | PASS；未登记状态不能生成正式授权 |

本轮命令覆盖：

- `tests/test_evidence_factor_trace.py`：7
- `tests/test_project_two_revision_action_trace.py`：11
- `tests/test_structure_two_comparator_typed_dual_gate_b_v0_8.py`：37
- `tests/test_structure_two_engineering_trust_checkpoint.py`：5
- `tests/test_structure_two_gate_b_v0_8_raw_formal_execution.py`：23
- `tests/test_structure_two_strongest_neighbor_gate.py`：9
- `tests/test_structure_two_trusted_ablation_authorization.py`：38
- 合计：130；exit code 0。

## 绑定证据

- strongest-neighbor report content SHA-256：`08bb22d1baba6b2132ac26520ca2dfd4d45c14cbde15c1ccd2944f71c7df820b`
- corrected-instrument report content SHA-256：`a556c4e0d3f8aff4cdc545a85f0b7e8b84bf5f81c34e7bac944c64137238fd95`
- Task 11 result SHA-256：`22971c0e31f4634f5266d03dbe204c8f0a30518d315e7c27045fb053b9a76214`
- Task 12 result SHA-256：`66b3a62d976cff28ed8926368d182dddd9ab741e3ec27aa5c0614699ae74de73`
- engineering audit receipt content SHA-256：`562240665957fd7231b0cdfc2c5231139e31bd363bd36876e3fc3642d4054d46`
- engineering checkpoint content SHA-256：`83d1ecaba03e23f5916322e7a8aed05c3a30bbaca9941b5c8af2cefca851ec9b`

## 本轮边界

- 本轮证明的是当前工作树上的本地语义拒绝能力，不是历史真实性证明。
- unkeyed SHA-256（无密钥哈希）只提供内容一致性；不能替代外部不可变锚。
- 原生复现、Gate B 正式执行、D1/D2 合格采集和独立托管仍未完成，因此论文级公平比较与七算子优越性均不得宣称。
