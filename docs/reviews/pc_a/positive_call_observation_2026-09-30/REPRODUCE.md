# 复现与解释

实际测试源码053b27851c2f935e4de8fb00b0bee4dd9f294821，base2bd0ee7f44e01cb59dd29d36deb3ed4464907c5c；生产src/工作流/依赖均无变化。

按协作说明重建uv冻结环境：uv sync --frozen --extra dev --extra perception --extra hand-perception。初次沿用前轮外部环境，但验收工具要求本地实体.venv且拒绝符号链接；最终在本轮工作目录用同一锁文件创建实体环境。外部环境和符号链接失败、同步日志均保留。不能称另一台机器独立复现。

run_checks.py reviews --attempt attempt01先核验已提交Python和依赖、CI工作流，再顺序运行44项完整动作测试与124项来源/算子/反馈审查；命令、时间、退出码、JUnit和前后源码清单见attempt01。脚本绝对本机路径按可信部署修改，不编辑测试或历史证明。

run_checks.py full --attempt attempt01要求两轮先通过，随后以4个worker执行完整测试选择，--maxfail=20和90分钟预算。超时写124，失败保持非零，跳过/xfail单独报告；任何未完整执行的前缀均不能声称6035项通过。本机不额外注入测试标签或改变生产配置。

上一轮被替换方法的失败证据仍在PR66封存包的first-failure-diagnostic内；本轮不覆写。远端实际源码CI单列，重复开工文档运行的取消不等于通过。

最终attempt02重新执行扩展两轮，第一轮额外加入完整验收工具模块，随后完整选择采用-v逐项打印节点名与--tb=short；执行选择和预算不减少。物理实体环境是验收协议要求，Windows按自己的平台重建，不复制本机.venv。
