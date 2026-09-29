# 复现

实际源码c87b6bb1e3c72986afe517f7f29ebf3d028f2283；原件output/ci-action-report-20260930。先查看每次attempt的source.json、commands.json和JUnit，失败attempt01不可用attempt02结论覆盖。

完整运行/检查环境命令为uv sync --frozen --extra dev --extra perception --extra hand-perception。测试根在pyproject.toml声明；pytest不再依赖手工设置PYTHONPATH。受限的旧editable环境不等于移机部署，按AGENTS要求重建环境。本轮实际新环境为/private/tmp/cpswm-ci-full-env-20260930，环境清单见environment-full.json；A在同一Mac重建，不是B独立或Windows验收。

run_frozen.py reviews --attempt attempt02顺序运行两轮审查、无额外PYTHONPATH的完整收集、全仓静态检查。相同冻结源码下run --attempt attempt02运行真实北侧RGB-D视觉神经历史并另进程完整复算；SDK/Unity前后身份检查保留。脚本的绝对本机路径须按可信部署配置调整，不编辑历史证明或模型身份。

recompute_action_reports.py只读取PR64/65保存的命令对，输出新报告含义及输入文件哈希；不能用于声称旧原件在新源码下完整验证通过。audit_action_report.py复制当前完整历史，分别构造字段相互一致的伪造报告，由完整重放与真实拥有的计划/回执重新决定报告值。一次提前启动的审计主动中断，因为正常视觉报告仍会创建派生文件；中断副本及原因保留，最终审计必须等正常验证结束再固定清单。

verify_relocation.py在新环境中复制源码/历史并搬移模型，子进程排除旧editable搜索入口，同时用审计钩子禁止旧目录读取；完整核验和五类状态摘要比较都必须通过。该测试与新机器重建、跨架构数值复核分别记录。

run_first_failure.py是完整选择但--maxfail=1、两worker和30分钟预算的诊断。任何提前失败/超时均不是完整回归通过；远端正式CI仍使用其原65分钟完整执行预算。后续封存时明确当前各运行是否结束，不能把正在写入的日志当作已冻结原件。

完整封存1,248文件/356,394,634字节，压缩48,530,479字节，SHA256 28bd25e25a1eef66d621d47f11f1f796e900bf95aae1c9c471b9641b75ce546d，逐文件读回核验；仅排除派生Python/pytest缓存。远端完整CI仍在运行，未冒充已完成。
