# 运行与复核命令

独立目录：`.local/simulation-stack/cpswm-reliability`。core Python 3.13环境和锁文件沿用PR127；解释器、依赖版本和uv.lock hash见evidence/reliability-environment.json。以下为本轮实际命令；复跑必须选择新输出目录，不覆盖现有证据。

## 冻结源码运行

首个串行与前缀使用42db7931ed9bda42ba2758efe39abe96c94e8e03；前缀exit0。串行因调度优化中断，exit130，109个完整记录保留。这个中断不是模型/样本选择或完整成功运行。

```sh
PYTHONPATH=src:tools ../envs/core/bin/python tools/run_reliability_replication.py --output ../runs/reliability-fresh01
PYTHONPATH=src:tools ../envs/core/bin/python tools/run_reliability_replication.py --prefix-only --output ../runs/reliability-prefix01
```

a5f3b024f23f870753b8f8ac78da18def04e4f47四进程完整运行exit0，18轨迹768时点。并行仅按轨迹，全部生产src与PR127相同。与串行开发夹具2步、前缀36步、保留串行109步（两类共137唯一时点）全部记录除计时一致。

```sh
PYTHONPATH=src:tools ../envs/core/bin/python tools/run_reliability_replication.py --workers 4 --output ../runs/reliability-fresh02
PYTHONPATH=src:tools ../envs/core/bin/python tools/analyze_reliability_replication.py ../runs/reliability-fresh02 --output ../runs/reliability-analysis01
```

完整运行source.json绑定750文件；结束再次确认源文件内容未变。所有方法同时计算并提交动作后才访问评估真值；没有主模型参数修改。

## 独立来源和完整伪造检查

下面核验器对应2ea1e97b7f0848569186cd72a3246e71af1bb4e5。它从冻结生成器重新生成所有输入/真值，逐项重算每个三类RB与最终混合，独立累计错误和配对得失，并对照另进程状态记录。

```sh
PYTHONPATH=src:tools ../envs/core/bin/python tools/verify_reliability_evidence.py ../runs/reliability-fresh02 --analysis ../runs/reliability-analysis01 --prefix ../runs/reliability-prefix01 --interrupted ../runs/reliability-fresh01
```

不要把包含全部来源核验的算术检查写成全768状态的第二次重跑；完整状态只复跑了报告明确列出的子集。B独立复核未完成。

## 测试

```sh
PYTHONPATH=src:tools ../envs/core/bin/python -m pytest -o addopts='' -q tests/test_reliability_replication.py tests/test_memory_action.py tests/test_memory_goal_control.py tests/test_current_event.py tests/test_current_event_adversarial.py tests/test_synergy_missing_regime.py tests/test_five_stage_synergy.py
PYTHONPATH=src:tools ../envs/core/bin/python -m pytest -o addopts='' -q tests/test_reliability_replication.py
../envs/core/bin/ruff check tools/run_reliability_replication.py tools/analyze_reliability_replication.py tools/verify_reliability_evidence.py tests/test_reliability_replication.py
../envs/core/bin/ruff format --check tools/run_reliability_replication.py tools/analyze_reliability_replication.py tools/verify_reliability_evidence.py tests/test_reliability_replication.py
```

第一条在a5f运行为74 passed；第二条新增来源核验后为6 passed（4项重叠、2项新增）。动作和统计一起伪造并重算自签hash仍被拒绝；输入变造后局部算术可自洽，但真实来源重生成/前缀重跑拒绝；错误汇总不能替换原始净收益计数。

## 数据与诊断

- evidence/summary.json：所有六臂错误、搜索评分成本、配对得失、六seed分组区间、分条件/分阶段结果。
- evidence/diagnostic_limits.json：概率下限1e−300、零真值概率次数、置信度≥0.8错误、损害的当前人物和cell诊断。源数据为analysis档案中的audit_points.json。
- evidence/reliability-known-diagnostic.json：只读重算PR127已见768点；不与新数据合成未见结果。
- 四档案保留完整主数据、另进程前缀、中断数据和分析产物；merged流已包含18分片全部未压缩记录，重复的worker分片留在本地，交付记录其hash和合并校验。

## 全部交付文件回读

```sh
../envs/core/bin/python - <<'PYCODE'
import json,hashlib,tarfile
from pathlib import Path
root=Path('docs/reviews/pc_a/reliability_net_benefit_2026-10-25')
m=json.loads((root/'MANIFEST.json').read_text())
for name,e in m['files'].items():
    b=(root/'evidence'/name).read_bytes()
    assert len(b)==e['bytes'] and hashlib.sha256(b).hexdigest()==e['sha256']
for name,e in m['archives'].items():
    path=root/'evidence'/name
    assert hashlib.sha256(path.read_bytes()).hexdigest()==e['sha256']
    with tarfile.open(path) as archive:
        assert set(archive.getnames())==set(e['members'])
        for member in archive.getmembers():
            b=archive.extractfile(member).read(); expected=e['members'][member.name]
            assert len(b)==expected['bytes'] and hashlib.sha256(b).hexdigest()==expected['sha256']
print('all delivery evidence verified')
PYCODE
```
