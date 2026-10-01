# 第二轮：兼容性、完整原件重算和 fresh 恢复

第一轮完成后才开始；相同源码 `63b053fa30a508a0c73dcff44d47a645f5a1362f`，A 自审非独立 B。73 passed，142.63s，无失败/跳过。原完整正路径、攻击和后果检查均保留，不修改历史断言。

```sh
CPSWM_SSDLITE_WEIGHTS=/private/tmp/cpswm-natural-candidate-evidence-20261001/ssdlite.pth PYTHONHASHSEED=223 .venv/bin/python -m pytest tests/test_native_position_production.py tests/test_native_raw_candidate_verification.py tests/test_natural_vision.py tests/test_soft_surface_position.py tests/test_natural_candidate_position.py::test_complete_forged_natural_readout_with_valid_neural_proof_rejected tests/test_natural_candidate_position.py::test_loaded_selection_replacement_rejected_before_update_then_recovers tests/test_natural_candidate_position.py::test_fresh_interpreter_natural_reconstruction --junitxml=/private/tmp/cpswm-natural-candidate-evidence-20261001/review2.xml
```

旧位置因子和 canonical raw 验证覆盖完整 target 伪造、模型/来源/原件攻击、profile 降级、父状态/历史和恢复；自然 RGB 边界覆盖越界、未来信息、错误权重、非有限输出、精度边界、空检测不授权负观察；表面读出覆盖重复网格、多来源、空/无效支持、模型 pin、公开输入和资源边界。

新自然 profile 再次执行完整三维读出伪造、已加载选择函数替换和三个阶段的新解释器恢复，全部通过。攻击保留有效神经证据，拒绝后继续走合法更新，不以破坏外形/缺字段作为拒绝的唯一原因。

重叠执行不作为独立样本；此结果不证明全仓验收、跨机迁移、身份概率校准、多帧统计独立或行为收益。SSDLite 本地路径属于配置绑定，本轮仅验证同机 fresh 解释器；旧 DB 跨机器迁移没有通过结论。实际 Unity 新采集实验单列主报告，不计入本轮受控测试数量。
