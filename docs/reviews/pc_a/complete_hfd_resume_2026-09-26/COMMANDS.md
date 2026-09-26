# 复验与B交接

固定Python源码 `c10a311430ff68ecce4aea0eaa6b3039e2f88974`，base PR43 `f72413fdd55bb3324ca064c02ba1fd8507aba54b`。独立检出后按uv.lock重建Python3.13.5及dev/perception/hand-perception依赖，不复制macOS虚拟环境。后续文档提交不改变受测Python；原资源轮7c19637的完整视频结果绑定原版本，本轮不以HFD类型检查替代重跑神经视频。

```sh
uv sync --frozen --extra dev --extra perception --extra hand-perception
.venv/bin/python docs/reviews/pc_a/complete_hfd_resume_2026-09-26/run_frozen_intake.py --main <original-evidence-project> --output <new-output-directory>
```

Windows解释器入口改为`.venv/Scripts/python.exe`；驱动内部使用sys.executable。FIFO/Unix socket对抗夹具需要支持这些本地文件类型的环境（A为macOS）。本轮沙箱EPERM不是产品漏洞，也不是测试通过；B若原生Windows不能执行相应攻击，明确记未覆盖并在适用平台另做复验，不能静默跳过后宣称全通过。

main需具有以下经登记的资料：

- `output/datasets/hfd-full-training-20260926/raw/training_set.verified.tar.gz`：官方training_set.tar.gz，9,185,706,983字节，MD5 14232fcd1b34030b77db48d8c771710d，实际SHA256 d515b35e9c6cc2a9af717395247eda0a914118d368a09d5b00b7b8da9aded5a4。
- `output/joint-training-loop-20260925/public-evidence/`：training_labels.tar.gz、handover-record.json、class_names.json、datasheet.pdf，实际输入分别受public_evidence_registry固定SHA约束。来源https://zenodo.org/records/10708763，CC BY 4.0。

串行顺序：首审和相关回归 → 不同第二审 → mypy/Ruff → 全归档实际接入 → 新解释器`--verify`从原归档重算。每条命令前后检查受控Python与Git和起始SHA-256。任何失败停止且保留日志；创建失败目录保留，合法重试选新的输出目录，不能用未经检查的既有manifest续跑冒充完成。

真实入口也可直接运行：

```sh
python tools/inspect_hfd_training_archive.py --archive <verified-full-archive> --metadata <pinned-author-metadata> --output <new-packet>
python tools/inspect_hfd_training_archive.py --archive <verified-full-archive> --metadata <pinned-author-metadata> --output <same-packet> --verify
```

新进程重建是同实现的可重复验证，不是另一审核人的独立实现。B应独立检查来源根、坏试次分母、完整伪造、所有权限标记及真实试次/帧数；记录自己的平台、SHA和实际命令。Git只含代码及精简证据，大包在A主仓output，取不到原归档时应明确资料缺失。未合并集成、B未签收；共享集成和B所有权不变。
