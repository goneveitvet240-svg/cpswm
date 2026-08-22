# 结构一 B1 纵切：M05/M06、M28 与进度账本

日期：2026-08-22
状态：**implemented_contract_vertical_slice**（契约纵切已实现；**不是正式 B1 已完成**）

本文记录本次在结构一下推进的三个交付，以及它们的准确成熟度、已知限制和
允许/禁止声明。本文不替项目负责人决定任何技术路线（技术框架 §14 ADR 仍全部开放）。

---

## 0. 总览

| 交付 | 模块 | 成熟度（账本） | 门状态 |
|---|---|---|---|
| M05 统一观测入口 | M05 | `synthetic_vertical_slice` | — |
| M06 标定与时间同步契约 | M06 | `synthetic_vertical_slice` | — |
| M28 隐私与治理纵切 | M28 | `synthetic_vertical_slice` | — |
| 进度账本 + 验证器 | M01–M32/WS1–WS10 | 机器可读数据 | 见 §4 |

B1 门已拆为两个：`B1_SYNTHETIC_READINESS`（M05–M12 全部 `synthetic_vertical_slice`，
当前 **BLOCK**，M07–M12 仍为 `absent`）与 `FORMAL_B1_REAL_VALIDATION`
（M05–M12 全部 `real_data_validated`，当前 **BLOCK**）。全局结构一完成门
`STRUCTURE_ONE_COMPLETE`（M01–M32 全部 `replay_validated`，且 WS1–WS10 覆盖）
当前 **BLOCK**。

---

## 1. M05 统一观测入口（`src/cpswm/perception_mapping/adapters/`）

`ObservationEnvelope` 绑定：

- 身份：`household_id / session_id / trace_id / observation_id`（`ObservationIdentity`）；
- 传感器：`sensor_id + modality`（`SensorRef`，`SensorModality`）；
- 时间：`capture_time / arrival_time / clock_domain`（三者均要求 aware）；
- 帧：`frame_id`；
- 载荷：普通 `payload` 与 oracle `oracle_payload` **分离**，两者互斥；
- 来源：复用 M01 `BaseRecordMetadata.source_type`；
- oracle 标记：`oracle_channel + oracle_authorization`（后者是 M28 的
  `OracleAccessDecision` decision receipt，`purpose` 固定 `evaluation_only`）。

适配器边界拒绝（`adapters/validation.py`）：

1. GT 字段进入普通感知通道（`ground_truth_refs` 且非 oracle）；
2. 跨 household/session/frame 混用；
3. naive datetime；
4. payload hash 或**实际字节大小**不一致；
5. 过期标定（`calibration_valid=False`）；
6. source type 与 oracle 标记矛盾（物理 SENSOR 不能是 oracle）；
7. oracle 通道携带被拒绝或非 evaluation_only 的 decision receipt。

合成适配器 `SyntheticSimulatorAdapter` 只读取 `simobs.*`，**从不 import
`cpswm_gt`**（有测试用正则断言源码无 `import cpswm_gt`）。

## 2. M06 标定与时间同步（`src/cpswm/perception_mapping/calibration_sync/`）

`SensorCalibration` 绑定：

- `intrinsics / extrinsics`（extrinsics 复用 M02 `FrameTransform`）；
- `calibration_version`；
- `valid_time`（半开区间）；
- `frame_id`（source frame，extrinsics.source_frame 必须等于它）；
- `CalibrationUncertainty`（intrinsics/extrinsics covariance）；
- `artifact_sha256`（标定产物哈希，可由 `compute_artifact_hash()` 从规范化
  参数重算，或由 `verify_artifact(bytes)` 验证外部产物字节）。

`CalibrationRegistry.calibrate(...)` 是真正的标定流程：绑定
sensor/frame/time/household，自动计算产物哈希（或接受外部 artifact bytes），
注册标定并可选记录时间同步。

`SensorTimeSyncResult` 保留 `source_time`（原始时间）与 `target_time`
（对齐时间）、`offset_seconds`、`uncertainty_seconds`；校验
`target_time == source_time + offset`。原始时间从不被覆盖。

`CalibrationRegistry` 按 household + sensor + valid-time 查询有效标定，
跨 household 查询返回无效（测试覆盖）。

## 3. M28 隐私与治理（`src/cpswm/system/privacy_governance/`）

版本化记录（均携带 M01 `BaseRecordMetadata`，经 M03
`AppendOnlyTransactionLog` 持久化）：

- `CapabilityGrant`（subject/household/resource/operation/purpose/valid_time/issuer）；
- `CapabilityRevocation`（撤销后旧 grant 不再授权）；
- `OracleAccessRequest`（强制 `evaluation_only`，记录 caller/purpose/watermark）；
- `OracleAccessDecision`（拒绝必须给 denial_reason）；
- `OracleAccessAuditRecord`（caller/purpose/watermark/output_summary）；
- `DataRetentionPolicy`；
- `UserDeletionRequest`；
- `DeletionExecutionReceipt`。

关键规则：

- `authorize` 检查 grant 有效、未撤销、未过期、household 匹配、purpose 匹配；
- `decide_oracle_access` **不接受调用方传入 `allowed`**：决策从有效 grant 自动
  推导，并在 decision 里强制绑定 request_hash、grant、caller、household、
  purpose（`evaluation_only`）、resource、operation、decision time 和 watermark；
- 普通模块 subject（`perception_mapping.` / `world_model.` / `language_query.` / `action.` 前缀）
  **不能**获得 `gt.*` grant（`FORBIDDEN_GT_SUBJECT_PREFIXES`）；
- 删除必须严格满足 `PRIVACY + DELETE + purpose=user_deletion`，并检查 subject
  与有效期；
- 删除采用 tombstone/redaction projection，不改写 append-only 历史，
  `redacted_projection` 返回过滤后的派生投影，审计证明保留；
- household A 的 grant 不能授权 household B（测试覆盖）；
- `restore()` 从 append-only log 重建状态，并对每个恢复的 grant **重新执行
  grant policy 验证**（违反 GT-subject 或 household 约束的日志记录被拒绝）。

## 4. 进度账本与验证器（`src/cpswm/system/progress_ledger/`）

- 数据：`progress_ledger.json`（M01–M32，每模块记录 module_id / workstream_ids /
  maturity / implementation_paths / test_paths / evidence_artifacts / blockers /
  allowed_claims / forbidden_claims）。
- 证据：`EvidenceArtifact` 除路径外还可携带 `content_sha256`（内容哈希，验证器
  逐字节核验）、`artifact_schema` 和 `run_receipt`，不能只检查路径。
- 成熟度序列：`absent → contract_only → synthetic_vertical_slice →
  integrated_synthetic → replay_validated → real_data_validated → embodied_validated`。
- `contract_only` 要求存在合同实现文件**及**专项测试；无实现的模块只能标 `absent`。
- CLI：`apps/progress_ledger/validate_progress.py` 校验引用文件与证据哈希、检测
  矛盾声明、输出覆盖矩阵、输出 BLOCK 原因；**任何 required gate BLOCK 或内部
  不一致都返回非零退出码**；`internally_consistent` 与 `required_gates_passed`
  是两个独立布尔。

验证器**只做校验、从不升级**成熟度，也**不替用户决定研究路线**。篡改检测：

- 删除未完成模块 → 报 missing module；
- 把 B1 门改写为 ATG-1 → 报 "must require exactly M05-M12"；
- 用 synthetic evidence 冒充 real validation → 报缺 real-data evidence；
- 缺失引用文件 → 报 path missing；
- 声明超出成熟度 → 报 claim exceeds maturity；
- 篡改 evidence 内容哈希 → 报 content hash mismatch；
- 全结构门缺 M01–M32 任一项 → 报 "must cover exactly M01-M32"。

## 5. 已知限制

- M05/M06 是**契约 + 合成适配器**纵切，不含真实 SLAM、目标检测、真实机器人
  驱动、真实标定估计或真实时钟同步。
- M28 是治理纵切，**不是生产级安全系统，也不是完整 GDPR 合规**；能力模型是
  防止误用的 API 边界，不是对抗同进程恶意代码的沙箱。
- 进度账本的 `synthetic_vertical_slice` 模块引用的测试文件均已存在；账本只
  记录仓库事实，不构成任何门通过声明。
- 未触碰 `_to_delete/`、SHIFT 测试数据与未跟踪文件。

## 6. 允许 / 禁止声明

允许：

- "M05/M06 契约与合成适配器纵切已实现并测试通过"；
- "M28 能力授权、oracle 审计、删除墓碑纵切已实现并测试通过"；
- "进度账本如实反映 B1 与结构一完成门为 BLOCK"。

禁止：

- 禁止声明正式 B1 已完成；
- 禁止声明 M07–M12 已达到 `synthetic_vertical_slice` 及以上；
- 禁止把 synthetic 结果表述为 real/embodied 验证；
- 禁止把任何门从 BLOCK 改为 PASS/accepted；
- 禁止声明 M28 为生产安全系统或 GDPR 合规。
