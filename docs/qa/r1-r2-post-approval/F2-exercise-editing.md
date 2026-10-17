# F2 — 题库题干编辑（P2，F3 资源合同之后）

状态：独立待办，未实施。题干只读、参考答案可编辑的批准边界继续有效。

用户价值：修正 OCR、漏条件、公式和题目来源，避免把错误题干反复用于练习。不能通过删除重建实现，因为会失去稳定题目和作答关联。

当前能力：`ExerciseRecord` 保存 question_text、answer、explanation、image_path、ocr_text、来源/章节/标签、origin_type/id、linked_concepts、status 和 practice_history。当前端点支持新增/删除、状态、答案保存，没有题干更新 API。`ExerciseBank.update` 是整记录写入，并对带 operation_id 的 direct-practice 历史做合并，不能直接作为并发编辑合同。直接练习 history 已包含 source_snapshot；普通 practice-session 的 history/results 保存作答/质量，未冻结完整题干与答案。题目修改可能使历史作答失去可解释来源，必须显式解决这一差异。

技术阻断：无题目 revision/CAS 和编辑回执；已有练习是否引用旧题意/答案不明确；修改来源/图片不等于新来源事实；重新计算掌握状态不能靠模型判断。

推荐最小方案：保持 exercise ID；增加 revision、明确白名单 patch、expected_revision、operation_id 与同事务回执。题干/答案/附件或关键条件变化生成不可变内容版本；作答绑定该版本，旧记录无法重建时标 unknown，不回填当前内容伪造历史。普通 session 在进入题目时冻结版本，活跃练习遇到编辑需显式继续旧版或重新开始，不能静默替换。编辑界面支持 Markdown/LaTeX 预览并明确确认题意变化；内容未改变的标签/来源整理单独处理。不能删除重建，也不能顺便迁移所有学习 Runtime。

涉及模块：`memory/exercise_bank.py`、`backend/schemas.py`、`backend/api/exercises.py`、`backend/services/exercise_practice.py`、`ExerciseReader.tsx`、`usePracticeSession.ts`、候选导入、备份/恢复和历史阅读投影。

风险：历史被重解释、并发覆盖、旧练习迟到提交、版本存储增长、答案与新题干不一致。数据库/版本迁移须另行批准。

工作量：约5–8工程日，包括迁移与旧数据测试；如完整题目版本合同需要更大改动，先拆设计评审。不是本轮已授权实施项。

验收标准：保持 ID 与来源；CAS 冲突不丢编辑；operation_id 重放只更新一次、参数改变拒绝；旧/新题干及答案对应正确；历史 unknown 不伪装已知；活跃 session 与迟到作答可恢复；公式/图片/长题原文不被摘要转换；删除重建不是通过标准；两平台恢复另验。

依赖：F3 附件身份；既有 direct-practice 幂等；需先确定普通 session 的内容版本合同。F1 不阻塞纯人工编辑。
