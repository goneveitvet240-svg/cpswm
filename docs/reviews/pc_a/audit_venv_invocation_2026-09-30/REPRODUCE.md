# 复现

检出源码818d83a36cc1812d68662297b76bc6940272b25c，uv sync --frozen --extra dev --extra perception --extra hand-perception --python 3.13.5创建实体.venv。证据run_reviews.py顺序执行新环境模块9项及其与完整统一验收模块的49项组合，源清单/命令/日志/JUnit全部保留。

probe_environment_invocation.py比较真实版本调用与直接虚拟环境调用的sys.prefix；preserve_fingerprint_attacks.py真实构造并重算完整指纹，重签假版本/假入口仍拒绝。将可信部署路径改为新目录，不能把旧环境指纹当可跨机器直接接受的凭据。

current-manifest-component-input.json只是组件测试输入，不是冻结清单发布或工程验收。保留原P0字节哈希及其过期测试失败。运行器本轮只在macOS实体环境验证，不宣称Windows路径协议已完整适配。
