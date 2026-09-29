# 本窗口复核命令与覆盖

实际运行根为 `/private/tmp/cpswm-pc-a-independent-route-audit-20260929`，冻结对象 `e80ddab4f4f792a372c1410862b071f79aebdb64`。本窗口提交只改审核/状态资料，没有改 `src/tests/tools/pyproject.toml/uv.lock`。解释器复用 `/private/tmp/cpswm-pc-a-sim-method-audit-20260929/.venv/bin/python`，通过 `PYTHONPATH=src:tests:tools` 加载本审核工作树代码。它不是独立依赖环境；迁移机器需按锁文件重建并准备感知依赖、模型与原件，不复制该虚拟环境。

以下路径变量须按本机资源设置，不能将缺失工件当作测试通过：

```sh
export PYTHONPATH=src:tests:tools
export PYTHONHASHSEED=0 OMP_NUM_THREADS=2 MKL_NUM_THREADS=2
export CPSWM_REPETITION_FIXTURE=/Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/output/sim-reliability-20260929/repeatability-attempt01/fixture
export CPSWM_CHECKPOINTS=/private/tmp/cpswm-pc-a-independent-route-audit-20260929/docs/reviews/pc_a/neural_native_loop_2026-09-29/evidence/development-checkpoints
export CPSWM_SSDLITE_WEIGHTS=/Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/output/models/torchvision/ssdlite320_mobilenet_v3_large_coco-a79551df.pth
export CPSWM_FASTERRCNN_WEIGHTS=/Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/output/models/torchvision/fasterrcnn_resnet50_fpn_v2_coco-dd69338a.pth
```

为简洁，下文的 `python` 指上面已说明的锁定解释器；输出位置为 `docs/reviews/pc_a/independent_route_audit_2026-09-29/evidence/`。

| 执行 | 返回与文件 | 边界 |
|---|---|---|
| 首批 pytest | 50 passed / 5 setup errors，exit 1，pytest.log/xml | 本窗口误填 `CPSWM_REPEATABILITY_FIXTURE`，实际程序要求 `CPSWM_REPETITION_FIXTURE`；5项不计通过 |
| 更正参数后的补测 | 46 passed / 0 skipped，exit 0，pytest_followup.log/xml | 包含5个实际图像工件节点及41个策略识别节点；与首批50个通过节点共96个不同节点 |
| recompute.py.txt | exit 0，recompute.log、fresh_inference.json | 全部16格128帧，两模型256次推理，395.20秒；源码图前后相同 |
| readbacks.py.txt | exit 0，readbacks.log | 2072归档、1920历史动作/真值、VISOR逐帧算术；不重新训练 |
| policy matrix run | exit 0，policy-matrix.log/result.json | 三实际权重、24受控组合，非Unity；结果与历史限制一致 |
| ruff format --check src tests | exit 1，ruff-format.log | 两个格式文件复现失败；未自动修复 |
| gh run/pr read | exit 0，ci-identity.json、pr57.json、ci-failed.log | 网络受限首次失败后获准只读访问；CI失败状态经远端核对 |

另一次本窗口自写重算脚本在执行前因末尾多一个括号触发 SyntaxError，未读取或改写实验数据；更正后从头完整执行成功。原记录保留在 `recompute_setup_failure.log`，不将其计为产品缺陷。

首批命令：

```sh
python -m pytest -o addopts= -q \
  tests/test_native_neural_production.py \
  tests/test_native_neural_recovery.py \
  tests/test_neural_pixel_camera_loop.py \
  tests/test_neural_camera_comparison.py \
  tests/test_simulator_repeatability.py \
  tests/test_simulator_repeatability_artifacts.py \
  --junitxml docs/reviews/pc_a/independent_route_audit_2026-09-29/evidence/pytest.xml
```

实际首批使用了错误的夹具环境变量名，上述正确环境可直接复跑全部；本次保留失败运行后只补跑受阻节点和新增识别检查，不重复跑已经通过的50项。

补测命令：

```sh
python -m pytest -o addopts= -q \
  tests/test_simulator_repeatability_artifacts.py \
  tests/test_camera_policy_identifiability.py \
  tests/test_camera_policy_identifiability_artifacts.py \
  --junitxml docs/reviews/pc_a/independent_route_audit_2026-09-29/evidence/pytest_followup.xml
```

新重算命令（脚本内显式列出原件目录，迁移时先核对完整原件和路径）：

```sh
python -u docs/reviews/pc_a/independent_route_audit_2026-09-29/evidence/recompute.py.txt
python docs/reviews/pc_a/independent_route_audit_2026-09-29/evidence/readbacks.py.txt
python -u tools/run_camera_policy_identifiability.py run \
  --output /Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/output/independent-route-audit-20260929/policy-matrix \
  --checkpoints "$CPSWM_CHECKPOINTS"
```

`run` 要求新的输出目录，不覆盖已有工件。完整24组SQLite等原件位于上面主仓 output；Git保存全量结果JSON及执行日志。原128帧核验代码只读原目录，不运行会改写原 `verification.json` 的原CLI。公开图像复推沿用原前端，原始掩膜和保存预测的统计独立重写；账本/合法正路径和伪造路径复跑沿用现有针对性测试，没有把同一测试两次运行算作双倍覆盖。

本轮未进行全量 pytest、自然训练、当前模型历史60-episode重放、新Unity采集或跨机器确认。CI的测试失败节点因超时未有最终异常汇总，需要实现窗口补充失败诊断，不能从本地96项测试推断完整回归通过。
