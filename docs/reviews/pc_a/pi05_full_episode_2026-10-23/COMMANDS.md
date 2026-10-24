# 完整episode与重放命令

运行源码 `611e9dbee986a7fe6a2af33661d7a7d284402d03`，干净启动，工作树位于 `.local/simulation-stack/cpswm-full-episode`。输出使用兄弟runs目录，不污染启动Git状态。Mac原生MuJoCo图形上下文需可用。官方vendor和已有模型按manifest锁定；不下载、不训练。

```sh
../envs/libero/bin/python tools/simulation_python.py tools/run_libero_stack.py --policy pi05-local --task table_center --initial-state 0 --seed 7 --steps 220 --stop-on-success --output ../runs/pi05-full-episode-20261024-03
../envs/libero/bin/python tools/simulation_python.py tools/verify_pi05_full_episode.py ../runs/pi05-full-episode-20261024-03 --output /private/tmp/cpswm-pi05-full-episode-03-verification.json
PYTHONPATH=src:tools ../envs/libero/bin/python tools/simulation_python.py -m pytest -o addopts='' -q tests/test_pi05_full_episode.py tests/test_libero_stack.py
../envs/core/bin/python -m ruff check tools/run_libero_stack.py tools/verify_pi05_full_episode.py tests/test_pi05_full_episode.py
```

新复现必须使用不存在的独立输出目录。重放核验不重新调用π0.5推理；它重建公开策略输入、执行保存动作并核对物理轨迹/逐步done/首次成功/最终图像，不能作为对模型计算真实性的独立认证。

首次run01被SIGTERM中断，20动作/4推理，未完成；后台run02未启动，没有manifest或动作，不计为episode。run03为从头重新执行的唯一完成并经重放核验的运行，不拼接早先轨迹。
