# 当前未关闭的跨环境复现差异

远端Ubuntu源码4ae7685的8项完整科学循环攻击测试先被“learned interaction example evidence is not source-regenerated”拒绝，未到达预定攻击条件。其中合法基线也失败。当前Mac源码fa4dc03复查同一合法基线/runner替换节点，在PYTHONHASHSEED=0、1、123下均通过（各约1秒）。

相关src、configs、benchmarks、该测试文件、pyproject.toml与uv.lock在两个SHA间字节完全相同。版本核验工具和其他测试虽已修复，这个差异不能归因于它们；也不能仅凭三种seed排除所有环境因素。应在远端保留当前重生成的训练/验证例子及环境指纹，与本机逐值比较后确定原因。当前只确认跨环境复现差异，未判定根因。

不得放宽错误字符串使反例看似通过，或仅重签旧报告就称当前合法基线成立。保留该矩阵为部分覆盖，先恢复完整正路径，再重复原定攻击与账本/动作后果验证。本轮没有修改该模块、旧证据或科学指标。

## Python patch version diagnostic

The completed Linux run used Python 3.13.15, whereas the original macOS environment used 3.13.5. An independent 3.13.15 interpreter on macOS, borrowing the existing cp313 site-packages through PYTHONPATH, passed the same selected runner-substitution node (1 passed, 1.07 s). This is a limited diagnostic, not a separately installed complete acceptance environment: attempts to reconstruct full and then dev environments from uv.lock failed downloading torch and scikit-learn, and both failure logs are retained. Python patch version alone did not reproduce the failure. Operating-system, math-library, dependency or other runtime differences remain unseparated. No source, artifact, verifier tolerance or expected error was changed.
