# 复现入口

功能源码 `a981541fc15bd1e441051f9479dc96b17cdc2f44`，base `e80ddab4f4f792a372c1410862b071f79aebdb64`。文档/证据提交不改变这个受测功能版本。A 使用本机已锁定模型依赖与 AI2-THOR SDK，未重建独立环境；B 仍需独立复核。

完整命令、退出码、源码 SHA 和前后源文件摘要分别保存在 `evidence/attempt01/` 与 `evidence/attempt02/` 的 `commands.json`、`source.json`。第一批的 `round1.xml` 与 `round2.xml` 对应两轮顺序自审；首批 23/24 格完成、1 格受人工窗口调整影响失败。第二批从头完整采集，`review-reuse.json` 证明与受审源文件逐字一致，不重复制造测试计数。公共观察数为第二批 384，首批、夹具和对抗测试的重复推理不加入该分母。完整原件保存在 A 主仓 `output/sim-timing-control-20260929/` 的两个 attempt 目录；Git 交付完整矩阵与汇总、日志和逐文件摘要，部分完整原始序列的范围以交付报告为准。

先在对应源码工作目录按锁文件重建模型环境，准备相同的 torchvision 官方权重、AI2-THOR SDK 与模拟器构建。路径变量须由执行者指向实际文件，不能直接使用另一台电脑的虚拟环境或绝对路径。

```sh
export PYTHONPATH=src:tests:tools
export PYTHONHASHSEED=0 OMP_NUM_THREADS=2 MKL_NUM_THREADS=2
.venv/bin/python tools/run_simulator_timing.py \
  --mode verify --output "$CPSWM_TIMING_CAPTURE_DIR" \
  --sdk-python "$CPSWM_SDK_PYTHON" --binary "$CPSWM_UNITY_BINARY" \
  --ssdlite-weights "$CPSWM_SSD_WEIGHTS" \
  --fasterrcnn-weights "$CPSWM_FRCNN_WEIGHTS"
```

`verify` 必须取得完整矩阵的原件并通过清单核对，然后从拥有者公共 RGB 实际执行两模型，逐项核对所有 SDK 调用及私有评价；不能用单条共享序列替代完整矩阵。`run` 则要求不存在的新输出目录，实际启动 24 个仿真进程。`fixture` 固定采集 south/320 的三种模式各一条，专供合法与伪造路径检查，非性能评测集。

复核单条完整序列，可在同一环境使用 `analyze(directory, cell, weights=..., verify=True)`，其中 cell 必须是 `plan()` 中与目录相符的条件。该入口也执行实际模型推理，不只比较已有摘要。生产前端只接收公共记录；完整 SDK 元数据和目标掩膜在得到预测后才用于核验。

同源运行封装器与后处理脚本以 `.py.txt` 保存，避免新增执行文件改变被冻结源码映射。SDK/Unity 运行前后身份记录在 `runtime-before.json`、`runtime-after.json`；它们支持本轮本机来源核验，不是外部不可变见证。平台、线程、依赖或引擎构建变化导致的不一致应单独报告，不得为对齐旧结果而事后改阈值或挑图。
