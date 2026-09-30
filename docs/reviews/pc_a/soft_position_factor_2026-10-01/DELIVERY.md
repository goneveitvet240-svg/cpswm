# 本轮交付与复现

实际两审/运行源码 `1bd6c204d349024196c23df12cca61dbcea91e6c`（895 Python），后续文档SHA不替代功能SHA。base PR77 head8623e7890594fce2b3c872bd2484b30138a9f408。真实run324.36s / fresh326.64s，302输出逐字节相同；完整case ledger pin `9b9ed2d9208c1907d8295d5edc5aeb2f48af7b9b3625108b9642430a06780efc`。最终开发174项，新R1 68项，新R2 35项不同测试通过；A辅助非B独立/全仓CI。原493、379及171组合失败均保留，不计当前通过。

全部原件9295文件、3713960160原始bytes，gzip 427706204 bytes，完整SHA256 `fa7620a0b1ba5f522db4fdf10d8e1778fcf83adb7608b5facc402984b808174f`。逐成员读回和原件复核均通过；只排除清单中派生Python缓存和pytest current符号别名，真实目标文件保留。未排除任何失败、日志、模型、原始测试数据库。源外本机原件为 output/soft-position-factor-20261001，已停止写入。

- `soft-position-factor.tar.gz.part001`: 40000000 bytes, SHA256 `a23edf9a0d5037cb3212b78a4abfdd1a788bfedf537f84b83f371c2202c64b4c`
- `soft-position-factor.tar.gz.part002`: 40000000 bytes, SHA256 `fea07efba2c0203bbf55330a442f4039c543d1ee00e34e533e156f65d804a524`
- `soft-position-factor.tar.gz.part003`: 40000000 bytes, SHA256 `8749e36eac100d1524eaf1cdaed16439afa5b19de58780063e96e20e3643edba`
- `soft-position-factor.tar.gz.part004`: 40000000 bytes, SHA256 `0f8219b191d53fc2a3f543df46b075ffced7a9b4f3f6d105366c2b0325009cfd`
- `soft-position-factor.tar.gz.part005`: 40000000 bytes, SHA256 `02344803b8717c57707e6583d9c23bfdbbd6eb1cc088bd0bb4d092805751f820`
- `soft-position-factor.tar.gz.part006`: 40000000 bytes, SHA256 `7c948890a635673a83be80d51923b5a7d91ddd94097dc3d37998a8f4badaef54`
- `soft-position-factor.tar.gz.part007`: 40000000 bytes, SHA256 `4c7d9dd9af04600a1e32459223605f450b98c5097f2f689fc39330658697fc40`
- `soft-position-factor.tar.gz.part008`: 40000000 bytes, SHA256 `84305ba3fa155bf6750e3d9a5b1cbffe122792fef9b242102da8916f98ac82d6`
- `soft-position-factor.tar.gz.part009`: 40000000 bytes, SHA256 `f8713f28df1f27edb3f011f941c7dcffedb0b1db186d769a2d159dd945dbfb24`
- `soft-position-factor.tar.gz.part010`: 40000000 bytes, SHA256 `e3bba6040baced0b61d578aee9fbc86067564f8f6d9a09129c282979ce7d8799`
- `soft-position-factor.tar.gz.part011`: 27706204 bytes, SHA256 `67b8a13dd32348b6fd0b7786ca87b3e244f57296e4696c442087d5234d1bed3a`

若有多个part，按archive.json的archive_parts顺序以二进制拼接；检查完整SHA256后解压。不要只解压某个part。每个成员路径/大小/摘要见 evidence/inventory.json。重放时同时按父PR77/76/74/73交付说明恢复各自不可变原件与匹配源码，不能用新源码重签旧来源。完整命令见REPRODUCE.md及包内run_experiment.py/case-results.json。

[报告](REPORT.md)、[一轮审核](ADVERSARIAL_REVIEW_1.md)、[二轮审核](ADVERSARIAL_REVIEW_2.md)、[逐屋图](position-development.png)。首次独立算术因重复解压开销中止，缓存同一原掩膜后的8.22s完整检查通过；版本和日志均在包内。数值误差2,004训练/1,664验证seed强相关、55/96帧无监督；两参考并列，不选择正式目标定义。四模型实数据目前仅进入数值diagnostic，Native测试仍为受控数据。真实模型到Native桥接在下一分支进行中，未计为本轮完成。

用户原树、STATUS_B与完整统一研究范围保留，未合并共享集成分支。下一主项为真实归档单capture桥接，再解决同语义新raw观测事务与逐cluster重放。自然身份/未知模型/正式参考、朝向、完整闭环任务收益、B验收仍开放。
