# 审计复现命令

从独立工作树 `.local/simulation-stack/cpswm-third-party-audit` 执行。已有仿真环境和官方模型沿用之前交付；core 为 Python 3.13，libero 为 Python 3.11。不要复用已存在的 output 目录。以下列出本次实际目录；重新复现时换新名字。

目标源码 `90e6c60009e17226b1a58f31245dcd04b810b23a`；审计工具 `d6aa33464f7117e465722f5cd4353ebc026a8683`。后续报告提交不改变被测代码。命令 exit 0 仅表示审计复现运行完成；三个缺陷均为 OPEN，不是项目验收通过。

## 定向已有回归与静态检查

```sh
PYTHONPATH=src:tools ../envs/core/bin/python -m pytest -o addopts= -q tests/test_memory_action.py tests/test_memory_goal_control.py tests/test_reliability_replication.py
../envs/core/bin/python -m ruff check tools/audit_current_project.py
../envs/core/bin/python -m ruff format --check tools/audit_current_project.py
```

已有套件 45 passed / exit 0；审计脚本 Ruff 通过。没有重跑全仓测试。CI 日志下载自 PR128 当前 static-quality job 121218474190，不是审计分支新 CI 的结果。

## A1：来源撤回与已执行事实

```sh
PYTHONPATH=src:tools ../envs/core/bin/python tools/audit_current_project.py state-machine --output ../runs/third-party-audit-state01
```

包含合法对照和改变到达顺序的反例。完整结果中 feedback、plan、step 均拒绝，未结算 ticks=[101]。

## A3：冻结配置副本改写

原始 runs 从 PR128 的 `reliability-fresh02.tar.gz`、`reliability-prefix01.tar.gz`、`reliability-fresh01.tar.gz` 分别恢复到对应目录；先按原 MANIFEST.json 核对原件。本机使用此前完整保存的相同原件，所有成员均再次比对一致。

```sh
PYTHONPATH=src:tools ../envs/core/bin/python tools/audit_current_project.py protocol --runs ../runs --output ../runs/third-party-audit-protocol01
```

该命令重新分析合法原件、完整核验，再复制并修改 bootstrap 次数，重新分析和完整核验副本；不会修改原目录。源数据 768 点完整重生成，重复状态只比较既有 36 前缀与 109 中断记录，不宣称第二次全量推断。

交付 `protocol-evidence.tar.gz` 不重复打包未变的 points.jsonl.gz，也不打包可由原记录重新生成的 audit_points.json；原件 hash 在 original_data_unchanged.json，全部其他配置、结果和日志保留。

## A2：真实 smoke 与伪造策略标签

新 smoke 在开工提交 770bd7c 的干净目录执行；完整源码 SHA 和与目标生产代码等价核对见 source_binding.json。没有实际调用 π0.5。

```sh
../envs/libero/bin/python tools/simulation_python.py tools/run_native_pi05_probe.py --policy smoke --steps 5 --output ../runs/third-party-audit-smoke03
PYTHONPATH=src:tools ../envs/core/bin/python tools/audit_current_project.py native --smoke ../runs/third-party-audit-smoke03 --output ../runs/third-party-audit-native01
../envs/libero/bin/python tools/simulation_python.py tools/verify_native_pi05_probe.py ../runs/third-party-audit-smoke03 --physics --output ../runs/third-party-audit-smoke03-physics.json
../envs/libero/bin/python tools/simulation_python.py tools/verify_native_pi05_probe.py ../runs/third-party-audit-native01/forged-pi05 --physics --output ../runs/third-party-audit-native01/forged-physics.json
```

物理执行及重放需要 macOS 图形服务权限，在获准沙箱外执行；不下载/采购算力。两种副本 core/physics 都接受，构成漏检。原件/副本均在 native-evidence.tar.gz 中，包含视频、输入/输出数组、相机/跟踪和请求日志；没有模型权重。

失败尝试保留：smoke01 漏用 simulation_python.py，LIBERO 导入失败 exit 1；smoke02 在沙箱图形服务处停滞，终止本轮进程后 exit 143；不能把它们写成成功物理执行。成功的是 smoke03 / exit 0。

## 证据回读

```sh
../envs/core/bin/python - <<'PY'
import hashlib, json, tarfile
from pathlib import Path
root = Path('docs/reviews/pc_a/third_party_audit_2026-10-26')
m = json.loads((root/'MANIFEST.json').read_text())
for name, meta in m['files'].items():
    b = (root/'evidence'/name).read_bytes()
    assert len(b) == meta['bytes'] and hashlib.sha256(b).hexdigest() == meta['sha256']
for name, meta in m['archives'].items():
    p = root/'evidence'/name
    assert hashlib.sha256(p.read_bytes()).hexdigest() == meta['sha256']
    with tarfile.open(p, 'r:gz') as t:
        assert set(t.getnames()) == set(meta['members'])
        for member in t:
            b = t.extractfile(member).read()
            expected = meta['members'][member.name]
            assert len(b) == expected['bytes'] and hashlib.sha256(b).hexdigest() == expected['sha256']
print('archive bytes verified; findings remain OPEN')
PY
```

外部清单的字节校验与生产 standalone 核验是不同层：前者能识别本次副本改动；本轮发现的是后者对来源和冻结规则的漏检，未声称能绕过受信 Git 对完整原件的外部锚定。
