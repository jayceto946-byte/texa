import { describe, expect, it } from 'vitest';
import { pendingActionPresentation as present } from './pendingActionPresentation';
describe('pending write presentation preserves the proposed decision', () => {
  it('keeps zero scores, false shuffle and all selected exercise ids', () => {
    expect(present({ type: 'mark_concept_reviewed', payload: { name: '极限', quality: 0 } })?.fields).toContainEqual({ key: 'quality', label: '拟记录评分', value: '0 / 5' });
    const fields = present({ type: 'create_practice_session', payload: { book_name: '教材', exercise_ids: ['a', 'b'], shuffle: false } })?.fields;
    expect(fields).toEqual(expect.arrayContaining([{ key: 'exercise_count', label: '题目数量', value: '2' }, { key: 'exercise_ids', label: '题目编号', value: 'a、b' }, { key: 'shuffle', label: '随机顺序', value: '否' }]));
  });
  it('distinguishes clearing notes and recording an empty answer', () => {
    expect(present({ type: 'update_mistake', payload: { book_name: '教材', mistake_id: 'm1', expected_revision: 1, notes: '' } })?.fields[0].value).toBe('清空备注');
    expect(present({ type: 'record_practice_result', payload: { book_name: '教材', session_id: 's1', exercise_id: 'e1', user_answer: '', quality: 2 } })?.fields[0].value).toBe('空答案');
  });
  it('retains full text, flags unknown fields, and never invents a textbook', () => {
    const question = '完整条件'.repeat(500);
    const result = present({ type: 'add_mistake', payload: { question_text: question, future_field: { value: 1 } } });
    expect(result?.fields).toEqual([{ key: 'question_text', label: '题目', value: question }]);
    expect(result?.unknownCount).toBe(1);
  });
  it('falls back to the full payload when a contract cannot be described', () => {
    for (const action of [{type:'unknown',payload:{}}, {type:'constructor',payload:{}}, {type:'mark_concept_reviewed',payload:{concept_name:'极限',quality:4}}, {type:'create_practice_session',payload:{book_name:'教材',exercise_ids:[]}}, {type:'update_mistake',payload:{book_name:'教材',mistake_id:'m1',expected_revision:1,notes:{text:'changed'}}}]) expect(present(action)).toBeNull();
  });
});
