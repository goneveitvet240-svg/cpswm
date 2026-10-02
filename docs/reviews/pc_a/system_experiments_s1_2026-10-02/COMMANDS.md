# S1 执行与复核

矩阵执行代码：`747ea0187a6a03c4decaa2d3ad05e000a31f1dca`。从该版本建立独立目录和环境，不覆盖现有数据库；生产 src/ 与 PR96 完全相同。实际依赖与954个 Python 源文件 pin 由运行前 `plan.json` 记录。macOS 已有 Unity binary、SDK Python 与两组预训练权重沿用 PR96；本批环境为借用原 venv，不冒称独立重建。

下列变量应改成本机资源的绝对路径。`S1_OUTPUT` 必须不存在；外层不自动重试失败，不在同目录覆盖结果。需要允许 Unity GUI/本地 socket 的环境。

```sh
python tools/run_surface_system_suite.py \
  --output "$S1_OUTPUT" \
  --weights "$S1_SSD_WEIGHTS" \
  --mask-weights "$S1_MASK_WEIGHTS" \
  --sdk-python "$S1_SDK_PYTHON" \
  --binary "$S1_UNITY_BINARY" \
  --house docs/reviews/pc_a/sim_timing_control_2026-09-29/evidence/raw-examples/south-320-frozen-0/evaluator_house.json \
  --model "$S1_FROZEN_MODEL" \
  --targets "$S1_EVALUATOR_TARGETS"
```

外层预先写入 `plan.json`，然后串行执行六组真实配对。每组分别调用：

1. `tools/run_surface_comparison.py`：同一冻结世界、重置相机、实际采集和事务更新；记忆组加 `--memory-only`。
2. `tools/evaluate_surface_episode.py ARM TARGETS ARM/evaluation.json`：结束后隔离评分，读取 SDK 实例掩码与真实 AABB。
3. `tools/run_surface_episode.py restore --output ARM`：新进程、恢复副本、不重复执行 bootstrap，保存 `fresh.json`。
4. `tools/summarize_surface_comparison.py GROUP GROUP/comparison.json`：公共输入、世界状态、动作预算和记忆干预匹配检查。

完整实际命令、返回码和持续时间均在 `summary.json` 的 `commands` 中。持续时间包含本机源绑定/恢复检查开销，不能将减少动作数直接解释为相同比例的墙钟加速。

本批新增驱动检查为 Ruff、format 与 Python 编译；旧54项回归是 PR96 的既有证据，本批没有把旧结果冒称新的全仓测试。运行后另按原始实例掩码/SDK AABB重算评分，核对新进程恢复结果和物理账本计数；这仍是 A 本机产物核验，不是 B 的独立仿真验收。

主结果的原始证据重算（需完整本机原始目录，输出文件必须新建）：

```sh
python docs/reviews/pc_a/system_experiments_s1_2026-10-02/evidence/score_audit.py \
  "$S1_OUTPUT" "$S1_CHECKOUT" "$S1_NEW_AUDIT_JSON"
```

`--all-steps`的15次事后诊断命令及返回码在四份`all-steps-commands-part*.json`中，117个逐帧查询槽不是额外独立任务。
