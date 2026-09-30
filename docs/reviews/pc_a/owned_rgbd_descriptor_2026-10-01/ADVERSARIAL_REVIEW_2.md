# R2：当前 owner RGB-D 描述的独立有界复核

**结论：在固定 owner journal 的明确边界内 PASS，未发现新的产品阻断。** 本接口仅支持 canonical `controlled-position-raw@1` 当前 Native base 上的首个 modeled command；描述无 posterior update、无 consumption authority，不是历史物理执行认证或下一轮 raw target-update 事务。较小的一致 raw/delivery/receipt 子图改写就能得到新描述，不能将源码 docstring 的 “entire journal” 解读成只要未改整个目录就已受独立认证。

审查绑定工作树 `/private/tmp/cpswm-pc-a-owned-rgbd-descriptor-20261001`，冻结 SHA `6faa17e178ad001de6b5c0e1094f9e62568d7a7e`，903 个 Python 文件。各执行前后和最终核对 HEAD/map 一致、git clean。未编写或修改生产源码/作者测试；此前参与只读准备和上游诊断，仍为 A 辅助审查，非电脑 B 或统一科学验收。

顺序前提已验证：R1 报告 SHA256 `99389e2ead8124a092d26e04784d6f1213160abbf7253a250736f0761797d91c`，R1 manifest `e34f271ea797978a82abdb12212a17185336c5db1bae0e619a899bbbbe33bfad`，121 件文件、外部锚和符号链接前后复核。根任务另行确认远端 child/integration/B 未变；本报告直接绑定上述本地冻结源码。

## 本轮实际结果

**4 项独立测试通过，19.61 s；另 1 项 harness 诊断通过，6.86 s，分开计数。** 不把 R1 的 82 项或失败 attempt 中的重复通过算入本轮四项。

实际入口：

```text
/private/tmp/cpswm-pc-a-camera-checkpoint-fixture-20260930/.venv/bin/python DO/R2/run_review.py 02
/private/tmp/cpswm-pc-a-camera-checkpoint-fixture-20260930/.venv/bin/python DO/R2/run_review.py diagnosis
```

`DO=/Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/output/owned-rgbd-descriptor-20261001`。runner 在冻结工作树执行 pytest，显式 `-c <DW>/pyproject.toml -o addopts= -q`，`PYTHONPATH=DW/src:DW/tests:DW/tools`、`OPENBLAS_NUM_THREADS=1`、`PYTHONDONTWRITEBYTECODE=1`。外层 timeout 300 s，fresh 子进程 timeout 180 s；无超时。完整 argv/cwd/environment、前后源 map、日志摘要和退出码见 `R2/independent-02.json`、`independent-diagnosis.json`；所有新输出仅在 R2，旧父 BO/SO 与 R1 不写入。

### 1. 完整有限 log 支持与实际 source 映射

从真实 owner/planner prepare→execute→accept 获得一次受控 RGB-D delivery。独立沿当前 accepted input body 的 neural base、`current_posterior_projection_source` 和 core 原 input anchor，核对 descriptor 的 source ID/body、cluster 和 parent input。

用 **90 位 Decimal** 从 accepted receipts 的 `exact_log_weight` 和 aggregate 原项重新做 log-normalization，不调用 helper 的归一化方法作为期望值。两条 accepted 粒子完整保留；其中 known 显示概率为 0，normalized log 为 `-2456.633927596179`，另一粒子与 aggregate 各 `-0.6931471805599453`，与 descriptor 在 `1e-12` 内一致。

把隐藏 log 加 1，保留全部支持、有限类型和展示零，再重签 descriptor 的 previous-weight/input 声明及内容摘要。原 owner 不变时 fresh rebuild 拒绝完整错误描述；原描述随后通过。raw/命令/status/origin、Native/ledger/producer、完整 core/P5、DB checkpoint/字节全部相同，相机调用保持 1。

### 2. 两个合法 capture 的完整移植和实际后续动作

建立两个独立 owner，各通过真实 API 执行一次合法受控 capture，两个 descriptor 本身均合法。向第一个 owner 提交三种完整自签派生替换：另一描述仅改 action ID；另一 capture 的 members/camera/delivery/time；另一 owner 的 source/parent/log-support 全组。三者均在实际 action-only 原件重建后以 `descriptor differs from fresh original owner` 拒绝，原描述恢复通过，core/P5/DB 无变化。

随后第一个 owner 真实签发并执行第二次 camera-feedback-prior command，camera executor 恰好执行一次；其描述以 `only the unchanged native-base decision is supported` 拒绝，第一次 capture 在 base 未变时仍可描述。再通过原 `advance` 真正发布下一 neutral Native batch，第一次描述转为 stale 并拒绝。没有手动制造 READY 或修改 UUID 来满足来源检查。这里验证的是现有状态机后果，不是位置收益。

### 3. 较小 owner 子图一致改写：明确接受边界

保留原 command 与 native origin，先仅修改新 capture 的 raw：拒绝，因为与原 delivery 不一致。再一致修改对应 delivery/receipt，使原 RGB-D 包变为 yaw `41°`、depth `7 m`，helper **接受并描述新日志内容**。parent input/log weights 不变，`posterior_updated=False`、`consumption_authority=False`，helper 本身不改变 core/P5 或改后的目录；旧描述相对新日志被拒绝。

恢复原始对象引用与数据后，原描述再次通过，所有受测状态与 DB 字节相同，相机次数仍为 1。该接受实例不是被阻止的完整数据替换，也不证明原 capture 的历史字节；它展示目前没有独立接受时锚。未来如要将新观测消费为受保护 likelihood，必须另外完成接受锚、原子更新、重复消费与撤回/历史重放设计，本 helper 不能替代。

### 4. 真正 fresh resume、计算与无新增副作用

将 R1 同 SHA 的已保存 underflow SQLite/config/expected descriptor **复制到 R2**。新 Python 子进程没有先构造临时 owner，而是直接恢复原 checkpoint，使用原模型/producer/decoder 绑定；P5 builder 若被调用会显式失败。恢复后原 descriptor SHA `fe9f69561cea0b0be4d219c0419a559127f146e933416f38d40fe39932ef9c15` 逐字段一致。

没有替换函数、清空 cache 或人为预热。`sys.setprofile` 分阶段记录：cold-process resume 触发一次既有 `score_support` 和一次旧 producer/readout/condition；first 和 warm descriptor 调用各触发 3 次旧 producer/readout/condition。所有被读出/condition 的 action 都是旧 `00000000-0000-0000-0000-000000000385`，不是新 capture `e913448c-6f1f-42f2-a658-3789c9be1d22`。纯 helper 窗口没有 measurements、execute、save、persist 或 posterior publication；SQL trace 无调用/写入，完整 core（含 P5）序列化不变，复制的 DB 字节也不变。

因此不称“零推理”；恢复已自然验证/缓存旧 q，不能把后续 warm 结果推广成任意 cold helper 零计算。实际新观测没有进入位置更新或新 producer publication。

## 保留的失败与精确诊断

`independent-01` 为 2 passed / 1 failed，第四项因 maxfail 未执行。失败发生在测试把原 raw/status 各自 `deepcopy` 保存再恢复后，要求 owner StateCodec 字符串逐字节相同的断言；没有删除原脚本、日志或产物。`attempt01-harness/test_independent_r2.py` 保留原版本。

另从原版本生成只加诊断的 `diagnose_attempt01.py` 实际复现：descriptor 一致；raw/status 值、完整 decoded owner 值、Native workspace、ledger、producer、checkpoint 行、core/P5、DB 字节和 camera=1 都一致。唯一差值在 owner 序列化引用图：command/status 的 action UUID 原来共享 ref24，深复制 status 后分别为 ref24/ref35；节点 742→743，该 UUID 的节点重数 2→3。**不是 raw 对象本体原本共享，也不是验证 cache 或持久状态变化。** 两份完整 codec 和 `alias-graph-diagnosis.json` 均保留。

修正只让测试用浅复制字典保留原不可变值的引用，恢复对象图而不放宽断言；最终 `[state, core, DB]` 三分量与 state 的 8 子分量全部相同。诊断测试作为 1 项单列，不混入四项功能检查。另一次开始核对 R1 manifest 时，harness 将 `{bytes,sha256}` 条目误当哈希字符串，读取后即断言失败，未运行产品；修正解析并完整复核，记录在 `r1-before.json`。

## 覆盖与封存范围

本轮未重跑 R1 的 82 项、全部字段类型替换或全部 legacy/失败状态；未增加 Unity/真实采集、自然身份关联、target update、历史不可篡改证明、校准/任务收益或跨机器验收。cold-process restore 有实测，任意 cache 状态及并发交错未穷举。R2 是上述限定范围的 partial coverage，不扩大完整研究框架的完成声明。

`R2/final-check.json` 和 `R2/evidence-manifest.json` 绑定本报告、903 源码、R1 原封存及 R2 所有脚本/日志/失败尝试/复制数据库。可变 review-gate 和根任务未来 REPORT/交付文件不在不可变 manifest 内。封存后审核者停止写入，由根任务更新 gate 与推送。
