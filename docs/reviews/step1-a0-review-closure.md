# Step 1 A0 阻断修复与复审候选证据

实现状态：`implemented_vertical_slice`  
审核门：`BLOCK`  
验收状态：`not_accepted`
基线提交：`53d193ca55a99ea2a51ea2499ca1755d281ab8fc`

## 阻断项与关闭证据

| 阻断项 | 修复 | 自动化证据 |
|---|---|---|
| 同一事务允许重复 `record_id` | M03 在任何状态变更前检查批内 ID 唯一性 | `test_duplicate_record_id_inside_one_transaction_is_rejected` |
| 空日志水位随读取时间变化 | 零水位固定为序号0、零UUID和 Unix epoch UTC | `test_empty_watermark_and_fingerprint_are_stable` |
| ReplayManifest 未绑定运行版本和输入日志 | 核验实际 Git HEAD、源码树哈希、活动配置、模型版本、指定水位和日志指纹 | `test_replay_rejects_manifest_runtime_and_input_mismatches` |
| ReplayManifest 指纹未绑定 runtime 使用的逻辑时间 | 指纹只排除 `replay_manifest_id`，纳入作为 replay clock（回放时钟）的 `created_at` | `test_replay_manifest_fingerprint_ignores_identity_but_binds_logical_time` |
| ReplayManifest 可通过 `model_copy` 绕过完整契约 | `ReplayRunner` 入口先递归拒绝 live extra fields（活动额外字段），再完整 round-trip 验证；负容差或注入字段均在 handler 执行及日志写入前拒绝 | `test_replay_runner_revalidates_manifest_model_copy_bypass` |
| 同一 manifest 的输出日志提交时间取进程墙钟，ReplayRun 又漏掉该时间 | replay append 显式使用 manifest 逻辑时间；事务、记录和 watermark 共享该时间；比较完整 output watermark（含 `recorded_at`） | `test_replay_is_deterministic_across_fresh_runtimes`、`test_replay_comparison_detects_changed_output_log_time` |
| ReplayRun output fingerprint 未参与比较且未绑定 payload | 契约强制 payload/hash 等长并逐项重算；比较入口递归拒绝 live extra fields 后重新验证，以关闭 `model_copy` 绕过；零容差显式比较指纹，包括数值相等但 canonical JSON 不同的 `-0.0`/`0.0` | `test_replay_run_rejects_unbound_output_fingerprints`、`test_replay_comparison_revalidates_model_copy_bypass`、`test_zero_tolerance_compares_self_consistent_canonical_output_hashes` |
| Replay 比较可由调用方放宽 manifest 声明容差 | `ReplayRun` 绑定有限非负的 `manifest_numeric_tolerance`；默认比较使用该声明，兼容参数只能收紧，两个 run 的声明必须一致；manifest 指纹在 dispatch 前完成计算 | `test_replay_comparison_cannot_widen_manifest_numeric_tolerance`、`test_replay_comparison_rejects_non_finite_numeric_tolerance`、`test_replay_comparison_rejects_mismatched_manifest_tolerances`、`test_replay_runner_revalidates_manifest_model_copy_bypass` |
| 零容差大整数被转换为浮点数 | 整数保持精确整数比较；仅正容差数值比较使用十进制差值 | `test_zero_tolerance_compares_large_integers_exactly` |
| 集成测试不是真正重启回放 | M03日志和清单落盘，由两个独立Python进程分别加载和执行，再比较输出及执行谱系 | `test_restart_replay_loads_serialized_log_in_independent_processes` |
| emitted message 身份未确定性绑定 | 运行时按父消息、handler、attempt 和输出序号生成确定性 `message_id`，完整消息身份和顺序进入回放比较 | `test_emitted_message_identity_and_order_are_deterministic` |
| emitted message 允许跨 session | 强制继承输入消息的 `session_id` | `test_emitted_message_cannot_cross_session_boundary` |
| emitted message 完整契约可被 `model_copy` 绕过 | runtime 出口从普通字段重建并重新验证完整 `RuntimeMessage`，拒绝 stale payload hash、空名称、非法 schema、负序号、非法枚举和额外字段 | `test_emitted_message_is_fully_revalidated_at_runtime_boundary`、`test_valid_emitted_message_is_round_trip_valid_after_normalization` |
| incoming message / output record 完整契约可被 `model_copy` 绕过 | runtime 入口重建并验证 incoming `RuntimeMessage`；持久化前按每条 output record 的具体模型重建、拒绝额外字段并完整验证 | `test_incoming_message_is_fully_revalidated_before_dispatch`、`test_handler_output_record_is_fully_revalidated_before_persistence` |

emitted message identity（发出消息身份）由 runtime（运行时）拥有：处理器给出的 `message_id` 和 `created_at` 会被运行时按确定性执行上下文规范化，而 household、session、trace 和 causation 仍由运行时严格校验。

当前 emitted-message 身份、session 继承和完整契约复验由同进程 fresh runtime（全新运行时）测试覆盖；现有独立 Python 进程重启测试使用不产生 emitted message 的 `AlignmentHandler`，因此本页不声称 emitted-message 已完成跨进程复验。

## 严格回放链

```text
M03 canonical input log
→ 序列化 TransactionLogDump
→ ReplayManifest 绑定 input watermark + input log SHA-256
→ 新 Python 进程加载日志和清单
→ 重新计算 Git HEAD + source tree SHA-256 + configuration hash
→ 核验 active model versions
→ 从指定水位解码 RuntimeMessageRecord
→ M04 执行并把输出提交到独立日志
→ 保存 output payload、完整 watermark（含 canonical committed_at 对应的 recorded_at）和 handler execution provenance
→ 第二个独立进程重复执行
→ 零容差逐字段比较
```

输入日志与输出日志必须是不同实例，防止回放过程修改自身输入。严格回放日志只能包含 `cpswm.RuntimeMessageRecord`；遇到其他记录类型、缺失水位或指纹不符时立即拒绝。

## 状态说明

本记录表示已针对审核意见完成实现和本地自动化验证，不冒充外部审核已经放行。当前全项目审核门仍为 `BLOCK`；实现状态仅为 `implemented_vertical_slice`，必须经复审确认才能改为 `accepted`。
