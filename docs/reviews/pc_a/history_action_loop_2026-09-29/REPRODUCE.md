# 同历史任务对照复现

功能源码冻结 `c59b8c88d9d3cb1d03f9042909a58fd7378f7e03`；base `bf374f9331426cfa384f2ec23bf0bd0a098ba033`。本机复用已有视觉/神经环境，不是独立环境验收。完整正式框架和 B 比较协议不变。

从冻结源码运行，使用锁定依赖并明确设置 `PYTHONPATH=src:tests:tools PYTHONHASHSEED=0 OMP_NUM_THREADS=2 MKL_NUM_THREADS=2`。`CPSWM_SSDLITE_WEIGHTS` 指向官方 SSDLite 文件，不能将未提供权重产生的跳过算通过。

顺序局部自审命令（运行结果另见 REVIEWS.md）：

```sh
python -m pytest -o addopts= -q tests/test_clarification_camera_model.py tests/test_revised_camera_collection.py tests/test_history_camera_worker.py tests/test_continuous_camera_collection.py
python -m pytest -o addopts= -q tests/test_revised_camera_attacks.py tests/test_history_reconstruction.py tests/test_native_neural_recovery.py tests/test_joint_camera_feedback_recovery.py
python -m mypy --no-incremental src/cpswm/system/revised_camera_collection.py src/cpswm/world_model/grounded_search/active_verification.py
```

通过后用四个独立的新输出目录，分别给 `--task classification|clarification` 与 `--site north|south`。此处带竖线参数表示取一个值，不能原样运行：

```sh
python -u tools/run_history_action_loop.py --mode run --task clarification --site north --output NEW_OUTPUT --sdk-python SDK_PYTHON --binary UNITY_BINARY --weights SSDLITE_WEIGHTS --checkpoint docs/reviews/pc_a/neural_native_loop_2026-09-29/evidence/development-checkpoints/typed_factor_graph_transformer/checkpoint
```

每次创建一条持续 Unity 历史：固定暂停物理及两次 Pass 后，策略自主决定是否观察；在同一状态库接收已绑定的受控纠正，关闭并重开状态库，同时保持 Unity 进程连续，再由重新计算的联合后验决定后续动作。所有停止、失败和不确定结果保留；不以固定扫描补齐。

归档复算：保持上述参数，将 `--mode run` 改为 `--mode verify`，指向已存在的输出目录。它使用真实检查点重放纠正前保存的 SQLite、重新应用保存的绑定反馈、复算原生联合状态，再核验实际派发/SDK/RGB及真实视觉推理。它不启动新的 Unity，也不等同于独立物理重跑。固定的任务、数据来源与当前源码映射必须匹配。

完整原件暂在 `output/history-action-loop-20260929/`；交付报告会注明 Git 共享范围及对应库存。不要用历史文档的通过结论替代当前功能 SHA 的检查。

归档重建分开验证两种身份：重新执行撤回可分配新的内部快照和账本UUID，因此先用既有语义校验器比对原始账本、外部证据/授权、原生工作区和实际返回后果；再从已接受的 `after-feedback.sqlite` 恢复，神经重放结果仍必须与在线原生状态完全相同。不能通过删掉外部ID或只比较概率来绕过检查。

Git交付的完整实验原件位于 `evidence/history-action-loop.tar.gz`，外层 `archive.json` 固定压缩包摘要，`inventory.json` 列出逐文件字节数和SHA256。在独立空目录解包后，可针对 `attempt02/{task}-{site}` 重建四条历史。`attempt01` 是原复核器错误导致失败的首条历史，不能当成通过数据。检查点仍使用本分支继承的原 `development-checkpoints`，不重训、不自动选择其他权重。压缩包本身不包含Python虚拟环境或Unity安装。
