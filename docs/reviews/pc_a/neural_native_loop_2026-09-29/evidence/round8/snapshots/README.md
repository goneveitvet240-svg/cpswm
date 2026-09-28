# 三个实际快照的完整对应证据包

45个原始文件逐字复制，共11,333,779字节，FILES.json列出SHA。含公共采集StateCodec、RGB、全部46实例目录及掩膜、分割图、动作日志和预测；私有评价放在evaluator_only，不能给政策/视觉前端输入。原受测源码b1969f30b85434452f6b23ec53c93d84799ff62f。复制后已在本目录实际重算3/3、所有原文件摘要保持，package-replay.log位于父目录；这不是原冻结执行器内的新命令。

在同源仓库和相同Torch依赖下，可执行tools/run_instance_correspondence_diagnostic.py --mode verify --output <本目录>，其余参数为--sdk-python、--binary、--ssdlite-weights、--fasterrcnn-weights。verify模式只重算现存数据，不启动Unity；两个权重必须实际可用，前两项解析器要求填写但此模式不调用。推理固定2 CPU线程。这里保持原字节，不把路径修改成新的采集记录。原始A机器二进制/SDK摘要仅为历史采集来源，不代表当前机器使用过它们。

三个事后选定快照不能当独立样本或泛化基准。全部SDK数据是仿真评价身份，不是自然身份训练授权、人物复核或接触标注。
