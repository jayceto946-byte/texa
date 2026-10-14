export interface DirectPracticeInput {
  id: string;
  user_answer: string;
  quality: number;
  add_to_mistake: boolean;
}

export interface DirectPracticeOperation extends DirectPracticeInput {
  operation_id: string;
}

function storageKey(scope: string, id: string) {
  const book = scope.startsWith('?') ? new URLSearchParams(scope).get('book_name') || 'default' : scope || 'default';
  return `texa:direct-practice:v1:${encodeURIComponent(book)}:${encodeURIComponent(id)}`;
}

export function pendingDirectPractice(scope: string, id: string): DirectPracticeOperation | null {
  try {
    const stored = localStorage.getItem(storageKey(scope, id));
    return stored ? JSON.parse(stored) as DirectPracticeOperation : null;
  } catch {
    return null;
  }
}

// Persist before sending so a reload after a lost response retries the same attempt.
export function prepareDirectPractice(scope: string, input: DirectPracticeInput): DirectPracticeOperation {
  const key = storageKey(scope, input.id);
  const previous = localStorage.getItem(key);
  if (previous) {
    const stored = JSON.parse(previous) as DirectPracticeOperation;
    if (stored.id !== input.id || stored.user_answer !== input.user_answer
      || stored.quality !== input.quality || stored.add_to_mistake !== input.add_to_mistake
      || !stored.operation_id) {
      throw new Error('尚有未确认的作答，请使用原答案和相同自评重试，恢复后再开始新作答。');
    }
    return stored;
  }
  const operation = { ...input, operation_id: crypto.randomUUID() };
  localStorage.setItem(key, JSON.stringify(operation));
  return operation;
}

export function completeDirectPractice(scope: string, operation: DirectPracticeOperation) {
  const key = storageKey(scope, operation.id);
  const stored = localStorage.getItem(key);
  if (stored && (JSON.parse(stored) as DirectPracticeOperation).operation_id === operation.operation_id) {
    localStorage.removeItem(key);
  }
}
