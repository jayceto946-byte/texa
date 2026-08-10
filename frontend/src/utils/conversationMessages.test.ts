import { describe, expect, it } from 'vitest';
import { mapStoredConversationMessages } from './conversationMessages';

describe('mapStoredConversationMessages', () => {
  it('restores persisted metadata and pairs an assistant with its user question', () => {
    const messages = mapStoredConversationMessages([
      { id: 'u1', turn_id: 't1', role: 'user', content: '什么是矩阵的秩？' },
      {
        id: 'a1',
        turn_id: 't1',
        role: 'assistant',
        content: '矩阵的秩是……',
        answer_mode: 'textbook_grounded',
        sources: [{ id: 'E1', label: '教材位置' }],
      },
    ]);

    expect(messages[1]).toMatchObject({
      id: 'a1',
      turnId: 't1',
      role: 'assistant',
      stage: 'done',
      originalQuestion: '什么是矩阵的秩？',
      answerMode: 'textbook_grounded',
    });
    expect(messages[1].sources).toHaveLength(1);
  });

  it('does not invent an original question across a pagination boundary', () => {
    const messages = mapStoredConversationMessages([
      { id: 'a2', turn_id: 't2', role: 'assistant', content: '续页回答' },
    ]);

    expect(messages[0].originalQuestion).toBeUndefined();
  });
});
