# P1-A — Textbook Contextual Expansion

日期：2026-10-18（Asia/Shanghai）

- Worktree：`/Users/jichengqian/Documents/ChatGPT/texa-p1-a-textbook`
- Branch：`feature/p1-textbook-context`
- Base：`ac071baca0382bdfefece0c1a2b693105dced8a7`（本地最新已记录验证的 Texa_MacOS 提交，含 P0 数学修复；未 fetch 或假定远端更新）
- 原工作区：仍在 Texa_MacOS；未切换、stash、清理、覆盖其未提交修改；没有修改其他 Worktree、合并或 push。
- 改动不涉及依赖、数据库、索引格式或正式教材发布；没有模型请求。

## A–F 链路审查

| 问题 | 代码和实际结论 |
| --- | --- |
| A 原始内容是否完整 | `ingestion/document_ir.py` 的 CanonicalBook/DocumentBlock 已持久化顺序、身份、路径、equations、页码、bbox、review_status；`chapter_splitter.py` 原子保存公式/表格并建立 source_block_ids/locations。结构存在不证明 OCR 正确或原书无缺页。本次不修补 OCR。 |
| B 是否能命中必要原文 | `retrieval_node.py` 已有 KG、向量/词法融合、教学/例题/列表/公式邻接，但选中一个相关 chunk 不等于完整定理或证明。检索后仍可能缺上下文。本次复用命中锚点，不扩书/跨章，不重建检索。三例真实词法探针仅说明这些锚点可读，不是完整混合检索准确率证明。 |
| C EvidencePack 是否裁剪 | 是：默认 9000 字、单条 1800 字、按书/版本/章数量限制。原 Runtime search 回执又按打包后的 chars 切原文。裁剪可丢失定理前提、公式尾部或后续证明。 |
| D 最终模型是否看到完整内容 | 原先不能保证：同步章节讲解还会在打包后执行 content[:6000]。本次把 6000 字教学限制提前到同一打包边界，移除二次切片。测试捕获实际 `llm.invoke(messages)` 参数，检查 QA 三种提示、章节讲解及 Runtime 回执重打包；不是只检查候选召回。 |
| E 公式/图片是否真正进入输入 | 公式正文及单独 equations 字段现在都进入可见文本；表格结构也保留。FigureLearningService 的 asset_path 只证明资源可取，只有 `multimodal_bridge.py` 的已有显式 Figure 路径把 data URL 作为 image_url 发送。本次普通教材展开不额外调用视觉模型，主文本消息仍没有图片像素，故始终如实标 not_read/not_required，绝不把 URL/图注当视觉观察。 |
| F 能否小范围复用 | 可以：新增一个确定性投影模块，复用 Canonical IR、canonical_retrieval_paths、paragraph_title、索引读快照、活跃 manifest 和 FigureLearningService 缓存/受控资源路径；接入既有 Runtime search 与统一生成打包入口。没有新搜索工具、Ingestion 改造、Agent Loop 或数学验证改动。 |

## 实现与取舍

1. `graph/textbook_context.py` 从检索锚点定位同书、同版本、同章节的有界原文章节；证明/解答子标题不被当作安全起点，尽量保留上位内容中的前提。已有 `paragraph_title` 可缩小局部主题，不能仅凭标题推断前提已完整，状态保持 unknown。相同单元的多个命中合并，仍保留 anchor_chunk_ids。
2. Canonical fingerprint、active manifest 和命中 index_version 必须一致；缺 IR、缺块、版本不匹配或无可靠边界时保留原片段并标 unknown。读取全程使用现有 index_read_snapshot，不接触 Chroma 或写索引。
3. EvidencePack 总正文预算仍为 9000，章节教学仍为 6000。展开内容按完整原文块分配预算，允许一单元超过原 1800 字单条限制；不会从中切半个公式/证明块。超出文本预算、128 块扫描上限或 8000 字符来源元数据预算均明确 partial，并保留版本绑定的 continuation。
4. 来源元数据预算服务于现有 Runtime 64KB checkpoint / 128KB 回执限制，不扩大原限制；删除块内重复位置/公式字段，精确位置仍在 source_locations 中。若背景展开挤掉第一检索锚点，则回退原命中片段并标 partial，不能假装恢复全文。没有增加主动读取工具；continuation 当前是内部后续读取锚点。
5. complete 仅指这份版本化 IR 中有明确边界的全部块已进入可见上下文，**不证明 OCR 正确、前提语义完备或答案正确**。`text_status`、`source_status` 与总体 `status` 分开；OCR/MinerU、review_status、源 warnings 或空正文保持 unknown。数值、公式及最终答案验证器未改。
6. 图片分别记录 availability（available/missing/unknown）、required、model_input（not_read/not_required）、原 figure_id、hash、受控 asset_relpath 和页码；校验受控文件、SHA256、图像可解码及像素上限。明确图号只在同章解析；歧义或章外资源为 unknown，不能误报缺失。每单元最多核查 8 个资源，超出仍明确未知并保留下一资源身份。
7. split/native 从已有模型角色配置读取，分别指向 vision/reasoning；没有新供应商判断、额外常规视觉调用或把资源可取升级为模型已读。必要图未读时总体不得 complete。
8. chunk_id 继续指向原**检索锚点**；扩展正文以独立 learning_unit、source_block_ids/locations 和 canonical_hash/index_version 描述，未伪造新索引 chunk。最终 verification_items 直接复用实际可见正文；新增 visible_fingerprint，原 fingerprint 保持兼容。
9. 只把必要的完整度/图片限制送入模型，不把资源路径、hash 或原始块身份放入模型正文。提示要求自然说明影响本题的缺口，不复述内部状态。没有前端改动，不恢复页码/强制引用 UI，既有引用显示策略不变。兼容工具 `backend/tools/learning_tools.py` 的片段输出未扩展，主生成路径和 canonical Runtime 工具使用新边界。
10. Runtime search 工具版本从 1 升为 2，schema 没有改；旧暂停工具合同会被现有版本栅栏拒绝复用，应重新发起问题。没有改写旧任务/学习数据。

## 验证

环境：复用已有 `venv310/bin/python`，实际 Python 3.10.21；命令工作目录均为本 Worktree。没有重装依赖或迁移数据。

- Python 相关回归：**353 passed**，6 个既有依赖弃用警告。覆盖证据、检索、上下文评测合同、视觉服务、SSE、Runtime/原生入口、来源合同、表格、普通 QA 及故障降级。
- 新增 `tests/test_textbook_context_expansion.py`：23 项，覆盖定理前提、多块证明、例题/公式、表格字段、预算 partial、缺图/可取未读/不需要图、split/native、版本/块缺失、OCR、多个锚点去重、三种生成提示、教学实际 6000 字入口、checkpoint 包络、局部标题和命中回退。生成测试捕获真实调用边界的 messages，响应为 stub，不是付费模型验收。
- Electron：`npm test --prefix desktop` **24 passed**；`npm run check --prefix desktop` 通过。macOS 后端构建脚本既有 `--collect-submodules graph` 会包含新增模块；没有改路径、资源配置或桌面启动入口。
- 真实既有教材只读探针：2489 条词法目录、3 问，每问 3 个候选；最终可见正文均与 verification_items 一致，版本/Canonical hash 保留。正文字符数为 1501/2025/2435（含限制提示；不代表语义覆盖分数），存在 partial/unknown，未宣称 OCR 已恢复。Canonical、词法索引、manifest 前后 hash 一致。详情见 `real-corpus-probe.json`，可用同目录 `probe_real_corpus.py` 重跑；无向量重建、Chroma 客户端、trace 写入或模型请求。
- 曾有新增测试把提示中“来源”二字也误判为强制引用；最终改为检查强制引用协议后，完整同批 353 项复验通过。没有用忽略失败或删除测试代替修复。
- `git diff --check` 通过；提交只包含本任务代码、测试、探针和文档。

最终相关回归命令：

```sh
/Users/jichengqian/Documents/ChatGPT/texa/venv310/bin/python -m pytest -q \
  tests/test_textbook_context_expansion.py tests/test_evidence_pack.py \
  tests/test_agent_runtime_textbook.py tests/test_generator.py tests/test_minimal_teaching_prompt.py \
  tests/test_textbook_rag_precision.py tests/test_textbook_generalization.py \
  tests/test_textbook_retrieval_policy.py tests/test_evidence_support_gate.py \
  tests/test_evidence_continuity.py tests/test_textbook_scope.py tests/test_figure_learning.py \
  tests/test_provenance_contract.py tests/test_document_block_splitter.py \
  tests/test_textbook_workflow_repairs.py tests/test_chat_stream_reliability.py \
  tests/test_agent_runtime_chat_binding.py tests/test_agent_runtime_p2a.py \
  tests/test_agent_runtime_p4_contract.py tests/test_agent_tools.py tests/test_answer_verification.py \
  tests/test_context_eval.py tests/test_context_eval_v3.py tests/test_mineru_list_retrieval.py \
  tests/test_table_retrieval.py tests/test_rag_degradation.py tests/test_question_understanding.py \
  tests/test_agent_direct_path.py
npm test --prefix desktop
npm run check --prefix desktop
```

## 验收结论与限制

| 用户要求 | 结果 |
| --- | --- |
| 定理必要前提 | PASS：有界非 OCR 夹具的完整章节前提进入模型；无界/待审来源保持 unknown |
| 多块连续推导 | PASS：原文有序进入最终消息，整块预算策略 |
| 例题及必要公式 | PASS：题干、步骤、公式及字段补全文本 |
| 超预算 partial | PASS：文本/元数据预算与版本化续读锚点；主命中保底 |
| 必要图片缺失不伪造 | PASS：缺失、未读取、可取、无需参与分开；不把文字当图像 |
| 来源版本/原块 | PASS：manifest/Canonical 校验及可见来源列表、hash |
| 普通教材 QA | 相关回归 PASS；三例真实只读上下文探针 PASS，不外推为线上答案准确率 |

**P1-A 最小离线工程验收达到；完整生产教学验收未完成。**

NOT VERIFIED：真实模型是否正确使用上下文、真实视觉理解、完整生产混合检索黄金集、Electron 实机教学/断线恢复、完整安装包。真实教材仍会因 OCR 审阅状态、局部边界、图像未读或预算返回 partial/unknown；本次不能宣称任意定理/证明已完整恢复。不会静默补造，也不会自动启动额外模型读取或付费验收。
