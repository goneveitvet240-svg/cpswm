# CI 依赖隔离补充交付（2026-09-30）

本补充绑定测试修复源码 ac93f8d489209943cbcff9292ab483330538854b，base 00cc5a47cad988b453d5839b63fd7c6a89f4246d。实际四条历史和原始双审仍绑定 00283c607a5fb49c293cefe8eafd65cc2192f558；二者只有两个新增测试文件不同，其他 Python、pyproject.toml 和 uv.lock 逐项相同。后续仅补充文档及证据。原 326 文件实验包保持字节不变，没有拿测试修复后的版本冒称生成过原实验。

## 发现、修复与实际验证

CI 只安装 dev 依赖，视觉模块为可选依赖。两个新增测试先前会在缺 Torch 或未提供固定权重时错误收集/访问环境变量。本次仅隔离这些可选条件：缺模型依赖或权重时明确 skip（跳过）；带真实权重的验收仍要求零跳过。

缺权重问题修复前实际复现 2 failed / 1 passed；修复后 13 passed / 2 skipped。通过导入钩子模拟缺 Torch，两个测试模块在收集时跳过（此窄选择没有剩余测试，pytest exit 5），不是独立重建环境，也不是模型验收通过。初次提交钩子删去了不需要的 E402 抑制，当次未产生提交；修正后提交并重新冻结。

修复后的同一源码按顺序完整重跑两轮 A 局部对抗自审：第一轮 33 passed / 0 skipped，103.04 秒；第二轮 42 passed / 0 skipped，256.30 秒。两者均实际载入指定本机权重，源码摘要前后不变；6 个变更 Python 文件的 Ruff 和格式检查通过。覆盖范围沿用 [REVIEWS](REVIEWS.md)，不能把两次重复执行计成更多独立测试或 B 验收。

原命令、JUnit、日志、全源码映射、失败复现和依赖探针见 [补充证据](evidence/ci-followup/inventory.json) 与 [版本差异证明](evidence/ci-followup/provenance.json)。探针原脚本另存 .py.txt，防止交付文档本身改变 Python 源码集合。逐文件复制后读回一致。

## 远端 CI 尚未关闭

交付前核验 PR61 的旧 head 14f5709a5fd5cf3adc474a528f09e22e0ff23058：两个 static-quality 作业均失败，全量 test 当时仍运行中。已下载 [GitHub 作业日志](https://github.com/goneveitvet240-svg/cpswm/actions/runs/36593246800/job/109491498180)，失败为以下继承文件的格式检查：

- tests/dual_pc_review/test_w3_five_boundaries_repair.py
- tests/test_structure_two_ciav_negative_observation_layers.py

两文件与本轮 base 的 Git blob 完全一致；本地全 src/tests 格式检查复现同样两个失败。未修改 B 所有权文件或历史验收内容。局部 Ruff 通过不覆盖这个全仓失败，也不预先宣称新 head 的远端检查通过。

## 复现版本区分

重算封存实验必须使用原始 00283c607a5fb49c293cefe8eafd65cc2192f558 源码，原验证器对完整 Python 源码集合绑定，测试文件变化也会被正确拒绝。ac93f8d489209943cbcff9292ab483330538854b 是本次可选依赖修复及补充双审版本。没有改验证规则、改原件源码标签或重新打包实验以规避检查。生产/实验方法没有变化，因此未重复四条实际仿真；原结果、统计局限和下一主线判断保持。
