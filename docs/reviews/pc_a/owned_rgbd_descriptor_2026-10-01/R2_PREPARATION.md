# 当前 owner RGB-D 描述：R2 只读准备

状态：**仅准备，未正式审查，未运行测试/真实模型/相机，未写生产源码。** 正式 R2 必须等待新源码冻结、同 SHA R1 完成且停止写入后由根任务明确启动。本文件不是审核通过报告。

准备工作树 `/private/tmp/cpswm-pc-a-owned-rgbd-descriptor-20261001`；初始 HEAD `382d59c6e27f14f6c391cfac9fcac0dbcd29768b`，功能 base `82c7a81fba0c3af3688978ce222b1b94e4cc5bd9`。2026-09-30 UTC 本轮准备时 `git fetch origin --prune` 成功，集成引用 `19ddf26830348a2f0b33f0af54d6ba702c5cfb1c`。作者正在新文件中实现，本文不绑定未完成源码为可接受版本。父 BO 及旧 SO 封存不写入。

已读 PLAN、NEXT_DELIVERY_FEASIBILITY、现有 Native origin 签发/恢复、完整 previous-weight evidence、原 RGB-D fixture 和 Native log-underflow fixture。这里验证的是**当前 owner 的原件描述**，不是 target update、历史执行 authority 或物理真实性证明。完整科研范围保持；结果只可标 A 辅助/partial coverage，非电脑 B 验收。

## 必须保留的工程边界

根任务已明确更正“零推理”表述：保留已有完整 Native 验证；允许它在 cold cache 时进行确定性 proposal 重算，不能为了零计数削弱原 owner 检查，也不能预热后隐藏首次成本。新 helper 不应为本次新 capture 新增视觉 decoder/detector/position readout、producer publication、相机执行或持久写入。既有历史 raw 验证可能重建旧观测数学，须与本次新 capture 的消费分开记录。

源码链 `_native_joint_decision_view → _verify_native_raw_sources / prepared_particle_location_marginal → validate_neural_input_body → verify_raw_base / verify_neural_evidence` 解释了为何 helper 不显式调用神经 producer，仍不能推出零推理。测试将分别测量 descriptor cold/warm 窗口与 fresh-resume 窗口；不得把恢复之前的建模/执行/持久化计入纯描述，也不得把真实恢复成本藏起来。

## 三组优先完整检查

### 1. 真实签发来源与完整父支持

建立最小合法 protected neural owner，通过真实 `prepare_posterior_observation → execute_observation → _accept_observation` 收到 RGB/depth/pose；相机恰好一次后，仅用 action UUID 调新 helper。独立沿 owner 原目录核对 command/delivery、base Native origin、runtime/snapshot/cluster、accepted body、source posterior ID/body 与 `current_posterior_projection_source`、batch 和 previous-weight evidence 全部一致。

- 首次 camera feedback 可能改变 `current_joint_decision_view`；描述仍绑定签发时严格相同的 base Native view，不能错取 feedback 后 view。测试同时记录这两个 view 的差异，不把合法反馈误判为 stale。
- 在完整合法有限 log 模型压力下保留显示概率为零但 accepted 的粒子；从 accepted receipts 和 aggregate 原 log 项独立核对支持与归一 log，不从 `view.atoms` 或 `log(display_probability)` 反推。至少覆盖 known-display-zero + 两个其余有限分量；若另一压力配置的合法策略选择 STOP，应记录 STOP/零相机，不能强行制造 READY 来取得描述。
- 完整描述中的 parent/source/receipt pin 即使被重新自签，也必须由同一 owner action-only fresh rebuild 检出。优先让数值改动保持展示概率不变，防止只比可见概率漏掉 finite-log 支持。
- 完成一次正常 neutral advance 或 replay，使数值视图可保持相同而 runtime/source/snapshot/cluster 改变；旧 action 应 stale 拒绝。新的不同 batch、反馈派生 prior 的后续 command 和 legacy/unmodeled 路径按明确范围拒绝，不猜历史来源。

### 2. 完整描述替换及原 transport 重建

先保存一份完整合法 frozen descriptor，再逐例复制全部字段、保持严格类型与可解析结构，修改 candidate-independent 的描述事实并同步更新自身摘要：source/parent/log-evidence、scope、command/delivery、capture/arrival/received 时序、depth unit、camera pose、RGB/depth payload 及 observation ID 对应。每次要求 action-only 重新取 owner 原件后拒绝，随后原 descriptor 合法通过。

进一步建立两份各自完整合法且不同 action 的 RGB-D delivery，用一整套来自另一 action 的字段作移植；不只测试缺字段或坏 hash 字符串。错误 descriptor 与单侧 owner `status`/`raw` 目录替换分开记录，后者保留其余真实 owner 原件不变。capture receipt/hash 合法重签仍不能使跨 capture RGB/depth/pose 混合通过。普通 admit、archive raw、READY/OUTCOME_UNCERTAIN/FAILED、non-modeled command 单列，避免与“成功 owner modeled capture”的拒绝混为一谈。

明确反例边界：同时改写整个可信 owner 目录不是本 helper 能认证的历史物理执行证明。不得将 descriptor 的 canonical hash 当消费授权，不注册新 raw source/NativeVisualAuthority，不增加任何消费 journal。

### 3. 无新增行为与真正恢复正路径

在合法 capture 完成后记录原始目录、command/status/origin、core/workspace/ledger、producer 状态、当前 batch/logs、SQLite checkpoint generation/document/digest、effects 行和文件哈希。对合法描述、完整错误描述、合法恢复三类调用均检查前后完全一致，executor.calls 保持 1。

用无函数替换的 profiler / Torch observer 记录实际执行计数，优先 `sys.setprofile` 采函数名/计数，不长期保存 frame/traceback 引用。禁止使用替换 verifier/decoder 函数的 sentinel 来“证明未调用”，因为 loaded-code binding 可能先被测试自身破坏。SQL 使用连接 trace callback 观察描述窗口，记录任何 INSERT/UPDATE/DELETE/DDL/commit；同时核对内容和 generation。既有 Native 验证的 deterministic q/旧 raw 条件数学另计，新增 capture 不得成为 proposal/position 消费输入。

真正 fresh 子进程仅从保存的 SQLite 和相同冻结配置/模型绑定执行 `ContinuousEvidenceInput.resume`，不先创建另一个 owner 代替原源；恢复阶段单独计数。恢复完成再设 helper 基线，重复描述及完整错误描述恢复后逐字段等于原描述，DB 不写、相机不重发。成功描述不应改变下一步合法状态机行为；本轮也不要求实现尚未存在的新 raw posterior update。

## 执行编排与报告限制

冻结后先验证 R1 报告/manifest/源码 map；基于 R1 已封存合法 owner fixture 的副本做外部检查，必要时单独构造一个最小 owner。避免重复所有父 bridge/bare arms。每阶段外层 180–300 s；fresh child 单独 timeout，保留失败日志与原 harness，再以新 attempt 修复。先判断 harness 与产品，不把 STOP、源绑定误触发、准备期错误或 timeout 当产品缺陷。

正式交付应列实际 test 数和独立 fresh 进程数；分别写 early input/type/pin 拒绝、实际 owner source/parent 检查、深层 raw/math 重建和合法输出后果。至少有一个完整正路径与恢复路径后才可给有界 PASS。源码变动使同轮审查失效；由根任务统一更新 gate。当前仍没有新 R2 通过结果。
