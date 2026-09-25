# 固定源码与 B 复跑入口

A 本机审核不等于 B 复核。本次固定 SHA：首轮 `cf5f1f873681772574d18c1787c73cb121ae9db1`；修复二轮 `4a8bfdcc08f99660778283d1849b86ef17e767c6`；后续推理 `5936824c806b2c20b14220e33d89b15a9642ff3e`。在独立 checkout/工作树操作，不改共享集成。下载最新分支的报告后，按待复现轮次取对应 SHA，不能用最终代码冒充首轮基线。

```sh
git fetch origin --prune
uv sync --frozen --extra dev --extra perception --extra hand-perception
```

A 用 Python 3.13.5、macOS、CPU 两线程。B 自建环境，不复制 A 的 `.venv`。Windows 使用等效 Python 路径和环境变量。PyTorch/源码/线程绑定不同，已有推理快照会拒绝恢复，应在 B 自己的确切版本重新生成并报告差异。

## 两轮审核

首轮 5 个案例可将修复 SHA 中 `tests/test_joint_package_adversarial.py` 复制到独立的基线工作树测试；保持基线 `src/tools` 不变，选择下列测试：

```sh
OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 .venv/bin/python -m pytest -o addopts= -q tests/test_joint_package_adversarial.py -k 'fully_forged or hocap_package or preserves_version_counter or fully_rehashed'
```

预期在首轮基线 5 failed；在修复及最终版本均通过。完整伪造包含有效视频、力、姿态与自洽回执，不只是少字段的负例。

第二轮在 `4a8bfdc`：

```sh
OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 .venv/bin/python docs/reviews/pc_a/joint_audit_next_2026-09-25/run_checks.py output/review-round2 /absolute/path/input-spec.json /absolute/path/public-evidence
```

输出目录必须不存在。预期 391 passed、mypy 357、Ruff 通过，八命令全退出 0、源码前后相同。540 帧数据/spec 和公开辅助证据沿用 PR36 的已验证输入；见上一报告 [COMMANDS](../joint_training_loop_2026-09-25/COMMANDS.md) 与 [来源记录](../joint_training_loop_2026-09-25/PUBLIC_SOURCES.json)。本次新增固定来源登记表，新下载的作者元数据若变动，不要手改摘要过门：先记录差异、复核来源，再单独变更登记。

A 的现存输入在主仓 `output/joint-training-loop-20260925/input-spec.json` 与 `public-evidence/`。B 可按已有下载入口重取媒体；与实际固定登记字节不一致的元数据须使用本次原始包交接核对，不能将内生回执当外部来源认证。

## 后续推理接入验证

在 `5936824c806b2c20b14220e33d89b15a9642ff3e`，使用第二轮产生的训练目录；runner 不再训练：

```sh
OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 .venv/bin/python docs/reviews/pc_a/joint_audit_next_2026-09-25/run_next_checks.py output/review-final output/review-round2/training
```

最终预期 405 passed / 10 个既有 warnings、mypy 358、Ruff 通过；4 命令成功、源码前后相同。没有数据包也可先跑不依赖外部媒体的组件检查和夹具推理：

```sh
OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 .venv/bin/python -m pytest -o addopts= -q tests/test_joint_package_adversarial.py tests/test_proposal_inference_session.py tests/test_typed_proposal_training.py tests/test_native_joint_production.py
OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 .venv/bin/python tools/run_typed_proposal_development.py --output output/review-training --steps 4
OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 .venv/bin/python tools/run_checkpoint_proposal_inference.py --training output/review-training --output output/review-inference
```

三份检查点都要运行，不能按夹具损失选胜者。逐项核查每臂六类操作、总质量 1、修订替换效果仍保留、3 个历史请求及 5 个后续请求重放相同、重复请求随机数不变、两项写入授权为 false。读取 `final-manifest.json` 的实际命令/退出码与源码摘要，再对照当前 Git 对象，不只看 `all_checks_passed`。

完整伪造恢复测试主动重封外层摘要；改完整合法目标及其概率、概率值、随机位置、权限字段、重复记录仍须拒绝。请求重用更换上下文/支持、参数 `.data` 变更与消费随机数后的中断必须拒绝或原子回滚。

原生生产者负例必须保留账本/粒子不变；纠正重放应改变三解析块但仍拒绝未完成的 joint 发布。不得把旧的拒绝断言改成允许，来宣称训练网络已接全闭环。

B 将实际 HEAD、导入位置、环境、命令、源摘要、正路径后果和缺口记录到 STATUS_B；A 负责后续整合，不预先宣布 B 签收。
