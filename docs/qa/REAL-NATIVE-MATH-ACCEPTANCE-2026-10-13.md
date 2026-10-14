# 真实模型数学工具验收与无工具对照

2026-10-13，用户明确授权真实调用，随后将范围扩为三道复杂考研数学题、一道难度相近的无工具题，并要求开始/过程/完成截图、耗时、token 与正确性统计。

结论：真实 Qwen 3.7 Plus 经现有主聊天、LangChain create_agent、SQL Runtime、隔离 SymPy、SSE 与 Electron 开发壳完成原生多轮调用。第二题满足三轮模型/两次真实工具/最终回答的完整闭环。数学结论与交付完整性仍有缺陷，不能把执行链通过当作教学答案全部验证通过。

## 条件与预算

- 使用已配置的 Qwen 3.7 Plus 北京端点，temperature=0、保留思考模式、零自动重试。没有改动凭据或生产学习数据。
- 三道工具题与对照来自[大学公开的 2024 数学一 PDF](https://edu.xaiu.edu.cn/__local/2/44/D5/335CC768F01FC88CDE7A9F247F4_7E8D3961_4C7E6.pdf)，核对 PDF 图像后合并其拆分小问，追加“说明过程”、最小 MSE、n=0 等验收要求。题面及来源在[questions.json](evidence/native-tool-loop/paid-2026-10-13/extended-deadline/questions.json)。未把来源网页答案提供给模型。
- 真实 macOS Electron 开发壳；FastAPI、SQL Runtime、SSE、SymPy 与前端均真实。数据和会话独立存于 `/private/tmp`；不访问用户教材、学习历史、错题或正式会话。
- 每题 SQL 预算最多 5 轮模型 / 3 次工具；无工具对照是 1 轮模型 / 0 次工具，实际 Provider payload 删除全部工具定义及 tool_choice。对照复用同一教学模型、问题装配、Runtime 和最终验证。
- QA 进程将输出额度扩大为 `max_completion_tokens=16384`，含思考和回答；不是先前建议的 1024 token。官方说明该参数包含思维链与回答，最多存在 10 token 误差。[参数文档](https://help.aliyun.com/zh/model-studio/qwen-api-via-openai-chat-completions/)
- 费用硬上限 ¥1：每次发送前，以实际 UTF-8 请求字节数作为输入 token 保守上界、16384+10 输出 token 预留最坏费用；回执后按 usage 释放预留。失败且无用量回执不按 0 费用计算。按[北京官方输入 2 / 输出 8 元每百万 token 定价](https://help.aliyun.com/zh/model-studio/qwen3-7-plus)估算；忽略缓存优惠，账单仍以供应商为准。
- 总共 **11 次远程请求，58,222 tokens，估价 ¥0.367214**，包含所有先前超时/失败。没有自动网络重试、强制 tool_choice、模型回答夹具或模拟执行器。

## 完成时间、用量与正确性

耗时为 SQL Run 创建到终态的时间；UI 端提交到结束的墙钟另记在 metrics.json。Token 为供应商 usage **实际回执**，含思考 token、工具 schema、消息历史和工具结果；优先使用回执，不凭字数猜测。

“分项正确率”是本次独立核对的六项 rubric，包含推导与必要交付项；不是正式阅卷分数，也不是 Runtime verified。每项等权。无法完成的超时试验另列，未从记录中删除。

| 题目 | 条件 | Run 耗时 | 输入 / 输出 tokens | 总 tokens | 模型 / 工具 | 正确性及完整性 |
|---|---|---:|---:|---:|---:|---|
| 多元函数、切平面、闭区域最值 | 工具可用 | 109.569 秒 | 3,357 / 6,125 | 9,482 | 2 / 1 | 6/6，100%；完整正确 |
| 空间曲线积分（Stokes） | 工具可用 | 190.236 秒 | 5,384 / 10,789 | 16,173 | 3 / 2 | 5/6，83.3%；最终值正确，半径表述错误 |
| 次序统计量、无偏与 MSE | 工具可用 | 52.486 秒 | 3,417 / 2,731 | 6,148 | 2 / 1（失败） | 5/6，83.3%；最终值正确，独立答案缺分布推导 |
| 三维递推与矩阵幂 | **完全无工具** | 130.776 秒 | 628 / 7,551 | 8,179 | 1 / 0 | 6/6，100%；完整正确 |

三道工具题的最终主要数值/公式均正确（3/3）；按完整且没有推导错误的严格标准，只有 1/3 完全通过。分项合计 16/18（88.9%）。无工具一题为 6/6，但三题与一题不是同题随机配对，无法由此推断“工具提高/降低正确率”或普遍速度优势。第三题虽处于工具可用组，实际计算失败后主要由模型手算，不能当作工具成功带来的收益。

统计文件：[工具题及首次无工具超时 metrics](evidence/native-tool-loop/paid-2026-10-13/extended-deadline/metrics.json)、[完成的无工具对照 metrics](evidence/native-tool-loop/paid-2026-10-13/no-tool-completed/metrics.json)、[工具题逐项评审](evidence/native-tool-loop/paid-2026-10-13/extended-deadline/independent-review.json)、[无工具逐项评审](evidence/native-tool-loop/paid-2026-10-13/no-tool-completed/independent-review.json)。

[独立离线 SymPy 核对记录](evidence/native-tool-loop/paid-2026-10-13/independent-oracles.json)保存驻点/边界值、球面展开残差、投影被积函数、矩与 MSE、矩阵谱投影及模型矩阵的零残差；没有把这些答案提供给被测模型。

## 真实闭环证据

第二题 Run `arun_44e029ffe88c4fd1a9233f4c4d6c8f6e`：

```text
LLM #1
  → symbolic_math(calculate, pi*(2/5)*(2/sqrt(5)))
  → ToolMessage(call_406c5b4970694488ad30ad65)，真实精确结果
LLM #2（上下文含前一 AIMessage 与匹配 ToolMessage）
  → symbolic_math(simplify, 4*pi/(5*sqrt(5)))
  → ToolMessage(call_1317f959ba1f427796f3ee03)，真实精确结果
LLM #3（保留两组原生调用与结果）
  → 最终教学答案，积分值 4*sqrt(5)*pi/25
```

SQL 原生消息顺序是 `system, human, ai(call), tool, ai(call), tool, ai(final)`，两次工具均 succeeded。SSE 收到三轮真实 model started/completed、两轮 tool requested/started/completed，以及 **254 条 output_delta** 和终态事件；原生 ID 一一对应，没有用字符串摘要继续模型。

[完整 SQL / 原生消息 / 工具回执](evidence/native-tool-loop/paid-2026-10-13/extended-deadline/runtime-traces.json)与[Electron SSE 记录](evidence/native-tool-loop/paid-2026-10-13/extended-deadline/electron-results.json)保留实际过程。第一题是一工具两模型；第三题工具因 `theta` 不在解析白名单返回错误，错误作为 ToolMessage 返回同一模型，模型自主选择手算后结束。无工具对照的[Runtime 轨迹](evidence/native-tool-loop/paid-2026-10-13/no-tool-completed/runtime-traces.json)与[Provider 用量回执](evidence/native-tool-loop/paid-2026-10-13/no-tool-completed/provider-receipts.json)证明实际 `mode=no_tools`、工具调用为 0。

## 截图

开始是发送前的完整题面，过程是请求运行中或答案增量正在生成，完成是终态后的页面。四题的截图均真实捕获，没有拼接、伪造进度或替换模型答案。

| 题目 | 开始 | 解答过程中 | 完成 |
|---|---|---|---|
| 最值 | [开始](evidence/native-tool-loop/paid-2026-10-13/extended-deadline/q1-extrema-start.png) | [正文增量](evidence/native-tool-loop/paid-2026-10-13/extended-deadline/q1-extrema-answer-progress.png) | [完成](evidence/native-tool-loop/paid-2026-10-13/extended-deadline/q1-extrema-complete.png) |
| 曲线积分 | [开始](evidence/native-tool-loop/paid-2026-10-13/extended-deadline/q2-stokes-start.png) | [正文增量](evidence/native-tool-loop/paid-2026-10-13/extended-deadline/q2-stokes-answer-progress.png) | [完成](evidence/native-tool-loop/paid-2026-10-13/extended-deadline/q2-stokes-complete.png) |
| 统计估计 | [开始](evidence/native-tool-loop/paid-2026-10-13/extended-deadline/q3-estimation-start.png) | [正文增量](evidence/native-tool-loop/paid-2026-10-13/extended-deadline/q3-estimation-answer-progress.png) | [完成](evidence/native-tool-loop/paid-2026-10-13/extended-deadline/q3-estimation-complete.png) |
| 无工具递推 | [开始](evidence/native-tool-loop/paid-2026-10-13/no-tool-completed/q4-no-tools-start.png) | [正文增量](evidence/native-tool-loop/paid-2026-10-13/no-tool-completed/q4-no-tools-answer-progress.png) | [Electron 完成](evidence/native-tool-loop/paid-2026-10-13/no-tool-completed/q4-no-tools-complete.png) / [只读恢复后末尾结果](evidence/native-tool-loop/paid-2026-10-13/no-tool-completed/q4-final-results-restored.jpg) |

无工具长矩阵使完成时的 Electron 视口停在中段，因此另用禁止外部连接的 QA 服务、相同持久化答案，在内置浏览器只读恢复并点击“回到最新回答”，补充末尾结果截图；没有再次生成或付费。长连乘矩阵出现横向滚动，列为后续排版问题，没有声称复杂公式所有尺寸无溢出。

## 失败证据与局部修复

1. **35 秒旧等待预算**：前两题分别约 35.369、35.055 秒终止，第三题约 0.029 秒因前两 worker 未释放而失败；三题都没有权威最终答案。[初次完整记录](evidence/native-tool-loop/paid-2026-10-13/runtime-traces.json)。后续收到的两个 usage 合计 10,186 tokens，估价 ¥0.06341；首次夹具对重叠迟到回执按最近 pending 请求归属，单题归属不可靠，只使用合计，不伪造单题 token 数。后续按 worker thread 关联回执，已修正夹具。
2. **120 秒无工具等待预算**：Run 120.039 秒终止，模型约 128 秒后才完整返回；可见部分推导没有完整 An / 递推 / n=0，不能认定完成。8,054 tokens 和费用全部计入总量。扩至 180 秒后单独重做一次无工具题，130.776 秒完成；两次都保留。
3. **等待与取消修复**：native 数学默认模型等待改为 180 秒 / Run 600 秒，支持 `TEXA_NATIVE_MODEL_TIMEOUT` / `TEXA_NATIVE_RUN_TIMEOUT`，分别硬上限 300 / 600 秒。新 Run 在 checkpoint 冻结这两个值；恢复不因环境变化重置预算。旧 checkpoint 没有该字段时沿用旧 35 / 120 秒。非数学兼容路径仍为 35 秒，不扩展开放式 Agent。
4. **实际迭代停止**：Run fence 改用复制模型的 constructor callbacks，避免 bind_tools 丢失 RunnableBinding 配置；不修改共享缓存模型。新增真实 LangChain 流回归：收到首个文本后停止 SQL Run，后续 token 迭代必须提前停止，而非仅隐藏迟到内容。模型 deadline / worker capacity / adapter failure 使用独立错误代码。等待时间增加仍受取消、Run 总时长与数量预算约束。

## 独立评审、验证状态与遗留问题

- 最值题：切平面 x+y+z=3；D 是第一象限 x+y≤3；最大 21，最小 17/27，驻点与边界均正确。
- 曲线积分题：独立展开球面应是 `(x-1)^2+y^2+z^2=1`。模型错误写为 2 / 半径 sqrt(2)，但后面从原始方程正确计算投影椭圆、方向、旋度和积分值。这一真实推导错误没有被两次面积/化简工具调用发现。
- 统计题：E(max)=n*theta/(n+1)，二阶矩 n*theta²/(n+2)，无偏 c=(n+1)/n，最优 c=(n+2)/(n+1)，最小 MSE=theta²/(n+1)²，均正确。但 CDF 推导只在工具调用前 AIMessage 中出现；该段展示增量在工具阶段被 replace 清除，最终独立答案没重述，留下交付缺项。这是过程与最终答案连接的实际缺口，不能忽略。
- 无工具题：独立 SymPy（离线评审，未接入被测模型）验证 A 的特征值 0,-2,1；n≥1 时 An=投影矩阵 P1+(-2)^n*P(-2)，向量为 (8+(-2)^n,-8-2*(-2)^n,12)，n=0 单列原初值，答案一致。
- 三道工具题 task 都为 **degraded**，不是 verified。现有 required outputs 的字面 anchor 检查会误判正确推导缺失；数学最终绑定也保守。无工具题为 unverified / degraded。没有为测试变绿而放宽 Gate、修改批准 pins 或把工具成功当作最终准确性证明。
- 待修复：canonical schema 应明确表达式允许的符号/函数及参数改名合同；最终答案必须完整重述必要前置推导，不能依赖已清除的 interim 文本；复杂数学 required outputs 的 anchor 误判需要定点修复和评测；长矩阵排版需单独验证。未重构 Gate，未调用 Policy 小模型。

代码回归：最终数学/原生/恢复/验证/SSE/事件相关 **93 passed**；包括预算上限、恢复时冻结配置和绑定后取消停止迭代。明确排除三个旧 Policy 冻结源码身份文件后，**1379 passed**。无模型测试费用；旧 Policy 批准源码身份失效仍保留，不声称通过旧全量发布评测。无 Windows 正式安装包或真实付费供应商取消专项验收。
