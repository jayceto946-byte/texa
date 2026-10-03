export const reviewReason: Record<string, string> = {
    image_input_not_owned: '图片未随笔记保存，请检查可读题干是否完整',
    incomplete_answer: '来源回答未完成', source_unverified: '来源回答尚未核实', missing_required_input: '缺少题干、图片、附表或其他关键输入',
    historical_evidence_text_unknown: '历史教材支持片段未保存', textbook_alignment_unknown: '原回答引用未完成段落对齐', chapter_unavailable: '章节来源不可读取',
    numeric_or_formula_support_needs_review: '数字或公式与来源的一致性待检查', user_statement_only: '内容仅来自用户自述或假设', user_edit_requires_review: '人工编辑后需重新核对来源', group_member_removed: '题干或推导组成员已删除，请检查完整性',
};
export const jobLabel: Record<string, string> = { queued: '等待整理', running: '正在生成', cancelling: '正在停止', completed: '生成已完成', failed: '生成失败', cancelled: '已取消', interrupted: '生成中断' };
