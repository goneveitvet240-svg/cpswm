# 复现入口

代码 `c642f4cfdde0359be762eaa15d9d7f2cd1b3b74d`。在此提交的独立工作树执行。以下环境路径是本次实际路径；其他机器应另建环境，并使用本目录两个 requirements 文件重建，不能复制 macOS 虚拟环境。

- Host Python 3.13.5：`/private/tmp/cpswm-object-reid-venv/bin/python`，通过 `PYTHONPATH=src:tools` 绑定本工作树，不修改原环境。
- Component Python 3.11.16：`/private/tmp/cpswm-external-object-env-20261010/bin/python`，真实 Open3D 0.19.0，独立临时环境。

```sh
PYTHONPATH=src:tools CPSWM_COMPONENT_PYTHON=/private/tmp/cpswm-external-object-env-20261010/bin/python \
  /private/tmp/cpswm-object-reid-venv/bin/python -m pytest tests/test_external_surface_pilot.py -q

PYTHONPATH=src:tools /private/tmp/cpswm-object-reid-venv/bin/python \
  tools/run_external_surface_pilot.py \
  docs/reviews/pc_a/matched_transition_death_test_2026-10-09/evidence/natural-30-5-5 \
  docs/reviews/pc_a/matched_transition_death_test_2026-10-09/evidence/manifest.json \
  /private/tmp/cpswm-external-object-results-20261010-a \
  --component-python /private/tmp/cpswm-external-object-env-20261010/bin/python
```

输出目录须为全新路径。四组 `current`、`cg_same_support`、`mask_readout`、`cg_mask_readout` 全部生成后，分别运行现有隔离评分器：

```sh
PYTHONPATH=src:tools /private/tmp/cpswm-object-reid-venv/bin/python \
  tools/run_matched_transition_death_test.py evaluate \
  docs/reviews/pc_a/matched_transition_death_test_2026-10-09/evidence/natural-30-5-5 \
  docs/reviews/pc_a/matched_transition_death_test_2026-10-09/evidence/manifest.json \
  /private/tmp/cpswm-external-object-results-20261010-a/current.json \
  docs/reviews/pc_a/matched_transition_death_test_2026-10-09/TARGETS.json \
  /private/tmp/cpswm-external-object-results-20261010-a/current-evaluation.json
```

将最后两个 `current` 替换为其他组名。第二遍改用只包含 `public` 的输入根目录及新输出目录，四组文件 SHA256 应与第一遍一致；runtime.json 含计时，因此不要求它逐字相等。[verification.json](evidence/verification.json) 保存四组重复结果、独立算术复算36行和旧 current 输出一致性。

主控脚本、适配器、worker、上游函数的 SHA256 及实际依赖版本记录在 runtime.json；本目录要求列表记录环境安装版本。输入完整性沿用原 manifest，不上传第二套原始 RGB-D 数据。
