# 复算入口

本轮工作树 /private/tmp/cpswm-pc-a-owned-visual-neural-20260930；独立分支 codex/pc-a-owned-visual-neural-20260930。方法初版90d9abbc8ba820347a2086a2332d377b0acdb3f0，追加运动修复30d57a0ba7df824ab7fb6fc955e5deacb404f256。实际证据将绑定修复版本，旧审查只证明旧源码的局部矩阵。

环境沿用本机 Python3.13.5，并非独立环境重建；设置 PYTHONPATH=src:tests:tools，防止环境的旧 editable 路径覆盖当前源码。torch线程2，PYTHONHASHSEED=0；SDK独立Python3.11 / AI2-THOR5.0.0，Unity commit f0825767cd50d69f666c7f282e54abfe58f1e917。SDK/二进制身份必须运行前后核对。

本机原件：output/owned-visual-neural-20260930。run_frozen.py 先执行 reviews（顺序第一审、第二审和静态检查），新源码必须新 attempt 目录；检查完成且源码逐文件未变化，才允许 run。真实命令为 tools/run_history_action_loop.py --mode run --task clarification --site north --detector-kind fasterrcnn --sensor-profile rgbd_self_pose，再比较省略/提供 --visual-context；保留1次纠正前、2次纠正后动作预算。同历史新进程复算由 history_visual_evidence.py 调用完整 history verifier。

analyze_neural_input.py 只在同一原件的候选支持上重算实际 / 移除几何 / 移除全部视觉输入，检查真实q变化及精确积分目标不变；这是计算输入消融，没有为反事实行动编造相机像素。audit_native_archive.py 只操作归档副本，重建完整假几何源及真实11源网络/原生记录，检验拥有者重新推理后拒绝。

绝对checkpoint目录仍是跨机恢复缺口；不能改证明文件里的路径再宣称同一证据已通过。B须按对应源码复核，并使用可信本地路径解析迁移方案后再进行跨机验收。本机恢复/新进程复算不代替 B 独立验收。所有命令、返回码、原始失败和未完成项在交付归档中保留。

完整原件286文件、254,979,377字节；压缩33,953,861字节，SHA256 56c4dc23d09ad3dd12dcff9172695131b406514a54e13aae816608944ea76ac5，逐文件读回核验。包含两版源码审查、运动失败/修复、真实历史、完整伪造副本和全部辅助脚本。见[evidence/archive.json](evidence/archive.json)与[evidence/inventory.json](evidence/inventory.json)。
