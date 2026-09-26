# 本轮外部监督的范围与出处

来源为 EPIC-KITCHENS VISOR（Darkhalil 等，NeurIPS 2022），同时引用 EPIC-KITCHENS-100（Damen 等，IJCV 2022）。官方数据入口：https://doi.org/10.5523/bris.2v6cgv1x04ol22qp9rm9x2j6a7 。原数据 README：https://data.bris.ac.uk/datasets/2v6cgv1x04ol22qp9rm9x2j6a7/README.txt 。作者更正代码固定 8566507382add7dd037a83e7233950e0ad1ea78e；两份代码/更正表的 Git blob 已核验，未执行外部代码。

在查看接触结果前固定官方 train/P01 下首个视频 P01_01，全部485稀疏帧，无validation/test，无插值标签，无按手部检测成功筛选。这是一个已花费的开发子集，不能代表完整VISOR、多人交接或HFD。训练与科研架构的正式选择未变。

官方README区分接触某个分割实体、hand-not-in-contact、none-of-the-above和inconclusive。当前按作者HOS转换器对后两者的排除做法，保留两种原始状态但不生成二分类目标；不把它们标成负例。对非穷尽的对象掩膜保留exhaustive标志，不凭一条接触边生成其它对象的负关系。没有跨帧物体身份、释放时刻或新时间插值。官方已公布11帧关系更正及手套更正，本固定视频均不涉及；本入口遇到相关更正帧或未支持手套schema会拒绝，扩展须单独审核。

官方README声明CC BY-NC 4.0，数据目录通用许可证栏显示另一非商业标签；两者记录保留。按原README的非商业研究范围使用并署名。原图与作者代码只保存在本地研究备份，Git不重分发完整图片或第三方代码。

来源摘要是本机从官方HTTPS取得后冻结的内容身份，不冒充作者签名或独立真实性证明。作者人工标注独立于本项目模型预测，但没有本项目第二位人工复核，也不是物理传感器接触/释放真值。数据可为单帧接触组件提供监督；它不能填充完整ProposalSample九因子/六操作目标，不能授权运行时语义、记忆或动作，也没有校准本前端位姿误差。
