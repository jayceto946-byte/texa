# 本轮集成发现

## D-01 — 教材例题的解答混在题干（P2，独立解析待办）

状态：OPEN；观察结果 FAIL（结构化分离），正文保真/显示结果 PASS。不是本轮UI回归。

复现：对真实桌面教材 Canonical IR 的隔离副本调用 `/exercises/textbook-analyze`，`use_llm=false`，打开首个例题候选。完整题干中仍包含“解:”及推导，而答案字段为空。真实私有截图位于 `artifacts/r1-r2-post-approval/real-copy-verified/electron/1280-real-candidates.png`，不提交教材内容。

根因范围：`LearningUnit.text` 有意合并完整 stem/solution/formula/table/figure 来源单元；`memory/textbook_exercise_importer.py::analyze_learning_unit_candidates` 把 `unit['text']` 整体交给规则分析。该层在 checkpoint 前就存在，本轮未改。现有规则不能保证按题干/答案/解析划分，候选必须人工校对。不能为了让空答案变绿而截断“解”后的内容，否则会误切题干条件/子问并丢公式。

最小后续方向：保留完整来源单元和块身份；用 Canonical 角色/明确解答边界提议结构化分离，对歧义只告警；人工能把解答移到答案/解析，且可对照完整原文。先建立同书例题、跨页、多小问、表格/公式/图片与“解”字属于题干的回归样本，再实施。禁止新增未授权模型调用，不改索引或数据库。涉及 textbook_exercise_importer、exercise_importer、候选校对合同及测试。预计2–4工程日，取决于原IR角色可用性。与F2无强依赖，导入前人工校对仍是门槛。

验收：原始块不丢；明确边界样本正确分离；歧义保持整单元且可审阅；题干不泄漏解答；来源页/块一致；人工入库内容准确。108候选中93条有需注意项、16条与已有题重复，这些统计不等于解析准确率。

## B-01 — 完成会话与最近一轮摘要

状态：OPEN / 低优先级；持久化与完成反馈 PASS，额外“上轮完成”摘要不稳定。

`usePracticeSession` 在提交完成后刷新 overview；后端仅返回active/paused会话，因此清掉前端 completed 投影。当前“本轮完成：…题”反馈及记录/统计正常。逻辑在R1/R2前已存在，不能靠Fixture返回completed假装真实overview保留最近会话。若产品需要稳定“最近一轮”，增加明确只读查询/投影合同；不把已完成会话伪装为active，不用本地闭包覆盖另一范围的会话。

## 测试环境问题（C，已关闭）

保留原始失败日志于 ignored `artifacts/r1-r2-post-approval/`：Fixture漏remote-ready；隔离health/config门槛；学科选择/隐藏公式/完成文案断言；快照漏mistake_book；真实action回执形状；原生dialog竞态；重复运行触发真实去重；剩余未提交候选阻止整页卸载。后两者本身是正常保护，测试须明确处理，不能改产品绕过。最终完整四库API与Electron复跑通过。
