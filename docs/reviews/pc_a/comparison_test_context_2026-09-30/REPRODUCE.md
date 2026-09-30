# 复现

检出实际源码 fa4dc032c9ef843d8ec0975810c010cd1c5ca7d6，完整历史、独立实体 .venv，Python 3.13.5；`uv sync --frozen --extra dev --extra perception --extra hand-perception --python 3.13.5`。不要用其他工作树的 editable 环境或把 .venv 链到外部目录。

归档 evidence.tar.gz 含 run_reviews.py、原始每步完整命令、日志/JUnit/退出码/源文件摘要、当前 bundle 以及全部伪造副本。按 attempt01/commands.json 将绝对路径换成新的独立工作树和空输出目录；不得覆盖原件。执行顺序 round1→generate→attribution→round2→ruff→format。

run_reviews.py 原始绝对截止时刻是本次八小时窗口的 2026-09-30T01:15:00Z；未来复现需显式设新截止时间并记录，不把过期脚本无执行解释为通过。保留原件脚本，修改副本。

当前比较材料只可与对应源码验证，不能把前版本 bundle 重签成当前来源。验证设置 S2_AUDIT_BUNDLE 指向本次新生成目录；第二轮两个真实 CLI 正路径耗时约各15分钟，保留合法与伪造包完整输出。单独生成 attribution.json 不构成核验。
