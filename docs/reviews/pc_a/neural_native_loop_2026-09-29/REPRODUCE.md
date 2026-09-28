# 固定源码复现与交接边界

草稿PR：https://github.com/goneveitvet240-svg/cpswm/pull/56 。独立分支codex/pc-a-neural-native-loop-20260929，叠在既有A视觉开发分支上。完整集成与B审查未完成。每轮报告绑定自己的实际代码SHA，后续源码不能继承旧审查。

先fetch，再使用独立工作目录检出欲复核的完整SHA。不要把本机venv、工作树.git指针或绝对路径拷贝到另一台机器。按uv.lock新建环境：`uv sync --frozen --extra dev --extra perception --extra hand-perception`。本轮实际Python 3.13.5 / Torch 2.13.0，像素与神经推理固定2 CPU线程；Unity SDK使用另一个已配置解释器，不能将两者混作同一依赖。运行路径通过CLI显式传入，不自动安装/购买资源。

第一轮实际检查点由`tools/run_neural_native_replay.py`生成，三个目录名分别为typed_factor_graph_transformer、slot_conditioned_perceiver、autoregressive_typed_graph_policy，内含checkpoint/manifest.json与实际权重；它们是微型组件夹具训练，不是自然训练。固定源码的完整两审/运行入口是`.venv/bin/python docs/reviews/pc_a/neural_native_loop_2026-09-29/run_frozen.py <新空目录>`（输出是位置参数，不是--output）。受测原始目录与完整文件摘要保留在A主仓output/neural-native-loop-20260929/round1-attempt01。

这三个**实际已使用**的微型检查点亦逐字备份到本报告目录`evidence/development-checkpoints/`；六个文件共2,440,880字节，逐文件摘要在FILES.json。`--checkpoints`可指向该目录，从而不依赖A的临时目录或重新训练出不同权重。旧SHA本身不含此后补充的证据包，复核旧版本时应在独立数据目录取得并核对包后再检出对应旧源码；不能把新源码叫旧SHA复现。SQLite中实际神经证据保存当时绝对路径，跨机重新执行可以使用新路径，直接搬旧SQLite并改路径不叫原样恢复。

第二轮入口run_frozen_camera.py显式接收--output、--sdk-python、--binary、--weights、--checkpoint。第三轮入口run_frozen_comparison.py接收--output、--sdk-python、--binary、--ssdlite-weights、--fasterrcnn-weights、--checkpoints。checkpoints指向上面的三架构目录的共同父目录。后两个入口会启动真实Unity进程及本机通信；所提供的解释器、仿真二进制与官方权重必须实际可用，不能以伪造响应替代未配置的仿真器。

第三轮按45项第一审→两个真实阳/阴样本→17项结果攻击/重建→16项恢复→mypy/Ruff→完整24场→逐场重建执行。所有组相同动作预算、已有0.5过滤值与类别停止/已看视角规则。matrix.json在启动前写入全部24个格子，未跑/失败不能隐藏。每场保存result.json、state.sqlite、实际RGB和独立evaluator_only真值；verify_neural_camera_comparison.py不接受只填成功率的报告，会重载实际模型重算。

现有工件包含source/dependency绑定，本地SQLite不能直接换源码/权重/推理配置后声称同源恢复。重新运行与迁移要分别报告。原图、作者/模拟器真值、假设观测似然、自然语义资格四者分离；神经q/q枚举一致性不等于提议性能，类别阳性不等于实例身份、取回成功或完整结构二科学收益。B按具体SHA独立复核后，才进入A集成流程。

## 第四至八轮入口

各入口均位于本报告目录，先独立检出报告中的完整功能SHA，再新建输出目录。显式传入当前机器的SDK解释器、可用Unity二进制、两份官方权重；这些参数不是A目录的自动发现或Windows可运行承诺。

| 轮次 | 冻结执行器 | 必填参数 |
| --- | --- | --- |
| 4 | run_frozen_grid.py | --output --sdk-python --binary --ssdlite-weights --fasterrcnn-weights |
| 5 | run_frozen_resolution.py | 上行全部，另加 --checkpoints |
| 6 | run_frozen_identifiability.py | --output --checkpoints |
| 7 | run_frozen_resolution_grid.py | --output --sdk-python --binary --ssdlite-weights --fasterrcnn-weights |
| 8 | run_frozen_instances.py | --output --sdk-python --binary --ssdlite-weights --fasterrcnn-weights |

每条命令前后验证全部被跟踪Python、pyproject.toml、uv.lock与Git文件内容相同，不允许未跟踪Python混入。第五至八轮依次各完成两轮局部A自审，再运行全矩阵并在新进程重算；第八轮只采集三个事后选定实际快照，不是完整动作闭环。每轮日志、JUnit XML和命令参数在对应evidence目录，失败/跳过的历史尝试保留，不能拼接为同SHA一次通过。

选择性反例原图包在`evidence/selected-pixel-cases`，含15个原始数据文件及SHA清单和实际模型逐帧重放结果。按其README在仓外运行`.py.txt`脚本，避免触发未跟踪Python保护。它不是正式holdout，不能用三个事后案例估计泛化率。第七轮原始132帧在A主仓output持久目录，Git中共享完整数值结果/来源/命令；第八轮三个快照的45个完整原件（含全部实例掩膜）亦共享在evidence/round8/snapshots，并已在该位置重算；重新运行采集可能得到不同RGB。相同旧RGB重算与重新渲染是两种复现范围。

最终跨模块两审的详细命令与结果见FINAL_INTEGRATION.md。需要显式设置`CPSWM_SSDLITE_WEIGHTS`到实际官方文件，否则五项真实解码器测试会skip；skip不能计为通过。环境继续固定`PYTHONPATH=src:tests:tools`、`PYTHONHASHSEED=0`、`OMP_NUM_THREADS=2`、`MKL_NUM_THREADS=2`。测试数量不是安全性完备证明，B应按完整SHA复核合法正路径、完整伪造、依赖状态、账本和行动后果。
