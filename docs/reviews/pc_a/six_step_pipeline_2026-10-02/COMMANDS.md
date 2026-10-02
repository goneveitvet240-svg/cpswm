# 执行与复核

生产实现冻结 `745613ef0b804b5da4d1d2afcbba56fd9f78925c`。其后新增/修正的是驱动、评分和文档，完整源文件SHA见证据清单。不要用main或旧集成SHA冒称此版本。环境为借用已有Python3.13.5 venv，非独立重建；实际依赖见 evidence/environment.json。

```sh
export PYTHONPATH=src:tests:tools
export CPSWM_SSDLITE_WEIGHTS=/absolute/path/ssdlite.pth
export CPSWM_MASK_WEIGHTS=/absolute/path/maskrcnn.pth
python -m pytest tests/test_surface_episode.py tests/test_surface_action_model.py tests/test_owned_position_update.py tests/test_owned_position_delivery.py tests/test_target_position_report.py
python -m mypy src/cpswm
python -m ruff check src/cpswm tests/test_surface_episode.py tests/test_surface_action_model.py tools/*surface*.py
```

两权重pin分别为 `a79551df90c79834bcd3bb3845ef9d966b5449a3a9b2833ae8404778ca5d65d2`、`73cbd0190fcbe3ba339921fbce2c3a0b6bb9126c9a133c85e43a2a8e060a109e`。权重不在归档内。

1. `tools/capture_surface_development.py --output NEW --mask-weights MASK --sdk-python SDK --binary UNITY --house HOUSE --degrees 30 1 1 1 1 1 1 1 1 1 1 --target bottle:0 bottle:1 bowl:0`；另一开发轨迹degrees为30 5 5 5 5。公开输入和evaluator_only目录分离。
2. `tools/evaluate_surface_episode.py RUN TARGETS OUTPUT --all-steps`，用既定targets.json离线评分；`tools/fit_surface_action_model.py --pair RUN1 SCORE1 --pair RUN2 SCORE2 --output NEW_MODEL`，生成冻结84条频率模型。已有模型及源pin在证据中，不能用最终比较标签重拟合。
3. `tools/run_surface_comparison.py --output NEW --weights SSD --mask-weights MASK --sdk-python SDK --binary UNITY --house HOUSE --degrees 30 5 5 --target bottle:0 bottle:1 bowl:0 --model MODEL`。同一个冻结Unity世界执行fixed/active/no-update，不能拿各自重新启动的屋子替代。每臂再执行第2步评分（无all-steps，写臂内evaluation.json），最后 `tools/summarize_surface_comparison.py COMPARISON NEW_SUMMARY`。
4. 同第3步加 `--memory-only`，执行memory-retain / memory-reset，后者第三帧前撤回中间观测但保留首帧任务参考；逐臂评分后同一汇总器检查全部帧输入、世界状态及干预内容。
5. `tools/run_surface_episode.py restore --output ARM` 在新进程从copy.db恢复，禁止执行语义bootstrap。`--withdraw 0` 在该副本撤回首观察；不得直接修改原state.sqlite。数据库绑定源码/运行依赖，不能为了跨平台读入而改写绑定值。
6. `tools/verify_surface_memory.py run ARM --output NEW_MEMORY` 建立retain/withdraw-first/withdraw-last/reset四副本；各用独立进程 `tools/verify_surface_memory.py verify NEW_MEMORY/PHASE`；`tools/score_surface_memory.py ARM NEW_MEMORY TARGETS NEW_SCORE`。这部分静态控制首次完整执行源码为822fc3e（驱动后续提交7083056），与最终745613e的策略首参考修复分开标记；最终源码另实跑恢复和后续真实观察对照。

Unity binary使用已有 `f0825767cd50d69f666c7f282e54abfe58f1e917`；house为 `docs/reviews/pc_a/sim_timing_control_2026-09-29/evidence/raw-examples/south-320-frozen-0/evaluator_house.json`。macOS图形程序需在允许GUI/本地socket的环境运行。此次沙箱内首轮初始化超时，独立新运行在允许环境成功；不将不确定旧action重发。所有中止、失败目录和日志单独归档。

电脑B需先fetch并核对冻结SHA，在自有目录建立环境、下载已pin权重，然后复核源绑定和执行测试/独立比较。Windows不能直接复用macOS venv、绝对路径或数据库依赖绑定；若只能离线重评分，须标“归档复算”，不能签真实仿真独立验收。A不自动合并此堆叠PR。
