# 三次传感器问答拒答诊断（2026-10-04）

## 结论

三题不是同一种拒答。第一题通过证据门槛后由模型报告证据缺失；第二题先被证据门槛拦截，用户选择学科通用后又被错误沿用的教材提示词限制；第三题在 Resolver 阶段误把题内指代当成历史指代，未进入教材检索。

本次仅检查日志、会话持久化、当前代码和既有索引快照，并做不调用模型的规则复现。未修改业务代码、阈值、教材、索引或用户学习数据，未发起付费模型请求。

## 数据与时间

- 桌面数据根：`/Users/jichengqian/Library/Application Support/kaoyan-assistant-desktop/data`。
- 读取 `progress/rag_traces.db`、`progress/conversations/_conversation_events.db` 的临时副本，并核对 LearningTask 的持久化 execution events。
- 对照 `_lexical_versions/传感器原理及应用/c8b6947edb7858f2.json`；与四次请求记录的 corpus_version 一致。
- 模型：Qwen 3.7 Plus；提示词：`refined-teaching-v1-2026-08-25`。
- 下述时间为北京时间；起止由会话消息时间与 trace 总耗时对应。三题共四次请求，第二题含显式切换模式后的重问。

| 截图 | 请求时间 | 请求 ID | 实际路径 |
| --- | --- | --- | --- |
| 1：电阻式传感器分哪两类 | 19:20:34–19:21:18 | `16dab85e2ea1441b97090d5fc440b9f2` | textbook_grounded → partial → 模型生成 → completed |
| 2：物性/结构/复合分类举例 | 19:18:24–19:18:37 | `bf6688b75ef241e1afb73399003ead4c` | textbook_grounded → insufficient → 固定拒答，无回答模型生成 |
| 2：改用学科通用后 | 19:18:49–19:18:59 | `ca0468450b664ef18182b20979464060` | subject_general → 跳过检索/门槛 → 模型生成拒答 |
| 3：两种材料的特点与场景 | 19:16:44–19:16:45 | `310a9c4cd5ac49db98bfa50d1026f8d0` | Resolver clarify → waiting_for_input，无检索/回答模型调用 |

四条 trace 的 error 均为空，没有记录 API 故障或检索异常。`status=done` 是请求流结束，不表示题目得到正确解答；第三题实际 task 状态是 waiting_for_input。

## 1. 分类问题：所需分类段落未进入本轮证据

第一题的 support_status 为 partial；10 个候选全部进入 EvidencePack，无整条预算丢弃。规划选中第4章与第1章，规划耗时约23.1秒，检索约267毫秒，回答生成约19.9秒，总耗时43.37秒。

模型可见内容包括第1章一般分类、第4章应变式传感器简介、应用，以及压电、电容、动态特性等旁支。它引用 E6 的应变式电阻传感器简介和 E8 的电参量分类，随后说明未见两类分类。这不是后置验证阻断或 support gate 硬拒答。

同版本索引中存在 chunk `ce4ce372a342a11b35a0`，第4章 **4.1.1 电阻应变片的种类**，PDF物理页83，正文明确写道：

> 按应变片敏感栅的材料分类，可分为金属应变片和半导体应变片两大类。

这条不在那次10条证据中；送入的是其上级4.1简介（`2fb9bad416f7a4bfbcba`）。因此“当前提供的证据未覆盖”有依据，但不能推成“整本教材没有”。若用户指的是按应变片材料分类，已有可用教材段落被漏召回/漏选。问题原句没有指定分类轴，仍应保留这一条件，不能直接断言所有电阻式传感器只有这两类。

历史 trace 未保留完整初始候选池，无法进一步确定该段落是在初始召回还是融合/邻接/最终选择阶段丢失。

## 2. 分类举例：门槛误判与通用提示词错误叠加

### 教材模式：确实被证据门槛拦截

trace 明确记录 support_status=insufficient、assembly_mode=grounded_refusal_no_generation。会话正文是 `grounded_failure_message()` 针对 `topic_matched_but_question_focus_missing` 返回的固定文本，说明没有调用回答模型生成该拒答；此前规划模型仍有调用。

6条候选中5条属于1.5“传感器技术发展方向”，1条属于1.2“传感器的分类”（`092af635016a3b4c57e8`）。后者已经包含结构型、物性型、复合型定义及光电管的物性型例子，不能视为完全无相关内容；但这一段也不是用户所需所有器件对应关系的完整证据。

代码定位：`graph/retrieval_node.py` 的 `_extract_query_focus()`（约1200行）会把句首“根据传感器的分类”抽成主题 **根据传感器**，焦点为“分类”。`_assess_evidence_support()`（约1328行）要求主题与焦点在相关证据中匹配；真实分类段落不包含“根据传感器”，反而发展方向段落出现“根据传感器的特性”，错误满足主题条件。

只读规则复现确认：原问句主题为“根据传感器”；只删句首“根据”后主题为“传感器”，分类段落开始通过主题匹配。用历史6条 chunk、固定相同的测试评分元数据，可以复现 insufficient → supported 的变化。

**复现边界：**历史 trace 没有保存 matched_concepts、query_coverage、fusion_sources 等完整门槛输入。该对照使用 matched_concepts=[传感器]、query_coverage=0、fusion_sources=[dense,bm25] 隔离主题规则，不是逐字段重放历史执行，也不证明修改规则后已经具备回答所有对应关系的完整证据。历史拦截阶段与拒答 reason 已由持久化 trace/正文确认；主题抽取错误由当前代码复现确认。

### 学科通用：没有被证据门槛拦截，是提示词仍在禁止模型知识

重问记录明确为 answer_mode=subject_general、scope_reason=requested_subject_general、planner.mode=general_qa_bypass、retrieval.status=ordinary_qa、support_status=not_applicable、assembly_mode=subject_general_refined。模型生成约9.41秒，却答“未提供相关教材证据”。

`graph/generator.py:359` 在 refined preset 下直接调用 compact builder 并传入固定 `REFINED_TEACHING_PROMPT`；虽然 builder 根据模式省略教材证据，却不替换系统规则，也不注入通用模式的 model knowledge 授权。`graph/teaching_prompts.py:16` 仍要求“证据不足时明确说明，不用模型记忆补齐”。

只读构造 subject_general 的实际 system/human messages 已复现上述不一致。通用模板本来允许模型知识，但 refined 分支提前返回，绕过 `_build_generate_prompt()` 中的通用模板。无需把门槛调低，首先应修复生成模式与提示词的契约。

## 3. 材料特点问题：题内指代被误当成历史引用

trace 为 method=unresolved_reference、confidence=0（rule_strength）、resolution_action=clarify、is_followup=true。历史/ledger topic 均为空；检索 action=none、status=clarification、assembly_mode=clarification_no_generation。总耗时30毫秒、首字约9毫秒，符合固定澄清路径。

`backend/services/resolver_reference.py:107` 检测“它”等词后，仅依赖旧 state.topic；没有 topic 就转 unresolved_reference。没有在这一分支优先识别题内“电阻式传感器，**它**……”的明确先行词。`session_context.py` 虽有题内替换能力，但这次无历史分支直接保留原问句，观察器仍将其判作 unresolved_reference。

只读复现：原句得到 clarify；仅把第一个“它”替换成“电阻式传感器”，其余内容不变，得到 identity_no_history / continue。需要先让题内对象正常进入检索，再判断“两种材料”的具体分类是否需要补充。当前笼统要求用户补充“对象名称”，与题目已经给出对象不符。

## 额外问题：完成校验未识别未实质作答

第一题、第二题两次回答的 verification 均为 passed。通用模式只校验 required output 中 kind=content 的正文长度达到4字符（`backend/services/answer_verification.py`），没有识别“学科通用模式因为缺教材证据拒答”这一模式违约；教材拒答的 citation 检查可以记为 not_applicable。

因此界面的“已完成/通过门槛”并不证明用户所问分类、举例、场景已得到回答。这里应增加针对回答模式、应交付内容的有效校验，而不是整体降低现有引用/数值安全要求。

## 建议修复次序

1. 修复 refined/minimal 提示词与 textbook/subject_general/global_general 模式的契约；显式通用模式应允许对应范围内的模型知识。
2. 修复题内先行词的指代判断，保留真正缺历史对象时的澄清门槛。
3. 修复支持度主题抽取的“根据…”污染，并覆盖口语长问句、分类与器件举例的焦点拆分。
4. 改善应变式电阻传感器→应变片材料分类的召回、邻接和证据覆盖；保留分类轴不明确时的必要限定。
5. 补充“模式违约拒答”和所问事实未交付的校验与诊断字段。

以上均为建议，本次尚未实施修复或重跑真实模型。
