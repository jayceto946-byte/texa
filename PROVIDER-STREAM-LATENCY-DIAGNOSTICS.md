# Qwen3.7 Plus 流式耗时诊断

2026-10-13，已完成用户授权的单次诊断。**本样本符合A：reasoning增量在约2.3–2.4秒开始并持续到达，公开前等待主要与Thinking生成窗口重合；没有观测到几十秒的请求等待或流式静默。50–60 tokens/s仍只是端到端有效平均值，不是decoder吞吐量。** 免费阶段请求0；授权后2请求、8047 tokens、回执估算¥0.042788，无重试。

## 已有证据与实际分解

复查主工作区 `TEXA-AGENT-LOOP-PERFORMANCE-REPORT.md`、逐请求 receipts、Runtime traces、SSE、`llm/factory.py`、adapter、native_loop及实验回调。补充资产尚未提交于共同基线，按只读历史证据使用，未复制其生产代码。源文件SHA-256和全部23条请求的白名单摘录在 [history.json](docs/qa/evidence/provider-stream-diagnostics/history.json)。其中19条有完整回执，4条缺完整usage；中断Run中已返回的请求仍保留，不当作Run成功。

历史计时来源必须区分：

| 时间点 | 现有记录 | 可观测性 |
|---|---|---|
| T0 实际发送开始 | `started_at`/单调时钟起点来自httpx request hook | **真正发送T0 unknown**，hook在连接/传输之前，不冒充发送 |
| T1 响应头 | response hook `response_headers_ms` | 可恢复，但相对request hook |
| T2 首原始provider delta | `first_chunk_ms`来自LangChain on_llm_new_token | **原始T2 unknown**；只能叫首LC callback |
| T3 首非空reasoning delta | 没有记录 | unknown |
| T4 最后reasoning delta | 没有记录 | unknown |
| T5 首过滤后公开content | 回调用ThinkingFilter观测 `first_public_ms` | 可恢复；不是浏览器paint |
| T6 完成/终止 | 正常 `on_llm_end`的`request_ms`/ended_at；失败有错误回执时间 | 正常为上层消费完成；失败未必等于底层worker停止 |
| usage / finish_reason | 每请求Provider回执，包含reasoning计数 | 完整回执可恢复；不按chunk提供准确token计数 |
| 最大原始/reasoning chunk间隔 | 无逐chunk记录 | unknown；SSE正文间隔不包括私有推理 |

以下同一请求内时间都相对历史request hook，单位秒，不把它重命名T0：

| 请求 | hook→响应头 | 响应头→首LC回调 | hook→首公开 | hook→完成 | output / reasoning tokens | output/整体耗时 |
|---|---:|---:|---:|---:|---:|---:|
| Stokes A #1，tool_calls | 1.948 | 0.024 | 55.859 | 58.209 | 3295 / 3163 | 56.61 tokens/s |
| Stokes A #2，stop | 2.935 | 0.005 | 43.136 | 56.494 | 3152 / 2361 | 55.79 tokens/s |
| Stokes D，无工具历史对照 | 2.251 | 0.020 | 74.027 | 95.544 | 5489 / 4219 | 57.45 tokens/s |
| 积分 A #1，tool_calls | 1.950 | 0.018 | 8.329 | 9.529 | 448 / 371 | 47.02 tokens/s |

19条成功请求的hook→响应头为1.777–3.691秒；响应头→首LC回调为2.83–23.65毫秒。Stokes A两次请求的响应头前等待合计约4.883秒，占请求总时间114.703秒的约4.26%。首轮**首LC回调→首公开空窗53.888秒**，第二轮40.195秒。长公开空窗不是“50秒未收到任何响应”；但首LC回调可能只是空role/协议块，不能由此证明reasoning已经开始。

旧Run模型envelope占99%以上，只定位到请求区间，不能把这个比例全归为推理。公开SSE不传私有reasoning，公开事件空窗也不能证明网络没数据。新旧批次不作因果优化对照。

## 新增最小计时能力

新增可选同步适配器 [provider_stream_timing.py](scripts/diagnostics/provider_stream_timing.py)，只在隔离实验显式构造 `DiagnosticChatOpenAI` 时生效；生产factory/adapter/native_loop无任何修改，无全局monkey patch、数据库字段或SSE变化。

专用httpx.Client挂 `probe.request_hook/response_hook`；模型传 `timing_probe=probe`。继续原有ChatOpenAI参数、bind_tools、回调与AIMessage/ToolMessage转换。它在SDK解析后、LangChain丢弃额外字段之前旁观provider delta，调用原始转换并原样yield。新增字段仅在probe内存records中；实验结束后只序列化该白名单。不自动发请求、不自动写日志、不包含网络runner或凭据。

- **T0**：httpcore `send_request_headers.started` trace，表示传输层开始发送headers的客户端边界；不是网卡发包/服务器收到时刻。无trace则null。连接、DNS、TLS可能在该边界前，时间均相对本次适配器开始的monotonic原点。
- **T1**：专用HTTP响应头hook。没有保存headers正文、URL或密钥。
- **T2**：首SDK解码的原始provider delta，在LC转换之前。**不是首socket字节**，含SDK解析/可能缓冲；JSON/HTTP帧边界无法当解码token边界。
- **T3/T4**：非空 `delta.reasoning_content` 首/末；独立计数/最大间隔，不保存文本。T4只有完整消费且有终止finish标识才发布，异常/取消/无终止标識时null。
- **T5**：原LC转换结果经独立ThinkingFilter旁观过滤后的首非空文字；不改实际过滤器或正文。
- **T6**：SDK/LC流完整消费或异常退出边界；不是Provider内部停止或Runtime超时的瞬间。consumer backpressure也可能影响消费时间。

记录每次请求的times、SDK/reasoning/public chunk计数、两类最大静默间隔、整数usage、HTTP状态、白名单finish_reason与终止类别。正常完成、工具交接、截断、过滤、timeout、connection failure、consumer close、RuntimeConflict取消和协议不完整分别表示。caller deadline与迟到worker流结束必须分开，探针不改变Runtime超时/取消合同，也不提前把worker标成完成。异步/Responses/beta结构化流不在此同步Chat诊断支持范围。

免费检查发现安装的 `langchain_openai.chat_models.base._convert_delta_to_message_chunk` 会保留tool_call_chunks和content，**不保留reasoning_content**。因此现有LC callback看不到该字段，并非已经证明Qwen Provider不提供它。官方[Chat流式合同](https://help.aliyun.com/zh/model-studio/qwen-api-via-openai-chat-completions/)定义reasoning_content增量；实际请求是否发送需原始delta观察确认。

离线测试使用httpx.MockTransport和真实SDK/LC解析，零外网，Python3.10/venv310，**7 passed**。验证reasoning/content交错、T5先于T3、每请求独立、原生工具ID/内容原样、think跨块过滤、usage、timeout/connection error/取消关闭、无reasoning/无trace的null、截断、EOF不完整、确定性10秒静默间隔，以及序列化不含私有文本。它证明观测合同，不证明真实Provider时序或性能。安装SDK版本保存在history.json；适配器旁观的是私有转换方法，版本升级需重跑这些离线检查。

## 核心判断与不可观测部分

数千输出tokens与约56tokens/s的历史有效平均值，在量级上足以与近一分钟请求时间相容；**这个平均值本来就是tokens/耗时，不能再用它“证明”耗时原因**。较大reasoning占比与公开前长空窗支持Thinking生成是主要候选解释；响应头前等待只有几秒，已观测的请求前阶段不是主要部分。

授权前仅凭历史不能选定A（reasoning早开始且稳定），也不能排除C（中途静默）。B中的“首原始/reasoning长等待”未知，但“几十秒才有响应头”不符合这些完成样本。D不能表述为Provider不暴露：准确说法是**历史LC层没记录、且转换丢弃reasoning字段，具有D式可观测性限制**。

历史中仍unknown：首字节/原始delta精确时间、reasoning首末及持续性、Provider排队/Prefill内部时间、网络与服务端buffer分别占比、逐chunk真实token数量。即使本次T3/T4完整，reasoning_tokens/(T4-T3)也只能是客户端窗口比值，不能叫精确decoder吞吐量；流式批处理、首块生成前时间和SDK消费都会影响它。

## 已授权的最小验证计划

**最值得做的下一项是一次原始reasoning delta连续性观测，先定位瓶颈，再决定模型侧措施。** 当前不建议SSE/前端/毫秒级Runtime优化；没有证据表明它们能消除50秒空窗。不开展Prompt或模型对比。

如用户授权：复用历史Stokes A完整冻结题面及required outputs（本轮不简化题目或提供oracle），Qwen3.7 Plus北京、现有Thinking开启、temperature=0、auto原生Tool Calling、parallel_tool_calls=false，同实际历史16384总输出额度。一次Run，预计2请求，**最多3模型请求/2工具**；零重试，不重跑失败，不改变生产默认。隔离目录拟 `/private/tmp/texa-stream-diagnostics-<run-id>`，专用SQL/日志，单Runtime，无其他QA服务共享数据；无需开Electron或改变端口，沿现有stream_run消费。仅专用model factory注入诊断模型/HTTP客户端，不编辑共享生产文件；执行前冻结模型配置、代码/题面hash及预算guard。

预算：每次请求实际UTF-8字节≤25,000，累计≤75,000，按同地域输入token保守上界预检；3×(16,384+10)=49,182输出tokens（含推理），总上限124,182。按[官方北京≤256k价格](https://help.aliyun.com/zh/model-studio/qwen3-7-plus)输入¥2/输出¥8每百万tokens、不计缓存优惠，最坏预留 **¥0.543456，硬费用上限¥0.60**。发送前保守预留，缺usage不释放；端点/阶梯/token上界不符先停止重新预算。保持原生协议，最多3次是整题Loop上限，不为诊断加一次请求。临时配置只绑定隔离对象。

用户随后明确回复“授权”，按上述边界执行且未扩展实验。结果如下。

## 授权实测结果与限制

[逐请求T0–T6](docs/qa/evidence/provider-stream-diagnostics/authorized/timings.json)、[用量与费用guard回执](docs/qa/evidence/provider-stream-diagnostics/authorized/ledger.json)、[分段汇总](docs/qa/evidence/provider-stream-diagnostics/authorized/summary.json)、[冻结题面/代码身份](docs/qa/evidence/provider-stream-diagnostics/authorized/manifest.json)。T0为httpcore发送开始trace，T2为SDK解析后原始delta，均不是网卡/服务器内部时刻。以下单位秒；“适配器”是每请求monotonic原点。

| 请求 | T0→T1 | T1→T2 | T2→T3 | T3→T4 | 适配器→T5 | 适配器→T6 | 推理Chunk数 | 最大推理静默 | 输出/推理tokens |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| #1，工具交接 | 1.376 | 0.0167 | 0.0032 | 27.645 | 29.941 | 31.242 | 440 | 0.254 | 1707/1628 |
| #2，最终消息stop | 1.320 | 0.0016 | 0.0026 | 26.347 | 28.868 | 49.132 | 424 | 1.076 | 2742/1549 |

T3相对适配器开始分别2.290/2.419秒，SDK总Chunk数461/747。T5在T4之后；原始reasoning确实可见，LC现有转换将其丢弃，诊断旁观没有改变该行为。两请求完整消费，T4有效。最大SDK间隔也分别0.254/1.076秒，没有长达几十秒的中途停顿。

请求模型适配器总区间80.375秒，reasoning首末窗口合计53.992秒（约67.2%）；公开前空窗与这些窗口大体重合。适配器开始到首推理合计4.709秒（约5.9%）；第二请求之后还用约20.367秒生成公开内容/流尾，不能把整题80秒全部算Thinking。适配器起点→T0的0.895/1.095秒包含客户端准备/连接相关区间，不能单独叫TLS或排队。HTTP发送→响应头合计仅2.696秒。

输出tokens/(T6−T0)为56.248/57.080；以适配器整体时间为分母则54.637/55.808。这与历史50–60有效平均值相符，连同持续reasoning到达证据，支持生成阶段主导本样本等待。**不计算或宣称精确reasoning decoder速度。** 单样本不能解释历史所有慢请求，也仍无法拆分服务端调度、Prefill、批量发送与网络各自占比。

实验操作问题必须保留：首工具的隔离进程重新导入入口脚本时，因初始脚本缺少multiprocessing main guard而退出，工具回执为`worker_failed`。这是本次harness错误；已补入口保护并离线确认spawn导入不运行主流程，**没有重跑付费请求或工具**。第二模型实际收到失败ToolMessage并完成流；Run最终degraded，1工具失败，墙钟80.924秒。不能用整题时间比较历史正常工具Run，也不声称本次最终答案质量通过。原始启动脚本hash未及时冻结，保留unknown；交付的是加保护和显式授权开关后的runner，hash另记，不能冒充初始启动版本。

实际输入3598、输出4449（含reasoning3177），总8047 tokens，发送12665 UTF-8字节。2请求均有完整usage，估算费用¥0.042788，低于3请求/¥0.60授权上限；不是账单结算。测试期间所有模型/Runtime来自只读源代码的独立快照，数据位于`/private/tmp/texa-stream-diagnostics-20261013-authorized`；未启动共享服务、未修改生产源/模型参数。诊断交付只有数值/协议数据与公开题面；不复制SQL、原生消息或私有推理正文。

后续优化重心应放在**模型侧必要生成量与耗时**，结合已有A主线质量证据决定是否调整思考预算；本次不实施参数优化、不新增实验。SSE/前端传输优化不是本样本的优先方向。残余1秒级停顿值得保留为观察，不能当作几十秒等待的主因。

## 交付身份

复用既有干净B Worktree `codex/agent-early-output`，本轮父Commit `5a05d2415db0bf38c02a15766a4676520fcf19a3`；共同基线仍为 `f91633673c40cf9c353e49804e2584b64f3131cc`。免费阶段新增此报告、history.json、隔离诊断适配器与测试；授权后补充白名单实测资产与独立runner；不改主工作区/其他分支未提交成果，不合并。最终提交Hash见Git记录与回复。
