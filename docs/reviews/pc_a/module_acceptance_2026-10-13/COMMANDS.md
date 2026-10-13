# 单入口模块验收与复现

本轮base `8805c4b9589caf24b6d55c6a567dbd11df636237`。这是模块执行验收，保留原`tools/structure_two_unified_acceptance.py`的全框架验收职责，不替代S1或独立设备验收。

## 1. 重建本工作树环境

旧临时解释器`/private/tmp/cpswm-object-reid-venv/bin/python`的`pyvenv.cfg`已不存在，`sys.prefix`落到基础Python，`python -m pytest`实际报“No module named pytest”。不能拿旧环境的历史安装记录当当前可运行证据。首次重建因uv缓存写权限失败；获得沙箱工具授权后按同命令离线重建成功。

```sh
uv sync --offline --frozen --extra dev --extra perception \
  --python /Users/pangwei/.local/share/uv/python/cpython-3.13.5-macos-aarch64-none/bin/python3.13
```

实际安装锁定的84个包。换机器时可使用可用的Python 3.13.5路径；若本地没有依赖缓存，去掉`--offline`从配置包源安装。`--frozen`仍保留。无需激活，直接用该工作树`.venv/bin/python`；验收器拒绝基础解释器回退和其它工作树导入。

## 2. 一次运行全部本轮检查

```sh
.venv/bin/python tools/run_module_acceptance.py \
  --output /private/tmp/cpswm-module-acceptance-final
```

输出目录必须不存在，防止复用历史成功记录；每阶段独立子进程、日志、退出码、JUnit/数据原件和散列留存。默认每阶段1200秒上限，超时终止该进程组并记录失败。实际原始控制台另保留为`console.log`。不要用`|| true`隐藏退出码。

- 退出1：运行失败、校验失败或源码变化。
- 退出2：模块检查完成但仍有跳过/未完成能力，本版本正常预期为`PARTIAL`。
- 退出0：保留给完整验收；当前已知缺口存在时绝不会返回0。

实际联跑用固定验证seed7、sparse32的32步，联合/因子化各有与无新证据四臂，共128步。仍使用冻结v06、24粒子和修复后的采样。然后两个原生臂分别执行control/withdraw/restore的7步独立前缀，共42步。它们是新的实际执行，但复用开发案例，不是新独立留出或自然世界实验。

## 3. 独立复核与归档

```sh
PYTHONPATH=src:tools:tests .venv/bin/python tools/verify_module_acceptance.py \
  /private/tmp/cpswm-module-acceptance-final \
  --output /private/tmp/cpswm-module-acceptance-verified.json
.venv/bin/ruff check tools/run_module_acceptance.py tools/verify_module_acceptance.py \
  tests/test_module_acceptance.py tests/test_structure_two_backbone_operator_wiring.py
```

复核检查原件集合、散列、阶段顺序、真实JUnit节点、状态和退出码；重算四臂位置似然/重要性权重/采样及RB读出；核对撤回恢复续跑。源码清单绑定执行时的源文件，不把最终报告提交SHA冒称执行SHA。此验证不是恶意进程隔离，也不认证D0人物来源是真实自然观测。

交付`evidence/raw-final.tar.gz`含完整验收目录，`ARCHIVE_MANIFEST.json`记录成员和档案SHA。解压到新目录后，把上述复核命令的第一个参数改成该目录，可重新验证。结果报告不写入被验证目录内部，以免改变原件集合。

## 4. 基线失败与修复

原61项基线实际58通过/3失败，均为旧测试期待presence-only CIAV改变人物归因。保留`baseline/rebuilt.log.gz`及XML压缩原件；原始行尾空白不清洗，解压散列见baseline清单。修复后增加显式合成actor来源的正路径，并保留无人物来源的中性对照；原有八/七回执、无长期提交、动作阈值跨越等断言保持。相关35项补测通过，最终矩阵再次执行。显式来源只是D0测试承诺，不是自然人物校准或来源真实性认证。

编写验收器期间修正了审计原件目录层级及Ruff格式问题；最终执行前已冻结工具和测试提交。没有为了通过改变生产似然或动作权重。
