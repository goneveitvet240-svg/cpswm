# 复现

实际源码4ae76850ffd99d86703b4e45e837d4e402203c78。在当前工作目录创建实体环境：uv sync --frozen --extra dev --extra perception --extra hand-perception --python 3.13.5。不要复制Mac环境到Windows。

run_reviews.py顺序运行两轮并核验源码前后哈希；命令/时间/退出码和JUnit见attempt01。实际完整命令为python tools/run_ci_regression.py --output output/ci-regression/execution --budget-seconds 3900 --grace-seconds 60。输出目录必须新建，避免覆盖旧失败。

result.json中的状态和child_exit_code分别保存调度结果与子进程退出；超时124、人工中断130、启动失败127。即使子进程收到中断后返回0，超时仍不是成功。pytest.xml若存在也可能只覆盖已完成前缀；完整CI必须另核验测试数量/跳过/失败，不能只看XML存在。

check_collection_shell.py核验Bash管道退出传播；probe_shallow_history.py before/after比较独立深度1克隆与补全历史。浅副本只检出12个必要材料，全部来自同一HEAD；前后不改材料。完整克隆本机路径/private/tmp/cpswm-ci-shallow-20260930是重建方式，不作为独立科学证据。

开发日志11/13/15项及一次FIFO异步终止观测失败全部保留；正式结论仅绑定最终两轮15/55矩阵。远端实际上传/完整回归在本次封存时仍未完成。

补充原件运行：同一冻结源码再次执行15个生命周期案例，15通过，21.28秒；专用basetemp保存10份实际执行记录、原日志、JUnit/覆盖率和夹具，每份log_sha256核验一致。此前两轮临时子记录已被pytest清理，不冒充已封存；两轮命令/JUnit保留，补充运行单列，不冒充独立第三方。

封存105个常规文件/1863198字节，压缩401516字节，SHA256 e0748315bb7c4a8ab6652d40d0b480668fae23f2aa4b011c6d00f54c9b46543a，逐文件读回核验。排除派生缓存、临时FIFO与pytest便捷符号链接；原始数据文件、命令、日志、失败和补充案例保留。
