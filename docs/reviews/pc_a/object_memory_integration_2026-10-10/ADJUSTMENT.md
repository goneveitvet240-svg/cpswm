# 开发观测后的单一调整冻结

初版 learned map 使用原ViT-H-14与IoU聚合，原9查询仍身份7/9、位置6/9、联合6/9。两瓶关联正确；Kettle首帧有点，后两帧缺少独立检测，CG只保留旧地图但当前读出UNKNOWN；已有参考特征跟踪能在这两帧恢复正确身份/位置。Bowl首帧位置越界、后两帧无mask的问题不因学习相似度自动解决。

因此冻结hybrid：仅当CG当前没有点时，使用原生产MaskSurfaceSequence同anchor的当前几何支持；CG已有点不替换、无支持保持UNKNOWN、晚生anchor不变成首帧查询。不调阈值、不使用标签择优。初版与hybrid都在原3帧和另一批16历史帧运行；16帧是已开发暴露的同屋复查，不是盲测或跨屋泛化。overlap_aabb实现作为可选研究适配但本轮不根据它的分数选优。原查询分母9保持，额外初始轨迹只作诊断。

## 开发阶段第二次诊断：第一次补回无效，记录保留

上面的missing-only fallback实测仍10/15初始轨迹联合成功、6/9原查询，完全没有触发。最初把两只Kettle混同；核对冻结anchor后发现旧系统修复的是dining-table掩码内Kettle|surface|2|6，而CG整mask最大概率点落在CounterTop|2|0。sink锚点的Kettle|surface|2|5并没有可补回支持。因此不能将不同首帧选点推导的身份直接对比，也不能把mask匹配等同对象实例匹配。

第二版固定为同candidate时保留原参考特征支持点，并仍允许missing-only补回；candidate冲突不替换。原始CG结果和v1无效结果保留。初始轨迹额外评分固定用现有系统首帧点的SDK身份，而非每个方法自己重新定义身份；正式三查询和9槽不变。未读16帧评价分数来制定本调整；16帧v1已运行，只能作为同屋历史复查。

工程问题另记：owner首次试运行在一次次完整source验证中重复散列3.94GB权重，数分钟还没完成第一条指令；中断堆栈确认。改为进程内按device/inode/size/mtime/ctime失效的摘要缓存，worker启动仍独立完整散列。此优化不缓存外部输入的派生语义。完整恶意解释器/进程攻击未覆盖。

## 历史复查发现的执行缺陷

290f629三帧正常/中间撤回/冷启动与运行期helper篡改检查已通过，33项检查通过。5°历史序列frame3触发既有tracker合法输入异常：4个几何核验点中一个浮点光流坐标(0.4009,158.3143)四舍五入到(0,158)，而该处不在mask内；几何过程曾允许选邻近像素，不能据此授权这个tracker种子。

修复保留严格tracker校验，重初始化前过滤实际rounded seed不在mask/图像内的特征；不足4个则UNKNOWN_REIDENTIFICATION_SEED_OUTSIDE_MASK，继续处理序列。既不膨胀mask也不移动特征编号。单独候选修复已完成5帧；下一版本再跑三臂19帧和已接入hybrid的owner，重新绑定源码后做冷启动。

## 最终对照工具修正与完成

hybrid的进程内reference轨迹含tuple，owner JSON持久化后为list，直接Python容器相等曾误报差异。9480c489改为同一canonical JSON散列比较，同时保留原始Python相等值；3前缀均raw_python_frontend_equal=false而规范前端/读出完全相同。修正的是比较表示，不是放宽评分或删除感知字段。最终hybrid正常、撤回和冷启动通过；47项聚焦检查通过。19帧三臂与public-only新worker重跑相同；最终原9查询6/9不变，历史几何39/80→47/80但不能推为实例身份联合收益。
