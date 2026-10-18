# Mac 本机 LIBERO / π0.5 / SAM 接入

本入口仅做仿真，保持核心 Python 3.13 环境与仿真 Python 3.11 环境隔离。
官方 openpi 以 Ubuntu/NVIDIA 为支持环境；本机 JAX CPU 兼容运行需用实际证据单独验证，不承诺实时速度。

## 目录与官方来源

工作树同级目录包含 `envs/libero`、`envs/core`、`vendor`、`models`、`cache`、`runs`。
工作树可放在主项目 `.local/simulation-stack/cpswm`。不要复制旧 venv 到不同电脑；在新路径重新安装。

- openpi: https://github.com/Physical-Intelligence/openpi ，固定 `215abfb217dbac7d5f1273282331b9b1866c0479`。
- LIBERO: openpi 子模块 `third_party/libero`，固定 `f78abd68ee283de9f9be3c8f7e2a9ad60246e95c`。
- SAM2: https://github.com/facebookresearch/sam2 ，固定 `2b90b9f5ceec907a1c18123530e92e794ad901a4`。
- π0.5 权重：`gs://openpi-assets/checkpoints/pi05_libero`，使用本地 `models/pi05_libero`；分词器缓存 `cache/openpi/big_vision/paligemma_tokenizer.model`，来源 `https://storage.googleapis.com/big_vision/paligemma_tokenizer.model`。

不修改这些官方仓库的网络实现。LIBERO 顶层为 namespace package，上游 setup.py 的 find_packages 会漏掉；macOS 隐藏 .pth 也可能被 Python 跳过。
`tools/simulation_python.py` 检查解释器前缀并用显式相对路径加载固定 vendor 源码，不依赖 .pth。

## 环境

在同级 `envs/libero` 建立 Python 3.11 环境，再安装 `requirements/libero-mac.txt` 与 `requirements/pi05-mac.txt`。
openpi 只需要上述推理依赖，不执行全量训练依赖同步。核心环境用本工作树 `uv.lock` 的 Python 3.13 冻结依赖建立于 `envs/core`。
正式运行的完整包版本、模型校验和源码摘要在证据清单中保留。Pydantic/numpydantic/Optax 固定到官方锁文件版本；任意最新版组合曾造成 InvalidSchemaError。

## 命令（在本工作树执行）

```sh
../envs/libero/bin/python tools/simulation_python.py -m pytest -o addopts= -q tests/test_libero_stack.py
../envs/libero/bin/python tools/simulation_python.py tools/run_libero_stack.py --steps 0 --output ../runs/camera-check
../envs/libero/bin/python tools/simulation_python.py tools/run_libero_stack.py --policy pi05-local --steps 10 --sam --box 104 131 143 163 --output ../runs/pi05-sam-check
```

每次指定新输出目录；旧失败证据不覆盖。Mac 原生离屏渲染仍需图形服务，在限制图形服务的沙箱中可能阻塞，应在获准环境执行。
示例框只适用于 `table_center/init0/seed7` 的256像素旋转后首帧，来自人工图像选框；更换场景先查看首帧重选，不能从仿真真值自动初始化。

## 接口与证据边界

- 两路 RGB、8维机器人状态和语言指令进入官方 π0.5 预处理；模型输出7维 OSC_POSE 动作。CPU JAX 路径不冒称 MPS 加速。
- 每5步重新规划；证据版本或目标改变立即丢弃剩余动作块。SAM 只读取已接收帧的前缀，首帧初始化与后续预测明确区分。
- SAM 视觉事件送入核心独立进程的真实 CPSWM 原生记忆；动作后帧标记 robot_generated，不作为人物习惯证据。
- 本入口执行官方任务指令。CPSWM 目前记录视觉证据与绑定动作版本，尚未自主选择新的机械臂操作目标。
- 仿真完成标志仅用于评估；不是视觉确认。图像区域不是标定的物理位置。10步联调不是完整任务成功或科学收益验收。

查看 `runs/<name>/summary.json`、`journal.json`、`manifest.json`、`policy_metadata.json`、动作数组和 `rollout.mp4`；失败时保留 `failure.json`。
