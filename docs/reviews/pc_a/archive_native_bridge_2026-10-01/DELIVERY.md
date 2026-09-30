# 本轮交付与复现

实际冻结/两轮审核/运行源码 `82c7a81fba0c3af3688978ce222b1b94e4cc5bd9`，901 Python文件。父位置功能源码1bd6c204d349024196c23df12cca61dbcea91e6c；父交付head df8e30bd7eb436444b191ea242e938c8948d08a1，文档合并ced6aa1439b2cd23018042e0c6453300c74d8390。后续文档head不替代该功能SHA。分支codex/pc-a-archive-native-bridge-20261001，草稿PR以PR78分支为base，不合并共享集成分支。

bridge: run 761.56s / verify 722.54s / 76 files；bare: run 354.22s / verify 398.48s / 103 files。四次exit0，fresh后原输出逐字节不变。case ledger外pin `328b4b10276c44a05b91cfcbb7f24d370ff8092e85a9fe729939311bc6b4fc42`，父ledger外pin9b9ed2d9208c1907d8295d5edc5aeb2f48af7b9b3625108b9642430a06780efc。完整固定参数见case-results.json/run_experiment.py；后者在匹配源码、clean工作树和顺序双审的基础上执行。

原始证据共11429成员（11428常规文件，1条保留的测试符号链接），3162036763原始bytes。gzip 342551816bytes，完整SHA256 `807e4ab4a2ae1cd9551edcf8d20faecf52d6ab2ec4504c0f7739fc0c408bce4f`。所有成员读回及原件复核通过；只排除inventory说明的派生缓存/pytest current别名，保留所有失败、日志、原数据库和恶意形状测试数据。符号链接按原文本保存，不转换成普通文件，不盲目解引用。

- `archive-native-bridge.tar.gz.part001`: 40000000 bytes, SHA256 `7d0df9a116ee7fc25d299711fcb3db5c3f3fdba0d44aa77fad824806ac8e1b9b`
- `archive-native-bridge.tar.gz.part002`: 40000000 bytes, SHA256 `5d65dc888d18c8cba0fd960547c455117d9ecb6e4dc9101df8afa77456efa0cf`
- `archive-native-bridge.tar.gz.part003`: 40000000 bytes, SHA256 `df411c15f1ae9c751cb7cb46479b2063bd43e95cec60e0b188ac1684a9b44798`
- `archive-native-bridge.tar.gz.part004`: 40000000 bytes, SHA256 `91449af0d370e1fd763bd71dcf0dcb00c6dc53c99034bc913a3a42d15987ed56`
- `archive-native-bridge.tar.gz.part005`: 40000000 bytes, SHA256 `168043acad3213408796bffc31913ccfd70d29e46cff7b2d27fda49ee2051e11`
- `archive-native-bridge.tar.gz.part006`: 40000000 bytes, SHA256 `ebef3876b0a38da28c1d98ca93a2be85cad9c8634568c06839c0b4018597c093`
- `archive-native-bridge.tar.gz.part007`: 40000000 bytes, SHA256 `6bc4f1f2938f2a1f4c694a9b8d9bc99b275b82a430a71638abd7496e2f821279`
- `archive-native-bridge.tar.gz.part008`: 40000000 bytes, SHA256 `60642be101a0f7ed08334215b9219cfdeeb24783cf8dc1decf25e2f2dc637688`
- `archive-native-bridge.tar.gz.part009`: 22551816 bytes, SHA256 `2f22e66f5a9071357580a01947aee86ab5ca209652ac5770b1836f1ca8951826`

按archive.json中archive_parts顺序二进制拼接，校验完整SHA后解压；每条成员大小/类型/摘要见evidence/inventory.json。先按PR78、77、76、74、73交付恢复外pin原件与对应源码，只在满足原环境绑定时映射本机路径，源码/输入身份不变。不要运行case ledger里不受信的任意argv；生产入口自行构造固定历史verify命令。包内绝对路径保留实际运行事实，原DB不可直接搬到Windows，顶层历史verify仍耦合POSIX路径与原Mac SDK/runtime/binary。B可先静态核验归档和独立受控测试，跨平台运行需另轮受审适配；详PORTABILITY_REVIEW.md及REPRODUCE.md，不承诺换路径即可复现。

[结果](REPORT.md)、[图](position-comparison.png)、[R1](ADVERSARIAL_REVIEW_1.md)、[R2](ADVERSARIAL_REVIEW_2.md)。R1 180不同测试、4次受控bare CLI及8个Native分支/16次真实SQLite子进程；R2独立本机完整数据改动、保存状态及恢复范围详报告。属于A辅助，非B独立或全仓CI。真实桥接采用frame000训练屋图像+四个真实模型，语义关联/身份/prior仍受控，不是自然身份或新物理相机实验。

配对validation结果：sdk_transform_position_m: bare_seed 0.750330→0.661757m (n=1664), soft_affinity 0.674738→0.615581m (n=1664), uniform 0.833717→0.785566m (n=1664)；sdk_aabb_center_m: bare_seed 0.549088→0.561687m (n=1664), soft_affinity 0.513540→0.523058m (n=1664), uniform 0.712308→0.711919m (n=1664)。所有96帧保留；相关seed、空帧/VOID与条件监督如实报告。两参考并列，不按结果选择正式参考或校准。Native独立算术以SciPy logpdf/Joseph形式核对；分析脚本修复与其专项复核独立于产品源码双审计数。

下一完整主项：同语义来源后续owner-issued capture进入Native真实更新、一次消费、失败回滚、逐cluster重放与fresh恢复。设计NEXT_OBSERVATION_IMPLEMENTATION.md已明确原子边界，尚未实现；不得把重发semantic、改UUID或重复乘相关seed当作完成。完整框架、原分类对照/主动澄清保留。自然跨视角身份、正式位置/未知模型/时间相关性、朝向、长时程与行动收益、B验收仍开放。
