# Tool Calling Phase 1 交付报告

日期：2026-10-12。Checkpoint：CP1。完整证据见 [现状审计](../../TEXA-TOOL-CALLING-AUDIT.md)。

## 本次修改

- 新增根目录 `TEXA-TOOL-CALLING-AUDIT.md`：记录两条实际主聊天调用链、数学工具覆盖、Provider、Runtime、EvidencePack/Gate、Answer Verification、SSE 与前端展示差距。
- 新增 `tests/test_tool_calling_audit.py`：5 个无费用观察测试；真实 LangChain BaseChatModel 接口经现有 NativeToolAdapter 和 BoundedAgentRunner，完成同 Run 两次真实本地查询与三轮模型响应，直接检查下一轮上下文。
- 本报告与 patch_notes：记录 CP1 与后续验收条件。未修改生产实现、模型角色、环境变量、依赖、数据结构或用户数据。

## 根因与复用结论

已有 SymPy、ToolRegistry、FixedRunner、BoundedAgentRunner、RuntimeStore、受控权限和发布验证均可复用。当前工具未通过主教学模型自主发挥作用，根因不是执行器为空，而是：默认主聊天规则预选工具；数学工具缺 canonical schema 和 Runtime 候选入口；原生消息/调用 ID 在适配阶段丢失；Runtime finish 后另调回答生成；Runtime 流式输出完整缓冲答案；/ask 未走同一 Runtime。

安装的 LangChain create_agent 提供现成循环机制；下一阶段先验证在工具 wrapper/middleware 中委托现有 Runtime，保留 SQL 单一权威。尚未实施该集成，不能宣称 LangChain Agent Loop 已完成。

## 验证

Python 3.10.21，venv310。第一批 54 passed，第二批 114 passed，共 168；git diff --check 通过。只有依赖弃用警告。

新增探针证实：工具结果文本进入后续两轮，两个调用 succeeded，模型计数 3，Run 身份一致；但没有 ToolMessage、没有保留原生 AIMessage.tool_calls、provider ID 丢失。此结果是连接缺口实证，不是完整原生闭环通过。

此外确认：symbolic_math 真输出 1024；其 runtime_metadata 不可用；math.verify 无候选；limit 不支持；概念题不强制计算。既有测试覆盖非法 Python 表面、预算、超时与迟到结果、Runtime SSE投影、教材边界及验证。未做远程或付费模型调用。

## 失败场景与未完成项

daemon thread 超时无法中止 SymPy；错误结果回传语义不完整；复杂/复数/未求值结果及定义域/解集完整性仍需验收。默认生成 Gate 与 SQL Runtime 教材 Gate 不一致，需要在变更前定点明确纯数学和教材事实的输出边界。

Phase 2–5 生产代码、真实 SymPy + 原生两工具三模型轮次、流式参数聚合、同 Runtime /ask parity、取消时运算终止、Electron实际验收与授权后真实模型验收均未完成。本次按“现在先完成现状审计”交付 CP1，不启动付费测试或重大职责重划。
