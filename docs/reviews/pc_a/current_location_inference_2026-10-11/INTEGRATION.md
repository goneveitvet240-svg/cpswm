# 入口、模型与信息边界

入口：`CurrentLocationActionState`包装现有`TaskSeparatedFullJointActionState`；`project_search_input`白名单投影给纯`CurrentLocationBelief`；`execute_current_search`逐次选择/计费D0检查，再调用`consume`和终端`finish`。只在本轮runner opt-in使用，旧默认/生产调用方未迁移。

统计N(s,a,l)=alpha/(A*L)+Σ decay^(age)*1(previous=s)*1(found=l)*cue(a)。当步统计只在完成收费搜索后写入，下一步使用；cue缺失均匀，非人物真值，也非反推后验。该软计数估计不是一个已校准的完整贝叶斯生成模型。表每步由已完成记录重建，alpha为每个前位置行的总平滑量。

joint未观测人物时使用N(s,a,l)归一化；factor使用N(s,.,l)*N(.,a,l)/N(.,.,l)归一化；有actor posterior时以它替换人物边缘一次，保留模型的P(l|a,s)，不把输入posterior当likelihood重复相乘。Markov直接求人物边缘；recent使用可见/最近位置加ID尾序，不宣称校准概率。原可见位置如有则先条件化；之后理想位置检查以1(found与位置一致)更新联合分布。排名以14位舍入处理浮点平手；所有方法同一规则，无留出调整。

支持集沿用既有benchmark已给定菜单。当known_location_ids为空，菜单从全episode可见位置集合构造，因而不是因果发现新地点；只使用支持成员，不使用未来顺序/频数/日期。未来步骤/机制/角色/隐藏真值均不进入位置头；持有UUID仅绑定回执/历史，不作为预测特征。

cue_only诊断只隐藏搜索头位置读数。原生完整框架仍按原观测跑，故其放回动作不能当作cue_only同信息对照。独立计分逐步从白名单重建全部搜索结果，完整入口20条运行与隔离头一致。全部长期习惯/原生隐状态保持，新增人物后验不直接写授权、不传播到原生联合粒子，也未作为下一步人物先验。历史记录目前只用于位置经验统计，不能冒称新位置因素已获得七算子撤回/纠正接口。

检查预算为每步菜单大小，找到停止；全负报告支持耗尽并清空位置记忆，无伪造成功/人物标签。D0环境在记账后访问真值，只返回查询位置found/not_found；代码API隔离，不是敌对Python进程安全或实际机器人执行。理想检测/固定外生轨迹与原人物反馈保持，未实现自然检测、导航、抓取或行动改变下一世界。
