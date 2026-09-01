# 原始数据到外部基线结果的证据链 v0.1

状态：仓库内契约和对抗测试完成；真实 FindingDory 视频、O-STaR/STREAK 外部复现结果仍未
接入，不得将本协议解释为真实证据已经产生。

## 证据链

```text
raw file bytes
  -> RawDataArtifactSignature (whole-file + ordered chunk SHA-256, Ed25519)
  -> DirectionThreeFrameContentManifest
       (raw signature + raw content + encoded frame + preprocessing + decoded frame)
  -> DirectionThreePredictionCache
       (episode/split/frame + decoded input + signed frame-manifest hash)
  -> IndependentTestProcessReceipt
       (sanitized env + distinct child PID + timeout + stdout/stderr + fresh output hashes, Ed25519)
  -> OAMExternalEvidenceReceipt
       (complete reproduction + independent tuning + raw/frame/process/result hashes, Ed25519)
```

## 强制边界

- 原始数据签名绑定绝对 locator、字节数、全文件哈希及有序 chunk 哈希；签名期间文件元数据
  漂移、验签密钥错误、同内容复制到另一 locator、签名后修改均拒绝。
- 正式证据使用 Ed25519 非对称签名。候选/评估进程只需获得公钥 verifier，不获得签名能力；
  既有 HMAC 仍只适合开发态内部回执。
- 结构三帧清单同时绑定原始签名哈希和原始内容哈希。每帧再绑定 encoded bytes、预处理
  配置和 decoded input；prediction cache 的 `input_content_hash` 必须等于已签帧输入。
- 独立测试必须是不同 PID 的无 stdin 子进程，使用显式环境、硬超时和进程组终止。输出文件
  必须位于工作目录内且运行前不存在，防止把旧结果认领为本次运行产物。
- OAM-PHM 外部回执只接受 `REPRODUCTION_COMPLETE` 的外部方法；进程角色必须精确为
  `oam_external:<method>`，结果必须来自该签名子进程，raw/frame/tuning 哈希必须与调用方当前
  期望完全一致。

## 当前不构成的结论

- 这些契约不能证明下载来源本身可信；首次签发仍要求独立 custodian（保管方）核对官方来源。
- 哈希和签名不能替代数据许可审查、视频解码正确性抽查、外部方法忠实复现和独立调参。
- 当前 O-STaR/STREAK manifest 仍未达到 `REPRODUCTION_COMPLETE`，所以按设计不能获得接纳回执。
