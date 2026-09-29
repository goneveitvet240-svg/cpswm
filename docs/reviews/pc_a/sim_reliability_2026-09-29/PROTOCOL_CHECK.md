# 操作语义与数据用途核查

已查当前源码、实际SDK源码和AI2-THOR官方文档。这里的认可范围是固定相机的局部测量实验，不是导航/操纵基准认证。

- 官方[导航API](https://ai2thor.allenai.org/ithor/documentation/navigation/)中RotateLeft/RotateRight的degrees控制机身yaw，正horizon向下看。当前明确传15/45/90度、俯仰30，私有日志核对实际yaw、cameraPosition、FOV60、真实RGB尺寸；没有把初始化改位姿计作机器人导航。
- 官方[环境状态](https://ai2thor.allenai.org/ithor/documentation/environment-state/)定义frame为RGB uint8、instance mask为实例分割；visible还含距离条件。当前RGB按RGB进入模型，没有BGR交换；目标像素数由boolean掩膜直接算，SDK visible单列。bbox IoU>0只是描述性几何交集，不是严格目标成功标准。
- 官方[初始化](https://ai2thor.allenai.org/ithor/documentation/initialization/)说明step返回动作执行后的状态。当前成功状态与同一event的RGB/掩膜成对落盘，命令ID/原图摘要和拥有者记录一致；host-utc时间是宿主收到事件附近的时间，不是物理接触真值时钟。
- 初始苹果位置由场景文件外生设置，目标kinematic=True。机身初始化y=0.95之后SDK实际落地高度约0.901，相机高度约1.576；实际相机位姿与请求机身位姿分别记录。这允许受控观察诊断，不验证移动可达性、抓取动力学或可操作成功。
- 两前端在同一原图上的读数是可配对对照。独立启动的不同方法场次并非逐字相同图像；当前各条件仅两个目标摆放位置，不能把六算法重复当六个独立场景，也不能据此给出可靠泛化置信区间。相同规则不自动消除渲染差异和顺序效应。
- 旧运行绑定了Unity执行文件及Python解释器摘要，但没有完整SDK包/Unity资源包身份。现补录实际SDK 5.0.0、Python 3.11.16、默认质量Ultra、27 SDK Python文件与166 Unity app文件（1,069,810,761字节）摘要，供后续绑定；不能倒推证明旧时完整资源包未变。
- 所有自审只检查本机可读源码/数据的一致性和实际重算，不保护被一起伪造的解释器、模拟器与全部数据，也没有第三方外部不可变见证。Git交付摘要支持检测交付后文件变化，不能替代独立B复核。

基于以上，原报告中“可运行”“可重算”的工程层结论可逐项验证；“已校准”“成功识别了该实例”“额外行动收益”“自然长期闭环”仍不在现有证据范围。下一步依据完整旧图重算结果与已固定的新重复采集诊断，决定观测建模可以使用哪些数据。
