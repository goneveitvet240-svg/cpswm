# 固定源码复现与交接边界

草稿PR：https://github.com/goneveitvet240-svg/cpswm/pull/56 。独立分支codex/pc-a-neural-native-loop-20260929，叠在既有A视觉开发分支上。完整集成与B审查未完成。每轮报告绑定自己的实际代码SHA，后续源码不能继承旧审查。

先fetch，再使用独立工作目录检出欲复核的完整SHA。不要把本机venv、工作树.git指针或绝对路径拷贝到另一台机器。按uv.lock新建环境：`uv sync --frozen --extra dev --extra perception --extra hand-perception`。本轮实际Python 3.13.5 / Torch 2.13.0，像素与神经推理固定2 CPU线程；Unity SDK使用另一个已配置解释器，不能将两者混作同一依赖。运行路径通过CLI显式传入，不自动安装/购买资源。

第一轮实际检查点由`tools/run_neural_native_replay.py`生成，三个目录名分别为typed_factor_graph_transformer、slot_conditioned_perceiver、autoregressive_typed_graph_policy，内含checkpoint/manifest.json与实际权重；它们是微型组件夹具训练，不是自然训练。固定源码的完整两审/运行入口是`docs/reviews/pc_a/neural_native_loop_2026-09-29/run_frozen.py --output <新空目录>`。受测原始目录与完整文件摘要保留在A主仓output/neural-native-loop-20260929/round1-attempt01。

第二轮入口run_frozen_camera.py显式接收--output、--sdk-python、--binary、--weights、--checkpoint。第三轮入口run_frozen_comparison.py接收--output、--sdk-python、--binary、--ssdlite-weights、--fasterrcnn-weights、--checkpoints。checkpoints指向上面的三架构目录的共同父目录。后两个入口会启动真实Unity进程及本机通信；所提供的解释器、仿真二进制与官方权重必须实际可用，不能以伪造响应替代未配置的仿真器。

第三轮按45项第一审→两个真实阳/阴样本→17项结果攻击/重建→16项恢复→mypy/Ruff→完整24场→逐场重建执行。所有组相同动作预算、已有0.5过滤值与类别停止/已看视角规则。matrix.json在启动前写入全部24个格子，未跑/失败不能隐藏。每场保存result.json、state.sqlite、实际RGB和独立evaluator_only真值；verify_neural_camera_comparison.py不接受只填成功率的报告，会重载实际模型重算。

现有工件包含source/dependency绑定，本地SQLite不能直接换源码/权重/推理配置后声称同源恢复。重新运行与迁移要分别报告。原图、作者/模拟器真值、假设观测似然、自然语义资格四者分离；神经q/q枚举一致性不等于提议性能，类别阳性不等于实例身份、取回成功或完整结构二科学收益。B按具体SHA独立复核后，才进入A集成流程。
