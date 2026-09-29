# 审查版本命令保留虚拟环境入口

Base21619f014b43c724b28a93fa4612e03e5a10e2c7，实际源码818d83a36cc1812d68662297b76bc6940272b25c，分支codex/pc-a-audit-venv-invocation-20260930。只修改版本探针调用入口及其新测试；生产src、既有科学协议、依赖/P0清单均未改。

旧_tool_version先解析.venv/bin/python软链接再执行，Python丢失pyvenv.cfg发现上下文，错误进入基础环境。直接对照证明同一可执行文件身份哈希不足以保持sys.prefix。修复使用invocation_executable执行，与正式审查执行器一致，同时保留resolved_executable与文件SHA身份绑定。真实项目pytest版本现在能读取，空虚拟环境不回退至基础环境，命令退出17仍失败。

实际源码两轮顺序9/49 passed、零跳过；Ruff/格式通过。第二轮包含完整40项统一验收工具测试。真实别名一致性、替代有效环境、完整重签假版本/假入口均检查。另保存当前内存清单输入、1份真实完整指纹与2份完整伪造JSON，真实重算拒绝两份伪造，磁盘旧P0原字节不变。

原失败测试单项复查仍为失败：修复后已通过工具版本阶段，到达toolchain file drifted from source manifest: pyproject.toml。其旧清单确实不匹配当前环境，不能为了变绿绕过或自动刷新。本轮关闭入口执行缺陷，没有关闭全仓旧回执/P0验收，更不是B/Windows独立复现或自然闭环科学收益。
