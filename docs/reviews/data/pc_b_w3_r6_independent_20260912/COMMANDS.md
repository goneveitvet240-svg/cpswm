# 命令、退出码与日志映射

以下命令均从 `F:\庞惟\codex\cpswm-w3-r6-review` 运行，解释器为该独立工作树自己的 `.venv\Scripts\python.exe`。测试命令显式清空仓库 `addopts` 并禁用 pytest cache provider；日志文件是当次输出的未编辑副本。

## W3 R6 原始运行

### R6 新增边界组

```powershell
& '.venv\Scripts\python.exe' -m pytest -o addopts='' -q -p no:cacheprovider tests/test_structure_two_w3_round6_prepared_boundary.py
```

- 退出码：`0`
- 结果：`67 passed in 54.95s`
- 日志：`logs/round6-prepared-boundary.log`
- 日志 SHA-256：`B584980479DBE08C84217AB104FD8C15F0597281AC69D1EAAAF6214768C1DFB5`

### W3 七文件专项组

```powershell
& '.venv\Scripts\python.exe' -m pytest -o addopts='' -q -p no:cacheprovider `
  tests/test_structure_two_w3_native_bundle.py `
  tests/test_structure_two_w3_native_particles.py `
  tests/test_structure_two_w3_operator_acceptance.py `
  tests/test_structure_two_w3_revision_acceptance.py `
  tests/test_structure_two_w3_round5_boundaries.py `
  tests/test_structure_two_w3_round6_prepared_boundary.py `
  tests/test_structure_two_w3_supplement.py
```

- 退出码：`0`
- 结果：`306 passed, 10 warnings in 868.79s`
- 日志：`logs/w3-snapshot-tests.log`
- 日志 SHA-256：`BB2232EA8B337686984C4FA1BBAADC0BC0E698521A70E090A6FCCF848911D96E`

### affected 50

```powershell
& '.venv\Scripts\python.exe' -m pytest -o addopts='' -q -p no:cacheprovider -rfE `
  tests/test_structure_two_selected_method.py `
  tests/test_structure_two_particle_falsifier.py `
  tests/test_structure_two_neural_amortized.py `
  tests/test_structure_two_stateful_full_joint.py `
  tests/test_structure_two_stateful_full_joint_adversarial.py `
  tests/test_structure_two_task7_support_recovery.py
```

- 退出码：`1`
- 结果：`31 passed, 9 failed, 10 errors in 9.78s`
- 归因：7 个失败是默认 Windows checkout 的 CRLF 原始字节哈希不一致；其余 2 个失败和 10 个 setup error 与缺失神经模型工件有关。
- 日志：`logs/affected-group.log`
- 日志 SHA-256：`20FC21635750C0CDDD2AB530D0EF98BDF044AE23D62942E925B9DD5EFEA936E5`

### 五项独立反例（原始历史结果）

```powershell
& '.venv\Scripts\python.exe' -m pytest -o addopts='' -q -p no:cacheprovider tests/test_structure_two_w3_r6_pc_b_review.py
```

- 退出码：`1`
- 原始结果：`5 failed in 3.67s`
- 解释：五项都写成“公开边界应拒绝”；实际均未抛出，因此 pytest 失败并确认五个 open finding。
- 原始日志：`logs/independent-adversarial.log`
- 原始日志 SHA-256：`301F3D4F09BD4C6D207B9EB6BB5DDDD602C1F9C54D1D42CAFF84413590679858`

提交前另加入一个独立命名的合法 control。复核命令相同，结果和新日志单列，不覆盖上述 R6 原始结果。

### 早期单项探针

同一测试文件形成五项矩阵前，曾单独执行地点支持重绑定用例，退出码 `1`、`1 failed in 2.21s`。该日志仅保留演进历史，不作为最终五项矩阵：`logs/independent-support-rebind.log`，SHA-256 `1BE8AC998E968E10ED48BA6AE625F007B99FDA67B73D0D73C0EB9F171D636D8A`。

### 上一轮独立字段探针

上一轮 one-off 驱动的 JSON 输出原样保存为 `logs/previous-independent-probe.json`，SHA-256 `30DEE28C08CBC514B90F42E1D76C4F427314583B46FAC13CF7C817696D8D1CA1`。当时的临时 stdin 驱动源码未进入 Git，故本交接不把它冒充为可完全重放的测试；它只作为补充字段证据，正式可复现结论以已提交 pytest 文件为准。

## LF 对照

LF 对照工作树由同一 R6 SHA 以一次性 checkout 配置创建：

```powershell
git -c core.autocrlf=false worktree add --detach 'F:\庞惟\codex\cpswm-w3-r6-lf-control' 1bd513f51ab7e54a7290870a5f34b524254d55c6
```

在该工作树中执行：

```powershell
& '.venv\Scripts\python.exe' -m pytest -o addopts='' -q -p no:cacheprovider `
  tests/test_structure_two_selected_method.py `
  tests/test_structure_two_neural_amortized.py
```

- 退出码：`0`
- 结果：`15 passed in 5.02s`
- 日志：`logs/line-ending-control.log`
- 日志 SHA-256：`2A407CD7A90F525D64C384D66DB019AD1BC83F07E9FA29D4F7C8EBEFD1FDFA63`

一次性 `-c` 只控制创建 checkout 的转换，不写入共享 Git 配置；因此随后查询 effective config 仍会显示全局 `core.autocrlf=true`，而 `git ls-files --eol` 和实际 SHA-256 证明该对照工作树的受测文件保持 `w/lf`。

## 元数据与 W1 静态核对

```powershell
& 'docs/reviews/data/pc_b_w3_r6_independent_20260912/collect_metadata.ps1' *>&1 |
  Set-Content -Encoding utf8NoBOM 'docs/reviews/data/pc_b_w3_r6_independent_20260912/metadata.log'
```

- 退出码：`0`
- 输出：被测 SHA/tree、实际解释器和导入源、56 项 base+dev 环境、Git 配置来源、`.gitattributes` 状态、Windows/LF 两个工作树的 EOL 和字节 SHA、W1 五文件 delta 与缺失依赖闭包。

## 当前测试文件的定向复核

只运行一个合法 control 与原五项反例：

```powershell
& '.venv\Scripts\python.exe' -m pytest -o addopts='' -q -p no:cacheprovider tests/test_structure_two_w3_r6_pc_b_review.py
```

预期在 R6 得到 `1 passed, 5 failed`；五个失败仍逐项解释为预期拒绝未发生。该复核日志保存为 `logs/independent-adversarial-with-control.log`。

## 五项状态后果诊断

pytest 红灯在 `DID NOT RAISE` 处结束，不能单靠该栈追踪证明接受后的持久状态。因此另运行不改变生产代码的诊断记录器；它包含同一合法 control 和同五项输入，并在调用前后采集 workspace、input bodies、ledger head、semantic identity、运行支持与 marginal：

```powershell
& '.venv\Scripts\python.exe' `
  'docs/reviews/data/pc_b_w3_r6_independent_20260912/w3_five_case_observations.py' `
  > 'docs/reviews/data/pc_b_w3_r6_independent_20260912/logs/five-case-observations-r6.json'
```

- 退出码 `0` 只表示六个案例采集完成，不代表五项边界通过。
- 正式判断依据是每项 `call.status`、before/after 和 `case_results.json`；输出 SHA-256 写入最终 manifest。
