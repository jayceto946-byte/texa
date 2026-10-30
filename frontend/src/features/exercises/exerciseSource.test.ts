import { describe, expect, it } from 'vitest';
import { exerciseSourceCategory, exerciseSubjectMatches } from './exerciseSource';
import type { ExerciseRecord } from '../../types';

describe('exercise sources and scope', () => {
  const record = { source: '传感器原理 / 第十章', origin_type: 'import_candidate' } as ExerciseRecord;
  it('keeps existing textbook imports attached to their book and honors explicit categories', () => {
    expect(exerciseSourceCategory(record, '传感器原理')).toBe('textbook_example');
    expect(exerciseSourceCategory({ ...record, source_category: 'exam' }, '传感器原理')).toBe('exam');
    expect(exerciseSourceCategory({ ...record, source: '练习册.pdf' }, '传感器原理')).toBe('exercise');
    expect(exerciseSourceCategory({ ...record, origin_type: 'manual' })).toBe('manual');
  });
  it('keeps sibling subjects separate and permits parent subject selection', () => {
    expect(exerciseSubjectMatches('数学/高数', '数学')).toBe(true);
    expect(exerciseSubjectMatches('数学/高数', '数学/线代')).toBe(false);
    expect(exerciseSubjectMatches('专业课', '专业课')).toBe(true);
  });
});
