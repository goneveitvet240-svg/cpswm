# 归档预检记录

实际实验还在运行，第一次只执行sealer的清单构建前缀，没有创建archive或Git证据目录。它拒绝了 `R2/integrity-02/test_complete_saved_packages_rcurrent 2`，因为pytest重复current别名未在固定名单中。原脚本保留seal_preflight_attempt01.py。逐一检查以下现有重复别名：目标均为同一父目录内带数字的真实pytest目录，所有真实目标文件保留；只对这份明确名单按派生current别名处理，不普遍排除任意symlink。攻击夹具中的public.json symlink另以原链接文本作为真实证据成员保留。

- `R1/extended-01/native-neural-checkpointscurrent 2`
- `R1/extended-01/test_only_exact_pinned_json_mecurrent 2`
- `R2/integrity-02/test_complete_saved_packages_rcurrent 2`
