# f52271cf 重建与两轮作者对抗复测

2026-09-13。结论：**缺失资产静默跳过反例已关闭；有限矩阵通过，全面验收仍未通过。** 用户已明确授权本批仿真证据向指定 GitHub 仓库公开；没有公开原始许可日志、账号凭据或二进制程序。

## 版本与真实构建

- CPSWM 任务分支 `codex/pc-a-procthor-unity-build-20260913`，任务 base `ec2215ac7138c2b359d77219519e5628669c8b82`。本轮测试工具来自已公开提交 `253ade19297ca26f1f74431141d8dd50eef98e68`，运行前后源码摘要一致。
- 实际上游源码 `f52271cf6f1251f6ed31154a8373d89971d7d51e`，固定 upstream base `f0825767cd50d69f666c7f282e54abfe58f1e917`；不推送 AllenAI 上游。
- 在已授权且解锁的 Unity Editor 中刷新源码，通过 `CPSWM > Build Frozen Mac Development` 构建，Unity 2020.3.25f1，Succeeded / 0 errors / 26 warnings。警告边界沿用前报告，不能一概视为无害。
- 新输出目录 `cpswm-unity-gui-build-79d1f4998dbf4a3d8a89cb9120e26936`；实际 gameplay DLL SHA-256 为 `823575cc05afa25da8b8bd824ab3253deb80250727a03ffb36f98db778ac9b05`，与旧 a86468d6 程序不同。
- 构建前后各 19,478 项输入；源码 revision 与 git status 不变，唯一文件摘要变化是生成的 `unity/Assets/Resources/ResourceAssetCatalog.json`（311,181 bytes）。上游 BuildCatalog 会重新生成含当前 timestamp 的目录；这里只确认文件级变化范围，没有保存旧目录原文，不能声称已逐字段证明只变时间戳，也不声称位级可复现构建。

## 实际运行结果

| 复测 | 输出目录 | 结果 |
|---|---|---|
| 第一轮 | `cpswm-post-house-round1-20260913-02` | 6/6 场景通过 |
| 扩展第二轮 | `cpswm-post-house-round2-20260913-03` | 4/4 场景通过 |
| 普通场景双实体 guarded 回归 | `cpswm-unity-fixed-ordinary-2-20260913-01` | 通过，观测到 2 个实体，2.99 秒 |
| 输入快照工具单元检查 | `pytest tests/test_structure_two_unity_snapshot.py -q` | 9 passed；非运行时验收 |

第一轮检查真实建房后的 N=1/2/3/6、原始传输实体 ID、有限分离位置、RGB-D 数组、逐实体左右转向隔离、非法输入后合法恢复以及建房前拒绝。

第二轮检查连续状态机、缺失对象资产导致的部分建房失败、持物禁止复制、重复建房。具体包括幂等生成、改请求/人数/代次/调用者拒绝，主副实体重初始化拒绝，真实 reset 产生新代次并重新生成。

本次缺失资产链实际通过：真实 CreateHouse 返回失败 → Pass 返回 Episode discarded → reset 合法房屋 → 新 generation → 真实生成两个实体。旧 a864 的 `house_failure_reported` 失败原样保存在 evidence_01，没有用新结果覆盖。修复原因是上游 spawnHouseObject 原先在资产不存在时日志报错后返回 null，使外层错误地报告建房成功；现在抛异常交由 CreateHouse 捕获并废弃 episode。不是用手填失败回执或放宽断言关闭反例。

相邻调用静态检查：spawnHouseObject 还被 SpawnObjectInScene 使用，公开动作分发有 TargetInvocationException 捕获并返回失败；该相邻公开动作未专项实测，不升级为已验证。

## 证据与复跑

- `evidence_02/manifest.json`：17 项构建回执、完整 app 文件摘要、输入快照、两轮回执和原始传输档案；全部压缩前后摘要已核对。
- `evidence_03/`：普通双实体回归证据，单独保留，不改写 evidence_02。
- 两轮回执记录完整 argv、Python 版本、实际程序/游戏 DLL/房屋/测试工具摘要；运行前后一致。归档只保留选择性仿真证据，不包含 unity_logs。
- 实际运行工具为 `tools/structure_two_post_house_probe.py --binary <上述新 Player> --house docs/reviews/pc_a/proposal_scheduler_2026-09-13/procthor_run_07/train_house.json --output <全新目录> --round 1`，随后使用另一全新目录运行 `--round 2`。普通回归入口为 `tools/structure_two_multiagent_diagnose.py --scene ordinary --count 2 --guarded`，其余参数见原回执。
- `tools/unity/post_house_f52271cf_UNVERIFIED.patch` 文件名保留其历史状态，补丁内容未改；本报告和新证据将同一源码版本升级为本机有限矩阵已复测，不代表独立异机签收。

## 仍然未通过的门与下一步

1. 子实体已生成一部分后后续初始化失败的真实触发、全部出生点不足/复杂动态碰撞、异常寻址与全部相机/持物污染矩阵仍不完整。应追加公开输入下的合法对照和后果检查，不能只检查代码中的保护分支。
2. 电脑 B 尚未独立重建/复测此源码 SHA；交接为草稿 PR，不自动合并共享集成分支。B 可先验清单和补丁，真实执行仍需兼容环境。
3. 此路径生成的是默认 robot agent，不是人物。人物像素覆盖、检测、实例关联、角色证据和人物动作后端仍未成立。强制 PickupObject 仅为持物负例准备，禁止当作合法训练样本。
4. 完整提议模型、真实测量/噪声校准、连续历史监督、七算子与联合主干默认生产闭环仍未验收。没有训练、没有改科研路线或计算预算。

下一推进顺序仍为物理多实体余下矩阵 → 人物可见执行和观测证据 → 连续历史推导监督与账本修订 → 数据门/参数/预算明确后训练。此次有限运行成功不越过这些门。
