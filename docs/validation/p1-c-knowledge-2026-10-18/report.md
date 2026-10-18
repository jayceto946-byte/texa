# P1-C：题目知识结构与作答证据诊断

2026-10-18。独立工程合同验收通过；真实 LLM 分类与错因判断质量 **NOT VERIFIED**。不将确定性/夹具结果表述为模型准确率。

## Git 与隔离

- 主仓库：`/Users/jichengqian/Documents/ChatGPT/texa`，原分支 `Texa_MacOS`；开始时有候选题合同与 UI 等未提交工作，未复制、覆盖、清理或切换。
- Worktree：`/Users/jichengqian/Documents/ChatGPT/texa-p1-c-knowledge`。
- Branch：`feature/p1-knowledge-structure`。
- Base SHA：`ac071baca0382bdfefece0c1a2b693105dced8a7`。采用主目录最新已提交的集成基线，其 patch_notes 记录已有运行与测试验收；不把未提交候选题工作当作稳定基线。
- 不修改 P1-A/P1-B，不自动合并 master 或 Texa_MacOS，不推送。最终提交 SHA 由交付消息及 `git log -1` 给出。

## 已审查的数据链路

| 链路 | 原有结构 / 本轮判断 |
|---|---|
| ExerciseRecord / ExerciseBankStore | 现有 SQLite `data` JSON、subject/chapter/question_type/tags、linked_concepts、practice_history；保留所有存储与查询主干 |
| MistakeRecord / MistakeLifecycleStore | 现有内容/诊断状态、content_revision、source_ref、独立 occurrence/redo attempt、CAS 与幂等回执；诊断直接扩展 attempt.data，不新增表 |
| KnowledgeGraph / ConceptLinker | 预构建 KG 有 concept_id、canonical_name、aliases、roles、occurrences 与章节映射；旧启发式名称标签不是已验证知识身份 |
| exercise_importer / textbook_exercise_importer | 现有 ExerciseCandidate、题型与启发式标签；可保持空/未分类，不因标签为空阻断合法习题，不新增第二套候选结构 |
| 练习创建、直接作答、会话作答与转错题 | 保留 operation_id、session/exercise 来源及 mo_/ma_ attempt 身份；原始作答仍由既有流程冻结 |
| 错题讲解、学习摘要、薄弱查询、复习 | 检查关联→ConceptMemory→weak-points→KG摘要→页面计量全链路；修复自动弱项传播，SM-2 算法与练习/重做评分保持原实现 |

额外只读检查了主目录 `docs/validation/question-candidate-contract-2026-10-18/implementation-report.md` 及其登记内容：108 题差分、题干/答案/解析分离、人工校对和候选回执目前在主工作区未提交。本轮不复制其实现；正式记录新增的可选 `knowledge_structure` 不改变 Candidate 或批次回执。合入时需与该任务核对共享文件 `memory/exercise_bank.py`、`backend/api/exercises.py`、`backend/schemas.py`、`patch_notes.md` 的重叠，不能直接整文件覆盖。

## 最小合同

`knowledge/exercise_structure.py` 提供严格 Pydantic 输入合同（拒绝额外字段），Runtime 保存显示名称及来源：

- `knowledge_structure.schema_version=1`；primary（可空）、related[]、theorems[]、properties[]、domain、question_type 分开；各项 basis、整体 basis/uncertainty 独立保留。
- `status=proposed/unknown/unclassified`；题目改动标记 stale。分类始终 `verification=unverified`，不作为答案验证结论。
- `scope={book_name, book_id, kg_version, chapter}`；旧记录没有 book_id 时仍由 book_name 命名空间隔离。同名、甚至相同裸 ID，不跨教材或 KG 版本合并。
- KG 版本来自实际 concepts/occurrences/meta/章节映射的 SHA-256；题目版本来自精确题干、教材身份、学科、章节、图片/visual_ir 的摘要。模型不能提供或改写这些版本。
- 候选最多40个，优先题干/已有标签对 canonical name/aliases 的命中；有章节限制时只选可定位到该章节的概念。没有章节出处不静默放宽到其他章节。
- 所选 ID 必须属于本次候选集合；主/关联重复、无效 ID、范围或版本变化拒绝。不存在的新概念只保存 `new_concepts` 和 `pending_review`，没有正式节点创建路径。

ExerciseRecord 与 MistakeRecord 增加可选 `knowledge_structure`，并通过内部 extra_fields 保留未知 JSON 顶层字段；读取、编辑、保存、练习快照均继续保留扩展。旧 `question` 别名、空 chapter 及缺省状态继续兼容。数据库版本、索引、依赖和生产数据均没有迁移。

## attempt 级证据与语义分离

`mistake_attempts.data.diagnosis` 保存：attempt_id、question_revision/digest、answer_digest、教材/KG scope、errors、uncertainty、suggested/confirmed 状态。错误类型为稳定枚举，显示名称独立提供。每项错误保留 concept_ids、原作答 `[start,end)` Unicode span、精确 quote、step 行号及解释。

- 仅已由用户或确定性流程判断 wrong/partial 的真实 attempt 可提出诊断；具体方向/概念/过程错误需要多行作答、有效步骤和逐字证据。仅最终答案只能记录 final_answer_incorrect/unknown，不能归因到概念。
- 模型只能生成 suggested。显式确认要求 record revision、diagnosis digest、有效 span、当前题目版本与教材/KG 范围再次匹配；事务沿用既有幂等回执，重放不重复写。模型不能覆盖已确认诊断。
- 修改题意或参考答案会推进错题 content_revision；旧诊断保留在历史 attempt，但退出当前薄弱统计。题目修订的当前 diagnosis_status 复位为 missing。参考答案手工编辑不沿用旧生成分类的有效状态。
- 去掉强行提高到0.999/1.0及额外错题关键词 LLM 请求；保留旧关联的真实启发式分数，并明确 confidence_kind/evidence_kind。
- 题目分类、旧标签与 linked_concepts 不写 ConceptMemory 弱项。历史 linker 生成的 mistake 弱标志保留原文件，但退出当前有效弱项/摘要投影；手工标记、真实自评复习、明确困惑信号保持原流程。
- weak-points 与诊断汇总只消费已确认且版本有效的 attempt 证据。每个 attempt/概念/错因去重，并提供独立 confirmed_error_attempts，不能把各概念分组之和当作错误总数。
- 学习摘要只将知识点维度作为概念卡候选，错因名称不再变成知识点。错题查询与 counts 复用同一证据搜索词；页面将统计单位改为已确认作答次数，不把它显示成错误率。

## 接入点

- 既有习题答案生成与 `/mistakes/explain` 同次响应末尾附可选 `<texa_structure>JSON</texa_structure>`，使用明确 Schema。正文与 metadata 分离后再走原答案验证；没有第二次模型调用、独立分类模型或聊天后的新分类任务。
- 无 metadata、非法 Schema/ID 或可选 KG 损坏时保持未分类/过期并披露 metadata_status，不丢弃可用讲解正文。长/不合格作答不猜测原因。
- 既有 `/exercises/answer/save` 从本题、本教材、已完成且正文完全匹配的 Job 取得结构，并重新校验再与答案同事务保存；可显式传 knowledge_job_id。改写答案/过期 Job 不自动采用新分类。
- `GET /api/exercises/by-concept/{concept_id}?book_name=...` 根据当前 KG、精确教材身份和有效分类查询同考点习题。不会按名称跨书合并。
- `POST /api/mistakes/{mistake_id}/attempts/{attempt_id}/diagnosis` 接受 proposal，或 confirm + expected_diagnosis_digest；要求 expected_revision/operation_id。attempts 读取接口回传 diagnosis 及 digest。
- 保留原 SM-2 与重做会话。诊断建议/确认不改变 review_history、复习间隔或概念掌握度；后续真实作答的评分继续影响原复习计划。

## 验证

- Python：主目录既有 `venv310/bin/python`，实测3.10.21；所有测试 cwd 为 P1-C Worktree。相关19个文件 **205 PASS**，含20个新确定性参数化案例；覆盖单/多考点、非法ID、新概念、同名跨书/KG版本、最终答案禁止具体归因、精确步骤、确认幂等/过期、多标签去重、数据往返、旧JSON别名/缺省、ConceptMemory、原习题/错题/练习/复习和故障隔离。
- Electron壳：**24 PASS**，check通过。
- 前端：TypeScript/Vite生产构建通过；全量现有测试 **227 PASS**，修改页面ESLint通过。Vite仍有既有大chunk提示。
- 真实 macOS Electron37.10.3：隔离SQLite/合成KG/既有生产前端构建，**16项PASS**。包含保存、同考点查询、未确认排除、确认重放、证据读回、题目编辑失效，以及1280×820、1024×768、760×820已填充诊断页。三尺寸截图实际检查，不是 Astra 设计签核。
- Electron使用真实预加载与本轮API；首次配置/ready状态为明确夹具，未验证实际模型配置、后端预热、OCR或真实模型推理。QA中遇到的缺少worktree桌面依赖引用、首次导航竞争、回环origin与首次配置夹具问题均修正；不是产品模型质量测试。
- `git diff --check` 通过。仅本任务文件提交；测试产物与依赖引用不入Git。

复现Python相关回归：

```sh
/Users/jichengqian/Documents/ChatGPT/texa/venv310/bin/python -m pytest -q \
 tests/test_exercise_knowledge_structure.py tests/test_learning_memory_api.py \
 tests/test_kg_learning_summary_service.py tests/test_kg_api.py tests/test_kg_summary_cache.py \
 tests/test_exercise_bank.py tests/test_exercise_importer.py tests/test_mistake_book.py \
 tests/test_mistake_lifecycle.py tests/test_mistakes_api.py tests/test_textbook_exercise_importer.py \
 tests/test_exercise_file_importer.py tests/test_legacy_practice_partial_result.py \
 tests/test_execution_effects.py tests/test_mistake_chat_sources.py tests/test_mistake_image_lifecycle.py \
 tests/test_learning_state_v1.py tests/test_learning_state_concurrency.py tests/test_query_concepts.py
```

Electron运行 `scripts/qa-p1c-electron.cjs`，显式提供现有 `TEXA_QA_PYTHON`、`TEXA_QA_ELECTRON` 和包含playwright的 `NODE_PATH`。先在本Worktree构建 frontend；脚本创建隔离临时目录，绝不指向生产数据。

## 限制与验收结论

1. 真实 LLM 分类/错因语义质量、供应商对附加结构输出的遵从性、自由正文是否严格区分易错点与真实错因：**NOT VERIFIED**。Schema/span通过和用户确认不证明数学语义正确。
2. 没有完整的分类/诊断编辑UI；确认合同已通过真实Electron renderer→API验证，本轮界面只修正计量文案。旧标签不是新证据，缺少真实 attempt 的旧错题不会凭空补诊断。
3. 候选40个、最近最多3个合格attempt、每份作答最多6000字符。超出候选/章节映射缺失允许 unknown；不承诺隐含知识点全面召回。新概念人工审阅工作台不在本轮。
4. 同考点查询扫描既有每书JSON；规模化索引优化与跨版本canonical映射不在本轮。历史已确认诊断携带自己的KG scope，不将其悄悄重绑当前版本。
5. 未运行Windows、安装包更新/恢复、真实教材模型分类或生产数据库回放。未更改P1-A检索或P1-B验证器；其后续成果需审查后单独集成。

P1-C最小增量数据合同与确定性工程验收达到要求；真实教学内容质量验收仍待少量经授权的真实模型案例，不能宣称全部生产验收完成。
