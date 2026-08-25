import type { ChatMessage } from '../contexts/ChatContext';

type StoredConversationMessage = {
  id?: string;
  turn_id?: string;
  role?: string;
  content?: string;
  sources?: ChatMessage['sources'];
  linked_concepts?: ChatMessage['linkedConcepts'];
  answer_mode?: ChatMessage['answerMode'];
  suggested_answer_mode?: ChatMessage['suggestedAnswerMode'];
  scope_reason?: string;
  request_id?: string;
  answer_feedback?: ChatMessage['answerFeedback'];
  learning_task?: ChatMessage['learningTask'];
};

export function mapStoredConversationMessages(
  storedMessages: StoredConversationMessage[],
): ChatMessage[] {
  return storedMessages.map((item, index) => ({
    id: item.id || undefined,
    turnId: item.turn_id || undefined,
    requestId: item.request_id || undefined,
    role: item.role === 'assistant' ? 'assistant' : 'user',
    content: item.content || '',
    stage: item.role === 'assistant' ? 'done' : undefined,
    sources: Array.isArray(item.sources) ? item.sources : undefined,
    linkedConcepts: Array.isArray(item.linked_concepts) ? item.linked_concepts : undefined,
    answerMode: item.answer_mode || undefined,
    suggestedAnswerMode: item.suggested_answer_mode || undefined,
    scopeReason: item.scope_reason || undefined,
    answerFeedback: item.answer_feedback || undefined,
    learningTask: item.learning_task || undefined,
    originalQuestion: item.role === 'assistant' && storedMessages[index - 1]?.role === 'user'
      ? storedMessages[index - 1].content
      : undefined,
  }));
}
