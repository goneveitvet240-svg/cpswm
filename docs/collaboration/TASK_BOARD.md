# A交付回执：双线诊断已推送，PR104保持草稿（2026-10-10）

证据提交 `7198f29c705bf583f436a721c70fda230aa4878c` 已成功推送，创建 [草稿PR104](https://github.com/goneveitvet240-svg/cpswm/pull/104)，堆叠PR103、未合并。实际最终工具源码 `209b688a322970ee71bf985e13fb5201d6520294`；[报告](../reviews/pc_a/failure_mechanism_diagnostic_2026-10-10/REPORT.md)。165定向测试、482证据验算及41原件散列核验通过。原查询6/9未提升；一致受控观测的已有双时标21/36仍低于相同当前人物权重的普通记忆36/36。已定位默认慢读出与被阻断写入的组合、假设人物似然污染及玻璃实例/深度差异；不是自然任务准确率、整体无价值结论或完整验收。B复核、完整S1/全仓、正式收益与共享集成待完成。

---

# A交付：底层失败定位与核心读出对照（2026-10-10）

分支 `codex/pc-a-failure-mechanism-diagnostic-20261010`，base `9767a2d63f3d4f501911fc1b1cd0fc0f94b48dc7`，最终诊断工具源码 `209b688a322970ee71bf985e13fb5201d6520294`；生产src未改。[报告](../reviews/pc_a/failure_mechanism_diagnostic_2026-10-10/REPORT.md)、[复现](../reviews/pc_a/failure_mechanism_diagnostic_2026-10-10/COMMANDS.md)。

A：三臂原查询均6联合正确、1正确实例但几何出界、2无报告。后两次bowl检测0.4704/0.4963低于0.5而失去当前mask；光流各10点仍存。玻璃碗三帧真值像素入原AABB均0，约92%深度位于台面主导高度区间。独立54射线控制不支持取消半像素/深度比例作为修复，具体玻璃渲染/碰撞差异待定向核验。

B：6个生产case及同状态5路读出。same组默认0/36、latest-owner/v0.6各21/36、获得相同当前人物权重的普通完整历史计数36/36；长期写入被行政阻断，默认慢读出不读快证据，假设CIAV似然又将客人事件主人权重推过快门槛。旧different夹具人为改位置，其7/15/15/12/12仅作诊断；不报科学准确率。3个different纠正每个仅1合法目标，恢复/同算法重放一致；same组3/3无合法目标，保留失败。人物/阶段组件正负路径通过，未证明独有收益。

165项定向测试通过（132.24s），Ruff通过；482项封存验算、41原件完整SHA核验。全仓、完整S1、完整强邻近系统、B独立验收、共享集成和科学收益仍未完成。后续：玻璃像素定向射线、读出接线/CIAV人物似然诊断、真实反证与长期对照。原用户树与STATUS_B未改，完整框架保留。本节为本地交付结果，GitHub推送由后续回执确认。

---

# A交付回执：三流程证据已推送，PR103保持草稿（2026-10-10）

报告、复现和45份散列证据提交 `7c266e23ef244616df86bd89a3d05a33365c4bd8` 已成功推送到 `codex/pc-a-object-memory-integration-20261010`。[PR103](https://github.com/goneveitvet240-svg/cpswm/pull/103) 已更新最终结果，未合并；实际工具源码仍 `9480c489a22036e1980a813eb83b28b5149d8c1f`。47定向检查、19帧三臂public-only重跑、312条算术复核、最终owner撤回/冷启动检查通过。原联合6/9和同前端记忆读出无净收益；历史几何39/80→hybrid47/80不等于身份/泛化收益。完整S1/全仓/B与共享集成待完成。

---

# A交付：三流程首轮完成，查询/记忆无净收益，历史几何局部改善（2026-10-10）

[草稿 PR103](https://github.com/goneveitvet240-svg/cpswm/pull/103) 堆叠PR102，独立分支 `codex/pc-a-object-memory-integration-20261010`，base `2b99bbd53bfdb622f171eca9572b58e8df67e6a6`。生产src `d3e1d448261f0fef456aab4db32277cec6e6b938`，实际完整工具源码 `9480c489a22036e1980a813eb83b28b5149d8c1f`。[报告](../reviews/pc_a/object_memory_integration_2026-10-10/REPORT.md)、[复现](../reviews/pc_a/object_memory_integration_2026-10-10/COMMANDS.md)、[结果](../reviews/pc_a/object_memory_integration_2026-10-10/evidence/summary.json)。

已实际接入原OpenCLIP ViT-H-14＋ConceptGraphs 13个官方函数/类的对象匹配/融合，可选进入现有owner；并非完整作者系统复现。原9查询当前/CG/hybrid均身份7、位置6、联合6，额外相同初始身份轨迹10/15→7/15→10/15。历史16帧AABB几何当前39/80、CG51/80、hybrid47/80；缺少instance masks且同屋开发暴露，不报身份联合或泛化收益。Bowl0/16未解决。

普通来源记忆与CPSWM共享同一前端、原始历史及撤回信息；最终hybrid三前缀和中间来源撤回后规范读出相同，来源3→2、账本仍3，冷启动完整state相等、运行期helper篡改拒绝。新物理动作0、语义受控。修复混合mask内参考点被替换的退化、rounded seed在mask外导致的崩溃、重复4GB权重散列开销及tuple/list对照误报。未微调模型。

47定向检查、Ruff、3文件mypy、312条独立算术复核通过；public-only新worker重复19帧三臂，9组逐步payload完全一致。封存45个清单约束证据文件30,534,160 bytes，含SQLite/检查点/交付原件。owner检查477秒，尚非实时。完整S1/全仓/完整伪造状态机矩阵、B独立复核与共享集成未完成；PR保持draft、主收益门未过、完整框架保留。本节提交推送前结果为本地完成。

---

# A进行中：三个流程已形成可执行实验，最终边界修复复测中（2026-10-10）

分支 `codex/pc-a-object-memory-integration-20261010`；base `2b99bbd53bfdb622f171eca9572b58e8df67e6a6`。首次功能源码 `290f629531daa75b3f21939b60f018f83d5d778c`，当前修复源码 `d3e1d448261f0fef456aab4db32277cec6e6b938`。[计划](../reviews/pc_a/object_memory_integration_2026-10-10/PLAN.md)、[调整记录](../reviews/pc_a/object_memory_integration_2026-10-10/ADJUSTMENT.md)。

接入原ViT-H-14特征、几何+视觉关联及点云融合，可选进入原owner；同前端普通来源记忆与CPSWM的3前缀/中间撤回读出相同，290f629冷启动状态一致、helper替换被拒、物理账本不变。原查询9槽仍联合6，无新增科学收益。加入同mask参考特征读点消除额外初始轨迹退化。16帧历史复查的5°第3帧发现rounded seed在mask外会崩溃；d3e1d44改为合法seed不足时UNKNOWN，不放宽输入门。

当前在d3e1d44重新运行三臂19帧、hybrid真实owner/普通来源记忆、定向回归；最终结果尚待汇总。33项轻量检查、3文件mypy与Ruff已通过，完整全仓/B验收/共享集成未完成。新增物理动作0，语义为受控bootstrap。13个官方符号加适配器，不冒充完整ConceptGraphs系统或强系统死亡测试通过。完整研究范围保留。

---

# A开工：原版对象特征、匹配记忆对照和观测驱动调整（2026-10-10）

用户明确授权推进三个流程。独立分支 `codex/pc-a-object-memory-integration-20261010`，base `2b99bbd53bfdb622f171eca9572b58e8df67e6a6`；[计划](../reviews/pc_a/object_memory_integration_2026-10-10/PLAN.md)。ConceptGraphs 官方算子已锁定，原 ViT-H-14/laion2b_s32b_b79k 权重下载完成。尚未产生本轮实验结果；完整生产验收/B复核/共享集成均未完成。此开工提交只包含源码来源与实验协议，不宣称代码完成。完整框架和其他工作树保留。

---

# A交付：首个外部对象组件已运行，原查询收益为零（2026-10-10）

[草稿 PR102](https://github.com/goneveitvet240-svg/cpswm/pull/102) 已建立并堆叠 PR101；报告与13个散列证据文件（13,597,153 bytes）提交 `84caf84bd4b7f95fe69cd17c5b0f0cc0e44412b6` 已推送。实际适配器仍为 `c642f4cfdde0359be762eaa15d9d7f2cd1b3b74d`，未合并。

分支 `codex/pc-a-external-object-pilot-20261010`，base `ac1df559f36630cd7e587936f5d56e7dbf30ed14`，实际适配器源码 `c642f4cfdde0359be762eaa15d9d7f2cd1b3b74d`。[报告](../reviews/pc_a/external_object_pilot_2026-10-10/REPORT.md)、[复现](../reviews/pc_a/external_object_pilot_2026-10-10/COMMANDS.md)、[机器结果](../reviews/pc_a/external_object_pilot_2026-10-10/evidence/summary.json)。

ConceptGraphs 官方最大点云簇函数已通过独立 Open3D worker 接入冻结 RGB-D 到只读表面报告的实验边界。四组同输入/查询/源动作预算均为身份7/9、位置6/9、联合6/9；过滤1272/114571点，未改变主对照选点，无查询收益。四组各重复一次逐字节一致，第二遍仅提供public目录；36评分独立算术复算一致，当前对照与上一轮记录完全一致。11定向检查及Ruff/提交钩子通过；未跑全仓/S1完整矩阵。

只是官方去噪组件，非完整ConceptGraphs/强系统基线；未接生产owner、记忆或新动作策略，生产src未改。两Python环境隔离兼容已落实。下一批应检验完整对象关联，以及同强前端下普通记忆和CPSWM的效用差异；新科学路线/面板仍交用户决定。B独立复核、PR审查和共享集成未完成，完整框架保持。

---

# A：外部对象组件接入试验开工（2026-10-10）

用户授权接入已有组件并根据实测迭代。独立分支 `codex/pc-a-external-object-pilot-20261010`，base/生产源码 `ac1df559f36630cd7e587936f5d56e7dbf30ed14`。首次接入 ConceptGraphs 官方最大点云簇去噪函数，用现有冻结 RGB-D、同查询同动作预算和严格身份+AABB做四臂读出对照；不冒充完整外部系统/强基线/新主动策略。

[计划](../reviews/pc_a/external_object_pilot_2026-10-10/PLAN.md)。独立 Open3D 环境已建立；当前尚无实验收益，B独立复核和共享集成未完成。保留完整统一框架与原用户树。本节推送前为本地进行中。

---

# A交付：参考特征几何核验修复局部门通过，完整死亡测试仍 FAIL（2026-10-09）

分支 `codex/pc-a-reference-feature-reid-20261009`，base `2d54c541107bd718d02c5427220f5715a0eca93a`，生产代码 `8acab228c6cdaa85865088f73c82b9455fb3fea1`，报告/证据提交 `c4d7bf4ee9913cd7b295591828caa36a330deeb3`。[草稿 PR101](https://github.com/goneveitvet240-svg/cpswm/pull/101) 堆叠 PR100；[报告](../reviews/pc_a/reference_feature_reid_2026-10-09/REPORT.md)与[机器汇总](../reviews/pc_a/reference_feature_reid_2026-10-09/evidence/subpixel-summary.json)。

同一输入/三动作预算下错误重识别 `2→0`，得到 1 次自然身份＋严格 AABB 联合恢复且下一帧保持正确；确定性、歧义拒绝、晚出生隔离、可评分和零查询退化均通过。既定查询联合分数仍 `6/9→6/9`，因此 `query_level_joint_gain=false`、总状态 FAIL、不扩 S1 全矩阵。54 项聚焦测试和静态/类型/编译/证据清单检查通过；B独立复核、PR审查和共享集成待办。若下一轮改变查询面板，须由用户决定。

---

# A：参考特征几何核验修复开工（2026-10-09）

用户批准按A推荐路线继续。独立分支 `codex/pc-a-reference-feature-reid-20261009`，base为PR100 head `2d54c541107bd718d02c5427220f5715a0eca93a`。[计划](../reviews/pc_a/reference_feature_reid_2026-10-09/PLAN.md)复用同一冻结死亡测试，不重新采集/检测或改指标；用原feature ID直接对应、既有至少4点、FB≤1.5px和0.5m几何尺度阻止宽语义mask无谱系重初始化。错误接受须归零且至少一个旧LOST轨迹身份＋严格AABB正确恢复；原query-level收益门保持，若无查询收益仍不扩完整矩阵。当前尚无修复运行结果或B验收。

---

# A交付：匹配过渡死亡测试未过门（2026-10-09）

电脑 A 在 `codex/pc-a-matched-transition-death-test-20261009` 完成同一冻结 RGB-D/native-mask 输入、同一三动作预算的旧/新源码配对重放；实验代码/报告/完整9.7 MB证据提交 `ebc52828af02b4825aa153d5f1deca27974356d1`，[草稿 PR100](https://github.com/goneveitvet240-svg/cpswm/pull/100) 堆叠 PR99。[报告](../reviews/pc_a/matched_transition_death_test_2026-10-09/REPORT.md)与[机器汇总](../reviews/pc_a/matched_transition_death_test_2026-10-09/evidence/summary.json)。两臂身份/位置/联合得分均为 `7/9、6/9、6/9`；候选两次将实际 Kettle 错误恢复为 CounterTop，正确自然联合恢复为零，死亡测试 FAIL。UNKNOWN、LOST、错误接受和晚出生均保留；SDK真值仅离线评分。

确定性重放、完整双候选歧义拒绝、晚生 query 隔离和零查询退化通过，不能代替任务收益。mask 成分诊断显示被接受的 dining-table mask 主要是 CounterTop（`67.30%/74.07%`），目标 Kettle 仅 `7.28%/6.63%`，说明当前粗类别＋RGB直方图＋单点几何会产生唯一但错误的实例匹配。相关4文件48项、Ruff/format、编译和diff检查通过；完整S1矩阵因预声明门失败而未启动。

下一项建议：在保留现有指标与 UNKNOWN 语义的前提下加入 reference-feature geometric verification，先复用已有 `min 4`、`FB≤1.5 px` 条件修复本冻结反例，再重跑死亡门。B需绑定最终SHA独立复核；A不集成当前失败方法、不改STATUS_B/原用户树/共享集成，完整统一范围保持。

---

# A交付：持续对象出生与保守重识别（2026-10-08）

电脑A已在 `codex/pc-a-continuous-object-reid-20261008` 提交生产实现 `a5385ddaf6724d2d346fc222866edc2b7ec9407c`（base `6e9c953a81e2fc072f4d079d7a19194b1324ea64`），[草稿PR99](https://github.com/goneveitvet240-svg/cpswm/pull/99)已建立。[交付报告](../reviews/pc_a/continuous_object_reid_2026-10-08/REPORT.md)：晚生轨迹与首帧query隔离，丢失恢复复用既有开发能量并要求唯一一对一；合法、无候选、多候选、共享候选、晚生、回滚和依赖绑定路径已验证。17项核心及42项最终组合通过，5组相邻回归另有30通过/21依条件跳过；冻结公开输入只证明旧LOST行达到唯一门控，不等于任务收益。完整S1原始包缺失，15-run重放未完成。下一交接为B绑定该SHA独立验收；随后A在同任务/同预算重新运行fixed/active/no-update与retain/withdraw矩阵。共享集成不自动合并，几何AABB误差和完整统一研究范围不变。

---

# A：持续对象出生与保守重识别开工（2026-10-08）

电脑 A 从 PR98 head `6e9c953a81e2fc072f4d079d7a19194b1324ea64` 在独立分支 `codex/pc-a-continuous-object-reid-20261008` 实现自然对象晚出生和可拒绝重识别。沿用既有外观—几何开发配置，不选择新阈值/先验；晚出生轨迹不冒充首帧任务引用，冲突保持 UNKNOWN。交付需含合法正路径、完整歧义/伪造路径、事务回滚及冻结 S1 只读重放诊断；B 独立验收仍 pending。[计划](../reviews/pc_a/continuous_object_reid_2026-10-08/PLAN.md)。

---

# A：公开方法与 S1 代码对照完成（2026-10-03）

分支 `codex/pc-a-method-code-review-20261003`，base/被审代码 `1c21e4eb4fb998a8fcdc334bb727441052aea4b3`；开工提交 `76e978c830d70c2f82db7673c3a2b4dc1a98fc08` 已推送。S1 实际执行 SHA `747ea0187a6a03c4decaa2d3ad05e000a31f1dca`，本次仅追加文档，生产代码无变化。[对照报告](../reviews/pc_a/method_code_review_2026-10-03/REPORT.md)及[官方源码清单](../reviews/pc_a/method_code_review_2026-10-03/SOURCES.json)。

核查 ConceptGraphs、3D-Mem、GOAT/HomeRobot、Where Did I Leave My Glasses 原文与所选官方代码，26 文件全部与固定提交的 Git blob 哈希一致。确认 S1 支路只首帧建轨、光流丢失不可恢复、主动决策仅类别/序号/状态查表、表面更新 neutral 且最后帧位置读出。记忆消融仅撤回中间帧，不是跨任务清记忆；论文导航成功判据不能与严格 AABB 直接排名。碗毫米误差根因仍待独立几何校验。建议先持续对象层及最强邻近基线配对效用检验，再扩展矩阵；不改变用户指标/先验/研究范围。

验证：26 外部 blob、所有报告本地链接、src/tests/tools 相对 base 无差异、git diff --check。未执行对方方法、未重跑生产回归/仿真、未宣称对方论文成功率已复现。外部完整源码及论文只在 `/private/tmp/cpswm-prior-art-20261003`，仓库仅分析与来源索引；无新原始实验包公开。B 独立验收仍 pending。报告/来源清单提交 `882f36a9b905af29525fc2099bcb53186239f43b` 已推送；[草稿 PR98](https://github.com/goneveitvet240-svg/cpswm/pull/98) 堆叠 PR97，未合并。

---

# A：公开方法/代码与S1失败对照开工（2026-10-03）

用户要求核查别人成功的方法与代码，再分析本项目。分支 `codex/pc-a-method-code-review-20261003`，base/当前被审源码 `1c21e4eb4fb998a8fcdc334bb727441052aea4b3`（PR97）；S1执行SHA为747ea0187a6a03c4decaa2d3ad05e000a31f1dca。已fetch核对集成仍19ddf26830348a2f0b33f0af54d6ba702c5cfb1c。只进行公开原文/官方代码与冻结结果对照，不改生产实现、指标、先验或研究范围。

[检索计划](../reviews/pc_a/method_code_review_2026-10-03/SEARCH_PLAN.md)。证据拟保存于 `/private/tmp/cpswm-prior-art-20261003`；报告记录公开代码精确SHA、读取位置、全文/摘要证据级别和未复现实验的边界。原S1工作树、STATUS_B和共享集成不改，B独立验收仍pending。此节推送前为本地进行中。

---

# A：S1 首批系统矩阵完成，收益边界已核验（2026-10-02）

分支 `codex/pc-a-system-experiments-s1-20261002`，base PR96 `9c0206be16057689a2b06ee1c64b008a30c35f19`；实际执行源码 `747ea0187a6a03c4decaa2d3ad05e000a31f1dca`，生产src/及tests/未改。[草稿PR97](https://github.com/goneveitvet240-svg/cpswm/pull/97)堆叠PR96，未合并。[报告](../reviews/pc_a/system_experiments_s1_2026-10-02/REPORT.md)、[协议](../reviews/pc_a/system_experiments_s1_2026-10-02/PROTOCOL.md)、[命令](../reviews/pc_a/system_experiments_s1_2026-10-02/COMMANDS.md)。

预声明15运行/45查询槽全部完成，39真实动作；6/6组公共输入和全物体状态匹配，15/15新进程恢复一致，42主流程子命令返回0。固定5/9（9动作）、主动6/9（3动作）、关闭更新0/9；保留/撤回中间记忆均5/9、各9动作。三次主动都首步停止，局部优势来自避免后续丢失，不是新视角澄清证据；未测到中间记忆增益。20个最终unknown保留；逐帧15个有报告碗观测均位置失败，高度越界约1.561–2.066mm，根因未确证，未改AABB容差。

954源码pin和冻结资源核对，45主评分按原始SDK掩码/AABB重算一致；117逐帧查询作为事后诊断。新增驱动Ruff/format/编译通过，旧54回归不冒称本批重跑。完整2067文件/608.5MB原始证据与已逐文件核验的103.8MB压缩包在 `/private/tmp/cpswm-system-s1-evidence-20261002` 及同名tar.gz；新大包未上传，本分支提供源/协议/派生评分恢复记录/原始哈希清单。原PR96已公开证据保持。

当前结论限单屋相关视角、受控语义bootstrap，非完整自然联合系统/独立场景/长时动态或B验收。下步依据为自然目标初始化、持续关联和几何读出问题，完整统一框架不缩小。B需实际绑定SHA复核，A不代签、不改STATUS_B/原用户树/共享集成、不自动合并。

---

# A：S1 系统试验开工（2026-10-02）

用户要求开始系统试验。独立分支 `codex/pc-a-system-experiments-s1-20261002`，base/开工代码 `9c0206be16057689a2b06ee1c64b008a30c35f19`（PR96）。生产源码保持 `745613ef0b804b5da4d1d2afcbba56fd9f78925c` 内容，仅补矩阵编排及如实枚举各组动作集合。fetch 已核对集成 `19ddf26830348a2f0b33f0af54d6ba702c5cfb1c`、B `fd4ca6ef5e81c90d7cf7987b42c0b2810d8a810a`，无新集成进度。

[预声明协议](../reviews/pc_a/system_experiments_s1_2026-10-02/PROTOCOL.md)：25°/30°/35°三个首观察设置，fixed/active/no-update及保留/撤回中间记忆，共15运行、45查询槽、每运行预算3。旧模型冻结，严格AABB，保留未知/失败，真实同世界组内配对；15个完成运行拟逐一新进程恢复。源冻结和证据在 `/private/tmp/cpswm-system-s1-evidence-20261002`，实际执行SHA由 plan.json 记录。当前尚无新实验结果，推送前为本地进行中。完整研究框架保持，B独立验收待实际B执行；不改原工作树、STATUS_B、共享集成，不自动合并。

---

# A：六步流水线已公开交接（2026-10-02）

[草稿PR #96](https://github.com/goneveitvet240-svg/cpswm/pull/96)堆叠PR95，未合并。完整源码/原始证据提交 `284ccb00f7a55e4d10988d9ea5f0fdc3d8560c32` 已成功推送；生产冻结仍 `745613ef0b804b5da4d1d2afcbba56fd9f78925c`，驱动/评分仍 `9581ebcd94e11e79dd459761df3b3cdfcedb100a`，本次只追加交接确认。

一次自动审批因新增公开原始数据载荷而拒绝推送；用户随后明确授权“公开本次全部证据”（106.9MB压缩/548.5MB原始），重新推送成功，数据发布阻塞已解除。B独立复核仍待实际B执行，不以A的归档核验/新进程恢复替代。下一位从本PR head核对源文件pin、[报告](../reviews/pc_a/six_step_pipeline_2026-10-02/REPORT.md)与[复现命令](../reviews/pc_a/six_step_pipeline_2026-10-02/COMMANDS.md)开始；不要混用默认main或旧集成源码。

---

# A：六步开发闭环本机交付，B复核待执行（2026-10-02）

分支 `codex/pc-a-six-step-final-20261002`；原始base/PR95 `1bdacaec1b97e6e82e4138ea94fcd48e5b9f6130`；生产冻结 `745613ef0b804b5da4d1d2afcbba56fd9f78925c`，驱动/评分冻结 `9581ebcd94e11e79dd459761df3b3cdfcedb100a`。[报告](../reviews/pc_a/six_step_pipeline_2026-10-02/REPORT.md)、[协议](../reviews/pc_a/six_step_pipeline_2026-10-02/PROTOCOL.md)、[命令](../reviews/pc_a/six_step_pipeline_2026-10-02/COMMANDS.md)、[证据清单](../reviews/pc_a/six_step_pipeline_2026-10-02/evidence/MANIFEST.json)。本节所属提交推送前仍为本地交付。

统一入口、自然表面支持owner事务、固定连续观察、冻结联合成功策略、跨进程记忆及撤回、同任务同预算比较均已实际运行。最终fixed 3动作2/3；active 1动作2/3；no-update 3动作0/3，身份/位置分别记录，初始RGB/depth/pose和全物体状态完全一致。后续记忆保留与仅撤回中间观察均2/3，后续各1动作，逐帧公共输入完全一致，**未测到额外记忆收益**。碗身份正确但y低于真盒约1.46mm，判据不改。保持一屋开发/受控语义bootstrap范围，未宣称完整自然语义或统一科学成功。

最终54项事务/策略回归通过；Ruff、mypy398、format413通过，960源文件封存未变。最终fixed及中间撤回后继续观察的数据库均新进程恢复一致；早期四种静态记忆控制另有四进程复核，绑定822fc3e/7083056而非混称最终SHA。完整1791文件+8链接封存，首轮Unity初始化超时、中止运行、UNKNOWN和故意故障均保留；详见报告区分各证据层级。

原集成仍19ddf26830348a2f0b33f0af54d6ba702c5cfb1c，B仍fd4ca6ef5e81c90d7cf7987b42c0b2810d8a810a（fetch核对）。B执行入口未连接、未自签独立验收、未合并。下一步由真实B绑定冻结SHA复核合法/完整伪造/状态机/账本动作后果与公平性；研究下一缺口为自然位置读出误差、独立场景联合效用与长时/动态记忆收益。完整统一框架不缩小；原用户树、STATUS_B及共享集成未改。

---

# A：六步流水线最终收口（2026-10-02）

为保持旧工作树正在执行的源绑定恢复实验不受修改影响，从 `7083056` 单独创建 `codex/pc-a-six-step-final-20261002`，工作目录 `/private/tmp/cpswm-pc-a-six-step-final-20261002`。功能冻结 `745613ef0b804b5da4d1d2afcbba56fd9f78925c`；仅修复撤回首参考后策略可能重锚定的边界，并把同组报告合并为一次owner状态读取。旧树/旧证据保留，不改变共享集成分支。

反例已在旧源码复现（3 passed / 1 failed），修后4项通过。第一次真实同屋配对确认初始RGB/depth/pose和全物体状态完全相同：固定3动作与主动1动作均2/3联合成功，不更新3动作0/3。旧冻版本53项事务回归、3项旧连续回归通过；最终修复版本正在重新实跑/恢复验证，不能用前一SHA结果代替最终验收。[协议](../reviews/pc_a/six_step_pipeline_2026-10-02/PROTOCOL.md)。未连接电脑B执行入口，独立复核仍pending；本节推送前为本地进行中。

---

# A：六步任务流水线开工（2026-10-02）

用户明确要求执行统一入口、自然观察更新、固定扫描、联合任务决策、后续记忆与配对验收六步。独立分支 `codex/pc-a-six-step-pipeline-20261002`，base/当前代码 `1bdacaec1b97e6e82e4138ea94fcd48e5b9f6130`（PR95）。fetch成功，集成19ddf26830348a2f0b33f0af54d6ba702c5cfb1c、B fd4ca6ef5e81c90d7cf7987b42c0b2810d8a810a未变，旧窗口无重复活动。

优先复用已有owner事务/持久化/撤回，区分表面特征与对象状态；固定扫描独立于主动策略，不改停止条件制造成功。身份＋位置/AABB既有指标保持，未知/失败保留，训练开发与评分隔离。本轮未产生新结果；B独立复核必须由实际B执行，不冒称完成。完整统一框架、原用户树/STATUS_B/集成分支保持。证据拟存 `/private/tmp/cpswm-six-step-evidence-20261002`。提交推送前为本地进行中。

---

# A：自然掩码表面支持局部交付（2026-10-02）

分支 `codex/pc-a-natural-mask-surface-20261002`，base/PR94 head `01c52fef24d5fafc95bf8f6584602771aa176d5c`，冻结实际功能/测试/驱动 SHA `d2c3f51b005b49b97812f43b5dc75c3801017807`。[报告](../reviews/pc_a/natural_mask_surface_2026-10-02/REPORT.md)、[验证](../reviews/pc_a/natural_mask_surface_2026-10-02/VALIDATION.md)、[命令](../reviews/pc_a/natural_mask_surface_2026-10-02/COMMANDS.md)。用户明确授权发布后，代码与完整证据提交 `992724e8698ab114e708b0c6f88bfb636f514e12` 已推送；[草稿 PR #95](https://github.com/goneveitvet240-svg/cpswm/pull/95)叠加PR94，未合并。本次追加仅确认交接，冻结功能源码不变。此前自动审批两次拦截证据包公开发布，已由用户本轮明确授权解除。

一屋16帧/14组RGB冻结比较：WineBottle离线首帧参考，mask内原光流表面点11/11、3/5盒内，末2帧永久丢失；旧constant-soft为0/16。10条初始轨迹/80记录全留，49有点/31未知丢失；碗0/16命中及类别误识保留。不是正式自然身份或联合任务成功；两模型/分辨率同时改变，非mask单因素消融或同计算预算优势。新组件无Native/记忆权限，旧默认保持。

顺序R1 89项、R2既有事务定向2项通过，零跳过；mypy401/Ruff/format819通过，938冻结文件未变。run/fresh33输出和评分一致；独立复算76+49点、7038 AABB成员关系通过。封存106文件14.4MB含实际消费raw/SDK/masks/评分/日志，不含权重但提供完整pin。非B/全仓验收，不宣称新mask已接事务。

下步将可变表面feature谱系与相关观测模型对齐，再接撤回/重放；当前选点会换feature，不能强当静态中心累计。实际同任务同动作预算主动澄清、后续记忆收益未完成；完整统一框架保持。恢复树fetch核对集成19ddf26830348a2f0b33f0af54d6ba702c5cfb1c、B fd4ca6ef5e81c90d7cf7987b42c0b2810d8a810a；原树fetch失败另留，不改原树源码/STATUS_B/共享集成、不自动合并。

---

# 2026-10-02：推进自然掩码表面支持

A分支 `codex/pc-a-natural-mask-surface-20261002`，base PR94 `01c52fef24d5fafc95bf8f6584602771aa176d5c`，增加固定RGB实例分割与深度读点对照，保留旧模型/全部候选/未知。[计划](../reviews/pc_a/natural_mask_surface_2026-10-02/PLAN.md)。尚无新结果，未更换默认或运行时真值权限。完整框架、同预算任务及后续记忆验证范围保持。

---

# 2026-10-02：位置校准首轮完成，表面对应仍阻断自然任务

交付：[草稿 PR #94](https://github.com/goneveitvet240-svg/cpswm/pull/94)，叠加PR93，未合并。代码与完整证据提交 `cfc70b4779a6847a5d25ae1739683aec06de4287` 已推送；功能仍为 `27d396d6db4c248992f37285d3b7ad42b20df408`。本次追加仅确认交接链接，不改变已验证源码。

A分支 `codex/pc-a-position-calibration-20261002`，功能 `27d396d6db4c248992f37285d3b7ad42b20df408`；[报告](../reviews/pc_a/position_calibration_2026-10-02/REPORT.md)。用户校准授权已落实；六模型、完整96帧run/fresh与独立算术一致。新检查27、旧报告/连续事务兼容49通过，范围和版本分开。自然首点错误、软读出混入背景、旧先验收缩都保留；新校准优于旧受控模型但劣于原始表面读数，未提升为默认或接新Native。主任务定义不变，主动与后续记忆收益仍未跑。等待B对最终交接SHA独立复核；完整框架不缩减。

---

# 2026-10-02：位置校准已获用户批准

A在 `codex/pc-a-position-calibration-20261002` 开始表面对应检查和训练/评测分离的位置先验、误差校准，base `5073311fbd9aa5cdc0520876d2b34b02ab92c8b1`。保留旧受控对照和三项已批准任务定义。[计划](../reviews/pc_a/position_calibration_2026-10-02/PLAN.md)。尚无新结果；下方新先验待批准为历史状态。

---

# 2026-10-02：联合报告评分已接通，位置模型仍阻断任务成功

交付：[草稿 PR #93](https://github.com/goneveitvet240-svg/cpswm/pull/93)，叠加PR92，未合并。代码与证据提交 `5b6d6fc3a5322c1270aac5441622ba9ea48bd5b2` 已推送；冻结功能源码仍为 `10af59aba3a26bbbe66346b1bee89ae9b0a55de1`。

A独立分支 `codex/pc-a-joint-report-evaluation-20261002`，源码 `10af59aba3a26bbbe66346b1bee89ae9b0a55de1`。用户三项任务定义已批准；owner报告/撤回、隔离身份＋AABB评分、同清单预算汇总局部实现，26/37顺序检查通过。[报告](../reviews/pc_a/joint_report_task_2026-10-02/REPORT.md)。旧真实输入的位置报告明确失败，原始读数与受控先验均存在问题；新先验/误差校准方案待用户决定。主动与后续记忆收益仍未实验，非B/全仓验收，不改统一范围。

---

# 2026-10-02：首轮后续任务已确定

用户选定“找对物体并报告可复查位置”，采用身份＋位置联合成功，分别报告两项结果。A独立分支 `codex/pc-a-joint-report-evaluation-20261002`，base `5907f85b5b3171fd1c71121c095d4589dc7339ae`；[方案](../reviews/pc_a/joint_report_task_2026-10-02/PLAN.md)已具体化表面点输出和评估隔离。用户也已批准三维包围盒开发评分判据；三项定义均已确定。正在实现报告/评估，收益比较尚未运行。

---

# 2026-10-02：用户选定身份＋位置联合成功

正式主成功方向已确定：找对具体物体且位置满足后续任务要求，分别报告身份与位置结果；[比较协议](../reviews/pc_a/joint_target_observations_2026-10-02/COMPARISON_PROTOCOL.md)已更新。原成功方向待选择项解除。首轮后续任务和相应空间判定仍待确定，任务损失及实际动作结果模型待接线，主动观察/后续记忆收益尚未验证。

原PR92分支续接，仅文档变更；本次base `98560609501dfe8bab2b37cfd4bd4c4d9f11ba5e`，功能源码仍为 `ccccacc8ced5245ee6c38b2466632bac37d37cd0`。不改变完整框架或双机分工。下方待选择条目为历史时点，不覆盖本次用户决定。

---

# 2026-10-02：联合观测路线已批准；连续事务局部交付

交付：[草稿 PR #92](https://github.com/goneveitvet240-svg/cpswm/pull/92)，叠加 PR91；代码与原件提交 `24c7e352e071af06aa245bf1c65f8ff6b54df6c7` 已推送，冻结被测功能源码仍为 `ccccacc8ced5245ee6c38b2466632bac37d37cd0`。

`codex/pc-a-joint-target-observations-20261002`，冻结源码 `ccccacc8ced5245ee6c38b2466632bac37d37cd0`，base为PR91的 `ee4fc7c0885d7fcd12c26525d3a33a56892323b8`。相关多帧条件更新、重复证据去重、回滚、语义与采集撤回重放接通；顺序33/61定向检查通过、零跳过，非B或全仓验收。[报告](../reviews/pc_a/joint_target_observations_2026-10-02/REPORT.md)。

真实Unity首帧更新后策略停止，实际主动澄清/后续记忆收益仍未建立；下一项为由用户确定澄清任务成功判定、接通任务损失与实际动作结果模型后执行配对预算比较。原“相关证据方法待选”已解除；完整框架及双机分工不变，不自动合并共享集成分支。

---

# 2026-10-02 当前独立工作分支补充

`codex/pc-a-continuous-target-20261002`，实际源码19986b08c7605f84e73533cf71a7efa776a0a20d。A完成连续自然候选支持的单屋局部验证；[报告](../reviews/pc_a/continuous_target_2026-10-02/REPORT.md)。阶段二相关证据处理方法待用户答复，阶段三同任务/同预算的实际澄清和记忆收益未执行。未合并/未B验收/未改集成分支，原分工和完整统一范围保留。

---

# A：关联分支已接入；真实跨视角匹配仍未成功（2026-10-01）

交付：[草稿 PR #90](https://github.com/goneveitvet240-svg/cpswm/pull/90)，叠加 PR #89；代码及证据提交 `bc0fdaa47640729ce6274e7c61a10e3a7da42b89` 已推送，实际被测源码仍为下述 `5a4e3a0…`。

用户已同意未校准外观＋三维几何基线，解除此前待答复项。分支 `codex/pc-a-appearance-geometry-association-20261001`；base `0a5e38c0e59ce2a42342925be7dc5de6fc994c19`；实际功能/测试源码 `5a4e3a0660114b3e7bc5b2482f4d49456b825239`。开工 fetch 核验集成 `19ddf26830348a2f0b33f0af54d6ba702c5cfb1c` 与 B `fd4ca6ef5e81c90d7cf7987b42c0b2810d8a810a`。

新增原始 owner 参考—查询帧关联：参考只作为条件，查询多个候选/未知分别进入真实 Native 后验及条件统计；旧对照保留；原事务承担去重、回滚、语义撤回重放及 fresh 恢复。观测依赖的未校准关联能量计入观测项，不冒称转移先验或身份概率。

同源码顺序 A 自审 R1 **21 passed / 349.97s**，R2 **62 passed / 526.61s**，零跳过；mypy 394 源文件无错误；ruff 全 src/tests 通过、803 文件 format 通过；926 项冻结源码清单不变。两轮均非 B/全仓，core 环境非独立重建。[本轮报告](../reviews/pc_a/appearance_geometry_association_2026-10-01/REPORT.md)。

实际 Unity 1 屋3次诊断、6次模型动作/6帧（5组不同 RGB 字节）：15+15° 与30+5°均不同类别→未知，无已知位置更新；30+1°无候选→拒绝并回滚。**真实跨视角关联成功为零，不作成功率估计**。三份实际 DB 新进程核验：两份恢复一致，一份复核原始交付保留、再次拒绝且后验/语义/producer/SQLite 不变。瓶子原分数30°约0.514、31°约0.258，既有0.5阈值未改；事后 SDK显示仍可见，仅作离线诊断，未进入方法输入。

下一主项：稳定相邻视角的候选支持并保留未知/原对照，再扩展第二、第三次查询的相关证据事务。本 profile 仍只消费一个帧对；初始语义锚定/人物/先验/残差/效用受控，长期自然身份、校准、实际任务收益、全仓与 B 验收未完成。原用户工作树/STATUS_B/统一科学范围未改，不自动合并。

---

# A：自然候选后验接线通过双审与实时 Unity（2026-10-01）

分支 `codex/pc-a-natural-candidate-update-20261001`，base `0061bf82c5db70367f8afa513478e3e86c4ca470`，实际功能源码 `63b053fa30a508a0c73dcff44d47a645f5a1362f`。开工 fetch 核验集成 `19ddf26830348a2f0b33f0af54d6ba702c5cfb1c`、B `fd4ca6ef5e81c90d7cf7987b42c0b2810d8a810a`。

新增自然检测候选 profile：从 owner RGB 重新执行固定官方 SSDLite，RGB-D 重建完整候选/网格，再按公开固定规则将一个读出接入原单测量事务。拒绝 caller 框/seed/分数/XYZ，空候选与无效深度不更新但保留交付、允许后续有效 capture。原受控 profile、完整统一框架及任务对照保持。

冻结后顺序 A 自审 R1 35 / R2 73 passed；392 源文件 mypy 无错误，1022 项冻结源码清单未变。真实新 Unity 一次 RotateRight→1 个自然 bottle 候选/64 有效网格→后验更新→重新决策停止通过；实际 DB fresh 新解释器恢复一致、无重拍/语义重跑。见[报告](../reviews/pc_a/natural_candidate_update_2026-10-01/REPORT.md)。开发恢复装配错误及修正前失败保留；非独立 B/全仓。

身份仍为受控关联假设，不把 bottle 类别或检测分数当作目标身份。新增外观/三维关联开发基线的用户选择仍待答复，依赖该选择的部分未实施；多帧相关性、自然身份概率、校准、跨机持久化迁移及任务收益仍开放。原用户树/STATUS_B 不改，经独立分支和草稿 PR 交付，不自动集成。

---

# A：同语义新观测事务与一次实时 Unity 闭环通过（2026-10-01）

分支 `codex/pc-a-owned-observation-update-20261001`，base `cab777ff69c250696611a65e387aa305f7b5f30d`，实际功能源码 `d84d570d0c12ec56d5f47f699f7211ffd99422b9`。已 fetch 集成 `19ddf26830348a2f0b33f0af54d6ba702c5cfb1c`、B `fd4ca6ef5e81c90d7cf7987b42c0b2810d8a810a`。主线开发与全仓诊断分开推进。

新增单测量 owner RGB-D 原子消费：同语义更新真实后验及条件统计、重复去重、计算失败回滚保留物理交付、SQLite 不确定恢复、按更新序列/历史 cutoff 撤回重放，默认 collector 接线。冻结源码顺序 A 自审 R1 32 / R2 44 passed，391 源文件 mypy 无问题；1020 项源码清单未变。两轮非独立 B，非全仓。

实时 Unity 首尝试 READY 前超时，旧 SDK iCloud 文件导入实际 122 秒，保留失败；按旧版本约束建立独立本地 SDK 后，一次真实 RotateRight→RGB-D→后验→下一决策停止通过。实际 live DB 新进程恢复一致，无重发动作。详[报告](../reviews/pc_a/owned_observation_update_2026-10-01/REPORT.md)及其中逐项证据。

仅受控单次工程闭环：固定候选/身份/先验/残差/动作效用，第二测量明确不支持；自然身份、多帧相关证据、校准和行为收益仍开放。全仓工程验收、独立 B、旧回执缺口保持。下一步自然候选/身份接入后再评价任务收益，不以归档或测试数量代替。原用户工作树和 STATUS_B 未改；交付经本分支/草稿 PR，不自动集成。

---

# A：全仓执行对账通过两审，远端完整执行待完成（2026-10-01）

分支 `codex/pc-a-regression-completion-20261001`；base `9a4955811be33a2d6443f4c9e13426639a85d551`；实际源码 `d9d409bedd1cae074ef5459307c236de0a872b46`。CI 加入逐节点终态/源码对账，测试执行预算明确 65→180 分钟，准备仍 120 分钟；不改断言或科学阈值。原失败全部保留。

最终同源码顺序 A 自审 38/38 passed，1120 文件摘要不变；实际全仓仅收集 6783 项。旧 6758 项真实产物仍 2040 缺失，4 匿名不计通过；不称全仓/独立 B/严格回执验收通过。修前重复清理错误及匿名计数缺陷另存。[报告](../reviews/pc_a/regression_completion_2026-10-01/REPORT.md)。

原 7 项过期 checkpoint、完整运行及验收材料缺口仍开放。下一步依据完整终态修复回执/失败，再做新 capture 更新事务。源方法、统一范围、用户原树及 STATUS_B 未改。当前交付待远端运行结果。

---

# A：清理探测竞争修复通过双审，整体工程仍未验收（2026-10-01）

分支codex/pc-a-cleanup-probe-20261001，base b0ed673da4d6a577338a904c5d25152730eb294c，实际源码34b66c3496b036da2f3a9ba7d7243180f39354ab。原版受控复现2失败；保持原5秒期限重试瞬时EPERM，持续拒绝仍报错。顺序A自审R1 3 passed、R2 27 passed，1118源/配置/工作流/锁摘要不变，实际收集6760；非独立B/全仓。详[报告](../reviews/pc_a/cleanup_probe_2026-10-01/REPORT.md)。

父fd08b59回归实际4687通过、1失败、29跳过、1 xfailed，65分钟超时124且2040节点无具名终态，原件已完整对账保留。父报告已顺序并入各叠加分支，未覆盖原用户工作树或STATUS_B。原7项过期checkpoint失败、完整执行和验收输入缺口仍开放；最新CI待实际完成，新capture原子事务尚未启动。

本轮及前序修复分开绑定SHA，不把历史/局部通过当作新HEAD的全仓通过。完整统一研究范围、原分类/主动澄清及科学阈值保持。

---

# A：为真实输入准备配置独立预算，远端全链待完成（2026-10-01）

分支codex/pc-a-validation-budget-20261001，base3644873f74c34e3ace340d544a3f25faa189493e，实际源码5a6cce24d633acea5e690f47667cdf57b95465c1，仅改CI工作流。真实CI36847860851在准备第4步65分钟超时124，未发布成功输入、test未运行；改为独立120分钟准备预算，保留原65分钟全仓测试与全部重算。顺序R1 28 passed、R2生产执行器真实成功/失败/超时探针通过，非实际Linux全链通过。详[报告](../reviews/pc_a/preparation_budget_2026-10-01/REPORT.md)。

父分支材料/依赖修复见草稿PR83/84；本机fd08b59完整回归已超时并完成逐节点对账，不混用本候选源码。工程回执、全仓终态和新观测事务仍未闭合；无新科学收益声明。原用户树、STATUS_B及完整统一研究范围不改。

---

# A：原生审计依赖契约修复，整体工程仍未验收（2026-10-01）

独立分支codex/pc-a-audit-environment-20261001，base c8f1d29b90b60ef4ddc5303628c87def428d1d1b，实际源码488c7a62e5562e340b61bbe735c1c2bad858933e。原生审计只读uv检查补齐perception/hand-perception，与CI一致；冻结后顺序R1/R2真实命令正路径、旧契约拒绝、缺必需依赖拒绝及恢复后正路径通过。现有契约测试1 passed，变更文件lint/format通过。非全仓/独立B/科学收益验收。详[报告](../reviews/pc_a/audit_environment_2026-10-01/REPORT.md)。

父fd08b59的6758项回归已超时：4687通过、1失败、29跳过、1预期失败，2040节点缺少具名终态。工程历史回执过期与新增运行时失败仍待闭合，未开始后续新capture事务。原用户工作树、STATUS_B与完整统一范围保持。

---

# A：当前材料功能已交付，完整回归超时仍未验收（2026-10-01）

分支codex/pc-a-current-validation-inputs-20261001；base3d6b9f13cf4e71a482cf36974be92220602542b0，实际功能fd08b59bdc01ca9ffe4e9b159cb1393052711d15。顺序A自审R1 162通过、R2八阶段真实准备2552.77秒通过，真实CLI合法包及21完整伪造核验通过。非独立B。详[报告](../reviews/pc_a/current_validation_inputs_2026-10-01/REPORT.md)，草稿PR83，未合并。

本机完整收集6758，65分钟实际超时124：4687 passed、1 failed、29 skipped、1 xfailed；4718具名终态、4匿名中断记录不计通过、2040节点缺少终态。1117源/配置/工作流/锁摘要不变。原31失败本轮仅8项有通过终态、23未观察到；不能声称31项关闭。单独当前checkpoint仍7 failed/8 passed，旧回执未闭合。

Linux CI36847860851静态通过，新增准备阶段第4步65分钟超时，test未执行。后续独立PR84修复依赖声明、PR85将准备单独设120分钟，原回归65分钟不变；清理竞争的候选34b66c3另行审查，不改本轮失败。新capture原子更新未启动，科学收益/B独立验收仍未完成，完整研究范围保留。原用户树/STATUS_B不覆盖。

证据/private/tmp/cpswm-current-validation-evidence-20261001；结束后已核对准备包并恢复本工作树P0至原HEAD，当前生成原件及测试journal保留。归档与精确命令见报告。

---

# A：第三候选R1通过，完整材料与全仓回归继续（2026-10-01）

分支codex/pc-a-current-validation-inputs-20261001，base3d6b9f13cf4e71a482cf36974be92220602542b0，实际功能fd08b59bdc01ca9ffe4e9b159cb1393052711d15。R1为162 passed，6758项收集，1027摘要不变。当前源码材料准备、跨进程、完整伪造消费者与全仓仍待完成；工程门槛未关闭。新增有限源码编译缓存仍每次读盘/live代码核对，锁测试从实际handoff起计1s；没有删测试、弱化阈值或延长原回归65分钟。

PR82 CI36836009498已实际65min超时124：4349 passed、2 failed、1 xfailed；4个匿名JUnit记录不计通过，有名结果4352/6738，至少2386项缺少结果。原31失败未全部执行，不称降至2。类型检查Linux已通过；当前P0及锁期限失败继续在本候选核验。详[第二候选记录](../reviews/pc_a/current_validation_inputs_2026-10-01/ADVERSARIAL_REVIEW_2_ATTEMPT_2.md)。旧候选主动中断/取消均保留，不算自然失败或成功。

当前证据output/current-validation-inputs-20261001。原用户树/STATUS_B不改，两轮A同实现者自审，独立B未完成；未启动新capture事务、Unity或行为收益研究。完整统一范围保留。

---

> 更新：R2发现准备阶段缺少内部超时/进程组清理，已修复并重新冻结a8ebb1b0969b871daf079bd0a66f6c6031ef6d85。新R1 61项通过，6751项完整收集，源/工作流/锁共1026摘要不变；新R2真实全链运行中。旧fad9580不再是验收候选，其结果和中间失败保留。准备阶段新增65分钟受控预算，CI任务85分钟留诊断上传余量；原回归65分钟不变。

# A：当前验收材料第一轮通过，第二轮实际流水线验证中

分支codex/pc-a-current-validation-inputs-20261001；实际功能fad9580a81edd6d9e35b249ff186f3f63819d393，base 3d6b9f13cf4e71a482cf36974be92220602542b0。R1同实现者A自审60项通过，严格mypy389文件/格式通过；R2正在执行真实比较生成/重算/归因重算与当前科学循环、P0准备全链，未通过前不进入下一轮功能修改。当前CI新增独立准备job，回归仍完整收集、保留65分钟预算和所有失败，不弱化保护。当前材料准备不等于工程回执通过。

[依赖与新增阻断](../reviews/pc_a/current_validation_inputs_2026-10-01/ENGINEERING_DEPENDENCIES.md)：工程回执要求零skip/xfail，而全仓含平台限定/显式实数据用例和项目一已知RLS strict xfail；不得靠降低阈值或重签旧回执消除。正式全仓/严格工程/科学收益分开。后续新capture事务仍未开始。原用户树/STATUS_B保持，完整研究范围不变。R2证据output/current-validation-inputs-20261001/review2-prepared；真实执行和Linux CI后更新结果，不提前计通过。

---

# A：当前验收材料与完整回归接线开工（2026-10-01）

分支 codex/pc-a-current-validation-inputs-20261001，base/开工源码3d6b9f13cf4e71a482cf36974be92220602542b0（PR82），独立工作目录。远端集成19ddf26830348a2f0b33f0af54d6ba702c5cfb1c、B fd4ca6ef5e81c90d7cf7987b42c0b2810d8a810a 已核对。PR82全仓CI仍运行，未计通过。

本轮先建立真实当前比较包与测试材料准备、核对工程回执依赖并完整执行回归；不重签旧结果、不弱化验证、不用skip掩盖缺口。实施后冻结源码，顺序两轮同实现者A自审，独立B仍待完成。证据output/current-validation-inputs-20261001；原用户树和STATUS_B不改。工程门槛未通过前不启动新观测事务或科学收益实验。保留完整统一范围及用户既有研究选择。

---

# A：工程回归首批修复，整体验收仍阻断（2026-10-01）

分支 `codex/pc-a-engineering-regressions-20261001`；base `b6c6317a35c99cd95fe636251ce1e63bfba5f402`，实际修复/双审源码 `8f7edafd51cdf735ca9c65a7c8e4ac367cebdc68`。严格 mypy 155→0（389文件），两项子进程导入和两项有限log下溢契约已本地修复。顺序 A 同实现者自审 R1 283 / R2 120 passed；异目录污染路径2项通过，完整收集仍6738。非独立B/非全仓CI，不能相加为独立覆盖。

[本轮报告](../reviews/pc_a/engineering_regressions_2026-10-01/REPORT.md)。原CI36783640567为31失败和65分钟超时；其余27节点在新建当前锁定实体环境复跑为19失败/8通过，8项Linux失败本机未复现，不计修复。当前P0、比较包、工程回执生命周期及异环境差异仍阻断。原Task-7条件参考字段本机精确一致，不能假定旧CI错误已解决。证据 output/engineering-regressions-20261001，包含失败原件、源码pin和两轮审查。

优先级已按新审核改为：完整工程回归与当前合法材料准备→同语义新capture的原子更新/一次消费/回滚/撤回重放/恢复→行为收益。尚未实施后续观测事务；新训练和Unity实验0次。位置1664相关seed仍仅4屋15帧25对象，房9反例/校正退化保留。完整统一框架及既有分类/澄清对照不缩减。已推送并创建[草稿PR82](https://github.com/goneveitvet240-svg/cpswm/pull/82)，证据交付46c03527e5043dd1e3c419c277eac832f68cdfc6，未合并。最新CI未完成核验；原用户树与STATUS_B不改。

---

# A：工程回归修复开工（2026-10-01）

分支codex/pc-a-engineering-regressions-20261001，base/当前源码b6c6317a35c99cd95fe636251ce1e63bfba5f402。远端CI36783640567为155类型错误、31失败及65分钟退出124；不能以PR76–80局部通过覆盖。失败审计793f5e0c9a20094e9c482dde1ba4d10bd1f0b018已读。先修工程回归，再同语义新观测完整更新事务，随后行为收益；完整统一范围与既有科学选择保持。独立工作树，原树/STATUS_B不改。证据output/engineering-regressions-20261001；实现后冻结并进行两轮明确标记的本机自审，独立B仍开放。

---

# A：当前 owner RGB-D 只读描述已交付（2026-10-01 06:05）

分支codex/pc-a-owned-rgbd-descriptor-20261001，实际功能/双审源码6faa17e178ad001de6b5c0e1094f9e62568d7a7e（903 Python），base父功能82c7a81 / 父交付dc57a687f6cfe0912de7415357765fff79f2c2ff。顺序R1/R2同源码通过，详[报告](../reviews/pc_a/owned_rgbd_descriptor_2026-10-01/REPORT.md)和[交付](../reviews/pc_a/owned_rgbd_descriptor_2026-10-01/DELIVERY.md)。A辅助、非B独立/全仓CI。

实际owner prepare/execute/accept的受控RGB-D描述、完整typed派生替换拒绝、stale、有限log但显示零概率父支持、SQLite新进程与无新增后验/动作/DB副作用已按报告核验。仅新增两文件，posterior_updated/consumption_authority均False。允许旧Native证据复核重算；不消费新capture，不提供owner相关原件一致替换的独立历史认证。证据244成员，SHA256 d9e925c3ac86042e8bb724709540a5448b76bea53f57897aac0f8faa976aeb98；全部读回、失败与原DB保留。

六小时主线已形成：公开特征对照→软表面三维/残差模型→实际归档四模型Native消费/撤回/恢复与裸点配对对照→当前owner原件描述。父PR79已推送；本轮草稿叠加它，不自动集成。仍缺同语义后续新capture的原子Native更新；下一轮应整体实施接收锚、消费一次、失败回滚、重放/撤回/fresh，不用重发semantic绕过。自然I/朝向、正式prior/unknown/时间相关性、任务收益和B验收保持开放，完整统一范围与原对照保留。

---

# A：实际位置归档到 Native 桥接与裸 seed 对照完成（2026-10-01 05:46）

本轮分支codex/pc-a-archive-native-bridge-20261001，实际源码82c7a81fba0c3af3688978ce222b1b94e4cc5bd9（901 Python），base父功能1bd6c20 / 交付df8e30bd7eb436444b191ea242e938c8948d08a1。两轮顺序对抗审查绑定同源码；实际bridge: run 761.56s / verify 722.54s / 76 files；bare: run 354.22s / verify 398.48s / 103 files，四次成功，原件不变。R1 180不同测试，R2完整覆盖/限制见报告；A辅助非B独立/全仓CI。独立数值检查与图表已完成，case pin 328b4b10276c44a05b91cfcbb7f24d370ff8092e85a9fe729939311bc6b4fc42。

真实RGB-D原件、公开读出及四模型改变受控Native的likelihood、log权重和Gaussian信息统计；8臂重复/中性继续/撤回及16次SQLite新进程验证，fresh重新复算并验证原数据库副本。身份/语义/prior/unknown仍合成，frame000来自训练屋，本轮0物理相机命令；不是自然在线闭环或动作收益。

配对位置结果：sdk_transform_position_m: bare_seed 0.750330→0.661757m (n=1664), soft_affinity 0.674738→0.615581m (n=1664), uniform 0.833717→0.785566m (n=1664)；sdk_aabb_center_m: bare_seed 0.549088→0.561687m (n=1664), soft_affinity 0.513540→0.523058m (n=1664), uniform 0.712308→0.711919m (n=1664)。所有96帧、空/VOID保留，样本强相关，两种参考目标并列，不选正式目标、不声称独立校准。详[报告](../reviews/pc_a/archive_native_bridge_2026-10-01/REPORT.md)、[交付](../reviews/pc_a/archive_native_bridge_2026-10-01/DELIVERY.md)。证据11429成员/342551816压缩bytes/SHA256 807e4ab4a2ae1cd9551edcf8d20faecf52d6ab2ec4504c0f7739fc0c408bce4f，全部读回，失败与原DB均保留。

下一主项是同一semantic source后续owner capture更新与逐cluster重放，当前尚未完成；设计已列原子范围，不以archive消费替代新观测。自然I/未知模型、正式参考与prior/时间相关性、朝向、长时程、完整任务效用、公平对照与B验收继续开放。完整H/R/I/C/Z/r/V、三个RB blocks、七算子、分类对照与主动澄清不缩减。原用户树、STATUS_B不改，当前仅草稿PR交接，不自动合并。

---

# A：位置观测开发与受控原生消费已完成（2026-10-01 04:32）

分支codex/pc-a-soft-position-factor-20261001，base PR77 head8623e7890594fce2b3c872bd2484b30138a9f408；实际源码1bd6c204d349024196c23df12cca61dbcea91e6c，895 Python。174项最终开发回归、新R1 68项、新R2 35项不同测试通过。早期493观测似然完整替换缺陷、379显示下溢后log(0)、首次171组合helper误拒绝均保留且阻断原版，不用后续通过抹去。最终保护保留完整raw重算/父链/core锚及loaded code检查，增加原始log权重继续支持。

真实12屋96帧四模型拟合；run324.36s/fresh326.64s exit0、302输出逐字节一致，独立像素几何/监督/残差/指标/高斯更新复核通过。2004train/1664validation监督seed，55/96无监督帧保留。验证RMSE(m)：soft pivot .674738→.615581；soft AABB .513540→.523058；uniform pivot .833717→.785566；uniform AABB .712308→.711919。去bias有改善也有退化，两参考并列，不选正式参考/声称校准；需裸seed基线、自然关联与任务效果。

[报告](../reviews/pc_a/soft_position_factor_2026-10-01/REPORT.md)、[交付](../reviews/pc_a/soft_position_factor_2026-10-01/DELIVERY.md)。完整原件9295文件/3713960160bytes，压缩427706204bytes，SHA256 fa7620a0b1ba5f522db4fdf10d8e1778fcf83adb7608b5facc402984b808174f；全部读回，日志/失败/模型/DB保留。case ledger pin9b9ed2d9208c1907d8295d5edc5aeb2f48af7b9b3625108b9642430a06780efc。A辅助非B独立/全仓CI；真实四模型仅进入数值诊断，Native消费/撤回恢复仍是受控像素/模型测试，不能合称真实模型已进Native。

下一独立分支codex/pc-a-archive-native-bridge-20261001已从通过双审源码隔离开工：实际归档/四模型Native桥接、重复/撤回/SQLite恢复，保留原raw字节、合成语义关联明示。尚未冻结双审/实数据验收。逐raw观测事务、自然I、朝向和行动收益继续开放。原分类对照/主动澄清及完整H/R/I/C/Z/r/V、三RB块、七算子保持；原树与STATUS_B不改。交付前fetch确认集成19ddf26830348a2f0b33f0af54d6ba702c5cfb1c、B fd4ca6ef5e81c90d7cf7987b42c0b2810d8a810a未变。

---

# 位置因子第二次冻结：完整历史检查通过，数值继续路径阻断（2026-10-01 03:15）

实际源码 `37981c3c44475b0bcbeff3379dcf90be288c49c9`，894份Python。修复完整raw数值替换后，最终兼容97项、新R1的49项及受控CLI完整伪造拒绝通过；新R2三条完整历史重签与32项恢复通过，但追加合法数值压力失败，当前版本仍不能通过推进门槛。真实96帧位置实验尚未启动。

合法owner配置在首步产生有限LL `-2465.7563115023117`，known显示概率下溢为0；下一neutral语义步骤调用log(0)报错。[二轮阻断与证据](../reviews/pc_a/soft_position_factor_2026-10-01/ADVERSARIAL_REVIEW_2_ATTEMPT_2.md)。不能用epsilon抬高概率或丢掉分支；正在补实际前批原始log权重证据、稳定对数域传递、零显示概率的有效q支持和consumer prior核验，仍从owner接受历史重建。修复后新SHA重新两审。

此次完整历史反例把中间active因子与全部后代q/receipt/state/journal重签：局部neutral后代可自洽，完整workspace仍进入真实位置condition后拒绝错误祖先；core外部锚和READY动作拒绝另外记录。该完整性结果不抵消数值继续失败。A辅助、非B独立/全仓CI/自然任务收益。用户原树、STATUS_B及全部旧失败证据保留，六小时主线继续。

---

# 位置观测因子第二轮审核发现阻断，正在修复（2026-10-01 02:09）

实际被审核源码493e05720f066c5db7173502d03b245bf74b6d43（891份Python）；首轮通过后，第二轮实际发现完整观测似然和未决aggregate自洽替换仍被原consumer接受，导致后验改变。728项冻结前回归不覆盖此缺陷，当前SHA不通过推进门槛；真实96帧新实验尚未启动。

[失败审核与数值后果](../reviews/pc_a/soft_position_factor_2026-10-01/ADVERSARIAL_REVIEW_2_ATTEMPT_1.md)。原packet、配置和模型绑定不变，known概率0.097778可被错误发布成0.444687；完整aggregate替换也被接受。修复须在consumer重算完整观测包并使用真实父链，而非只验证q或增加自签摘要。缺少验证材料不能降级为旧路径。

跨进程恢复的初次失败已定位为测试重新生成配置；使用原持久化配置/模型的独立进程复核exit0，view/state/workspace/ledger一致、重复不增量、下一neutral步骤保留统计。此合法路径不能抵消观测因子的阻断缺陷。完整原件保留output/soft-position-factor-20261001，修复后新SHA重新做顺序两轮审核，再进入原固定实数据run/fresh。当前仅本机修复进行中，非B独立/非统一验收，六小时主线继续。

---

# 2026-10-01 第二轮开工：公开位置读出与受控目标密度消费

A分支codex/pc-a-soft-position-factor-20261001，base PR77 8623e7890594fce2b3c872bd2484b30138a9f408。[协议](../reviews/pc_a/soft_position_factor_2026-10-01/PLAN.md)。做soft/uniform读出、pivot/AABB双3D残差、正确Gaussian预测密度及后验/重放后果；不据验证改正式定义、不直接赋身份或自然权威。每轮仍两审后实数据运行，B边界不变。

---

# 2026-10-01 六小时主线：固定特征对照PR77已交付

A分支codex/pc-a-affinity-controls-20261001，实际功能SHA a6c026963b5fec1503fa0d582fe016eccf60c756；两轮各447、真实run/fresh与独立算术通过，已推送[草稿PR77](https://github.com/goneveitvet240-svg/cpswm/pull/77)叠加PR76，文档/原件交付82bd0c4570279ed65f9f32384e9386686535297a，未合并。联合验证损失低于单组但负类仍高、失败屋保留，非身份或自然因子验收。[交付](../reviews/pc_a/affinity_controls_2026-10-01/DELIVERY.md)。下一主项公开软表面+双参考位置残差+受控目标权重后果，B边界不变。

---

# 六小时主线推进：第一轮固定信息对照

本轮2026-10-01 00:18:40（上海时区）开工，六小时工作窗到06:18:40；按结果推进，不用延时等待填满预算。用户授权继续项目并可作适当选择。工程/开发选择自行处理，完整研究范围、原分类对照、主动澄清、位置+朝向任务保持；新正式身份阈值、对象位置参照与科学指标不在本轮静默指定。

远端fetch已成功：集成19ddf26830348a2f0b33f0af54d6ba702c5cfb1c、B fd4ca6ef5e81c90d7cf7987b42c0b2810d8a810a。第一轮独立分支codex/pc-a-affinity-controls-20261001，base/开工源码为PR76 head ffcaa7b292c73201d799f6631688387409c21cb7；工作树/private/tmp/cpswm-pc-a-affinity-controls-20261001。旧原件与用户工作树保留。

第一轮目标：在同一PR76数据和固定分区下比较rgb_only（原特征0–2）、geometry_only（3–7）、combined（0–7）。不改旧8维学习器，新增明确mode外层契约：禁用列置0、固定相同L2/优化预算，保存原输入与转换后输入摘要、内层检查点及mode绑定，恢复时严格核验。combined应重现PR76原学习参数与分数。本轮是共同候选和样本上的特征组对照：rgb_only仍沿用RGB-D有效性筛选，geometry_only仍条件于RGB检测框，不能称独立传感器系统比较。三模式均使用相同有效监督集合/频率常数；全部公开有效VOID分数、零候选和全VOID帧保留。按帧/屋/分区并分解同/不同实例的BCE与Brier；缺某类为null，不把它记作0损失。仅描述性开发对照，不选正式胜者/阈值。

输入为PR76外部case ledger pin 32e0dc7cec8fce6dfca5bc36755cfba5cf3551b454c1f746f20ac2076936e842及其完整674成员；使用匹配旧源码入口从原PR73/74输入fresh verify原训练结果后再加载。原始RGB-D/私有标签分区和所有来源信任锚不改，不因新增工具重签历史代码或数据。公开预测仅依赖公开特征与冻结模型。整个历史核验可能读取私有验证资料，不冒称恶意进程隔离。

实现及定向测试后冻结源码，顺序R1/R2两轮A辅助对抗审查，包含合法完整训练/搬移、完整模式伪造/改分数指标/删VOID/移植分区等；任何源码修复重新绑定审查。两审后才运行固定真实对照与另进程从头复算，辅助独立数值检查后封存，通过草稿PR交接。A辅助不等于B独立或全仓CI。

后续轮次依结果推进：把公开像素亲和关系形成可重推的软实例支持，接入同一视觉历史并验证纠正/撤回重放；再评估自然实例/位置观察因子的剩余实现与证据缺口。每轮仍先冻结+两审，再运行/交付，不能将soft score直接当作校准P(observation|state)，不能相关像素对相乘重复计证据。若尚不能支持下一正式因子，推进有用接口与校准准备并精确记录阻塞，不编造完整闭环收益。

---

# A：实例像素亲和度首次训练交付（2026-10-01）

已推送并以[草稿 PR76](https://github.com/goneveitvet240-svg/cpswm/pull/76)叠加 PR74 交接，未合并。文档/原件交付 `837c1dc776dbd448999b4a06abd45b087eae9987`；实际双审/训练源码 `0a8a2384c321c3a2dc14cf218854754161af9ffd`，后续交接记录不改变冻结功能字节。分支 `codex/pc-a-instance-foreground-20260930`；base/父 PR74 `d698792a8e3750af284a2c991a28aff2453b0729`；实际双审/训练源码 `0a8a2384c321c3a2dc14cf218854754161af9ffd`。新增三模块/三个测试文件，875 份绑定 Python 源码与实际运行一致；后续文档交付 SHA 单列。

固定 12 屋 96 帧公开 RGB-D 配对开发模型已实际训练：8 屋 38,993 个合格训练对、4 屋 35,735 个开发验证对，验证 BCE 0.445967→0.298310、Brier 0.135510→0.087341，相对同训练频率常数。首次 run 及另进程从头拟合 verify 均 exit 0，674 输出逐字节一致；另写公式对原 mask/特征/标准化/预测/统计复算一致。两轮顺序 A 辅助审查各 344 passed，Ruff/格式通过；非 B 独立、非全仓 CI。

352,719 个公开对中 277,991（78.8%）为 VOID，全部预测保留；38/96 帧无候选。验证屋 9/10 只有 0/6 个负对，训练屋 4/6 反而劣于常数。159 个可见合格实例仅 80 个进入有效监督对（验证 23/41）；这是采样覆盖，不是实例分割准确率。配对相关、来源已开发曝光，没有新场景或正式科学收益证据。

[报告](../reviews/pc_a/instance_foreground_2026-09-30/REPORT.md)、[交付](../reviews/pc_a/instance_foreground_2026-09-30/DELIVERY.md)、[复现](../reviews/pc_a/instance_foreground_2026-09-30/REPRODUCE.md)。完整原件 5,112 文件 / 332,673,503 字节，压缩 21,047,249 字节，SHA256 `4ae753a03fd1237e86fa548db7290143daa7ee73d0a51b36055cb504865e324e`，全部读回且无排除。本机 `output/instance-foreground-20260930`；开发首轮 3 个 setup errors 与独立脚本首次 Git mmap 超时均保留，生产源/原件未为复核改写。本轮复用 PR73/74 原件与检测缓存，没有重新启动 Unity/运行检测器。授权离线标签用途仍有效。

下一主项：同数据固定 RGB-only/geometry-only/combined 对照及逐屋/正负类诊断，再形成可用软实例支持。当前不是完整 mask、跨视角身份、正式位置/朝向观测或校准似然，不能直接写入自然联合目标密度；自然因子、B 独立、全仓 CI 和动作收益未关闭。正式身份规则/位置参照/阈值不擅自指定，位置+朝向、原分类对照、主动澄清及完整统一范围保持。

交付前再次 fetch 核对：集成 `19ddf26830348a2f0b33f0af54d6ba702c5cfb1c`、B `fd4ca6ef5e81c90d7cf7987b42c0b2810d8a810a`、父 PR74 上述 SHA 均未变。STATUS_B 与用户原工作树未修改。以下为历史时点，不能覆盖本节训练结果。

# 渲染实例像素亲和度开发基线开工

分支codex/pc-a-instance-foreground-20260930；base/开工源码d698792a8e3750af284a2c991a28aff2453b0729（PR74）。开工fetch已核对共享集成19ddf26830348a2f0b33f0af54d6ba702c5cfb1c、B当前fd4ca6ef5e81c90d7cf7987b42c0b2810d8a810a未变。用户主工作树保留。

用户已批准离线实例/mask/位置训练校准并继续实例前景下一步。本轮从固定PR73采集与PR74两前端公开预测构建像素对监督，训练一个小型logistic regression开发基线。每个公开框8×8固定网格，取像素中心在半开框内的唯一点，保留全部无序不同点对；按动作与规范像素对跨候选/前端去重，候选来源另存，不用私有mask挑点。全部96帧/零候选/无效深度保留。

特征仅公开RGB颜色差、像素相对距离、深度差/对数深度差、相机几何世界点距离。两端各自唯一属于合格渲染mask时，同实例=1、不同实例=0；无mask、冲突、任一不合格或公开深度无效均VOID。SDK ID/类别/asset/位置/分区不进入模型。原房屋1–8训练、9–12开发验证；同一去重训练有效集计算标准化与常数频率对照，固定L2=0.01、固定优化预算，无验证选型。

产物保留全部公开预测、监督、checkpoint、训练常数对照、逐屋与总体BCE/Brier描述性诊断。单类/无有效监督显式拒绝拟合，不把无标签屋计为零损失。输出是未校准的同渲染实例亲和分数，不保证传递性、完整mask、候选目标选择、跨视角身份、物理表面或自然似然。本轮不改线上任务路径/正式阈值/对象参考点，不填造朝向；位置+朝向、原对照及完整统一框架保留。

先完成实现与定向验证，冻结源码后顺序两轮A辅助对抗审查，再在固定真实归档训练及新进程复算。A辅助不是B独立验收。原件output/instance-foreground-20260930；GitHub草稿PR叠加PR74交接。下一主项仍为可用实例观测支持、位置模型与原生目标密度接线，不能把本开发基线称完整闭环收益。

# A：固定96帧公开前端诊断交付（2026-09-30）

已推送并以[草稿PR74](https://github.com/goneveitvet240-svg/cpswm/pull/74)叠加PR73交接，未合并。文档/原件交付62c98fb87cc28b6fe7640909c0df24ebc218c7d3；实际双审/运行源码3babc6d1557b4fe54abc6c8ac1f6054cdeb03e57，后续交付未改生产/测试/工具/依赖字节。

分支codex/pc-a-offline-front-end-20260930；base为PR73 head 5a2a963d7f3b9fc8c3084e0b50d1696b2a7314f2，实际双审/实归档源码3babc6d1557b4fe54abc6c8ac1f6054cdeb03e57。新增两个诊断工具和两个测试；生产src、依赖、权重及原采集数据不改。869份源码摘要运行前后匹配。

同一12屋96帧，Faster R-CNN与SSDLite各首次运行和新进程完整重推，四项exit0且结果一致。两轮顺序A辅助审查各231 passed，Ruff/格式通过，完整正路径与伪造原件保留。非B独立、非全仓CI；本轮没有新启动Unity。

503合格对象中159可见；两方法任意框交叠81/65、样点命中48/20；至少两个实际相机航向样点命中9/3。105/109与67/67框交叠多个SDK实例不是误检数量。mask覆盖非身份识别，表面点到pivot/AABB距离非位置校准误差。固定视点只转yaw，没有平移视差，当前验证来源已经用于开发诊断。

完整原件229文件/206306336字节，压缩14530311字节，SHA256 19f379aefd42434e311bba00b5116fdc9f562f73982b67e280244bf038742177，全部逐件读回无排除。[报告](../reviews/pc_a/offline_frontend_2026-09-30/REPORT.md)、[交付](../reviews/pc_a/offline_frontend_2026-09-30/DELIVERY.md)、[复现](../reviews/pc_a/offline_frontend_2026-09-30/REPRODUCE.md)。本机原件output/offline-front-end-20260930。

离线实例/掩膜/位置训练校准用途已获批准，线上仍仅RGB-D与自位姿。下一主项为实例级前景监督与自然观测支持，再推进位置模型/校准/目标密度和主动闭环。正式位置参照尚未选择，不能填造朝向凑6D；位置+朝向、原分类对照和完整框架保持。训练、自然因子和科学收益尚未完成。

交付前fetch核对共享集成19ddf26830348a2f0b33f0af54d6ba702c5cfb1c、B当前fd4ca6ef5e81c90d7cf7987b42c0b2810d8a810a、父PR73 head未变；通过草稿PR叠加PR73交接，未合入集成。以下历史状态不覆盖本节。

# 固定新数据的公开前端诊断开工

分支 codex/pc-a-offline-front-end-20260930；base／开工源码5a2a963d7f3b9fc8c3084e0b50d1696b2a7314f2（PR73）。fetch核对共享集成19ddf26830348a2f0b33f0af54d6ba702c5cfb1c、B当前fd4ca6ef5e81c90d7cf7987b42c0b2810d8a810a未变。主用户工作树与历史原件保留。

目标：在已封存collection-attempt02的固定12屋/96帧上，先仅用公开RGB-D/自位姿运行既有Faster R-CNN与SSDLite，使用既有权重和默认0.5开发筛选设置；随后用私有完整实例目录评价全部候选×实例的像素归属、可见目标覆盖、背景与多实例混合、表面点至SDK原点/AABB中心的原始距离。原生COCO/SDK词表分别记录，不临时映射标签或据验证集调整阈值。不调用自然任务策略，不以任意重叠称正确识别。

历史数据外部inventory pin：9791a946543b9158890324d3ff35a80ea04d51c9cabb6e09540f569abd903d47。先使用匹配历史采集源码/环境的CLI复核，再用本轮源码做公开推理和完整评价；不能为了适配新增工具而重签历史configuration。两种方法使用全部相同保存帧，零候选、不可见、重复和失败全部保留，按房屋/资产及对象帧次描述依赖。

批准的离线标签用途继续有效。位置+朝向科学目标、原对照、三个RB blocks、七算子和完整框架保留。当前轮不假定表面点即对象中心，不填造朝向，不拟合形式不符的6D误差，不新增正式成功阈值。先冻结代码、顺序两轮A辅助对抗审核，再运行实数据；发现代码问题后重新冻结复审。A辅助不是B独立验收。

原件output/offline-front-end-20260930；完成后GitHub草稿PR叠加PR73交接。下一项依此结果实现适配既定状态定义的自然观测因子，不把诊断完成写成模型训练完成。

# A：已批准离线实例／位置数据入口交付（2026-09-30）

已推送并以[草稿PR73](https://github.com/goneveitvet240-svg/cpswm/pull/73)叠加PR72交接，未合并。文档／原件交付 b9d6b6e7e095b1c91873d9d7af60f0182282ac1f；实际双审与采集源码 e88f50752ca50843fc5382b853c65abe134f1281，交付时865份绑定源码摘要一致，生产／测试／工具／依赖字节不变。

用户“选择1”已生效：仿真实例ID、mask、位置可用于离线训练／校准；线上仍仅RGB-D与相机自位姿。该用途不再是待决权限。完整统一框架、三个RB blocks、七算子、原对照与正式任务效用保留。

分支 codex/pc-a-offline-factor-data-20260930；base 0ce10502e8c2292c6d7b34dcbf62f795133ad4c4；实际双审／采集源码 e88f50752ca50843fc5382b853c65abe134f1281。五工具／六测试共160 passed、零跳过，Ruff／格式通过，顺序两轮A辅助对抗审查完成。第一批12项失败及修复前两种完整伪造漏洞全部保留；第二批固定12屋verified、exit0，96公开帧、144 SDK事件，外部inventory pin CLI复核exit0。

最终数据资格503对象（训练411／验证92），实际mask可见159对象（118／41），253对象帧次；96不同输入组合仍按12房屋／资产聚类。全部1618 SDK实例与594原空assetId保留，派生组件／建筑没有目标资格。目标资产隔离不等于全场景资产不共享。未导出监督、未选择正式位置训练参照、未训练／校准、未完成自然观测因子。

完整证据2103文件／663159971字节，压缩113738082字节，SHA256 6264e670f4a848918285f04ec0c1f6ca98a28f52027313c525e9e2cfce43db29；逐文件读回，三卷重连摘要一致。[报告](../reviews/pc_a/offline_factor_data_2026-09-30/REPORT.md)、[交付／分卷](../reviews/pc_a/offline_factor_data_2026-09-30/DELIVERY.md)、[复现](../reviews/pc_a/offline_factor_data_2026-09-30/REPRODUCE.md)。本机原件 output/offline-factor-data-20260930。

交付前fetch核对集成19ddf26830348a2f0b33f0af54d6ba702c5cfb1c、父PR72源码0ce10502e8c2292c6d7b34dcbf62f795133ad4c4、B审查fd4ca6ef5e81c90d7cf7987b42c0b2810d8a810a未变。B独立、全仓CI、自然任务收益尚未通过。下一主项是固定新数据的公开前端覆盖／位置参照诊断，再推进自然实例／位置观测因子。以下历史待决状态不覆盖本节批准记录。

# 已批准离线实例／位置监督：第一批数据开工

用户在本任务明确回复“选择1”，批准将仿真实例ID、实例掩膜和真实位置从仅评价扩展到离线训练和校准。在线感知仍只读取公开RGB-D和相机自身位姿。原 CALIBRATION_DECISION.md 的待决状态由本记录更新；历史报告保持其当时状态，不继续把这一项列作权限阻塞。

分支 codex/pc-a-offline-factor-data-20260930；base / 开工源码 0ce10502e8c2292c6d7b34dcbf62f795133ad4c4。已fetch核对共享集成19ddf26830348a2f0b33f0af54d6ba702c5cfb1c、B当前审查fd4ca6ef5e81c90d7cf7987b42c0b2810d8a810a未变。

按已批准方案固定 ProcTHOR TRAIN revision439193522244720b86d8c81cde2e51e3a4d150cf及完整包SHA256 ee3c4aa14b4d8f0895fecfb5fdaca59395427ca1018b2f9aeeedbc61e5824587。index0旧场景仅诊断；预定index1–8训练来源、9–12验证来源，不按结果替换房屋。先形成全部资产覆盖及隔离清单，再采集公开RGB-D/自位姿、独立保存同事件SDK标签和动作回执。新监督仅限实例/掩膜/位置，不将仿真标签冒充独立人工接触、释放或人物标注。

本轮重点是数据入口：使用固定相机观察日程，保留失败、无目标、无候选和重复帧；不让私有目标可见性调整采集日程。训练/验证目标资产不得跨分区，同一观测不得靠重新命名重复计数。冻结源码后顺序两轮对抗审核再实际采集；多代理审查是同一A任务内的辅助审查，不称B独立验收。

证据 output/offline-factor-data-20260930。完整框架、三个RB blocks、七算子和既有对照保留；新权限不自动改变先验、正式任务效用或验收阈值。先完成可审查的独立新数据批，再推进观测模型训练/校准和原生因子接线。

# A：自然实例／位置因子评价诊断交付（2026-09-30）

已通过[草稿 PR72](https://github.com/goneveitvet240-svg/cpswm/pull/72)叠加 PR71 交接，保持未合并。文档/原件交付 cf4244e687f44e31550339c19a2ad8659e784b46 与实际审查源码4798bd67059eb96f2128a957cfd81d1b1f5d509f的 src/tests/tools/依赖字节一致。

分支 codex/pc-a-surface-factor-diagnostic-20260930；base c52920208c123434c556710988cbbec2119373a1；实际审查源码 4798bd67059eb96f2128a957cfd81d1b1f5d509f。新增全类别候选 × 全实例的 RGB-D 表面归属与原始位置位移诊断；生产 src 不改。首次绑定适配错误使五份合法归档失败，原件保留；修复后重新顺序 70 / 52 passed、零跳过，静态检查通过。

固定五份旧归档重新推理 5/5 完成，共 14 帧 / 50 候选 / 150 采样，仅 3 组不同 RGB-D 几何输入、32 组不同几何采样像素。发现跨类别双框覆盖同一苹果及框内背景，不能把框或表面点直接当独立实例/对象中心。真实归档跨目录复算通过，三类完整伪造按预期拒绝。结果是旧场景诊断，不是新仿真实验、自然因子训练、校准或任务收益。

[报告](../reviews/pc_a/surface_factor_diagnostic_2026-09-30/REPORT.md)、[复现](../reviews/pc_a/surface_factor_diagnostic_2026-09-30/REPRODUCE.md)；原件 output/surface-factor-diagnostic-20260930。

封存 312 文件 / 262957322 原始字节，压缩 33958510 字节，SHA256 e1a8485f267633afb21f355a0703ee84dfa2ee58360b22c2ecb47a9d3e68582a；已逐文件读回。

交付前 fetch 核对集成 19ddf26830348a2f0b33f0af54d6ba702c5cfb1c、父候选 c52920208c123434c556710988cbbec2119373a1、B 当前审查 fd4ca6ef5e81c90d7cf7987b42c0b2810d8a810a 未变。此为 A 自审；完整 CI / B 独立 / 自然实例位置因子和自然任务收益尚未完成。下一项是有证据支持的自然观测模型，先前离线标签训练/校准用途仍待用户明确答复；原对照及完整统一范围保留。以下历史状态不覆盖本节。

# 自然位置观测因子的评价诊断开工

分支 codex/pc-a-surface-factor-diagnostic-20260930；base / 开工源码 c52920208c123434c556710988cbbec2119373a1。已 fetch 核对集成 19ddf26830348a2f0b33f0af54d6ba702c5cfb1c、B 当前审查 fd4ca6ef5e81c90d7cf7987b42c0b2810d8a810a。

本轮把旧临时表面归属检查做成可复算诊断：从已交付 RGB-D 动作原件先重新运行公开检测器和几何，再读取已有私有实例评价材料，保留每一候选与全部实例的框交叠、三个表面采样的像素归属，以及到 SDK transform position / AABB center 的原始位移。类别错报、无候选、不可见实例、重复像素和背景均保留；不以中心距离挑选配对，不从评价端生成方法身份。

本轮不训练或校准，不新增正式评价阈值、先验或似然。离线标签用途问题仍待用户答复。线上方法、原任务对照和完整框架保持。新诊断与历史完整闭环复算分别记录：当前工具不得冒称旧源码完整验收。

冻结代码后顺序两轮 A 对抗自审，第一轮覆盖真实处理正路径、完整候选/实例矩阵和错位材料；第二轮覆盖完整伪造、原件搬移与复算，以及现有几何/权限回归。审查后执行固定已有归档，失败不替换、不丢弃。原件 output/surface-factor-diagnostic-20260930；报告 docs/reviews/pc_a/surface_factor_diagnostic_2026-09-30。尚未验收，不是 B 独立审核或科学收益。

# A：八小时窗口最终交接记录（2026-09-30）

最后两批已由[草稿PR71](https://github.com/goneveitvet240-svg/cpswm/pull/71)统一交接，父PR70；GitHub读回OPEN/DRAFT、CLEAN/MERGEABLE，未合并。最后实际源码14409b3beabbd298196ea8f65c4e4f7a0cf719f2；前批比较实际源码fa4dc032c9ef843d8ec0975810c010cd1c5ca7d6；后续提交仅文档/原件，生产/测试/工具/依赖字节核验不变。

十个批次的4500原件/1446503881字节已在最终候选再次逐文件读回核验。补充总交接、4个远端源码CI原始包及失败分类另封存85文件/25154909字节，压缩5428343字节，SHA256 92eb31eb03d903e90c1afbc4ec914e1304978d23e48678e6f794c34f61edcf1b；归档meta指交付候选，内部每个历史远端结果保留自己的源码SHA。

总报告 docs/reviews/pc_a/mainline_handoff_2026-09-30/MAINLINE_PROGRESS.md；本机可读副本 output/mainline-handoff-20260930/MAINLINE_PROGRESS.md。全仓/B独立/自然任务收益未通过，已提出的离线标签用途尚待用户答复。最新14409b3完整远端CI仍未完成，不能用前一版部分结果替代。共享集成19ddf26830348a2f0b33f0af54d6ba702c5cfb1c与B当前审查fd4ca6ef5e81c90d7cf7987b42c0b2810d8a810a保持，完整研究范围和原对照保留。

# A：最后两批与主干窗口交付（2026-09-30）

当前分支codex/pc-a-camera-checkpoint-fixture-20260930，base175a54baf91b782907518906b56f28acc84541be，实际源码14409b3beabbd298196ea8f65c4e4f7a0cf719f2。相机checkpoint默认目录修复13/13顺序双审零跳过；3种显式非法覆盖按预期exit1拒绝、不回落，3条真实网络/反馈/行动输出保留。原件99文件，压缩12295469字节，SHA256 f4ab144cc3bbaac8f8f94d0e14d975c99743b9a144de89af09ae62ee6f8ebf9e，逐文件读回。前批fa4dc03的14/2双审和10完整伪造原件保留，两个批次分别绑定实际源码。

当前fa4dc03远端完整选择6059项，65分钟超时；4576通过、27失败、8准备错误、30跳过、1预期失败，3匿名节点不计通过。最新14409b3的全CI尚未完成。旧60历史缺失失败有53节点配对转为通过、7未完成；当前自然后验仍受控、未决高，任务收益未确立。总交接见docs/reviews/pc_a/mainline_handoff_2026-09-30/MAINLINE_PROGRESS.md；原始远端材料与失败分类在output/mainline-handoff-20260930。

本轮所有改动仍为独立A候选；共享集成19ddf26830348a2f0b33f0af54d6ba702c5cfb1c不变，B独立/跨平台/自然观察因子与离线监督用途选择仍待闭合。完整统一框架及原对照保留。以下历史状态保留。

# A：相机模型测试默认材料修复开工（2026-09-30）

分支 codex/pc-a-camera-checkpoint-fixture-20260930，base175a54baf91b782907518906b56f28acc84541be；前轮fa4dc03的顺序14/2双审已完成，原件封存并推送。重新fetch核对集成19ddf26830348a2f0b33f0af54d6ba702c5cfb1c，B当前审查分支codex/pc-b-adversarial-audit-fix-20260913为fd4ca6ef5e81c90d7cf7987b42c0b2810d8a810a。

当前远端出现8个CPSWM_CHECKPOINTS缺失准备错误。本轮仅在环境变量未设置时使用仓库已经登记的三个受控开发checkpoint；显式覆盖路径必须照常验证，错误路径/损坏模型不得回落。保留三个真实网络、所有完整伪造和公平对照断言，不训练/重写模型。先留修前错误，冻结后两轮顺序审查：默认目录真实正路径及完整伪造；搬移覆盖路径的正路径、全部矩阵攻击及错误覆盖不回落。原件output/camera-checkpoint-fixture-20260930。全仓/B独立/自然闭环不升格。

# A：当前比较数据与测试上下文交付（2026-09-30）

分支 codex/pc-a-comparison-test-context-20260930；base3e030d2345d53f0fa4a4e9b41795a038dca10dc2；实际源码fa4dc032c9ef843d8ec0975810c010cd1c5ca7d6。只修两个旧测试上下文，不改生产机制。冻结后顺序14/2 passed、零跳过；生成当前60段/1920步，两个完整fresh replay正路径通过，10类完整重签伪造拒绝；Ruff/格式通过。

长期P5提交全0、三臂搜索相同，公平性和科学验收仍未建立。封存72文件/106435466字节，压缩21790329，SHA256 2aa7b5a739445dc4bb8dddba2aea4fcc2a9b745a1cad5ecc63bc72678cc7d88a，逐文件读回。报告 docs/reviews/pc_a/comparison_test_context_2026-09-30/REPORT.md；原件 output/comparison-test-context-20260930。同步自己父分支交付文档，实际生产/测试/工具/依赖字节核验未改。全仓/B独立/自然实例位置因子及离线标签选择仍待闭合；旧P0不刷新。

# A：当前比较测试上下文修复开工（2026-09-30）

分支codex/pc-a-comparison-test-context-20260930，base3e030d2345d53f0fa4a4e9b41795a038dca10dc2，前轮PR70实际源码818d83a的9/49顺序双审已完成。远端fetch已核对，集成19ddf26830348a2f0b33f0af54d6ba702c5cfb1c、B fd4ca6ef5e81c90d7cf7987b42c0b2810d8a810a未变。只适配两个实际暴露的测试问题：未获CCRR准入更正应事务回滚而非保留历史丢失预期；覆盖率与消费追踪在不同实际进程执行，不移除生产探针对既有tracer的拒绝。

冻结源码后两轮审查：第一轮真实动态边界、消费观测和正式修订谱系；第二轮先由当前CLI生成既有D0的当前比较材料，再真实完整重放合法包与完整伪造动态/公平性包。材料生成是受控开发协议，不是新仿真私有标签训练；旧P0与旧比较包保留。原件output/comparison-test-context-20260930。

# A：审查虚拟环境入口修复交付（2026-09-30）

分支codex/pc-a-audit-venv-invocation-20260930，base21619f014b43c724b28a93fa4612e03e5a10e2c7，实际源码818d83a36cc1812d68662297b76bc6940272b25c。版本核验按真实venv入口执行，继续绑定解析后解释器字节身份；修复前/后sys.prefix因果对照、两轮顺序9/49 passed零跳过、真实指纹合法与2种完整重签伪造全部保留。旧P0仍报实际toolchain drift，未刷新、未升格验收。

封存34文件/1917565原始字节，压缩450632字节，SHA256 02f655691e35fba4fd33f62028008fcb310eef2a2d53eefab921fb92fafb2e18，逐文件读回核验。[报告](../reviews/pc_a/audit_venv_invocation_2026-09-30/REPORT.md)、[双审](../reviews/pc_a/audit_venv_invocation_2026-09-30/REVIEWS.md)。同步保留PR68真实正路径完整失败分类、前轮历史检出双审报告和所有原件。当前完整CI/B独立/自然训练校准与长期任务收益仍未完成，下一项为当前比较材料及两个已定位的历史测试适配；完整科学框架/原对照/待决标签用途不变。以下历史状态保留。

# A：版本核验虚拟环境入口修复开工（2026-09-30）

分支codex/pc-a-audit-venv-invocation-20260930，base21619f014b43c724b28a93fa4612e03e5a10e2c7。前轮同源码两轮7/2通过零跳过，完整历史重放及攻击结束，证据已本地封存；该目录当前正在只读生成D0比较材料，延后文档提交以保持其HEAD稳定。当前轮只修复环境版本命令使用基础Python的问题，保留身份哈希、清单失效和全部生产保护；不刷新P0或旧回执。冻结源码后顺序两轮审查。原件output/audit-venv-invocation-20260930。GitHub远端重新fetch，集成19ddf26830348a2f0b33f0af54d6ba702c5cfb1c、B fd4ca6ef5e81c90d7cf7987b42c0b2810d8a810a。

# A：CI历史检出修复（2026-09-30）

分支codex/pc-a-ci-history-20260930，base59dd5ce3ab70411e3af5a9421c99cf5b482a19c2，实际源码21619f014b43c724b28a93fa4612e03e5a10e2c7。测试job使用完整Git历史；同HEAD/同12份材料，浅检出拒绝，补全后11记录通过，完整重签伪造仍拒绝。顺序两轮7/2 passed、零跳过；第二轮包含跨目录完整重放、9类报告伪造及源码/历史记录替换，10份报告原件保留。完整集合6050项/368模块收集通过，远端run36641464926尚执行，不能等同全部通过。

封存36文件/515382原始字节，压缩132659字节，SHA256 de4523855efd7812d772b708b32b6e13fc2792e7344025ae5a3aada7b64f75b0，逐文件读回核验。最初过宽局部尝试中断记录保留。报告位于docs/reviews/pc_a/ci_history_2026-09-30，原件output/ci-history-20260930。下一项版本核验误用基础解释器已因果重现，分支隔离修复；当前受控比较包在固定源码目录另行生成。P0旧清单、B独立、完整CI、自然训练/校准与任务收益仍未关闭，完整范围/对照保持。以下历史状态保留。

## 2026-09-30 A 开工：CI 历史检出完整性

任务分支 codex/pc-a-ci-history-20260930，base 59dd5ce3ab70411e3af5a9421c99cf5b482a19c2。上一轮 PR #67 已交付双审与失败原件。GitHub 集成19ddf26830348a2f0b33f0af54d6ba702c5cfb1c / B fd4ca6ef5e81c90d7cf7987b42c0b2810d8a810a 已重新 fetch 核对。本轮只修复默认浅历史造成的历史来源校验失败，保留固定版本证据、所有比较协议与科学 BLOCK。源码冻结后两轮顺序审查；证据输出 output/ci-history-20260930。

# A：CI失败证据保存交付（2026-09-30）

分支codex/pc-a-ci-failure-artifacts-20260930，base053b27851c2f935e4de8fb00b0bee4dd9f294821，实际源码4ae76850ffd99d86703b4e45e837d4e402203c78。完整测试集合和3900秒执行预算保留；job总85分钟另留准备/中断/上传，逐项节点、原日志、退出状态、JUnit/覆盖率全部归档，超时假零退出不得变成功。顺序两轮15/55 passed零跳过，Ruff/格式通过；另15案例补存10份真实子记录，管道成功/失败/写失败返回0/3/1。

封存105个常规文件/1863198字节，压缩401516字节，SHA256 e0748315bb7c4a8ab6652d40d0b480668fae23f2aa4b011c6d00f54c9b46543a，逐文件读回核验。排除派生缓存、临时FIFO与pytest便捷符号链接；原始数据文件、命令、日志、失败和补充案例保留。

远端实际run36639386505仍执行，未宣称上传或全仓成功。本机父任务完整集合仍在独立冻结目录运行，已发现P0清单陈旧及一条历史修订缺陷预期失败，继续诊断。只取消当前分支被替代的旧运行，其他分支保留。

隔离浅克隆实际失败；补全历史后HEAD和12份材料字节完全不变，11个历史记录通过。下一轮修复CI检出历史并审查剩余失败；不弱化来源检查，不自动刷新清单掩盖漂移。[报告](../reviews/pc_a/ci_failure_artifacts_2026-09-30/REPORT.md)、[双审](../reviews/pc_a/ci_failure_artifacts_2026-09-30/REVIEWS.md)、[复现](../reviews/pc_a/ci_failure_artifacts_2026-09-30/REPRODUCE.md)。原件output/ci-failure-artifacts-20260930。完整范围、原对照及待决离线监督用途保留。以下历史记录保留。

# A：CI失败证据保存独立开工（2026-09-30）

分支codex/pc-a-ci-failure-artifacts-20260930，base/开工源码053b27851c2f935e4de8fb00b0bee4dd9f294821。父任务完整集合在另一冻结目录继续，实体环境两轮84/124通过。前轮远端65分钟到76%超时且丢失完整失败回溯；本轮改善原始日志/JUnit/覆盖率/退出码保留，不减少测试集合或改变科学协议。[计划](../reviews/pc_a/ci_failure_artifacts_2026-09-30/PLAN.md)，证据output/ci-failure-artifacts-20260930。以下历史记录保留。

# A：真实正路径调用观测交付（2026-09-30）

分支codex/pc-a-positive-call-observation-20260930，base2bd0ee7f44e01cb59dd29d36deb3ed4464907c5c，实际源码053b27851c2f935e4de8fb00b0bee4dd9f294821。仅测试观测从生产方法替身改为真实函数调用监测；原断言和生产来源防护保留。实体环境顺序84/124 passed、零跳过，Ruff/格式通过。完整诊断4276通过/21失败/29跳过/1预期失败，2975.46秒退出2；达到20失败诊断预算后向本任务控制器SIGINT，未执行余下集合，不是全仓完成。远端同源码65分钟超时失败。

8项旧清单/回执、9项缺少当前比较包/旧schema、旧CORRECT预期1项、trace覆盖率冲突1项、基础解释器误调用2项已保留回溯分类；不自动刷新或弱化检查。封存94文件/8098483原始字节，压缩1521984字节，SHA256 8847057989bb9c6fc5ecefd7b4131ec3b2ec50ae485cd06bbc1828ab7db661ae，逐文件读回通过。证据output/positive-call-observation-20260930。[报告](../reviews/pc_a/positive_call_observation_2026-09-30/REPORT.md)、[双审](../reviews/pc_a/positive_call_observation_2026-09-30/REVIEWS.md)、[当前pipeline](../reviews/pc_a/positive_call_observation_2026-09-30/CURRENT_PIPELINE.md)。后继PR67已完成失败证据保存；历史检出另轮推进。B独立/完整CI/自然模型与任务收益未关闭，完整框架和对照保留。以下为历史状态。

# A：反馈正路径观测修复开工（2026-09-30）

分支codex/pc-a-positive-call-observation-20260930，base/开工源码2bd0ee7f44e01cb59dd29d36deb3ed4464907c5c。修复完整回归首失败中的测试替身，保留生产来源防护与正路径断言；随后顺序两轮对抗审查，再诊断下一失败。[计划](../reviews/pc_a/positive_call_observation_2026-09-30/PLAN.md)，证据output/positive-call-observation-20260930。完整CI/B独立及自然监督校准仍未关闭。以下历史时点保留。

# A：完整依赖与行动报告交付（2026-09-30）

已推送并通过[草稿PR66](https://github.com/goneveitvet240-svg/cpswm/pull/66)叠加PR65交接，未合并。

分支codex/pc-a-ci-action-report-20260930，base778e35418d79b350148c774d98377b0a4ab6e6d4，实际源码c87b6bb1e3c72986afe517f7f29ebf3d028f2283。冻结依赖、src/tests/tools搜索路径补齐，保留全部6035项/367模块；新环境顺序74/31双审零跳过，全仓mypy382及Ruff/格式757文件通过。远端static-quality与收集通过，完整回归尚在运行。

真实RGB-D三观察、一受控撤回、11源/22记录，旧READY左转90取消后Pass，报告明确action_replaced；无旧动作的历史则action_started，不再混淆。独立视觉复算与源码/模型搬移完整重放通过；两种完整自洽假报告均被真实计划/回执重算拒绝，原件未变。未决仍97.5440%，不是自然任务成功。

完整选择首失败诊断1750 passed/1 xfailed/1 failed：旧正路径测试替换生产方法触犯来源检查。下一轮修复调用观测手段，生产防护和正路径断言保留；完整CI、B独立、自然目标密度/监督校准仍未关闭。离线标签用途待用户明确答复，未开展私有标签训练。

完整封存1,248文件/356,394,634字节，压缩48,530,479字节，SHA256 28bd25e25a1eef66d621d47f11f1f796e900bf95aae1c9c471b9641b75ce546d，逐文件读回核验；仅排除派生Python/pytest缓存。远端完整CI仍在运行，未冒充已完成。

[报告](../reviews/pc_a/ci_action_report_2026-09-30/REPORT.md)、[双审](../reviews/pc_a/ci_action_report_2026-09-30/REVIEWS.md)、[复现](../reviews/pc_a/ci_action_report_2026-09-30/REPRODUCE.md)。原件output/ci-action-report-20260930。交付fetch核验集成19ddf26830348a2f0b33f0af54d6ba702c5cfb1c、B fd4ca6ef5e81c90d7cf7987b42c0b2810d8a810a、父778e35418d79b350148c774d98377b0a4ab6e6d4未变；完整统一框架与原对照保留。以下为历史时点。

# A：CI依赖与行动报告修复开工（2026-09-30）

分支codex/pc-a-ci-action-report-20260930，base/开工源码778e35418d79b350148c774d98377b0a4ab6e6d4（PR65）。[计划](../reviews/pc_a/ci_action_report_2026-09-30/PLAN.md)处理45个隔离dev收集错误、两个继承格式错误及None→Pass动作报告歧义；不删测试、不改变方法/先验/效用。冻结后顺序双审，再实际运行与完整回归。证据output/ci-action-report-20260930；旧记录保留。B独立/自然模型校准及标签权限答复仍未关闭。以下为历史时点。

# A：内容定位神经checkpoint交付（2026-09-30）

分支codex/pc-a-portable-checkpoints-20260930，base589b825e2bc232ce7d24213745ed4908f06ad18d，实际方法/采集源码154595da9a2f033934edaeb2d490d039ece29c23。v2证明按manifest内容引用，可信配置指定本机目录；v1原件不改。顺序两轮33/45自审零跳过、四文件Ruff/格式、三个修改模块及全仓382模块mypy通过。

新格式真实RGB-D历史2动作、1受控撤回、11源/22记录；正常及新进程完整复算通过。源码/模型同时搬移、禁止读原源码目录后，workspace/证明/视图/动作/账本完全一致，原历史未改。完整假几何+真实11源网络重封装内部通过，但拥有者原件核验拒绝读出/恢复。SDK27/Unity166文件前后未变。

最终未决99.1422%，无自然语义或物体操作，不是任务成功。这次纠正前无READY，继承报告把None→Pass标成动作改变，已明确记录歧义，下一轮修正；没有将其算作取消或替换旧动作。隔离dev环境复现45个torch/cv2收集错误，连同既有两个格式失败待下一轮修复。

完整归档2,064文件/350,060,119字节，压缩47,287,798字节，SHA256 805893b66846d682ab42d615e99dae4b4b5ecab88475a885891f30e3912029e8；逐文件读回核验。包含实际历史、完整伪造副本、源码搬移副本及初次失败原件；见evidence/archive.json及inventory.json。

[报告](../reviews/pc_a/portable_checkpoints_2026-09-30/REPORT.md)、[双审](../reviews/pc_a/portable_checkpoints_2026-09-30/REVIEWS.md)、[复现](../reviews/pc_a/portable_checkpoints_2026-09-30/REPRODUCE.md)。原件output/portable-checkpoints-20260930。离线监督用途待用户答复，训练/校准未启动；完整框架与原对照保持。B独立/跨平台/全CI/自然长期闭环未关闭。交付fetch核验集成19ddf26830348a2f0b33f0af54d6ba702c5cfb1c、父分支589b825e2bc232ce7d24213745ed4908f06ad18d、B fd4ca6ef5e81c90d7cf7987b42c0b2810d8a810a未变。已推送并通过[草稿PR65](https://github.com/goneveitvet240-svg/cpswm/pull/65)叠加PR64交付，未合并。以下为历史时点。

# A：按内容定位神经checkpoint开工（2026-09-30）

分支codex/pc-a-portable-checkpoints-20260930，base/当前源码589b825e2bc232ce7d24213745ed4908f06ad18d（PR64交付头）。[计划](../reviews/pc_a/portable_checkpoints_2026-09-30/PLAN.md)固定新证明格式和可信本地模型配置，目录搬移不改变模型/概率证据；旧原件不改。先复现故障，再冻结双审与真实历史复算；不是跨平台验收。证据output/portable-checkpoints-20260930。离线监督科学权限选择仍待用户答复，依赖它的训练/校准未启动；B独立/全仓CI/自然闭环仍未关闭。以下为历史时点。

# A：RGB-D 进入原生神经提议交付（2026-09-30）

分支 codex/pc-a-owned-visual-neural-20260930，base c1ae096f55c6487285a83a4aff5e08f743054df5。实际方法/采集源码30d57a0ba7df824ab7fb6fc955e5deacb404f256；新增显式视觉条件输入，由拥有者登记来源、消费者重建网络输入，恢复/行动前再从公共原件复推。默认语义/RGB/分类/澄清及完整框架保持。

初版90d9abb顺序54/34通过后，追加检查发现相机转动45度仍复用3条图像轨迹；失败保留，修复后重新60/34顺序双审零跳过。mypy5模块、Ruff/格式9文件通过。两条真实RGB-D历史各3动作、10候选/30表面点、新进程2/2复算通过；SDK27/Unity166文件前后不变。11个重放源各读入截止时1帧4候选12表面点，几何消融改变11/11个q，目标后验差异0。最终未决均97.5440%，无自然语义/物体操作，不是自然任务收益。

真实归档副本完整重封装假几何、真实网络11源/22记录和全部原生锚点后，内部一致性通过，但保留原件使读出/恢复均拒绝。归档286文件254,979,377字节，压缩33,953,861字节、逐文件读回核验，SHA256 56c4dc23d09ad3dd12dcff9172695131b406514a54e13aae816608944ea76ac5。[报告](../reviews/pc_a/owned_visual_neural_2026-09-30/REPORT.md)、[双审](../reviews/pc_a/owned_visual_neural_2026-09-30/REVIEWS.md)、[复现](../reviews/pc_a/owned_visual_neural_2026-09-30/REPRODUCE.md)。本机原件output/owned-visual-neural-20260930。

[离线仿真监督具体方案](../reviews/pc_a/owned_visual_neural_2026-09-30/CALIBRATION_DECISION.md)已提交用户科学权限选择，未答复前不训练/校准。继续推进绝对checkpoint路径的恢复缺口；自然目标密度、B独立、全仓CI和长期自然闭环仍未关闭。交付fetch核验集成19ddf26830348a2f0b33f0af54d6ba702c5cfb1c、父分支c1ae096f55c6487285a83a4aff5e08f743054df5、B fd4ca6ef5e81c90d7cf7987b42c0b2810d8a810a未变。已推送并通过[草稿PR64](https://github.com/goneveitvet240-svg/cpswm/pull/64)叠加PR63交接，未合并。以下为历史时点。

# A：视觉输入进入原生神经提议开工（2026-09-30）

分支 codex/pc-a-owned-visual-neural-20260930，base/开工源码 c1ae096f55c6487285a83a4aff5e08f743054df5。承接已交付 PR63，推进运行时拥有的完整候选/几何进入提议网络及原生源核验；默认语义对照保留。精确枚举 q 仍抵消，目标密度与自然训练缺口不变。[计划](../reviews/pc_a/owned_visual_neural_2026-09-30/PLAN.md)。输出 output/owned-visual-neural-20260930；冻结后顺序两轮自审，B 独立未关闭。远端集成19ddf26830348a2f0b33f0af54d6ba702c5cfb1c、B fd4ca6ef5e81c90d7cf7987b42c0b2810d8a810a 未变。以下为历史时点。

# A：RGB-D / 自位姿主干接线交付（2026-09-30）

用户已明确授权新增公开 RGB-D 与相机自身位姿；本轮分支 codex/pc-a-rgbd-camera-geometry-20260930，base f57d67e4bde4f036cb6cfc13710966d8b289930b。实际方法/采集源码 dacc6c6cf070225fbc5b13ce351f1487636f6ec8，归档轨迹核验修复源码 2ff55ee5b69f27b963d389c5ecccd0044f2d7373（仅验证器+测试）。RGB/depth/self-pose 三路配对进入原有 M05/SQLite，由 owner 重建世界表面候选；没有加入世界身份/物体中心/概率或新记忆权限。

初始两审 96/44、修复后再两审 19/54，均零跳过。真实归档攻击曾揭出伪造动作标签被旧验证器接受，已修复并保留失败；合法完整归档与五类完整伪造均已核验。6 姿态/54 射线中 50 点误差小于1厘米，最大17.05厘米差异未掩盖。两条真实主历史各3动作；RGB-D有10候选/30世界表面点，另进程2/2完整恢复复算完成，未决均97.5440%，不是任务成功。苹果被报为 sports ball，框内混合背景；几何尚未进入原生联合提议/目标密度。

[报告](../reviews/pc_a/rgbd_camera_geometry_2026-09-30/REPORT.md)、[双审](../reviews/pc_a/rgbd_camera_geometry_2026-09-30/REVIEWS.md)、[复现](../reviews/pc_a/rgbd_camera_geometry_2026-09-30/REPRODUCE.md)。全原件462文件/288,148,940字节，压缩54,907,409字节，逐文件读回核验，SHA256 4ef7f013203f48d5786b1ede52ead6cfc7789a8cc27d39e6d26994e2a127c3a9。SDK27/Unity166文件前后不变。本机原件 output/rgbd-camera-geometry-20260930。保留纯RGB、分类对照、已批准澄清和完整研究范围；B独立、全量CI、旧checkpoint绝对路径及自然长期闭环仍未关闭。

已推送并通过[草稿PR63](https://github.com/goneveitvet240-svg/cpswm/pull/63)交接，未合并。

下一主项：完整候选/几何通过运行时拥有的来源进入提议网络，保留类别歧义，不使用评价标签或任意先验制造成功。继续推进，以下为历史时点。

# A：RGB-D / 相机自身位姿主干开工（2026-09-30）

用户本轮明确同意新增公开 RGB-D 与相机自身位姿，另授权八小时主干推进和常规工程选择。分支 codex/pc-a-rgbd-camera-geometry-20260930，base/开工实际源码 f57d67e4bde4f036cb6cfc13710966d8b289930b。先做单位/坐标/权限/同历史来源绑定和几何候选，再核验对后续联合输入的贡献。原 RGB/分类对照、已批准澄清任务及完整研究范围保留。两轮顺序自审后才进入下一轮；B 独立与科学收益未关闭。证据 output/rgbd-camera-geometry-20260930；[计划](../reviews/pc_a/rgbd_camera_geometry_2026-09-30/PLAN.md)。开工远端集成 19ddf26830348a2f0b33f0af54d6ba702c5cfb1c、B fd4ca6ef5e81c90d7cf7987b42c0b2810d8a810a 未变。以下为历史时点。

# A：公共视觉候选同历史接线交付（2026-09-30）

分支codex/pc-a-visual-support-20260930，base 1d3538794b8b86d66414255f8d37f64d8ff0d88e；实际功能源码d699b90db2b0cfa719be7f44f8c7128d27c08780。新增运行时visual_observation_support读出，使用原始动作拥有的公共RGB和既有绑定检测器，返回帧候选/图像位置/原生代际及重复像素组。未拟合自然目标密度，未把图像位置当三维位置、框ID当世界身份或检测分数当概率。

冻结后顺序两轮A局部自审61/42 passed、零跳过，Ruff/格式和两个生产模块mypy通过。命令与JUnit见[双审](../reviews/pc_a/visual_support_2026-09-30/REVIEWS.md)及原件attempt01/commands.json。两条固定北侧真实历史完成：5帧13候选，另进程2/2重建通过；真实完整归档副本的伪造阳性/派生候选被原图复推拒绝。未决仍97.5440%/99.1422%，不是任务收益；保留受控语义/撤回、原分类对照和完整框架。

[完整报告](../reviews/pc_a/visual_support_2026-09-30/REPORT.md)、[复现](../reviews/pc_a/visual_support_2026-09-30/REPRODUCE.md)、[下一实现单元](../reviews/pc_a/visual_support_2026-09-30/NEXT_STEP.md)。原件173文件143,006,032字节，压缩14,843,221字节并逐文件读回核验；持久位置output/visual-support-20260930。SDK27/Unity166文件前后不变；同机复用环境，不是B独立验收。完整CI、旧神经归档绝对路径跨机定位和自然长期闭环仍未关闭。

交付前fetch核验集成19ddf26830348a2f0b33f0af54d6ba702c5cfb1c、父分支1d3538794b8b86d66414255f8d37f64d8ff0d88e、B fd4ca6ef5e81c90d7cf7987b42c0b2810d8a810a未变。下一主项仍是自然实例/位置候选密度与测量模型；新增RGB-D及相机自身位姿权限已提出具体选择，未收到答复前维持纯RGB，不自行新增先验/指标或收窄框架。已推送并通过[草稿PR62](https://github.com/goneveitvet240-svg/cpswm/pull/62)叠加PR61交接，未合并。以下为历史时点。

# A：公共视觉候选同历史接线开工（2026-09-30）

分支codex/pc-a-visual-support-20260930，base/当前实际源码1d3538794b8b86d66414255f8d37f64d8ff0d88e。核验远端后从父分支独立开工；[计划](../reviews/pc_a/visual_support_2026-09-30/PLAN.md)固定两轮审查后再跑两条北侧历史。生产候选读出接线，不添加传感器权限、世界身份、密度先验或阈值；完整框架保持。证据output/visual-support-20260930，目前未验收。B独立及全仓CI缺口仍未关闭。

# A：视觉历史测试依赖修复及重审（2026-09-30）

分支codex/pc-a-visual-history-20260929，base 00cc5a47cad988b453d5839b63fd7c6a89f4246d；测试修复源ac93f8d489209943cbcff9292ab483330538854b。仅两个测试隔离可选依赖/权重；真实权重下重新顺序33/42双审零跳过，局部Ruff通过。四条实际历史仍绑定00283c607a5fb49c293cefe8eafd65cc2192f558，原封存包不变；其他Python/依赖源码一致。见[补充命令与失败记录](../reviews/pc_a/visual_history_2026-09-29/CI_FOLLOWUP.md)。

[草稿PR61](https://github.com/goneveitvet240-svg/cpswm/pull/61)继续交接，未合并。远端全仓静态检查的两个继承格式失败已复现并保留，全量测试未取得完成结果；B独立/统一验收未关闭。下一主项仍是自然观测支持的实例/位置候选密度及测量校准。以下为此前时点。

# A：同历史视觉对照与瓶颈定位交付（2026-09-29）

分支codex/pc-a-visual-history-20260929，base 00cc5a47cad988b453d5839b63fd7c6a89f4246d，实际功能源码00283c607a5fb49c293cefe8eafd65cc2192f558。顺序两轮A局部自审33/42通过、零跳过，Ruff/格式通过；后续精确枚举诊断3项通过。固定4条历史、11次实际观察及另进程4/4复算完成；4个完整归档副本攻击拒绝。SDK27/Unity166文件前后不变。

6个目标可见帧：同图SSDLite目标框覆盖0/6、Faster4/6，但北Faster最终未决99.1422%并因预期收益不足停止，其余97.5440%。两个视角四种结果的代数穷举显示当前实际先验/假设模型最低未决81.7963%；候选密度仍由受控fixture给出，精确枚举q正确抵消，因此单换前端或多训练q不自动补齐自然推断。自然任务完成/收益尚未成立。

完整原件326文件289,262,814字节，压缩31,019,073字节并逐文件读回验证；监督索引保留11观测/5份不同RGB/1房屋来源组，不当独立holdout。见[报告](../reviews/pc_a/visual_history_2026-09-29/REPORT.md)、[双审](../reviews/pc_a/visual_history_2026-09-29/REVIEWS.md)、[复现](../reviews/pc_a/visual_history_2026-09-29/REPRODUCE.md)、[下一实现单元](../reviews/pc_a/visual_history_2026-09-29/NEXT_STEP.md)。本机原件output/visual-history-20260929。旧神经归档绝对路径跨机定位、B独立/统一验收及既有全量CI仍未关闭；完整框架、原任务对照和已批准澄清任务保持。下一主项为公共自然观测支持的实例/位置候选密度及校准，不能用任意降未决或私有标签入策略造成功。

交付前fetch核验集成19ddf26830348a2f0b33f0af54d6ba702c5cfb1c、父分支00cc5a47cad988b453d5839b63fd7c6a89f4246d、B fd4ca6ef5e81c90d7cf7987b42c0b2810d8a810a未变。已推送并通过[草稿PR61](https://github.com/goneveitvet240-svg/cpswm/pull/61)叠加父分支交接，未合并；以下为历史时点。

# A：同历史视觉证据接线开工（2026-09-29）

分支codex/pc-a-visual-history-20260929，base/当前源码00cc5a47cad988b453d5839b63fd7c6a89f4246d。延续已批准主动澄清任务，固定4条两前端×南北同历史，增加同原图完整实例评价，默认/正式配置和证据权限不改。冻结后顺序两轮局部自审再实际实验；现在未验收。见[计划](../reviews/pc_a/visual_history_2026-09-29/PLAN.md)，证据output/visual-history-20260929。远端集成19ddf26830348a2f0b33f0af54d6ba702c5cfb1c、B fd4ca6ef5e81c90d7cf7987b42c0b2810d8a810a未变，B未独立复核；复用本机环境。

# A：同历史纠正—行动续接交付（2026-09-29）

独立分支 `codex/pc-a-history-action-loop-20260929`，base `bf374f9331426cfa384f2ec23bf0bd0a098ba033`，实际功能源码 `c59b8c88d9d3cb1d03f9042909a58fd7378f7e03`。当前冻结源顺序两轮局部A自审18/24通过、零跳过；Ruff/check-format及两个生产模块mypy通过。命令/源码映射见下方报告及原件中attempt02/commands.json。

用户确认新增主动澄清开发任务，保留原分类对照。南/北四条同历史完成并由另进程4/4复算：每条一次受控撤回、11源神经重算/22记录、记忆首选位置变化；原分类均0动作，澄清各3个真实RGB返回，旧左转90度READY取消，新代先原地重观测再左转90度。6个公共帧中3个目标可见帧全部漏检，最终未决概率97.54%，没有可靠目标完成或方法收益。自然语义/反证仍为缺口，像素没有长期反证权限，完整统一框架与B正式协议保持。

首版d9d4941在实际归档核验因内部随机ID误比较而失败，首批/开发失败日志完整保留；修正后从头运行四条。完整原件269文件/325,879,662字节，以33,412,800字节压缩包共享并逐字读回验证；三项完整归档攻击被拒绝。SDK27/Unity166文件运行前后未变。此为受控语义+真实相机混合工程闭环，不是自然完整pipeline或B独立验收；既有全量CI失败仍未解决。

[报告](../reviews/pc_a/history_action_loop_2026-09-29/REPORT.md)、[两轮审查](../reviews/pc_a/history_action_loop_2026-09-29/REVIEWS.md)、[复现](../reviews/pc_a/history_action_loop_2026-09-29/REPRODUCE.md)。持久原件output/history-action-loop-20260929；已推送并通过[草稿PR60](https://github.com/goneveitvet240-svg/cpswm/pull/60)叠加上一A分支交接，未合并。下一主项是将可信自然实例/事件证据接入这条同历史链路，补测量可靠性和自然纠正，再评估任务完成/成本/长期恢复。交付前fetch成功：集成19ddf26830348a2f0b33f0af54d6ba702c5cfb1c、B fd4ca6ef5e81c90d7cf7987b42c0b2810d8a810a未变。

下方为历史时点，不覆盖本节绑定源码和原件的结果。

# A：同历史纠正与实际行动续接开工（2026-09-29）

用户要求回归完整闭环。分支 `codex/pc-a-history-action-loop-20260929`，base/开工源码 `bf374f9331426cfa384f2ec23bf0bd0a098ba033`。本轮连接合法长期源纠正、联合重算、SQLite恢复和同一Unity进程的后续行动；不继续扩大静态帧矩阵。计划见 [PLAN](../reviews/pc_a/history_action_loop_2026-09-29/PLAN.md)，持久原件 `output/history-action-loop-20260929/`。语义及反证仍受控、自然证据缺口明确保留，每轮冻结后顺序两轮对抗自审再实际运行，尚无验收结论。独立审核窗口F1/F3/F5已读，B协议不改，完整框架保留。开工远端核验集成19ddf26830348a2f0b33f0af54d6ba702c5cfb1c、B fd4ca6ef5e81c90d7cf7987b42c0b2810d8a810a 未变。

# A：时序诊断完成，实例对应为下一主项（2026-09-29）

`codex/pc-a-sim-timing-control-20260929`，base `e80ddab4f4f792a372c1410862b071f79aebdb64`，受测 `a981541fc15bd1e441051f9479dc96b17cdc2f44`。32/17 顺序双审、Ruff、第二批完整24格384帧及768次原图重新推理通过；首批23完成/1失败单列，不拼接、不报运行100%可靠。冻结有效但稳定误报/漏检仍在，且跨启动物理初始态不完全相同。见[完整报告](../reviews/pc_a/sim_timing_control_2026-09-29/REPORT.md)。

A 下一项优先补同一保存图像的可信实例对应；实时闭环方法比较须另补初始状态配对。原件在 `output/sim-timing-control-20260929/`，Git 共享全量轻证据与三条完整序列。草稿叠加交付不合并；正式模型/先验/阈值、B比较协议、完整框架保持。B独立与统一验收未完成。

# A：时序控制两审通过，完整矩阵执行中（2026-09-29）

分支 codex/pc-a-sim-timing-control-20260929，base e80ddab4f4f792a372c1410862b071f79aebdb64。实际功能源码 a981541fc15bd1e441051f9479dc96b17cdc2f44；32/17 顺序两轮 A 自审及 Ruff 通过，三种模式实际 16 帧夹具各自合法复推通过，完整伪造阳性/步长/返回动作/漏事件/几何/漏帧被拒绝。当前预先固定 24 格/384 帧采集与随后逐图复推执行中，不先写全量成功结论。命令及冻结映射 output/sim-timing-control-20260929/attempt01；方案 docs/reviews/pc_a/sim_timing_control_2026-09-29/PLAN.md。

三条夹具初步显示冻结后位姿可保持不变，但准备后仍有早期图像变化，后续公共图像稳定时检测仍漏。不能从夹具替代完整矩阵，更不构成校准/方法收益。B独立验收未完成，完整框架和正式协议/模型/先验/阈值保持。本条不改变受测功能源。

# A：物理步进与采集时序控制开工（2026-09-29）

独立分支 codex/pc-a-sim-timing-control-20260929，base e80ddab4f4f792a372c1410862b071f79aebdb64。用户授权继续最关键下一步，先隔离物理演化与启动采集效应。预先固定 24 格/384 帧三条件对照；实现后冻结代码、顺序两轮 A 自审，再实际全量采集/原图复推。计划 docs/reviews/pc_a/sim_timing_control_2026-09-29/PLAN.md；持久原件 output/sim-timing-control-20260929。当前尚未验收。开工 fetch 成功，集成19ddf26830348a2f0b33f0af54d6ba702c5cfb1c 与B fd4ca6ef5e81c90d7cf7987b42c0b2810d8a810a 未变；B所有权和完整研究范围保持，复用本机锁定依赖不冒称独立环境。

# A：仿真核验及固定重复诊断交付（2026-09-29）

独立分支 `codex/pc-a-sim-method-audit-20260929`，base `915d7614026ac2b90be5b7bc91bc2bbe5201595d`。原数据审计实际代码 `ebaea38a8fef26ee503c4c0ad69ea67ad3bb4af1`，32/14 顺序两轮 A 自审通过；2,072 文件清单一致，132 帧几何/分母独立重算及 264 次原图模型复推逐字段一致。首次受限环境启动超时单独保留，随后同源码完整重跑成功，不报启动可靠率 100%。

可靠的旧记录基础上推进了预先固定的 16 格/128 帧重复采集。实际代码 `69ebcf90ea271798b8f0c1eb89df501065954ebd`，31/13 顺序两轮 A 自审、Ruff、完整采集和另 256 次原图复推通过；SDK/Unity 文件运行前后不变。全部格相机/目标位置和掩膜一致，但南侧 320 四组均首帧阳性、后七帧漏检；128 帧场景未静止。原数值可信，稳定观测概率/理想表现/算法收益仍无依据，暂不拟合似然或改变正式模型、先验和阈值。

[完整报告](../reviews/pc_a/sim_reliability_2026-09-29/REPORT.md)与[复现说明](../reviews/pc_a/sim_reliability_2026-09-29/REPRODUCE.md)列出命令/证据/局限。持久原件 `output/sim-reliability-20260929/`；Git 交付全部轻量矩阵及一条完整八帧原件，复制位置已再推理验证。后续提交仅文档/证据；草稿 PR 叠加上一批 A 分支交付，不合并。下一项先显式控制物理时间并固定采集稳定性协议，再做可信实例对应/条件测量。B 独立与统一验收未完成，完整统一框架及 B 正式协议保持。

下方为历史时点，不能覆盖本节绑定源码的结果。

# A：仿真操作与数据可靠性核验开工（2026-09-29）

独立分支codex/pc-a-sim-method-audit-20260929，base/审计对象915d7614026ac2b90be5b7bc91bc2bbe5201595d，源码对应b1969f30b85434452f6b23ec53c93d84799ff62f。用户授权先核验可靠性，可靠后推进。先检查归档完整性、动作/几何、真值隔离、原图重算和分母；再核查同位姿重置/采集序列导致的图像变化。计划docs/reviews/pc_a/sim_reliability_2026-09-29/PLAN.md；持久工件output/sim-reliability-20260929。复用相同本机锁定Python依赖、显式PYTHONPATH加载本任务源码，不声称独立机器复现。B正式协议和独立验收不变，旧原件不覆盖。开工fetch成功，集成19ddf26830348a2f0b33f0af54d6ba702c5cfb1c与B fd4ca6ef5e81c90d7cf7987b42c0b2810d8a810a未变；本轮尚未验收。

# A：五小时主线八轮交付，当前功能版双审完成（2026-09-29）

分支`codex/pc-a-neural-native-loop-20260929`，base `2a0bbdf2e77e76b8e45d5f92211e820d337c3cf3`，最终实际功能代码 `b1969f30b85434452f6b23ec53c93d84799ff62f`；交付后续提交仅文档/证据。三主项依序已完成受控神经原生接入、实际相机反馈和开发比较，共八轮各自两轮顺序A自审。最终当前源码145/69交叉复核，214通过、0跳过，mypy377/Ruff通过。此前缺权重参数的5skip单独保留并完整重跑。具体命令、完整SHA和证据见[总报告](../reviews/pc_a/neural_native_loop_2026-09-29/REPORT.md)、[最终复核](../reviews/pc_a/neural_native_loop_2026-09-29/FINAL_INTEGRATION.md)。

48场分辨率比较的84次转动/132帧成功，但第七轮完整网格显示高分辨率误报增多：Faster R-CNN目标框重叠16/30→19/30，无目标误报1/36→13/36。第八轮证实高分apple框覆盖Tomato_5，完整实例对应私有评价已共享。二视角全部测量组合中，后验组与关闭反馈/右扫描动作相同，当前配置无额外收益证据。下一步为可信实例对应/条件测量与能区分反馈收益的行动任务；完整神经修订核、自然联合训练及长期效用仍未闭合。

持久工件`output/neural-native-loop-20260929/`，Git证据`docs/reviews/pc_a/neural_native_loop_2026-09-29/evidence/`；3实际开发检查点、3旧图反例与3完整实例快照均有逐文件摘要。草稿[PR56](https://github.com/goneveitvet240-svg/cpswm/pull/56)，B独立/统一验收未完成、不合并。完整统一框架与B正式协议所有权保持。交付前fetch成功，共享集成`19ddf26830348a2f0b33f0af54d6ba702c5cfb1c`、B `fd4ca6ef5e81c90d7cf7987b42c0b2810d8a810a`未变。

以下为按时间保留的旧状态，不能覆盖上方当前结果。

# A：48场分辨率对照交付，第六轮可区分性双审执行中（2026-09-29）

第五轮实际代码c54f890aecd5c6af2f9a2005413f7cbf0ba7920b，55/36两审、mypy377/Ruff、48场运行及逐场重建共12命令源码冻结通过。84次转动/132帧，全部48先验一致；Faster R-CNN目标框重叠320为6/12、640为11/12，另1场无目标像素却高分误判并提前停止；SSDLite均0/12。两位置×六方法重复不是12独立场景。三神经方法未见优于关闭反馈/右扫描。详见[第五轮报告](../reviews/pc_a/neural_native_loop_2026-09-29/ROUND5.md)。完整工件output/neural-native-loop-20260929/round5-attempt01。第六轮受测db67b66b2703a34dda750ac8f65c0a3a4a3c5e93，四种二元测量×六方法的穷举已进入顺序双审，使用已发布的相同开发检查点，暂不写完成结论。B未验收、完整自然闭环/研究收益未成立，完整框架保持。

# A：分辨率对照双审通过，完整实际比较进行中（2026-09-29）

实际源码c54f890aecd5c6af2f9a2005413f7cbf0ba7920b；55/36顺序两轮A自审、mypy377/Ruff通过。UTC20:22时320的24场运行及从实际模型/原图/SQLite逐场重建已完成，640矩阵仍运行，不先写总体效果。所有场次采用同源码、先验、过滤值、动作预算；完整工件output/neural-native-loop-20260929/round5-attempt01。三实际开发检查点已逐字备份到报告evidence/development-checkpoints并列摘要（组件夹具各2次优化，不是自然训练）。第六轮二视角可区分性及后续132帧分辨率网格计划已固定，依次双审后推进；B未验收、不合并、完整框架保持。

# A：66帧测量诊断交付，进入分辨率控制（2026-09-29）

实际代码f8425a0813d78ebabb6b8dbcb55a297203ff978d，43/24顺序两审、mypy377/Ruff、66/66采集及两模型从原图逐帧重算通过，7命令源码冻结。30可见帧SSDLite 0阳性；Faster R-CNN 16类别阳性/15框重叠，其中一帧错误框在另一物体上。36无目标像素帧无apple候选。发现南侧195/240度可识别但225度漏，较远位置全漏；不能用0.9假设当标定或类别停止当实例成功。详见[第四轮报告](../reviews/pc_a/neural_native_loop_2026-09-29/ROUND4.md)。完整工件output/neural-native-loop-20260929/round4-attempt01。接着按提前固定计划做320/640真实采集48场对照。B未验收、完整框架与自然科学缺口保留。

# A：24场真实比较完整交付，推进测量诊断（2026-09-29）

实际代码a8992c02508bcede986f1af9986e5f7dbdc6c5cc，45/33顺序两审、mypy377/Ruff、24场实际运行和逐场重算，9命令源码冻结通过。43转动/67原图无执行失败；各组初始后验一致。SSDLite两位置均漏；Faster R-CNN只北位置阳性，后验组与关闭反馈/右先扫描动作相同，未见额外收益。重复渲染有微小差异，不冒称逐字同输入。见[第三轮完整报告](../reviews/pc_a/neural_native_loop_2026-09-29/ROUND3.md)，工件output/neural-native-loop-20260929/round3-attempt02。草稿[PR56](https://github.com/goneveitvet240-svg/cpswm/pull/56)，B未验收，不合并。接着按预先固定66帧计划诊断测量漏检；自然语义、完整神经修订和长期任务仍未闭合，完整框架不缩减。

# A：第三轮两审通过，24次实际比较执行中（2026-09-29）

分支 `codex/pc-a-neural-native-loop-20260929`，base沿开工记录。实际代码 `a8992c02508bcede986f1af9986e5f7dbdc6c5cc` 已完成45/33顺序两轮A自审、mypy377/Ruff。前次5ab9597误混坐标导致合法工件拒绝，未算通过；修后两个实际阳/阴像素样本重新采集并完整重建。SSDLite北处2动作均漏检；Faster R-CNN北处1动作类别阳性、同样第一动作后恢复。6方法×2位置×2前端的24次真实比较执行中，尚未出完整结论；[第三轮报告](../reviews/pc_a/neural_native_loop_2026-09-29/ROUND3.md)。工件output/neural-native-loop-20260929/round3-attempt02。B独立验收未完成、不合并，原生完整神经修订/自然语义/长期效果范围保留。

# A：相机历史来源漏洞修复及重审交付（2026-09-29）

实际代码 `3d917ee4f5a203bd3bddbdfb1fa6a8e71713c372`，分支/base沿本轮开工登记。完整重封的断链动作不能再静默丢弃像素后验；所有者独立记录原生来源，新批次和12来源纠错重放合法路径仍通过。56/41两轮A自审、mypy377/Ruff、两次真实Unity，共8命令源码冻结通过。证据 `output/neural-native-loop-20260929/round2-attempt02/` 与 [第二轮报告](../reviews/pc_a/neural_native_loop_2026-09-29/ROUND2.md)。实际仿真仍两处SSDLite漏检，没有识别成功主张。第三轮固定24次比较实现开工；B正式协议/验收未动，完整范围保留。

# A：第二轮真实像素反馈交付，进入公平比较（2026-09-29）

受测 `01d041189c702c3e7f571f9c565b6fe86aa6b7e5`，56/36顺序两轮A自审、mypy377/Ruff、八命令源码冻结通过。真实Unity两场景4次转动均成功，回包确实改变联合行动概率，第一动作后SQLite恢复同视图再继续；原生批次及长期账本均保持。

但SSDLite在实际可见554/558目标像素的两帧均漏检苹果，假设观测模型因此把可见位置降权，两场景均未获得苹果类别阳性；不可称理想仿真任务成功。[第二轮报告](../reviews/pc_a/neural_native_loop_2026-09-29/ROUND2.md)。完整output/neural-native-loop-20260929/round2-attempt01。Faster R-CNN同RGB离线诊断及公平比较继续，正式架构未选。B未验收、不合并，完整范围保留。

# A：第一轮神经原生接入完成，进入仿真反馈（2026-09-29）

分支 `codex/pc-a-neural-native-loop-20260929`，base `2a0bbdf2e77e76b8e45d5f92211e820d337c3cf3`，受测源码 `08e5cc1f5cdb049d7bbd68b66e4da829a59e4efd`。43/16顺序两审、mypy375/Ruff、三网络真实12→撤回1→重放11→SQLite同视图/状态全部通过；22原生记录、2当前原子、6维位姿、11份实际模型证明。原生发布和恢复的完整伪造概率/已加载验证函数攻击已修复。

[第一轮报告](../reviews/pc_a/neural_native_loop_2026-09-29/ROUND1.md)。完整工件主仓output/neural-native-loop-20260929/round1-attempt01。有限支撑枚举q/q正确性，不是神经性能收益、六操作全闭合或自然训练。B独立验收未完成，不合并。第二轮按预先固定计划接实际相机反馈到短时联合行动视图；不把单次未检出授予长期记忆撤回资格。

# A：神经原生接入、仿真闭环与比较诊断开工（2026-09-29）

用户授权五小时按三个顺序推进，开工 UTC 2026-09-28 17:05:56，工作预算截止 UTC 22:05:56（北京时间 06:05:56）。分支 `codex/pc-a-neural-native-loop-20260929`，独立目录 `/private/tmp/cpswm-pc-a-neural-native-loop-20260929`，base/开工源码 `2a0bbdf2e77e76b8e45d5f92211e820d337c3cf3`。fetch 成功：共享集成 `19ddf26830348a2f0b33f0af54d6ba702c5cfb1c`、B `fd4ca6ef5e81c90d7cf7987b42c0b2810d8a810a` 未变。

顺序：1）真实检查点/完整提议概率到原生状态更新和撤回重放接入；2）同历史实际仿真动作—观察闭环，受控语义与自然视觉分开；3）有区分力的开发基线诊断。每轮实现冻结后依次两轮 A 局部对抗自审，发现生产缺陷则修复并重跑两轮，再继续。独立审核者仍为 0，B 正式比较/验收所有权不变。

A 拥有 native 联合生产、主干与连续入口的本轮增量、专属测试和仿真工具；必要改动粒子消费者用于本轮模型绑定，保持已集成 B 五边界修复，拒绝覆盖 B 未完成修改。第三步以新增 A 开发工具验证接口和机制区分力，不改 B 专属比较生产模块。保留完整 H/R/I/C/Z/r/V、三个 RB blocks、七算子、多人物/隐藏事件/开放世界/可逆/具身；不放宽资格门，不用自报通过替代实际模型执行。

三种已有神经候选采用参数化接入与分别记录，不代选正式胜出架构。未定正式先验/权限/预算作为显式配置与未决项保留，不把已打开开发诊断升级为确认。无新收费算力或外部联系，共享分支不自动合并。旧自动接续保持暂停，本次在当前任务持续推进。

证据目录 `docs/reviews/pc_a/neural_native_loop_2026-09-29/`；持久本地工件 `output/neural-native-loop-20260929/`。本轮测试尚未运行。开工登记推送后表示任务已共享，不能继承旧版本通过。

# A：VISOR 图像/偏置对照与分离视频诊断交付（2026-09-28）

分支 `codex/pc-a-visor-feature-control-20260928`，base `365eac5d6989f18d6e272e4615c160afbcbbdd2e`，实际受测源码 `61eafe4e2a8e57ff2660a5797e0bdbc43366c058`。57/53顺序两轮A局部自审、mypy374/Ruff、6命令与执行器exit0；931 Python每条命令前后同Git。前三次测试预期/收集失败与修复保留，不冒充生产通过或B验收。

已取得P01_03完整61帧/64手关系（57接触、2无接触、5未知），与训练P01_01分开但同一参与者。原骨干冻结，图像/偏置各128次真实非零梯度参数更新，保留16/128两个预算；另8次隔离恢复下一更新检查；新进程从头训练/全61帧诊断后四模型/manifest/报告逐字一致。16步图像参数与上一轮完全相等。

新视频目标：图像16/128步1.088961/0.789911，偏置1.160622/0.991537，训练频率解析常数0.725423。图像优于同SGD预算偏置，但仍不及解析常数；128步无接触类BCE图像1.343687、偏置0.904045，图像更差。循环错配小幅恶化只提供有限图像依赖，不能主张接触/召回/跨人物收益。

[报告](../reviews/pc_a/visor_feature_control_2026-09-28/REPORT.md)。45文件19,728,143字节完整逐文件备份主仓output/visor-feature-control-20260928/closed；新数据为公开作者训练源，不是新增独立本地人工复核。下一主项是扩充可信训练与无接触监督，保留视频隔离和常数/分类诊断，再检验候选生成/对应。三完整提议网络自然联合训练/自然发布/记忆/动作仍未闭合。

最后fetch核验共享集成 `19ddf26830348a2f0b33f0af54d6ba702c5cfb1c`、B `fd4ca6ef5e81c90d7cf7987b42c0b2810d8a810a` 未变。本轮为A局部开发对照，B正式比较所有权及完整框架不变；待B独立复核、不合并，旧自动接续暂停。

# A：VISOR 图像特征对照与分离视频诊断开工（2026-09-28）

独立分支 `codex/pc-a-visor-feature-control-20260928`，base/开工源码 `365eac5d6989f18d6e272e4615c160afbcbbdd2e`。fetch 已确认集成 `19ddf26830348a2f0b33f0af54d6ba702c5cfb1c`、B `fd4ca6ef5e81c90d7cf7987b42c0b2810d8a810a` 未变。A 负责新的隔离开发探针与数据入口，不改 B 正式比较协议，不合并集成分支。

保留上一轮 P01_01 前8帧训练与冻结既有视觉骨干，图像特征线性读出和仅偏置读出均零初始化、相同 SGD lr0.01 与帧序。固定两个预算16和128更新，均保留结果，不按诊断结果选预算。另给出按相同逐帧目标求得的训练频率解析常数参照。仅用于排查图像是否提供可利用信息，不选新正式架构、部署阈值或论文指标。

按官方目录中的下一训练视频 P01_02 获取完整作者稀疏标注/RGB；若该视频不存在，则按目录中字典序下一视频记录替代依据后继续。先核查已知更正、手套/schema 和完整正负监督支持，再确定数据可用性；不依据模型结果挑帧，保留完整视频分母。新视频为另一已公开训练视频的开发诊断，不宣称独立人员、场景或正式validation/test。两类不足或不支持记录均显式报告，不能默默筛除。

主实验保持RGB-only；另用固定帧循环错配作图像依赖的消融诊断，作者标签永不进入骨干输入。按全帧目标和两轴正/负类分别记录BCE，避免多数类掩盖失败；这些是辅助诊断，不替代动作收益/原冻结指标。不得把训练小探针称为完整三提议网络联合学习。

实现后冻结全部Python，依次进行两轮A局部对抗自审（含合法优化/恢复与完整伪造包），再实际运行并新进程复算。若修代码则重新冻结并重跑两审。B独立复核待交接。保持完整H/R/I/C/Z/r/V、三个RB blocks、七算子和自然行动任务；旧自动接续仍暂停。

证据目录 `docs/reviews/pc_a/visor_feature_control_2026-09-28/`。测试及新数据下载尚未执行。

# A：VISOR 全图监督及真实梯度探针交付（2026-09-27）

分支codex/pc-a-visor-pixel-supervision-20260927，base7f9d6def715169d19079f1d72f09ccf24cfe6169，受测38224fece7f0ad2baec2293d62a79f7608150b99。58/45顺序两轮A局部自审、mypy372/Ruff、8实际命令和执行器exit0；925 Python每命令前后同Git。完整485帧两轴像素监督源重建；未标注/冲突忽略，未知接触保留手存在监督。

固定前8帧两遍、后8帧只诊断，冻结现有FPN，仅训练隔离514参数读出。16次非零梯度及参数变化，另2次隔离下一更新恢复检查；原模型参数/缓冲未变；新进程从头16+2次重放后report/head逐字一致。训练目标1.2130→1.0790、后8帧1.2997→1.1468，但事后不看RGB的标签频率常数反例更低（0.5207/0.3631），不能主张视觉能力收益。后8帧接触负像素0，非独立验证。

[报告](../reviews/pc_a/visor_pixel_supervision_2026-09-27/REPORT.md)。完整数据/参数/日志备份主仓output/visor-pixel-supervision-20260927/closed并逐文件SHA核验，最新清单见该根上级backup-manifest.json。下一主项：图像特征与仅偏置读出受控对照、正负均覆盖的分离视频检查，再接候选生成/对应。三提议网络自然训练/自然发布/记忆/动作仍0；B未验收、不合并，旧定时接续暂停，完整范围保持。

# A：VISOR 全图像素监督与冻结骨干学习探针开工（2026-09-27）

独立分支codex/pc-a-visor-pixel-supervision-20260927，目录/private/tmp/cpswm-pc-a-visor-pixel-supervision-20260927，base/开工源码7f9d6def715169d19079f1d72f09ccf24cfe6169。已fetch确认集成19ddf26830348a2f0b33f0af54d6ba702c5cfb1c、B fd4ca6ef5e81c90d7cf7987b42c0b2810d8a810a未变。

上一轮揭示候选配对不能直接作真值。本轮将作者多边形/接触状态转成隔离的全图像素目标：手存在轴使用所有明确手掩膜及其他已标注实体；接触轴只使用明确接触/无接触手像素。未标注、跨类型冲突、接触未知/冲突均忽略，不把背景或未选物框造负例。模型输入只有原图，无作者ROI/掩膜/身份/接触输入。

实现后冻结Python，依次两轮A局部对抗审查，再构建完整485帧监督包并实际运行开发学习探针：冻结既有FasterRCNN-FPN官方骨干与原变换，只学习零初始化两通道1×1读出；固定前8帧训练2遍、后8帧仅诊断，各帧顺序不按标签/检测成功筛选；CPU两线程、SGD lr0.01、掩蔽二元交叉熵每轴按有效像素平均后相加，不做类别加权/早停/调参。该微型探针检查真实梯度和恢复，不是新正式架构、精度门限、独立验证集或三提议网络训练，原前端不替换。

保留完整研究范围；本轮不产生可信候选配对、人物身份、精确释放或自然动作权限。B未验收、不合并，旧自动接续保持暂停。证据docs/reviews/pc_a/visor_pixel_supervision_2026-09-27/；测试与训练尚未运行。

# A：VISOR 全量候选对齐交付（2026-09-27）

独立分支codex/pc-a-visor-candidate-alignment-20260927，base ced69a60c2e81d37f7b9012276451a6778b78020；最终评估受测860bc46a05bed4b805badbf351154292b0761653，79/43顺序两审、mypy370/Ruff、8命令及执行器exit0，919 Python前后同Git。真实485帧预测生产于98c64b1df1008422c1af6f5056fb371edd9c96c9；修后自动证明推理代码不变，固定摘要复用，不伪称重新推理。

完整485帧/2,876掩膜，1,041手候选、5,300非人物物候选、1,187人物候选。809作者手关系中268无地标覆盖；680明确接触中218至少一侧缺失，462两侧有几何，其中446多组合、16唯一组合仍不保证正确。首版物侧误计person的3个唯一组合被真实反例否决；沿用既有actor/instance类型规则修正后重审、重算、实际回读，旧结果保留。

[报告](../reviews/pc_a/visor_candidate_alignment_2026-09-27/REPORT.md)。30文件26,153,681字节逐文件SHA备份主仓output/visor-candidate-alignment-20260927/closed。下一主项：补候选对应监督与第一视角手部覆盖，再接组件训练，不能用唯一几何组合或未选物框自动造标签。新增训练/自然发布/记忆/动作0；B未验收、不合并，完整范围保持，旧自动接续暂停。HFD46/96及10/24仍部分覆盖。

# A：VISOR 候选—人工掩膜逐帧对齐开工（2026-09-27）

独立分支 codex/pc-a-visor-candidate-alignment-20260927，目录 /private/tmp/cpswm-pc-a-visor-candidate-alignment-20260927。base/开工代码 ced69a60c2e81d37f7b9012276451a6778b78020。fetch 已核验共享集成19ddf26830348a2f0b33f0af54d6ba702c5cfb1c、B fd4ca6ef5e81c90d7cf7987b42c0b2810d8a810a，均未变。

本轮固定上一轮P01_01全部485帧，以现有FasterRCNN和MediaPipe全图+人物区域默认配置推理；RGB输入与监督离线分离。保存全部前端候选及每个候选对每个适用作者掩膜的几何量，不选匹配阈值、不以最高重叠自动授予接触标签。记录无候选、无重叠、多重重叠及跨区域重复可能，分母保留全部帧/作者关系。零新增正式训练、语义发布、记忆写入和动作；不推断稀疏帧释放时间或跨帧身份。

先冻结Python并顺序执行两轮不同设计的A局部自审，覆盖合法正路径、完整重封伪造、标签隔离、同帧来源与重试；再跑真实全部帧并源绑定复核。证据 docs/reviews/pc_a/visor_candidate_alignment_2026-09-27/。尚无本轮测试结果；B未验收、共享分支不合并、旧自动接续保持暂停，完整研究范围保持。

# A：VISOR 接触监督完整子集交付（2026-09-27）

分支codex/pc-a-visor-contact-supervision-20260927，base b31ba02b17fdf28c9ad8cf2224f10a34b6e79ffb；实际受测7fba64d39699be5e47fe1b9867583ac8c3854f62。63/44顺序双审、mypy369/Ruff通过，7实际命令与执行器exit0，914 Python前后同Git。完整485训练稀疏帧：680明确接触+74无接触，55未知关系保留，23无手帧不当负例。标签隔离、来源重建和组件读取实际通过；初版乱序失败修复后重审，失败保留。

517文件366,344,895字节逐文件SHA校验备份主仓output/visor-contact-supervision-20260927/closed。证据[本轮报告](../reviews/pc_a/visor_contact_supervision_2026-09-27/REPORT.md)，命令入口run_frozen.py；受测源码后只文档交付。最后fetch集成19ddf26830348a2f0b33f0af54d6ba702c5cfb1c、B fd4ca6ef5e81c90d7cf7987b42c0b2810d8a810a未变。

A局部自审，B未验收、不合并；新增优化/自然发布/记忆/动作0。单帧作者接触不等于精确释放、身份或前端位姿校准，完整自然闭环未完成。下一主项：当前前端候选与该人工掩膜逐帧对齐及漏检/配对歧义，再接组件学习监督；科学选型和完整研究范围保持。旧自动接续保持暂停。上轮46/96及10/24仍单独部分覆盖。

# A：VISOR 作者人工接触监督接入开工（2026-09-27）

独立分支 codex/pc-a-visor-contact-supervision-20260927，目录 /private/tmp/cpswm-pc-a-visor-contact-supervision-20260927，base/开工实际代码 b31ba02b17fdf28c9ad8cf2224f10a34b6e79ffb。已 fetch 核验共享集成19ddf26830348a2f0b33f0af54d6ba702c5cfb1c、B fd4ca6ef5e81c90d7cf7987b42c0b2810d8a810a未变；上一轮46/96及10/24部分覆盖保持原状。

本轮推进接触监督缺口：核验公开VISOR人工稀疏接触关系、作者已知更正和原始训练图像；预先固定训练视频子集，不按标签或检测成功筛选。建立源绑定、标签隔离和未知/歧义保留的学习数据入口，实际统计能支持的目标；不以插值标签充人工标签，不把本数据接触关系映射成HFD接触真值或精确释放/人物身份/位姿校准。先冻结Python后顺序两次不同设计的A自审，含合法正路径、完整重封伪造、重放及账本动作边界，再真实包复验。测试尚未运行。

证据 docs/reviews/pc_a/visor_contact_supervision_2026-09-27/。仅现有本机CPU和公开训练数据，无费用、外部联系、正式架构/训练日程选择或共享合并；完整H/R/I/C/Z/r/V、三解析块及七算子保持。旧三小时自动接续继续暂停，本次为用户新的接续授权。

# A：三小时推进封存，最终矩阵 46/96，恢复 10/24（2026-09-27）

第五轮固定矩阵实际完成 **46/96** 个评分/消融组合和 **10/24** 个首窗恢复组合，9/24 分片完整完成。19/32 个窗口至少一种网络完成，13/32 窗口三网络均完成；已完成组合涉及 76/128 唯一原帧。 受测 `7549f1eaaf16a50bc5ab8be30877f504883b3a65`，296/80 两审、mypy368/Ruff 通过，909 Python 前后同源；9 分片退出0、8 到预定16:40 UTC截止超时、7 未启动。所有完成工件另行回读通过，备份 95 文件、18,050,946 字节逐文件 SHA256 一致。未完成仍保留在分母，不拼接旧17组合。

分支 codex/pc-a-sharded-hand-matrix-20260926，base1cdc0889516c39227d9213f3574f3ae0418cd1e9；源码后仅文档交付。五轮草稿 PR47–51；[总进度](../结构二/05_三小时主路径推进_2026-09-26.md)、[最终证据](../reviews/pc_a/sharded_hand_matrix_2026-09-26/REPORT.md)。最后 fetch 已验证集成19ddf26830348a2f0b33f0af54d6ba702c5cfb1c、B fd4ca6ef5e81c90d7cf7987b42c0b2810d8a810a未变。B未验收、共享集成未合并。

主缺口仍是可信事件/身份/当前前端位姿误差监督、真实训练及自然行动反馈；本批自然训练/语义发布/行动0。保持完整研究范围，后续优化仅为待办。三小时预算到期收口并暂停自动接续，不再开始新轮。

# A：第五轮双审完成，固定96组合分片运行中（2026-09-27）

受测7549f1eaaf16a50bc5ab8be30877f504883b3a65；296/80两审、mypy368/Ruff通过后，UTC15:52:34启动24分片、最多8进程。每臂8片，各4窗口与1首窗恢复，合计计划96评分和24恢复组合。909受测Python冻结，每命令前后核对Git；最终完成数与总摘要待收口。[当前总进展](../结构二/05_三小时主路径推进_2026-09-26.md)、[第五轮报告](../reviews/pc_a/sharded_hand_matrix_2026-09-26/REPORT.md)。

前四轮报告与备份已合入本分支文档，实际Python仍与7549f1e逐字相同。第三轮旧17/96不拼接；第四轮真实三臂243候选回执等价验证完成。计算截止UTC16:40，授权截止16:47:47，B未验收、共享集成未合并，完整自然闭环仍缺。

# A：第五轮固定矩阵分片开工（2026-09-26）

base/开工源码1cdc0889516c39227d9213f3574f3ae0418cd1e9，独立codex/pc-a-sharded-hand-matrix-20260926，目录/private/tmp/cpswm-pc-a-sharded-hand-matrix-20260926。第四轮e018c432c2c6f4181b8521c4ea2eb7a700be971b已通过284/74两审和真实首窗三臂243候选完整回执逐字对照；906 Python前后同源。仅规范化内部标量快路径，所有篡改校验保留。

本轮将原8试次×4窗口×三臂的固定96组合按来源和窗口序号轮转分成互斥分片；每臂8片、每片4窗口和1个首窗恢复组合；仅依固定完整候选数量估计工作量，先调度较重分片，最多8个独立CPU进程。完整候选、原权重、科学阈值及128原帧不变。分片集合必须并集等于全部计划且两两不重叠，实际工件也逐项复核；先冻结双审再真实运行。旧第三轮主动停止结果单列，绝不拼接补分母。计算截止UTC16:40，授权16:47:47不变，未完成仍明确计数。

# A：第四轮规范化提速双审与真实等价验证完成（2026-09-26）

受测e018c432c2c6f4181b8521c4ea2eb7a700be971b：284/74两审、mypy368/Ruff、5命令与执行器exit0，906 Python前后同源。9行严格内置标量快路径，全部候选和指纹检查保留。固定真实首窗三臂各243候选完整目标/概率回执逐字相同，完整评分本次耗时减少约22%/31%/23%；共享主机计时，不是公平速度或能力增益结论。[报告](../reviews/pc_a/canonical_speed_2026-09-26/REPORT.md)。

14文件19,665,825字节已逐文件校验备份主仓output/canonical-speed-20260926/closed。A自审、B未验收、无新训练/自然发布/动作。第三轮仍是17/96部分覆盖；第五轮独立分片从头运行全部96，不能把不同版本拼接成完成。授权截止UTC16:47:47不变。

# A：三小时第四轮规范化评分性能开工（2026-09-26）

base/开工源码60453f212c7a9435b272cbd4aece3cf8db4be4a8；独立分支codex/pc-a-canonical-scoring-speed-20260926，目录/private/tmp/cpswm-pc-a-canonical-scoring-speed-20260926。第三轮228/51两审已通过，原目录真实矩阵仍独立运行，不修改它的Python或拼接新旧结果。GitHub fetch已验证集成19ddf26830348a2f0b33f0af54d6ba702c5cfb1c、B fd4ca6ef5e81c90d7cf7987b42c0b2810d8a810a未变。

只读profile显示243候选一次评分有1,461条件节点和约35万次候选处理，规范化摘要占主要插桩耗时。先用严格内置标量类型快路径降低重复类型判断，保留原完整校验次数和摘要语义，不引入信任缓存或跳过篡改检查。独立差分参考保存原源码；计划完整结构值/异常/负零/枚举差分，以及三臂全q、恢复、原篡改路径双审。尚无本轮测试结果；授权截止UTC16:47:47不变，计算最晚16:40停止，无新训练/模型选择/自然发布。

# A：第三轮以部分覆盖封存，完整矩阵由第五轮重新运行（2026-09-26）

草稿PR49，受测60453f212c7a9435b272cbd4aece3cf8db4be4a8：228/51两审与静态检查通过，901 Python前后同源。旧final-03实际17/96评分组合（5/7/5），6/24恢复组合；UTC15:48主动停止各旧进程-15，总执行器exit1。全部已完成结果无候选截断，但矩阵未完成。证据已逐文件校验备份主仓output/full-hand-proposal-matrix-20260926/closed，完整报告与原尝试保留。

第四轮严格规范化快路径已通过284/74两审及真实三臂243候选完整回执逐字对照。第五轮在独立codex/pc-a-sharded-hand-matrix-20260926从头执行同一96组合的互斥分片，不用旧17补分母。计算截止16:40 UTC，授权16:47:47不变，B未验收、共享集成未合并。

# A：第三轮双审完成，真实矩阵运行中；第四轮独立性能验证（2026-09-26）

第三轮受测源码60453f212c7a9435b272cbd4aece3cf8db4be4a8，228/51两审及mypy368/Ruff已通过，901个Python冻结。全32窗×三臂的96组合矩阵在本目录final-03运行，尚未完成，不能用计划数代替完成数。首窗24组合有采样恢复，其余72只做完整评分和状态检查；时间截止16:40 UTC。[第三轮报告](../reviews/pc_a/full_hand_proposal_matrix_2026-09-26/REPORT.md)。

发现规范化占主要插桩耗时后，第四轮在独立目录/private/tmp/cpswm-pc-a-canonical-scoring-speed-20260926、分支codex/pc-a-canonical-scoring-speed-20260926推进严格标量快路径，base同60453f2；第三轮Python保持不动。第四轮计划原/新内容身份与完整q差分、两审和真实三臂比较；实际结果以该分支交付为准，不拼接新旧版本。B未验收，集成与科学范围不变，三小时授权截止UTC16:47:47。

# A：三小时第三轮完整四帧窗口矩阵开工（2026-09-26）

前轮[草稿PR48](https://github.com/goneveitvet240-svg/cpswm/pull/48)已完成224/44两审及24个真实两帧组合。新分支 `codex/pc-a-full-hand-proposal-matrix-20260926`，目录 `/private/tmp/cpswm-pc-a-full-hand-proposal-matrix-20260926`，base/开工代码 `6b9f260530d53ac9c1a58ca35cb881ed86a48cf7`。已fetch核验集成与B仍为19ddf26830348a2f0b33f0af54d6ba702c5cfb1c、fd4ca6ef5e81c90d7cf7987b42c0b2810d8a810a。

计划32既定窗口四帧×三臂共96组合，全候选q及同支持手部消融；每个试次首窗额外采样恢复/下一次采样和相同输入重复评分，其他窗仅评分前后请求/RNG不变，分别记录。截止前保留未完成分母，不改原权重、数据、门限或截断。实现只有实验矩阵编排，生产src不变；冻结后两轮不同审查。计划16:40 UTC停止计算，为16:47:47授权截止前备份交付留时间。证据 `docs/reviews/pc_a/full_hand_proposal_matrix_2026-09-26/`，尚无本轮结果。

# A：三小时第二轮手物提议输入已双审和三网络实际验证（2026-09-26）

分支 `codex/pc-a-hand-proposal-input-20260926`，base PR47 `74db008222979e4ae508a7c6fded524ae62e19ae`；实际受测 `b55867d0138c2af2c39175cba18123d99c8bd60b`。224/44两审、mypy368/Ruff通过，9命令exit0，898 Python前后同Git。128帧/32窗中378区域手候选、2,530手物测量、34未决人物对进入模型特征；24个试次×网络两帧组合完成固定目标消融、完整质量及恢复/下一次采样。概率差很小，仅输入响应，无准确率/校准收益；新优化/自然发布/动作0。

136文件28,101,313字节校验备份 `output/hand-proposal-input-20260926/closed/`。A自审、B未复核，不合并集成。[报告与范围](../reviews/pc_a/hand_proposal_input_2026-09-26/REPORT.md)。下一轮对全部既定32窗做四帧三臂完整分布评分，并对每个试次首窗做采样恢复；其他窗仅评分状态检查，分别报告，截止UTC16:47:47不变。

# A：三小时第二轮手物提议输入开工（2026-09-26）

第一轮[草稿PR47](https://github.com/goneveitvet240-svg/cpswm/pull/47)的185/34两审和128原帧全窗复跑已经封存，才开始本轮。新分支 `codex/pc-a-hand-proposal-input-20260926`，目录 `/private/tmp/cpswm-pc-a-hand-proposal-input-20260926`，base/开工实际代码 `74db008222979e4ae508a7c6fded524ae62e19ae`。再次fetch，集成19ddf26830348a2f0b33f0af54d6ba702c5cfb1c、B fd4ca6ef5e81c90d7cf7987b42c0b2810d8a810a未变。

主项是源绑定未校准手检测、前缀重算手物关系和身份未决条件进入三类网络输入，并用固定支持检查真实消费。无本轮测试结果。固定128原帧全部上下文，先用预定8试次首窗前2帧×三臂消费/恢复，剩余时间再扩四帧；不按成功筛样本。完整科研范围、原权重与门限不变，无自然训练/权限新增。两轮源码绑定自审后才进入下一轮。证据 `docs/reviews/pc_a/hand_proposal_input_2026-09-26/`。截止UTC16:47:47。

# A：三小时第一轮身份歧义已双审并真实复跑（2026-09-26）

分支 `codex/pc-a-person-ambiguity-20260926`，base PR46 `47a51cc88c1cd9bc1d661eaedf12e703fee48983`，受测源码 `4b576567d11258f18697ad74c680e91cadf77cde`。185/34 两轮自审、mypy367/Ruff通过，8命令与总执行器exit0，893 Python前后同Git。原337试次重建和新进程复验通过；128原帧/32窗产生34未决人物对，原64角色均绑定不同人条件，仍不是真实身份成功。1,002检测与8,012完整候选，原像素逐帧同前轮；恢复、记忆/账本/动作检查通过。新训练/自然发布/动作0。

470文件139,975,519字节校验备份主仓 `output/person-ambiguity-20260926/closed/`。完整检测缓存伪造可通过一致性恢复但不能获得语义输出的边界已实测；非身份执行认证。A自审、B未复核、不合并集成。下一轮接手物和人物歧义到三类网络并做固定支持消费检查；授权截止UTC16:47:47不变。[本轮报告](../reviews/pc_a/person_ambiguity_2026-09-26/REPORT.md)。

# A：三小时主路径推进开工（2026-09-26 21:47）

新授权截止北京时间次日 00:47:47。独立分支 `codex/pc-a-person-ambiguity-20260926`，工作目录 `/private/tmp/cpswm-pc-a-person-ambiguity-20260926`，base/开工代码 PR46 `47a51cc88c1cd9bc1d661eaedf12e703fee48983`。已 fetch，集成 `19ddf26830348a2f0b33f0af54d6ba702c5cfb1c`、B `fd4ca6ef5e81c90d7cf7987b42c0b2810d8a810a` 不变。

先处理人物对身份未决条件，再接手物观测到提议网络，最后固定真实样本复跑。每轮源码冻结后两次不同自审，失败修复则两审重跑；测试/实验时不编辑 Python。尚无本轮通过结果，当前实际源码同 base。完整范围和科学选择保持，不新增费用、正式训练、共享合并或对外联络。[限时计划](THREE_HOUR_20260926.md)。

# A：HFD 连续窗口已双审运行，角色质量暴露新缺陷（2026-09-26）

[草稿 PR46](https://github.com/goneveitvet240-svg/cpswm/pull/46)，已推送，叠加 PR45，未合并共享集成。

分支 `codex/pc-a-hfd-continuous-windows-20260926`，base PR45 `4f1717bc5ab596a5870d58f7206fc7eaf7a63b19`；最终受测/真实源码 `16df89b13576ba1af83564169caaed0102b4c2b2` 已推送，证据文档随本次交付推送。首审178、二审26（12新增+14既有来源回归）、mypy367/Ruff通过，7条命令与总执行器exit0，889个Python前后同Git。首个MediaPipe沙箱图形服务崩溃及夹具错误均保留；本机固定CPU模型重跑通过，无依赖/阈值变更。

实际8试次128原帧/32短窗：1,002检测、601几何关联、378区域手候选、2,530手物测量；完整支持8,012候选，全部窗口无截断且恢复/core/ledger检查通过。64角色候选集中于11帧，逐帧AI视觉核查均是单个人体被重复/局部分框，不能当多人角色成功或训练正标签。104帧仍少于两个人物候选；精确接触/释放、机器人参与者与身份校准未闭合。新训练/自然发布/记忆/动作0；手物测量尚未成为提议网络输入。

891文件、300,184,812字节已逐文件校验备份主仓 `output/hfd-continuous-windows-20260926/closed/`。A两轮自审，B未复核，完整自然闭环仍未完成。下一主项：处理同一人多框造成的虚假多人角色，同时保留真实多人重叠正路径、未知身份和机器人角色，再接手物证据消费；未擅自调NMS/科学先验或选择训练方案。集成19ddf26830348a2f0b33f0af54d6ba702c5cfb1c、B fd4ca6ef5e81c90d7cf7987b42c0b2810d8a810a未变；不合并共享集成，旧八小时自动接续仍暂停。[完整报告、反例与复跑入口](../reviews/pc_a/hfd_continuous_windows_2026-09-26/REPORT.md)。

# A：HFD连续原帧窗口与手部关联开工（2026-09-26）

独立分支 `codex/pc-a-hfd-continuous-windows-20260926`，目录 `/private/tmp/cpswm-pc-a-hfd-continuous-windows-20260926`；base/开工源码PR45 `4f1717bc5ab596a5870d58f7206fc7eaf7a63b19`。已fetch核验集成19ddf26830348a2f0b33f0af54d6ba702c5cfb1c、B fd4ca6ef5e81c90d7cf7987b42c0b2810d8a810a未变。前轮最终138+14审查、32帧实际结果和备份已交付后才开始此轮。

主项：同八层开发试次，固定四个均匀短窗口、每窗四个连续原帧；保留原时钟、来源重建和答案隔离。接既有MediaPipe人物区域手部入口，逐窗口检查视觉关联/角色候选、手物几何和完整提议支持。保持关联器1秒门和模型原参数，重叠窗口明确统计独立原帧与重复呈现；短窗口不冒充完整交接跟踪。预期真实128唯一原帧/32短窗口，尚未有实际结果。

冻结后两轮不同A自审，覆盖正路径/内部一致完整伪造/恢复重试/账本与动作后果，再运行真实矩阵。证据目录 `docs/reviews/pc_a/hfd_continuous_windows_2026-09-26/`。本地CPU两线程与已有权重，无收费资源、正式训练、自然发布或B签收。科研选型及完整统一框架保持；旧八小时自动接续仍暂停，不合并共享集成。

# A：HFD原帧对齐、真实运行与加强双审交付（2026-09-26）

[草稿PR45](https://github.com/goneveitvet240-svg/cpswm/pull/45)，已推送，未合并共享集成。

分支 `codex/pc-a-hfd-observation-alignment-20260926`，base PR44 `34ad8d35f12d74bd6c2c357e73db32b69b9e5add`。真实执行 `1c180cfdecc35bed0233d89646201398c5b1217d`；最终双审 `dc2c23183d244a443fae05494912b6cd7619d81a`（只加强第二审脚本，生产src/tools/tests逐字相同）。首轮138、第二轮14、mypy367/Ruff通过；两个冻结阶段各885个Python前后同Git。完整伪造包先内部一致通过结构准入，再由原归档拒绝。修复重复传感器来源、结果排序时间侧信道及随机metadata ID。

已源重建全部337训练试次，实际8层8试次/32原帧进入连续感知，248检测、14,637完整候选；作者监督隔离。角色候选0：原帧间隔3.035–8.380秒均大于现有1秒关联门，下一主项是固定连续原帧窗口和手部/目标物关联诊断，尚未启动新轮。全零/超原力范围9/3帧保留；完整提议target/新训练/自然发布/记忆/动作0，未把导入时刻当物理事件时刻。

159文件、74,018,060字节已校验备份主仓 `output/hfd-observation-alignment-20260926/closed/`。A两次自审，B未复核，完整自然闭环与统一验收仍未完成，不合并共享集成。远端集成19ddf26830348a2f0b33f0af54d6ba702c5cfb1c、B fd4ca6ef5e81c90d7cf7987b42c0b2810d8a810a不变；旧八小时自动接续保持暂停。科学选择/完整研究框架保持。[本轮报告及复核入口](../reviews/pc_a/hfd_observation_alignment_2026-09-26/REPORT.md)。

# A：HFD原帧运行输入与作者监督对齐开工（2026-09-26）

新独立分支 `codex/pc-a-hfd-observation-alignment-20260926`，目录 `/private/tmp/cpswm-pc-a-hfd-observation-alignment-20260926`，base/开工代码 `34ad8d35f12d74bd6c2c357e73db32b69b9e5add`（PR44）。本轮已fetch核验集成19ddf26830348a2f0b33f0af54d6ba702c5cfb1c、B fd4ca6ef5e81c90d7cf7987b42c0b2810d8a810a不变；PR43/44两轮自审及真实输入结果已封存。

主项：新增按原始帧序号的RGB入口，把正常/失败交接视频接到既有连续感知与完整候选生成；作者阶段、结果、力数据只在隔离评价侧按原帧配对，不能以重采样序号假定对齐。固定开发样本包含全部8种方向×结果分层，保留337试次分母和未处理范围。完整提议目标/位姿校准仍缺，不擅自选择训练损失或填写身份/隐藏事件真值。冻结后逐轮两次不同自审并验证实际数据；B复核/科学验收另列，旧八小时自动接续保持暂停。

目前尚未有本轮代码测试通过。证据目录计划 `docs/reviews/pc_a/hfd_observation_alignment_2026-09-26/`；CPU两线程，本地既有权重，无新增付费资源、正式训练或共享集成合并。

# A：HFD全训练证据已双审、337试次及重建通过（2026-09-26）

`codex/pc-a-complete-hfd-resume-20260926`，base PR43 f72413fdd55bb3324ca064c02ba1fd8507aba54b，受测Python `c10a311430ff68ecce4aea0eaa6b3039e2f88974`。修前12个实际反例已保存，修后首审32、二审19、mypy366/Ruff通过。337试次/141,462帧全部实际解码配对，90作者成功、247其余结果；新进程从原完整归档重建相同，6命令和总执行器exit0，879个Python文件前后同Git。

3,052文件、2,410,627,477字节完整原始/evaluator及成功失败证据校验备份主仓 `output/complete-hfd-resume-20260926/closed/`。77试次89帧超出原始力时间范围及所有全零力数据保留，作者单人阶段不升级为精确接触/身份/前端校准；新训练、自然发布/动作0。两轮A自审，B未复核，草稿PR44不合并集成。下一主项是正常/失败资料到运行观测和现有提议监督的合法对齐及自然质量诊断；科学选型和完整统一框架不变。[完整报告、范围与复核入口](../reviews/pc_a/complete_hfd_resume_2026-09-26/REPORT.md)。

# A：HFD完整证据接续开工（2026-09-26 19:24）

分支 `codex/pc-a-complete-hfd-resume-20260926`，独立目录 `/private/tmp/cpswm-pc-a-complete-hfd-resume-20260926`，base/开工实际源码PR43 `f72413fdd55bb3324ca064c02ba1fd8507aba54b`。已fetch：集成19ddf26830348a2f0b33f0af54d6ba702c5cfb1c、B fd4ca6ef5e81c90d7cf7987b42c0b2810d8a810a不变；前轮完整12组合、双审和877文件源绑定已封存后才启动本轮。

接续PR42未完成第二审，检验完整伪造、隔离分母、别名/特殊文件、末次校验漂移、数值时钟及视频标签配对。修复需新SHA上从首审复跑，再执行全部337作者训练试次和新进程全归档重建。9,185,706,983字节原包已匹配作者MD5；尚未接受任何新试次，不访问validation/test、不新增训练、运行权限或科学选择。证据目录 `docs/reviews/pc_a/complete_hfd_resume_2026-09-26/`。两轮A自审，B职责不变，不合并共享集成。

# A：完整支持资源修复已双审并完成12组合（2026-09-26）

`codex/pc-a-complete-support-resume-20260926`，base PR42 `3095a2ac112f7934192177a5ef4725b83188e148`，受测源码 `7c19637791e45dbf28e041beb3b98bc9acd92038`。第一审112、第二审36（18项既有检查重叠）、mypy366/Ruff通过；三原权重303密集对照及旧783输入失败回滚/RNG通过。固定四视频×三网络12组合全部完成，原失败37,241节点案例全三臂通过。14条命令exit0、总执行器exit0，877个Python文件前后与Git相同。候选/原权重/容差保持，新训练和自然发布/动作0。

完整证据逐文件校验备份主仓 `output/complete-support-resume-20260926/closed/`；此前失败/中断和部分备份保留。耗时及局部范围不隐藏，不声称实时或自然闭环。A自审、B未复核，草稿PR43不合并集成。下一轮HFD第二审及337试次实际验收；原始全包已匹配作者MD5，尚无本轮试次接受结果。旧八小时自动接续保持暂停。[报告与B入口](../reviews/pc_a/complete_support_resume_2026-09-26/REPORT.md)。

# A：八小时窗口收尾，第五轮未完成草稿

授权截止北京时间 2026-09-26 11:18:22。最后一次恢复执行读钟为14:18:27，已经超时；之后仅整理现有结果/备份/推送并暂停自动接续，没有重启实验或下载。不能宣称八小时全程持续执行。源码 `cd687f92a3cf23922d94ac24b4b1f62b75ce85a9`，base PR41 `768b2578c1805ec09f073fd8b6a0369bd28bf91b`；本人前轮仅文档最终证据已并入，B文件/共享集成未改。

第五轮第一审4失败修复后21通过；第二轮对抗审查、真实全归档验收和修后全仓检查未完成。373下载分片共6,257,901,568字节，SSL失败，无全包MD5，不接受新真实试次。第四轮最终矩阵3/4视频完整完成、9/12片段×网络组合完成，第三段节点超限；不能称全轮闭合。详见[第五轮草稿](../reviews/pc_a/hfd_normal_evidence_2026-09-26/REPORT.md)、[完整窗口交接](EIGHT_HOUR_20260926.md)。自动接续已暂停；无新增训练/自然发布/自然动作，独立审核者0、B未签收。先闭合现存资源失败及第二审，再开展新一轮。

# 2026-09-26 八小时窗口第四轮最终结果（部分覆盖）

固定源码 `c25fa44d51a42d87b906c844b03b67c39900ff2a` 的两审 99/26、三臂 303 候选/10,246 节点受控验证通过；最终四段视频为 3 完成、1 资源超限失败（9/12 片段×臂完成）。第三段 216→783 候选没有被截断，也没有完成恢复验证，完整长前缀能力仍开放。868 Python 文件运行前后相同，原始证据已备份主仓 `output/full-support-compute-20260926/`。A 自审，B 未复核，新训练/自然发布/自然动作 0；不合并集成。详见 [最终矩阵与边界](../reviews/pc_a/full_support_compute_2026-09-26/REPORT.md)。八小时截止后只做证据整理，不启动新实验。

# 2026-09-26 完整支持计算（A，局部双审交接）

`codex/pc-a-full-support-compute-20260926`，受测源码 `c25fa44d51a42d87b906c844b03b67c39900ff2a`。完整 303 候选/10,246 节点在三臂原权重上均通过数值对照、恢复与失败原子性；第一审 99、第二审 26、mypy 365/Ruff 通过。完整伪造发现后修复非权重结构、缓存张量与候选关联，并保持预定 1e-5 容差。首段固定四帧视频三臂通过（108→324），其余三段扩展测试继续冻结运行，全部结果尚未出齐。A 自审、B 未签收；不增加自然发布或训练。下一主项为已计划的正常交接外部监督接入，保持所有科学路线与完整框架。[报告及修前反证](../reviews/pc_a/full_support_compute_2026-09-26/REPORT.md)。

# 2026-09-26 撤回后的原生联合重放（A，部分交付）

`codex/pc-a-joint-full-replay-20260926` 叠加 PR39；最终源码 `348d11a172d0d26cb6ec990ad930664912f8495d`。原消费序列的撤回重放、代际归档、模型完整类方法绑定、SQLite 恢复及有效下一相机命令已有实现。两轮实际发现四问题，修后 654 回归＋5 第一审＋7 第二审全部通过。受控 12→11 来源、22 记录、2 原子/六维；自然/真实 Unity 动作本轮 0，B 未复核。下一主项是完整支持的可计算推理与更长真实前缀；六操作原生内核/新纠正来源及自然校准继续保留为缺口。[报告/反证/边界](../reviews/pc_a/joint_full_replay_2026-09-26/REPORT.md)。

# 2026-09-26 三解析块计算与原子恢复（A，部分交付）

`codex/pc-a-joint-revision-runtime-20260926` 叠加 PR38；修后源码 `69d8b6a615c2c12f49e4573905596b709b16e809`。已补完整提议到三解析块及六维状态的实际计算，保留原评分目标，神经随机数/条件模型/日志失败回滚与重算恢复。两轮自审发现并修复四项问题；466 回归、11 专项及三检查点各 88 候选运行通过。不是活跃粒子集六操作、联合发布或自然闭环完成；A 下一主任务是正确抽样权重与原生修订/联合发布，B 独立职责保持。[完整报告](../reviews/pc_a/joint_revision_runtime_2026-09-26/REPORT.md)。

# 2026-09-26 真实候选生成与双轮局部审核（A，部分交付）

源码 `40486b981898cb9420fdafe765c9ac49e8e5ff96`，分支 `codex/pc-a-runtime-candidates-20260926` 接续 PR37。实际像素自动候选、三网络、迟到续跑及恢复已实现；444 回归＋第一轮 7 攻击＋第二轮 10 新检查通过，两轮各四视频×三网络实际重跑通过。六操作受控支持 88 候选实际打分；303 候选超网络预算明确拒绝。自然发布/记忆/动作仍 0，未宣称准确率或自然闭环。A 主干下一项是三解析块消费与六操作修订联合发布，B 保留独立复核/比较职责，完整框架不缩减。[本轮覆盖与缺口](../reviews/pc_a/runtime_candidates_2026-09-26/REPORT.md)；[八小时持续推进](EIGHT_HOUR_20260926.md)。

# 2026-09-25 PR36 两轮审核与可恢复检查点推理（A，部分交付）

`codex/pc-a-joint-audit-next-20260925` 叠加 PR36。首轮发现 4 类 P2 并保留 5 失败案例；修复 SHA `4a8bfdcc08f99660778283d1849b86ef17e767c6` 第二轮 391 通过。随后 `5936824c806b2c20b14220e33d89b15a9642ff3e` 实现三网络检查点推理、重复请求/中断回滚和重算恢复，405 回归、mypy 358 通过；实际三份训练权重恢复后各 5 次采样一致。两轮 A 本机审核，独立审核者 0，B 未签收；未合并集成、未选定具体架构/日程。A 下一步仍负责真实完整候选生成、六操作修订核/重放发布与自然证据接入；B 保留独立跨机/比较职责，完整框架和科学门保持。[覆盖、后果与缺口](../reviews/pc_a/joint_audit_next_2026-09-25/REPORT.md)。

# 2026-09-25 数据、训练器与条件纠正重算（A，部分交付）

分支 `codex/pc-a-joint-training-loop-20260925` 接续 PR35，固定源码 `bfe876cdb3fd702f4ac856e1f0d37245cb59d1e4`。540 帧作者监督包，另实际补取 1680 位姿对、801 时刻人际力/动捕与 897 帧外部人工阶段视频；三候选真实优化器与条件撤回后缀重算已实现，383 测试及 mypy 356 通过。仍缺完整自然提议监督、稳定人物/释放正例、实际前端位姿校准、完整粒子修订发布与自然动作强比较；A 继续实现，B 保留独立跨机复核职责。本机自验不能替代完整验收，未合并共享集成。[报告/来源/完整缺口](../reviews/pc_a/joint_training_loop_2026-09-25/REPORT.md)。

# 2026-09-25 两轮审核及配置联合生产连接（A，部分交付）

`codex/pc-a-grounded-audit-native-20260925` 叠加 PR34。首轮发现 3 个来源/完整性问题并修复，二轮固定 `1e6e0373248d3881be67f00922cc7c330b6f1bba` 的 114 项通过；均为 A 本机自审，B 未复核。随后固定 `7a534842ec3b1206bc4c3389e11e558c4a0f31d5`，配置 prepared producer 已自动接入采集与 SQLite 恢复；264 项、mypy 351、真实 Unity 左转/像素回流通过。默认缺模型、已选神经工件与六操作修订内核、独立自然校准、完整自然行动和强基线仍未完成；不以夹具替代，不合并集成。[版本、证据及下一依赖](../reviews/pc_a/grounded_two_round_2026-09-25/REPORT.md)。A 负责后续模型与观测接入，B 保留独立跨机/比较职责。

# 2026-09-25 开发跟踪、非空纠错与重放（A，部分交付）

独立分支 `codex/pc-a-grounded-correction-20260925` 叠加 PR33，实际源码 `d23438d4724d48a093439303b7db3988165ed567`。64 帧辅助标注/首帧跟踪部分可用；三个受控 seed 皆非空撤销与恢复/从头语义重放一致，两个改变放回读出。103 相邻测试通过；自然转移、实际动作和独立强基线未完成。默认 P5 仍无联合粒子 batch，真实调用证据见[报告](../reviews/pc_a/grounded_correction_2026-09-25/REPORT.md)。下一步 A1 补默认完整候选/三解析块生产到动作消费；B 复核所有权不变，未合并集成。

# 真实交接阶段监督与标签隔离（A，2026-09-20 部分交付）

- 分支 `codex/pc-a-handover-phase-supervision-20260920`；base `9eaaa56d54bfd8968b3daf9956fc60cbe79c18b4`（PR32）；最终源码 `5188e65986eab9f6345ec03231968858296bd8aa`。已fetch共享集成19ddf268；不自动合并。
- 自行补取4交接片段，6有效视频290帧、760作者行；两视频和一时间表全零显式排除。阶段为运动阈值proxy，不能当独立接触真值；时钟误差/视觉人物绑定仍未知。
- 发现作者像素烧录阶段答案，模型运行前建立六视频SHA allowlist和固定去底部裁剪；不读作者CSV。四段64模型帧产生58区域手候选、911几何量、40未校准角色备选；记忆/动作0。64保存输入与独立裁剪采样逐字节相同。
- 两独立组件审核发现跨文件配对/CSV缺口后修复，最终66回归与mypy349文件通过，两位各22组件及真实评价重跑通过；不是B或最终整体P5验收。
- [完整证据及缺口](../reviews/pc_a/handover_phase_2026-09-20/REPORT.md)，[B固定源码复核](../reviews/pc_a/handover_phase_2026-09-20/COMMANDS.md)。B未复核，完整五任务未完成；A继续负责独立事件监督、角色/误差生产、P5及反证执行。

# 2026-09-20 监督对齐和位姿真值核验（A，部分推进）

最终源码3534e9796bb2aae99b594a330671a1328ddf5ccf；分支codex/pc-a-supervision-alignment-20260920，叠加PR31。
新增固定清单核验工具并实际发现024的7行非刚体姿态；保持对齐未决、不用作者序列标签生成答案。
独立审核发现跨帧梯度泄漏后修复；33工程回归及两位独立真实重跑通过。
A继续持有合法监督/语义生产责任；[报告与剩余缺口](../reviews/pc_a/supervision_alignment_2026-09-20/REPORT.md)，[B复核入口](../reviews/pc_a/supervision_alignment_2026-09-20/COMMANDS.md)。B未复核、完整自然闭环未成立。

# 2026-09-20 人物区域手部推理与监督核查（A，部分推进）

最终源码 `e0e572baf602c0e75bf834fd8e9f2aabe62da90b`，分支 `codex/pc-a-hand-roi-supervision-20260920` 接续PR30。
新增同源模型人物ROI手部推理；两份独立组件审核发现恢复来源漏洞后修复。
取得作者分割但时间/身份映射未确认，不用作运行答案或准确率真值。
A继续负责监督对齐与合法语义生产，B按[复核入口](../reviews/pc_a/hand_roi_2026-09-20/COMMANDS.md)独立复现；未记录B通过。
[真实结果、工程测试与未完成范围](../reviews/pc_a/hand_roi_2026-09-20/REPORT.md)。

# 2026-09-20 公开多人数据与同生产者媒体关联（A，部分推进）

固定源码 `b391400d7272510067cd5b1173843077cb92091c`，分支 `codex/pc-a-public-interaction-20260920` 接续PR29。A自行取得两段CORE4D原视频554帧和隔离监督，现有Unity相机通道实际运行成功。修复迟到帧配对/归档时钟，同生产者72采样帧产出11手候选/110几何量；144回归与两轮独立组件复验通过，完整自然语义、P5、反证动作和科学收益仍未签收。A继续负责实现，B按[复核入口](../reviews/pc_a/public_interaction_2026-09-20/COMMANDS.md)独立复跑，未记录B通过。[证据及完整边界](../reviews/pc_a/public_interaction_2026-09-20/REPORT.md)。

# 2026-09-20 自然事件与手部生产（A，部分推进）

冻结代码 `288b429a7d1e1d7f22f282ded333eedcf41957bc`；分支 `codex/pc-a-natural-event-loop-20260920` 叠加PR28。官方补360帧，累计540帧来源/监督核查；360帧实际产生463手部候选，同连续入口保留。没有自然语义转移、记忆或物理动作。独立组件审核发现恢复缺陷后修复，154回归通过；六真实帧重建恢复一致。仍缺独立多人/接触/纠正事件、完整角色/位姿概率生产、P5工厂及干预反馈。A继续持有实现职责，B负责[固定源码复核](../reviews/pc_a/natural_event_loop_2026-09-20/B_HANDOFF.md)，未记录B通过；完整五任务未签收。[结果和边界](../reviews/pc_a/natural_event_loop_2026-09-20/REPORT.md)。

# 2026-09-16 自然诊断与受控机制（A，部分推进）

冻结源码`47e307d97100c7fc1f04cb64fd1a05e926355c7e`。555漏检分解为422应用分数、125原生分数、8原生尺寸/NMS/top-k；校准事件澄清并纠正G15/G18/G19域声明，旧失败保留。自然表面几何仍不能合法消费为语义更新；受控registered P5已修迟到反证对降级活跃观测不可达的缺口，恢复重建不复活。B所有权、完整C/框架、真实连续验收和最终两轮独立审核条件保持。[本轮逐项结果](../reviews/pc_a/semantic_diagnostics_2026-09-16/REPORT.md)。

# 2026-09-15 真实自然输入（A，部分推进）

`codex/pc-a-real-semantic-input-20260915`，实际源码 `521d4f17c8538116b30a7c3c3c6c5e5a8f894141`，接续PR25。已取得180对真实RGB-D及作者标签，同源码新前端定位165/720个操作目标—帧；定位校准Brier变差，未标通过，主干／提议网络未训练。115工程回归通过；真实GroundedTransition／语义记忆更新／动作仍0。下一步是可靠语义生产、测量历史与核心消费；完整框架、B所有权、最终两轮整体审核条件保持。[本批结果与未完成矩阵](../reviews/pc_a/real_semantic_input_2026-09-15/REPORT.md)。

# 2026-09-15 连续能力接续（A，部分实现）

冻结源码`26808e61f8291ec1704a3638ada23d154751e730`，分支`codex/pc-a-continuous-capability-20260915`。共用提议解码／采样与默认后验采集调用已接，254相邻工程案例通过；真实自然语义、完整训练／支持生产及合格runtime factory仍缺，未启动真实后验策略运行或最终两轮整体审核。B所有权不变。[逐项结果与缺口](../reviews/pc_a/continuous_capability_2026-09-15/REPORT.md)。

# 2026-09-15 语义生产与后验行动（A，阶段交付）

`codex/pc-a-semantic-production-20260915`共同审核源码`0e3848f48f75cfed3d685e7b9a3e16856c277b98`。新增位姿实测拟合／条件统计接口、完整提议可微损失、联合后验相机选择与恢复；239回归及两轮独立复验通过。本批仍缺真实自然语义生产者、完整训练器与默认策略、真实语义反馈及正式比较；完整任务未完成，B比较／跨机验收所有权不变。[本批证据与未完成矩阵](../reviews/pc_a/semantic_production_2026-09-15/REPORT.md)。

# 2026-09-14 统一连续状态与恢复（A，部分工程交付）

[草稿PR23](https://github.com/goneveitvet240-svg/cpswm/pull/23)已推送。共同审核源码 `e2730d594b6f2608413317426c4348f823cfb182`，分支 `codex/pc-a-unified-continuation-20260914`。唯一核心/感知关联/账本/命令历史可持久化恢复；注册 P5-first 已有工程接入，真实 Unity 相机新观测可回到同一历史。两轮独立整体审视并修复四项 P2，两者共同SHA复验通过。完整真实人物语义闭环仍未建立；当前固定扫描与合成撤销不能合并成验收正例。[本批完整矩阵](../reviews/pc_a/unified_continuation_2026-09-14/REPORT.md)。B 仍负责独立跨机复现及比较，未修改其专属实现。

# 2026-09-14 人物交互接续（A，局部交付）

`codex/pc-a-person-evidence-20260914` 共同被审源码 `6f142dbf732009a82e08cd882b62f55708dfdd6d`；50帧公开真实人物交互RGB已接入，几何实例关联与角色候选/校准入口已实现，75项回归和两轮局部复验通过。尚无独立真实校准、可靠角色或真实记忆行动闭环；完整任务保持未完成，B跨机验收仍待执行。详见[完整已实现/缺口矩阵](../reviews/pc_a/person_evidence_2026-09-14/REPORT.md)。

# 2026-09-14 自然外观视觉（A）

用户已选择自然外观模型。新分支 `codex/pc-a-natural-vision-20260914`，最终源码 `6bb72386d588c82f0e264afa1dadd51306c1cada`，已连接真实检测与连续原始入口。两轮独立局部复验和68项相邻回归通过。新512采集只有1盆栽候选，无人物交互证据；完整语义行动闭环仍缺。详见[报告](../reviews/pc_a/natural_vision_2026-09-14/REPORT.md)，不把此前视觉条件待选状态沿用为阻塞。共享集成未合并；B比较与跨机验收边界不变。

# 2026-09-13 后续：连续修订与动作连接（A）

`codex/pc-a-continuous-loop-20260913` 的固定源码为 `be6e06348106c5a46ad766c136824c5eab70192a`，叠加 PR16 并接收独立审核的 B 三文件修复。新增连续诊断桥，两轮独立局部审核已在同一源码复验；真实原始输入到语义、默认完整 P5、原生动作仍未接齐。完整缺失矩阵和测试见 [本批报告](../reviews/pc_a/continuous_loop_2026-09-13/REPORT.md)。本候选不覆盖共享集成 PR18 的新导航；远端集成当前为 19ddf26830348a2f0b33f0af54d6ba702c5cfb1c。A 继续实现，B 保持比较及跨机验收边界；未声明科学收益或统一验收。

# 2026-09-13 后续：C 位姿＋本地开发（A）

用户已选C位置＋朝向和本地小预算开发，旧“这两项待批准”状态失效。A新任务分支codex/pc-a-pose-local-dev-20260913基于候选e6bdd018；当前代码188f9fc9aa17bf38f973ee00f04e0b2f148f4ca3。A拥有位姿模块、条件统计维数接入、专属测试及配置；B比较/独立复现所有权不变。871项基线、62项最终定向检查；第二轮独立116项通过，两轮局部审核完成。真实姿态感知、校准、监督、训练器与默认闭环仍缺，完整范围不缩减，训练未开始。详见STATUS_A及pose_local_dev_2026-09-13报告。

# 2026-09-13 候选整合更新（A）

当前共享集成分支未变。任务分支 `codex/pc-a-unified-runtime-20260913` 的最新实现 `06366579a1a72a46b465194b6e1bc2b6c27a3e87`；详细证据见 STATUS_A 及 docs/reviews/pc_a/unified_runtime_2026-09-13/REPORT.md。此表更新工作分工，不宣布项目完成。

| 任务 | 负责人 | 当前准确状态 / 下一依赖 |
|---|---|---|
| A1 统一源码与真实入口 | A | B五边界/W1/W2已接入独立候选；原始RGB-D入口和启动修复已实现；完整默认联合闭环仍缺 |
| A2 执行身份与编排 | A | 01d44d5上85项W1原生检查通过；没有执行完整统一编排器签收 |
| B2 当前比较输入与正路径 | B | 新包1920步已生成未独立重算；旧CORRECT probe 被CCRR拒绝而旧断言失败，需按当前合同补合法正例；不由A私改B专属模块 |
| A3 本批两轮独立审核 | A组织独立审核者 | 第一轮身份覆盖P2已修，第二轮Git对象替换P1已修并在0636657独立复验；仅本批入口/工具范围 |
| G2/G3/G4与默认闭环 | A实现，B复核 | 真实人物和语义输入、连续历史的原生监督、全轴模型、实际测量与全后验行动反馈未完成；用户待决项见执行方案 |
| B3 最终源码复核 | B | 待复核候选确切SHA；本机代理独立审核不能替代Windows/跨机验收 |

以下保留初始任务板作为所有权与历史边界依据，旧状态不覆盖上表。

# 双机任务板

2026-09-12 初始化；由电脑 A 维护汇总。完整方向结构一/二/三的文件均保留；当前双机活动优先延续结构二已有修复与审核，不代表缩小项目范围。优先级是工作安排，不改变已冻结科研路线和科学门。

| 顺序 / 任务 | 负责人 | 代码/文档所有权 | 交付与验收条件 | 初始状态 |
|---|---|---|---|---|
| A0 交接及现有窗口收口 | A | 快照登记、任务板、集成分支 | 冻结 W1/W2/W3 实际文件，保存未提交修复；避免现有窗口和新任务重复工作 | 本次建立，见 SNAPSHOTS.json |
| A1 主干与七算子工程修复 | A | src/cpswm/system 核心、相关原有生产测试；沿用窗口三 | 先保全/复核最新 R6 修复，再补尚未完成的真实后验投影绑定、默认联合粒子生产/消费、唯一账本和纠正/延期/晋升/取消/恢复；按既有合同实现，涉及新科学决策先列选项交用户 | R6 为修复方报告，待 B 独立复核；完整主干未验收 |
| A2 统一验收编排 | A | tools/structure_two_unified_acceptance.py、pytest runtime、编排集成测试；沿用窗口一 | 接收当前窗口一修复，核验比较包生成→绑定→消费顺序，测试产物进入 run 区，实际 Python/模块来源绑定；真实集成后才运行统一入口 | 最新未提交修复待复核，不重复假定 R5 缺陷仍在 |
| B0 环境与来源自检 | B | Windows/WSL 复现记录、STATUS_B.md | 新克隆、匹配 SHA、重建环境；验证实际解释器和导入路径；记录依赖差异 | 待用户在 B 启动 |
| B1 最新 W3 R6、W1 独立复核 | B | 新独立 tests/dual_pc_review/、docs/reviews/pc_b/；不改 A 生产文件 | 按快照完整 SHA 重跑 R5 独立反例与最新修复回归，含合法正例、伪造来源/地点、数值质量、拒绝无副作用、实际进程绑定与生产者—消费者；报告每个缺陷是否关闭，覆盖不足明确标注 | B 的第一项科研工程任务 |
| B2 比较/公平性与重算 | B | structure_two_comparison_audit.py 及对应 apps、专属比较测试/报告；沿用窗口二 | A 提供统一 SHA 后更新旧“预期缺陷存在”断言，生成全新比较包，独立核查来源、共同支持/先验/预算、三臂长期账本及实际行动；未经确认不改已冻结指标和阈值 | 先复现既有诊断；统一重算等待 A 集成 |
| A3/B3 交叉审核与统一验收 | A 集成，B 复核 | 集成副本与绑定其 SHA 的证据 | A 审核 B 比较改动；B 审核 A 修复；每次集成重绑定源码与证据，分窗口记录工程/科学状态，完整矩阵未齐不整体签收 | 等前置任务 |

## 已知事实与时间边界

- 主工作树起点 `09eb4d4`；W1 分支起点 `f5089d9` 加本次实际未提交修复；W2 当前已提交 HEAD `a5f3dec`；W3 `281e888` 加 R4/R5/R6 实际未提交修复。精确冻结版本以 SNAPSHOTS.json 为准。
- 2026-09-12 第五轮独立报告提出 W1 两项编排/解释器问题、W3 三类准备粒子问题；窗口二按局部开发诊断接受，统一科学门未通过。
- 此后 W1 已有新的在做修复，W3 已有 R6 修复报告。第五轮报告只能说明它审核过的旧快照；不能据此否定或认可更晚修复。B 必须复核新快照。
- R6 报告明确：投影消费尚未原生绑定而被拒绝；默认主干自动生成完整联合粒子、动作/长期账本闭环等缺口仍需单独推进。禁止把局部安全拒绝解释成能力最终完成。
- 映射权限、支持集、先验、资源预算如涉及尚未决定的科研设定，由用户选择；不得为过门而调整协议、阈值或缩小方向。

## 冲突避免

A 不直接改 B 专属比较模块，B 不直接改 A 主干或编排器。遇到跨边界缺陷：提交复现脚本/报告，更新本人 STATUS 并明确交给对方；必要跨文件修复先在 GitHub 状态中确认一次唯一负责人。普通同步不强行 cherry-pick 全窗口全部历史。只有审过的确切变更进入集成分支。
