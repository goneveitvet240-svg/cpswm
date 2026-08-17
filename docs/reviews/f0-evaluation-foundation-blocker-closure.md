# F0 评价底座与 A0 回放阻断修复及复审证据

日期：2026-08-14  
审核门：`BLOCK`  
实现状态：`implemented_vertical_slice`  
验收状态：`not_accepted`  
范围门禁：`review_blockers_only`

本文记录截至本轮审核阻断的本地修复和可复现证据，用于提交外部复审。早期 `106 passed` 后的复审结论仍为 `BLOCK`；本文不宣称审核已经放行。只有复审者确认后，状态才能改为 `accepted`。多人物、访客污染、交接和变化检测扩展仍暂停。

本节列出的截至本轮阻断目前均已在本地实现与反例测试中 addressed（已处理），但这只是 re-review candidate（复审候选）状态，不是审核者结论。当前唯一有效状态仍为 `BLOCK / implemented_vertical_slice / not_accepted`。

## 1. 阻断项与反例证据

| 阻断项 | 修复后的约束 | 自动化反例 |
|---|---|---|
| P0 真值泄漏、因果观察与视野几何 | 机会严格来自显式 primary-task robot trajectory（主任务机器人轨迹）的 pose/frustum samples（位姿/视锥采样），而非真值事件；按机会时刻查询因果状态并做视锥相交；FOV coverage 为零或目标在视锥外时禁止检测；未检出时，隐藏 relocation（迁移）的实际视锥相交和未来目的地几何不会进入公共 opportunity/result；普通 `run` 路径不再物化 GT trajectory（真值轨迹）；public result（公共结果）不含真值或 plan 身份，特权 view（视图）需 benchmark capability（基准能力）且与公共 API 分离；simulator 入口及其记录 schema 会重验证；leakage detector（泄漏检测器）扫描完整 public visible result（公共可见结果），覆盖连字符 UUID、`UUID.hex`、顶层字符串 carrier（承载字段）与显式特权标签 | `test_observation_clock_is_independent_of_hidden_truth_event_cardinality`、`test_undetected_target_relocation_does_not_leak_through_opportunity_visibility`、`test_future_hidden_destination_without_geometry_does_not_change_pre_event_run`、`test_observation_queries_causal_state_before_a_future_placement`、`test_zero_field_of_view_coverage_never_emits_a_detection`、`test_camera_frustum_excludes_target_outside_primary_task_view`、`test_public_simulator_api_requires_explicit_capability_for_truth`、`test_simulator_revalidates_model_copy_inputs_before_execution`、`test_evaluator_rejects_mislabeled_visible_record_schema`、`test_leakage_detector_recognizes_compact_gt_event_uuid_encoding`、`test_leakage_detector_scans_visible_result_top_level_carriers` |
| P0 运行身份未绑定内容 | `plan_id` 绑定规范化生成配置和生成器版本；`simulation_run_id` 绑定 plan/policy ID+hash、实现版本、时间、长度、seed 和两个目标对象；`evaluation_run_id` 绑定 manifest hash/version、simulation content hash、track 和 evaluator version | `test_content_bound_plan_simulation_and_evaluation_ids_change`、`test_simulation_run_id_rejects_self_consistent_projected_input_tampering`、`test_simulation_run_id_rejects_self_consistent_scheduled_target_tampering` |
| P0 manifest 绑定不完整 | evaluator 核验 manifest 自身内容哈希、支持版本、duration、seed、plan、policy、simulator、GT run ID、实体集合、时域和预算；checked-in manifest 额外保存预期 simulation content hash | `test_evaluator_rejects_incomplete_manifest_bindings`、`test_evaluator_rejects_a_verification_over_budget`、`test_manifest_rejects_self_consistent_tampered_simulation_hash` |
| P0 recall 定义错误 | 使用 maximum-cardinality matching（最大基数匹配）完成一对一匹配；分母只包含 scheduled observation target（计划观察目标），隐藏无关物体不影响分数；异常召回只评价该目标的 temporary exception（临时异常）并单独匹配；零真值样本输出 `value=null, sample_count=0` | `test_recall_matching_maximizes_cardinality_instead_of_greedy_latest_truth`、`test_controlled_recall_ignores_unrelated_hidden_truth_events`、`test_contextual_or_persistent_change_is_not_scored_as_anomaly`、`test_recall_with_no_anomaly_truth_is_undefined` |
| P1 emitted message 身份不确定 | runtime 按父消息完整 fingerprint、handler、attempt 和输出序号生成确定性 ID，并固定 `created_at`；回放比较包含完整身份和 tuple 顺序 | `test_emitted_message_identity_and_order_are_deterministic` |
| P1 emitted message 可跨 session | emitted message 必须继承输入消息的 household、session、trace 和 causation | `test_emitted_message_cannot_cross_session_boundary` |
| P1 emitted message 契约绕过 | runtime 出口完整重新验证 emitted `RuntimeMessage`，拒绝 stale payload hash、空名称、非法 schema、负序号和非法枚举 | `test_emitted_message_is_fully_revalidated_at_runtime_boundary` |
| P1 runtime 入口与记录契约绕过 | `dispatch` 入口完整重验证 incoming message（传入消息）；handler output record（处理器输出记录）在持久化前按具体模型完整重验证，非法对象不会执行 handler 或写入日志 | `test_incoming_message_is_fully_revalidated_before_dispatch`、`test_handler_output_record_is_fully_revalidated_before_persistence` |
| P1 预算与成本过度声明 | manifest 只保留已选择观察动作/验证动作预算；成本指标改为 `declared_primary_task_additional_action_cost_total`，仅汇总 selected action（已选择动作），并明确不代表实际中断/延迟 | `test_f0_budget_rejects_unmeasured_legacy_limits_and_incoherent_caps`、`test_unselected_verification_does_not_consume_selected_budgets`、`test_declared_action_cost_counts_only_selected_observation_actions` |
| P1 检测身份与计划目标未绑定 | detection result ID（检测结果身份）绑定除自身 ID 外的完整实现内容；成功检出的对象必须等于 policy/manifest 的 scheduled observation target（计划观察目标） | `test_detection_result_identity_changes_with_realized_target_state`、`test_evaluator_rejects_stale_detection_result_identity`、`test_evaluator_rejects_detection_for_a_non_scheduled_object` |
| P1 evaluation report 自洽篡改 | 报告反序列化时重算 evaluation/metric IDs，核验 report→metric 身份继承、名称/ID 唯一、task family、recall/coverage 取值范围、`n=0 ↔ null` 和 leakage flag/reasons | `test_evaluation_report_rejects_self_consistent_run_identity_tampering`、`test_evaluation_report_rejects_metric_binding_and_duplicate_names`、`test_evaluation_report_rejects_invalid_recall_semantics` |
| P0 A0 回放时间与身份分叉 | `ReplayManifest.fingerprint` 纳入实际作为 replay clock（回放时钟）的 `created_at`；同一 manifest 的 transaction/record/watermark 统一使用该逻辑时间；ReplayRun 比较完整 output watermark | `test_replay_manifest_fingerprint_ignores_identity_but_binds_logical_time`、`test_replay_is_deterministic_across_fresh_runtimes`、`test_replay_comparison_detects_changed_output_log_time` |
| P0 A0 输出指纹与声明容差未进入严格比较 | `ReplayRun` 强制 output payload/hash 等长且逐项重算并保存 manifest-declared numeric tolerance（清单声明数值容差）；compare 入口重新验证以拒绝 `model_copy` 绕过；两个 run 的声明必须一致，调用方只可收紧、不能放宽；拒绝非有限容差；零容差同时比较 canonical output fingerprints（规范输出指纹） | `test_replay_run_rejects_unbound_output_fingerprints`、`test_replay_comparison_revalidates_model_copy_bypass`、`test_replay_comparison_cannot_widen_manifest_numeric_tolerance`、`test_replay_comparison_rejects_non_finite_numeric_tolerance`、`test_replay_comparison_rejects_mismatched_manifest_tolerances`、`test_zero_tolerance_compares_self_consistent_canonical_output_hashes` |
| P1 A0 replay boundary 可被 `model_copy` 绕过 | ReplayRunner/compare 在 round-trip 前先递归拒绝顶层和嵌套 live extras，并重新验证 ReplayManifest/ReplayRun 完整契约；非法负容差或注入字段不执行 handler、不写输出日志 | `test_replay_runner_revalidates_manifest_model_copy_bypass`、`test_replay_comparison_revalidates_model_copy_bypass` |
| P0 A0 调用方可放宽 manifest 声明容差 | `ReplayRun` 保存有限非负的 manifest tolerance（清单容差）；比较默认使用该声明，兼容参数只允许收紧，两个 run 的声明必须一致；manifest 指纹在 dispatch 前完成计算 | `test_replay_comparison_cannot_widen_manifest_numeric_tolerance`、`test_replay_comparison_rejects_non_finite_numeric_tolerance`、`test_replay_comparison_rejects_mismatched_manifest_tolerances` |
| P0 grounded-search 写前边界 | common pipeline（公共管线）在入口重验证 request 和可替换 fusion result（融合结果），把 query/model、candidate grounding（候选落地）、posterior support（后验支持集）与 hard constraints（硬约束）绑定回 request；`decide` 与闭环均完整复验 observation action；append 前再复验 observation、execution、outcome model 和 posterior transition；request/result/observation/opportunity/feedback 的 schema name/version 与具体契约强绑定；execution opportunity 与反馈时间自洽并在一个事务提交 | `test_direction_three_rejects_recursive_live_extras_on_input`、`test_direction_three_request_requires_canonical_schema_label`、`test_decide_revalidates_observation_actions`、`test_common_pipeline_rejects_fusion_grounding_drift_without_a_write`、`test_pipeline_binds_fusion_result_to_request`、`test_verification_observation_requires_canonical_schema_label_without_a_write`、`test_common_pipeline_rejects_unbound_provider_observations_without_a_write`、`test_execution_feedback_must_bind_real_execution_context_without_a_write`、`test_execution_records_require_schema_and_time_consistency_without_a_write`、`test_execution_outcome_model_is_validated_before_atomic_write`、`test_execution_posterior_failure_leaves_no_partial_batch` |
| P1 CHEH 来源一致性与去重 | `cheh@0.3` 的 `hypothesis_set_id` 绑定完整端点内容；branch/revise/retract/rebuild 先递归拒绝 `model_copy` live extras、绑定具体 endpoint/evidence schema 并完整复验；证据绑定 household/session/trace、物体、已知端点及精确端点时间；record/cluster/semantic fingerprint 均禁止复用，semantic fingerprint 把 `EvidenceRef` 当作内容集合并规范化 `-0.0/0.0`；retract 必须提交对目标人物给出零概率的完整反证 | `test_cheh_hypothesis_set_identity_binds_complete_endpoint_content`、`test_cheh_branch_rejects_mislabeled_endpoint_schema`、`test_cheh_revise_rejects_mislabeled_actor_evidence`、`test_cheh_rejects_semantic_evidence_clone_with_fresh_wrapper_ids`、`test_cheh_rejects_duplicate_evidence_ref_wrapper_across_revisions`、`test_cheh_retract_rejects_duplicate_ref_semantic_clone_in_same_tuple`、`test_cheh_semantic_fingerprint_normalizes_negative_zero`、`test_cheh_retract_rejects_negative_zero_semantic_clone_in_same_tuple`、`test_cheh_rejects_actor_evidence_from_a_different_scope`、`test_cheh_rejects_actor_evidence_one_hundred_days_after_its_endpoint`、`test_cheh_retract_rejects_counterevidence_without_a_known_endpoint` |
| P1 S3 直接入口依赖环境 | 两个 `apps/direction_three` 入口在导入项目包前按脚本位置加入 `src`，不依赖调用方的 `PYTHONPATH`；演示 ID 固定以保证输出稳定 | `test_direction_three_cli_runs_directly_without_pythonpath` |

对抗复审又补充了以下绕过测试：截断 result 但保留旧 hash、同步重算 self-hash 后缺失 result、篡改 ground truth、通过 `model_copy` 注入重复 manifest metric、以及 result/opportunity 的 household、session、trace、metadata time、detection time 不一致。相关测试位于 `tests/test_f0_long_horizon_vertical_slice.py`。

## 2. 内容与版本绑定链

```text
manifest_id: oam-phm-f0-book-on-sofa
manifest_version: 0.4.0
manifest_sha256: 7850ac8317c4115a59a10380e2d829489b4356d9496ebcf0184f65e8a9d1bc3f
routine_plan_id: 00fb7f52-5845-5bbd-b6f7-f4443537f022
routine_plan_sha256: ea4cf80aca652a596b01ad00caf1f91ba60067130b3c1d7f6993cce1b08bfc15
observation_policy_id: cup-search-incidental@0.3
observation_policy_sha256: 97cc9231c97922795b334bd901ec565758a53b601e27ce7f932f52bce6083371
simulation_run_id: 8ed1d2e2-684e-5bb5-8bfc-542468ef9d15
simulation_content_sha256: 6aa3dd5023478428888ddb6dae1a970b711177e70e6d3d800fc668e5db2cfce4
generator_version: synthetic-routines@0.2
simulator_version: symbolic-simulator@0.8
evaluator_version: f0-evaluator@0.9
```

`BenchmarkManifest.expected_simulation_content_sha256` 等于上面的 simulation content hash。evaluator 先校验 simulation 自身哈希，再与 manifest authority anchor（清单权威锚）比较，之后才计算指标。

当前 checked-in 资产为 `book_on_sofa_manifest_v0.4.json`、`book_on_sofa_routine_v0.2.json` 和 `book_on_sofa_policy_v0.3.json`；manifest 显式绑定 routine plan、policy 和 simulation 内容哈希。policy、simulator、evaluator 与 manifest 均因本轮轨迹/视锥、公共—特权隔离和严格评价语义发生变化而升级；routine generator 未变，保持 v0.2。

## 3. 可复现命令与结果

以下是本轮修复后的当前本地证据；它只说明复审候选快照可运行且反例已纳入自动化测试，不构成外部验收。

```bash
.venv/bin/python -m pytest -o addopts='' --collect-only -q
# 306 tests collected

.venv/bin/python -m pytest -o addopts='' -q
# 306 passed

.venv/bin/python -m pytest -o addopts='' -q \
  tests/test_f0_long_horizon_vertical_slice.py \
  tests/test_m04_runtime_orchestration.py \
  tests/test_step1_a0_integration.py \
  tests/test_step1_restart_replay.py \
  tests/test_direction_three_grounded_search.py \
  tests/test_counterfactual_event_hypergraph.py
# 208 passed

.venv/bin/python apps/evaluation_runner/run_f0_vertical_slice.py > run-a.json
.venv/bin/python apps/evaluation_runner/run_f0_vertical_slice.py > run-b.json
cmp -s run-a.json run-b.json
# exit 0

shasum -a 256 run-a.json run-b.json
# 7386c2e6e6e7b686a74e6be6f64af8e90fbecce593cdf587a910abf652a740d8  run-a.json
# 7386c2e6e6e7b686a74e6be6f64af8e90fbecce593cdf587a910abf652a740d8  run-b.json

env -u PYTHONPATH .venv/bin/python apps/direction_three/run_grounded_search_oracle_closed_loop.py
# SHA-256: 054f5039ef576c84bc5230f949c6e7edad32693e93a298f222726161ae08c6c6

env -u PYTHONPATH .venv/bin/python apps/direction_three/run_grounded_search_vertical_slice.py
# SHA-256: 0c0f04aaa5083397a9e8bda984b3f6f2f8759ff71b756c93c5d9feea7edc3ddc

git diff --check
# exit 0
```

初始阻断发现时的 CLI SHA-256 是 `7315c3c497b275f894a4ff9f420b30b24ae3b7eeb039905506f6fd1aab8b4b35`；第一轮修复后是 `2882b0b76ebf6bc416a01074766006721aa09b0e5766183858cab1647d28cf6d`。后续修复改变了契约、版本、身份和报告字段，因此当前哈希再次按预期变化。

`ground_truth_leakage_detected` 的声明范围是 exact privileged-reference detector（精确特权引用检测器）：它检测机器人侧记录中的真实 GT event UUID、其连字符/compact hex（紧凑十六进制）字符串嵌入和显式 ground-truth/gt-event/privileged 标签。它不是通用信息流证明，也不宣称识别任意编码或隐写泄漏；结构性隔离由 public/privileged API separation（公共/特权接口分离）、capability gate（能力门）、任务轨迹、因果状态查询、视锥几何、空机会候选集及未检出字段约束共同承担。

## 4. 明确信任边界

本轮把版本库内的 checked-in manifest 视为可信 benchmark authority。`manifest_sha256` 是内容身份，不是数字签名；若威胁模型允许攻击者同时改写可信 manifest 和所有基准资产，则还需要签名或外部不可变登记。本轮审核项要求的是实验身份、输入内容和评价产物的可复现绑定，不扩展到供应链签名。

同理，evaluator 验证的是“simulation 输出与可信 manifest authority anchor（权威锚）一致”，不会仅凭输出重新执行原始 simulator 来证明每个 sensor outcome（传感结果）确实来自因果状态。若需要这种更强保证，应把原始 plan/policy 资产交给独立执行器重跑并比对，而不是扩大 leakage detector 的声明。

`BenchmarkGroundTruthCapability（基准真值能力）` 是 Python API boundary（接口边界），不是进程级安全沙箱；它防止普通调用路径意外获得真值，不抵御能任意导入内部模块并执行代码的同进程攻击者。

方向结构三的 common pipeline（公共管线）现已在任何由 pipeline 自身执行的 canonical append（规范追加）前统一重验证 request、可替换 fusion result（融合结果）、provider action、observation、likelihood model、calibration domain、realized outcome 与候选覆盖；fusion result 会绑定回 request 的 query/model、候选落地、后验支持集及硬约束；request/result/observation/opportunity/feedback 的 schema name/version 会绑定具体契约，execution opportunity 与 feedback 还校验逻辑时间；`GroundedTaskExecution（落地任务执行包）` 绑定选中候选、实体、位置、实际 action/type、execution opportunity 与 feedback，并把同次执行记录作为单事务追加。反例覆盖错误 fusion candidate/query/model/support、错误 action/model/domain/outcome、`target_entity=None`、错误位置、任意 execution opportunity UUID、错 schema、错时序及后验计算失败时零写入。该边界保证 pipeline-managed write（管线管理写入）的契约绑定和 per-append/per-cycle atomicity（单次追加/单周期原子性），不是整个 closed loop（闭环）的单一事务，也不是 robot hardware attestation（机器人硬件证明）、provider authenticity（提供器真实性）或同进程写能力沙箱：当前没有可信 provider/model registry；如果外部 provider 自身持有并直接调用 canonical log，它可以绕过 pipeline，部署时必须只授予返回值接口而不授予日志写 capability（能力）。active verification（主动验证）阶段的 `observation_opportunity_id` 仍只是 observation 内记录，尚未绑定完整 opportunity envelope（机会信封）；outcome model version/domain（结果模型版本/域）目前只在未持久化的执行包中校验，canonical log 单独不能重建该瞬时绑定。

CHEH 的准确定位保持为 `method-specified, contract-tested heuristic vertical slice（方法已规格化、契约测试的启发式纵切）`。本轮执行了上下文、完整端点身份、时间及 record/cluster/semantic 去重约束；没有 trusted provenance registry/signature（可信来源注册表/签名），自洽但伪造的 source/model/endpoint 声明仍无法由 CHEH 单独识别，因此不升级为通用 `provenance-constrained revision（来源约束修订）`，也不是严格因果反事实推断。

## 5. 提交边界

本轮只修改评价底座和 A0 回放阻断相关实现、测试、基准资产与状态文档；没有实现多人物、访客污染、交接或变化检测扩展。共享 Git 根目录位于项目父目录，且当前工作树包含用户的其他修改与未跟踪文件；本轮没有自动 stage（暂存）、commit（提交）或删除任何文件，提交前必须按文件清单显式核对范围。
