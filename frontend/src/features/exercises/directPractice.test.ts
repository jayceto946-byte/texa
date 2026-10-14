import { beforeEach, describe, expect, it, vi } from 'vitest';
import { completeDirectPractice, pendingDirectPractice, prepareDirectPractice } from './directPractice';
const input = { id: 'exercise-1', user_answer: 'x', quality: 1, add_to_mistake: false };
describe('direct practice durable identity', () => {
  beforeEach(() => {
    const values = new Map<string, string>();
    vi.stubGlobal('localStorage', {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => values.set(key, value),
      removeItem: (key: string) => values.delete(key),
    });
  });
  it('reuses pending operation after lost response and reload', () => {
    const first = prepareDirectPractice('book-a', input);
    expect(prepareDirectPractice('book-a', input)).toEqual(first);
    expect(pendingDirectPractice('book-a', input.id)).toEqual(first);
  });
  it('shares identity across equivalent default and encoded book scopes', () => {
    const first = prepareDirectPractice('', input);
    expect(prepareDirectPractice('?book_name=default', input)).toEqual(first);
    const named = prepareDirectPractice('?book_name=%E9%AB%98%E6%95%B0', input);
    expect(prepareDirectPractice('高数', input)).toEqual(named);
  });
  it('blocks changing an unresolved answer and isolates books', () => {
    const first = prepareDirectPractice('book-a', input);
    expect(() => prepareDirectPractice('book-a', { ...input, quality: 5 })).toThrow('尚有未确认');
    expect(prepareDirectPractice('book-b', input).operation_id).not.toBe(first.operation_id);
  });
  it('clears only the confirmed identity and permits a new genuine attempt', () => {
    const first = prepareDirectPractice('book-a', input);
    completeDirectPractice('book-a', { ...first, operation_id: 'stale' });
    expect(pendingDirectPractice('book-a', input.id)).toEqual(first);
    completeDirectPractice('book-a', first);
    expect(pendingDirectPractice('book-a', input.id)).toBeNull();
    expect(prepareDirectPractice('book-a', input).operation_id).not.toBe(first.operation_id);
  });
});
