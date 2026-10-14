# 问题理解接口适配（2026-10-04）

本次保留原有正则、意图分类、指代解析和受控工具规则；为未来小模型增加可关闭的接口。默认 `off`，未接入真实小模型，也没有付费调用或数据出境。本次完成的是调用契约与主链路适配，不是小模型识别准确率验收。

## 三个接入位置

1. **最终澄清门槛前**：`build_resolution_trace` 先执行规则。未解决指代、低强度意图和句内对象/历史指代冲突才允许尝试理解接口；已明确的规则指代、实体纠正和锁定意图继续优先。接口关闭、未配置、超时或返回非法结构时保留规则结果。恢复 task 使用保存的解析结果，后续 learning bridge 失败不会重复调用理解模型。
2. **当前句内对象识别**：接口输出原问题的字符区间，或 Runtime 提供的有界历史候选 ID。区间必须对应当前原文，候选不能新增。当前对象优先于历史话题；口语比较保留两个对象供后续规则使用。原问题、数值、公式和条件完整保留；澄清不推进 Ledger。
3. **Planner、检索与 Policy 候选生成前**：校验后的白名单意图/维度进入同一 GraphState。Planner 保留强规则意图，检索按维度补充关键词和有界分类召回，分类组贯穿 rerank 与 EvidencePack。练习意图可补充只读 `exercise.inspect` 候选，且由现有工具注册表、范围、输入门槛和预算继续准入；接口不能生成工具名、写操作或扩大教材范围。SSE 与普通问答共用同一准备流程。

## 契约与配置

服务入口：`backend/services/question_understanding.py::understand_question`。生产适配器通过现有 `llm` provider registry/factory 构造独立模型；测试或后续其他运行时可注入 `model_runner(prompt) -> str`。Graph 消费契约位于 `graph/question_understanding.py`，不依赖 API DTO。

模式为 `off`、`shadow`、`fallback`：

- `off`：不构造模型、不发起网络请求，继续规则路径。
- `shadow`：校验输出并记录计数/耗时，不改变解析、Ledger 或候选。
- `fallback`：应用通过校验的对象、指代和意图提示；异常返回规则路径。

配置入口为 `QUESTION_UNDERSTANDING_MODE` 和独立的 `LLM_UNDERSTANDING_PROVIDER / MODEL / BASE_URL / API_KEY`；可用 `CREDENTIAL_ID` 显式选择已有凭据槽。模型名不绑定供应商或模型版本，不加入首次启动必需角色，不默认借用回答模型、凭据或其端点。配置示例已加入 `.env.example`，实际 `.env` 与用户 profile 未修改。

未来使用千问等小模型时，按实际服务名与端点配置；名称可以来自 Ollama tag 或 OpenAI-compatible 服务的模型 ID。这里的可配置性不代表已验证某个模型版本或 0.8B 参数规模的语义准确率。

接口输出示例：

```json
{"action":"continue","intent":"comparison","dimensions":["features","scenarios"],"entity_spans":[{"start":0,"end":7}],"reference_id":""}
```

`start` 含、`end` 不含，按 Python Unicode 字符索引；以上区间须对应实际当前问题。`action` 仅能继续或澄清，其他字段均有白名单/长度限制。不接受自由改写 query、章节名、工具名或 state operation。`intent_locked` 时最终意图由规则决定。

当前生产调用预算：问题不超过 2000 字符、历史候选不超过 12 个、prompt 不超过 6500 字符，一次调用、6 秒 HTTP 超时、无重试、最多 384 输出 token。超过预算、JSON 不合法、实体越界或模型异常均降回规则。日志只记录版本、模式、是否尝试/通过、意图、数量、耗时和固定错误码；不记录 prompt、模型原文、thinking 或供应商异常消息。

## 验证与限制

- `venv310` / Python 3.10：**376 项通过，其中新增接口测试 41 项**。后端回归日志见 [backend-regression.log](validation/question-understanding-interface-2026-10-04/backend-regression.log)，覆盖原有规则、口语表达、当前对象优先、比较延续、非法对象/工具输出、错误脱敏、shadow、恢复幂等、工具与 Policy 门槛、检索/证据和 SSE。
- 真实教材 2489-chunk 词法快照绑定生产 `retrieve_node` 和最终 EvidencePack：原三题以及一个口语材料比较变体均达到 `supported`。口语变体的理解结果由模拟适配器提供；章节范围固定、向量/KG 关闭，因此不是线上小模型、Planner 或回答准确率测评。[检查结果](validation/question-understanding-interface-2026-10-04/real-corpus-offline.json)与可重跑脚本同目录。
- 旧 Policy 数据集扩展检查有 **20 项失败**，原因统一为 `source_content_digest_mismatch`：新适配改动了 `policy.py`、`policy_projection.py`、`router.py`，冻结源码基线仍绑定旧版本。原 6 个 fixture 文件保持 Git 原始内容，未改金标、已批准哈希或绕过校验；该发布评测需对新源码版本重新审阅，当前不能宣布全量发布门槛通过。[冻结门槛记录](validation/question-understanding-interface-2026-10-04/frozen-policy-gate.json)。
- 默认 `off` 供当前 Electron 共用后端使用，未新增依赖、UI 入口、数据库结构或教材索引格式，也未重启用户正在运行的桌面会话。正式开启前需要真实模型的口语改写、错误澄清率、引用解析、条件保持、20/40/80 轮连续性及延迟评测；已有 Context Eval 回归不是小模型准确率证明。
