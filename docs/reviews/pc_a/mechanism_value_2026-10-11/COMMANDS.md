# 复现命令与边界

推断源码：d87555760376339b662e8fcdb4c0609d9687bc2b；独立算术工具：52331f2a84261f293ce7e59490e336f8213adfa3。生产 src 与 base 536d222c57bcd3654b49f222a6c0b8312a00dcc7 相同。

本机 Python 为 `/private/tmp/cpswm-object-reid-venv/bin/python`，Python 3.13.5。跨机器请重建环境，不复制 macOS venv；版本见 environment.json。以下在本分支仓库根目录执行。

```sh
PYTHONPATH=src:tools python tools/verify_full_mechanism_value.py --output /tmp/cpswm-mechanism-value-new
python tools/score_full_mechanism_value.py /tmp/cpswm-mechanism-value-new --output /tmp/cpswm-mechanism-value-checks.json
python -m pytest tests/test_full_mechanism_value_diagnostic.py tests/test_structure_two_stateful_full_joint.py tests/test_structure_two_stateful_full_joint_adversarial.py -q
python -m ruff check tools/verify_full_mechanism_value.py tools/score_full_mechanism_value.py tests/test_full_mechanism_value_diagnostic.py
```

输出目录必须不存在。默认三条件、各10条评价序列、validation7/8/9；每个简单控制3个候选独立选择。没有修改随机数、写授权、粒子数、联合强度或生产读出参数。运行脚本写入 source.json，并在完成时重新验证代码、配置和模型 hash。

证据归档 main-output.tar.gz 保存逐步模型可见输入、四臂实际动作、动作提交后单独写出的 evaluator truth、机制/公平性回执和全部调参结果；解压后运行独立算术工具。manifest.json 保存归档与解压内容校验信息。原始数据与图表均为 D0 受控语义，非 RGB-D 自然闭环或机器人实测。

已有 CIAV 仿真器在选定动作之后，从 evaluator truth 生成模拟人物观测；这不是自然人物校准。AMG 匹配适配器仅消费原始语义输入、没有完整共同 CIAV 接入，不能称严格同信息强外部系统。严格同完整状态/候选评分/粒子预算的识别对照是 joint 与 factorized；latest 是同底层推断和纠正链的读出消融。

试跑：相同 complete32 条件、仅 seed30，用于工具可执行性；未纳入主评价。补充重复：complete32 seed31 四臂重新构建运行，比较实际动作与关键指标；只算重复验证，未计作额外独立样本。

运行中未改推断源码。首次 pytest 因 sparse checkout 缺 apps/evaluation_runner 启动器而退出，补取既有目录后28测试通过；无生产修复。独立算术初稿错误地把空 known_location_ids 当作候选全集，随后按既有评分协议从公开 source/attempted/destination 列构建全集；阶段按日历日期而非时间差向下取整划分。这些评测工具修正未改变原始动作、标签或主实验输出。
