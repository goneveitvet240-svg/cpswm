# 复现与证据边界

实际功能提交00283c607a5fb49c293cefe8eafd65cc2192f558，base 00cc5a47cad988b453d5839b63fd7c6a89f4246d。共享原件含逐命令参数、退出码、完整Python/dependency源码摘要、Python包清单、SDK/Unity前后摘要和全部历史输入。

在对应提交独立创建环境，按uv.lock安装依赖；原机复用了本地开发环境，不是独立重建。设置PYTHONPATH=src:tests:tools、PYTHONHASHSEED=0、OMP_NUM_THREADS=2、MKL_NUM_THREADS=2。真实前端测试还需显式CPSWM_SSDLITE_WEIGHTS及CPSWM_FASTERRCNN_WEIGHTS，缺失不可当作通过。

本轮连续两轮命令、JUnit、lint和源码映射见原件attempt01/commands.json、round1.xml、round2.xml、source.json。完整仓库CI已触发但未通过（继承文件格式失败、全量测试尚未得到完成结果）；B独立验收未执行。

实际运行入口：tools/run_history_action_loop.py --mode run --task clarification --detector-kind ssdlite（或fasterrcnn）--site north（或south）--output <新目录> --sdk-python <AI2-THOR解释器> --binary <Unity二进制> --weights <所选前端固定权重> --checkpoint <既有typed_factor_graph_transformer开发checkpoint>。默认前端仍为ssdlite，分类控制通过--task classification保留。按PLAN固定顺序执行；输出目录已存在会拒绝，不能覆盖失败试次。

其后运行tools/history_visual_evidence.py --mode run --output <历史目录> --ssdlite-weights <权重> --fasterrcnn-weights <权重> --checkpoint <同checkpoint>。该命令实际恢复SQLite/重做原受控反证/11源神经重放/原图视觉推理，再在同图上推两个前端并读取评价标签；私有标签不会成为decoder参数或策略输入。函数paired_predictions只接受公共拥有者记录。已有观测无法代替一个未执行动作的反事实返回。

将两个工具的mode改为verify可复算记录，不会重新启动Unity。visual-evidence的verify也会复算整个历史。不要把同机另进程复算称为独立环境或新仿真验收。一个新Unity重跑须另建输出目录；跨启动画面不保证逐字相同。

开发checkpoint来自父分支docs/reviews/pc_a/neural_native_loop_2026-09-29/evidence/development-checkpoints/typed_factor_graph_transformer/checkpoint，仅是组件夹具2步SGD训练。官方视觉权重、Unity和Python环境不装入本轮原件包；模型文件摘要由解码器及源记录验证。

结果中完整候选与全实例对应矩阵保留零重叠项；掩膜交集按半开框内的像素中心计算。bbox IoU和掩膜交集都是评价数值，不自动赋目标身份。三维位置/朝向、接触/释放、长期证据权限以及独立经验校准不由此成立。

跨机限制：当前NativeNeuralEvidence保存checkpoint_directory绝对路径，verify_neural_evidence会直接读取该路径。原件里的路径指向/private/tmp/cpswm-pc-a-visual-history-20260929/...；仅解压到另一目录，尤其Windows，不足以复算旧证据。清单字节检查可跨机，实际重跑应从本源码/锁/权重新建历史；已有归档的跨机checkpoint定位适配和B复验仍待处理，不能通过编辑已签入的证据路径来伪造原身份。本轮只验证本机新进程，不宣称跨机器一键复现。

封存原件复算严格使用00283c607a5fb49c293cefe8eafd65cc2192f558：源码校验覆盖测试文件。后续ac93f8d489209943cbcff9292ab483330538854b只修复两个新增测试的可选依赖隔离，生产与实验入口逐字不变，但不应在新测试版本上要求旧源码归档通过。新测试版本顺序33/42双审零跳过及完整补充命令见[CI补充交付](CI_FOLLOWUP.md)。
