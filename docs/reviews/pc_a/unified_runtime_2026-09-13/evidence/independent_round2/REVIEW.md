# 第二轮独立审核

固定候选：`fd516c33532a3fb61a978d0a0c0bd403a3f3794a`。审核者独立执行，未改生产源码、测试、工具或 HEAD。本轮结论：**CHANGES_REQUIRED（需要修复）**；不签统一运行或科学收益。

## P1：Git 替换引用突破完整 SHA 的来源绑定

位置：`tools/structure_two_rgbd_ingress_replay.py:31-38`。

工具通过完整 commit SHA 读取归档，但 `git cat-file` 和 `git show` 均默认遵从 `refs/replace`。在完整合法归档仓库中建立两捕获 commit A，再提交只保留一捕获的 commit B，执行 `git replace A B`。以 `--source-sha A` 运行工具，退出 0，最终回执继续声明 source_sha=A，实际却输出 B 的一捕获、两观测。用 `git --no-replace-objects show A:.../release_journal.json` 可确认 A 本体有两捕获。因此回执不能按声称的 SHA 重建输入，破坏本次新增功能的核心来源保证。正常克隆不会自动取得 replace refs，但工具接受本地任意 source-root；残留/恶意替换引用无需修改 A，就足以触发此问题。

复现：候选 `.venv/bin/python /private/tmp/cpswm-unified-review2/probe.py`，在新证据目录运行时需改 O 或清除仅此探针生成的目录（脚本拒绝重复建目录）。完整输出 `results.json`，其中 git_replace 字段含 A、B、原日志、退出码及成功回执。原对象 `8e0f923d3b155bbb4757fe8ed222ba644de15bc2`，替换对象 `0639f0ec8ecd46bc2751e9aa9e1fa39d594a57e0`；完整仓库保留于 replacement/archive。

建议：所有对象类型和文件读取一律显式禁用 Git replace，例如每次 git 命令加入 `--no-replace-objects`。回归须同时包含替换引用存在时仍读取 A 本体的合法正路径，以及普通两捕获、迟到、重复身份和异常无成功回执路径。

## 独立执行结果

1. 新30项测试：`./.venv/bin/python -m pytest -q -o addopts= tests/test_structure_two_raw_rgbd_ingress.py tests/test_structure_two_rgbd_ingress_cli.py tests/test_structure_two_standalone_startup.py --junitxml=/private/tmp/cpswm-unified-review2/targeted.xml`，30 passed / 3.16 秒。这是有限覆盖，与上述新增来源反例同时成立。
2. 完整合法双捕获档案：迟到捕获零排在捕获一后，CLI退出0，2捕获/4观测/8文件；逐文件 SHA-256 均核对，四观测身份唯一。
3. 第一轮重复内部身份：CLI退出1，无成功回执，当前探针处理顺序在首个捕获处拒绝，没有观测文件。第一轮覆盖缺陷在本轮固定候选上关闭。
4. 先处理合法捕获、后遇伪造 sensor hash：退出1，无 receipt.json，已写2个观测JSON及对应像素仍残留。这不构成该工具所声明的成功；下游必须以完整回执为提交边界，不能扫描 observations 目录就消费。当前没有实时目录消费者，本轮不另立已证实缺陷。
5. 完整 Git replace 伪造：退出0、成功回执存在、来源SHA与实际输入不符，见 P1。

## 协作及其他新增代码

- 对比共享 `bdec3ee21b7db361e390496d97ff2eb30390dc6c`，START_HERE.md、TASK_BOARD.md 无差异，入口补齐正确。
- 新 A 状态保留旧 A 历史，B 状态含已完成修复及未关闭Windows结果；原共享 A/B 状态副本存在 component_snapshots。未重新联网核验分支，不能由本轮读本地仓库推断最新远端。
- 只读检查原始适配器、lazy exports、检查记录器。未在这些文件额外确认实质缺陷。检查记录器只是前后文件快照，不能替代独立测试进程/缓存/瞬时修改来源证明；W1仍须单独运行。

## 用户完整目标评估

**未达到“来源明确、真实输入驱动、能连续修订并影响行动的统一运行版本”。** 本批实现是归档原始 RGB-D 到 M05 的输入边界和生产首次导入修复。本轮还发现该归档来源绑定需要修复。CLI明确标注 new_simulator_run=false、semantic_detector_verified=false、default_joint_runtime_verified=false，与实现一致。

未交付或未验收的关键链：真实人物/语义检测及标定；真实历史原生六操作监督；全轴神经提议模型；经明确物理语义和残差校准的信息块；同一默认运行内 q→联合粒子→三个条件块→唯一账本→行动→实际反馈，以及迟到纠正撤回与重算。实现中没有把这个原始适配CLI接入上述完整生产闭环。保留整个框架和未决选择，不能把归档图像可读取或30测试通过替换为完成。

本轮未运行完整1170、85W1、Windows、Unity新场景或W2重算消费者矩阵；未进行全仓库所有正向授权路径/状态机/瞬时篡改审核。即使修复本报告P1，结论上限仍是本次新增边界的有限独立审核，不是最终完整运行验收。用户所要求最终完成后的两轮独立审核仍应绑定最终完整产物执行。
