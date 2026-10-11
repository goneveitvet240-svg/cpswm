# 开发冻结

源码/runner/评分/新增测试51dd6f261aa04249b88dbc56c839fc2f7a67173f。dev7/8/9、3条件、2视图、每视图15候选，共270次实际隔离搜索运行；独立复算通过。三类方法各自开发选择均为sharing2/persistence2，基础alpha0.25/decay0.9固定。完整网格和旧基线保留在freeze.json。

每view384时刻。native最近位置431，旧joint/factor446；所选共享joint/factor/Markov均419，无共享但同持续性joint423。cue_only最近536，旧joint567/factor533；所选joint498/factor497/Markov502；无共享但同持续性joint519。

开发支持共享和持续性可降低检查数，但尚未显示联合胜过同表因子化；保持全部8臂，新留出65001–65010，不看测试调整公式/配置。与PR110使用不同输入身份/seed，绝对计数不能作跨轮因果对照；旧joint/factor在本轮内部真实重跑。
