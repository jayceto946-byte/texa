# F1 — 错题 AI 讲解草稿与明确保存（P2，有界接入）

状态：独立待办，未实施。保留 AI 页签与已保存解析；不开放旧生成写入按钮。

用户价值：围绕原始作答和教材证据解释错误，允许用户编辑后明确保存，避免覆盖人工档案。

当前行为：`POST /api/mistakes/explain` 的 `MistakeExplainRequest` 只有 id/book_name。先构造回答模型；按首个 tag 做同书检索并取片段；`MistakeBook.explain(persist=True)` 调模型后直接写 explanation；Router 再清理 thinking/LaTeX、重新读取记录、写 explanation、提取/关联概念并再次 update，最后记录 mistake_explained 学习事件。底层 update 会增加 revision，但没有 expected_revision 检查。两次写入与概念/事件副作用不在单一提交合同中。此接口也未使用完整 Final EvidencePack 发布验证合同，不能因有 RAG 就宣称教材支持充分。

技术阻断：无 operation_id；无生成前的不可变来源/revision 快照；等待模型期间人工编辑可能被覆盖；请求断开仍可能写入，客户端无法区分未执行、生成失败、已写入但回执丢失；重试可能再次付费、增加 revision、重复概念/事件。现有 `update_once` 白名单只含 notes/tags/difficulty，不能借它偷偷写 explanation。现有档案 PATCH 的 CAS/幂等可借鉴，但应扩充领域服务而非绕开它。

推荐最小方案：异步持久 job 基于 mistake ID、revision、题干/原始作答及附件 hash 冻结输入，只生成草稿；复用角色工厂及有界检索/答案验证。任务完成不写档案、概念、掌握度或 SM-2。用户编辑后通过白名单 save action，以 expected_revision + operation_id + payload hash 同事务提交 explanation 与回执。CAS 冲突保留草稿并要求核对新档案；禁止全量旧记录覆盖。事件/概念用既有可恢复副作用合同协调，至少保证稳定身份和去重；查询 job/回执恢复未知结果，不自动重发生成或写入。旧端点保留兼容策略需单独评审。

涉及模块：`backend/api/mistakes.py`、`backend/schemas.py`、`backend/services/mistake_lifecycle.py`、`backend/services/exercise_answers.py`（借鉴草稿合同）、`backend/job_manager.py`、`memory/mistake_book.py`、`memory/mistake_lifecycle.py`、错题详情领域 hook、execution effects/event 服务。

风险：并发覆盖、重复付费、草稿/正式答案混淆、迟到响应污染其他错题、不完整图片/附表生成精确结论。若需要迁移/Runtime 合同变动，先提交方案获批准；本轮不改数据库。

工作量：约5–8工程日，另需显式预算与真实模型/图片验收。F3 若缺图为 required input，应阻断生成；不得以无图文本替代完整题意。

验收标准：queued/running/completed 不写档案；保存才增加一次 revision；重复 operation_id 返回同一回执、参数不同拒绝；生成中人工编辑产生409且保稿；断线查询恢复不重复付费/写入；重启不自动付费重跑；跨题与迟到响应隔离；源文本/thinking/凭证边界有效；概念/事件去重；失败/unknown 分开；真实模型另获付费/出境授权后验证，Fixture 不能替代。

依赖：既有 JobManager、CAS/幂等领域服务、答案发布验证；图片题依赖 F3 或现有错题附件完整输入。与 F2 可独立规划，不需要全库迁移。
