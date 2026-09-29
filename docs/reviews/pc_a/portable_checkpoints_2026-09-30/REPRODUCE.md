# 复算入口与边界

实际源码154595da9a2f033934edaeb2d490d039ece29c23；base589b825e2bc232ce7d24213745ed4908f06ad18d。本轮源码/模型定位证明使用native-neural-enumeration-development@2；旧v1原件没有改写，必须结合对应旧冻结源码理解和复算，不能手改路径后称同一证据通过。

本机工作树/private/tmp/cpswm-pc-a-portable-checkpoints-20260930，持久原件output/portable-checkpoints-20260930。Python3.13.5/macOS26.4 ARM共享已有环境；PYTHONPATH=src:tests:tools，PYTHONHASHSEED=0，torch线程2。SDK另用Python3.11/AI2-THOR5.0.0，Unity commit f0825767cd50d69f666c7f282e54abfe58f1e917。environment.json和installed-distributions.json记录环境；不是新环境独立重建。

原件run_frozen.py先reviews，依次执行两轮及静态检查，再run；attempt01保存冻结源码文件哈希/完整命令/返回码/JUnit。真实运行命令为tools/run_history_action_loop.py --mode run --task clarification --site north --detector-kind fasterrcnn --sensor-profile rgbd_self_pose --visual-context，仍采用1次纠正前与2次纠正后观察预算。此轮先复制同一checkpoint到attempt01/checkpoint-initial；不会修改仓库原模型。

verify_relocation.py在正常实际历史核验后，将源码src/tests/tools与原房屋夹具复制到relocated-checkout，将历史复制到relocation-history，在新子进程取得状态基准，再把模型目录改名checkpoint-relocated。第二个新子进程运行完整history verifier并对比全部原生workspace、神经证明状态、视图、动作和账本摘要。两次均用审计钩子禁止实际读取原源码工作树；共享.venv符号链接按解析后真实路径处理，它是外部共同环境，不能因此声称全栈独立。

新部署应通过NeuralNativeProducer(checkpoint=本机目录, manifest_sha256=原哈希)显式注册模型；证明只有sha256内容引用。生产者加载与消费者复算均查文件内容；缺失/未配置/错误模型不会搜索别处或自动下载。相同哈希最后一次成功配置是当前进程的位置，失败注册不覆盖旧有效配置。证明不能自己注册路径。

audit_native_archive.py在完整历史副本上重建假几何、全部真实网络q和原生链，然后保留原始拥有者数据挑战读出与恢复。该测试针对已有托管根内的完整伪造；不提供外部签名/可信硬件，也不声称能鉴别整个托管根被一起替换。

模型与源码目录可搬移不等于Windows或跨架构数值验收。B仍需新环境和对应源码独立复核。原路径存在于采集命令/环境元数据是审计记录；新神经证明不将它当模型身份。所有训练、先验、效用、目标密度及正式指标不因目录修复改变。

完整归档2,064文件/350,060,119字节，压缩47,287,798字节，SHA256 805893b66846d682ab42d615e99dae4b4b5ecab88475a885891f30e3912029e8；逐文件读回核验。包含实际历史、完整伪造副本、源码搬移副本及初次失败原件；见evidence/archive.json及inventory.json。
