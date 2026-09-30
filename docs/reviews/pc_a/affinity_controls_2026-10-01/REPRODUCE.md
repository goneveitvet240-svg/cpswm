# 固定特征组对照复现

功能源码a6c026963b5fec1503fa0d582fe016eccf60c756，base/父PR76 head ffcaa7b292c73201d799f6631688387409c21cb7。四个新增文件，旧训练器未改；功能身份879份src/tests/tools Python文件见frozen-source.json。复用Python3.13.5开发环境，OPENBLAS_NUM_THREADS=1；环境实际版本与锁文件摘要见runtime-environment.json，不是独立环境重建。

父材料是PR76完整原件包4ae753a03fd1237e86fa548db7290143daa7ee73d0a51b36055cb504865e324e，内含674训练输出及case ledger。调用方保持ledger外部SHA256 32e0dc7cec8fce6dfca5bc36755cfba5cf3551b454c1f746f20ac2076936e842。父真实训练源码0a8a2384c321c3a2dc14cf218854754161af9ffd有875份Python源码；PR76交付head仅文档不同，可作为匹配源码目录。新879文件源码不能冒充旧875身份。

新CLI先核对父ledger两次成功run/verify、完整674成员、旧代码内容，再使用明确调用方路径构造旧run_instance_affinity.py --verify命令，从PR73/74原始输入重建并重训父模型。不会执行ledger中记录的任意argv。原采集inventory pin为9791a946543b9158890324d3ff35a80ea04d51c9cabb6e09540f569abd903d47，PR74前端ledger pin为517fc5b24afd80e4311d0de66dcfa6d113de6cd11763d61aeaaecd345740ccf6；旧capture/frontend来源身份分别865/869份Python文件，具体取得步骤继承PR73/74/76复现说明。SDK及historical Python都保持venv入口，不能resolve symlink成基础解释器。

在冻结新源码根目录，用全新、不与输入/来源目录互相包含的输出目录运行：

```sh
PYTHONPATH=src:tests:tools OPENBLAS_NUM_THREADS=1 "$PYTHON" tools/run_instance_affinity_controls.py \
 --affinity-results "$PR76_ARTIFACTS" --affinity-source "$PR76_SOURCE" --historical-python "$HISTORICAL_PYTHON" \
 --affinity-ledger-sha256 32e0dc7cec8fce6dfca5bc36755cfba5cf3551b454c1f746f20ac2076936e842 \
 --collection "$COLLECTION_ATTEMPT02" --capture-source "$CAPTURE_SOURCE" --archive "$PROCTHOR_ARCHIVE" \
 --sdk-python "$SDK_VENV_PYTHON" --binary "$UNITY_BINARY" --frontends "$PR74_ARTIFACTS" --frontend-source "$PR74_SOURCE" \
 --inventory-sha256 9791a946543b9158890324d3ff35a80ea04d51c9cabb6e09540f569abd903d47 \
 --frontend-ledger-sha256 517fc5b24afd80e4311d0de66dcfa6d113de6cd11763d61aeaaecd345740ccf6 \
 --output "$NEW_OUTPUT"
```

追加--verify会重新验证父输入并从头训练三模式，再比较全部292输出文件字节，不是仅恢复旧模型。完整实际argv/源码/UTC时间/退出码/产物摘要由run_experiment.py写入case-results.json。已有目录不覆盖，失败日志不复用。

模式rgb_only仅保留颜色差三列，geometry_only保留像素/深度/点距离五列，combined保留全部八列；禁用列先经过完整原输入验证再置0。三者共享相同候选、像素对、深度有效性、train/validation/VOID和固定L2=0.01/30步预算。wrapper绑定模式、原features/targets、投影后内层model摘要和禁用列零均值/系数、单位尺度。checkpoint restore验证字段及外pin，不能单独证明训练来源。combined内层模型JSON及96份score NPY必须与父模型精确相同。

顺序：全部公开features/valid载入→仅64训练帧targets→三模式fit/restore及全部96帧预测→32验证帧targets→报告。历史fresh核验确实提前读取含私有信息的原件，因此这是模型拟合隔离，不是恶意进程隔离。每个公开有效VOID score必须保留且有限，不只验有标签的分数。

产物models/下三份wrapper、frames/000至095中每模式一份scores NPY、report.json。report绑定父674原件及当前879代码，包含全部帧/屋/分区的总计、正负类BCE/Brier、各类实际有样本房屋数与house_macro。缺类或无监督为null，不是0损失；常数来自同一训练标签频率。本轮是共用RGB检测候选、RGB-D有效性上的特征组开发对照，非三个独立传感器系统、正式选型、calibration、mask、世界身份或位置/行动成功。

定向回归：

```sh
PYTHONPATH=src:tests:tools OPENBLAS_NUM_THREADS=1 "$PYTHON" -m pytest -q -o addopts='' \
 tests/test_instance_affinity_controls.py tests/test_instance_affinity_controls_driver.py \
 tests/test_instance_affinity.py tests/test_instance_affinity_dataset.py tests/test_run_instance_affinity.py \
 tests/test_offline_frontend_diagnostic.py tests/test_offline_frontend_evaluation.py \
 tests/test_surface_factor_diagnostic.py tests/test_offline_factor_manifest.py tests/test_offline_factor_worker.py \
 tests/test_offline_factor_capture_verifier.py tests/test_offline_factor_collection.py \
 tests/test_offline_factor_orchestration.py tests/test_offline_factor_asset_provenance.py
```

冻结前447 passed in82.11s，四文件Ruff/格式通过。正式两轮顺序审查与实际训练结果分别见报告与日志；A辅助不是B独立/全仓CI/统一科学验收。原分类对照、位置+朝向、主动澄清及完整框架保持。

## 实际结果与独立核验

真实 run/fresh verify 均 exit 0，用时111.96/109.26秒，全部292输出逐字节一致。case-results.json原pin：5eaabaaae15e4ed453c0f84b4f243103e25e5e9c1125f87f23e82e2be352bad2。独立检查脚本命令如下（先把源码和父归档路径按脚本参数或复现布局准备好）：

```sh
PYTHONPATH=src:tests:tools OPENBLAS_NUM_THREADS=1 "$PYTHON" independent_result_check.py --ledger-sha256 5eaabaaae15e4ed453c0f84b4f243103e25e5e9c1125f87f23e82e2be352bad2 --source-sha a6c026963b5fec1503fa0d582fe016eccf60c756
```

独立结果independent-analysis.json SHA256：1ab124f0d83cda109e80d10307f868a89c0edeb49c8e3d77a7e68c6bb3a45060；从父已pin特征独立重算三模式标准化、目标/梯度、全部分数和分组统计，非另一套原始RGB-D提取器。独立脚本保留在原件归档与可读预览中。R1/R2实际命令、两轮447通过和受控替身范围见各报告。

plot_results.py只读冻结report生成PNG/PDF，根已打开PNG检查：图例/坐标/分母/分组清楚，无裁切。绘图exit0，首次字体缓存提示不影响产物；未重算或选择模型。
