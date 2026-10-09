# Fixed deterministic fixtures — Spec V0

These are implementation-authored, independently reasoned fixtures, not human-adjudicated locked gold.
No Rule/teacher prediction was used to fill labels. No production reachability/answer-quality claim.

- direct@v0: 概念问答无记录查询或教材要求，可以直接解释。
- input-gate@v0: 附表缺失且影响精确结果；pre-SQL gate 应等待输入。
- textbook-needed@v0: 当前无教材证据，唯一合法下一步是同范围检索。
- textbook-empty@v0: 同轨迹检索成功但零证据，grounded 不允许通用生成且 V0 不重试；合法零候选。
- progress-needed@v0: 用户要求当前记录，未查之前回答在 Runtime 可准入但语义上过早。
- progress-done@v0: 查询已完成，有界摘要可支持披露覆盖限制的回答；不重试。
- multi@v0: 两个查询都是所需任务的合法第一步，无依赖先后；回答过早。
- lexical@v0: 强词法匹配不能覆盖明确否定；工具不获取必要事实，直接解释。
- resolved@v0: 显式纠正与 resolved query 指向进度，旧习题对象不可继承。
- goal@v0: goal 明确当前任务只解释统计含义，无需查询个人记录。
- optional@v0: 已有信息可解释方法；用户允许查询改善覆盖，工具与答案均可接受。
- exercise-empty@v0: 已查同范围题库且为空，可如实说明无匹配，不能临场编题。
- failed-allowed@v0: 工具失败允许明确披露无法读取当前记录；不伪造查询结果。
- unknown-forbidden@v0: 教材查询状态未知，不能当成功、重试或给教材事实；合法 Runtime 零候选。
- scope-defect@v0: 故障注入：工具 book_name 绑定到 other-book，与冻结范围 fixture 不同，整条退出选择分母。
- missing-defect@v0: 故障注入：预算及权限足够却遗漏必要查询，不是合法 Runtime-only。
- pending@v0: 未独立审阅，未知 gold 必须为 null，不填写默认答案。
- insufficient@v0: 指代对象及关键覆盖信息缺失，Observation 不足以区分下一步。
