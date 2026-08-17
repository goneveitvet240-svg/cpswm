# Step 1 A0：身份、事务日志、编排与确定性回放

- 实现状态：`implemented_vertical_slice`
- 审核门：`BLOCK`
- 验收状态：`not_accepted`
适用范围：M01–M04  
依据：`技术框架_修改后执行步骤_v1.2.md`

## 1. 完成范围

Step 1 在既有 M01 schema v0.1 上实现：

- M02：身份命名空间、UTC 时间语义、跨时钟对齐和时变坐标变换；
- M03：追加式原子事务、全局提交序号、水位、存储隔离、快照和回放清单；
- M04：同进程命令/事件编排、有界重试、幂等、追踪、版本记录和回放比较；
- 联合链：M02 对齐输入，M04 执行处理器，M03 原子提交，再由同一 `ReplayManifest` 重放。

A0 是完整 A 层的第一实现成熟度，不删除数据库、ROS 2、多进程消息、分布式编排或生产部署能力。这些能力通过当前接口增加物理适配器，不改变上层语义。

## 2. M02 语义

### 2.1 身份

`ScopedIdentity` 将 UUID 与下列命名空间绑定：

```text
household / session / entity / observation / event /
transaction / trace / frame / record
```

除 `household` 自身外，所有身份都必须声明所属 `household_id`。注册表拒绝同一 UUID 被赋予不同命名空间或家庭范围。

### 2.2 时间

- M01 的 `valid_time / observed_time / recorded_time` 保持不变；
- 所有边界时间必须携带时区；
- M02 服务将时间点标准化为 UTC；
- `ClockAlignment` 定义 `target_time = source_time + offset_seconds`；
- 多跳对齐累加偏移和保守累加不确定性；
- 同一家庭、同一时钟对的重叠有效区间被拒绝，防止歧义。

### 2.3 坐标

`FrameTransform` 明确定义从 `source_frame_id` 到 `target_frame_id` 的刚体变换。变换携带：

- 家庭范围；
- 有效时间；
- 版本；
- 平移和归一化四元数；
- 可选 6×6 协方差；
- 组合路径中的原始变换 ID。

注册表支持直接、逆向和多跳查询。组合变换 ID 由路径确定性生成。A0 不伪造复合协方差；需要正确传播时由后续数值实现补充。

## 3. M03 事务与存储语义

`AppendOnlyTransactionLog` 提供：

```text
一个事务只属于一个 household 和一个 trace
一次提交包含一个或多个版本化契约记录
所有记录共享 global_commit_seq
提交前完整验证，验证失败时零写入
```

幂等键按家庭隔离：

- 相同键、相同内容：返回原事务和原水位；
- 相同键、不同内容：抛出冲突；
- 已提交的 `record_id` 不允许在另一事务重复出现。

当前提供三个物理隔离分区：

```text
online / training / replay
```

每个分区继续隔离 canonical（规范）与 derived（派生）数据。派生投影清空不会改变规范日志水位。

`ReplayManifest` 固定：输入水位、Schema 版本、代码版本、模型版本、配置哈希、随机种子、执行模式、数值容差和回放逻辑时间。`fingerprint` 只排除存储身份 `replay_manifest_id`；runtime 使用的 `created_at` 必须进入指纹。

严格回放还将清单绑定到指定水位的日志 SHA-256，并在执行前重新计算实际 Git HEAD、源码树 SHA-256 和活动配置哈希。声明版本与实际运行状态不一致时拒绝回放。

## 4. M04 运行语义

- Command（命令）必须有且只有一个处理器；
- Event（事件）允许多个订阅者，并按稳定处理器名称排序；
- 处理器输出在验证后作为一个 M03 事务提交；
- 输出必须保持输入的 `household_id / session_id / trace_id`；
- 重试有最大次数，失败不会留下部分事务；
- 幂等缓存按 `household + handler + idempotency_key` 隔离；
- 回放模式使用清单时间、固定随机种子和确定性 UUID；
- 回放产生的 canonical transaction（规范事务）把 `committed_at` 固定为同一清单时间；完整 output watermark（输出水位，含 `recorded_at`）进入 `ReplayRun` 比较；
- `ReplayManifest` 和 `ReplayRun` 在执行/比较入口递归拒绝 `model_copy` 注入字段并完整重验证；清单容差必须是有限非负数，且 `ReplayRun.manifest_numeric_tolerance` 保存清单声明；`ReplayRun` 强制 output payload（输出载荷）与其 SHA-256 指纹一一对应；默认比较使用清单声明，兼容参数只能收紧、不能放宽该声明；零容差比较同时核对指纹，正数值容差只允许各自哈希有效的载荷在声明范围内变化；
- emitted message identity（发出消息身份）由 runtime 拥有：按父消息完整 fingerprint、handler、attempt 和输出序号生成确定性 ID，并固定 `created_at`；
- runtime 出口从普通字段重建并完整验证每条 emitted `RuntimeMessage`，拒绝 stale payload hash、非法 schema/枚举/序号、额外字段及跨 household/session/trace/causation；
- runtime 入口同样重建并完整验证 incoming `RuntimeMessage`；每条 handler output record 在持久化前按其具体契约完整重验证；
- 处理器产生的新消息只作为输出返回，不在同一调用栈自动递归分发。

最后一条保证未来的 M16↔M18、M17↔M19 和 M11↔M12 反馈循环可以遵守 tick/epoch 时序规约。

## 5. Step 1 验收

联合测试执行：

```text
M02 身份和坐标注册
→ RuntimeMessage
→ M04 handler
→ M02 坐标对齐
→ M03 原子提交
→ 清空运行状态
→ 日志与ReplayManifest序列化落盘
→ 两个独立Python进程分别加载和重放
→ 输出逐字段完全一致
```

上述独立进程链当前验证记录输出；使用的 `AlignmentHandler` 不产生 emitted message。emitted-message 的身份、顺序和完整契约边界由两个 fresh in-process runtime（全新同进程运行时）的反例覆盖，本页不把它表述为跨进程 emitted-message 复验。

测试命令：

```bash
.venv/bin/python -m pytest -q
```

Step 1 不声明 M13–M19 领域存储、信念推理、查询、仿真或机器人能力已经完成。2026-08-13 复审发现 emitted message 身份确定性、`session_id` 继承和完整契约绕过阻断项；修复及本地反例测试通过只表示已具备再次复审条件，不自动升级为 `accepted`。
