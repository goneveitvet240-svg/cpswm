# 项目一 SHIFT ATG-2/ATG-3 Authority Hardening（2026-08-22）

## 本轮替换的弱边界

`project-one-shift-gates@2` 不再把普通 SHA-256 自哈希当成 TEST 解封权限。旧的 `receipt.is_authentic()` 只能证明 JSON 内部自洽，报告生产者可以改字段后自行重算，不能构成 authority（权威）。

新链路使用两个同时成立的外部约束：

1. 独立 evaluator authority（评价权威）持有至少 32 bytes、权限为 `0600` 或更严格的 HMAC-SHA256 signing key；该密钥不会出现在 config、report、worker argv 或 Git snapshot。
2. authority 把状态写入持久化 M03 append-only transaction log（追加式事务日志）；receipt 绑定 committed transaction ID、global commit sequence、request hash、registration payload hash 和当时的 log head。

`SealedTestSplit` 的 scope-protected（作用域保护）模式现在只接受完整 `ShiftATG2Report + ShiftExperimentAuthority`。只传 receipt、缺 ledger、HMAC 错误、登记事务不存在、日志头不一致或代码/划分绑定漂移都会在 TEST 返回前失败。

## 进程与数据隔离

CLI 的 evaluator/supervisor 独占：

- 全套 synthetic suite（合成套件）的生成；
- TEST model input、TEST truth 和 evaluator；
- authority signing key；
- M03 event log。

ATG-2 tuning worker 由独立 Python subprocess（子进程）执行，只收到：ATG-1 topology report、validation cases、预算和 code snapshot hash。它不接收 suite config、TEST cases、TEST truth、authority key 或 event log。worker 只能输出 `ShiftATG2Draft`，无权签发可解封 TEST 的 receipt。

## 冻结前 seed 与 power analysis

新配置使用三组显式且全局互斥的 seeds：

- train：`1103, 2207, 3301`；
- validation：`4409, 5519, 6619`；
- TEST：`7727, 8837, 9949`。

每个 seed 生成 6 个 shift families，因此 train/validation/TEST 各 18 cases。冻结配置包含 `paired-seed-normal-approximation@1` power analysis（成对 seed 正态近似功效分析）：双侧 `alpha=0.05`、target power `0.8`、minimum detectable effect `0.2`、assumed paired-difference standard deviation `0.1`，重算得到至少 2 个独立 TEST seeds，计划值为 3，状态为 PASS。required seed count 和 analysis hash 都会重新计算校验。

这个 power analysis 只说明预注册假设下的 seed 数满足计划门槛，不把小型 synthetic TEST 外推成外部有效性或普遍优越性证据。

## 可独立重算的 TEST 产物

ATG-3 report 保存：

- 完整逐案例 `OnlineShiftPrediction`，按 arm 分组；
- 完整 evaluator-only TEST truth artifact；
- 每臂 prediction artifact hash 和 truth artifact hash；
- aggregate metrics（汇总指标）；
- 以 `scenario_seed_trajectory` 为单位的 paired bootstrap intervals（成对自助区间）。

反序列化时会从 truth + predictions 重新计算全部 aggregate metrics 和全部 bootstrap intervals，精确比较原报告；即使攻击者重算外层 artifact hash，也不能让篡改后的 prediction 与旧指标同时通过。

## 持久化状态机

M03 log 必须形成严格顺序：

```text
ATG2_COMPLETED (seq=1)
  -> TEST_UNSEALED (seq=2)
  -> ATG3_COMPLETED (seq=3)
```

每一步都有 transaction ID、request SHA-256、event payload SHA-256 和对应水位的 log-head SHA-256。重复解封、解封后重新调参、缺失前序事务或伪造 completion proof 均拒绝。最终报告写出前，authority 会重新读取持久日志并验证完整三步链。

## 字段与 claim policy

原先容易被误读为模型资源的 `persistent_bytes`、`parameter_count` 和 `peak_memory_bytes` 已替换为准确名称：

- `hyperparameter_json_bytes`；
- `hyperparameter_field_count`；
- `peak_tracemalloc_bytes`。

allowed/forbidden claims 改为版本化 canonical IDs（规范标识），并像 ATG-1 一样要求 tuple 的内容与顺序精确等于规范集合。仍明确禁止 general superiority、state of the art、正式结构一 B1 完成和 11 臂全实验完成。
