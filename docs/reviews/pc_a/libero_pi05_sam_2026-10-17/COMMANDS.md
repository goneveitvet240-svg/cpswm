# 可复核命令

所有命令在任务工作树执行。对应运行源码为 `85e0664d8fa3d0fc5fa5acc468716ef6c02ce690`；验证工具随证据提交。

```sh
../envs/libero/bin/python tools/simulation_python.py -m pytest -o addopts= -q tests/test_libero_stack.py --junitxml=docs/reviews/pc_a/libero_pi05_sam_2026-10-17/evidence/final-contract-tests.xml
../envs/core/bin/python -m pytest -o addopts= -q tests/test_small_sim_framework.py --junitxml=../runs/core-simulation-regression.xml
../envs/libero/bin/python tools/simulation_python.py tools/run_libero_stack.py --policy pi05-local --steps 10 --sam --box 104 131 143 163 --output ../runs/pi05-sam-native-03
../envs/libero/bin/python tools/simulation_python.py tools/verify_libero_stack_run.py docs/reviews/pc_a/libero_pi05_sam_2026-10-17/evidence/run
```

运行目录已存在时必须换新名字，不覆盖原件。图形仿真在获准访问macOS图形服务的环境执行，纯检查不需要。包版本、vendor SHA、源码哈希、原始参数见 `evidence/run/manifest.json`，模型配置见 `evidence/run/policy_metadata.json`。
`uv pip check`仍列出openpi的未安装训练/其他平台依赖：equinox、flatbuffers、gym-aloha、lerobot、ml-collections、polars、tyro、wandb。本入口只用已经实跑验证的推理子集；不宣称完整openpi训练环境可用。

最终修复复跑把 `--steps` 改为5，输出 `../runs/pi05-sam-native-04`；绑定 `96c8e026bec097bcc135b3c0d121ad55b9360c68`。
局部类型检查：`../envs/core/bin/python -m mypy --follow-imports=silent src/cpswm/simulation/integrations`，6文件通过。
