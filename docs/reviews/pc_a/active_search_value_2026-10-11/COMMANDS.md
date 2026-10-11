# 复现

分支`codex/pc-a-active-search-value-20261011`；base为PR107 `20f2a1f38125eb5ce973f48238f17d02c38286de`。独立工作目录/环境，不复用另一电脑的虚拟环境或`.git`指针。

- 推断、runner与18项新增测试：`a8e98dc3a243467b52c62672e1f3ef9c4439e540`。
- 留出前开发冻结/独立评分：`db1942027529984c2a27a6cbae7b1ef7c7a14f48`。
- 独立篡改/重复检查：`170ece8e5e715d045a4e52df990c6147b074df8e`。
- 描述性汇总：`d7a6fb58e80264f7e79911db036887841327ab77`；归档验证：`90e942bde6d20e3057222175b4e8f168f556d1cd`。

本机Python3.13.5，现有环境`/private/tmp/cpswm-object-reid-venv/bin/python`；跨机器按项目依赖重新安装，以`source.json`文件散列核对，不以文件夹名称代替来源。

```bash
export PYTHONPATH=src:tools
python -m pytest -q tests/test_active_location_search.py tests/test_task_readout_repair.py tests/test_full_mechanism_value_diagnostic.py tests/test_structure_two_stateful_full_joint.py tests/test_structure_two_stateful_full_joint_adversarial.py
python tools/run_active_location_search.py --phase dev --condition sparse32 --output /tmp/active-main/dev-sparse32
python tools/score_active_location_search.py /tmp/active-main/dev-sparse32 --output /tmp/active-main/dev-sparse32-score.json
```

源代码/配置冻结后，下面三个condition可作为独立进程运行；默认留出seeds62001–62010，无测试集策略选择。

```bash
python tools/run_active_location_search.py --phase test --condition complete32 --output /tmp/active-main/test-complete32
python tools/run_active_location_search.py --phase test --condition sparse32 --output /tmp/active-main/test-sparse32
python tools/run_active_location_search.py --phase test --condition long64 --output /tmp/active-main/test-long64
python tools/score_active_location_search.py /tmp/active-main/test-complete32 --output /tmp/active-main/test-complete32-score.json
python tools/score_active_location_search.py /tmp/active-main/test-sparse32 --output /tmp/active-main/test-sparse32-score.json
python tools/score_active_location_search.py /tmp/active-main/test-long64 --output /tmp/active-main/test-long64-score.json
python tools/run_active_location_search.py --phase test --condition sparse32 --seeds 62001 --output /tmp/active-repeat/sparse32
python tools/check_active_search_artifacts.py /tmp/active-main/test-sparse32 --repeat /tmp/active-repeat/sparse32 --output /tmp/active-main/artifact-checks.json
python tools/summarize_active_search_value.py /tmp/active-main --output /tmp/active-main/combined.json
```

独立评分、篡改/重复比较与汇总只使用标准库，不加载模型推断；它们仍属于A本机核对，不能标记B独立设备验收。主归档含开发与全部留出原件、独立评分；重复归档保留另进程的完整原件。归档成员hash和解压后重评分回执见MANIFEST/ARCHIVE_VERIFY。

归档及解压复核（要求输出目录不存在）：

```bash
python tools/package_active_search_evidence.py --main /tmp/active-main --repeat /tmp/active-repeat --output /tmp/active-evidence
```

输出的4份评分重算要求序列化JSON字节相同，其余篡改/重复检查和总汇总要求解析后对象完全相同。`PROVENANCE.json`另记录源码/工具SHA、测试命令和远端交接SHA。
