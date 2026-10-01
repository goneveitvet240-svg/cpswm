# 第一轮：原子事务、状态机及动作后果

绑定源码 `d84d570d0c12ec56d5f47f699f7211ffd99422b9`。同一实现者 A 自审，不是独立 B。先冻结再执行，无中途改源。32 passed，396.69s，0 failed/skip；见 evidence/review1.log、review1.xml。

命令：

```sh
.venv/bin/python -m pytest tests/test_owned_position_update.py tests/test_native_joint_full_replay.py tests/test_continuous_camera_collection.py tests/test_revised_camera_collection.py --junitxml=/private/tmp/cpswm-owned-observation-evidence-20261001/review1.xml
```

审查目标：

1. 同语义重复观测是否被旧 once-per-source 短路：中性 S 后单独 A 确实新增簇并改变后验，语义账本不变；下一决策绑定更新后视图。
2. 失败是否只回滚表面输出：在 raw admission 和发布后持久化前注入异常，核对实际 workspace、producer、owner、账本及数据库，交付保留，合法重试不重复相机。
3. SQLite 已提交后抛异常是否误判回滚：提交前/后分别注入故障，当前实例封锁，恢复依据真实 DB，均无物理重试。
4. 撤回是否只按 revision 去重吞掉 A：保留 S+A 的重放与删除 S+A 分开覆盖，旧 cutoff 不读取未来帧，真实 fresh interpreter 恢复无替代 P5。
5. 完整伪造是否靠缺少 q 才拒绝：4 类攻击先通过真实 neural evidence 核验，再由原 owner raw 全量重算拒绝；之后合法路径成功。
6. 默认 collector 是否实际调用事务：真实 collector + 受控传感器执行一次，posterior 改变，无新语义转移。
7. 旧 replay / READY / OUTCOME_UNCERTAIN / 源变更和后续真实受控相机动作相关兼容测试通过。

数学参照包含独立 Gaussian 闭式归一化和 Λ/η，与无因子对照比较；不是自然校准验收。相机在本轮测试中为受控实现，不能当作 Unity 实验。仅上述范围通过；多测量与自然身份仍未覆盖。
