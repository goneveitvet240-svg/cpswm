# 复现

在本分析分支仓库根目录执行；工具只依赖Python标准库和同目录已有评分器。原推断来源清单505文件必须保持一致。实际本机解释器为 `/private/tmp/cpswm-object-reid-venv/bin/python`。以下示例不启动模拟器。

先从已归档证据按本报告输入清单提取50个成员，校验整个档案及每个成员的SHA256：

```bash
python3 - <<'PY'
import hashlib, json, tarfile
from pathlib import Path
old = Path('docs/reviews/pc_a/particle_support_repair_2026-10-12/evidence')
new = Path('docs/reviews/pc_a/joint_action_gap_analysis_2026-10-13/evidence')
manifest = json.loads((old / 'MANIFEST.json').read_text())['raw-main.tar.gz']
archive = old / 'raw-main.tar.gz'
assert hashlib.sha256(archive.read_bytes()).hexdigest() == manifest['sha256']
inputs = json.loads((new / 'inputs.json').read_text())['files']
dest = Path('/private/tmp/cpswm-joint-gap-archive')
with tarfile.open(archive) as tar:
    for name, sha in inputs.items():
        data = tar.extractfile('main/' + name).read()
        assert hashlib.sha256(data).hexdigest() == sha
        path = dest / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
print(len(inputs), 'members verified')
PY
python3 tools/analyze_joint_action_gap.py \
  --raw /private/tmp/cpswm-joint-gap-archive \
  --output /private/tmp/cpswm-joint-gap-recheck
```

核对三项输出与交付内容逐字节一致：

```bash
python3 - <<'PY'
import gzip
from pathlib import Path
expected = Path('docs/reviews/pc_a/joint_action_gap_analysis_2026-10-13/evidence')
actual = Path('/private/tmp/cpswm-joint-gap-recheck')
for name in ('summary.json', 'inputs.json'):
    assert (expected / name).read_bytes() == (actual / name).read_bytes()
assert gzip.decompress((expected / 'paired_steps.json.gz').read_bytes()) == (actual / 'paired_steps.json').read_bytes()
print('3 outputs byte identical')
PY
ruff check tools/analyze_joint_action_gap.py
ruff format --check tools/analyze_joint_action_gap.py
```

实际检查结果：32条既有运行、四臂1536步评分及采样验证通过；36864个粒子RB集合散列重建匹配；1536次最终动作概率重建误差全部为0；505来源文件匹配。直接读取运行目录与解压归档两次计算三项输出字节一致。本轮未新增模拟器试验或生产测试。

调试记录：最初按所有observation都有location_likelihood读取，遇到普通事件缺少该字段；改为无该字段时采用空映射。第一次按无前缀路径提取归档失败；核对真实成员后使用`main/`前缀，重新提取成功。Ruff首次导入块排序失败，修正后通过。以上均为本轮分析工具/复现脚本调试，不改变原推断或轨迹。
