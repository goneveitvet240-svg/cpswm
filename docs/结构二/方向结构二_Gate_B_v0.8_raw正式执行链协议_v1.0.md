# 结构二 Gate B v0.8 raw 正式执行链协议 v1.0

状态：`REGISTERED_NOT_EXECUTED`（已登记、未执行）
Gate B：`structure-two-comparator-typed-dual-gate-b@0.8`
执行链：`structure-two-gate-b-v0.8-raw-formal-execution-chain@1.0`

本协议只为当前 comparator-typed dual gate（比较器类型化双门）v0.8 增加正式证据链，
不修改、覆盖或重新解释历史 v0.7。历史 v0.7 继续保持
`INVALIDATED_SUPERSEDED_FOR_FUTURE`。

## 1. 正式链顺序

1. `preregistration_custodian`（预注册托管方）先签 run manifest。该清单冻结 Gate B
   v0.8 协议哈希、10 个 arm 的顺序、episode、8–12 个 UUID location、1–3 个独立
   guest、逐 arm×episode action projection、评估 step、step 数、bundle 哈希和预分配
   canonical execution ID，以及每个 task 的 runtime-engine 哈希。它不引用任何尚未生成的
   未来回执哈希。
2. `canonical_execution_verifier`（规范执行验证方）从 canonical executor v0.9 的原始
   执行工件重算 task trace，签出 child receipt；child 显式引用 run manifest 的父哈希，
   且签发时间不得早于预注册时间。
3. 每个 arm×episode 的 instrumented frozen bundle（插桩冻结包）写出 canonical JSON
   raw artifact。每个 step 必须保留 live predecision state、dense joint belief、dense action
   policy、typed runtime action、truth commitment 和 consequential utility（后果效用）。
   belief/action trace 哈希必须由所存 live readout payload 确定性重算，正式 verifier 对
   所有 step 检查公共 belief/action support，而不只检查最终被评分的 step。
4. `runtime_readout_executor`（运行时读出执行方）对 raw artifact bytes、content、bundle、
   canonical task、预注册 runtime engine 和执行时段签名；engine 哈希必须同时与 run plan、
   canonical verification 和 raw artifact 一致。文件通过 `O_NOFOLLOW` 打开，并用同一 file descriptor
   的执行前后 `fstat` 校验，拒绝 symlink、hard-link alias 和读取期间变化。
5. `causal_broker`（因果代理）为每个 step 独立签名，事件顺序固定为：
   `predecision_readout_captured → runtime_action_committed → evaluator_truth_disclosed →
   consequence_utility_observed`。事件 payload 哈希必须逐项由 raw step 重算；不接受
   `truth_before_action=false` 一类调用方布尔值代替事件证据。
6. `ingest_custodian → archive_custodian`（接收托管方→归档托管方）构成两个父哈希相连、
   分别签名的 custody hop（托管跳），共同绑定 raw bytes、runtime receipt 与所有 broker
   receipts。
7. `independent_reviewer`（独立复核方）从 raw chain 重建 v0.8 `DecisionReadout`，重新运行
   comparator scorer，并签名诊断报告哈希及 `PASS/FAIL`。报告声称与复算不一致时拒绝。
8. 所有其他检查通过后，verifier-owned persistent SQLite replay registry（验证方持有的
   持久重放注册表）在单一事务内消费全部 nonce；policy 与 root-signed manifest
   同时冻结 registry UUID、enrollment digest 和由 canonical path + device + inode 导出的
   stable storage identity。每次连接全程持有 `O_NOFOLLOW` guard descriptor，并在事务前后
   比对 regular-file、single-link、path 与 descriptor identity；异路径 clone、同路径 identity
   replacement、同链 nonce 重复或活跃数据库中的跨运行 replay 均拒绝。此检查**不能**检测保留
   device/inode 的 in-place content rollback 或 filesystem snapshot restore，因此这里只登记为
   identity-replacement defense（身份替换防护），不登记为 rollback-safe（回滚安全）。正式授权仍须
   另行登记 verifier-owned monotonic/WORM backend（验证方持有的单调/只写重放后端）；当前没有该
   后端，不能以本 SQLite candidate 替代。

## 2. 独立性与新鲜度

以下七个角色必须具有互异的 authority ID、key ID 与 Ed25519 public-key hash：

- canonical execution verifier；
- runtime readout executor；
- causal broker；
- preregistration custodian；
- ingest custodian；
- archive custodian；
- independent reviewer。

trust-manifest root 还必须与七个角色全部独立。每份回执必须满足：

`max(trust_manifest.issued_at, role_anchor.enrolled_at) ≤ receipt.issued_at ≤ now ≤ receipt.expires_at`

单份回执的有效期不得超过 24 小时。倒签、预登记前执行、过期、未来签发、父回执替换及
跨 policy 替换均 fail closed（失败关闭）。

## 3. exact coverage（精确覆盖）

正式验证要求：

- canonical plan、canonical verification、runtime artifact path、runtime receipt、custody
  chain 均精确覆盖 `10 arms × all registered episodes`，不得缺失、重复或增加；
- 每个 runtime artifact 与 causal broker receipts 精确覆盖该 episode 的全部 step；
- 每个 step 的 belief/action distribution 必须无损覆盖同一 episode public ontology；
- selected runtime action 必须等于 canonical source trace 的真实 action，并经登记 projection
  双向映射到公共 `put_back/search/deliver/ask` action；
- 评分只使用预注册 step，不能在看到结果后选择 step；未被评分的 step 仍必须通过完整
  support、broker 与 custody 校验。

## 4. 当前状态和授权边界

当前 policy 明确登记：

- `trust_anchor_status = NOT_ENROLLED`；
- `replay_registry_status = NOT_ENROLLED`；
- `execution_status = REGISTERED_NOT_EXECUTED`；
- `current_formal_gate_b_passed = false`；
- `seven_operator_ablation_authorized = false`。

因此，本模块中的 cryptographic component verification（密码学组件验证）即使在测试夹具中
完整通过，也只返回 `VerifiedRawChainCandidateV08`，其 formal Gate B 和七算子授权字段均为
不可提升的 `false`。当前唯一官方状态函数不接收调用方证据；要产生正式正向结果，必须由新
policy revision 登记真实独立 trust manifest、持久 replay custody 和已完成 raw execution，
再由上层唯一 `TrustedSevenOperatorAblationAuthorization` 聚合器复核全部依赖。

本协议禁止运行可信七算子消融，也不重算或改写全局 manifest、source-bundle、checkpoint。
