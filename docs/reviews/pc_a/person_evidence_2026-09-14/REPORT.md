# 人物交互输入、实例关联与角色候选：局部交付，完整能力仍未建立

日期：2026-09-14。分支 `codex/pc-a-person-evidence-20260914`，base `7516193f4cdcf1686d8187d2b8ce0398ecc0cf96`；共同被审生产/测试源码 `6f142dbf732009a82e08cd882b62f55708dfdd6d`。共享集成经 fetch 核对为 `19ddf26830348a2f0b33f0af54d6ba702c5cfb1c`，本批未改共享分支或 B 专属文件。

## 实际实现与边界

| 用户缺口 | 本批实际实现及验证 | 尚未解决 |
|---|---|---|
| 人物交互输入 | 官方公开 HOH / CORE4D 实拍视频的已检查纯 RGB 面板，经精确裁剪、源视频摘要、NPY 字节、M05 envelope、ContinuousEvidenceInput 和官方检测器真实回放 | 原始完整数据及独立事件/人物标注尚未获得；演示视频不是正式评估集 |
| 稳定实例关联 | 因果同类 IoU 双向唯一匹配，连续帧保留轨迹 ID；竞争歧义保留替代匹配并分支，跨镜头/维数/模型/时间范围拒绝，间断不擅自恢复身份 | 只是几何基线；未实现外观嵌入重识别、遮挡后重连、世界实体绑定；没有独立 ID 真值，不能给出 IDF1/HOTA 或宣称身份正确 |
| 校准 | 带模型/输入/标注来源的单调 Platt 拟合；分视频且分输入 hash 的留出检查，Brier/NLL；独立标注文件按候选 ID 严格 join，未标注不作为负例 | 未获得独立真实标签，未运行真实拟合/留出评价；数学夹具不是经验校准。hash 不证明标注真实，校准工具不赋予记忆权限 |
| 角色证据 | 连续人物与物体轨迹提出有序角色解释，保留交接/共同操作歧义；身份断裂撤去该解释；缺物体时提出近看请求，有物体时提出观察手与物体请求 | 框重叠不证明接触、持有、释放或交接。真实视频未检出可靠交接物体，真实角色候选为 0；手部时序、角色似然和世界位姿生产者仍缺 |
| 长期记忆 | 实际调用连续入口并断言核心状态和执行轨迹未变化 | 未实现本批真实语义 promotion；没有真实迟到反证→长期错误记忆撤销→物理行动改变正例。观察请求只是诊断输出，未派发给机器人 |

完整 H/R/I/C/Z/r/V、三个 RB blocks、七算子、P5_FIRST、C 位姿和本地预算范围不变。本批不是缩小后的最终研究目标，也不把上述未完成项改成验收通过。

## 实际运行

共同固定源码、新空 pycache prefix、本地锁定环境 CPU；没有训练和付费计算。两次运行均 `git_dirty=false`、`continuous_input_invoked=true`、`core_unchanged_verified=true`。

| 输入 | RGB 帧 | 检测候选 | 连续几何关联 | 新轨迹 / 歧义分支 | 有序角色候选 | 记忆写入 / 执行动作 |
|---|---:|---|---:|---|---:|---|
| HOH 01，0–7s，5Hz，178×100 | 35 | person 57 | 51 | 2 / 4 | 0 | 0 / 0 |
| CORE4D，6–9s，5Hz，576×324 | 15 | person 33，chair 15 | 43 | 5 / 0 | 0 | 0 / 0 |

候选数不是不同人物数；连续关联数不是正确身份数。CORE4D 的 chair 是场景椅子，不是两人正操作的蓝色容器。没有将该类别误当交接对象。CORE4D 人物戴采集设备/动捕标记，未使用其身份或动捕通道，不能称无标记自然环境验证。

公开来源：
- [HOH 项目](https://tars-home.github.io/hohdataset/)；[01 原视频](https://tars-home.github.io/hohdataset/assets/01.mp4)，SHA256 `16eeac89f372c49e51a659659aafca39c7bdb3274bdc258ac6c8340406854c01`。RGB crop `(0,0,178,100)`；复合图其他深度/骨架视角不输入模型。完整数据下载需要作者提供密码，未绕过或擅自联系作者。
- [CORE4D 项目](https://core4d.github.io/)；[演示原视频](https://core4d.github.io/static/videos/all.mp4)，98,370,878 bytes，SHA256 `c4e7244683435b288649d3fce2a7bf622b16c8cd2d9128d435232dd1c5ddb2ae`。已检查 Fix View 2，RGB crop `(672,150,576,324)`；Mocap 面板及后续网格动画不输入模型。完整 HF 数据连接在本机限时尝试失败。

原视频没有可靠绝对曝光 UTC。M05 capture/arrival 明确是导入采集 UTC，receipt 单独保留媒体重采样网格时间，不能当原始相机曝光时间。CLI 检查 entry/detector/association 三个磁盘文件 hash 与 git SHA 前后不变；不宣称整个 Python 运行时已做 code-object attestation。

## 复现

使用本分支锁定 `dev`、`perception` 依赖和 `ffmpeg` / `ffprobe`；权重沿用 PR21 官方固定 SHA，不自动下载。以下命令中的输出路径应为空：

```sh
.venv/bin/python tools/run_person_interaction_video.py --video /private/tmp/cpswm-hoh-public/01.mp4 --sha256 16eeac89f372c49e51a659659aafca39c7bdb3274bdc258ac6c8340406854c01 --source-url https://tars-home.github.io/hohdataset/assets/01.mp4 --crop 0 0 178 100 --duration 7 --weights /private/tmp/cpswm-natural-vision-models/ssdlite320_mobilenet_v3_large_coco-a79551df.pth --output /private/tmp/person-replay-new
.venv/bin/python tools/calibrate_interaction_scores.py --help
.venv/bin/python -m pytest -q tests/test_interaction_evidence.py tests/test_interaction_calibration_cli.py tests/test_natural_vision.py tests/test_structure_two_continuous_input.py
```

最终定向及相邻回归 75 passed，0 failed / skipped / xfail，JUnit 原始结果随本报告附带。算法/拒绝/角色双向解释正例使用明确合成夹具，不升级真实数据收益。未重跑全仓所有测试；范围由新增与相邻路径限定。

## 后续实际阻塞

需要独立标注的原始多人持物/交接视频，并确保交接物体能被视觉模型可靠提取。已向用户询问是否有 HOH/CORE4D 原数据、标注或本地路径；没有把等待回复当作已有授权或已有数据。即使拿到数据，仍须实现手部接触/释放与遮挡关联、真实校准、世界实例/位姿及角色合同生产连接，再运行完整真实记忆/行动闭环和整体固定源码验收；不能把剩余缺口全部归因于数据访问。

## 两轮独立审核

两位独立审核者均复验共同源码 `6f142dbf732009a82e08cd882b62f55708dfdd6d`。第一轮发现并关闭 UTC/naive/DST 时间问题和 FFmpeg 奇数裁剪取整问题；第二轮独立发现时间、失效校准实例绕过和 CLI 源码绑定缺口，复验原五项及新增校准五项、角色一项共11项通过，并从其他工作目录运行真实奇数尺寸视频裁剪。详见 review1/REVIEW.md、review2/REVIEW.md；原始失败未删除。

这两轮是本机独立局部审核，不替代 B Windows 独立接收，不代表固定源码整体统一运行验收。报告和记录最后归档为文档提交，生产/测试文件与被审 SHA 无差异。

## 工件

final_hoh01.json.gz / final_core4d.json.gz 是完整逐帧原始输出（含检测框、轨迹、角色读出、输入receipt和源hash）；tests.xml 是最终75项回归结果。为避免重复分发数据集原视频，本批 Git 工件不含原视频/人物RGB载荷；载荷仍在本机 `/private/tmp/cpswm-person-final-hoh01` 和 `/private/tmp/cpswm-person-final-core4d`，通过上述官方来源与源hash可重建。metadata hash只证明字节一致，不是标注质量或完整运行时身份的证书。

原始审核脚本以 `.py.gz` 保留，解压后运行；避免提交 hook 改写证据。第一次归档提交被 lint hook 拒绝，已从审核者原件重新压缩保全；生产/测试源码未受影响。
