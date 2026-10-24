# 复现命令

使用实际源码 `ea0d6f231ba9971d75131e9fa9fc4820ab4452cc` 的独立干净工作树，兄弟目录 core Python3.13.5。运行目录必须不存在。

```sh
PYTHONPATH=src:tools ../envs/core/bin/python tools/run_short_history_reference.py --output /private/tmp/reference-new
PYTHONPATH=src:tools ../envs/core/bin/python tools/verify_short_history_reference.py /private/tmp/reference-new --replay-output /private/tmp/reference-new-replay --output /private/tmp/reference-verification.json
PYTHONPATH=src:tools ../envs/core/bin/python -m pytest -q tests/test_short_history_reference.py
../envs/core/bin/python -m ruff check tools/run_short_history_reference.py tools/verify_short_history_reference.py tests/test_short_history_reference.py
```

`evidence/report.json`为原始报告，8份gzip为完整路径，verification.json为源绑定全部重放回执。压缩原件约14.5MB。
