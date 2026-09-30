# 当前 owner delivery 只读描述：可行性确认

2026-10-01；只读检查冻结 `82c7a81fba0c3af3688978ce222b1b94e4cc5bd9`，不实施、不运行新实验、不修改既有设计。作者参与当前 bridge 实现，本文件不计 R1/R2。

**可以不改变 core/stream 持久化格式，但只限当前 Native base 与签发 origin 完全相同的首个 modeled capture。**可以输出当前拥有者目录中该 capture 的完整可重算描述；不能输出一般历史签发证明，不能把这个值本身当作下轮 Native 消费 authority。

`prepare_observation` 已在真实签发时保存 `_observation_commands[action]=(command,digest)`、READY 状态，并对带配置 decoder 的 `joint-ciav@1:` command 保存 `_observation_native_origins[action]=_native_joint_decision_view().content_sha256`。执行后 `_accept_observation` 保存实际 delivery 和原 raw。以上字段已经通过 `_persist/resume` 保存，无需新增数据库表或 stream 字段。

## 严格可恢复范围

1. 用现 owner 的 `_native_joint_decision_view()` 验证当前 batch/source/proof/ledger/原件锚；严格要求保存的 native origin 等于该 **base Native view** hash，而不是相机反馈重加权后的 `current_joint_decision_view()`。
2. 为避免恢复任意历史相机反馈链，首版还要求原 `JointCameraProblem.source_belief_sha256` 等于这个 base hash，且原 command/model sources/select 结果完全一致。若 command 当时基于先前 camera feedback 的派生 view，明确不支持，不猜当时 prior。
3. Native view 含 runtime/snapshot/evidence_cluster_id，因此可以沿当前 cluster 找到已接受的 `workspace.input_bodies[cluster]`；用 `workspace.previous_weight_evidence(workspace.batch)` 取得完整 receipts+aggregate。不能只取 view.atoms：它省略显示概率为零的分支。此处的“parent”是未来 raw update 将使用的当前完整 batch，不是任意更早祖先。
4. 从该已接受 input body 的原 `neural_evidence.base_candidates.source_posterior_id/body_sha256` 查原 `posterior_sources`，并要求它等于 `core.current_posterior_projection_source()`。首版可明确只支持现 canonical neural raw profile；没有该证据的 legacy body 不猜 source。当前 source publication 改变、generation/replay 改变、current Native batch 改变，均 stale 拒绝。

因此在这个严格匹配子集内，不需要新增签发 source/parent 字段；它们可经签发 origin 的 cluster 和当前仍相同的受保护 input body 重建。若希望 Native 已继续更新后还接受旧 command，或接受其他历史/legacy producer，则现 origin 不足以支持完整历史映射，应回到完整下一轮在签发时登记独立 source/parent/update 锚。

## 两文件边界与接口

- 新 `src/cpswm/system/owned_position_delivery.py`：严格 frozen dataclass（例如 `CurrentOwnedRGBDDescriptor`）和只读 `describe_current_owned_rgbd(stream, action_id)`。除可信 owner 参数外只收 action ID；不得接收 raw/XYZ/parent/cutoff/“verified”字典。取得 stream/core 两把锁；无 `_persist`、无相机调用、无模型推理、无 Native stage。
- 新 `tests/test_owned_position_delivery.py`：真实 owner 签发/执行/接受目录的合法路径，以及完整派生结果替换、stale、来源冒充、fresh resume 和无副作用检查。

descriptor 最少记录：exact action UUID、完整 command/delivery pins、scope、decision/received 与原 capture/arrival 时间、原 RGB/depth/pose IDs/receipt/payload hashes/单位/相机自位姿、原 native origin、当前 runtime/snapshot/source ID/body、完整 input-body/batch/previous-weight-evidence pins，以及当前 helper/decoder 实现绑定。它只描述原件，不生成候选、实例身份或位置 likelihood。

复用 `unity_rgbd.decode_unity_rgbd` 校验同一 capture 的原 RGB-D/pose 配对、receipt、单位与内参；沿 `owned_visual_support.reconstruct_visual_support` 的原件检查核对 owner 的 raw 对象、scope、`metadata.source_id == action_id`、完整时间序列。不要直接调用整个 visual support 重建器，因为它会运行 detector 的 `measurements`，超出此步只读传输描述。

可提供 `require_current_owned_descriptor(stream, value)`：从 value 的严格 UUID 重新走 action-only 重建，再用 type-exact canonical 内容比较全部字段。这不把 value 变成 authority；只检验它是否仍准确描述原 owner 目录。

## 明确的安全边界

archive 或普通 `admit` 只有 raw，缺真实 command/status/native-origin 目录，拒绝。伪造整个 descriptor 并重签自身 hash，或只替换原 delivery/command/raw 的一侧，必须被 fresh 重建拒绝。若用户要求**同时替换整个 owner 的 command、status、origin、raw 目录后仍证明历史曾真实执行**，现接口做不到，不能以自签摘要冒充独立锚；应在下一完整事务轮添加接受时锚。既有 `owned_visual_support` 已明确同样边界：hash 约束拥有者原输入，不认证一个整体伪造的 owner/物理运行。

新 helper 也不宣称持久化不可篡改证明；SQLite 仍是既有可信本地恢复边界。若仅做此两文件前置，不能把结果送入深层 consumer 当作新的 protected observation authority，也不写新消费 journal。

## 有验收价值的最小测试

1. 复用 `test_native_position_production.scenario/advance` 的 protected neural owner，配上显式 decoder；复用 `test_owned_rgbd_support.RGBDCamera` 的真实 `prepare_posterior_observation → execute_observation → _accept_observation` 结构。capture 晚于旧 semantic；描述匹配实际原件/完整 accepted body，camera 恰好一次；core、producer、ledger、DB 行及文件无改动。
2. 保留实际原 owner，完整替换 descriptor 的 raw/scope/parent/source/时间/零概率分支来源字段，重算所有自签 pins 后拒绝；恢复原 descriptor 再通过。用真实 received 原件测试，不只是缺字段。
3. archive/direct-admit 伪装、普通 non-modeled command、READY/UNCERTAIN/FAILED、重复/缺失 RGB-D 成员、错单位/错 pose/action、不同 capture 的拼接、未来时间，均明确拒绝或返回严格不可用类型，不能伪造成功描述。
4. 语义 advance 或 Native replay 发生后旧 action stale 拒绝；另一次 Native batch 已发布时拒绝；原先 camera feedback 派生 prior 的 command 在首版不支持。不能修改 UUID 以重新满足。
5. fresh 子进程从原 SQLite resume（不先构造另一个 owner），相同配置重建描述逐字段一致；重复描述不执行相机、不写 DB。全量概率为零显示的 finite-log 支持仍由完整 input-body pin 保留。

可继续做这个两文件前置，但前提是交付承认上述边界。若目标是未来任何时间都能消费 A 的完整签发历史 authority，则本切片不足，应留到下一完整 owner-update 轮；不要扩大其声明。
