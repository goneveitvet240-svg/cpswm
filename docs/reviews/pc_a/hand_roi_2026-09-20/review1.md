# 第一轮独立组件审核：人物区域手部观测

审核源码：`2de22e8a60687944166913fc15d45d38d2beee46`。比较基线：`97d4d91`。2026-09-20，macOS，本任务独立审阅者。源码只读；未重复真实视频推理，也未运行 B 端复核。

结论：发现一个需要修复的 P2 来源校验问题。现有工程子集 74 项通过不能消除该反例；本版本暂不接受 ROI 来源恢复组件。

## P2：可将候选改挂至另一个合法区域并恢复成功

位置：`src/cpswm/perception_mapping/natural_hands.py:292`，`validate_hand_regions`。

生成端为每条候选计算 `uuid5(region.region_id, f"hand:{HAND_MODEL_SHA256}:{i}")`；恢复端却仅核查 `candidate.region_id` 是否属于合法区域集合。攻击者把 full-frame 候选的 `region_id` 改为同帧另一个真实 person ROI，保留原候选 ID 和关键点，`restore_state` 会接受并保留错误来源。现有 candidate 损坏测试仅使用全新 UUID，未覆盖已有合法区域之间换挂。`measure_hand_object_evidence` 共用该校验，不能检测此来源损坏。

独立探针命令如下，固定版本实际打印 `ACCEPTED swapped existing region: True`：

```sh
PYTHONPATH=tests .venv/bin/python - <<'PY'
from test_hand_person_regions import roi_components
from dataclasses import replace
from cpswm.perception_mapping.natural_vision import NaturalVisionEvidenceProducer
raw, detector, hands = roi_components()
p = NaturalVisionEvidenceProducer(detector, hands)
p.infer((raw,), cutoff=raw.envelope().arrival_time)
s = p.checkpoint_state()
h = s['hand_frames'][0]
assert len(h.regions_evaluated) > 1
wrong = replace(h.candidates[0], region_id=h.regions_evaluated[1].region_id)
s['hand_frames'] = (replace(h, candidates=(wrong,) + h.candidates[1:]),)
p.restore_state(s)
print('ACCEPTED swapped existing region:', p.hand_frames()[0].candidates[0] == wrong)
PY
```

建议恢复与直接测量入口验证区域内候选数量不超过 `model_binding[2]`，候选 ID 与生成端区域及顺序一致；补充已有合法区域之间换挂、数量溢出和未改变原状态的拒绝测试。该验证是结构完整性检查，不是对模型输出真实性的密码学证明。

## 已检查边界

- ROI 仅取同源视觉检测的人物框，15% 扩展、图像内裁剪；关键点通过裁剪原点及宽高映射回源图，独立合成正路径通过。
- 生成端绑定 raw 身份、payload、receipt、sensor、frame、scope、media timeline、时间以及尺寸；作者分割下载入口与运行时隔离。
- producer 恢复先深拷贝、校验全部依赖及重算交互，再统一赋值；现有损坏来源测试没有部分写入。
- 所有重叠区域候选仍是区域观测，不能当作互异物理手或人物所有权；没有发现本 diff 将 detector/handedness score 提升为角色概率。
- hand/object 输出仍明确限于像素几何；没有自然语义转移、可逆记忆和行动闭环完成证据。
- 分割下载清楚记录全档 LFS 未验、evaluator-only、未加载 pickle；本审查未重下档案，也未核验作者 mask 时间及类别映射。

## 实际执行

```sh
.venv/bin/pytest -q tests/test_hand_person_regions.py tests/test_natural_hands.py tests/test_hand_object_evidence.py tests/test_natural_vision.py tests/test_continuous_state_recovery.py
```

退出码 0，74 项通过，0 失败，0 跳过。另执行上述来源换挂探针，退出码 0，确认损坏状态被接受。子集结果不能与其他审查重复测试相加，不代表完整矩阵、自然能力提升、P5 完整闭环或科学收益；B 复核仍待完成。

## 修复版独立复验

复验固定源码：`6b8a9a0bcdee4a34091e130531a3c1c3a6223a0c`。检查了相对原审核版的生产补丁与新增三个反例，没有修改生产代码。

生成顺序、区域候选 ID 的 UUID5 推导及逐区域容量上限现在统一校验。重新执行原始合法区域换挂反例，`restore_state` 与直接 `validate_hand_regions` 均拒绝并报 `ROI candidate identity/order differs from region derivation`；确认拒绝后 producer checkpoint 完全未改变。合法完整恢复与原 checkpoint 相等。

同上五文件 pytest 子集重新执行：退出码 0，**77 项通过，0 失败，0 跳过**。新增三个测试分别覆盖合法区域换挂、5 个候选超过配置上限 4，以及区域候选顺序重排。另行运行原反例与直接入口探针，退出码 0。77 项是修复版本子集计数，不与之前的 74 项相加。

结论：原 P2 在此固定 SHA 下关闭；在已审源码及所列工程覆盖范围内，未发现剩余阻断项。此结论为 ROI 来源恢复组件审核，不能扩展为模型检测精度已提升、真实视频事件闭环、自然 P5 验收或 B 端独立复核。保留上方原版本发现供追溯。

### 最终交付源码绑定

最终源码 `e0e572baf602c0e75bf834fd8e9f2aabe62da90b` 相对已复验的 `6b8a9a0bcdee4a34091e130531a3c1c3a6223a0c`，独立 `git diff` 核对仅有一处变化：`expected_candidates = []` 增加局部类型注解为 `expected_candidates: list[tuple[UUID, UUID]] = []`。无运行逻辑变化，因此上述修复审核结论绑定至此最终 SHA。本次未重复运行测试；77 项测试实际执行仍绑定前一 SHA，不冒称最终 SHA 上重新执行。主任务提供的 mypy 结果也不计为本审阅者独立执行。
