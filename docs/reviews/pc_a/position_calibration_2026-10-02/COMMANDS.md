# 复现入口与封存边界

最终功能 `27d396d6db4c248992f37285d3b7ad42b20df408`；本机工作目录 `/private/tmp/cpswm-pc-a-position-calibration-20261002`。`.venv` 借用前序环境，非独立重建；环境与源码文件摘要随 evidence 保存。

定向检查：

```sh
.venv/bin/python -m pytest tests/test_calibrated_position.py tests/test_position_calibration_driver.py -x
CPSWM_SSDLITE_WEIGHTS=/private/tmp/cpswm-natural-candidate-evidence-20261001/ssdlite.pth .venv/bin/python -m pytest tests/test_target_position_report.py tests/test_owned_target_position_report.py tests/test_temporal_target_position.py -x
.venv/bin/mypy src
.venv/bin/ruff check src tests tools/run_position_calibration.py tools/probe_archived_target_surface.py
.venv/bin/ruff format --check src tests tools/run_position_calibration.py tools/probe_archived_target_surface.py
```

输入准备读取父轮完整302文件，不重新生成父轮模型：

```sh
PYTHONPATH=src .venv/bin/python tools/run_position_calibration.py prepare "$PARENT" "$COLLECTION" "$NEW_DATA" \
 --parent-pin 9b9ed2d9208c1907d8295d5edc5aeb2f48af7b9b3625108b9642430a06780efc \
 --collection-pin 9791a946543b9158890324d3ff35a80ea04d51c9cabb6e09540f569abd903d47
```

`PARENT` 包含 `case-results.json` 与 `experiment/`，来自上一轮 `soft-position-factor-20261001-sealed.tar.gz`；`COLLECTION` 是原始 `collection-attempt02`。prepare核对父账本和全部成员、SDK inventory、实际action owner及双参考，不重新选择检测框或seed。训练/验证分区为固定1–8/9–12。

每个产物必须是新文件，评分目录中的 `scored-rows.json` 也不得已有；全部实际参数及每步退出码/文件SHA在 `evidence/execution-ledger.json`。分别启动以下命令，pin取 `evidence/inputs.json` 及已冻结上一步文件的SHA256：

```sh
PYTHONPATH=src .venv/bin/python tools/run_position_calibration.py train "$DATA/training.json" "$OUT/models.json" --pin "$TRAINING_PIN"
PYTHONPATH=src .venv/bin/python tools/run_position_calibration.py predict "$DATA/public.json" "$OUT/models.json" "$OUT/predictions.json" --public-pin "$PUBLIC_PIN" --model-pin "$MODEL_FILE_PIN"
PYTHONPATH=src .venv/bin/python tools/run_position_calibration.py evaluate "$OUT/predictions.json" "$DATA/evaluation.json" "$OUT/report.json" --prediction-pin "$PREDICTION_PIN" --evaluation-pin "$EVALUATION_PIN"
```

运行后另起全新输出目录重复train/predict/evaluate，逐字比较四份JSON。seal中的 `frozen-data/` 是完整准备产物，可用于直接重训；这不替代前述原始输入来源验证。`fresh/` 与 `run/` 相同文件不重复塞入tar，摘要仍保留。

独立算术核验使用本报告目录的 `independent_check.py`，不导入被测实现；要求run/fresh全部结果与外部固定账本pin一致。封存包只包含run时，可先将其逐字复制为fresh，再核对外部账本；这只复核算术及保存证据，不称新进程复现。要验证fresh执行，应实际重跑上面的三个入口。

```sh
.venv/bin/python docs/reviews/pc_a/position_calibration_2026-10-02/independent_check.py "$EVIDENCE_ROOT" "$NEW_CHECK_JSON" --ledger-pin "$EXECUTION_LEDGER_PIN"
```

原WineBottle诊断必须使用原冻结core依赖，不能修改旧库的来源声明：

```sh
PYTHONPATH="$ORIGINAL_CORE/src:$ORIGINAL_CORE/tests:$ORIGINAL_CORE/tools" .venv/bin/python tools/probe_archived_target_surface.py "$PR92_LIVE_ARCHIVE" "$NEW_SURFACE_OUTPUT" --target 'WineBottle|surface|2|8'
```

`ORIGINAL_CORE` 为 `ccccacc8ced5245ee6c38b2466632bac37d37cd0` 对应依赖源码，PR92 live归档带 `copy.db`/`restore.json`/原件，固定SSDLite权重SHA `a79551df90c79834bcd3bb3845ef9d966b5449a3a9b2833ae8404778ca5d65d2`。第二进程更换输出目录；public/result逐字比较。绝对路径、Python版本与旧SQLite绑定的环境限制延续，不保证将Mac数据库直接复制到Windows可恢复。

开发期第一次prepare反复对整份public计算hash，运行缓慢而被中断，无完成产物；优化为每帧一次后成功，原 `prepare-development.log` 保留。26项初版检查也保留；最终增加账本防覆盖后27项，完整实际拟合/预测/评分再次执行，不拿旧数值产物替代最终运行。所有旧负结果均保留。
