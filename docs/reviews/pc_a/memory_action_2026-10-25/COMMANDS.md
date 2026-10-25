# 复现与检查

工作树：`.local/simulation-stack/cpswm-memory-action`；下列命令从此目录执行。`../envs/core` 为锁定的核心 Python 3.13 环境，`../envs/libero` 为实际 Torch/JAX/LIBERO Python 3.11 环境。依赖和模型准备沿用 PR126 仿真栈；提交不包含官方模型权重。新运行必须另选未使用的输出目录。查看结果前先核对 REPORT 中各阶段实际源码 SHA。

## 最终源代码检查（7a26b5eeedef2427f957bd41bc917b9806736031）

```sh
PYTHONPATH=src:tools ../envs/core/bin/python -m pytest -o addopts='' -q tests/test_memory_action.py tests/test_memory_goal_control.py tests/test_current_event.py tests/test_current_event_adversarial.py tests/test_synergy_missing_regime.py tests/test_five_stage_synergy.py
PYTHONPATH=src:tools ../envs/libero/bin/python -m pytest -q tests/test_fast_memory.py
PYTHONPATH=src:tools ../envs/core/bin/python -m mypy --follow-imports=silent src/cpswm/system/evaluation_operations/structure_two_memory_action.py src/cpswm/simulation/goal_control.py
PYTHONPATH=src:tools ../envs/core/bin/python -m mypy --follow-imports=silent --python-executable ../envs/libero/bin/python src/cpswm/simulation/fast_memory.py
```

第一条 70 passed；快速记忆 3 项。历史 d636 的另一组 72 项定向检查日志也保存，但不与最终套件相加。Ruff 对 base 至本轮全部 12 个 Python 变更文件执行 check 和 format --check，通过。

## 开发配对实验

原始运行在干净的 531b3ca 源码；命令如下，完整运行约半小时（取决于机器），不是 quick 模式。

```sh
PYTHONPATH=src:tools ../envs/core/bin/python tools/run_memory_action.py --output ../runs/memory-action-full01
PYTHONPATH=src:tools ../envs/core/bin/python tools/verify_memory_action_results.py ../runs/memory-action-full01 --output ../runs/memory-action-verification.json
```

核验器是最终 7a26 源码；它对源 manifest 的 SHA 读取 Git blob，重算读出及配对统计。后来的实际内容版本绑定只改变证据/命令版本语义，不把旧阶段完整运行标成新版本运行。

## 真实执行与物理反例

```sh
# 在 6e67 源码运行的完整任务
../envs/libero/bin/python tools/simulation_python.py tools/run_native_pi05_probe.py --policy pi05-local --steps 220 --output ../runs/native-memory-pi05-01
# 在 d636 源码运行的绑定修复短程
../envs/libero/bin/python tools/simulation_python.py tools/run_native_pi05_probe.py --policy pi05-local --steps 10 --output ../runs/native-memory-pi05-final10
# 当前核心和物理核验
PYTHONPATH=src:tools ../envs/core/bin/python tools/verify_native_pi05_probe.py ../runs/native-memory-pi05-final10 --output ../runs/native-memory-pi05-final10-core.json
../envs/libero/bin/python tools/simulation_python.py tools/verify_native_pi05_probe.py ../runs/native-memory-pi05-final10 --physics --output ../runs/native-memory-pi05-final10-physics.json
../envs/libero/bin/python tools/simulation_python.py tools/verify_native_pi05_probe.py ../runs/native-memory-pi05-01 --physics --output ../runs/native-memory-pi05-01-physics.json
../envs/libero/bin/python tools/simulation_python.py tools/audit_native_physics_forgery.py ../runs/native-memory-pi05-final10 --output ../runs/native-memory-physical-negative.json
```

图形/物理环境需要相应系统执行权限。完整旧任务的核心重放必须使用旧版本 native_goal_worker/runtime；本轮实际创建 `/private/tmp/cpswm-memory-action-6e67` detached worktree，命令如下。不要用新 revision 规则要求旧日志逐字一致。

```sh
PYTHONPATH=/private/tmp/cpswm-memory-action-6e67/src:/private/tmp/cpswm-memory-action-6e67/tools:tools ../envs/core/bin/python - <<'PYCODE'
import json
from pathlib import Path
from verify_native_pi05_probe import verify_core
result = verify_core(Path('../runs/native-memory-pi05-01'))
result['runtime_sha'] = '6e67a78355b8c79c38dbbccbc04d4f5db4656397'
Path('../runs/native-memory-pi05-01-core.json').write_text(json.dumps(result, indent=2))
PYCODE
```

相同公开 D0 前缀的记忆内容诊断可按以下方式重算。它直接干预状态，禁止解读为观测证据或新机器人试验。

```sh
PYTHONPATH=src:tools ../envs/core/bin/python - <<'PYCODE'
from dataclasses import replace
from native_goal_worker import controller_for
for arm in ('native_joint', 'native_six_potential_ablation'):
    for mode in ('intact', 'reset', 'swapped'):
        controller, _ = controller_for(arm)
        for p in controller.memory.runtime.particles:
            if mode == 'reset':
                p.world.rb_cells.clear()
            elif mode == 'swapped':
                def swap(x):
                    return (x[1], x[0], *x[2:])
                for k, c in list(p.world.rb_cells.items()):
                    p.world.rb_cells[k] = replace(c, location_alpha=swap(c.location_alpha), ridge_precision=swap(c.ridge_precision), ridge_natural=swap(c.ridge_natural))
        d = controller.memory.destination_distribution()
        print(arm, mode, min(d, key=lambda x: (-d[x], x)))
PYCODE
```

## 快速记忆原型

```sh
PYTHONPATH=src:tools ../envs/libero/bin/python tools/train_fast_memory_probe.py --output ../runs/fast-memory-probe01
PYTHONPATH=src:tools ../envs/libero/bin/python tools/train_fast_memory_probe.py --output ../runs/fast-memory-probe02
```

第二次训练对应 6e67。两份结果和 13 组张量一致；后续类型标注不改变数学行为。这里没有 π0.5 训练命令：其内部记忆接口、兼容动作示范及完整训练尚未实现，不能用上述命令替代。

## 证据档案回读

`MANIFEST.json` 的 archives 为每个 tar.gz 整体和成员记录 SHA-256；files 记录旁置摘要/日志。原件均在 evidence 中。以下只回读内存，不解压或覆盖现有工作树。

```sh
../envs/core/bin/python - <<'PYCODE'
import hashlib, json, tarfile
from pathlib import Path
root = Path('docs/reviews/pc_a/memory_action_2026-10-25')
m = json.loads((root/'MANIFEST.json').read_text())
for name, expected in m['files'].items():
    b = (root/'evidence'/name).read_bytes()
    assert len(b) == expected['bytes'] and hashlib.sha256(b).hexdigest() == expected['sha256']
for name, expected in m['archives'].items():
    path = root/'evidence'/name
    assert hashlib.sha256(path.read_bytes()).hexdigest() == expected['sha256']
    with tarfile.open(path) as archive:
        assert set(archive.getnames()) == set(expected['members'])
        for item in archive.getmembers():
            b = archive.extractfile(item).read()
            e = expected['members'][item.name]
            assert len(b) == e['bytes'] and hashlib.sha256(b).hexdigest() == e['sha256']
print('all evidence verified')
PYCODE
```
