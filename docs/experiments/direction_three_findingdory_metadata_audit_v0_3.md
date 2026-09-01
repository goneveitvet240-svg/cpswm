# 方向结构三 FindingDory Metadata Audit v0.3

日期：2026-08-26  
成熟度：`real_row_ingress_ready_official_artifact_pending`  
证据边界：官方仓库和文件结构已核对；本轮环境未成功下载官方 row payload。

## 1. 官方入口核对

- `yali30/findingdory` 当前公开为 Parquet 视频问答数据，许可标为 Apache-2.0；
- `findingdory/findingdory-habitat` 当前公开 train/val 的 `episodes.json.gz`、
  `transformations.npy` 和 `viewpoints.npy`，可支持比八列 SFT metadata 更深的 episode
  适配审计；
- 当前环境访问 Hugging Face Dataset Viewer API 超时；本地也没有 `pyarrow`，所以没有
  将 fixture 或网页描述冒充真实官方行。

来源：

- https://huggingface.co/datasets/yali30/findingdory
- https://huggingface.co/datasets/findingdory/findingdory-habitat

## 2. v0.3 新增入口

```text
JSONL                         本地行；始终标记 local_jsonl
Dataset Viewer JSON export   校验 dataset/config/split/truncated_cells；不单独证明传输来源
Dataset Viewer live fetch    固定官方 HTTPS endpoint，可记录真实官方行已读取
Parquet                       可选 pyarrow；缺依赖时明确停止
```

每次审计新增：

```text
source_kind
source_payload_sha256
real_official_rows_ingested
```

只有代码直接从固定的 `datasets-server.huggingface.co` HTTPS endpoint 请求
`yali30/findingdory/default/<split>` 且成功接受至少一行，才会得到
`real_official_rows_ingested=true`。保存后的 Dataset Viewer JSON、本地 JSONL 和 parquet
文件仅凭列名或自报字段不能升级证据等级。

## 3. 仍未完成

- 官方真实 row/parquet artifact 尚未落盘；
- 视频本体尚未下载或解码；
- Habitat episode、变换矩阵和 viewpoints 尚未转换成结构三 episode；
- VLM、RGB-D、点云、实例重识别预测尚未产生；
- actor/event/habit evaluator truth 仍不可由八列 SFT metadata 推导。

因此 v0.3 完成的是 real-row ingress（真实行接入）防火墙，不是 S3-3 真实感知成绩。
