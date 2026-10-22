# 复现与源码绑定

工作树 `.local/simulation-stack/cpswm-suffix-replay`。默认 full；可选 suffix 类在 `src/cpswm/simulation/suffix_memory.py`。不同机器重建环境，不能复制 Mac 虚拟环境。

## 成本矩阵

切到 `8e9d8da9276320f7d747bb4e02fb97bd2e936b5b`，输出位于工作树外；core Python 3.13。对每个 arm（native_joint/native_factorized）和 case（archive/long）运行 full、suffix 各 3 次，第二轮反转顺序。实际顺序在 `evidence/benchmark/jobs.json`。

```sh
PYTHONPATH=src:tools ../envs/core/bin/python tools/run_suffix_replay.py --implementation full --arm native_joint --case long --output /private/tmp/suffix-full.json
PYTHONPATH=src:tools ../envs/core/bin/python tools/run_suffix_replay.py --implementation suffix --arm native_joint --case long --output /private/tmp/suffix-cached.json
```

用 `tools/run_suffix_replay.py::compare_reports(full, suffix)` 比较配对原件；正式报告逐个核对 canonical content hash、干净 git status 和相同源码 SHA。Windows 使用本机 Python 与 `PYTHONPATH=src;tools`。RSS 在不支持 resource 的平台标 null，不伪填 0。

## 核心验证

```sh
../envs/core/bin/python -m pytest -o addopts='' -q tests/test_suffix_memory.py tests/test_small_sim_framework.py tests/test_research_pilot.py tests/test_current_event.py tests/test_current_event_adversarial.py
../envs/core/bin/python -m pytest -o addopts='' -q tests/test_memory_goal_control.py
../envs/libero/bin/python tools/simulation_python.py -m pytest -o addopts='' -q tests/test_libero_stack.py
../envs/core/bin/python -m mypy --follow-imports=silent src/cpswm/simulation/memory.py src/cpswm/simulation/suffix_memory.py src/cpswm/simulation/goal_control.py src/cpswm/simulation/integrations/bridge.py
```

核心/缓存测试对应实现源码内容，后续两次补丁只调整审计/遥测输出；目标测试在最终源码内容上再次运行。

## 真实仿真接口与负例

最终干净源码 `4efcd4c4b52a9030c6714d350030c54aa8b7ecde`：

```sh
../envs/libero/bin/python tools/simulation_python.py tools/run_libero_goal_loop.py --policy smoke --memory-replay suffix --box 104 131 143 163 --output ../runs/suffix-goal-smoke-20261023-02
../envs/core/bin/python tools/verify_libero_goal_run.py ../runs/suffix-goal-smoke-20261023-02
../envs/core/bin/python docs/reviews/pc_a/suffix_replay_2026-10-23/audit_artifacts.py ../runs/suffix-goal-smoke-20261023-02 /private/tmp/cpswm-suffix-smoke-negative-audit.json
```

macOS 渲染需要允许本机图形上下文。早期 `...-01` 运行源码为 e83feae，原件留在本机；最终归档只用 `...-02`。本次 smoke 不加载 π0.5 权重，不能把审计里的两次 inference 解释为两次 π0.5 推理；最终回执明确标 `policy=smoke`、`pi05_inference_executed=false`。
