# 三个可直接重放的原图案例

这是第五轮完整矩阵之后挑选的诊断示例，**不是新基准、独立样本集或成功率分母**。十五个原始工件共3,701,670字节，逐文件SHA见FILES.json；均直接从第五轮已验证的所有者状态及模拟器私有评估复制。原始代码c54f890，补充像素重放在第七轮b0a2aba的未改变像素前端上执行，三例Faster R-CNN完整读数均与第五轮逐字段相同，结果及执行脚本SHA见selected-pixel-replay.json。

| 示例 | 实际目标像素 | 同一份原图的检测 |
| --- | --- | --- |
| south_320_missed | 558 | 两前端均无apple候选 |
| south_640_found | 2235 | SSDLite无候选；Faster R-CNN有0.9519及0.6000两个apple候选，至少一框对应目标；仍非实例认证 |
| north_640_wrong_stop | 0 | SSDLite无候选；Faster R-CNN给另一物体apple 0.9209，原闭环因此错误停止 |

每例rgb.npy与envelope.json、raw.json重建公共RGB输入；evaluator_only目录仅供推理结束后核对。infer_public函数只接原图、截止时间、权重和模型类型；不给它掩膜、摆放位置或原有预测。两模型始终读取同一原图。原预测只在新推理后做比较。

在对应仓库根目录和重建的环境中，复制脚本文本到临时路径再执行。必须使用本轮两个官方权重文件；完整矩阵与原始source绑定仍以各轮报告为准。不要把需要其他Torch/前端源码才能成功的重跑冒称原版本一致。

```sh
cp docs/reviews/pc_a/neural_native_loop_2026-09-29/evidence/selected-pixel-cases/replay_selected_pixel_cases.py.txt /tmp/cpswm_replay_selected_pixels.py
OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 .venv/bin/python /tmp/cpswm_replay_selected_pixels.py \
  --directory docs/reviews/pc_a/neural_native_loop_2026-09-29/evidence/selected-pixel-cases \
  --weights-root /path/to/official/torchvision/weights \
  --output /tmp/cpswm_selected_pixel_replay.json
```

此补充不需要启动Unity，也不替代B的独立复核。没有新增独立人类标签、自然接触/人物身份或完整任务成功证据。
