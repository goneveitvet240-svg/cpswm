# 方向结构三：不依赖技术路线选择的闭环补全 v0.1

日期：2026-08-26  
状态：`route_independent_foundation_completed`  
边界：完成的是公共数据、回放和公平比较基础设施，不等于真实感知或真实机器人已经完成。

## 1. 本轮直接完成

### 1.1 M27 失败反馈可重启回放

- `ExecutionFeedbackRecord` 可持久保存 action-outcome model version（行动结果模型版本）
  与 calibration domain（校准域）；
- 结构三 pipeline 在规范提交前将执行包中的模型绑定写入反馈记录；
- `CanonicalExecutionFeedbackReplayer` 按 M03 commit order（提交顺序）回放搜索反馈；
- 每条 `not_found` 必须重新绑定目标、位置、真实观察机会、初始快照先验和完全相同的
  行动结果模型；
- 日志 dump/load 后得到相同派生信念；模型漂移、缺先验和缺观察机会均拒绝回放；
- 非搜索反馈保留在规范日志，但其恢复/转移语义仍由 `S3-DG-07` 决定，当前不擅自折叠成
  “目标不存在”或“习惯改变”。

运行入口：

```bash
.venv/bin/python apps/direction_three/replay_execution_feedback.py \
  canonical-log.json replay-spec.json --output replay-report.json
```

### 1.2 FindingDory 真实行入口

- 原有八列 JSONL 入口保留；
- 新增 Hugging Face Dataset Viewer JSON export（数据查看器 JSON 导出）入口，要求响应
  自证 `dataset=yali30/findingdory`、`config=default`、明确 split，且不得有截断单元格；
- 新增可选 parquet 入口；本地未安装 `pyarrow` 时明确报错，不降级为错误解析；
- audit（审计）记录 source kind、原始载荷 SHA-256 和
  `real_official_rows_ingested`；本地 fixture/JSONL 和保存后的 JSON export 不能仅凭字段
  自报为官方真实行，只有固定官方 HTTPS endpoint 的 live fetch（实时读取）路径可置真；
- 八列数据仍不能生成物体实例、人物、事件、位置、位姿、遮挡或完整候选真值。

本轮环境直连官方 Dataset Viewer 超时，没有官方真实 row artifact 落盘；因此当前状态仍是
“真实行入口完成、真实行数据待接入”，不是“真实 FindingDory 实验完成”。

### 1.3 外部系统公平比较门

- 内部与外部方法统一提交 method declaration（方法声明）和逐 episode 输出；
- 所有方法必须共享 dataset manifest hash、visible episode hash、candidate support、
  observation/execution action budget、路径/时间上限和五类成本权重；
- calibration/validation 与 sealed test（封存测试集）分离，test 不能出现在 tuning splits；
- evaluator-only truth 不进入方法提交；
- 不产生归一化 posterior（后验）的方法仍可比较检索和行动指标，但不会被列入
  ECE/Brier/NLL 等概率指标资格。

运行入口：

```bash
.venv/bin/python apps/evaluation_runner/validate_direction_three_comparison.py \
  dataset.json internal-run.json external-run.json --output fairness-audit.json
```

## 2. 未替项目负责人选择

以下内容已经进入 `结构三_技术决策门_v0.1.md`，本轮没有暗中固定：

- M21 使用哪一种真实 LLM 与受约束解码方案；
- 视觉检测、分割、VLM、3D 感知和跨天实例重识别组合；
- 人物跟踪、事件推断和条件化习惯证据采用独立模型、VLM 候选还是神经符号混合；
- Habitat、Isaac Sim、iGibson/AI2-THOR 及真实 ROS 2 机器人栈的先后顺序；
- 非搜索失败采用 retry、重新观察、重新定位、询问、停止还是安全撤退；
- 纳入哪些外部搜索/记忆系统；
- 是否新增 `pyarrow`/Hugging Face `datasets` 依赖。

这些 gate 暂缓不会删除语言、视觉、位置、事件、人物、习惯、unknown、主动确认、执行写回
或外部比较中的任何能力。
