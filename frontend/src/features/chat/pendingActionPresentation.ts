import type { AgentPendingAction } from '../../types';

type Kind = 'text' | 'strings' | 'number' | 'boolean';
type Field = readonly [key: string, label: string, kind?: Kind];
const common: Field[] = [['book_name', '教材'], ['subject', '学科']];
// Presentation only: the backend remains the authority for validation/execution.
const contracts: Record<string, { required: string[]; fields: Field[] }> = {
  add_mistake: { required: ['question_text'], fields: [['question_text', '题目'], ['user_answer', '你的答案'], ['correct_answer', '正确答案'], ['explanation', '解析'], ...common, ['chapter', '章节'], ['mistake_type', '错因类型', 'strings'], ['difficulty', '难度', 'number'], ['tags', '标签', 'strings'], ['source', '来源']] },
  mark_concept_reviewed: { required: ['name', 'quality'], fields: [['name', '概念'], ['quality', '拟记录评分', 'number'], ['book_name', '教材'], ['note', '备注']] },
  create_practice_session: { required: ['book_name', 'exercise_ids'], fields: [...common, ['exercise_ids', '题目编号', 'strings'], ['shuffle', '随机顺序', 'boolean'], ['chapter', '章节'], ['tag', '标签'], ['status', '题目状态筛选'], ['query', '检索词'], ['limit', '检索数量上限', 'number']] },
  record_practice_result: { required: ['book_name', 'session_id', 'exercise_id', 'user_answer', 'quality'], fields: [['user_answer', '你的答案'], ['quality', '拟记录评分', 'number'], ['note', '备注'], ['book_name', '教材'], ['session_id', '练习会话编号'], ['exercise_id', '习题编号']] },
  update_mistake: { required: ['book_name', 'mistake_id', 'expected_revision', 'notes'], fields: [['notes', '新备注'], ['book_name', '教材'], ['mistake_id', '错题编号'], ['expected_revision', '当前版本', 'number']] },
};
export function pendingActionPresentation(action: AgentPendingAction): { fields: { key: string; label: string; value: string }[]; unknownCount: number } | null {
  const contract = Object.hasOwn(contracts, action.type) ? contracts[action.type] : undefined;
  const payload = action.payload;
  if (!contract || !payload || contract.required.some(key => !Object.hasOwn(payload, key))) return null;
  const fields = [];
  for (const [key, label, kind = 'text'] of contract.fields) {
    if (!Object.hasOwn(payload, key)) continue;
    const value = payload[key];
    const valid = kind === 'text' ? typeof value === 'string'
      : kind === 'strings' ? typeof value === 'string' || Array.isArray(value) && value.every(item => typeof item === 'string')
      : kind === 'number' ? typeof value === 'number' && Number.isFinite(value)
      : typeof value === 'boolean';
    if (!valid) return null;
    if (contract.required.includes(key) && !['user_answer', 'notes'].includes(key)
      && (typeof value === 'string' && !value.trim() || Array.isArray(value) && !value.length)) return null;
    if (key === 'exercise_ids') {
      if (!Array.isArray(value)) return null;
      fields.push({ key: 'exercise_count', label: '题目数量', value: String(value.length) });
    }
    const text = typeof value === 'boolean' ? value ? '是' : '否'
      : key === 'quality' ? `${value} / 5`
      : Array.isArray(value) ? value.join('、') || '无'
      : value === '' ? key === 'notes' ? '清空备注' : key === 'user_answer' ? '空答案' : '未填写'
      : String(value);
    fields.push({ key, label, value: text });
  }
  return { fields, unknownCount: Object.keys(payload).filter(key => !contract.fields.some(([known]) => key === known)).length };
}
