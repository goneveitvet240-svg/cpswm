# 离线实例／位置采集的复现

本轮实际源码为 `e88f50752ca50843fc5382b853c65abe134f1281`；后续交付提交仅文档及证据。每批 configuration.json 记录实际 src/tests/tools 共865份 Python 源码、SDK文件、Python和Unity二进制摘要；不能只改文本SHA绕过核验。

## 环境与原始来源

采集器和测试实际复用 Python 3.13.5 的现有开发虚拟环境；SDK子进程为 Python 3.11.16、ai2thor 5.0.0、NumPy 2.4.6。具体环境见 runtime-environment.json 及 collection-attempt02/configuration.json；没有声称独立安装复现。开发依赖声明为 uv.lock / pyproject.toml，原生SDK运行环境另行记录。

固定 ProcTHOR TRAIN revision `439193522244720b86d8c81cde2e51e3a4d150cf`，原始 train.jsonl.gz SHA256 `ee3c4aa14b4d8f0895fecfb5fdaca59395427ca1018b2f9aeeedbc61e5824587`。原文件本轮不改写，plan保留原始0–12行字节；整批核验仍需要完整原压缩包。Unity固定构建 `f0825767cd50d69f666c7f282e54abfe58f1e917`，本机macOS可执行文件SHA为 `d8bbfbee47581f4aa4f5df71e095f0a1c00888bed7b493eaffcc0f37d6364df3`。Windows/Linux版本不能冒充同二进制复核；跨平台实验须另行绑定实际环境和证据。

## 顺序双审

在仓库根目录运行：

```sh
PYTHONPATH=src:tests:tools .venv/bin/python -m pytest -q -o addopts='' tests/test_offline_factor_manifest.py tests/test_offline_factor_worker.py tests/test_offline_factor_capture_verifier.py tests/test_offline_factor_collection.py tests/test_offline_factor_orchestration.py tests/test_offline_factor_asset_provenance.py
```

当前两轮均160通过、零跳过，源码冻结后先第一轮再第二轮。报告为 ADVERSARIAL_e88f507_ROUND1.md / ROUND2.md；受控组合探针及日志在完整证据包内。探针保留本机绝对路径和受控模拟SDK/进程，搬移需替换定位路径，不是实际Unity采集命令。

## 新采集与原件复核

以下变量须指向实际路径；输出目录必须不存在。采集一次恰尝试固定1–12，各8帧，不替换失败房屋。

```sh
PYTHONPATH=src:tools .venv/bin/python tools/collect_offline_factor_data.py \
  --output "$NEW_OUTPUT" --archive "$PROCTHOR_ARCHIVE" \
  --sdk-python "$SDK_PYTHON" --binary "$UNITY_BINARY"
```

第二批原件复核使用外部留存pin，不能对变更后的清单另签一个pin再称原件通过：

```sh
PYTHONPATH=src:tools .venv/bin/python tools/collect_offline_factor_data.py \
  --verify --output "$EVIDENCE/collection-attempt02" \
  --archive "$PROCTHOR_ARCHIVE" --sdk-python "$SDK_PYTHON" --binary "$UNITY_BINARY" \
  --inventory-sha256 9791a946543b9158890324d3ff35a80ea04d51c9cabb6e09540f569abd903d47
```

这条真实复核退出0，日志 collection-attempt02-reverify.log。需要同源码字节、SDK和二进制身份；文档提交不改变源码身份。第一批由 cd51415ced36b16f2e7ebcb743fdda5ca8a9b7ab 采集，12项失败原状保存，必须在其历史源码下复核，不能用当前源码回写其状态。

## 证据读取

压缩包包含两次真实采集的全部SDK事件、public命令/回执、RGB-D、mask/segmentation/目录、来源清单、失败记录、两轮审查、攻击探针及主引擎源码引用。外部 evidence/inventory.json 给出每个包内文件的SHA256；evidence/archive.json 给出整个压缩包的SHA256、大小、文件数和实际源码。封存时逐文件读回复算，不以打包命令成功替代验证。

先复核完整来源和固定分区，再根据mask统计可见性。资格503对象、可见159对象、253对象帧次分开。所有来源曝光审计通过不代表每个对象都具备目标资格；原始空assetId和建筑/部件必须保留。不得把归档真值导入线上特征或任务策略。

本轮没有导出监督样本、选择正式位置训练参照、训练或校准模型。下一轮先诊断自然前端候选覆盖与位置参照；完整框架、原对照、任务效用与正式门槛保留。
