# A 统一连续运行版本开工 2026-09-13

- 用户目标：来源明确、真实输入驱动、能连续修订并影响行动的统一运行版本，保留完整统一框架。
- 分支：`codex/pc-a-unified-runtime-20260913`；base/开工代码 `05836759cd96b89011efca71d3e9dc3ab393ce1b`；独立工作目录 `/private/tmp/cpswm-pc-a-unified-runtime-20260913`。
- fetch 成功；共享集成仍为 `bdec3ee21b7db361e390496d97ff2eb30390dc6c`；B 交付审核对象 `c366cad0a92593bb2c4c44db7e8d3408a2b5cc9c`。本分支是 A 集成候选，未替换共享集成分支，不改 B 分支。
- 本批先做 B 五项修复的源码审核与独立 Mac 复现，定位完整负载下锁 deadline；审过后才接入候选。随后接 W1/W2 与现有联合消费者、真实仿真输入，逐项记录未决模型/测量/人物证据绑定。
- 测试：开工尚未运行；不继承各分支总通过数，不宣称统一验收或科学收益。
- 证据计划：`docs/reviews/pc_a/unified_runtime_2026-09-13/`。有来源的真实输入、默认候选、三个条件块、完整后验行动和连续反馈逐项验收；不使用占位权重、手填后验、真值夹带或缩减范围过门。
- 必须保留的待决项：若网络参数化/预算、连续物理状态和标定模型、人物资产/后端、重采样等没有冻结程序可推导，列具体方案交用户；不因此停止不依赖这些选择的工程。

# 电脑 A 状态

## A 最新缺失资产修复重建及两轮复测完成 2026-09-13

- 本分支 `codex/pc-a-procthor-unity-build-20260913`，base `ec2215ac7138c2b359d77219519e5628669c8b82`；测试工具版本 `253ade19297ca26f1f74431141d8dd50eef98e68`，上游修复源码 `f52271cf6f1251f6ed31154a8373d89971d7d51e`。代码及证据已推送并 ls-remote 核验 `2a82f69c897078e1063572cc3b661103d2d1af80`。草稿交接 [PR #14](https://github.com/goneveitvet240-svg/cpswm/pull/14)，基线为本任务上一 A 分支，不自动合并；后续状态文字提交不改变此受测代码与证据身份。
- 新 Unity 构建 Succeeded / 0 errors / 26 warnings；实际 gameplay DLL `823575cc05afa25da8b8bd824ab3253deb80250727a03ffb36f98db778ac9b05`。两轮真实作者复测 6/6、4/4 通过，普通双实体回归通过；缺失资产失败/停止 episode/reset 恢复反例已关闭。输入快照工具 9 项检查通过。
- 新证据位于 `docs/reviews/pc_a/procthor_unity_build_2026-09-13/evidence_02/` 和 `evidence_03/`，报告 `REBUILD_F52271CF.md`；旧 3 passed / 1 failed 不覆盖。输入唯一变化为生成 ResourceAssetCatalog，不声称位级可复现。
- 仍为部分作者审核，待 B 独立复核；部分子实体失败/复杂碰撞等矩阵、人物像素及角色证据、真实连续监督和默认联合主干闭环仍未验收。没有训练、没有自动合并共享分支。下一步见报告，原始许可日志和二进制不公开。

## A 明确公开授权后交付并恢复重建 2026-09-13

- 用户已明确允许本批仿真证据、房屋对象记录及本机路径向指定 GitHub 仓库公开。已成功推送并通过 ls-remote 核验 `253ade19297ca26f1f74431141d8dd50eef98e68`；下方此前拒绝/仅本地记录属于历史状态，不再代表当前发布状态。
- 分支、base 和职责边界不变；集成 `bdec3ee21b7db361e390496d97ff2eb30390dc6c`、B `c366cad0a92593bb2c4c44db7e8d3408a2b5cc9c` 已 fetch 核验。
- Mac 已解锁，已刷新 Unity 源码，正在重建 `f52271cf6f1251f6ed31154a8373d89971d7d51e`。新程序和两轮复测尚未完成，缺陷暂不关闭。许可原始日志及程序二进制仍不公开。

## A 真实构建与两轮作者审核：最新修复待解锁重建 2026-09-13

- **本轮成果仅本地**：2026-09-13 公开推送被安全审核拒绝，要求用户明确确认约 20MB 仿真传输/房屋对象记录、摘要和本机路径可向 GitHub 公开发布。本轮实现/报告/证据未推送；远端仍只有此前恢复构建的开工登记。未绕过拒绝、未创建假交付 PR。
- 本分支 `codex/pc-a-procthor-unity-build-20260913`，任务 base `ec2215ac7138c2b359d77219519e5628669c8b82`。fetch 已验证 B `c366cad0a92593bb2c4c44db7e8d3408a2b5cc9c` 未变；不写 B 或共享集成分支。
- 授权生效；命令行第二次许可初始化失败记录保留。经已登录 Hub 成功打开固定项目并构建：基线 `bc2d0ed277b638c9986bd6ee7ba0be705d6f8783` 和多实体原型 `a86468d677639835e09c2b45d96c0d6eb7f76492` 均为 Succeeded / 0 errors / 26 warnings。
- 已构建原型真实 ProcTHOR N=1/2/3/6 生成、RGB-D 返回与动作隔离通过；普通场景双 agent 回归通过；旧 Procedural 双人数初始化改为明确拒绝。机器人多实体不等于人物角色证据或完整主干闭环。
- 两轮作者审核：第一轮 6 场景通过；第二轮初版状态机通过；扩展第二轮 **3 passed / 1 failed**，缺失资产会被上游静默跳过但建房仍成功。总体 CHANGES_REQUIRED。失败日志和旧审核源码保留，不以初版通过覆盖。
- 最新源码修复 `f52271cf6f1251f6ed31154a8373d89971d7d51e` 已改为缺失资产抛错并废弃部分建房 episode，但 **未重新编译/未复测**。Mac 已锁屏，计算机工具无法解锁，等待用户手动解锁。旧 a864 结果不转移到 f522。
- 证据、两份源码补丁、完整 `.app` 文件摘要及输入快照在 `docs/reviews/pc_a/procthor_unity_build_2026-09-13/` 与 `tools/unity/`。42 项选择性档案约 20MB，不含账号许可原始日志或二进制。9 项输入记录器检查通过；不是后台生产安全的全面验收。
- 剩余：新版本构建与两轮复跑、部分子 agent 失败/复杂碰撞/异常寻址、人物像素与角色证据、真实连续监督、完整联合主干默认生产路径。未训练、未更改科研路线/预算、未自动集成。详见 `PROGRESS_AFTER_AUTH.md`。

## A Unity 授权后恢复构建 2026-09-13

- 用户已完成系统授权；只读核验 `/Library/Application Support/Unity` 现已存在。首轮等待授权超时（3600 秒、退出码 1、关键源码前后未变），原 `baseline-build-20260913-01` 私有日志/失败回执保留。
- 本轮 fetch 成功，当前 CPSWM `7f8ffd1df102756c2cc66876b42b055cdc47a99e`，B `c366cad0a92593bb2c4c44db7e8d3408a2b5cc9c` 未变；继续同一独立任务分支，不写 B 或共享集成。
- 确认无旧 Unity Editor 构建进程后，使用新目录 `/private/tmp/cpswm-unity-baseline-build-20260913-02` 重启同一基线构建。开工尚无成功回执；不把许可授权当作后端修复或完整闭环通过。

## A Unity 工具链已安装，基线构建等待系统授权 2026-09-13

- 本分支 `codex/pc-a-procthor-unity-build-20260913`；Unity Hub 3.21.2 和 Unity Editor 2020.3.25f1 已安装成功。Hub UI 已核验登录及 Personal 许可激活；没有记录或公开账号、凭据、许可文件。
- 冻结 AI2-THOR `f0825767cd50d69f666c7f282e54abfe58f1e917` 完整源码/资源下载成功。独立本地源码分支增加严格构建入口，提交 `dc44ce2139cd026622fa3613421b6ed724850861`，未修改运行时算法、未推送 AllenAI 上游。
- 已实际启动基线构建；旧编辑器连接其许可客户端成功，但系统 `/Library/Application Support/Unity` 不存在，官方辅助进程弹出管理员授权。等待用户在 macOS 窗口操作，不读取凭据、不绕过保护。尚无构建成功回执、无新 DLL、多 agent 后端修复未实施。
- 构建入口和有界运行器属于未编译准备代码，Ruff format/check 已通过；两轮后端对抗审核尚未开始，旧版 53 项测试不能验收本轮。私有构建日志仅保留 `/private/tmp/cpswm-unity-baseline-build-20260913-01/`，不公开原始许可日志或二进制。
- 下一步：系统授权后完成基线构建和实机正负对照，再实施 post-house 生成并执行两轮真实对抗审核；不训练、不合并共享分支。详见 `docs/reviews/pc_a/procthor_unity_build_2026-09-13/REPORT.md`。

## A Unity 安装与独立构建开工 2026-09-13

- 用户已授权安装和构建；账号登录、许可确认仍由用户操作。分支 `codex/pc-a-procthor-unity-build-20260913`，base `ec2215ac7138c2b359d77219519e5628669c8b82`，独立工作目录 `/private/tmp/cpswm-pc-a-procthor-unity-build-20260913`。
- fetch 成功，B `c366cad0a92593bb2c4c44db7e8d3408a2b5cc9c`、集成 `bdec3ee21b7db361e390496d97ff2eb30390dc6c` 未变。保留官方 Unity release，不覆盖已有程序/证据，不写 B 文件或共享集成分支，不训练。
- 先核验冻结 AI2-THOR 源码的 Unity 版本/依赖，安装匹配工具链，记录实际构建与正负对照；真实 post-house 角色生成及两轮审核以真实构建结果为准。未构建之前不宣称 backend 完成。
- 本机 arm64，开工可用磁盘约 155 GiB，未发现已安装 Unity Hub/Editor。下载/构建产物不提交 Git；源码补丁、命令、摘要和报告通过本分支公开交接。

## A 多 agent 入口修复与两轮复核交付 2026-09-13（能力仍部分完成）

- 已公开推送并 ls-remote 核验交付证据 SHA `bd9e0f238d2afc2d7dbba7bcc1e3eddd66d76c38`；草稿 PR https://github.com/goneveitvet240-svg/cpswm/pull/13 。118 个本批归档工件摘要再次一致。本行状态登记不改变冻结代码和证据；尚未自动合并，待 B 独立复核。

- base `6a008aedd9c588a7716206eba60b3a57f9fc94d4`；入口/测试冻结 `0b46b7de077c6b25e675648deb8b5026c901c9eb`，原始 Unity 包记录器冻结 `14708f93aa006b465ddfb7a9e8823e0fb2311dee`。独立分支 `codex/pc-a-multiagent-lifecycle-20260913`，不改共享集成/B 主干。
- 真实四格对照：普通场景 1/2 agent 成功且独立转向；ProcTHOR 单 agent 成功；双 agent 原始 Initialize 包只有 1。修后在 Initialize 阶段明确拒绝，不继续 CreateHouse/Pass；不是多人能力通过。
- 实际 `AI2-THOR-Base.dll` IL 确认 Procedural guard 和初始化替换 primary / 外层旧 controller 错误回执链；高置信机制定位，尚未内部动态打点或修后 Unity 构建验证。不是源码目录名/启动程序哈希自行证明。
- 两轮作者对抗审核最终 31+22=53 passed；扩展过程中 4+2 个失败断言及源码快照保留。相邻 G1 177 passed，合计 230 项；不是电脑 B 独立验收或完整闭环。
- 交付入口人数/ID/状态/位姿校验与原始传输/序号绑定，会话不确定后停止；旧几何/多人 CLI 增加校验。没有修改 Unity DLL、伪造多人、训练或更换科学环境。
- 报告与证据：`docs/reviews/pc_a/multiagent_lifecycle_2026-09-13/REPORT.md`；后端构建清单 `NEXT_BUILD.md`。真正 post-house 多人生成未实施；常规安装位置无 Unity Editor/Hub，已询问安装授权/许可，尚待用户选择。G2/G3/G4 不签收。

## A 多人初始化因果诊断与修复开工 2026-09-13

- 分支 `codex/pc-a-multiagent-lifecycle-20260913`，base `6a008aedd9c588a7716206eba60b3a57f9fc94d4`；独立工作目录 `/private/tmp/cpswm-pc-a-multiagent-lifecycle-20260913`。
- 本轮 fetch 成功：B `c366cad0a92593bb2c4c44db7e8d3408a2b5cc9c`，集成 `bdec3ee21b7db361e390496d97ff2eb30390dc6c`，均未变化。只写本批仿真工具、专属测试/报告；不写 B 主干修复，不自动合并，不训练。
- 先做同运行程序普通场景/固定 ProcTHOR 房屋 × 1/2 agent 对照，逐步记录实际请求及响应、原始 agent 集合、动作寻址和程序集来源；随后根据实测修复并执行两轮作者对抗审核。
- 开工未测。多人底层能力、人物执行、真实监督、完整联合闭环分别验收；未安装 Unity Editor，若需定制构建将先验证工具链，不把未编译补丁作为已修复交付。

## A G1 修复与修后两轮审核交付 2026-09-13

- 公开证据提交 `975ca330da8e84fd545454e8b14b046b8fd36584` 已 push / ls-remote 核验一致；修复草稿 PR https://github.com/goneveitvet240-svg/cpswm/pull/12 。393 个归档工件与留存 manifest 逐项一致，工作树无生产路径未提交修改；后续状态登记不改变冻结代码/证据。
- 证据提交的自动格式化钩子曾触碰 run_01 两份历史源码快照，提交中止；已恢复原字节并核对全目录 manifest。仅此归档提交跳过变更文件的自动格式化钩子，实际生产代码 Ruff/mypy 及最终两轮测试已单独通过，日志均在 verification 中。未以格式化覆盖失败时源码。
- 分支 `codex/pc-a-proposal-g1-fix-20260913`；base `f95086718ad2d7d6f0707bcae1dc6758d3417233`；实际代码/测试冻结 `2ebd815543a9e51948c0eba237aacff8629b51ed`。A1–A7、分区隔离、样本 ID/pair 连接、@2 地点来源及快照目录交叉绑定已实现；`src/cpswm/system` 改动 0，不写 B 生产边界。
- 最终 `python tools/structure_two_proposal_g1_checks.py run_03`：125 原回归通过、第一轮 30 通过、第二轮 22 通过，既有坏枚举 warning 保留；Ruff/五模块 mypy 通过。第一次修后审核发现地点实体替换漏检，已修复，run_01 失败及源码快照保留。只迁移旧正例的合同字段/分区路径，不删旧攻击。
- 实际 `procthor_run_01`：42 几何事件、36 传感帧完成，source_unchanged=true；新读取器另校验全部 36 帧及原采集摘要。几何运行不是人物/完整 D1 通过。
- 两次真实多人后端探测均仅返回 1 个 agent event，`multiple_agents_verified=false`；接口成功不等于多人成功。对应版本源码含 Procedural 多 agent 限制，但本轮未观察到直接抛该异常，源码限制与实际响应分别记录。
- G1 仅作者工程复核完成，独立验收交 B。G2 人物后端选择/可行性、合法感知证据、G3 原生监督生产链、G4 网络/连续状态/预算仍未关闭；training_ready=false、training_started=false。地点目录/标注及外部保留摘要的真实性不由 schema 自证。
- 完整报告、两轮日志、源码/工件摘要、真实采集及探测：`docs/reviews/pc_a/proposal_g1_fix_2026-09-13/REPORT.md`。本分支公开交接，不自动合并共享集成分支。

## A G1 修复与两轮修后审核开工 2026-09-13

- 分支 `codex/pc-a-proposal-g1-fix-20260913`，base `f95086718ad2d7d6f0707bcae1dc6758d3417233`；独立工作目录 `/private/tmp/cpswm-pc-a-proposal-g1-fix-20260913`。fetch 已核验 B `c366cad0a92593bb2c4c44db7e8d3408a2b5cc9c`、集成 `bdec3ee21b7db361e390496d97ff2eb30390dc6c`。
- 实施 A1–A7、分区隔离/稳定样本连接/地点来源合同；随后两轮修后对抗审核。只改 data_preflight 及专属工具/测试，不接管 B 主干边界、不自动合并、不启动训练。
- 继续检查真实观测/人物事件和原生监督接入条件。人物后端、感知校准、网络参数、连续状态和预算尚未明确，不使用组件或手填标签替代真实生产者。完成度按工程修复、独立复核、原生链和科学验收分别报告。

## A 两轮对抗审核交付 2026-09-13：CHANGES_REQUIRED

- 远端审核证据提交 `becefb3db648db454fb752e2d84f0d24d0378e94` 已推送并 ls-remote 核验一致。实现草稿 PR https://github.com/goneveitvet240-svg/cpswm/pull/10 ；审核草稿 PR https://github.com/goneveitvet240-svg/cpswm/pull/11 。本行之后的状态登记提交不改变审核脚本/生产源码或已封存证据。
- 上一批完整实现和约 61MB 历史证据已获用户公开授权、推送并核验：`codex/pc-a-proposal-scheduler-20260913` = `5ec6204dfecc9137523b6c0e5dfb66658e574d41`，实际生产代码 `dbc7ec9c9b61ca2a029c3bd59ffbce136c4f7afe`。下文“推送受阻”保留为历史。
- 审核分支 `codex/pc-a-proposal-two-round-audit-20260913`，base 即上述 `5ec6204d...`；审核脚本冻结 `29076b65e7168218b885c890119757caed42f1c8`。生产算法改动 0；不是电脑 B 独立验收，不自动合并共享分支。
- 最终 `python tools/structure_two_proposal_audit_runner.py run_03`：原 125 passed / 1 warning；第一轮 1 passed / 6 failed；第二轮 1 passed / 7 failed。13 个 OPEN 断言归并为 7 类缺陷：完整提议后果绑定、三时钟、传感字段/数组真值夹带、释放时钟、重复帧引用、数值坐标别名、公共可变日程。修复尚未实施。
- 真实 Unity `unity_replay_02`：原 79 次请求成功重放；对象/相机位置 ≤2mm、视角 ≤0.01°。更正旧可见率含义：1/36 是 SDK 距离门限可见，实际目标像素非空 9/36，其中 8 帧 SDK visible=false，目标 4–46 像素。不据此生成负观测或训练标签。
- `gaps_02`：角色置换/7 次纠正引用改写不影响组件请求及输出；实际角色行为、解释→反证→修订生产者、原生六操作标签及 RGB-D→合法证据桥接仍缺。混合分区导出和地点来源合同另记准备风险；`training_ready=false`。
- 报告/根因/修复门/复跑入口：`docs/reviews/pc_a/proposal_two_round_audit_2026-09-13/REPORT.md`。run_01/02、gaps_01、首次真实复放完整保留。公开审查交接仅通过本审核分支/PR；B 后续应绑定修复后的新生产 SHA 复测，不能套用本次作者审核。

## A 提议合同与 ProcTHOR 两轮对抗审核开工 2026-09-13

- 用户本轮明确允许公开推送上一批完整证据；已成功推送并 ls-remote 核验 `codex/pc-a-proposal-scheduler-20260913` = `5ec6204dfecc9137523b6c0e5dfb66658e574d41`，实际生产代码提交 `dbc7ec9c9b61ca2a029c3bd59ffbce136c4f7afe`。下文“推送受阻”是上次历史，不再是当前发布状态。
- 本轮独立工作目录 `/private/tmp/cpswm-pc-a-proposal-audit-20260913`、分支 `codex/pc-a-proposal-two-round-audit-20260913`，审核 base `5ec6204dfecc9137523b6c0e5dfb66658e574d41`。fetch 核验 B 最新 `c366cad0a92593bb2c4c44db7e8d3408a2b5cc9c`；不覆盖其生产修复。
- 用户要求两轮对抗审核、调查缺口原因与如何修复；本轮只加专属审核脚本/测试/证据/报告及本人状态，不改生产算法，不自动合并。两轮是作者自我对抗复核，不冒称电脑 B 独立验收。
- 第一轮：全轴/六操作合同与谱系、概率绑定、输入输出隔离；第二轮：实际执行状态机、时钟/释放、样本采集根因与场景分布。保留每轮未通过断言、合法正例及基线回归，缺口与 bug 分开记录。
- 开工尚未得出结论；证据目录 `docs/reviews/pc_a/proposal_two_round_audit_2026-09-13/`。

## A 完整提议合同/ProcTHOR 调度交付 2026-09-13

- **当前仅本地交付**：实际代码提交 `dbc7ec9c9b61ca2a029c3bd59ffbce136c4f7afe`；提交后 run_05 所有被测源码摘要差异 0。2026-09-13 推送被安全审核拒绝；只读核验远端仓库 `visibility=PUBLIC`，本批约 61MB 证据含本机绝对路径、环境元数据和公开仿真房屋记录，待用户针对性确认公开发布。远端仅有此前开工登记，不得称本批代码已在 GitHub 交付；没有创建空内容 PR 或绕过拒绝。

- 可见分母补充：评测侧 2/42 中一次为未选观测；真正释放候选只有 1/36 目标可见。最新分层摘要 `final_inventory_04/summary.json`，不能把 2/42 当成 2 个可训练观测。

- 分支 `codex/pc-a-proposal-scheduler-20260913`，base `6e07ab682a9ec15e959e1a50001e237877bc4773`；实际代码 SHA 将由紧随交付的状态登记绑定，源文件摘要已记录于 `proposal_scheduler_2026-09-13/run_05/manifest.json` 和真实 run_07 receipt。本批尚未集成，等待 B 独立复核。
- 新增完整 H/R/I/C/Z/r/V 样本合同、多跳有序角色与竞争实例、六操作/修订祖先检查、完整条件概率回执合同、特征/标签隔离导出、ProcTHOR 日程/真实执行与因果图片读取。旧数据不改写，不给物理事件直接补推断操作标签。
- 最终 CPU 命令 `python docs/reviews/pc_a/proposal_scheduler_2026-09-13/run_checks.py run_05`：125 passed / 1 个既有故意坏枚举 warning，Ruff 通过，四个源文件 mypy 通过，前后源码一致。范围是新组件与相邻 D0/预检，不是完整 812 或独立验收。
- 真实 `procthor_run_07`：已校验官方 train 压缩包与训练房屋 0；已有 SDK5/Python3.11/Unity；3 个调度身份、7 个模拟日、2 个同类真实对象、42/42 几何事件、36 个 RGB-D 候选、7 次迟到释放。碰撞检查开启，预初始化 2.5cm 间隙明确记录。源前后相同。
- 严格未关闭：目标可见仅 2/42，人物角色实际执行 0；迟到释放未等于错误解释→新反证→正确修订；尚无原生六操作标签/真实角色证据/完整主干模型。training_ready=false，未训练/采购/读取封存集/改科研配置；固定日程不是完整 D1 规模或 7 自然日运行。
- 失败保留：真实 run_01/02 对象接触碰撞、run_03 运行中格式化来源不一致、run_04/05 静态视野 0 可见、run_06 观察点碰撞。run_07 为改进后的开发几何试运行，不覆盖上述历史。
- 交付说明/复跑/下一门：`docs/reviews/pc_a/proposal_scheduler_2026-09-13/REPORT.md`；机器 schema 和实际覆盖 `final_inventory_03/`。没有动 B/W1/W2 生产文件。需继续有效可见覆盖、人物证据与真实纠正链，再审查样本来源/全轴覆盖后才训练。

## A 完整提议样本合同与 ProcTHOR 调度开工 2026-09-13

- 分支 `codex/pc-a-proposal-scheduler-20260913`，base `6e07ab682a9ec15e959e1a50001e237877bc4773`。fetch 已成功，B 仍为 `c4eb20b045edb9dc34937f2b9d1038475a02e74a`；不写 B 五项边界及 W1/W2 专属文件，不自动集成。
- 用户授权补齐 H/R/I/C/Z/r/V、六种提议操作样本合同与 ProcTHOR 长期事件调度，随后进入训练准备；本批不启动训练、不选择新科研参数/预算、不读取封存数据。
- 独占新增 data_preflight 合同/调度模块、专属测试/工具和 `docs/reviews/pc_a/proposal_scheduler_2026-09-13/`。保留旧训练数据及其缺口报告，不回填伪造证据。
- 物理事件与提议操作分别记录；模型可见前缀、训练目标、评测真值分离。SDK 执行与符号调度/组件样例分别标识；测试尚未执行。

## A 数据预检交付 2026-09-13（组件及真实采集连通性，非完整训练/闭环）

- 实际交付代码 SHA `57e8576c7dd48203839cdd0ae3a4cdb295db7185`；最终真实 SDK 复验三步均成功，2.67 秒，源前后一致。此后的提交仅登记该 SHA，不改变被测代码。

- 分支 `codex/pc-a-data-preflight-20260913`，base `2a7a547fba30412d9349605aff3a7df7c60d6b3a`；实际源码逐文件摘要见 `docs/reviews/pc_a/data_preflight_2026-09-13/run_03/manifest.json`。
- method-free 训练世界盘点完成：24 世界、144 轨迹、49,428 步；完整 H/R/I/C/Z/r/V 和六操作监督不齐，不能直接训练全轴模型。未运行方法臂、未生成验证/确认世界。
- 新增可见记录前缀导出和 CLI，分开事件/到达时间，保留人物后验/reference prior，拒绝 oracle/未来记录/额外真值。开发示例已执行真实 CLI，仍明确是符号组件样例。
- 新增原始 SDK 采集接口；43 项回归、Ruff、4 新源文件 mypy 通过。真实采集使用已有 `.venv-ai2thor` Python 3.11.16/SDK 5.0.0 和本地 arm64 Unity，在同一 controller 执行 3 步并保存 RGB-D/实际执行结果，最终绑定证据 `real_simulator_02/result.json`。
- 主 Python 3.13 缺 SDK 的初检 exit 2 与第一次 fixture 失败保留；没有把不同环境混为同一结果。真实 iTHOR 单场景 smoke 不等于 ProcTHOR 日程、完整联合主干或科学收益。
- 未修改 B 的三个生产文件、W1/W2/科学配置。没有训练、采购、付费算力、自动集成。报告与来源/证据/可复跑命令在本批 `REPORT.md`。

## A 数据覆盖、可见前缀与仿真采集预检开工 2026-09-13

- 用户授权：先审核三项建议，可靠部分直接推进；不启动模型训练，不选择网络参数、连续状态或付费算力。
- 分支 `codex/pc-a-data-preflight-20260913`，工作目录 `/private/tmp/cpswm-pc-a-data-preflight.8orI6t`，base SHA `2a7a547fba30412d9349605aff3a7df7c60d6b3a`。fetch 成功，B 最新 `c4eb20b045edb9dc34937f2b9d1038475a02e74a`；保持其五项边界/W1/W2 文件不变。
- 独占新文件 `src/cpswm/data_preflight/`、`tools/structure_two_data_preflight.py`、专属测试和 `docs/reviews/pc_a/data_preflight_2026-09-13/`。不改主干、B 生产修复、现有冻结科学配置和封存集。
- 建议审核：训练世界协议有 method-free 限制，因此只运行允许的训练世界覆盖盘点，不适配到方法或训练模型。可见导出基于既有 ObservationOpportunityRecord/ObservationDetectionResult；加入发生时间与接收时间双重前缀，不把全历史摘要、种子、真值送入方法。
- 本机 Darwin arm64，项目解释器未安装 ai2thor/prior/torch；采集接口与环境预检可做，真实 Unity 运行尚未验证，不能用替身样例宣称真实采集。
- 测试尚未执行；本条推送后是已共享开工登记。

## A1 联合消费者/解析更新组件交付（非默认闭环）

- 实际交付代码 SHA：`1d24099a025c9d7c00a59e4c78c593703924b0eb`；提交后再次核对运行 manifest 全部源码摘要，差异为 0。后续本状态登记提交只更新文档，不改变被测生产源码。

- 分支 `codex/pc-a-native-joint-consumers-20260912`，生产 base `62870a3a38fce882b25d8d77f1d0526cca6fbc14`；实际执行源逐文件 SHA-256 在 `docs/reviews/pc_a/native_joint_consumers_2026-09-12/run_01/manifest.json`，交付代码提交由该分支确定。
- 新增全粒子决策视图、三解析块纯计算；扩展 CIAV 完整粒子期望效用，仍以原因边缘计算原因信息增益。不写 B 独占两个核心文件，不改科学配置。
- 命令：主仓库 `.venv/bin/python docs/reviews/pc_a/native_joint_consumers_2026-09-12/run_checks.py run_01`。85 passed / exit 0；Ruff、三个源文件 mypy 通过；源码前后摘要相同。不是 812 项全回归或 Windows 复现。
- 新增测试含明确标识的合成组件正例/负例与 prepared 接缝集成，不冒充真实默认候选生成。来源授权、完整概率、真实测量模型、默认调度与同一连续执行历史仍未完成。
- 用户确认没有现成全轴模型和测量/噪声工件；获取与训练方案见同目录 `INPUT_ACQUISITION.md`，不是要求用户自行找完才能继续。三候选训练覆盖盘点/可见特征导出可先开展，物理状态含义及未冻结参数需明确。
- 完整报告 `REPORT.md`；推送本人分支后交 B 复核，不自动集成。五项边界修复仍由 B PR #7 负责，本批不宣称关闭其反例。

## A1 默认完整联合主干：非冲突消费者与条件统计批次开工

- 任务目标：继续闭合默认完整联合主干及同一连续历史闭环，不以手工 prepared 注入、占位模型或模拟执行成功宣称完成。
- 本批分支：`codex/pc-a-native-joint-consumers-20260912`；base/开工源码 `62870a3a38fce882b25d8d77f1d0526cca6fbc14`；工作目录 `/private/tmp/cpswm-pc-a-native-joint.Ct7tPQ`。
- 本次 fetch 成功；B 最新 `23506024213d517ba4bab65d4318663163b00913`，PR #7 正在五项边界修复/证据运行器，唯一占用 `prototype_spine.py`、`structure_two_particle_workspace.py` 及直接必要类型。本批不写这两文件，不改 B 审核或比较工具。
- 本批 A 独占新增 `src/cpswm/system/structure_two_joint_consumption.py`、`src/cpswm/system/structure_two_conditional_updates.py`，必要时扩展 grounded_search/active_verification.py 的联合后验消费；专属新测试/工具/报告；不改科学配置。
- 本批落实：完整粒子相关性的期望效用/CIAV 消费及三个解析块的显式条件增量、累计与撤销。数学正例会明确标单元/组件验证，不冒充默认生产路径。
- 待接入依赖：B 边界修复经审查后接入当前工作区；真实全轴模型/选择回执、真实连续测量与噪声模型尚未见共享交付，已向用户询问；不把原因/阶段 MLP 更名为全轴模型。默认候选生成/完整 log-q、主干默认接入、动作执行反馈及完整连续验收均保留为未完成目标。
- 本批开工尚未测试；证据计划 `docs/reviews/pc_a/native_joint_consumers_2026-09-12/`。与 B 通过 GitHub 本状态/PR 公示分界，不自动合并共享集成分支。

## A1 窗口三完整主干工程 R7 — 进行中

- 分支：`codex/pc-a-w3-backbone-r7-20260912`。
- 工作目录：`/private/tmp/cpswm-pc-a-w3-backbone-r7-20260912`。
- base SHA / 当前被测代码 SHA：`1bd513f51ab7e54a7290870a5f34b524254d55c6`，包含 R4/R5/R6 实际修复。
- 已 fetch 核验集成 SHA：`bdec3ee21b7db361e390496d97ff2eb30390dc6c`；审核依据：`97e1d2c1e83a4532e2b3bab3bf87cc6a2927f274` 的 round6 REPORT。
- 任务边界：模型来源、真实后验消费、默认联合主干、唯一账本与延期取消恢复、同一连续运行七算子后果矩阵。不得改 W1 编排器或 W2 专属比较模块。
- 已冻结：Route C、Architecture A、P5_FIRST、A1+B1、H/R/I/C/Z/r/V、三个 RB blocks 与七算子；不重新选择。
- 本次命令：`git fetch origin --prune` 成功；本次尚未运行代码验收。
- 证据：`docs/reviews/pc_a/w3_backbone_r7_2026-09-12/`，保留远端四文件及版本。
- 下一步：定位并恢复可验证模型原件；分别提交依赖批次并推送本分支，通过 PR 交接，不自动集成。
- 本条随分支推送后为 GitHub 已共享的开工登记；完整主干和科学收益未验收。

## 批次一交付：真实模型原件恢复

- 实际被测生产代码仍为 `1bd513f51ab7e54a7290870a5f34b524254d55c6`；新增工件绑定历史提交 `505e723170c29f8707ee19d113a5b8646680c5f6`，精确字节/源码哈希见 model_recovery 和 model_restored_50.command.json。报告提交不自引用。
- 命令：主仓库 Python 3.13 运行 `docs/reviews/pc_a/w3_backbone_r7_2026-09-12/run_checked.py model_restored_50`，结果 50 passed / exit 0；恢复前 exit 1 的 17 项失败/错误保留。
- 下一步：真实生产后验绑定与消费、默认联合主干和延期取消恢复仍在进行；完整能力与科学收益未验收。

## 批次二交付：真实 PCHMP 生产来源与投影消费

- 生产者、消费者、证据和语义身份绑定已实现，合法非空正例和完整重封负例见 POSTERIOR_PROJECTION.md。
- 原 714 项回归通过（exit 0，868.63 秒）；107 项预检通过；Optional 类型守卫修改后的 85 项定向回归及 mypy 日志单独保存。
- 精确被测源码绑定：projection_regression_714.command.json、projection_typed_final.command.json；本批提交可由 GitHub 分支查看，不把旧代码测试冒作当前结果。
- 下一步：延期取消后的父贡献恢复，以及默认完整联合主干连接。安全拒绝与模型工件恢复均不等于完整能力完成。
- 后续定向复测检出 Python 原因集合键的顺序问题，85 项曾出现 3 失败、扩展后 87 项曾出现 2 失败，均保留原日志；最终109项通过。使用 native 局部确定序列化，未改共享旧散列格式。前述714通过是较早绑定，最终集成版本仍需重跑。

## 批次三最终交付：取消恢复、完整源绑定回归与连续连接证据

- 本批代码及证据提交：`1d6887206605841074ada0f5ed67db278d1b7958`；基于 R6 `1bd513f51ab7e54a7290870a5f34b524254d55c6`，未重建旧 HEAD，原有工作目录保留。
- 前两批提交：模型 `8607a751cc482661baefa127968b4bc0758ec1d8`；投影 `5fa093290f7f69d1e789915a66645ef1d0b3b875`。
- 最终命令：主仓库 `.venv/bin/python -m pytest -o addopts= -q -n 4 -p no:cacheprovider`，完整 38 个测试文件及 JUnit 参数在 `final_812.command.json`。结果 **812 passed / 0 failed / 0 skipped / exit 0**；包括原 647+67、邻接 50、新投影 21、新取消 27。最终源码前后相同，666 文件快照与本批提交逐一匹配。
- 非零退出保留：原模型 17 项失败/错误、投影集合序列化失败、取消开发失败、早期错误汇总断言 exit 1。原 round4 独立脚本 direct_revision 仍记录 CCRR 原子拒绝异常；没有把退出 0 当作字段全部通过。round5 正负结果、修前修后取消对照均保留。
- 新能力：真实 PCHMP 来源合法消费；延期取消通过唯一 Hybrid 账本恢复原父及被撤销的原派生贡献，资格、快记忆、来源、摘要、再次纠正/撤回保持，异常和 KeyboardInterrupt 原子回滚可重试。不是跨进程掉电持久恢复证明。
- 连续 24 次学习、主动验证、迟到纠正、后续读出，8 个公开干预/对照运行记录真实七算子对象、输入输出、消费及数值后果；不是每条连接全部中断组合已穷尽。
- **完整默认主干未完成**：默认完整联合粒子数实测 0，普通 ΔΛ/Δξ 为 0，CIAV 未消费完整粒子后验，默认自主修订尚未校准。全轴模型工件、真实条件信息模型/联合读出绑定与重采样决定详见 REMAINING_NATIVE_BACKBONE.md；不能将所有剩余接线都称作用户决策。
- 未改科学配置、窗口一编排器或窗口二专属比较实现；完整统一框架范围和既有用户决策保持；本批没有科学收益验证。
- 证据：`docs/reviews/pc_a/w3_backbone_r7_2026-09-12/REPORT.md`、`FINAL_COMMANDS.md`、`TEST_SUMMARY.json`、`committed_source_binding.json`。
- PR 草稿：<https://github.com/goneveitvet240-svg/cpswm/pull/4>。请求电脑 B 绑定本批实际代码 SHA 复核；不请求自动整合或窗口整体验收。
- 下一步：取得明确缺失的全轴模型/观测与读出绑定及待决重采样规则，继续默认候选调度、条件增量束、后验到行动、反馈后缀与重放工程；仍未实现项逐项保留。本状态随本人分支推送共享。
