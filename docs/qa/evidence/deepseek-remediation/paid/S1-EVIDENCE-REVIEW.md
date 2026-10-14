# S1 冻结题面人工证据复核

结论：LIVE-VERIFIED，当前冻结样本通过。不是 LLM 评判，没有额外模型请求。复核依据是 Native checkpoint 中实际 human message 的 `## 教材证据`，保存为 FINAL-VISIBLE-EVIDENCE.md；未借用检索候选中模型未见的段落。

| 原合同 | 本次答案与实际可见来源 | 判断 |
|---|---|---|
| 为什么不能真正静态测量 | E1 明确电荷只能无泄漏保存，实际不可避免漏电；交变力补充电荷。答案解释恒定力不能长期保持输出 | 通过 |
| 大时间常数能测准静态力 | E1 明确准静态应用，E6 明确 RfCf 可很大、低频下限到准静态；E5 给出慢变化及不大时间常数导致灵敏度下降 | 通过 |
| 二者是否矛盾 | 答案区分长期恒定与有限时间慢变，大时间常数降低低频下限而不消除漏电。这是对 E1/E5/E6 的合理推导，未声称教材逐字给出同一解释 | 通过 |
| 给出适合任务 | E9 明确压电式金属加工切削力测量及变化剧烈载荷，答案给出该任务 | 通过 |
| 不补无证据定量截止频率 | 答案没有编造 Hz 值；omega*tau 的 1/3 阈值均来自 E5 | 通过 |
| 教材引用支持结论 | E1/E5/E6/E9 均真实存在且支撑对应段落；Runtime citations passed，unsupported_ids=[] | 通过 |
| 完整正文、不截断、8192实际传递 | output_cap=8192，4337输出=3849推理+488非推理，stop，非空完整交付 | 通过 |
| 正文所有权及状态隔离 | 原始公开正文=SQL task/run/outbox=SSE final；无说明追加。Electron正确渲染，UI单独披露unverified | 通过 |

Runtime 仍 task=degraded / verification=unverified，failures=[]：教学完整性不能仅凭确定性对象出现证明。此人工验收不改写 SQL 验证状态，不称整份回答已获数学 Oracle 验证。

Electron screenshot S1.png 已人工检查，公式及引用渲染正常。完整答案 DOM 文本同时包含标题、状态与正文；状态在独立头部。原始 results.json 的6个 abort_stack 是全局拦截器记录的页面／设置清理调用，未出现 pageerror 或 requestfailed，未中断本次 paid stream。

仅证明这一冻结教材样本通过；不能声称8192能统计稳定地覆盖全部教材任务。S5/S6没有新增付费请求，保持历史LIVE证据 + 修复后FREE回放身份。
