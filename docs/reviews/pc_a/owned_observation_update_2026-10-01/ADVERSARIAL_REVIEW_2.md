# 第二轮：完整伪造、历史消费与兼容性

第一轮完成后才开始；绑定同一功能源码 `d84d570d0c12ec56d5f47f699f7211ffd99422b9`，实现者 A 自审，非独立 B。44 passed，215.92s，0 failed/skip。与第一轮有重复测试，不把 32+44 当成 76 个独立条件或样本。

```sh
PYTHONHASHSEED=193 .venv/bin/python -m pytest tests/test_native_position_production.py tests/test_native_raw_candidate_verification.py tests/test_owned_position_delivery.py tests/test_owned_position_update.py::test_complete_target_forgery_rolls_back_then_legal_retry tests/test_owned_position_update.py::test_fresh_process_recovers_and_retries_without_new_sensor_or_semantic_work tests/test_owned_position_update.py::test_replay_retains_each_update_or_removes_its_semantic_dependency --junitxml=/private/tmp/cpswm-owned-observation-evidence-20261001/review2.xml
```

重点复查：

- 新事务仍拒绝保留真实 q 与合法外形的四种伪造目标，并能在拒绝后正常消费原交付。
- 原 ControlledPositionProducer 通过相同接口重构后，已知/未知/未决质量、条件状态、撤回重放和无因子参照未回归。
- 原 profile 不能通过 downgrade、替换 catalogue、缺失证明、改 verifier 等绕过消费核验；旧原件描述的零显示概率/fresh SQLite 路径通过。
- 新事务在独立解释器 delivered / consumed / replayed 三个阶段恢复，首个动作就是恢复原 DB，不构造替代 stream，不重跑语义 producer，不重复相机。
- 同语义 S 的 A 必须保留为独立更新；撤回 S 删除其 A，撤回其他源保留 A 并根据新实际父状态重新计算。

检查范围仍不是全仓验收、独立 B 审核或自然行为收益评估。单测量 profile 拒绝第二次观测；全空历史、跨版本迁移和自然身份没有本轮通过证据。实时 Unity 检查另列于主报告，不混入本轮受控测试计数。
