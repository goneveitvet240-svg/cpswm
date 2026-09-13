# 自然外观预训练视觉接入：实施与验证

用户于 2026-09-14 明确选择自然外观预训练模型；C 位置＋朝向与本地小预算继续有效，不再列作待决定。完整隐藏事件、多人物、开放世界、H/R/I/C/Z/r/V、三个 RB blocks、七算子及 P5_FIRST 范围不变。

## 源码与实现范围

- 独立分支 `codex/pc-a-natural-vision-20260914`，base `0cb04a3a63b19786649a7b2091a14e67ec1c637d`（PR20）。开工及再次核对 GitHub 集成 `19ddf26830348a2f0b33f0af54d6ba702c5cfb1c`，本任务未合并共享集成分支。
- 初版源码 `9d50afb79fdba2e854edddb2f5ec1179e071604c`；修复及连续入口连接候选 `a3d1ea6de4db1d1bf9038482abbbefbdf707880c`。
- `NaturalAppearanceDetector`：本地 CPU、已锁定 torch 2.13.0 / torchvision 0.28.0，实际执行 SSDLite320 MobileNetV3 COCO_V1。该轻量检测器是可替换开发后端，不是重新选择正式结构二架构。
- 官方权重 [PyTorch 下载地址](https://download.pytorch.org/models/ssdlite320_mobilenet_v3_large_coco-a79551df.pth)，SHA-256 `a79551df90c79834bcd3bb3845ef9d966b5449a3a9b2833ae8404778ca5d65d2`；先校验完整字节，再从同一 BytesIO 通过 weights_only=True 严格加载。禁止隐式下载随机替代权重；eval/inference_mode，梯度关闭。
- 输入来自 M05 RawModalityObservation。验证 RGB 字节/hash、NPY 精确大小/有界 HWC uint8、来源、作用域和 UTC 可见时间；图像是模型唯一内容输入，仿真对象真值/角色信息不传给模型。
- 输出为逐帧候选：边框、类别、未校准分数、输入/回执/权重依赖。候选 ID 不是跨帧实例 ID，person 类别不是人物身份。姿态未估计；空检测不构成负观测。
- `NaturalVisionEvidenceProducer` 已接到既有 ContinuousEvidenceInput：保留原子视觉候选历史、检查前缀不可删改、去重避免重复推断。无校准实例/角色/位姿映射时明确返回 None，因此持续入口停留在 INSUFFICIENT_SEMANTIC_EVIDENCE，不能写长期记忆。
- CLI 实际经过该连续入口，并验证核心快照和 trace 不变。初始化用的 unresolved object/location/owner 仅为不参与推断的记账值，不是感知识别结果。

## 实际输入结果

1. 既有真实仿真归档：144 文件固定 hash、36 RGB + 36 depth；原图 96×96。在初版实际模型推断中，开发过滤设置 0.5 下 0 候选。另做 minimum_score=0 的低分诊断只用于观察模型输出，未替换 0.5 设置、未把低分候选升级为人物证据，也不是准确率评估。
2. 新启动已有 Unity 运行时，在同一个已选 ProcTHOR 训练房屋，用 512×512 固定四个相机方向采集。执行 Pass 一次、RotateRight 三次；不是 CPSWM 策略选择、拿放交互或真人角色场景。采集端保留源脚本、SDK、二进制和房屋 hash，以及每次调用回执；未因新采集而声明完整 D1 或多人物能力。
3. 新四帧共 8 RGB/depth 原始观测，经既有原始适配器入站；像素检测候选为 **potted plant 1 个**，无可靠人物或交互证据。人工查看图像可见盆栽、冰箱、台面和若干物体，但该查看不转写模型输出或身份真值。
4. 在 a3d1ea6 固定源码通过连续入口重跑：4 RGB、8 raw、1 盆栽候选，semantic_transitions=0、physical_actions=0、core_unchanged_verified=true，外部源码检查器 source_unchanged=true。这里 physical_actions=0 指方法动作；上述 4 次相机采集调用单独记录。CLI 自身是归档推断，所以 new_simulator_run=false；新 Unity 采集证据在单独 capture512 包，不能把两者混淆。

模型说明：[官方 Torchvision 文档](https://docs.pytorch.org/vision/stable/models/generated/torchvision.models.detection.ssdlite320_mobilenet_v3_large.html)。采用冻结安装版本的实际实现；score≥0.5 仅为可复现的开发输出过滤，并未独立校准。官方模型会执行 NMS/top-k，输出也不是完整后验假设集合。仅检测 COCO 类别，不能宣称开放词表识别或完整开放世界能力。

## 第一轮审核和修复

独立审核者实际加载官方权重（不是 mock），发现两个 P2：从其他 Git 工作目录启动会错误记录无关仓库 SHA/clean 状态；重复 capture_ref 字典项被静默覆盖，使来源回执歧义未拒绝。

a3d1ea6 修复：Git 明确绑定脚本仓库并禁 replace refs；重复 capture_ref 和 observation identity 拒绝；验证后保留的像素/信封字节直接供推断，避免重新开文件的 TOCTOU。CLI 比较自身及检测模块前后字节 hash、HEAD，明确这不是全运行时 code-object attestation。跨进程/缓存/整个依赖链的 W1 验收保持独立范围。

## 已运行检查

- 初始测试 4 fail / 15 pass 来自测试试图赋值冻结的 PayloadRef；改为 model_copy 构造完整输入，保留失败记录，未修改生产拒绝条件。
- 19 个初始边界检查通过；加入连续入口/前缀测试后，新测试＋原连续模块共 43 项通过。Ruff、mypy 新生产模块通过。
- 旧 9d50afb 同一固定源码 41 项检查 source_unchanged=true；不以此代替新增 producer 之后的回归。
- 最终两轮独立复验与新相邻检查将在对应报告和证据中记录；只认可本批实际覆盖，不签完整真实闭环。

## 剩余能力（不是待重复批准）

当前可验证的是自然像素推断已进入连续输入路径，并受到语义能力门约束。尚缺自然外观人物交互输入、稳定实例关联、姿态/坐标估计、独立校准与机会模型、角色时序证据到原生提议监督、完整默认 P5/神经提议和原生拿放执行器。当前画面无人，不能靠降低检测分数或读取仿真内部人物标签填补。

因此本批仍不能产生用户要求的真实多解释→行动→迟到反证→撤销错误记忆→改变下一行动的完整正例。已有合成语义正例与本批真实视觉结果继续分开；最终整体固定源码验收未成立。未启动模型训练，未使用付费算力。

## 最终固定源码结论

最终被审源码 **6bb72386d588c82f0e264afa1dadd51306c1cada**。第二轮发现配对 JSON/NPY 的 capture_ref 可矛盾而仍被接受，已补齐推断前配对引用/未知引用/孤立载荷/可选 observation_id 校验。第一轮在最终源码三组复验通过；第二轮五类来源链拒绝加一个合法真实推断场景均符合预期，六项前缀原子性/失败恢复/别名探针通过。两位审核者均执行了官方预训练模型；完整原始失败、脚本和最终报告分别保留。

该源码新视觉/连续入口/原始RGB-D及CLI相邻矩阵 **68 passed, 18.02秒**，源码检查器 source_unchanged=true；最终新512输入与旧96归档分别重跑通过，候选仍为1盆栽与0，语义转移和方法物理动作均0，核心不变。运行时 git_dirty=true 来自本报告等文档尚未提交；src/tests/tools/configs等源码hash在检查期间保持不变。后续交付提交只含文档证据，不重写被审生产源码。

## 证据与复现

`evidence/capture512_input.tar.gz` 含新方法输入、实际原始RGB-D及采集回执，排除 evaluator-only 真值。`convert-natural-vision-capture.py.gz` 保留转换脚本。解包后，使用最终源码的 `tools/run_natural_vision_archive.py --archive <method_input> --manifest-sha256 fe0ee798541f2978c508b96b57cfb545eab8e223ccb56adf8146df57dcb45c86 --weights <已核查官方权重> --output <新目录>` 重跑。原权重和SDK不重复放进Git；锁文件及官方hash可用于重建。旧96归档仍依赖PR15既有归档，不计入本新采集包。

各检查的 started/result JSON无损gzip压缩，保留完整命令和源清单；审核脚本gzip避免格式化钩子改写。复现时需替换记录中的本机绝对路径。MANIFEST.json校验 evidence 文件字节；哈希自洽不等于独立采集真实性托管。新模型依赖 installation 使用 `uv sync --frozen --extra dev --extra perception`，未修改锁文件。
