import type { ExerciseRecord } from '../../types';

export const exerciseSourceLabels: Record<string, string> = {
  textbook_example: '教材例题', exam: '真题', exercise: '习题', manual: '手动录入',
};

export function exerciseSourceCategory(record: ExerciseRecord, bookName = ''): string {
  if (record.source_category) return record.source_category;
  if (record.source_structure?.exam_source) return 'exam';
  if (record.origin_type === 'manual') return 'manual';
  // Older textbook imports retain a source label even without the new metadata.
  if (bookName && bookName !== 'default' && record.origin_type === 'import_candidate' && record.source.startsWith(`${bookName} /`)) return 'textbook_example';
  return 'exercise';
}

export function exerciseSubjectMatches(bookSubject: string, subject: string) {
  return !subject || bookSubject === subject || bookSubject.startsWith(`${subject}/`) || bookSubject === subject.split('/').at(-1);
}
