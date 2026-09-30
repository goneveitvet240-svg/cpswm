# 下一轮最小 API 设计：拥有者同帧亲和度支持

状态：只读设计，尚未实施或接线。依据 PR76 `ffcaa7b292c73201d799f6631688387409c21cb7` 的现有 owner、NativeVisualSource、ProposalPixelObservation、持久化与重放接口。当前第一轮已完成既定 R1/R2 并启动 run/fresh verify；其真实结果仍待独立核验，本文件不替代该核验。

本文件保留为可复用支持接口备选，不是下一轮唯一主项。当前 `OpenWorldJointFixture` 仍生成目标 density，proposal q 的改变会由 integration correction 抵消，因而只接描述摘要可以证明网络输入与 q 改变，不能证明精确后验改变。主任务正在另行设计软加权公开表面读出、uniform 对照、pivot/AABB 双参照训练残差和显式关联 fixture 下的预测观测密度消费者；本文件不把该方向称为已经实施，也不替其选择正式身份或位置定义。

固定原 PR76 combined 模型作为下一轮显式依赖，不根据已曝光开发验证集在 RGB/geometry/combined 间选型。建议直接使用原 `experiment/model.json`，外部内容 pin 为 `492ae03792fef90f6a1428b80a68da27818df1e595b42f2290ac874079458d22`，文件 pin 为 `2d14462d0245af91218ccc8af40dc73d7a2c93d276e4edbb4bedd88ad476024c`；由调用方配置原件和 pin，不从支持记录自认信任。训练路径、标签、house/split、SDK masks/目录均不进入新运行时依赖。

## 1. 具体能力与范围

从一次拥有者已接收的 RGB-D/相机自位姿和**单一实际 VisualFrame**，按固定 8×8 半开框内像素中心网格产生全部无序不同像素对，完整推理未校准分数。完整支持留在同一 owner 历史；proposal 网络仅消费预先固定的每候选描述统计。

这是“原 combined 特征映射在单前端拥有者候选上的接线”，不是原离线双前端并集协议的等价重放。保留当前 decoder，不额外运行第二个检测器，也不重写其 model_id、候选或类别。类别只属于原有 VisualFrame；亲和度特征仍仅取既定 8 列公开数值。

不创建世界实例 ID、前景二值图、聚类、阈值或接受判定，不填对象中心/朝向，不生成观测似然，不直接修改 memory/ledger/particle statistics。现有 `pixel_causal_readouts/pixel_hypothesis_bindings` 不因亲和度变化而合并或改名；它们原有的局部 perceptual-track 假设也不能升级为真实身份。

## 2. 建议模块与函数

新增 `cpswm/perception_mapping/instance_affinity_support.py`，只依赖公开 RGB-D 解码、VisualFrame、已冻结的 affinity 数值函数和通用内容摘要。禁止导入 tools 的私有 label helper。

```python
@dataclass(frozen=True)
class AffinityResourceLimits:
    max_candidates_per_frame: int
    max_pair_occurrences_per_frame: int
    max_unique_pairs_per_frame: int
    max_frame_support_bytes: int
    max_history_support_bytes: int

class FixedAffinityDependency:
    # 无训练方法、无可变 RNG；已验证 model 的脱离副本由实例持有。
    def __init__(self, model_path: Path, *, content_pin: str,
                 file_pin: str, limits: AffinityResourceLimits): ...
    @property
    def binding_sha256(self) -> str: ...
    def measure(self, observations: tuple[RawModalityObservation, ...],
                visual: VisualFrame, *, cutoff: datetime) -> FrameAffinitySupport: ...

def validate_affinity_support(value: FrameAffinitySupport) -> None: ...
def summarize_affinity(value: FrameAffinitySupport) -> FrameAffinitySummary: ...
def validate_affinity_visual(value: FrameAffinitySupport,
                             visual: VisualFrame, geometry: RGBDSurfaceSupport) -> None: ...
```

`measure` 首先重用 `decode_rgb/decode_unity_rgbd` 与 `_frame_support/surface_support` 的公开绑定规则；只接受同 receipt 的三路实际字节，核 scope、action、observation IDs、capture/arrival/cutoff、宽高、相机与候选。再调用固定 `grid_pixels/pixel_pairs/pair_features` 和原模型预测。不能接受外部已算好的 features/pairs/scores 来替代 raw 重算。

这里 `binding_sha256` 必须同时覆盖模型内容/文件 pin、8 列定义、网格与去重协议、摘要 schema、资源配置、实现源码及加载函数身份；不能只校验调用方字符串。`measure` 前后核绑定一致。既有 `checkpoint_artifacts.py` 专用于 manifest.json+weights.pt，不可假装它已能注册该 JSON 模型；此依赖使用自己的显式 JSON 加载/校验即可，不把路径放进证据。

## 3. 完整支持字段

建议 frozen dataclass，元组元素使用严格原生 int/bool/float/None；避免 dataclass 默认相等运算遇到 ndarray 后产生歧义。若为存储效率改为紧凑数组字节，应另定义 dtype/shape/endianness 和唯一编码，不能同时保留两套可分歧事实。

`FrameAffinitySupport`：

- `schema="owned-single-frame-pair-affinity@1"`、`status="UNCALIBRATED_SAME_FRAME_PAIR_SUPPORT"`。
- `action_id`、`observation_ids`（RGB/depth/pose 三个）、`scope`、`capture_time`、`arrival_time`、`inference_cutoff`、`width/height`。
- `payload_sha256` 三路、`capture_receipt_sha256`、`visual_frame_sha256`、`camera_sha256`、`dependency_sha256`、`model_content_sha256`、`feature_spec_sha256`、`grid_spec_sha256`。这些只作 provenance，不作网络特征。
- `pairs: tuple[tuple[int,int,int,int], ...]`，端点按 `(u,v)` 字典序规范化，行唯一且排序。
- `valid: tuple[bool, ...]`、`scores: tuple[float|None, ...]`，与 pairs 一一对应；有效行分数有限且在 `[0,1]`，无效行必须 None，不能将未评分填为 0。
- `candidate_sources: tuple[CandidateAffinitySource, ...]`，保留 VisualFrame 中所有候选和原顺序。每行含候选 ID、box、`grid_pixels`、`pair_indices`；候选 ID 只是同帧引用。
- `feature_array_sha256` 绑定重算的完整 N×8 数组；完整特征不必重复持久化，raw 已归 owner 所有，恢复时重新计算并比摘要。
- 严格禁止额外的 authority 字段；明确 `identity_association=None`、`object_centre_m=None`、`orientation=None`、`likelihood_model=None`、`memory_write_authorized=False`、`full_mask_predicted=False`。

结构校验包含：字段/类型精确、未知字段拒绝；候选 ID 唯一并与 VisualFrame 一致；网格像素在原框半开中心规则内；各候选恰好覆盖本网格全部不同点组合；pair_indices 无重复且为全局表合法索引；全局 pairs 恰好是所有候选集合之并，既不能省略也不能添加无来源行；分数/有效性长度与范围；无效 depth 分数为 None。结构自洽不构成 raw 真实性证明，后者仍由拥有者 fresh 重算与外部模型 pin 建立。

## 4. 去重、空输入与资源规则

每框最多 64 个去重像素，最多 `64*63/2=2016` 对。先在每框内枚举，再对**同一 action/同一无序像素对**跨框去重；绝不把所有框网格拼起来再生成全局组合，那会错误产生跨框新增对并变成候选数平方增长。同一个全局 pair 可以出现在多个候选的来源索引中。不能跨 action、相机或帧去重，也不由重复 RGB 判断独立性或身份。

候选统计只对自身 pair_indices 中每行计算一次。帧级统计用全局唯一 pairs，不能将多个重叠框当成独立重复证据。记录 `source_pair_occurrences`、`unique_pair_count`、`repeated_pair_occurrences` 区别两类分母。

- 无候选：保留正常空支持，候选列表、pairs/valid/scores 均空；不推出目标不存在。
- 有候选但合法中心不足 2 个：候选保留，pair_count=0。
- pair_count>0 但 valid_count=0：完整 pairs 保留，scores 全 None。
- 两种无可用分数情况的 mean/variance/min/max 全 None，不能填 0；pair/valid/invalid count 仍准确区分。
- 不接私有 eligible/VOID 标签。离线曾被标 VOID 的公开对，在运行时只要 depth 有效就仍评分。

资源配置属于部署约束，必须在新 profile 构造时显式给出并绑定，不能观察开发验证标签后调整。按 C×2016 先检查 pair-occurrence 上界，再建并集并检查 unique 上界；推理前检查候选/数组上界，形成支持后检查 canonical 字节长度，登记历史前检查累计字节与 StateCodec 限制。单框复杂度 O(N²)，N≤64；完整 frame 的未去重上界是 C×2016，而非 O((64C)²)。

任一上界超出时抛明确资源错误，不截断历史、不丢候选、不下采样对、不返回前半批支持。已经接收的真实 raw/action receipt 仍归 owner 保存；affinity/后验发布事务回滚，不冒称视觉采集失败或重新执行动作。网络端继续采用实际 `leaves(export_context(...))` 的已有 max_nodes 检查；摘要有界仅意味着每候选固定大小，不能保证任意候选数和任意长历史永不超限。

## 5. 网络白名单摘要及其实际局限

`CandidateAffinitySummary` 字段固定为：候选同帧引用、`pair_count`、`valid_pair_count`、`invalid_pair_count`、`score_mean`、`score_variance`（总体方差，分母 valid_count）、`score_min`、`score_max`。可保留 `grid_pixel_count` 以区分极小框。`FrameAffinitySummary` 保存 schema、unique/valid/source-occurrence counts 与全部候选摘要。

统计只用有效分数。均值用固定顺序 `fsum(scores)/n`，方差用 `fsum((p-mean)**2)/n`；n=1 时方差严格 0，n=0 时四个统计值都为 None。摘要在读取/恢复时必须从 full support 重算，不能被调用方作为第二份可编辑证据接受。

`ProposalPixelObservation.model_input` 最小变化是给既有候选项附加 `uncalibrated_pair_summary`，使用上述数值白名单；同帧 candidate ID 已在原候选中，无须再次编码随机身份。帧级只加有版本的状态和唯一分母。不把模型/资产/scene/输入摘要、路径、split、house、监督标签、authority token 或全量 pairs 送给网络。

这份摘要对当前 typed JSON 网络**可被真实编码并影响 proposal q**：网络已经编码全部数值叶，不需要新架构才能读取这些字段。但能读取不等于已学会有效使用。旧 proposal checkpoint 没有针对这些新摘要获得自然语义联合监督，因此本轮最多证明实际输入路径与精确目标守恒；不能因随机或旧权重导致 q 变化就称方法收益。

摘要提供的是候选内亲和度分布的粗略线索，丢失“哪两个像素相连”。相同均值/方差/极值可能来自完全不同的空间分区；大同质区域会主导全部像素对，不能由均值高推出框内单实例或前景完整。最小替代不是放开阈值/聚类，而是另版本的、预先固定的**空间分组摘要**：例如按框内四象限对分组，10 个无序象限组合分别保留 count/valid/mean/variance。它能保留少量空间关系，仍不输出 mask/identity；会增加网络叶节点与表示假设，应另行审核，不在本轮同时引入或根据验证结果挑选。若当前目标只是可复算支持接线，先用全局每候选摘要即可，不为追求 q 变化偷偷增加表示。

## 6. Owner、默认兼容与恢复

建议 `ContinuousEvidenceInput.__init__/resume` 增加 keyword-only `affinity_dependency: FixedAffinityDependency | None = None`。启用时要求实际 RGB-D decoder 支持；不具备三路数据时明确拒绝，不能伪造空 affinity 表。未启用时不读模型、不生成支持、不输出摘要、不改变原 decoder 或目标密度。

调用链仍是 `reconstruct_visual_support` → `NativeVisualSource` → `NativeJointContext`。该 reconstruct 函数增可选依赖与 expected_binding；在已有 `_frame_support+surface_support` 成功后推理，不接外部 affinity 缓存。注册到 `workspace.visual_sources` 前绑定实际 owner authority；producer 只能获得脱离副本，不能注册新 source。`_verify_native_visual_sources` 对当前和历史代际按 source.cutoff 从原 raw+同 checkpoint 重推，既校完整表也校摘要。失败生产恢复原 source catalogue 和 producer 状态；动作读出前继续验证。

默认字节行为要分清两层：原始采集/VisualFrame/无 affinity 的网络输入可保持原字节；新源代码/部署绑定本来就必须变化，不能承诺旧 SQLite 在不迁移时跨版本直接恢复。不要随意给每个旧 dataclass/model_dump 都添加一个 None 字段，这会改变旧 hash 与训练输入。

优先方案：保留旧 `OwnedVisualFrame` 原字段；仅启用时使用 kw-only 的 frozen 扩展 `AffinityOwnedVisualFrame(OwnedVisualFrame)`，新增完整支持。原 `NativeVisualSource` / `NativeJointContext` 不增默认空字段；新数据已包含在同一 support 中。proposal 侧可用独立 `ProposalAffinityPixelObservation` 扩展型保存小摘要和绑定证明，旧型继续不带新字段；`VisibleRecords.pixel_observations` 与 prefix 解析显式支持两种类型，并按有无新增受控字段派发。必须测试 Pydantic 嵌套 union 的 dump→validate 不会把扩展型降成旧型而静默丢字段。若这一兼容方案增加过多复杂度，可改用显式 v2 contract，但应承认输入/摘要变化，不能用全局 `exclude_none` 改掉其他旧语义字段。

运行时依赖句柄不进 StateCodec；仅启用时保存其 binding/profile/外部 pin，`_persist` 排除句柄，`resume` 要调用方显式重供同模型并立即校验。实例应冻结模型脱离副本并在每次使用检查参数/实现身份。无配置或换模型恢复必须失败；不能自动回退、从证据里的路径加载或刷新 pin。部署的 `ContinuousStateStore.dependency_identity` 也须包含该依赖，保持单一 owner。新类型由生产模块正常 import，不能只在测试导入后碰巧能恢复。

## 7. 下一轮验收的最小可执行范围

1. 合法 RGB-D/同一 VisualFrame → 全部 pairs+scores+摘要 → NativeVisualSource → 实际 proposal 输入；完整表不进网络叶。空候选、单点框、valid0 全保留。旧默认输入字节与正常行为对照不变。
2. 固定相同 proposal checkpoint/候选，只移除新的摘要做真实输入消融；证明摘要存在于实际编码，q 的变化如有只作接口现象；精确枚举 target posterior 与账本保持原有守恒。
3. 同帧跨框重叠/重复候选保留来源但只计算一次全局 pair；不同 action/相机不合并。造一个均值相同但空间关系不同的受控例子，明确摘要信息损失，不假装能恢复 mask。
4. 完整伪造 model pin、pair 集、valid、scores、摘要，并重算外层 context/q/receipt/hash，仍在 native stage 或动作读出前被 owner 原件重推拒绝；随后合法 source 仍可发布，账本/工作区/动作无污染。
5. 模型内存参数改写、文件替换、导入别名 monkeypatch、丢候选/加无来源 pair、仅改摘要、未来 cutoff、跨 owner 移植和 source catalogue 回填均拒绝。
6. SQLite fresh-process 恢复、语义修正后的完整代际 replay 和失败事务回滚；原始 action/delivery 不删除，相机不重发；旧 source.cutoff 不能偷看未来帧。任一资源上界溢出 fail closed，不留下部分注册。

这轮若完成，只能表述为“固定未校准亲和度的可重算公开支持进入同一视觉历史及有界 proposal 输入”。`JointFixture` 的 target density、语义事件、位姿/角色/事件测量和手工相机 outcome likelihood 仍是 fixture。自然联合后验、完整前景分割、稳定实例身份、观测似然校准与动作收益均留作未完成项目。
