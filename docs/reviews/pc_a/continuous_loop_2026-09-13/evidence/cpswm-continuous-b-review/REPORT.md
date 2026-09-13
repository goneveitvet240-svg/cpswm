# B4/B5 三生产文件接收审核

审核目标：只读复核 B 交付 `fd4ca6ef5e81c90d7cf7987b42c0b2810d8a810a`（生产修改提交 `0581ca8`），与 `c366cad` 对照。不是用户要求的最终连续闭环两轮审核，也不是跨机器/全项目/科学收益验收。

## 接收结论

可接收以下四组有限修复，建议以三文件差异 patch 集成，不整文件替换：

1. `NativeParticleWorkspace.advance` 写入前将提交链与来源帧的同 revision 历史精确比较，重验 schema，并保留脱离 caller 别名的对象。合法非空路径、完整重封攻击无副作用、失败后合法重试通过。
2. core-owned `_particle_input_anchors` 区分 workspace 内部自洽与生产边界实际接收过的内容；持久输入整体重封在核心读出与语义身份处拒绝。锚和 workspace 一起 checkpoint/rollback。
3. 延迟纠正撤销记录补拓扑、完整父记录、重复、trigger/rationale 检查，staged restore 与 durable cancellation 都绑定接收摘要；序列化变更前复核，事务撤销同步恢复锚。
4. persisted body/record 复用只发生在一次验证/advance 调用内，未引入跨调用永久“已验证”缓存；后续整体重封仍被拒绝。未独立重新测量长历史性能，本审核不背书性能倍数。

## 与 A 位姿版本的合并要求

B 的 workspace patch 没有改 `ConditionalAnalyticState.__post_init__`。B 完整文件仍将 RLS 与 Gaussian 都绑到 `len(b)`，A 位姿版已拆为 `len(b)` 和 `len(information_vector)`。应用 B diff 可保留 A 修改；不得将 B 全文件复制到 A。A `structure_two_conditional_updates.py` Gaussian H 宽度解耦和 `structure_two_pose.py` 完全保留。集成后仍须执行 A mixed-dimension/pose tests，接收审核对未生成的集成源码不发通过结论。

## 本次实际运行

- 运行解释器：A 工作树 `.venv/bin/python`，CPython 3.13，原生 pytest；`PYTHONPATH` 仅显式 B `src` 与 `tests`，不包含 B `tools`，没有 pytest shim。
- 5 个受影响测试文件：103 passed，10 个既有 Pydantic 非法输入序列化警告，99.76 秒。见 `affected.log` / `affected.xml`。
- 接收方新写独立测试：3 passed，1.99 秒。包括接收锚写入后人为失败的事务回滚及合法重试；多次合法读取后再次整体重封仍拒绝；实际加载的 173 个生产函数/方法 code object 与对 B 文件 fresh compile 结果相等，模块路径全部位于 B src，pytest 来自 A venv site-packages。见 `test_receiver.py` / `receiver.log` / `receiver.xml`。
- 使用新的独立 pycache prefix 且不写字节码，避免既有缓存；测试后 B Git 工作树干净且仍为指定 SHA。
- 独立验证脚本首轮误将 dataclass 自动生成 `<string>` 方法当成源码函数，出现脚本 KeyError；修正为只比较该源码文件定义的方法后 3/3。初始原始日志/XML保留为 `receiver_probe_initial.*`，不将其隐去或称为产品缺陷。

完整命令均为在 B cwd 运行 A Python `-m pytest -o addopts= -q -p no:cacheprovider`。受影响文件：

```
tests/dual_pc_review/test_pc_b_two_round_adversarial_audit.py
tests/dual_pc_review/test_pc_b_b5_extended_state_machine.py
tests/test_structure_two_w3_native_particles.py
tests/dual_pc_review/test_w3_five_boundaries_repair.py
tests/test_structure_two_w3_deferred_cancellation.py
```

## 边界

私有 core-owned 锚仍属于同进程工程接收边界，不是恶意代码无法修改的外部证据保管人。公开 workspace 自洽校验不等于真实传感来源证明。B6/B7 findings、冷导入、Ed25519 checkpoint、W1/W2 全链及真实输入到行动的能力均不在本三文件接收结论内。103 个测试是独立重新执行既有修复回归，3 个是本接收方新写检查，不能改称全部测试由接收方独立设计。
