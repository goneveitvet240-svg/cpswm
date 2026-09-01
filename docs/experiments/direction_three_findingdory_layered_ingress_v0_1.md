# Direction Three FindingDory layered ingress v0.1

日期：2026-08-26  
Gate：S3-DG-13D  
证据状态：官方固定 revision 的 3 行真实元数据已获取、哈希并离线重载

## 固定输入

- dataset：`yali30/findingdory`
- revision：`016160dd7ec1d0d23aa09bba7d48470e835030a0`
- split：`validation`
- 请求行数：3
- acquisition runtime：`datasets>=5,<6`
- normalized runtime：`pyarrow>=21,<26` 可选旁路；规范评测读取 JSONL

官方仓库页面在核验时显示约 85,083 行、32.5 GB，总仓库不适合在未规划存储前直接下载。
本次只请求流式前三行，不请求视频压缩包。

## 执行入口

```bash
uv run --isolated --extra findingdory python \
  apps/evaluation_runner/prepare_direction_three_findingdory_layered.py \
  --backend datasets \
  --artifact output/direction_three/findingdory/016160dd7ec1d0d23aa09bba7d48470e835030a0/validation_first3.jsonl \
  --manifest output/direction_three/findingdory/016160dd7ec1d0d23aa09bba7d48470e835030a0/validation_first3.manifest.json \
  --dataset-revision 016160dd7ec1d0d23aa09bba7d48470e835030a0 \
  --source-split validation \
  --max-rows 3
```

## 结果

隔离环境成功解析并安装锁文件中的 `datasets 5.0.1` 与 `pyarrow 25.0.1`。首次请求
收到 HTTP 429，程序在读取任何真实行前停止且未发布 artifact。等待服务端给出的限流
窗口后只重试一次；第二次成功流式读取 3 行，并生成：

- `validation_first3.jsonl`：2,063 bytes；
- `validation_first3.manifest.json`：454 bytes；
- normalized artifact SHA-256：
  `9a9aae2b638defbb104d3af19fa28a6417d6261d3f5abaf2c7979ab2944de7df`。

离线重载审计：

- accepted rows：3；rejected rows：0；
- unique episodes：1；unique tasks：3；
- source kind：`pinned_hub_artifact`；
- `real_official_rows_ingested=true`；
- video-question 与 frame-retrieval truth 可用；
- instance transition、person/event/habit truth 和完整结构三 episode 仍不可用。

因此当前结论是：

- 分层入口代码、依赖锁、本地固定行纵切片和官方三行固定 revision 纵切片均通过；
- 官方八列真实元数据已经进入不可变 artifact；
- 32.5 GB 视频仓库没有下载；
- 该成功不改变字段缺失审计，不能用三行元数据冒充完整 FindingDory 具身闭环。
