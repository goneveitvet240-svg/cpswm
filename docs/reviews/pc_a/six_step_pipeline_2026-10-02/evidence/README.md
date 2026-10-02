# 证据封存

1791个原始文件、8个原有符号链接，原始文件总计548,512,565字节。三个归档共106,864,271字节；相同内容仅在包内用hardlink去重，所有逻辑路径逐一SHA验证，未删除失败记录。

| 包 | 字节 | 已核对原始文件 | SHA-256 |
|---|---:|---:|---|
| development.tar.gz | 15171725 | 265 | ccc95802fd2ffcb0a34982fd02464f8706d46697d84758a0c366b8afd1404bd4 |
| historical.tar.gz | 53455933 | 865 | e41ffee7694ab9a54db752f1f7008ae2b1537b22b12d6f1f85f3e227e29ef6b8 |
| release.tar.gz | 38236613 | 661 | abe866c6f00018134452eb0f7d737ae85582fa05d8ec85c9b158918839b9561c |

三个包解压到同一空目录，均生成evidence-data/；保留tar内相对symlink/hardlink。development含拟合数据、失败日志、环境、source-history和原始源pin；historical含修前/中止比较及822fc3e静态控制；release含745613e最终三臂比较与相同生产源码的后续记忆对照。

数据库保存源/依赖/模型绝对路径绑定，不能改写以伪造跨平台恢复。B应建立自己的环境重跑，或如实限定为归档复算。归档中仅含仿真与受控fixture，没有两大预训练视觉权重；小型受控neural checkpoint原件保留。

MANIFEST.json保留每个文件的内容hash；release-source-files.json列出960个生产/测试/驱动源文件。封存时逐个复核未变。源代码历史见Git提交，calibration-worker.py由实际记录的worker hash逐字节核对。
